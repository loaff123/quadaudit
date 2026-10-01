"""Exact scheduled identities, without running numerical adapters."""

from copy import deepcopy
from dataclasses import asdict
from fractions import Fraction as F
import importlib.util
import unittest

from quadaudit.adapters import RunConfig, empty_result
from quadaudit.model import Case, Segment


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.cases = [
            Case("square", "polynomial", (Segment(F(0), F(1), (F(0), F(0), F(1))),), F(1, 3)),
            Case("line", "polynomial", (Segment(F(0), F(1), (F(0), F(1))),), F(1, 2)),
        ]
        self.configs = [
            RunConfig(),
            RunConfig(method="mpmath_tanhsinh", track="split", precision=120, budget=256),
        ]
        self.rows = [empty_result(case, config) for case in self.cases for config in self.configs]
        self.manifest = {
            "protocol": {"configs": [asdict(c) for c in self.configs]},
            "case_count": 2,
            "expected_runs": 4,
            "completed_runs": 4,
            "complete": True,
        }

    def coverage(self, rows=None, cases=None, manifest=None):
        self.assertIsNotNone(
            importlib.util.find_spec("quadaudit.coverage"),
            "schedule identity validation is missing",
        )
        from quadaudit.coverage import coverage

        return coverage(
            self.rows if rows is None else rows,
            self.cases if cases is None else cases,
            self.manifest if manifest is None else manifest,
        )

    def test_heterogeneous_explicit_configs_are_complete(self):
        result = self.coverage()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["expected_rows"], 4)
        self.assertEqual(result["matched_rows"], 4)
        self.assertEqual(result["missing_rows"], 0)
        self.assertEqual(result["extra_rows"], 0)
        self.assertEqual(result["reasons"], [])

    def test_duplicate_same_count_replacement_is_invalid(self):
        rows = self.rows[:3] + [self.rows[0]]
        result = self.coverage(rows)
        self.assertEqual(result["status"], "invalid")
        self.assertEqual(result["recorded_rows"], 4)
        self.assertEqual(result["matched_rows"], 3)
        self.assertEqual(result["missing_rows"], 1)
        self.assertEqual(result["extra_rows"], 1)
        self.assertEqual(result["duplicate_rows"], 1)
        self.assertEqual(result["unexpected_rows"], 0)
        self.assertEqual(result["duplicate_identities"][0]["count"], 2)
        self.assertEqual(result["missing_identities"][0]["case_id"], "line")

    def test_honest_partial_keeps_missing_identities(self):
        manifest = dict(self.manifest, complete=False, completed_runs=3)
        result = self.coverage(self.rows[:3], manifest=manifest)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["missing_rows"], 1)
        self.assertEqual(result["extra_rows"], 0)
        self.assertEqual(len(result["missing_identities"]), 1)

    def test_falsely_complete_missing_run_is_invalid(self):
        result = self.coverage(self.rows[:3], manifest=dict(self.manifest, completed_runs=3))
        self.assertEqual(result["status"], "invalid")
        self.assertTrue(any("complete" in reason for reason in result["reasons"]))

    def test_unexpected_case_config_method_and_track_are_invalid(self):
        mutations = [
            lambda row: row.update(case_id="unknown"),
            lambda row: row["config"].update(budget=257),
            lambda row: row.update(method="scipy_tanhsinh"),
            lambda row: row.update(track="split"),
            lambda row: row["config"].update(method="scipy_tanhsinh"),
            lambda row: row["config"].update(track="split"),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                rows = deepcopy(self.rows)
                mutate(rows[0])
                result = self.coverage(rows)
                self.assertEqual(result["status"], "invalid")
                self.assertEqual(result["unexpected_rows"], 1)
                self.assertEqual(result["missing_rows"], 1)
                self.assertEqual(result["extra_rows"], 1)
                self.assertEqual(len(result["unexpected_identities"]), 1)

    def test_every_recorded_config_field_is_part_of_identity(self):
        for field, value in (
            ("trace_limit", 1),
            ("precision", 81),
            ("maxlevel", 11),
            ("maxdegree", 9),
            ("callback_mode", "native_horner"),
            ("tolerance", "1/10"),
        ):
            with self.subTest(field=field):
                rows = deepcopy(self.rows)
                rows[0]["config"][field] = value
                self.assertEqual(self.coverage(rows)["status"], "invalid")

    def test_absent_schedule_is_unverified_even_with_matching_counts(self):
        manifest = {key: value for key, value in self.manifest.items() if key != "protocol"}
        result = self.coverage(manifest=manifest)
        self.assertEqual(result["status"], "unverified")
        self.assertEqual(result["recorded_rows"], 4)
        self.assertEqual(result["expected_rows"], 4)
        self.assertTrue(result["reasons"])

    def test_absent_schedule_keeps_count_only_partial_information(self):
        result = self.coverage(self.rows[:1], manifest={"expected_runs": 8})
        self.assertEqual(result["status"], "unverified")
        self.assertEqual(result["missing_rows"], 7)

    def test_malformed_schedules_are_invalid(self):
        for protocol in (
            None,
            [],
            {},
            {"configs": None},
            {"configs": {}},
            {"configs": []},
            {"configs": [None]},
            {"configs": [{}]},
        ):
            with self.subTest(protocol=protocol):
                result = self.coverage(manifest=dict(self.manifest, protocol=protocol))
                self.assertEqual(result["status"], "invalid")
                self.assertTrue(result["reasons"])

    def test_incomplete_or_invalid_config_is_not_filled_from_defaults(self):
        for field, value in (("budget", True), ("precision", None), ("method", "unknown")):
            with self.subTest(field=field):
                manifest = deepcopy(self.manifest)
                manifest["protocol"]["configs"][0][field] = value
                self.assertEqual(self.coverage(manifest=manifest)["status"], "invalid")
        manifest = deepcopy(self.manifest)
        del manifest["protocol"]["configs"][0]["trace_limit"]
        self.assertEqual(self.coverage(manifest=manifest)["status"], "invalid")

    def test_duplicate_schedule_config_or_corpus_id_is_invalid(self):
        manifest = deepcopy(self.manifest)
        manifest["protocol"]["configs"][1] = manifest["protocol"]["configs"][0]
        self.assertEqual(self.coverage(manifest=manifest)["status"], "invalid")
        self.assertEqual(self.coverage(cases=[self.cases[0], self.cases[0]])["status"], "invalid")

    def test_declared_count_mismatches_are_invalid(self):
        for field, value in (
            ("expected_runs", 3),
            ("completed_runs", 3),
            ("case_count", 3),
            ("expected_runs", True),
            ("completed_runs", "4"),
        ):
            with self.subTest(field=field, value=value):
                result = self.coverage(manifest=dict(self.manifest, **{field: value}))
                self.assertEqual(result["status"], "invalid")
                self.assertEqual(result["recorded_rows"], 4)
                self.assertEqual(result["expected_rows"], 4)

    def test_schedule_limit_is_bounded_before_cross_product(self):
        manifest = {"protocol": {"configs": [asdict(self.configs[0])] * 50001}}
        result = self.coverage([], manifest=manifest)
        self.assertEqual(result["status"], "invalid")
        self.assertTrue(any("limit" in reason for reason in result["reasons"]))

    def test_absent_schedule_does_not_hide_false_completion_counts(self):
        result = self.coverage(
            self.rows[:3],
            manifest={
                "expected_runs": 4,
                "completed_runs": 3,
                "complete": True,
            },
        )
        self.assertEqual(result["status"], "invalid")
        self.assertTrue(any("complete" in reason for reason in result["reasons"]))

    def test_absent_schedule_does_not_hide_excess_rows(self):
        result = self.coverage(manifest={"expected_runs": 3, "completed_runs": 4})
        self.assertEqual(result["status"], "invalid")
        self.assertEqual(result["extra_rows"], 1)
