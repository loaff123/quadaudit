"""Run the frozen core-v1 protocol, refusing silent version/corpus drift."""

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
from quadaudit.adapters import RunConfig
from quadaudit.corpus import load_corpus, verify_corpus
from quadaudit.runner import experiment, canonical

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=ROOT / "experiments" / "preview-v1")
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    protocol_path = ROOT / "corpus" / "protocol.json"
    protocol = json.loads(protocol_path.read_text())
    cases = load_corpus()
    check = verify_corpus(cases)
    if not check["valid"] or check["sha256"] != protocol["corpus_sha256"]:
        raise SystemExit("Frozen corpus verification failed")
    for name, version in protocol["dependency_pins"].items():
        if importlib.metadata.version(name) != version:
            raise SystemExit(f"{name} version differs from frozen protocol ({version})")
    if args.check:
        print(
            json.dumps(
                {
                    "valid": True,
                    "case_count": len(cases),
                    "expected_runs": protocol["expected_runs"],
                    "protocol_sha256": hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
                },
                indent=2,
            )
        )
        return
    configs = [
        RunConfig(
            method=m,
            track=t,
            tolerance=protocol["tolerance"],
            budget=protocol["budget"],
            trace_limit=protocol["trace_limit"],
            precision=protocol["precision"],
            maxdegree=protocol["maxdegree"],
            maxlevel=protocol["maxlevel"],
        )
        for m in protocol["methods"]
        for t in protocol["tracks"]
    ]

    def progress(n, total, row):
        if n % 50 == 0 or n == total:
            print(f"{n}/{total} {row['case_id']} {row['method']} {row['outcome']}", flush=True)

    manifest = experiment(
        cases, configs, args.output, protocol["timeout_seconds"], progress=progress
    )
    manifest["frozen_protocol_sha256"] = hashlib.sha256(protocol_path.read_bytes()).hexdigest()
    manifest["frozen_protocol_id"] = protocol["protocol_id"]
    (args.output / "frozen-protocol.json").write_bytes(protocol_path.read_bytes())
    (args.output / "manifest.json").write_bytes(canonical(manifest))
    print(
        json.dumps(
            {
                "complete": manifest["complete"],
                "completed_runs": manifest["completed_runs"],
                "results_sha256": manifest["results_sha256"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
