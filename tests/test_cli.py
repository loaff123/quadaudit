import contextlib
import io
import json
import runpy
import tempfile
import unittest
from pathlib import Path
from fractions import Fraction as F
from quadaudit.model import Case, Segment
from quadaudit.cli import main, export_regression


class CliTests(unittest.TestCase):
    def test_export_standalone(self):
        case = Case("square", "power", (Segment(F(0), F(1), (F(0), F(0), F(1))),), F(1, 3))
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "fixture.py"
            p.write_text(export_regression(case))
            ns = runpy.run_path(str(p))
            self.assertEqual(ns["REFERENCE"], F(1, 3))
            self.assertEqual(ns["f"](0.5), 0.25)

    def test_verify_corrupt_exit(self):
        case = Case("square", "power", (Segment(F(0), F(1), (F(0), F(0), F(1))),), F(1, 2))
        with tempfile.TemporaryDirectory() as td, contextlib.redirect_stdout(io.StringIO()):
            p = Path(td) / "cases.jsonl"
            p.write_text(json.dumps(case.to_dict()) + "\n")
            self.assertEqual(main(["verify", str(p)]), 2)

    def test_help(self):
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as caught:
            main(["--help"])
        self.assertEqual(caught.exception.code, 0)

    def test_tolerance_parser_rejects_exponent_bomb(self):
        from quadaudit.cli import parse_tolerance

        with self.assertRaises(ValueError):
            parse_tolerance("1e100000000")
        self.assertEqual(parse_tolerance("1e-8"), "1/100000000")
        self.assertEqual(parse_tolerance("1/8"), "1/8")
