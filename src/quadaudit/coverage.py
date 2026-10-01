"""Bounded identity-level coverage of an explicit experiment schedule.

A schedule is the corpus crossed with the *recorded list of configurations*, not
with the Cartesian product of the individual settings appearing in that list.
Counts alone cannot establish coverage. No result rows are removed or repaired.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import fields
import json

from .adapters import RunConfig

MAX_RUNS = 50000
_CONFIG_FIELDS = {field.name for field in fields(RunConfig)}


def _count(value):
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= MAX_RUNS


def _config_key(config):
    if not isinstance(config, dict) or set(config) != _CONFIG_FIELDS:
        raise ValueError("configuration must record every RunConfig field exactly once")
    # Validate without replacing the recorded configuration with defaulted or
    # normalized values. Every recorded field participates in the identity.
    RunConfig(**config)
    return json.dumps(config, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(case_id, config_key):
    config = json.loads(config_key)
    return {
        "case_id": case_id,
        "method": config["method"],
        "track": config["track"],
        "config": config,
    }


def coverage(rows, cases, manifest) -> dict:
    """Describe complete, partial, invalid, or unverified schedule coverage.

    ``matched_rows`` counts unique scheduled identities with coherent row labels.
    ``duplicate_rows`` counts occurrences after the first for a recorded identity;
    ``unexpected_rows`` counts rows outside the schedule or with invalid labels.
    Those diagnostic categories may overlap. ``extra_rows`` counts every row not
    needed to cover a unique scheduled identity. Without an explicit schedule,
    missing/extra counts are only count differences and status is never complete.
    """
    recorded = len(rows)
    reasons = []
    invalid = False
    if not isinstance(manifest, dict):
        manifest = {}
        reasons.append("manifest must be an object")
        invalid = True
    declared = manifest.get("expected_runs")
    expected = declared if _count(declared) else None
    result = {
        "status": "unverified",
        "recorded_rows": recorded,
        "expected_rows": expected,
        "missing_rows": max(0, expected - recorded) if expected is not None else None,
        "extra_rows": max(0, recorded - expected) if expected is not None else 0,
        "matched_rows": None,
        "duplicate_rows": 0,
        "unexpected_rows": 0,
        "duplicate_identities": [],
        "unexpected_identities": [],
        "missing_identities": [],
        "reasons": reasons,
    }
    for field in ("expected_runs", "completed_runs", "case_count"):
        if field in manifest and not _count(manifest[field]):
            reasons.append(f"invalid manifest {field} count")
            invalid = True
    if "completed_runs" in manifest and manifest["completed_runs"] != recorded:
        reasons.append("manifest completed_runs count does not match recorded rows")
        invalid = True
    if "case_count" in manifest and manifest["case_count"] != len(cases):
        reasons.append("manifest case_count does not match corpus")
        invalid = True
    if "complete" in manifest and not isinstance(manifest["complete"], bool):
        reasons.append("invalid manifest complete marker")
        invalid = True
    if expected is not None and recorded > expected:
        reasons.append("recorded row count exceeds manifest expected_runs")
        invalid = True
    if manifest.get("complete") is True and expected is not None and recorded != expected:
        reasons.append("manifest claims complete but recorded and expected counts differ")
        invalid = True
    if recorded > MAX_RUNS or len(cases) > MAX_RUNS:
        reasons.append("row or corpus count exceeds schedule limit")
        result["status"] = "invalid"
        return result
    if "protocol" not in manifest:
        reasons.append(
            "explicit protocol.configs schedule is absent; identity coverage is unverified"
        )
        result["status"] = "invalid" if invalid else "unverified"
        return result
    protocol = manifest["protocol"]
    configs = protocol.get("configs") if isinstance(protocol, dict) else None
    if not isinstance(configs, list) or not configs:
        reasons.append("protocol.configs must be a nonempty list of complete configurations")
        result["status"] = "invalid"
        return result
    if len(configs) > MAX_RUNS or len(cases) * len(configs) > MAX_RUNS:
        reasons.append("explicit schedule exceeds run count limit")
        result["status"] = "invalid"
        return result
    case_ids = []
    for case in cases:
        case_id = getattr(case, "case_id", None)
        if not isinstance(case_id, str) or not case_id:
            reasons.append("corpus has a missing or invalid case identity")
            result["status"] = "invalid"
            return result
        case_ids.append(case_id)
    if len(set(case_ids)) != len(case_ids):
        reasons.append("corpus has duplicate case identities")
        invalid = True
    config_keys = []
    for index, config in enumerate(configs):
        try:
            config_keys.append(_config_key(config))
        except (ValueError, TypeError, OverflowError) as exc:
            reasons.append(f"invalid scheduled configuration {index + 1}: {exc}")
            result["status"] = "invalid"
            return result
    if len(set(config_keys)) != len(config_keys):
        reasons.append("protocol.configs has duplicate configurations")
        invalid = True
    case_id_set, config_key_set = set(case_ids), set(config_keys)
    schedule = {(case_id, key) for case_id in case_id_set for key in config_key_set}
    result["expected_rows"] = len(schedule)
    if "expected_runs" in manifest and manifest["expected_runs"] != len(schedule):
        reasons.append("manifest expected_runs count does not match explicit schedule")
        invalid = True
    observed = Counter()
    matched = set()
    for index, row in enumerate(rows):
        problems = []
        row_identity = None
        if not isinstance(row, dict):
            problems.append("result row must be an object")
        else:
            case_id = row.get("case_id")
            if not isinstance(case_id, str) or case_id not in case_id_set:
                problems.append("unexpected or invalid case_id")
            try:
                key = _config_key(row.get("config"))
                if isinstance(case_id, str):
                    row_identity = (case_id, key)
                    observed[row_identity] += 1
                if key not in config_key_set:
                    problems.append("configuration is not scheduled")
                for field in ("method", "track"):
                    if row.get(field) != row["config"][field]:
                        problems.append(f"row {field} disagrees with recorded configuration")
            except (ValueError, TypeError, OverflowError) as exc:
                problems.append(f"invalid recorded configuration: {exc}")
        if problems:
            result["unexpected_rows"] += 1
            detail = {"row_number": index + 1, "reasons": problems}
            if isinstance(row, dict):
                detail.update(
                    {name: row.get(name) for name in ("case_id", "method", "track", "config")}
                )
            result["unexpected_identities"].append(detail)
        elif row_identity in schedule:
            matched.add(row_identity)
    for identity, count in observed.items():
        if count > 1:
            result["duplicate_rows"] += count - 1
            result["duplicate_identities"].append({**_identity(*identity), "count": count})
    missing = schedule - matched
    result.update(
        matched_rows=len(matched),
        missing_rows=len(missing),
        extra_rows=recorded - len(matched),
        missing_identities=[_identity(*identity) for identity in sorted(missing)],
    )
    if result["duplicate_rows"]:
        reasons.append(f"{result['duplicate_rows']} duplicate result rows")
        invalid = True
    if result["unexpected_rows"]:
        reasons.append(f"{result['unexpected_rows']} unexpected or invalid result identities")
        invalid = True
    if missing:
        reasons.append(f"{len(missing)} scheduled identities are missing")
        if manifest.get("complete") is True:
            reasons.append("manifest claims complete but scheduled identities are missing")
            invalid = True
    result["status"] = "invalid" if invalid else "partial" if missing else "complete"
    return result
