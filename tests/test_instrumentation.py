import importlib.util
import unittest
from fractions import Fraction as F
from quadaudit.instrumentation import BudgetCounter, BudgetExceeded


@unittest.skipUnless(
    all(importlib.util.find_spec(m) for m in ("scipy", "numpy", "mpmath")),
    "optional solver dependencies not installed",
)
class InstrumentationTests(unittest.TestCase):
    def test_scalar_counts_duplicates(self):
        c = BudgetCounter(2, 3)
        self.assertEqual(c.call_scalar(0.5, lambda x: x * x), 0.25)
        c.call_scalar(0.5, lambda x: x * x)
        with self.assertRaises(BudgetExceeded):
            c.call_scalar(0.5, lambda x: x * x)
        self.assertEqual(c.to_dict()["evaluations"], 2)
        self.assertEqual(c.to_dict()["attempted_evaluations"], 3)
        self.assertEqual(c.to_dict()["unique_abscissae"], 1)

    def test_atomic_batch_rejection(self):
        import numpy as np

        c = BudgetCounter(3, 0)
        calls = []
        c.call_array(np.array([1.0, 2.0]), lambda x: calls.append(x) or x)
        with self.assertRaises(BudgetExceeded):
            c.call_array(np.ones((1, 2)), lambda x: calls.append(x) or x)
        self.assertEqual(calls, [1.0, 2.0])
        self.assertEqual(c.evaluations, 2)
        self.assertEqual(c.denied_batch, 2)

    def test_trace_limit(self):
        c = BudgetCounter(10, 2)
        for x in range(5):
            c.call_scalar(float(x), lambda z: z)
        self.assertEqual(len(c.trace), 2)
        self.assertEqual(c.to_dict()["trace_truncated"], True)

    def test_mp_exact_conversion(self):
        import mpmath as mp
        from quadaudit.instrumentation import mp_fraction, round_mpf

        ctx = mp.mp.clone()
        ctx.prec = 53
        q = round_mpf(F(1, 3), ctx)
        self.assertEqual(mp_fraction(q), F.from_float(1 / 3))
        self.assertEqual(mp_fraction(round_mpf(F(1), ctx)), F(1))
