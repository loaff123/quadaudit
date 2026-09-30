"""Deterministic original corpus, canonical storage, and exact integrity audit."""

from __future__ import annotations

from collections import Counter
from fractions import Fraction as F
import hashlib
from importlib.resources import files
import json
from math import comb
from pathlib import Path

from .families import FAMILY_NAMES, build_case, family_reference
from .model import Case
from .oracle import audit_case

DEFAULT_SEED = 20260930
CASES_PER_FAMILY = 72
MAX_CORPUS_BYTES = 16 * 1024 * 1024
MAX_LINE_BYTES = 256 * 1024
MAX_CASES = 4096


def corpus_bytes(cases) -> bytes:
    """Canonical ordered JSONL: UTF-8, sorted keys, compact JSON, final newline."""
    return "".join(
        json.dumps(
            case.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
        for case in cases
    ).encode("utf-8")


def mathematical_fingerprint(case: Case) -> str:
    """Hash the function and domain, ignoring metadata and redundant subdivisions.

    Each local polynomial is expanded into global x powers, trailing zero powers
    are removed, and contiguous equal polynomial pieces are coalesced.  Functions
    on different domains are different cases.  Knot values follow the model's
    right-hand convention; redundant boundaries do not change those values.
    """
    pieces = []
    for segment in case.segments:
        coefficients = [F(0)] * len(segment.coefficients)
        width = segment.right - segment.left
        for k, ck in enumerate(segment.coefficients):
            for j in range(k + 1):
                coefficients[j] += ck * comb(k, j) * (-segment.left) ** (k - j) / width**k
        while len(coefficients) > 1 and coefficients[-1] == 0:
            coefficients.pop()
        coefficients = tuple(map(str, coefficients))
        if pieces and pieces[-1][2] == coefficients:
            pieces[-1] = (pieces[-1][0], str(segment.right), coefficients)
        else:
            pieces.append((str(segment.left), str(segment.right), coefficients))
    return hashlib.sha256(json.dumps(pieces, separators=(",", ":")).encode("ascii")).hexdigest()


class _DesignSampler:
    """Stable SHA-256 integer stream; designed sweeps are not workload samples."""

    def __init__(self, seed):
        self.seed = seed
        self.counter = 0

    def pick(self, choices):
        payload = f"quadaudit.core.v1:{self.seed}:{self.counter}".encode("ascii")
        self.counter += 1
        index = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") % len(choices)
        return choices[index]


def _power_of_two(exponent):
    return F(2**exponent) if exponent >= 0 else F(1, 2**-exponent)


def _modifiers(i, sampler):
    # Six domain widths and twelve signed amplitude levels, crossed with shapes.
    widths = [-6, -2, 0, 2, 4, 6]
    exponents = [-40, -16, -4, 0, 4, 16, 40, -8, 8, -24, 24, 0]
    return {
        "offset": str(sampler.pick([F(j, 8) for j in range(-16, 17)])),
        "width": str(_power_of_two(widths[i % len(widths)])),
        "amplitude": str(sampler.pick([-1, 1]) * _power_of_two(exponents[i // 6])),
    }


def _support(i, sampler):
    width = _power_of_two([0, -4, -12, -20][i % 4])
    left = F(0) if width == 1 else F(sampler.pick(range(1, 16)), 16) * (1 - width)
    return {"support_left": str(left), "support_right": str(left + width)}


def _shape(family, i, sampler):
    if family == "power":
        return {"n": i % 17}
    if family == "beta":
        return {"p": 1 + i % 8, "q": 1 + (i // 8) % 8, **_support(i, sampler)}
    if family == "legendre":
        return {"n": 1 + i % 16}
    if family == "chebyshev_even":
        return {"n": 1 + i % 8}
    if family == "hinge":
        return {"m": 1 + i % 16, "c": str(F(sampler.pick(range(1, 64)), 64))}
    if family == "cardinal_bspline":
        return {"degree": [1, 3, 7, 15][(i // 4) % 4], **_support(i, sampler)}
    if family == "staircase":
        count = [2, 4, 8, 16, 32, 64][i % 6]
        # Paired heights exactly cancel; a controlled final residual supplies
        # signed/nonzero and near-cancelling variants without a new family label.
        heights = []
        for _ in range(count // 2):
            height = F(sampler.pick(range(1, 16)), 8)
            heights.extend([height, -height])
        heights[-1] += [F(0), F(1, 16), F(-1, 64), F(1, 4096)][(i // 6) % 4]
        return {
            "breaks": ",".join(str(F(k, count)) for k in range(count + 1)),
            "heights": ",".join(map(str, heights)),
        }
    raise ValueError("unknown family")


def generate_corpus(seed: int = DEFAULT_SEED) -> list[Case]:
    """Generate exactly 72 distinct cases per archetype from a stable design seed."""
    if isinstance(seed, bool) or not isinstance(seed, int) or not -(2**63) <= seed < 2**63:
        raise ValueError("seed must be a signed 64-bit integer")
    sampler = _DesignSampler(seed)
    cases, seen = [], set()
    for family in FAMILY_NAMES:
        for i in range(CASES_PER_FAMILY):
            for _ in range(10000):
                parameters = {**_shape(family, i, sampler), **_modifiers(i, sampler)}
                case = build_case(family, parameters, f"{family}-{i:03d}")
                fingerprint = mathematical_fingerprint(case)
                if fingerprint not in seen:
                    seen.add(fingerprint)
                    cases.append(case)
                    break
            else:
                raise RuntimeError("unable to generate distinct designed cases")
    return cases


def verify_corpus(cases) -> dict:
    """Audit exact references and detect ID/function duplicates without raising.

    Known family metadata is also validated against its claimed mathematical
    identity and represented function.  Custom family labels receive the two
    polynomial audits but cannot claim the extra closed-form family check.
    """
    cases = list(cases)
    errors, duplicate_ids, duplicates, seen_ids, seen_functions = [], [], [], set(), {}
    counts = Counter()
    family_checks = 0
    if not cases:
        errors.append("corpus is empty")
    if len(cases) > MAX_CASES:
        errors.append(f"corpus exceeds {MAX_CASES} cases")
        return {
            "valid": False,
            "count": len(cases),
            "errors": errors,
            "sha256": None,
            "family_counts": {},
            "duplicate_ids": [],
            "mathematical_duplicates": [],
            "family_identity_checks": 0,
        }
    for index, case in enumerate(cases):
        if not isinstance(case, Case):
            errors.append(f"item {index}: not a Case")
            continue
        counts[case.family] += 1
        if case.case_id in seen_ids:
            duplicate_ids.append(case.case_id)
            errors.append(f"{case.case_id}: duplicate case identifier")
        seen_ids.add(case.case_id)
        fingerprint = mathematical_fingerprint(case)
        if fingerprint in seen_functions:
            duplicates.append([seen_functions[fingerprint], case.case_id])
            errors.append(
                f"{case.case_id}: mathematical duplicate of {seen_functions[fingerprint]}"
            )
        else:
            seen_functions[fingerprint] = case.case_id
        if not audit_case(case)["valid"]:
            errors.append(f"{case.case_id}: reference fails local/global exact integration audit")
        if case.family in FAMILY_NAMES:
            try:
                reference = family_reference(case)
                reconstructed = build_case(case.family, case.parameters, case.case_id)
                if reference != case.reference:
                    errors.append(f"{case.case_id}: reference fails family identity")
                if mathematical_fingerprint(reconstructed) != fingerprint:
                    errors.append(
                        f"{case.case_id}: coefficients/domain disagree with family parameters"
                    )
                family_checks += 1
            except (ValueError, KeyError, TypeError) as exc:
                errors.append(f"{case.case_id}: invalid family parameters: {exc}")
    valid_items = all(isinstance(case, Case) for case in cases)
    return {
        "valid": not errors,
        "count": len(cases),
        "errors": errors,
        "sha256": hashlib.sha256(corpus_bytes(cases)).hexdigest() if valid_items else None,
        "family_counts": dict(sorted(counts.items())),
        "duplicate_ids": duplicate_ids,
        "mathematical_duplicates": duplicates,
        "family_identity_checks": family_checks,
    }


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_corpus(path: Path | str | None = None) -> list[Case]:
    """Read bounded, audited JSONL; default data is also checked against its hash."""
    resource = files("quadaudit").joinpath("data/core-v1.jsonl") if path is None else Path(path)
    with resource.open("rb") as stream:
        blob = stream.read(MAX_CORPUS_BYTES + 1)
    if len(blob) > MAX_CORPUS_BYTES:
        raise ValueError("corpus exceeds byte limit")
    if path is None:
        manifest = json.loads(files("quadaudit").joinpath("data/core-v1.manifest.json").read_text())
        if hashlib.sha256(blob).hexdigest() != manifest["sha256"]:
            raise ValueError("frozen corpus hash mismatch")
    cases = []
    for lineno, line in enumerate(blob.splitlines(), 1):
        if len(cases) >= MAX_CASES or len(line) > MAX_LINE_BYTES:
            raise ValueError("corpus exceeds case or line limit")
        if not line.strip():
            raise ValueError(f"line {lineno}: empty records are not allowed")
        try:
            cases.append(Case.from_dict(json.loads(line, object_pairs_hook=_unique_object)))
        except (ValueError, TypeError, UnicodeError) as exc:
            raise ValueError(f"line {lineno}: invalid case: {exc}") from exc
    verification = verify_corpus(cases)
    if not verification["valid"]:
        raise ValueError("invalid corpus: " + "; ".join(verification["errors"][:8]))
    return cases
