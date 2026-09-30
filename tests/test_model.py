import unittest
from fractions import Fraction as F
from quadaudit.model import Case, Segment, rational, add_cases
from quadaudit.oracle import Reference, adjudicate, audit_case


def square():
    return Case("square", "control", (Segment(F(0), F(1), (F(0), F(0), F(1))),), F(1, 3))


class ModelTests(unittest.TestCase):
    def test_square_area(self):
        self.assertEqual(square().integral(), F(1, 3))
        self.assertEqual(square().evaluate_exact(F(1, 2)), F(1, 4))
        self.assertTrue(audit_case(square())["valid"])

    def test_piece_boundaries(self):
        c = Case(
            "step",
            "box",
            (Segment(F(0), F(1, 2), (F(2),)), Segment(F(1, 2), F(1), (F(-3),))),
            F(-1, 2),
        )
        self.assertEqual(c.evaluate_exact(F(1, 2)), -3)
        self.assertEqual(c.evaluate_exact(F(1)), -3)
        self.assertEqual(c.integral(), F(-1, 2))
        with self.assertRaises(ValueError):
            c.evaluate_exact(F(-1))

    def test_invalid_cases(self):
        for segs in [(), (Segment(F(0), F(1), (F(1),)), Segment(F(2), F(3), (F(1),)))]:
            with self.assertRaises(ValueError):
                Case("bad", "bad", segs, F(0))
        with self.assertRaises(ValueError):
            Segment(F(1), F(0), (F(1),))
        with self.assertRaises(ValueError):
            rational("1" * 400)
        with self.assertRaises(ValueError):
            rational(0.1)

    def test_roundtrip(self):
        self.assertEqual(Case.from_dict(square().to_dict()), square())

    def test_transform(self):
        c = square().affine(F(3), F(2)).scaled(F(-7))
        self.assertEqual(c.integral(), F(-14, 3))
        self.assertEqual(c.evaluate_exact(F(4)), F(-7, 4))
        self.assertTrue(audit_case(c)["valid"])
        with self.assertRaises(ValueError):
            square().affine(F(0), F(-1))

    def test_sum_aligns_knots(self):
        a = square()
        b = Case(
            "step",
            "box",
            (Segment(F(0), F(1, 2), (F(1),)), Segment(F(1, 2), F(1), (F(0),))),
            F(1, 2),
        )
        c = add_cases(a, b)
        self.assertEqual(c.integral(), F(5, 6))
        for x in [F(0), F(1, 4), F(1, 2), F(3, 4), F(1)]:
            self.assertEqual(c.evaluate_exact(x), a.evaluate_exact(x) + b.evaluate_exact(x))

    def test_corrupted_reference(self):
        d = square().to_dict()
        d["reference"] = "1/2"
        self.assertFalse(audit_case(Case.from_dict(d))["valid"])


class OracleTests(unittest.TestCase):
    def test_exact_threshold(self):
        r = Reference(F(1, 3), F(1, 3))
        q = F.from_float(float(F(1, 3)))
        e = abs(q - F(1, 3))
        self.assertEqual(adjudicate(q, r, e, F(0))["accuracy"], "accurate")
        self.assertEqual(adjudicate(q, r, e / 2, F(0))["accuracy"], "inaccurate")
        self.assertEqual(adjudicate(q, r, e, F(0))["estimate"], "underestimated")

    def test_unresolved_enclosure(self):
        r = Reference(F(0), F(2))
        self.assertEqual(adjudicate(F(1), r, F(1, 2), F(1, 2))["accuracy"], "unresolved")
        self.assertEqual(adjudicate(F(3), r, F(1, 2), F(0))["accuracy"], "inaccurate")
        self.assertEqual(adjudicate(F(1), r, F(1), F(1))["estimate"], "sufficient")

    def test_zero_unknown_invalid(self):
        r = Reference(F(0), F(0))
        self.assertEqual(adjudicate(F(0), r, F(1), F(0))["zero_estimate"], "exact_zero_error")
        self.assertEqual(adjudicate(F(0), r, F(1), F(-1))["estimate"], "invalid")
        self.assertEqual(adjudicate(None, r, F(1), None)["accuracy"], "unscorable")
        self.assertEqual(
            adjudicate(F(0), Reference(None, None, False), F(1), None)["accuracy"], "unscorable"
        )
        with self.assertRaises(ValueError):
            Reference(F(2), F(1))
        with self.assertRaises(ValueError):
            adjudicate(F(0), r, F(-1), None)
