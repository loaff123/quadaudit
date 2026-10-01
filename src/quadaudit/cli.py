"""Local, offline-first corpus and evidence commands."""

from __future__ import annotations
import argparse
import csv
from fractions import Fraction
import json
import re
from pathlib import Path
import sys
from .adapters import METHODS, RunConfig
from .coverage import coverage
from .model import Case, rational
from .runner import experiment, read_results, verify_experiment_artifacts


def export_regression(case: Case) -> str:
    """A standalone exact-rounded fixture, authored here, with no QuadAudit dependency."""
    return (
        """# Original QuadAudit regression fixture; BSD-3-Clause.
# Mathematical target is a rational piecewise polynomial.
# Function evaluation is exact at each binary64 input, then rounded once.
# This costs more than ordinary floating point evaluation.
from fractions import Fraction as F
import bisect
import json
import re

CASE = json.loads("""
        + repr(json.dumps(case.to_dict(), sort_keys=True))
        + """)
REFERENCE = F(CASE['reference'])
SEGMENTS = [(F(s['left']), F(s['right']), tuple(map(F,s['coefficients']))) for s in CASE['segments']]
KNOTS = [SEGMENTS[0][0]] + [s[1] for s in SEGMENTS]

def f(x):
    x = F.from_float(float(x))
    if not KNOTS[0] <= x <= KNOTS[-1]:
        raise ValueError('outside domain')
    i = min(bisect.bisect_right(KNOTS,x)-1,len(SEGMENTS)-1)
    left,right,coefficients = SEGMENTS[i]
    t = (x-left)/(right-left)
    y = F(0)
    for c in reversed(coefficients):
        y = y*t+c
    return float(y)

if __name__ == '__main__':
    from scipy.integrate import quad
    q,e = quad(f,float(KNOTS[0]),float(KNOTS[-1]))
    actual = abs(F.from_float(q)-REFERENCE)
    print({'case':CASE['case_id'],'returned':q,'reported_error':e,'exact_actual_error':str(actual)})
"""
    )


def _load(path=None):
    from .corpus import load_corpus

    return load_corpus(Path(path) if path else None)


def _select(cases, args):
    if getattr(args, "case", None):
        wanted = set(args.case.split(","))
        cases = [c for c in cases if c.case_id in wanted]
        absent = wanted - {c.case_id for c in cases}
        if absent:
            raise ValueError("unknown case IDs: " + ", ".join(sorted(absent)))
    if getattr(args, "per_family", None):
        counts = {}
        selected = []
        for c in cases:
            n = counts.get(c.family, 0)
            if n < args.per_family:
                selected.append(c)
                counts[c.family] = n + 1
        cases = selected
    if getattr(args, "limit", None):
        cases = cases[: args.limit]
    if not cases:
        raise ValueError("no selected cases")
    return cases


def _csv(rows, path):
    fields = [
        "case_id",
        "family",
        "method",
        "track",
        "applicability",
        "outcome",
        "native_success",
        "value",
        "error_estimate",
        "accuracy",
        "estimate",
        "error_lower",
        "error_upper",
        "evaluations",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            flat = {k: row.get(k) for k in fields}
            flat.update(
                {
                    k: row.get("adjudication", {}).get(k)
                    for k in ["accuracy", "estimate", "error_lower", "error_upper"]
                }
            )
            flat["evaluations"] = row.get("work", {}).get("evaluations")
            w.writerow(flat)


def parse_tolerance(text: str) -> str:
    if not isinstance(text, str) or len(text) > 128:
        raise ValueError("tolerance text too long")
    if "/" in text:
        return str(rational(text))
    if not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]{1,3})?", text):
        raise ValueError("invalid or oversized tolerance exponent")
    exponent = int(re.split("[eE]", text)[1]) if re.search("[eE]", text) else 0
    if abs(exponent) > 400:
        raise ValueError("tolerance exponent outside supported range")
    return str(rational(Fraction(text)))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="quadaudit", description="Exact-reference quadrature reliability research preview"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("corpus", help="write the canonical built-in corpus")
    p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("verify", help="independently audit every reference")
    p.add_argument("path", nargs="?")
    p = sub.add_parser("run", help="run isolated capped experiments")
    p.add_argument("--corpus")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--methods", default=",".join(METHODS))
    p.add_argument("--tracks", default="blind,split")
    p.add_argument("--case")
    p.add_argument("--limit", type=int)
    p.add_argument("--per-family", type=int)
    p.add_argument("--atol", default="1/100000000")
    p.add_argument("--budget", type=int, default=4096)
    p.add_argument("--trace", type=int, default=0)
    p.add_argument("--precision", type=int, default=80)
    p.add_argument("--timeout", type=float, default=10)
    p.add_argument("--memory-mb", type=int)
    p.add_argument(
        "--callback-mode", choices=["exact_rounded", "native_horner"], default="exact_rounded"
    )
    p = sub.add_parser("report", help="render a standalone offline HTML evidence explorer")
    p.add_argument("experiment", type=Path)
    p.add_argument("--output", type=Path)
    p = sub.add_parser("explain", help="inspect exact problem and independent reference audit")
    p.add_argument("case_id")
    p.add_argument("--corpus")
    p = sub.add_parser(
        "export-regression", help="export a standalone exact-reference Python fixture"
    )
    p.add_argument("case_id")
    p.add_argument("--corpus")
    p.add_argument("--output", required=True, type=Path)
    p = sub.add_parser("csv", help="flatten evidence fields; JSONL remains authoritative")
    p.add_argument("results", type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "corpus":
            from .corpus import corpus_bytes

            args.output.write_bytes(corpus_bytes(_load()))
            print(args.output)
        elif args.command == "verify":
            from .corpus import verify_corpus

            result = verify_corpus(_load(args.path))
            print(json.dumps(result, indent=2))
            return 0 if result["valid"] else 2
        elif args.command == "run":
            for value in (args.limit, args.per_family):
                if value is not None and value <= 0:
                    raise ValueError("case limits must be positive")
            cases = _select(_load(args.corpus), args)
            # CLI accepts decimal/scientific tolerances, then canonicalizes exactly.
            tau = parse_tolerance(args.atol)
            configs = [
                RunConfig(
                    method=m,
                    track=t,
                    tolerance=tau,
                    budget=args.budget,
                    trace_limit=args.trace,
                    precision=args.precision,
                    callback_mode=args.callback_mode,
                )
                for m in args.methods.split(",")
                for t in args.tracks.split(",")
            ]

            def progress(n, total, row):
                if n == total or n % 25 == 0:
                    print(
                        f"{n}/{total}: {row['case_id']} {row['method']} {row['outcome']}",
                        file=sys.stderr,
                        flush=True,
                    )

            result = experiment(cases, configs, args.output, args.timeout, args.memory_mb, progress)
            print(json.dumps(result, indent=2))
        elif args.command == "report":
            from .report import render_report

            manifest = verify_experiment_artifacts(args.experiment)
            rows = list(read_results(args.experiment / "results.jsonl"))
            cases = _load(args.experiment / "corpus.jsonl")
            checked = coverage(rows, cases, manifest)
            if checked["status"] not in ("complete", "partial"):
                raise ValueError("invalid experiment schedule: " + "; ".join(checked["reasons"]))
            target = args.output or args.experiment / "report.html"
            target.write_text(render_report(rows, cases, manifest), encoding="utf-8")
            print(target)
        elif args.command in ("explain", "export-regression"):
            cases = [c for c in _load(args.corpus) if c.case_id == args.case_id]
            if not cases:
                raise ValueError("unknown case ID")
            case = cases[0]
            if args.command == "explain":
                from .oracle import audit_case

                print(
                    json.dumps({"case": case.to_dict(), "oracle_audit": audit_case(case)}, indent=2)
                )
            else:
                args.output.write_text(export_regression(case))
                print(args.output)
        elif args.command == "csv":
            _csv(list(read_results(args.results)), args.output)
            print(args.output)
        return 0
    except (ValueError, FileNotFoundError, FileExistsError, KeyError) as exc:
        print(f"quadaudit: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
