"""Regenerate the original core-v1 artifacts; default checks without changing them.

Run from the repository root with PYTHONPATH=src python corpus/freeze.py [--write].
The --write mode is intended only for a deliberate new freeze before experiments.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from quadaudit.corpus import DEFAULT_SEED, corpus_bytes, generate_corpus, verify_corpus

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "quadaudit" / "data"


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("utf-8")


def artifacts():
    cases = generate_corpus(DEFAULT_SEED)
    audit = verify_corpus(cases)
    if not audit["valid"]:
        raise ValueError(audit["errors"])
    payload = corpus_bytes(cases)
    protocol = {
        "schema": "quadaudit.protocol.v1",
        "protocol_id": "core-v1",
        "freeze_date_utc": "2026-09-30",
        "corpus_sha256": audit["sha256"],
        "case_count": 504,
        "expected_runs": 3024,
        "methods": ["scipy_quad", "scipy_tanhsinh", "mpmath_tanhsinh"],
        "tracks": ["blind", "split"],
        "tolerance": "1/100000000",
        "tolerance_kind": "absolute post-hoc target; exact rational comparisons",
        "budget": 4096,
        "timeout_seconds": 10,
        "trace_limit": 0,
        "precision": 80,
        "maxlevel": 10,
        "maxdegree": 8,
        "callback_mode": "exact_rounded",
        "callback_rounding": "exact rational evaluation followed by one nearest rounding to the active native precision",
        "callback_precision": {
            "scipy_bits": 53,
            "mpmath_configured_output_bits": 80,
            "mpmath_expected_bits": 100,
            "mpmath_note": "pinned mpmath quadrature adds 20 guard bits; record observed active callback precision",
        },
        "evaluation_counting": "charged scalar callback invocations started, including failures and repeated abscissae; completed values are separate",
        "batch_budget_policy": "a request larger than remaining capacity is denied before any member is evaluated",
        "dependency_pins": {"scipy": "1.17.0", "mpmath": "1.3.0", "numpy": "2.3.5"},
        "native_settings": {
            "scipy_quad": {"epsrel": 0, "limit": 200, "epsabs": "tolerance / number_of_pieces"},
            "scipy_tanhsinh": {
                "rtol": 0,
                "minlevel": 2,
                "maxlevel": 10,
                "atol": "tolerance / number_of_pieces",
            },
            "mpmath_tanhsinh": {
                "precision_bits": 80,
                "maxdegree": 8,
                "error": True,
                "atol": None,
                "native_success_flag": None,
            },
        },
        "split_policy": {
            "breakpoints": "all stored segment boundaries, including explicit zero pieces",
            "budget": "one shared per-run callback budget across all pieces",
            "scipy_tolerance": "absolute tolerance divided equally between pieces",
            "endpoints": "each piece uses its local polynomial extension at both endpoints",
            "value_aggregation": "exact sum of represented piece values then one native-type rounding",
            "estimate_aggregation": "exact sum of native error estimates; not a certified bound",
        },
        "applicability": {
            "blind_scipy_tanhsinh_multi_segment": "exploratory; excluded from in-contract summaries",
            "split": "each supplied segment is polynomial",
        },
        "outcome_policy": "retain all returned, budget, timeout, exception, unsupported and invalid outcomes",
        "interpretation": "designed synthetic stress cases, not samples of scientific workloads or failure probabilities",
        "trace_examples": "any later traced examples are separate explanatory reruns, not replacements",
    }
    protocol_blob = json_bytes(protocol)
    manifest = {
        "schema": "quadaudit.corpus_manifest.v1",
        "corpus_id": "core-v1",
        "freeze_date_utc": "2026-09-30",
        "seed": DEFAULT_SEED,
        "generator": "quadaudit.corpus.generate_corpus",
        "design_stream": "SHA-256 of quadaudit.core.v1:<seed>:<counter>; first 8 bytes big-endian modulo choice count",
        "case_count": len(cases),
        "family_count": 7,
        "family_counts": audit["family_counts"],
        "taxonomy": "seven classical archetypes; affine, amplitude and compact-support changes are modifiers",
        "distinct_mathematical_functions": len(cases),
        "uniqueness": "global rational polynomial coefficients, trailing-zero trimming, equal-neighbor coalescence, domain included",
        "max_degree": max(len(s.coefficients) - 1 for c in cases for s in c.segments),
        "max_segments": max(len(c.segments) for c in cases),
        "breakpoints": "exact dyadic rationals; every frozen knot is exactly binary64-representable",
        "canonical_format": "ordered UTF-8 JSONL; ASCII escapes, sorted keys, compact separators, final newline",
        "bytes": len(payload),
        "sha256": audit["sha256"],
        "protocol_sha256": hashlib.sha256(protocol_blob).hexdigest(),
        "references": [
            "independent family identity",
            "local rational polynomial antiderivative",
            "separate global-x expansion and exact endpoint integration",
        ],
        "point_checks": "direct power/beta/hinge/rectangle formulas; closed-form Legendre/Chebyshev; Cox-de Boor spline recurrence",
        "provenance": "Original synthetic construction and code. Classical formulas are not claimed as new. No copied dataset or implementation.",
        "license": "BSD-3-Clause",
        "sources": [
            "https://dlmf.nist.gov/5.12#E1",
            "https://dlmf.nist.gov/18.3",
            "https://dlmf.nist.gov/18.5",
            "https://dlmf.nist.gov/18.9",
            "https://pages.cs.wisc.edu/~deboor/toast/pages005.html",
        ],
    }
    manifest_blob = json_bytes(manifest)
    return {
        DATA / "core-v1.jsonl": payload,
        DATA / "core-v1.manifest.json": manifest_blob,
        DATA / "core-v1.protocol.json": protocol_blob,
        ROOT / "corpus" / "manifest.json": manifest_blob,
        ROOT / "corpus" / "protocol.json": protocol_blob,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    for path, payload in artifacts().items():
        if args.write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        elif not path.exists() or path.read_bytes() != payload:
            raise SystemExit(f"Frozen artifact differs: {path.relative_to(ROOT)}")
        print(f"{hashlib.sha256(payload).hexdigest()}  {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
