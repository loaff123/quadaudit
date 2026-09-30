import importlib.util
import unittest
from fractions import Fraction as F
from quadaudit.model import Case, Segment
from quadaudit.adapters import RunConfig, run_case


def square():
    return Case("square", "power", (Segment(F(0), F(1), (F(0), F(0), F(1))),), F(1, 3))


def box():
    return Case(
        "box",
        "staircase",
        (
            Segment(F(0), F(1, 4), (F(0),)),
            Segment(F(1, 4), F(1, 2), (F(4),)),
            Segment(F(1, 2), F(1), (F(0),)),
        ),
        F(1),
    )


@unittest.skipUnless(
    all(importlib.util.find_spec(m) for m in ("scipy", "numpy", "mpmath")),
    "optional solver dependencies not installed",
)
class AdapterTests(unittest.TestCase):
    def test_real_methods_square(self):
        for method in ["scipy_quad", "scipy_tanhsinh", "mpmath_tanhsinh"]:
            with self.subTest(method=method):
                r = run_case(square(), RunConfig(method=method, budget=4096))
                self.assertEqual(r["outcome"], "returned", r)
                self.assertEqual(r["adjudication"]["accuracy"], "accurate", r)
                self.assertLessEqual(r["work"]["evaluations"], 4096)
                self.assertEqual(r["native_success"], None if method.startswith("mpmath") else True)

    def test_budget_no_result(self):
        for method in ["scipy_quad", "scipy_tanhsinh", "mpmath_tanhsinh"]:
            r = run_case(square(), RunConfig(method=method, budget=2))
            self.assertEqual(r["outcome"], "budget_exhausted", r)
            self.assertIsNone(r["value"])
            self.assertLessEqual(r["work"]["evaluations"], 2)

    def test_split_common_budget_and_contract(self):
        for method in ["scipy_quad", "scipy_tanhsinh", "mpmath_tanhsinh"]:
            r = run_case(box(), RunConfig(method=method, track="split", budget=4096))
            self.assertEqual(r["adjudication"]["accuracy"], "accurate", r)
            self.assertEqual(r["applicability"], "in_contract")
            self.assertEqual(len(r["pieces"]), 3)
        r = run_case(box(), RunConfig(method="scipy_tanhsinh"))
        self.assertEqual(r["applicability"], "exploratory")

    def test_endpoint_conversion_rejected(self):
        c = Case("tiny", "power", (Segment(F(1), F(1) + F(1, 2**60), (F(1),)),), F(1, 2**60))
        self.assertEqual(run_case(c, RunConfig())["outcome"], "unsupported")

    def test_invalid_config(self):
        for opts in [
            {"budget": 0},
            {"method": "fake"},
            {"track": "fake"},
            {"tolerance": "-1"},
            {"precision": 0},
        ]:
            with self.assertRaises(ValueError):
                RunConfig(**opts)

    def test_exact_callback_and_trace(self):
        r = run_case(square(), RunConfig(trace_limit=5))
        self.assertEqual(len(r["trace"]), 5)
        self.assertTrue(all(F(p["callback_error"]) >= 0 for p in r["trace"]))
