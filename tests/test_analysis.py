"""Summary denominators are evidence, rather than success-only leaderboards."""

import copy
import unittest

from quadaudit.analysis import summarize


def row(case="a", family="bumps", method="scipy_quad", track="blind", **changes):
    result = {
        "case_id": case,
        "family": family,
        "method": method,
        "track": track,
        "config": {
            "method": method,
            "track": track,
            "budget": 100,
            "tolerance": "1/100",
            "callback_mode": "exact_rounded",
        },
        "applicability": "in_contract",
        "outcome": "returned",
        "value": "1",
        "native_success": True,
        "error_estimate": "0",
        "adjudication": {
            "accuracy": "accurate",
            "estimate": "sufficient",
            "zero_estimate": "exact_zero_error",
        },
    }
    result.update(changes)
    return result


class AnalysisTests(unittest.TestCase):
    def test_all_in_contract_rows_are_denominator_including_nonreturns(self):
        rows = [
            row(),
            row("b", outcome="timeout", value=None, native_success=None),
            row("c", outcome="budget_exhausted", value=None, native_success=None),
            row("d", applicability="exploratory"),
        ]
        before = copy.deepcopy(rows)
        result = summarize(rows)
        self.assertEqual(result["total_rows"], 4)
        self.assertEqual(result["in_contract"]["total_rows"], 3)
        self.assertEqual(
            result["in_contract"]["accuracy_rate"],
            {"numerator": 1, "denominator": 3, "exact": "1/3", "approx": 1 / 3},
        )
        self.assertEqual(result["counts"]["outcome"]["timeout"], 1)
        self.assertEqual(result["counts"]["accuracy"]["unscorable"], 2)
        self.assertEqual(rows, before)

    def test_family_macro_is_unweighted_and_reports_its_denominator(self):
        rows = [
            row("a", family="small"),
            row("b", family="large", outcome="exception", value=None),
            row("c", family="large", outcome="unsupported", value=None),
            row("d", family="excluded", applicability="exploratory"),
        ]
        result = summarize(rows)
        self.assertEqual(result["family_macro_accuracy"]["exact"], "1/2")
        self.assertEqual(result["family_macro_accuracy"]["family_denominator"], 2)
        self.assertEqual(result["per_family"]["large"]["in_contract"]["total_rows"], 2)
        self.assertIsNone(result["per_family"]["excluded"]["in_contract"]["accuracy_rate"]["exact"])

    def test_native_success_missing_is_not_success(self):
        result = summarize([row(method="mpmath_tanhsinh", native_success=None)])
        self.assertEqual(result["counts"]["native_termination"]["not_reported"], 1)
        self.assertEqual(result["counts"]["native_termination"].get("success", 0), 0)
        self.assertEqual(result["counts"]["accuracy"]["accurate"], 1)

    def test_estimate_categories_and_zero_estimates_are_retained(self):
        rows = [
            row(),
            row(
                "b",
                adjudication={
                    "accuracy": "inaccurate",
                    "estimate": "underestimated",
                    "zero_estimate": "confirmed_nonzero_error",
                },
            ),
            row(
                "c",
                adjudication={
                    "accuracy": "unresolved",
                    "estimate": "unresolved",
                    "zero_estimate": "unresolved_error",
                },
            ),
        ]
        result = summarize(rows)
        self.assertEqual(sum(result["counts"]["estimate"].values()), 3)
        self.assertEqual(
            result["counts"]["zero_estimate"],
            {"exact_zero_error": 1, "confirmed_nonzero_error": 1, "unresolved_error": 1},
        )

    def test_pairing_requires_case_method_and_equal_config_except_track(self):
        blind = row()
        split = row(track="split")
        changed = row("b", track="split")
        changed["config"]["budget"] = 999
        rows = [blind, split, row("b"), changed, row("other", track="split")]
        result = summarize(rows)
        self.assertEqual(result["paired_tracks"]["matched_pairs"], 1)
        self.assertEqual(result["paired_tracks"]["unpaired_rows"], 3)
        self.assertEqual(result["paired_tracks"]["in_contract_pairs"], 1)
        self.assertEqual(
            result["paired_tracks"]["accuracy_transitions"], {"accurate → accurate": 1}
        )

    def test_duplicate_and_missing_config_rows_are_not_arbitrarily_paired(self):
        result = summarize(
            [
                row(),
                row(),
                row(track="split"),
                row("b", config=None),
                row("b", track="split", config=None),
            ]
        )
        self.assertEqual(result["paired_tracks"]["matched_pairs"], 0)
        self.assertEqual(result["paired_tracks"]["unpaired_rows"], 5)
        self.assertEqual(result["paired_tracks"]["ambiguous_groups"], 1)

    def test_empty_and_malformed_rows_are_not_fabricated_as_successes(self):
        empty = summarize([])
        self.assertEqual(empty["total_rows"], 0)
        self.assertIsNone(empty["family_macro_accuracy"]["exact"])
        result = summarize(
            [
                {},
                row(outcome="returned", value=None),
                row("b", applicability="unknown", native_success="yes"),
            ]
        )
        self.assertEqual(result["in_contract"]["total_rows"], 1)
        self.assertEqual(result["counts"]["accuracy"]["unscorable"], 2)
        self.assertEqual(result["counts"]["native_termination"].get("success", 0), 1)

    def test_matrix_counts_all_rows_in_every_group(self):
        rows = [row(), row("b", track="split"), row("c", method="mpmath_tanhsinh")]
        result = summarize(rows)
        self.assertEqual(sum(g["total_rows"] for g in result["family_method_track"]), 3)
        self.assertEqual(len(result["family_method_track"]), 3)

    def test_malformed_nonfinite_values_cannot_be_counted_accurate(self):
        rows = [row(str(i), value=value) for i, value in enumerate(["NaN", "Infinity", {}, "1/0"])]
        result = summarize(rows)
        self.assertEqual(result["in_contract"]["accuracy_rate"]["numerator"], 0)
        self.assertEqual(result["counts"]["accuracy"]["unscorable"], 4)

    def test_target_diagnostics_are_separate_with_unknown_preserved(self):
        rows = [
            row("a", target_diagnostics={"target_attainable": False, "zero_meets_target": False}),
            row("b", target_diagnostics={"target_attainable": True, "zero_meets_target": True}),
            row("c"),
        ]
        result = summarize(rows)
        self.assertEqual(
            result["counts"]["target_attainability"],
            {"attainable": 1, "unattainable": 1, "unknown": 1},
        )
        self.assertEqual(
            result["counts"]["zero_target"],
            {"zero_sufficient": 1, "zero_insufficient": 1, "unknown": 1},
        )
        self.assertEqual(result["in_contract"]["accuracy_rate"]["denominator"], 3)

    def test_invalid_estimate_is_retained_even_when_returned_value_is_unscorable(self):
        result = summarize(
            [row(value=None, adjudication={"accuracy": "unscorable", "estimate": "invalid"})]
        )
        self.assertEqual(result["counts"]["estimate"], {"invalid": 1})

    def test_family_macro_is_also_available_per_method_track(self):
        rows = [
            row("a", family="small"),
            row("b", family="large", outcome="timeout", value=None),
            row("c", family="large", outcome="timeout", value=None),
            row("d", family="large", method="mpmath_tanhsinh"),
        ]
        result = summarize(rows)
        groups = {g["method"]: g for g in result["per_method_track"]}
        self.assertEqual(groups["scipy_quad"]["family_macro_accuracy"]["exact"], "1/2")
        self.assertEqual(groups["scipy_quad"]["family_macro_accuracy"]["family_denominator"], 2)
        self.assertEqual(groups["mpmath_tanhsinh"]["family_macro_accuracy"]["exact"], "1")

    def test_malformed_adjudication_labels_are_retained_as_unknown_not_crashes(self):
        result = summarize(
            [row(adjudication={"accuracy": [], "estimate": {}, "zero_estimate": []})]
        )
        self.assertEqual(result["counts"]["accuracy"], {"unscorable": 1})
        self.assertEqual(result["counts"]["estimate"], {"unknown": 1})
        self.assertEqual(result["counts"]["zero_estimate"], {})

    def test_mixed_callback_settings_have_separate_method_and_matrix_denominators(self):
        a, b = row("a"), row("b", outcome="timeout", value=None)
        b["config"]["callback_mode"] = "native_horner"
        result = summarize([a, b])
        self.assertTrue(result["mixed_settings"])
        self.assertEqual(len(result["family_method_track"]), 2)
        self.assertEqual(len(result["per_method_track"]), 2)
        self.assertEqual(
            sorted(g["in_contract"]["accuracy_rate"]["exact"] for g in result["per_method_track"]),
            ["0", "1"],
        )
        self.assertEqual(len(result["configurations"]), 2)

    def test_target_strata_keep_all_rows_and_method_configuration_denominators(self):
        rows = [
            row(
                "a",
                target_diagnostics={"target_attainable": False, "zero_meets_target": False},
                adjudication={"accuracy": "inaccurate", "estimate": "underestimated"},
            ),
            row("b", target_diagnostics={"target_attainable": True, "zero_meets_target": True}),
            row("c", outcome="timeout", value=None),
            row("d", applicability="exploratory"),
        ]
        result = summarize(rows)
        self.assertEqual(sum(s["total_rows"] for s in result["target_strata"]), 4)
        self.assertEqual(sum(s["in_contract"]["total_rows"] for s in result["target_strata"]), 3)
        strata = {s["target_attainability"]: s for s in result["target_strata"]}
        self.assertEqual(strata["unattainable"]["in_contract"]["accuracy_rate"]["exact"], "0")
        self.assertEqual(strata["attainable"]["in_contract"]["accuracy_rate"]["exact"], "1")
        self.assertEqual(strata["unknown"]["in_contract"]["accuracy_rate"]["denominator"], 1)
        self.assertTrue(
            all("method" in s and "configuration_id" in s for s in result["target_strata"])
        )

    def test_configuration_label_uses_effective_output_precision(self):
        from quadaudit.analysis import configuration_identity

        scipy = row(config={"method": "scipy_quad", "track": "blind", "precision": 80})
        mp = row(
            method="mpmath_tanhsinh",
            config={"method": "mpmath_tanhsinh", "track": "blind", "precision": 80},
        )
        self.assertIn("output=53 bits", configuration_identity(scipy)["label"])
        self.assertIn("output=80 bits", configuration_identity(mp)["label"])


if __name__ == "__main__":
    unittest.main()
