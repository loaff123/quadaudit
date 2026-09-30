"""Independent formula identities and frozen-corpus regression tests."""

import copy
import hashlib
import json
import tempfile
import unittest
from collections import Counter
from fractions import Fraction as F
from functools import lru_cache
from math import comb, factorial
from pathlib import Path
from types import MappingProxyType

from quadaudit.model import Case, Segment
from quadaudit.oracle import audit_case
from quadaudit.families import build_case, family_reference, FAMILY_NAMES
from quadaudit.corpus import (
    corpus_bytes,
    generate_corpus,
    load_corpus,
    mathematical_fingerprint,
    verify_corpus,
)


@lru_cache(maxsize=None)
def cardinal_value(degree, u):
    # Cox-de Boor recurrence is independent of the builder's truncated powers.
    if degree == 0:
        return F(int(0 <= u < 1))
    return (
        u * cardinal_value(degree - 1, u) + (degree + 1 - u) * cardinal_value(degree - 1, u - 1)
    ) / degree


def formula_value(case, x):
    """Use direct family formulas, never builder coefficients or integration."""
    p = case.parameters
    t = (x - F(p["offset"])) / F(p["width"])
    amplitude = F(p["amplitude"])
    family = case.family
    if family == "power":
        y = t ** p["n"]
    elif family == "beta":
        left, right = F(p["support_left"]), F(p["support_right"])
        if not left <= t <= right:
            return F(0)
        u = (t - left) / (right - left)
        y = u ** p["p"] * (1 - u) ** p["q"]
    elif family == "legendre":
        n = p["n"]
        y = sum((comb(n, k) ** 2 * t**k * (t - 1) ** (n - k) for k in range(n + 1)), F(0))
    elif family == "chebyshev_even":
        m = 2 * p["n"]
        z = 2 * t - 1
        y = F(m, 2) * sum(
            (
                F((-1) ** k * factorial(m - k - 1), factorial(k) * factorial(m - 2 * k))
                * (2 * z) ** (m - 2 * k)
                for k in range(m // 2 + 1)
            ),
            F(0),
        )
    elif family == "staircase":
        breaks = list(map(F, p["breaks"].split(",")))
        heights = list(map(F, p["heights"].split(",")))
        i = next((i for i, right in enumerate(breaks[1:]) if t < right), len(heights) - 1)
        y = heights[i]
    elif family == "hinge":
        y = max(t - F(p["c"]), F(0)) ** p["m"]
    elif family == "cardinal_bspline":
        left, right = F(p["support_left"]), F(p["support_right"])
        u = (p["degree"] + 1) * (t - left) / (right - left)
        y = cardinal_value(p["degree"], u)
    else:
        raise AssertionError(family)
    return amplitude * y


class FamilyTests(unittest.TestCase):
    def make(self, family, **parameters):
        return build_case(family, parameters, case_id="example")

    def test_closed_form_areas_and_exact_point_values(self):
        cases = [
            (self.make("power", n=16), F(1, 17)),
            (self.make("beta", p=7, q=9), F(factorial(7) * factorial(9), factorial(17))),
            (self.make("legendre", n=13), F(0)),
            (self.make("chebyshev_even", n=8), F(1, 1 - 4 * 8 * 8)),
            (self.make("staircase", breaks="0,1/4,1/2,1", heights="3,-7,2"), F(0)),
            (self.make("hinge", c="5/8", m=5), F(3, 8) ** 6 / 6),
            (self.make("cardinal_bspline", degree=7), F(1, 8)),
        ]
        for case, expected in cases:
            with self.subTest(family=case.family):
                self.assertEqual(case.reference, expected)
                self.assertEqual(case.integral(), expected)
                self.assertEqual(family_reference(case), expected)
                self.assertTrue(audit_case(case)["valid"])
                for x in [F(0), F(1, 9), F(1, 3), F(1, 2), F(5, 7), F(1)]:
                    self.assertEqual(case.evaluate_exact(x), formula_value(case, x))

    def test_every_legendre_chebyshev_degree_has_identity(self):
        for n in range(1, 17):
            case = self.make("legendre", n=n)
            self.assertEqual(case.integral(), 0)
            self.assertEqual(case.evaluate_exact(F(2, 7)), formula_value(case, F(2, 7)))
        for n in range(1, 9):
            case = self.make("chebyshev_even", n=n)
            self.assertEqual(case.integral(), F(1, 1 - 4 * n * n))
            self.assertEqual(case.evaluate_exact(F(2, 7)), formula_value(case, F(2, 7)))

    def test_compact_support_has_explicit_zero_pieces(self):
        for family, parameters in [("beta", {"p": 4, "q": 6}), ("cardinal_bspline", {"degree": 7})]:
            case = self.make(
                family,
                **parameters,
                amplitude="-8",
                offset="-3/2",
                width="1/4",
                support_left="5/16",
                support_right="21/64",
            )
            self.assertEqual(case.segments[0].coefficients, (F(0),))
            self.assertEqual(case.segments[-1].coefficients, (F(0),))
            self.assertEqual(case.a, F(-3, 2))
            self.assertEqual(case.b, F(-5, 4))
            self.assertTrue(audit_case(case)["valid"])
            for segment in case.segments:
                for x in (segment.left, (2 * segment.left + segment.right) / 3, segment.right):
                    self.assertEqual(case.evaluate_exact(x), formula_value(case, x))

    def test_right_side_staircase_knots_and_final_endpoint(self):
        case = self.make("staircase", breaks="0,1/4,3/4,1", heights="9,-2,7")
        self.assertEqual(case.evaluate_exact(F(1, 4)), -2)
        self.assertEqual(case.evaluate_exact(F(3, 4)), 7)
        self.assertEqual(case.evaluate_exact(F(1)), 7)

    def test_unit_mass_spline_and_affine_amplitude_identities(self):
        for degree in range(1, 17):
            case = self.make("cardinal_bspline", degree=degree, width=degree + 1)
            self.assertEqual(case.integral(), 1)
            self.assertEqual(case.reference, 1)
            self.assertEqual(case.evaluate_exact(F(3, 7)), cardinal_value(degree, F(3, 7)))
        for family, parameters in [
            ("power", {"n": 5}),
            ("beta", {"p": 3, "q": 2}),
            ("legendre", {"n": 4}),
            ("chebyshev_even", {"n": 3}),
            ("hinge", {"m": 2, "c": "1/8"}),
        ]:
            base = self.make(family, **parameters)
            modified = self.make(family, **parameters, offset="3/8", width="1/16", amplitude="-32")
            self.assertEqual(modified.reference, -2 * base.reference)
            self.assertEqual(modified.integral(), modified.reference)
            self.assertEqual(
                modified.evaluate_exact(F(3, 8) + F(1, 16) * F(2, 7)),
                -32 * base.evaluate_exact(F(2, 7)),
            )

    def test_accepts_read_only_parameters_and_defensively_copies_inputs(self):
        original = {"n": 3}
        case = build_case("power", MappingProxyType(original), case_id="readonly")
        original["n"] = 4
        self.assertEqual(case.parameters["n"], 3)
        self.assertEqual(family_reference(case), F(1, 4))
        self.assertEqual(
            build_case(case.family, case.parameters, "rebuilt").segments, case.segments
        )

    def test_family_validation_rejects_invalid_parameters(self):
        bad = [
            ("unknown", {}),
            ("power", {"n": 17}),
            ("power", {"n": True}),
            ("power", {"n": 0, "width": 0}),
            ("power", {"n": 2, "amplitude": 0.1}),
            ("power", {"n": 2, "surprise": 1}),
            ("beta", {"p": 8, "q": 9}),
            ("beta", {"p": 0, "q": 1}),
            ("legendre", {"n": 0}),
            ("chebyshev_even", {"n": 9}),
            ("hinge", {"m": 0, "c": "1/2"}),
            ("hinge", {"m": 2, "c": "1"}),
            ("cardinal_bspline", {"degree": 17}),
            ("cardinal_bspline", {"degree": 1, "support_left": "1/2", "support_right": "1/4"}),
            ("staircase", {"breaks": "0,1/2,1", "heights": "1"}),
            ("staircase", {"breaks": "0,3/4,1/2,1", "heights": "1,2,3"}),
            ("staircase", {"breaks": "0,1/2", "heights": "1"}),
        ]
        for family, parameters in bad:
            with self.subTest(family=family, parameters=parameters), self.assertRaises(ValueError):
                self.make(family, **parameters)


class CorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = generate_corpus()

    def test_all_504_cases_audited_by_three_identities(self):
        self.assertEqual(len(self.cases), 504)
        self.assertEqual(
            Counter(c.family for c in self.cases), Counter({f: 72 for f in FAMILY_NAMES})
        )
        for case in self.cases:
            with self.subTest(case=case.case_id):
                self.assertEqual(case.integral(), case.reference)
                self.assertEqual(family_reference(case), case.reference)
                self.assertTrue(audit_case(case)["valid"])
                self.assertLessEqual(len(case.segments), 64)
                self.assertLessEqual(max(len(s.coefficients) - 1 for s in case.segments), 16)
                for knot in case.knots:
                    self.assertEqual(knot.denominator & (knot.denominator - 1), 0)
                    self.assertEqual(F.from_float(float(knot)), knot)
                for segment in case.segments:
                    for x in [segment.left, (segment.left + 2 * segment.right) / 3, segment.right]:
                        self.assertEqual(case.evaluate_exact(x), formula_value(case, x))
        result = verify_corpus(self.cases)
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(result["count"], 504)

    def test_canonical_seed_regeneration_and_frozen_bytes(self):
        blob = corpus_bytes(self.cases)
        self.assertEqual(blob, corpus_bytes(generate_corpus(20260930)))
        self.assertNotEqual(blob, corpus_bytes(generate_corpus(20260931)))
        frozen = load_corpus()
        self.assertEqual(blob, corpus_bytes(frozen))
        data_dir = Path(__file__).resolve().parents[1] / "src" / "quadaudit" / "data"
        manifest = json.loads((data_dir / "core-v1.manifest.json").read_text())
        self.assertEqual(hashlib.sha256(blob).hexdigest(), manifest["sha256"])
        self.assertEqual(manifest["case_count"], 504)
        self.assertEqual(manifest["seed"], 20260930)
        protocol = json.loads((data_dir / "core-v1.protocol.json").read_text())
        self.assertEqual(protocol["expected_runs"], 3024)
        self.assertEqual(F(protocol["tolerance"]), F(1, 100000000))
        self.assertEqual(protocol["budget"], 4096)
        self.assertEqual(protocol["precision"], 80)
        self.assertEqual(protocol["trace_limit"], 0)
        self.assertEqual(protocol["timeout_seconds"], 10)
        self.assertEqual(protocol["maxlevel"], 10)
        self.assertEqual(protocol["maxdegree"], 8)
        self.assertEqual(protocol["callback_precision"]["mpmath_expected_bits"], 100)
        self.assertIn("charged scalar", protocol["evaluation_counting"])

    def test_mathematical_duplicate_detection_ignores_metadata_and_subdivision(self):
        case = build_case("power", {"n": 2}, case_id="square")
        same = Case(
            "renamed",
            "different_label",
            (
                Segment(F(0), F(1, 2), (F(0), F(0), F(1, 4), F(0))),
                Segment(F(1, 2), F(1), (F(1, 4), F(1, 2), F(1, 4))),
            ),
            F(1, 3),
            {"irrelevant": "changed"},
            "Different metadata",
        )
        self.assertEqual(mathematical_fingerprint(case), mathematical_fingerprint(same))
        result = verify_corpus([case, same])
        self.assertFalse(result["valid"])
        self.assertTrue(result["mathematical_duplicates"])
        changed = Case("changed", "power", (Segment(F(0), F(1), (F(0), F(0), F(2))),), F(2, 3))
        self.assertNotEqual(mathematical_fingerprint(case), mathematical_fingerprint(changed))

    def test_duplicate_id_reference_and_coefficient_mutations_rejected(self):
        case = self.cases[0]
        self.assertFalse(verify_corpus([case, case])["valid"])
        for field in ["reference", "coefficients"]:
            data = copy.deepcopy(case.to_dict())
            if field == "reference":
                data[field] = str(case.reference + 1)
            else:
                data["segments"][0]["coefficients"][0] = str(
                    F(data["segments"][0]["coefficients"][0]) + 1
                )
            self.assertFalse(verify_corpus([Case.from_dict(data)])["valid"])
        data = copy.deepcopy(case.to_dict())
        data["parameters"]["n"] = 15 if data["parameters"]["n"] != 15 else 14
        self.assertFalse(verify_corpus([Case.from_dict(data)])["valid"])

    def test_loading_user_file_rejects_invalid_json_and_bad_references(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "cases.jsonl"
            path.write_bytes(corpus_bytes(self.cases[:2]))
            self.assertEqual(load_corpus(path), self.cases[:2])
            path.write_text('{"schema":"bad"}\n')
            with self.assertRaises(ValueError):
                load_corpus(path)
            data = copy.deepcopy(self.cases[0].to_dict())
            data["reference"] = str(self.cases[0].reference + 1)
            path.write_text(json.dumps(data) + "\n")
            with self.assertRaises(ValueError):
                load_corpus(path)
            path.write_text("\n")
            with self.assertRaises(ValueError):
                load_corpus(path)
        for seed in [True, 1.5, "20260930"]:
            with self.assertRaises(ValueError):
                generate_corpus(seed)
        self.assertFalse(verify_corpus([])["valid"])


if __name__ == "__main__":
    unittest.main()
