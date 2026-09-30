"""Auditable descriptive counts, with no success-only denominators or solver ranking.

Every supplied row contributes to the overall counts. In-contract rates include
all supplied scheduled in-contract rows, including pending and failed runs. A
manifest may describe missing rows; ``summarize`` cannot infer their identities.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from fractions import Fraction
import json
import re
import hashlib

MAX_EVIDENCE_BITS = 16384
MAX_EVIDENCE_DIGITS = 4933


def evidence_fraction(value):
    """Parse bounded plain integer[/integer] evidence, never exponent notation.

    Validate lexical size before conversion. Chunked integer parsing avoids
    changing Python's process-wide decimal-string limit for legitimate outputs.
    """
    if isinstance(value, bool) or not isinstance(value, (str, int, Fraction)):
        return None
    if isinstance(value, str):
        if len(value) > 2 * MAX_EVIDENCE_DIGITS + 2:
            return None
        if not re.fullmatch(r"-?[0-9]+(?:/[1-9][0-9]*)?", value):
            return None
        numerator, _, denominator = value.partition("/")
        negative = numerator.startswith("-")
        numerator = numerator.lstrip("-")
        denominator = denominator or "1"
        if max(len(numerator), len(denominator)) > MAX_EVIDENCE_DIGITS:
            return None

        def bounded_integer(text):
            n = 0
            for start in range(0, len(text), 1000):
                part = text[start : start + 1000]
                n = n * 10 ** len(part) + int(part)
            return n

        n, d = bounded_integer(numerator), bounded_integer(denominator)
        if max(n.bit_length(), d.bit_length()) > MAX_EVIDENCE_BITS:
            return None
        return Fraction(-n if negative else n, d)
    result = Fraction(value)
    return (
        result
        if max(result.numerator.bit_length(), result.denominator.bit_length()) <= MAX_EVIDENCE_BITS
        else None
    )


def fraction_text(value):
    """Rational string without modifying interpreter integer-conversion limits."""

    def integer_text(n):
        if n.bit_length() < 12000:
            return str(n)
        sign, n = ("-", -n) if n < 0 else ("", n)
        chunks = []
        while n:
            n, remainder = divmod(n, 10**1000)
            chunks.append(remainder)
        return sign + str(chunks[-1]) + "".join(f"{c:01000d}" for c in reversed(chunks[:-1]))

    numerator = integer_text(value.numerator)
    return (
        numerator if value.denominator == 1 else numerator + "/" + integer_text(value.denominator)
    )


def configuration_identity(row):
    """All recorded settings except track identify an analysis stratum."""
    config = row.get("config")
    if not isinstance(config, dict):
        return {"id": "unknown", "label": "configuration unavailable", "config": None}
    settings = {k: v for k, v in config.items() if k != "track"}
    try:
        encoded = json.dumps(settings, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        return {"id": "unknown", "label": "configuration invalid", "config": None}
    identity = hashlib.sha256(encoded.encode()).hexdigest()
    method = config.get("method")
    precision = (
        53
        if method in ("scipy_quad", "scipy_tanhsinh")
        else config.get("precision", "?")
        if method == "mpmath_tanhsinh"
        else "?"
    )
    label = (
        f"{config.get('callback_mode', 'mode unknown')} · "
        f"τ={config.get('tolerance', '?')} · B={config.get('budget', '?')} · "
        f"output={precision} bits · {identity[:8]}"
    )
    return {"id": identity, "label": label, "config": settings}


def _label(value, default="unknown"):
    return value if isinstance(value, str) and value else default


def classifications(row: dict) -> dict:
    """Conservative display labels without mutating authoritative raw evidence."""
    outcome = _label(row.get("outcome"))
    adjudication = row.get("adjudication")
    adjudication = adjudication if isinstance(adjudication, dict) else {}
    value = row.get("value")
    complete = outcome == "returned" and evidence_fraction(value) is not None
    accuracy = _label(adjudication.get("accuracy")) if complete else "unscorable"
    if accuracy not in {"accurate", "inaccurate", "unresolved", "unscorable"}:
        accuracy = "unscorable"
    estimate = (
        _label(adjudication.get("estimate", "missing")) if outcome == "returned" else "missing"
    )
    if estimate not in {"sufficient", "underestimated", "unresolved", "missing", "invalid"}:
        estimate = "unknown"
    native = row.get("native_success")
    native = "success" if native is True else "failure" if native is False else "not_reported"
    zero = _label(adjudication.get("zero_estimate")) if complete else None
    if zero not in {"exact_zero_error", "confirmed_nonzero_error", "unresolved_error"}:
        zero = None
    diagnostics = row.get("target_diagnostics")
    diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
    attainable, zero_target = (
        diagnostics.get("target_attainable"),
        diagnostics.get("zero_meets_target"),
    )
    return {
        "outcome": outcome,
        "accuracy": accuracy,
        "estimate": estimate,
        "native_termination": native,
        "zero_estimate": zero,
        "applicability": _label(row.get("applicability")),
        "target_attainability": "attainable"
        if attainable is True
        else "unattainable"
        if attainable is False
        else "unknown",
        "zero_target": "zero_sufficient"
        if zero_target is True
        else "zero_insufficient"
        if zero_target is False
        else "unknown",
    }


def _rate(numerator, denominator):
    q = Fraction(numerator, denominator) if denominator else None
    return {
        "numerator": numerator,
        "denominator": denominator,
        "exact": str(q) if q is not None else None,
        "approx": float(q) if q is not None else None,
    }


def _aggregate(rows):
    counts = {
        k: Counter()
        for k in (
            "outcome",
            "accuracy",
            "estimate",
            "native_termination",
            "zero_estimate",
            "applicability",
            "target_attainability",
            "zero_target",
        )
    }
    for row in rows:
        for axis, label in classifications(row).items():
            if label is not None:
                counts[axis][label] += 1
    return {
        "total_rows": len(rows),
        "counts": {axis: dict(sorted(values.items())) for axis, values in counts.items()},
        "accuracy_rate": _rate(counts["accuracy"]["accurate"], len(rows)),
    }


def _with_contract(rows):
    result = _aggregate(rows)
    result["in_contract"] = _aggregate(
        [row for row in rows if row.get("applicability") == "in_contract"]
    )
    return result


def _macro(per_family):
    rates = [
        Fraction(group["in_contract"]["accuracy_rate"]["exact"])
        for group in per_family.values()
        if group["in_contract"]["total_rows"]
    ]
    macro = sum(rates, Fraction(0)) / len(rates) if rates else None
    return {
        "exact": str(macro) if macro is not None else None,
        "approx": float(macro) if macro is not None else None,
        "family_denominator": len(rates),
        "policy": "Unweighted mean of family in-contract rates; families with no in-contract rows excluded",
    }


def _paired(rows):
    groups = defaultdict(lambda: {"blind": [], "split": []})
    for i, row in enumerate(rows):
        config, track = row.get("config"), row.get("track")
        if (
            not isinstance(config, dict)
            or track not in ("blind", "split")
            or not isinstance(row.get("case_id"), str)
            or not isinstance(row.get("method"), str)
            or not row.get("case_id")
            or not row.get("method")
            or config.get("method") != row["method"]
            or config.get("track") != track
        ):
            continue
        # A changed budget, precision, callback mode, trace cap, or any other
        # configuration field prevents pairing. Never pick among duplicate runs.
        settings = {k: v for k, v in config.items() if k != "track"}
        try:
            key = (
                row["case_id"],
                row["method"],
                json.dumps(settings, sort_keys=True, separators=(",", ":"), allow_nan=False),
            )
            groups[key][track].append((i, row))
        except (TypeError, ValueError):
            continue
    pairs, transitions, contract_transitions = [], Counter(), Counter()
    ambiguous = 0
    for key, tracks in sorted(groups.items()):
        if len(tracks["blind"]) > 1 or len(tracks["split"]) > 1:
            ambiguous += 1
            continue
        if len(tracks["blind"]) != 1 or len(tracks["split"]) != 1:
            continue
        bi, blind = tracks["blind"][0]
        si, split = tracks["split"][0]
        transition = classifications(blind)["accuracy"] + " → " + classifications(split)["accuracy"]
        in_contract = all(r.get("applicability") == "in_contract" for r in (blind, split))
        transitions[transition] += 1
        if in_contract:
            contract_transitions[transition] += 1
        pairs.append(
            {
                "case_id": key[0],
                "method": key[1],
                "blind_row": bi,
                "split_row": si,
                "both_in_contract": in_contract,
                "accuracy_transition": transition,
            }
        )
    return {
        "matched_pairs": len(pairs),
        "in_contract_pairs": sum(p["both_in_contract"] for p in pairs),
        "unpaired_rows": len(rows) - 2 * len(pairs),
        "ambiguous_groups": ambiguous,
        "accuracy_transitions": dict(sorted(transitions.items())),
        "in_contract_accuracy_transitions": dict(sorted(contract_transitions.items())),
        "pairs": pairs,
        "matching_rule": "Same case, method, and complete recorded config except track; duplicate groups excluded",
    }


def summarize(rows: list[dict]) -> dict:
    """Summarize present records; retain failures and applicability exclusions.

    Fraction strings make all rates independently verifiable. Approximate rates
    are display conveniences only. Family-macro accuracy gives each family with
    at least one in-contract row equal weight, rather than pooling its size.
    """
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("results must be a list of objects")
    result = _with_contract(rows)
    families, matrix, methods = defaultdict(list), defaultdict(list), defaultdict(list)
    configurations, by_method_track = {}, defaultdict(set)
    strata = defaultdict(list)
    for row in rows:
        family = _label(row.get("family"))
        configuration = configuration_identity(row)
        cid = configuration["id"]
        configurations[cid] = configuration
        method, track = _label(row.get("method")), _label(row.get("track"))
        by_method_track[(method, track)].add(cid)
        labels = classifications(row)
        strata[(method, track, cid, labels["target_attainability"], labels["zero_target"])].append(
            row
        )
        families[family].append(row)
        matrix[(family, method, track, cid)].append(row)
        methods[(method, track, cid)].append(row)
    per_family = {family: _with_contract(group) for family, group in sorted(families.items())}
    per_method = []
    for (method, track, cid), group in sorted(methods.items()):
        method_families = defaultdict(list)
        for row in group:
            method_families[_label(row.get("family"))].append(row)
        per_method.append(
            dict(
                method=method,
                track=track,
                configuration_id=cid,
                **_with_contract(group),
                family_macro_accuracy=_macro(
                    {f: _with_contract(g) for f, g in method_families.items()}
                ),
            )
        )
    result.update(
        {
            "schema": "quadaudit.summary.v1",
            "unique_cases": len(
                {row.get("case_id") for row in rows if isinstance(row.get("case_id"), str)}
            ),
            "denominator_policy": "All supplied scheduled in-contract rows; nonreturns are not accurate. Missing manifest rows are not inferred.",
            "per_family": per_family,
            "per_method_track": per_method,
            "configurations": [configurations[key] for key in sorted(configurations)],
            "mixed_settings": any(len(ids) > 1 for ids in by_method_track.values()),
            "target_strata": [
                dict(
                    method=method,
                    track=track,
                    configuration_id=cid,
                    target_attainability=attainable,
                    zero_target=zero,
                    **_with_contract(group),
                )
                for (method, track, cid, attainable, zero), group in sorted(strata.items())
            ],
            "family_method_track": [
                dict(
                    family=family,
                    method=method,
                    track=track,
                    configuration_id=cid,
                    **_with_contract(group),
                )
                for (family, method, track, cid), group in sorted(matrix.items())
            ],
            "family_macro_accuracy": _macro(per_family),
            "paired_tracks": _paired(rows),
        }
    )
    return result
