import importlib.util
import unittest
from fractions import Fraction as F
from unittest.mock import patch
from quadaudit.model import Case, Segment
from quadaudit.adapters import RunConfig, run_case
from quadaudit.instrumentation import represented


@unittest.skipUnless(
    all(importlib.util.find_spec(m) for m in ("scipy", "numpy", "mpmath")),
    "optional solver dependencies not installed",
)
class NumericalReviewRegressions(unittest.TestCase):
    def test_mpf_nonfinite_rejected(self):
        import mpmath as mp

        for x in [mp.inf, -mp.inf, mp.nan]:
            with self.subTest(x=x), self.assertRaises(ValueError):
                represented(x)

    def test_invalid_estimate_keeps_finite_accuracy(self):
        c = Case("zero", "power", (Segment(F(0), F(1), (F(0),)),), F(0))
        with patch("scipy.integrate.quad", return_value=(0.0, float("nan"), {"neval": 0})):
            r = run_case(c, RunConfig())
        self.assertEqual(r["outcome"], "returned")
        self.assertEqual(r["value"], "0")
        self.assertEqual(r["adjudication"]["accuracy"], "accurate")
        self.assertEqual(r["adjudication"]["estimate"], "invalid")

    def test_negative_piece_cannot_be_hidden(self):
        c = Case(
            "zero",
            "staircase",
            (Segment(F(0), F(1, 2), (F(0),)), Segment(F(1, 2), F(1), (F(0),))),
            F(0),
        )
        with patch(
            "scipy.integrate.quad",
            side_effect=[(0.0, -1.0, {"neval": 0}), (0.0, 2.0, {"neval": 0})],
        ):
            r = run_case(c, RunConfig(track="split"))
        self.assertEqual(r["adjudication"]["accuracy"], "accurate")
        self.assertEqual(r["adjudication"]["estimate"], "invalid")
        self.assertIsNone(r["error_estimate"])

    def test_trace_does_not_change_nonfinite_callback(self):
        from quadaudit.instrumentation import BudgetCounter

        for trace in [0, 1]:
            c = BudgetCounter(10, trace)
            self.assertEqual(c.call_scalar(0.0, lambda x: float("inf")), float("inf"))
            if trace:
                self.assertIsNone(c.trace[0]["y"])

    def test_started_and_completed_are_distinct(self):
        from quadaudit.instrumentation import BudgetCounter

        c = BudgetCounter(3, 0)

        def boom(x):
            raise RuntimeError("test callback failure")

        with self.assertRaises(RuntimeError):
            c.call_scalar(1.0, boom)
        self.assertEqual(c.to_dict()["evaluations"], 1)
        self.assertEqual(c.to_dict()["completed_evaluations"], 0)

    def test_budget_primitives_validate(self):
        from quadaudit.instrumentation import BudgetCounter

        for invalid in [-1, True, 1.5]:
            with self.assertRaises(ValueError):
                BudgetCounter(invalid)
        c = BudgetCounter(3)
        with self.assertRaises(ValueError):
            c.reserve(-1)

    def test_case_metadata_immutable(self):
        p = {"amplitude": "1"}
        c = Case("zero", "power", (Segment(F(0), F(1), (F(0),)),), F(0), p)
        p["amplitude"] = "999"
        self.assertEqual(c.parameters["amplitude"], "1")
        d = c.to_dict()
        d["parameters"]["amplitude"] = "2"
        self.assertEqual(c.parameters["amplitude"], "1")
        with self.assertRaises(TypeError):
            c.parameters["amplitude"] = "3"

    def test_invalid_estimate_axis_without_reference(self):
        from quadaudit.oracle import Reference, adjudicate

        r = adjudicate(None, Reference(None, None, False), F(1), F(-1))
        self.assertEqual(r["estimate"], "invalid")

    def test_exact_evaluation_rejects_floating_input(self):
        c = Case("square", "power", (Segment(F(0), F(1), (F(0), F(0), F(1))),), F(1, 3))
        with self.assertRaises(ValueError):
            c.evaluate_exact(0.1)
        with self.assertRaises(ValueError):
            c.segments[0].evaluate(0.1)
        self.assertEqual(c.evaluate_exact(F(1, 2**1100)), F(1, 2**2200))

    def test_mpmath_callback_precision_recorded(self):
        c = Case("square", "power", (Segment(F(0), F(1), (F(0), F(0), F(1))),), F(1, 3))
        r = run_case(c, RunConfig(method="mpmath_tanhsinh", precision=80))
        self.assertEqual(r["callback_precision_bits_observed"], [100])
        self.assertEqual(r["output_precision_bits"], 80)

    def test_known_family_transform_metadata_stays_consistent(self):
        from quadaudit.families import build_case
        from quadaudit.corpus import verify_corpus

        c = build_case("power", {"n": 2}, "square")
        for transformed in [
            c.affine(F(1), F(2)),
            c.scaled(F(3)),
            c.affine(F(-2), F(1, 4)).scaled(F(-7)),
        ]:
            check = verify_corpus([transformed])
            self.assertTrue(check["valid"], check["errors"])
            self.assertEqual(transformed.family, "power")

    def test_output_grid_diagnostic(self):
        from quadaudit.adapters import target_diagnostics
        from quadaudit.families import build_case

        c = build_case("power", {"n": 2, "amplitude": str(2**40)}, "large-square")
        diag = target_diagnostics(c, RunConfig())
        self.assertFalse(diag["target_attainable"])
        self.assertEqual(
            F(diag["closest_representable_error"]),
            abs(F.from_float(float(c.reference)) - c.reference),
        )
        self.assertTrue(
            target_diagnostics(c, RunConfig(method="mpmath_tanhsinh"))["target_attainable"]
        )

    def test_nearest_binary_boundary_rounding(self):
        from quadaudit.oracle import nearest_binary

        self.assertEqual(nearest_binary(F(1, 3), 53, min_exponent=-1074), F.from_float(1 / 3))
        self.assertEqual(nearest_binary(F(1, 2**1075), 53, min_exponent=-1074), F(0))
        self.assertEqual(nearest_binary(F(3, 2**1075), 53, min_exponent=-1074), F(1, 2**1073))
        self.assertEqual(nearest_binary(F(1) + F(1, 2**53), 53), F(1))

    def test_minimal_known_family_transform_defaults(self):
        from quadaudit.corpus import verify_corpus

        c = Case("square", "power", (Segment(F(0), F(1), (F(0), F(0), F(1))),), F(1, 3), {"n": 2})
        self.assertTrue(verify_corpus([c])["valid"])
        for transformed in (c.affine(F(1), F(2)), c.scaled(F(3))):
            check = verify_corpus([transformed])
            self.assertTrue(check["valid"], check["errors"])

    def test_trace_large_exact_error_does_not_change_real_solver(self):
        c = Case("degree32", "custom", (Segment(F(0), F(1), (F(0),) * 32 + (F(1),)),), F(1, 33))
        plain = run_case(c, RunConfig(method="scipy_tanhsinh", budget=1000, trace_limit=0))
        traced = run_case(c, RunConfig(method="scipy_tanhsinh", budget=1000, trace_limit=10000))
        self.assertEqual(plain["outcome"], "returned")
        self.assertEqual(traced["outcome"], plain["outcome"])
        self.assertEqual(traced["value"], plain["value"])
        self.assertEqual(traced["work"]["evaluations"], plain["work"]["evaluations"])
        self.assertTrue(
            any(p.get("callback_error_status") == "omitted_size_limit" for p in traced["trace"])
        )
