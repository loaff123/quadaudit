"""Post-hoc explanatory runs. These do not replace frozen-study measurements."""

import argparse
import json
from pathlib import Path
from quadaudit.adapters import METHODS, RunConfig
from quadaudit.corpus import load_corpus
from quadaudit.runner import canonical, experiment

ROOT = Path(__file__).resolve().parents[1]
SELECTED = ("beta-014", "legendre-037", "power-036")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=["traces", "grid"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = [case for case in load_corpus() if case.case_id in SELECTED]
    targets = (
        ["1/100000000"] if args.kind == "traces" else ["1/10000", "1/100000000", "1/1000000000000"]
    )
    budgets = [4096] if args.kind == "traces" else [256, 4096]
    configs = [
        RunConfig(
            method=method,
            track=track,
            tolerance=target,
            budget=budget,
            trace_limit=4096 if args.kind == "traces" else 0,
        )
        for method in METHODS
        for track in ["blind", "split"]
        for target in targets
        for budget in budgets
    ]
    manifest = experiment(cases, configs, args.output, timeout_seconds=10)
    manifest["selection"] = {
        "type": "post_hoc_explanatory",
        "case_ids": list(SELECTED),
        "reason": "Illustrate missed narrow support, large cancellation with warnings, and an output-grid accuracy floor observed in the first run.",
        "not_prevalence_evidence": True,
        "does_not_replace_frozen_run": True,
    }
    (args.output / "manifest.json").write_bytes(canonical(manifest))
    print(
        json.dumps({"complete": manifest["complete"], "runs": manifest["completed_runs"]}, indent=2)
    )


if __name__ == "__main__":
    main()
