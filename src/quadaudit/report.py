"""Dependency-free offline evidence explorer; exact values remain authoritative."""

from __future__ import annotations

from decimal import Decimal, localcontext
from fractions import Fraction
from html import escape
import json
import math
import re

from .analysis import (
    classifications,
    configuration_identity,
    evidence_fraction,
    fraction_text,
    summarize,
)
from .model import Case
from .oracle import audit_case


def _fraction(value):
    return evidence_fraction(value)


def _quantity(value):
    exact = _fraction(value)
    if exact is None:
        return {"exact": None if value is None else str(value), "approx": None}
    with localcontext() as ctx:
        ctx.prec = 6
        approximate = format(Decimal(exact.numerator) / Decimal(exact.denominator), ".6g")
    return {"exact": fraction_text(exact), "approx": approximate}


def _verified_row(row, case, reference_valid):
    """Use audited case evidence for display; keep the original row untouched."""
    effective = dict(row)
    recorded = row.get("adjudication")
    recorded = recorded if isinstance(recorded, dict) else {}
    config = row.get("config")
    config = config if isinstance(config, dict) else {}
    target = _fraction(config.get("tolerance", recorded.get("tolerance")))
    value = _fraction(row.get("value")) if row.get("outcome") == "returned" else None
    estimate = _fraction(row.get("error_estimate"))
    invalid_estimate = (row.get("error_estimate") is not None and estimate is None) or recorded.get(
        "estimate"
    ) == "invalid"
    checked = {
        "accuracy": "unscorable",
        "estimate": "invalid" if invalid_estimate else "missing",
        "error_lower": None,
        "error_upper": None,
        "zero_estimate": None,
        "tolerance": fraction_text(target) if target is not None else None,
    }
    notes = []
    if case is None:
        notes.append("Case definition unavailable; recorded accuracy claims cannot be verified.")
    elif not reference_valid:
        notes.append("Declared reference failed exact case audit; this result is unscorable.")
    elif (
        not isinstance(row.get("method"), str)
        or not isinstance(row.get("track"), str)
        or config.get("method") != row.get("method")
        or config.get("track") != row.get("track")
    ):
        notes.append(
            "Row method/track and recorded configuration are inconsistent; this result is unscorable."
        )
    elif row.get("family") != case.family:
        notes.append("Row family and case definition are inconsistent; this result is unscorable.")
    elif target is None or target < 0:
        notes.append("No valid bounded rational target; this result is unscorable.")
    elif value is not None:
        error = abs(value - case.reference)
        checked.update(
            accuracy="accurate" if error <= target else "inaccurate",
            error_lower=fraction_text(error),
            error_upper=fraction_text(error),
        )
        if estimate is not None:
            checked["estimate"] = (
                "invalid"
                if estimate < 0
                else "underestimated"
                if estimate < error
                else "sufficient"
            )
            if estimate == 0:
                checked["zero_estimate"] = (
                    "exact_zero_error" if error == 0 else "confirmed_nonzero_error"
                )
    elif row.get("outcome") == "returned":
        notes.append("Returned value is not a valid bounded rational; this result is unscorable.")
    compared = ("accuracy", "estimate", "zero_estimate", "error_lower", "error_upper")
    if any(recorded.get(key) != checked.get(key) for key in compared):
        notes.append(
            "Recorded adjudication disagrees with verified evidence; displayed classifications are recomputed. Original row retained below."
        )
    effective["adjudication"] = checked
    if (
        case
        and row.get("method") == "scipy_tanhsinh"
        and row.get("track") == "blind"
        and len(case.segments) > 1
    ):
        if row.get("applicability") != "exploratory":
            notes.append(
                "Blind multi-segment SciPy tanhsinh is exploratory; applicability corrected for summaries."
            )
        effective["applicability"] = "exploratory"
    return effective, " ".join(notes)


def _json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if value is None or isinstance(value, (bool, str, int, float)):
        return value
    return str(value)


def _embedded_json(value):
    # A JSON string's quotes do not protect against HTML's script end tag parser.
    return (
        json.dumps(_json_safe(value), ensure_ascii=True, separators=(",", ":"), allow_nan=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def _plot(case):
    sampled = []
    for segment in case.segments:
        subdivisions = max(1, min(64, 4 * (len(segment.coefficients) - 1)))
        points = []
        for i in range(subdivisions + 1):
            t = Fraction(i, subdivisions)
            x = segment.left + (segment.right - segment.left) * t
            points.append((x, segment.evaluate(x), t))
        sampled.append(points)
    # Rational normalization avoids float overflow even for huge amplitudes.
    ys = [y for points in sampled for _, y, _ in points] + [Fraction(0)]
    low, high = min(ys), max(ys)
    if low == high:
        low, high = low - 1, high + 1
    result = {
        "a": str(case.a),
        "b": str(case.b),
        "y_min": _quantity(low),
        "y_max": _quantity(high),
        "zero_y": float(-low / (high - low)),
        "segments": [],
    }
    for segment, points in zip(case.segments, sampled):
        result["segments"].append(
            {
                "left": str(segment.left),
                "right": str(segment.right),
                "points": [
                    [
                        float((x - case.a) / (case.b - case.a)),
                        float((y - low) / (high - low)),
                        float(t),
                    ]
                    for x, y, t in points
                ],
            }
        )
    return result


def _presentation(row, case):
    adj = row.get("adjudication") if isinstance(row.get("adjudication"), dict) else {}
    config = row.get("config") if isinstance(row.get("config"), dict) else {}
    work = row.get("work") if isinstance(row.get("work"), dict) else {}
    diagnostics = row.get("target_diagnostics")
    diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
    trace = row.get("trace") if isinstance(row.get("trace"), list) else []
    samples, invalid = [], 0
    if case is not None:
        for point in trace:
            x = _fraction(point.get("x")) if isinstance(point, dict) else None
            if x is None or not case.a <= x <= case.b:
                invalid += 1
                continue
            # Abscissa rug only: do not imply that rounded callback y equals f(x).
            locations = [
                [i, float((x - s.left) / (s.right - s.left))]
                for i, s in enumerate(case.segments)
                if s.left <= x <= s.right
            ]
            samples.append({"x": float((x - case.a) / (case.b - case.a)), "locations": locations})
    evaluated = work.get("evaluations")
    completed = work.get("completed_evaluations")
    count_label = (
        str(completed)
        if isinstance(completed, int) and not isinstance(completed, bool)
        else "unknown"
    )
    note = f"{len(trace)} of {count_label} completed evaluations retained in the trace."
    if not trace:
        note += " No sample abscissae were captured."
    if work.get("trace_truncated") or (isinstance(completed, int) and completed > len(trace)):
        note += " Trace truncated or disabled; these are not all evaluated points."
    if evaluated is None:
        note += " Work accounting is unavailable after worker termination."
    if invalid:
        note += f" {invalid} invalid or out-of-domain trace abscissae omitted from the plot."
    quantities = {
        name: _quantity(value)
        for name, value in {
            "reference": case.reference if case else None,
            "value": row.get("value"),
            "error_estimate": row.get("error_estimate"),
            "error_lower": adj.get("error_lower"),
            "error_upper": adj.get("error_upper"),
            "tolerance": adj.get("tolerance", config.get("tolerance")),
            "closest_representable_error": diagnostics.get("closest_representable_error"),
        }.items()
    }
    return {
        "labels": classifications(row),
        "configuration_id": configuration_identity(row)["id"],
        "quantities": quantities,
        "samples": samples,
        "trace_note": note,
        "plot_note": (
            "Segment-aware sampled sketch of the exact mathematical integrand; not a certified curve enclosure. "
            "Use a segment view to inspect narrow supports. Sample marks can overlap."
            if case
            else "Case definition unavailable; no integrand curve can be reconstructed."
        ),
    }


def _coverage(rows, manifest):
    expected = manifest.get("expected_runs")
    if not isinstance(expected, int) or isinstance(expected, bool) or expected < 0:
        expected = None
    return {
        "recorded_rows": len(rows),
        "expected_rows": expected,
        "missing_rows": max(0, expected - len(rows)) if expected is not None else None,
        "extra_rows": max(0, len(rows) - expected) if expected is not None else None,
    }


def _matrix(summary):
    groups = summary["family_method_track"]
    configurations = {c["id"]: c for c in summary["configurations"]}
    columns = sorted({(g["method"], g["track"], g["configuration_id"]) for g in groups})
    indexed = {(g["family"], g["method"], g["track"], g["configuration_id"]): g for g in groups}
    head = "".join(
        f'<th scope="col">{escape(method)}<span>{escape(track)}</span>'
        f"<span>{escape(configurations[cid]['label'])}</span></th>"
        for method, track, cid in columns
    )
    body = []
    for family in summary["per_family"]:
        cells = []
        for method, track, cid in columns:
            group = indexed.get((family, method, track, cid))
            if group is None:
                cells.append('<td class="muted">No rows</td>')
                continue
            eligible = group["in_contract"]
            rate = eligible["accuracy_rate"]
            excluded = group["total_rows"] - eligible["total_rows"]
            cells.append(
                f"<td><strong>{rate['numerator']} / {rate['denominator']}</strong>"
                f"<span>{group['total_rows']} recorded · {excluded} excluded</span></td>"
            )
        body.append(f'<tr><th scope="row">{escape(family)}</th>{"".join(cells)}</tr>')
    if not body:
        return '<p class="empty">No result rows. Run or import a study to populate this matrix.</p>'
    return (
        '<table class="matrix"><caption>Accurate / all in-contract rows, including nonreturns in '
        "the denominator. Excluded means applicability is not in_contract.</caption>"
        f'<thead><tr><th scope="col">Family</th>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>'
    )


def _strata_table(summary):
    configurations = {c["id"]: c["label"] for c in summary["configurations"]}
    body = []
    for group in summary["target_strata"]:
        rate = group["in_contract"]["accuracy_rate"]
        body.append(
            '<tr><th scope="row">'
            + escape(group["method"])
            + '<span class="sub">'
            + escape(group["track"])
            + " · "
            + escape(configurations[group["configuration_id"]])
            + "</span></th>"
            + "<td>"
            + escape(group["target_attainability"])
            + "</td><td>"
            + escape(group["zero_target"])
            + "</td><td>"
            + f"{rate['numerator']} / {rate['denominator']}</td><td>{group['total_rows']}</td></tr>"
        )
    if not body:
        body.append('<tr><td colspan="5">No recorded target strata</td></tr>')
    return (
        '<table id="target-strata" class="outcome-table"><caption>Each row is one method, track, '
        "complete recorded configuration, and target stratum. Accurate / all in-contract rows; "
        "all records remain in their original overall denominators. Unknown diagnostics stay unknown.</caption>"
        '<thead><tr><th scope="col">Method / settings</th><th scope="col">Target grid</th>'
        '<th scope="col">Zero baseline</th><th scope="col">Accurate / in-contract</th>'
        '<th scope="col">All records</th></tr></thead><tbody>' + "".join(body) + "</tbody></table>"
    )


def render_report(rows: list[dict], cases: list[Case], manifest: dict) -> str:
    """Build a standalone HTML document with raw rows and inspectable evidence.

    Missing case definitions and partial manifests are supported. Nonfinite
    metadata is retained as a string so the embedded payload remains valid JSON.
    Plot coordinates are normalized display approximations, never adjudication.
    """
    # Validate the row container before inspecting individual records.
    summarize(rows)
    manifest = manifest if isinstance(manifest, dict) else {}
    case_map = {case.case_id: case for case in cases}
    if len(case_map) != len(cases):
        raise ValueError("duplicate case identifiers in report")
    reference_validity = {}
    for key, case in case_map.items():
        try:
            reference_validity[key] = audit_case(case)["valid"]
        except (ValueError, OverflowError):
            reference_validity[key] = False
    coverage = _coverage(rows, manifest)
    effective_rows, presentation = [], []
    for row in rows:
        case = case_map.get(row.get("case_id")) if isinstance(row.get("case_id"), str) else None
        effective, integrity = _verified_row(
            row, case, reference_validity.get(case.case_id, False) if case else False
        )
        effective_rows.append(effective)
        detail = _presentation(effective, case)
        detail["integrity_note"] = integrity
        presentation.append(detail)
    summary = summarize(effective_rows)
    summary["evidence_policy"] = (
        "Display adjudication is recomputed against independently audited matching case references. Unverifiable rows are unscorable; original rows are preserved."
    )
    payload = {
        "rows": rows,
        "cases": {key: case.to_dict() for key, case in case_map.items()},
        "manifest": manifest,
        "summary": summary,
        "coverage": coverage,
        "plots": {key: _plot(case) for key, case in case_map.items()},
        "presentation": presentation,
    }
    rate = summary["in_contract"]["accuracy_rate"]
    accuracy = summary["counts"]["accuracy"]
    nonreturns = len(rows) - summary["counts"]["outcome"].get("returned", 0)
    zero_misses = summary["counts"]["zero_estimate"].get("confirmed_nonzero_error", 0)
    excluded = len(rows) - summary["in_contract"]["total_rows"]
    coverage_note = f"{len(rows):,} recorded rows"
    if coverage["expected_rows"] is not None:
        coverage_note += f" of {coverage['expected_rows']:,} scheduled"
    alerts = []
    selection = manifest.get("selection")
    if isinstance(selection, dict) and selection.get("type") == "post_hoc_explanatory":
        alerts.append(
            "Post-hoc explanatory selection: these cases were chosen after inspecting an earlier run. They do not replace the frozen study or provide independent prevalence evidence."
        )
    if summary["mixed_settings"]:
        alerts.append(
            "Mixed settings: at least one method/track has multiple recorded configurations. Matrix and method-macro scores are separated by the complete recorded settings; use the Settings filter. Overview counts and the study-wide family macro pool all recorded settings."
        )
    integrity_count = sum(bool(p["integrity_note"]) for p in presentation)
    if integrity_count:
        alerts.append(
            f"{integrity_count:,} rows need evidence attention. Displayed adjudication is recomputed against audited case definitions; missing or invalid evidence is unscorable. Inspect each row's evidence note and original record."
        )
    if coverage["missing_rows"]:
        alerts.append(
            f"{coverage['missing_rows']:,} scheduled rows are absent. Counts and rates below cover recorded rows only."
        )
    if coverage["extra_rows"]:
        alerts.append(
            f"{coverage['extra_rows']:,} extra rows exceed the manifest schedule; check provenance before interpreting rates."
        )
    if manifest.get("complete") is False or manifest.get("status") == "partial":
        alerts.append("The manifest marks this study incomplete.")
    if not rows:
        alerts.append("No result rows. Case definitions and study provenance are still retained.")
    alert_html = "".join(f'<p class="notice">{escape(text)}</p>' for text in alerts)
    replacements = {
        "@@DATA@@": _embedded_json(payload),
        "@@ROWS@@": f"{len(rows):,}",
        "@@CASES@@": str(summary["unique_cases"]),
        "@@FAMILIES@@": str(len(summary["per_family"])),
        "@@ACCURATE@@": f"{rate['numerator']:,} / {rate['denominator']:,}",
        "@@EXCLUDED@@": str(excluded),
        "@@NONRETURNS@@": str(nonreturns),
        "@@INACCURATE@@": str(accuracy.get("inaccurate", 0)),
        "@@ZERO@@": str(zero_misses),
        "@@COVERAGE@@": escape(coverage_note),
        "@@ALERTS@@": alert_html,
        "@@MATRIX@@": _matrix(summary),
        "@@STRATA@@": _strata_table(summary),
        "@@MACRO@@": escape(summary["family_macro_accuracy"]["exact"] or "not available"),
        "@@MACRO_FAMILIES@@": str(summary["family_macro_accuracy"]["family_denominator"]),
        "@@PAIR_COUNT@@": str(summary["paired_tracks"]["matched_pairs"]),
        "@@PAIR_ELIGIBLE@@": str(summary["paired_tracks"]["in_contract_pairs"]),
        "@@UNPAIRED@@": str(summary["paired_tracks"]["unpaired_rows"]),
        "@@UNATTAINABLE@@": str(summary["counts"]["target_attainability"].get("unattainable", 0)),
        "@@ATTAINABILITY_UNKNOWN@@": str(
            summary["counts"]["target_attainability"].get("unknown", 0)
        ),
        "@@ZERO_TARGET@@": str(summary["counts"]["zero_target"].get("zero_sufficient", 0)),
        "@@ZERO_TARGET_UNKNOWN@@": str(summary["counts"]["zero_target"].get("unknown", 0)),
    }
    # Substitute only tokens in the trusted template, never tokens inside data.
    return re.sub(r"@@[A-Z_]+@@", lambda match: replacements[match.group()], _TEMPLATE)


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light"><title>QuadAudit · Evidence explorer</title>
<style>
:root{--ink:#142a35;--muted:#53656e;--line:#dce3e4;--paper:#f3f6f5;--card:#fff;--teal:#086b68;--mint:#dff2ed;--amber:#875608;--red:#a3343b;--blue:#355aa5}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
a{color:var(--teal)}button,input,select{font:inherit}button,select{cursor:pointer}button{border:1px solid var(--line);border-radius:8px;background:#fff;padding:8px 13px;color:var(--ink)}button:hover{background:var(--mint);border-color:var(--teal)}button:disabled{opacity:.5;cursor:default}button:focus-visible,input:focus-visible,select:focus-visible,a:focus-visible,summary:focus-visible{outline:3px solid #2d84ce;outline-offset:3px}
.skip{position:absolute;left:14px;top:-60px;background:white;padding:10px;z-index:4}.skip:focus{top:8px}header{background:#142b35;color:#fff;padding:30px max(5vw,20px) 37px}nav{display:flex;justify-content:space-between;align-items:center;gap:20px;margin-bottom:35px}.brand{font-size:19px;font-weight:750;letter-spacing:-.6px}.brand i{font-style:normal;color:#79cfb9;margin-right:9px}.eyebrow{font-size:14px;text-transform:uppercase;letter-spacing:1.8px;font-weight:650}.hero{max-width:1400px;margin:auto}.hero h1{font-size:clamp(30px,4.1vw,51px);letter-spacing:-1.8px;line-height:1.12;margin:9px 0 16px;max-width:870px}.hero p{max-width:760px;color:#c6d8db;margin:0}.stamp{border:1px solid #58717a;border-radius:30px;padding:5px 12px;color:#cfe1df;font-size:14px}.hero-foot{display:flex;gap:25px;flex-wrap:wrap;margin-top:24px;color:#a5c9c7;font-size:14px}main{max-width:1540px;padding:27px max(4vw,18px) 50px;margin:auto}h2{font-size:21px;line-height:1.25;letter-spacing:-.5px;margin:0 0 8px}h3{font-size:16px;margin:0 0 12px}p{margin:8px 0 16px}.muted,.help{color:var(--muted)}.help{font-size:14px}.section-head{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;margin-bottom:18px}.section-head p{margin:0}.metrics{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:20px 0 25px}.metric{border:1px solid var(--line);background:#fff;border-radius:11px;padding:16px 17px}.metric strong{font-size:29px;line-height:1.2;font-weight:700;letter-spacing:-1px;display:block;margin:7px 0}.metric small{display:block;color:var(--muted);font-size:14px}.metric.accent{background:var(--mint);border-color:#b9dace}.metric .label{font-size:14px;font-weight:600}.panel{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:23px;margin-bottom:23px}.notice{border-left:3px solid #b47c1a;background:#fff7e7;padding:11px 16px;color:#674510;border-radius:0 6px 6px 0}.scroll{overflow:auto}.matrix{font-size:14px}.matrix td strong{display:block;font-variant-numeric:tabular-nums;font-size:16px}.matrix span{display:block;font-size:14px;color:var(--muted);white-space:nowrap}.matrix th span{font-weight:400;margin-top:2px}table{border-collapse:collapse;width:100%;text-align:left}th,td{padding:11px 12px;border-bottom:1px solid var(--line);vertical-align:top}thead th{background:#f6f8f8;color:#475e67;font-size:14px;text-transform:uppercase;letter-spacing:.55px;font-weight:650;white-space:nowrap}tbody th{font-weight:600}caption{text-align:left;caption-side:bottom;color:var(--muted);font-size:14px;padding:12px 0 3px}.matrix tr:last-child th,.matrix tr:last-child td{border-bottom:0}.study-notes{display:grid;grid-template-columns:1fr 1fr;gap:25px;margin-top:16px;border-top:1px solid var(--line);padding-top:15px}.study-notes p{font-size:14px;margin:0}.filters{display:grid;grid-template-columns:1.25fr repeat(6,1fr);gap:10px;padding:17px;background:#f5f8f7;border-radius:9px;margin-bottom:15px}label{font-size:14px;font-weight:650;display:block;margin-bottom:5px;color:#465c65}select,input{width:100%;height:37px;border:1px solid #cbd6d8;border-radius:6px;background:white;color:var(--ink);padding:6px 9px;min-width:0}.table-tools,.pager{display:flex;align-items:center;justify-content:space-between;gap:15px;margin:10px 0}.table-tools p{margin:0;font-size:14px}.pager{padding-top:8px}.pager div{display:flex;gap:8px}.outcome-table{font-size:14px}.outcome-table button{padding:0;border:0;background:none;color:var(--teal);font-weight:650;text-align:left;max-width:220px;overflow-wrap:anywhere}.outcome-table tbody tr:hover{background:#f4f9f7}.outcome-table tbody tr.selected{background:#e9f5f0}.outcome-table td{vertical-align:middle}.outcome-table .sub{display:block;font-size:14px;color:var(--muted);margin-top:3px}.pill{display:inline-block;border-radius:4px;padding:3px 7px;font-size:14px;font-weight:650;white-space:nowrap;background:#edf0f2;color:#50606c}.pill.accurate,.pill.sufficient{color:#176045;background:#e2f2e9}.pill.inaccurate,.pill.underestimated,.pill.invalid{background:#fdebec;color:#962d34}.pill.exploratory,.pill.unresolved,.pill.budget_exhausted{background:#fff2d6;color:#80570a}.pill.unscorable,.pill.timeout,.pill.exception{background:#eef0f5;color:#596477}.count{font-variant-numeric:tabular-nums}.empty{padding:28px;text-align:center;color:var(--muted)}.detail-head{border-bottom:1px solid var(--line);padding-bottom:17px;margin-bottom:20px}.detail-head h2{overflow-wrap:anywhere}.detail-head .kicker{font-size:14px;color:var(--teal);letter-spacing:.8px;text-transform:uppercase;margin-bottom:5px}.tags{display:flex;gap:7px;flex-wrap:wrap}.detail-grid{display:grid;grid-template-columns:minmax(0,1.18fr) minmax(0,1fr);gap:25px}.plot-box{background:#f5f8f7;border:1px solid var(--line);border-radius:9px;padding:14px}.plot-top{display:flex;align-items:center;justify-content:space-between;gap:10px}.plot-top select{max-width:215px;font-size:14px}.plot-top label{margin:0}.plot-box svg{display:block;width:100%;height:auto}.plot-note{font-size:14px;color:var(--muted);margin:7px 0 0}.legend{display:flex;gap:18px;font-size:14px;color:var(--muted)}.legend b{display:inline-block;width:15px;height:2px;vertical-align:middle;margin-right:5px;background:var(--teal)}.legend .sample{background:#af781a}.evidence-table{font-size:14px;table-layout:fixed}.evidence-table th{width:36%;font-weight:600;padding-left:0}.evidence-table td{padding-right:0;overflow-wrap:anywhere}.rational{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;color:#173e46;font-size:14px;word-break:break-all}.approx{display:block;color:var(--muted);font-size:14px;margin-top:4px}.rule{border-top:1px solid var(--line);margin:19px 0}.work-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.work-grid div{border:1px solid var(--line);border-radius:7px;padding:10px}.work-grid span{display:block;color:var(--muted);font-size:14px}.work-grid strong{font-size:18px;display:block;font-variant-numeric:tabular-nums}.detail-section{margin-top:23px}details{margin-top:13px;border:1px solid var(--line);border-radius:7px;padding:11px 14px}summary{cursor:pointer;font-size:14px;font-weight:600}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.55 ui-monospace,SFMono-Regular,Consolas,monospace;background:#f6f8f8;padding:15px;border-radius:6px;max-height:450px;overflow:auto}.caveats{display:grid;grid-template-columns:1fr 1fr;gap:22px}.caveats p{font-size:14px;margin:0 0 14px}.caveats strong{display:block;margin-bottom:4px}.footer{font-size:14px;color:var(--muted);display:flex;justify-content:space-between;gap:15px;padding:0 2px}.small-button{font-size:14px;padding:6px 10px}.main-button{background:var(--teal);color:#fff;border-color:var(--teal)}.main-button:hover{background:#064e4b;color:#fff}.axes-note{font-size:14px;border-left:2px solid #aacbc4;padding-left:12px;color:var(--muted)}
@media(max-width:1100px){.filters{grid-template-columns:repeat(3,1fr)}.metrics{grid-template-columns:repeat(3,1fr)}.detail-grid{grid-template-columns:1fr}.work-grid{grid-template-columns:repeat(4,1fr)}}
@media(max-width:620px){header{padding:23px 19px 28px}nav{margin-bottom:26px}.stamp{display:none}.metrics{grid-template-columns:1fr 1fr;gap:8px}.metric{padding:12px}.metric strong{font-size:25px}.metrics .metric:first-child{grid-column:span 2}.panel{padding:17px}.filters{grid-template-columns:1fr 1fr;padding:12px}.filters>div:first-child{grid-column:span 2}.study-notes,.caveats{grid-template-columns:1fr;gap:15px}.section-head{display:block}.section-head>button{margin-top:12px}.work-grid{grid-template-columns:1fr 1fr}.hero-foot{gap:10px 20px}.footer{display:block}.plot-top{align-items:flex-start}.plot-top select{max-width:160px}.pager{font-size:14px}.table-tools{align-items:flex-start}.table-tools button{white-space:nowrap}main{padding-top:15px}.hero h1{letter-spacing:-1px}}
@media print{header{background:white;color:var(--ink);padding:10px 0}.hero p,.hero-foot{color:var(--muted)}main{padding:0}.filters,.pager,button,.skip,nav .stamp{display:none}.panel{break-inside:avoid;border-radius:0}.detail-grid{grid-template-columns:1fr 1fr}body{background:white}.scroll{overflow:visible}.metrics{grid-template-columns:repeat(5,1fr)}}
</style></head>
<body><a class="skip" href="#explore">Skip to result explorer</a>
<header><div class="hero"><nav aria-label="Report identity"><div class="brand"><i>∫</i>QuadAudit</div><span class="stamp">Research preview · exact-reference protocol</span></nav>
<div class="eyebrow">Quadrature reliability / evidence explorer</div><h1>A returned number is only<br>the start of the evidence.</h1>
<p>Inspect numerical accuracy, estimated error, and native termination as separate questions. Every recorded outcome stays in view, including unsuccessful and exploratory runs.</p>
<div class="hero-foot"><span>@@COVERAGE@@</span><span>@@CASES@@ cases · @@FAMILIES@@ families</span><span>Offline · no external dependencies</span></div></div></header>
<main>@@ALERTS@@
<section aria-labelledby="overview-title"><div class="section-head"><div><h2 id="overview-title">Study at a glance</h2><p class="help">Descriptive counts for this fixed, designed stress corpus. These are not population failure probabilities.</p></div><button id="download-all" class="small-button">Download recorded JSONL</button></div>
<div class="metrics"><div class="metric accent"><span class="label">In-contract accurate</span><strong>@@ACCURATE@@</strong><small>All recorded in-contract rows in denominator</small></div><div class="metric"><span class="label">Inaccurate returns</span><strong>@@INACCURATE@@</strong><small>Across all applicability labels</small></div><div class="metric"><span class="label">Nonreturns / pending</span><strong>@@NONRETURNS@@</strong><small>Retained; never counted as accurate</small></div><div class="metric"><span class="label">Applicability exclusions</span><strong>@@EXCLUDED@@</strong><small>Retained outside in-contract summaries</small></div><div class="metric"><span class="label">Zero-estimate misses</span><strong>@@ZERO@@</strong><small>Zero estimate; confirmed nonzero error</small></div></div></section>
<p class="notice"><strong>@@UNATTAINABLE@@ output-grid-unattainable targets</strong> across recorded rows; @@ATTAINABILITY_UNKNOWN@@ unknown. <strong>@@ZERO_TARGET@@ targets already met by returning zero</strong>; @@ZERO_TARGET_UNKNOWN@@ unknown. These diagnostics depend on each row’s target and output precision. Unattainable targets are not evidence of solver defects, and zero-satisfying targets may be weak accuracy tests.</p>
<section class="panel" aria-labelledby="matrix-title"><div class="section-head"><div><h2 id="matrix-title">Family × method outcomes</h2><p class="help">Counts, not a general solver ranking. Matrix follows the filters below; overview cards remain study-wide.</p></div><span class="eyebrow muted">Accurate / in-contract</span></div><div class="scroll" id="matrix">@@MATRIX@@</div>
<div class="study-notes"><p><strong>Family-macro accuracy: @@MACRO@@</strong><br>Unweighted mean of @@MACRO_FAMILIES@@ family rates, each using all recorded in-contract rows. Families with no in-contract rows are excluded. This study-wide number is not a method ranking.</p><p><strong>@@PAIR_COUNT@@ exact-configuration blind/split pairs</strong><br>@@PAIR_ELIGIBLE@@ pairs have both rows in-contract; @@UNPAIRED@@ rows are unpaired. Same case, method, and complete configuration except track; duplicate groups are not matched.</p></div>
<details><summary>Accuracy by output-grid attainability and zero baseline</summary><div class="scroll">@@STRATA@@</div></details>
<details><summary>Inspect study-wide summary counts and paired row indices</summary><pre id="summary-json"></pre></details></section>
<section class="panel" id="explore" aria-labelledby="explore-title"><div class="section-head"><div><h2 id="explore-title">Follow an outcome to its evidence</h2><p class="help">Select any case to inspect its exact quantities, curve, evaluation budget, and native status.</p></div><button id="reset" class="small-button">Reset filters</button></div>
<div class="filters"><div><label for="search-filter">Find case or description</label><input id="search-filter" type="search" placeholder="Case ID or keyword" autocomplete="off"></div><div><label for="family-filter">Family</label><select id="family-filter"><option value="">All families</option></select></div><div><label for="method-filter">Method</label><select id="method-filter"><option value="">All methods</option></select></div><div><label for="track-filter">Track</label><select id="track-filter"><option value="">All tracks</option></select></div><div><label for="applicability-filter">Applicability</label><select id="applicability-filter"><option value="">All applicability</option></select></div><div><label for="accuracy-filter">Accuracy</label><select id="accuracy-filter"><option value="">All accuracy states</option></select></div><div><label for="configuration-filter">Settings</label><select id="configuration-filter"><option value="">All settings</option></select></div></div>
<div class="table-tools"><p id="result-count" role="status" aria-live="polite">@@ROWS@@ recorded rows retained</p><button id="download-filtered" class="small-button">Export filtered JSONL</button></div>
<div class="scroll"><table class="outcome-table"><caption>Accuracy is exact-reference adjudication. Native termination is reported separately in case detail.</caption><thead><tr><th scope="col">Case / family</th><th scope="col">Method / track</th><th scope="col">Applicability</th><th scope="col">Outcome</th><th scope="col">Accuracy</th><th scope="col">Estimate</th><th scope="col">Evaluations</th></tr></thead><tbody id="result-rows"></tbody></table></div>
<div class="pager"><span id="page-label"></span><div><button id="previous" class="small-button">Previous</button><button id="next" class="small-button">Next</button></div></div>
<noscript><p class="notice">JavaScript is needed for filtering and case detail. The study-wide counts and matrix above remain readable; all raw evidence is embedded in this document.</p></noscript></section>
<section class="panel" id="case-detail" aria-labelledby="detail-title"><div id="detail-content"><h2 id="detail-title">Case evidence</h2><p class="empty">Choose a recorded result to inspect its evidence.</p></div></section>
<section class="panel" aria-labelledby="reading-title"><h2 id="reading-title">How to read this study</h2><p class="help">The boundaries of the claim matter as much as the result.</p><div class="caveats"><div><p><strong>An exact reference for a mathematical model</strong>The reference is the rational integral of the declared piecewise-polynomial function. Result and error comparisons use exact represented rationals. Callback rounding, solver arithmetic, and aggregation can still affect the returned number.</p><p><strong>Two information tracks</strong>Blind runs receive the callback and domain. Split runs receive all polynomial segment boundaries and share one total evaluation budget. Split aggregation is an adapter policy; it is not a single native solver call.</p><p><strong>Applicability is a separate question</strong>Every multi-segment blind SciPy tanhsinh run is conservatively exploratory and excluded from in-contract summaries. Exploration is retained for diagnosis, regardless of whether its answer is accurate.</p></div><div><p><strong>Work counts are not full computational fairness</strong>Exact-rounded callbacks use rational evaluation and cost more than ordinary floating-point callbacks. Evaluation counts include repeated abscissae and probes; native nfev may differ. Counts do not measure full computational cost or justify speed rankings.</p><p><strong>Return, termination, and accuracy differ</strong>mpmath has no native success flag: a return is not a reported convergence success. Its precision-driven stopping criterion is not SciPy's requested absolute tolerance. Missing and zero estimates have separate meanings; “sufficient” is for this case, not a certified bound.</p><p><strong>A fixed designed corpus, not a population sample</strong>These parameterized cases probe chosen mechanisms. Family-macro rates give equal weight to eligible families; they do not estimate real-world probabilities or establish a general solver ranking. Failed, pending, unresolved, and exploratory records remain included in the evidence.</p></div></div>
<details><summary>Manifest, environment, hashes, and protocol</summary><pre id="manifest-json"></pre></details><details><summary>Complete case definitions and exact references</summary><pre id="cases-json"></pre></details></section>
<footer class="footer"><span>QuadAudit · transparent numerical experiments</span><span>Plot coordinates and decimal labels are approximate. Rational evidence is authoritative.</span></footer></main>
<script id="study-data" type="application/json">@@DATA@@</script>
<script>
(()=>{'use strict';
const data=JSON.parse(document.getElementById('study-data').textContent),rows=data.rows,p=data.presentation;
const $=id=>document.getElementById(id),esc=v=>(v!==null&&typeof v==='object'?JSON.stringify(v):String(v??'unknown')).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const lookup=(obj,id)=>typeof id==='string'&&Object.prototype.hasOwnProperty.call(obj,id)?obj[id]:undefined;
const known=new Set(['accurate','inaccurate','unscorable','unresolved','sufficient','underestimated','invalid','exploratory','budget_exhausted','timeout','exception']);
const pill=v=>'<span class="pill '+(known.has(v)?v:'')+'">'+esc(v)+'</span>';
const number=v=>typeof v==='number'&&Number.isFinite(v)?v.toLocaleString():'unknown';
const field=(r,k)=>typeof r[k]==='string'&&r[k]?r[k]:'unknown';
let filtered=rows.map((_,i)=>i),page=0,selected=rows.length?0:null;const pageSize=30;
const filters=['family','method','track','applicability','accuracy','configuration'];
const configurations=new Map(data.summary.configurations.map(c=>[c.id,c]));
const label=(i,k)=>k==='configuration'?p[i].configuration_id:k==='accuracy'||k==='applicability'?p[i].labels[k]:field(rows[i],k);
filters.forEach(k=>{const el=$(k+'-filter');[...new Set(rows.map((_,i)=>label(i,k)))].sort().forEach(v=>{const opt=document.createElement('option');opt.value=v;opt.textContent=k==='configuration'?(configurations.get(v)?.label??v):v;el.append(opt)});el.addEventListener('change',apply)});
$('search-filter').addEventListener('input',apply);$('reset').addEventListener('click',()=>{filters.forEach(k=>$(k+'-filter').value='');$('search-filter').value='';apply()});
function apply(){const query=$('search-filter').value.trim().toLowerCase();filtered=rows.map((_,i)=>i).filter(i=>filters.every(k=>!$(k+'-filter').value||label(i,k)===$(k+'-filter').value)&&(!query||[field(rows[i],'case_id'),field(rows[i],'family'),lookup(data.cases,rows[i].case_id)?.description].join(' ').toLowerCase().includes(query)));page=0;renderTable();renderMatrix();if(selected!==null&&!filtered.includes(selected)){selected=filtered[0]??null;renderDetail(false)} }
function renderTable(){const start=page*pageSize,part=filtered.slice(start,start+pageSize),eligible=filtered.filter(i=>p[i].labels.applicability==='in_contract').length;
$('result-count').textContent=filtered.length.toLocaleString()+' of '+rows.length.toLocaleString()+' recorded rows · '+eligible.toLocaleString()+' in-contract · '+(filtered.length-eligible).toLocaleString()+' excluded';
$('result-rows').innerHTML=part.length?part.map(i=>{const r=rows[i],d=p[i],w=r.work||{};return '<tr'+(i===selected?' class="selected"':'')+'><td><button data-row="'+i+'" aria-controls="case-detail">'+esc(r.case_id)+'</button><span class="sub">'+esc(r.family)+'</span></td><td>'+esc(r.method)+'<span class="sub">'+esc(r.track)+' · '+esc(r.config?.callback_mode??'callback unspecified')+'</span></td><td>'+pill(d.labels.applicability)+'</td><td>'+pill(d.labels.outcome)+'</td><td>'+pill(d.labels.accuracy)+'</td><td>'+pill(d.labels.estimate)+'</td><td class="count">'+number(w.evaluations)+'<span class="sub">budget '+number(w.budget??r.config?.budget)+'</span></td></tr>'}).join(''):'<tr><td colspan="7" class="empty">No recorded rows match these filters.</td></tr>';
$('page-label').textContent=filtered.length?'Showing '+(start+1)+'–'+Math.min(start+pageSize,filtered.length)+' of '+filtered.length:'No matching rows';$('previous').disabled=page===0;$('next').disabled=start+pageSize>=filtered.length;
$('result-rows').querySelectorAll('[data-row]').forEach(b=>b.addEventListener('click',()=>{selected=Number(b.dataset.row);renderTable();renderDetail(true)}));}
$('previous').addEventListener('click',()=>{page--;renderTable()});$('next').addEventListener('click',()=>{page++;renderTable()});
function renderMatrix(){const groups=new Map(),families=new Set(),methods=new Map();filtered.forEach(i=>{const r=rows[i],f=field(r,'family'),m=field(r,'method'),t=field(r,'track'),cid=p[i].configuration_id,key=JSON.stringify([f,m,t,cid]),col=JSON.stringify([m,t,cid]);families.add(f);methods.set(col,[m,t,cid]);if(!groups.has(key))groups.set(key,{total:0,eligible:0,accurate:0});const g=groups.get(key);g.total++;if(p[i].labels.applicability==='in_contract'){g.eligible++;if(p[i].labels.accuracy==='accurate')g.accurate++}});const cols=[...methods.values()].sort((a,b)=>a.join(' ').localeCompare(b.join(' ')));
if(!filtered.length){$('matrix').innerHTML='<p class="empty">No recorded rows match these filters.</p>';return}
$('matrix').innerHTML='<table class="matrix"><caption>Accurate / all in-contract rows, including nonreturns in the denominator. Excluded means applicability is not in_contract.</caption><thead><tr><th scope="col">Family</th>'+cols.map(([m,t,cid])=>'<th scope="col">'+esc(m)+'<span>'+esc(t)+'</span><span>'+esc(configurations.get(cid)?.label??'configuration unknown')+'</span></th>').join('')+'</tr></thead><tbody>'+[...families].sort().map(f=>'<tr><th scope="row">'+esc(f)+'</th>'+cols.map(([m,t,cid])=>{const g=groups.get(JSON.stringify([f,m,t,cid]));return g?'<td><strong>'+g.accurate+' / '+g.eligible+'</strong><span>'+g.total+' recorded · '+(g.total-g.eligible)+' excluded</span></td>':'<td class="muted">No rows</td>'}).join('')+'</tr>').join('')+'</tbody></table>';}
const qty=q=>q&&q.exact!==null?'<span class="rational">'+esc(q.exact)+'</span>'+(q.approx!==null?'<span class="approx">≈ '+esc(q.approx)+'</span>':'<span class="approx">No finite rational value available</span>'):'<span class="muted">Not available</span>';
function renderDetail(scroll){if(selected===null){$('detail-content').innerHTML='<h2 id="detail-title">Case evidence</h2><p class="empty">No selected result. Change the filters or add result rows.</p>';return}
const r=rows[selected],d=p[selected],c=lookup(data.cases,r.case_id),w=r.work||{},adj=r.adjudication||{},plot=lookup(data.plots,r.case_id),td=r.target_diagnostics||{};
const native=r.native_success===true?'Native success reported':r.native_success===false?'Native failure reported':'No native success flag reported';
const qnames=[['reference','Declared exact integral'],['value','Returned q'],['tolerance','Absolute accuracy target'],['error_lower','Exact-error lower bound'],['error_upper','Exact-error upper bound'],['error_estimate','Reported error estimate'],['closest_representable_error','Closest output-grid error']];
const quantities=qnames.map(([k,n])=>'<tr><th scope="row">'+n+'</th><td>'+qty(d.quantities[k])+'</td></tr>').join('');
const workNames=[['evaluations','Charged / started'],['completed_evaluations','Completed callbacks'],['attempted_evaluations','Requested evaluations'],['budget','Shared evaluation budget'],['callback_calls','Callback calls'],['unique_abscissae','Unique abscissae'],['denied_batch','Denied batch size'],['unused_budget','Unused budget']];
const works=workNames.map(([k,n])=>'<div><span>'+n+'</span><strong>'+number(w[k]??(k==='budget'?r.config?.budget:null))+'</strong></div>').join('');
let options='<option value="all">Full domain</option>';if(plot)plot.segments.forEach((s,i)=>{options+='<option value="'+i+'">Segment '+(i+1)+' · ['+esc(s.left)+', '+esc(s.right)+']</option>'});
$('detail-content').innerHTML='<div class="detail-head"><div class="section-head"><div><div class="kicker">Selected evidence · recorded row '+(selected+1)+'</div><h2 id="detail-title" tabindex="-1">'+esc(r.case_id)+'</h2><p class="help">'+esc(c?.description||'No case description supplied')+'</p></div><button id="download-row" class="small-button">Download this evidence</button></div><div class="tags">'+pill(field(r,'method'))+pill(field(r,'track'))+pill(d.labels.applicability)+pill(d.labels.outcome)+pill(d.labels.accuracy)+'</div></div>'+
(d.integrity_note?'<p class="notice">'+esc(d.integrity_note)+'</p>':'')+
'<div class="detail-grid"><div><div class="plot-box"><div class="plot-top"><label for="plot-view">Integrand & sample abscissae</label><select id="plot-view">'+options+'</select></div><div id="integrand-plot"></div><div class="legend"><span><b></b>Mathematical integrand sketch</span><span><b class="sample"></b>Retained abscissae</span></div><p class="plot-note">'+esc(d.plot_note)+'</p></div><p class="help">'+esc(d.trace_note)+'</p><div class="axes-note">Trace marks show where callbacks were sampled, with duplicates potentially overlapping. They do not certify a global bound on callback evaluation error.</div></div><div><h3>Exact evidence</h3><table class="evidence-table"><tbody>'+quantities+'</tbody></table><p class="help">Estimate adequacy: '+pill(d.labels.estimate)+(d.labels.zero_estimate?' · zero-estimate category: '+esc(d.labels.zero_estimate):'')+'</p><p class="help">All threshold decisions use rational arithmetic. Decimal labels are display approximations.</p></div></div>'+
'<div class="detail-section"><h3>Target and numeric precision</h3><p class="help">Target attainability: '+esc(d.labels.target_attainability)+' · Returning zero: '+esc(d.labels.zero_target)+'. Output precision: '+number(td.output_precision_bits??r.output_precision_bits)+' bits. Observed callback precision: '+esc(Array.isArray(r.callback_precision_bits_observed)?r.callback_precision_bits_observed.join(', '):'unknown')+' bits. Precision-driven methods may evaluate callbacks at higher precision than their final output.</p></div>'+
'<div class="detail-section"><h3>Termination is separate from correctness</h3><p>'+esc(native)+' · '+pill(d.labels.accuracy)+'</p><p class="help">'+esc(r.message||r.applicability_note||'No additional native or applicability message.')+'</p><div class="work-grid">'+works+'</div><p class="help">Charged / started evaluations can include a callback that raised. Completed callbacks are separate. Missing accounting is unknown, never zero. Native nfev and elapsed time are preserved in raw evidence below.</p></div>'+
'<details><summary>Native pieces, warnings, settings, aggregation, and complete retained trace</summary><pre id="row-json"></pre></details><details><summary>Selected case definition</summary><pre id="case-json"></pre></details>';
$('row-json').textContent=JSON.stringify(r,null,2);$('case-json').textContent=JSON.stringify(c??{message:'Case definition unavailable'},null,2);
$('download-row').addEventListener('click',()=>download('quadaudit-evidence.json',JSON.stringify({row:r,case:c??null,manifest:data.manifest},null,2),'application/json'));
$('plot-view').addEventListener('change',renderPlot);renderPlot();if(scroll){$('case-detail').scrollIntoView({behavior:'smooth',block:'start'});$('detail-title').focus({preventScroll:true})}}
function renderPlot(){const d=p[selected],plot=lookup(data.plots,rows[selected].case_id);if(!plot){$('integrand-plot').innerHTML='<p class="empty">Integrand definition unavailable</p>';return}const view=$('plot-view').value,index=view==='all'?null:Number(view),segs=index===null?plot.segments:[plot.segments[index]],x=v=>52+v*550,y=v=>220-v*180;
let svg='<svg viewBox="0 0 630 290" role="img" aria-labelledby="curve-title curve-desc"><title id="curve-title">Integrand and retained evaluation abscissae</title><desc id="curve-desc">'+esc(d.plot_note+' '+d.trace_note)+'</desc><rect x="52" y="40" width="550" height="180" fill="#fff"/>';
[0,.25,.5,.75,1].forEach(v=>{svg+='<line x1="52" y1="'+y(v)+'" x2="602" y2="'+y(v)+'" stroke="#e7ecec"/>'});svg+='<line x1="52" y1="'+y(plot.zero_y)+'" x2="602" y2="'+y(plot.zero_y)+'" stroke="#aebdc0" stroke-dasharray="3 3"/>';
segs.forEach(s=>{const path=s.points.map((v,i)=>(i?'L':'M')+x(index===null?v[0]:v[2]).toFixed(3)+','+y(v[1]).toFixed(3)).join(' ');svg+='<path d="'+path+'" fill="none" stroke="#087b70" stroke-width="2.3" stroke-linejoin="round"/>'});
d.samples.forEach(s=>{const location=index===null?s.x:s.locations.find(v=>v[0]===index)?.[1];if(location!==undefined)svg+='<line x1="'+x(location).toFixed(3)+'" y1="234" x2="'+x(location).toFixed(3)+'" y2="244" stroke="#ac781a" stroke-width="1" opacity=".62"/>'});
const left=index===null?plot.a:segs[0].left,right=index===null?plot.b:segs[0].right;
svg+='<text x="48" y="31" font-size="10" fill="#53656e">f(x), approximate scale</text><text x="52" y="264" font-size="10" fill="#53656e">'+esc(left)+'</text><text x="602" y="264" text-anchor="end" font-size="10" fill="#53656e">'+esc(right)+'</text><text x="8" y="44" font-size="9" fill="#53656e">'+esc(plot.y_max.approx)+'</text><text x="8" y="223" font-size="9" fill="#53656e">'+esc(plot.y_min.approx)+'</text><text x="327" y="282" text-anchor="middle" font-size="10" fill="#53656e">x · '+(index===null?'full domain':'segment '+(index+1))+'</text></svg>';$('integrand-plot').innerHTML=svg;}
function download(name,body,type){const url=URL.createObjectURL(new Blob([body],{type})),a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000)}
const jsonl=indices=>indices.map(i=>JSON.stringify(rows[i])).join('\n')+(indices.length?'\n':'');
$('download-all').addEventListener('click',()=>download('quadaudit-results.jsonl',jsonl(rows.map((_,i)=>i)),'application/x-ndjson'));
$('download-filtered').addEventListener('click',()=>download('quadaudit-filtered.jsonl',jsonl(filtered),'application/x-ndjson'));
$('summary-json').textContent=JSON.stringify(data.summary,null,2);$('manifest-json').textContent=JSON.stringify(data.manifest,null,2);$('cases-json').textContent=JSON.stringify(data.cases,null,2);renderTable();renderDetail(false);
})();
</script></body></html>"""
