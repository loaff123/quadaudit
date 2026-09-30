"""Report tests inspect emitted evidence and safe HTML, not implementation text."""

from fractions import Fraction as F
from html.parser import HTMLParser
import json
import math
import shutil
import subprocess
import unittest

from quadaudit.model import Case, Segment
from quadaudit.report import _fraction, render_report


class ParsedReport(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.tags, self.ids, self.scripts, self.visible = [], {}, [], []
        self.script = None
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append((tag, attrs))
        if "id" in attrs:
            self.ids[attrs["id"]] = (tag, attrs)
        if tag == "script":
            self.script = {"attrs": attrs, "text": ""}
            self.scripts.append(self.script)

    def handle_endtag(self, tag):
        if tag == "script":
            self.script = None

    def handle_data(self, data):
        if self.script is not None:
            self.script["text"] += data
        else:
            self.visible.append(data)

    def payload(self):
        return json.loads(
            next(s["text"] for s in self.scripts if s["attrs"].get("id") == "study-data")
        )


def sample_case(description="Square control"):
    return Case(
        "square",
        "polynomial",
        (Segment(F(0), F(1), (F(0), F(0), F(1))),),
        F(1, 3),
        description=description,
    )


def sample_row():
    return {
        "case_id": "square",
        "family": "polynomial",
        "method": "scipy_quad",
        "track": "blind",
        "config": {
            "budget": 100,
            "trace_limit": 2,
            "method": "scipy_quad",
            "track": "blind",
            "tolerance": "1/1000",
        },
        "outcome": "returned",
        "applicability": "in_contract",
        "native_success": True,
        "value": "1/3",
        "error_estimate": "0",
        "adjudication": {
            "accuracy": "accurate",
            "estimate": "sufficient",
            "error_lower": "0",
            "error_upper": "0",
            "zero_estimate": "exact_zero_error",
            "tolerance": "1/1000",
        },
        "work": {
            "budget": 100,
            "evaluations": 21,
            "completed_evaluations": 21,
            "attempted_evaluations": 21,
            "trace_limit": 2,
            "trace_truncated": True,
        },
        "trace": [
            {"x": "1/4", "y": "1/16", "callback_error": "0"},
            {"x": "3/4", "y": "9/16", "callback_error": "0"},
        ],
    }


class ReportTests(unittest.TestCase):
    def test_offline_accessible_filters_and_all_outcomes_retained(self):
        rows = [
            sample_row(),
            dict(sample_row(), outcome="timeout", value=None),
            dict(sample_row(), applicability="exploratory"),
        ]
        parsed = ParsedReport(render_report(rows, [sample_case()], {"status": "complete"}))
        self.assertEqual(parsed.payload()["rows"], rows)
        self.assertEqual(parsed.payload()["summary"]["total_rows"], 3)
        for name in ("family", "method", "track", "applicability", "accuracy"):
            self.assertEqual(parsed.ids[f"{name}-filter"][0], "select")
            self.assertTrue(
                any(
                    tag == "label" and attrs.get("for") == f"{name}-filter"
                    for tag, attrs in parsed.tags
                )
            )
        self.assertFalse(any("src" in attrs for tag, attrs in parsed.tags if tag == "script"))
        self.assertFalse(
            any(
                attrs.get("href", "").startswith(("http:", "https:"))
                for tag, attrs in parsed.tags
                if tag == "link"
            )
        )

    def test_script_breakout_and_html_metadata_are_inert(self):
        attack = '</script><script>alert("XSS")</script><img src=x onerror=alert(1)>&'
        row = sample_row()
        row["warnings"] = [attack]
        row["method"] = attack
        parsed = ParsedReport(render_report([row], [sample_case(attack)], {"title": attack}))
        self.assertEqual(len(parsed.scripts), 2)
        self.assertFalse(any(tag == "img" for tag, attrs in parsed.tags))
        self.assertEqual(parsed.payload()["rows"][0]["warnings"], [attack])
        self.assertEqual(parsed.payload()["cases"]["square"]["description"], attack)

    def test_empty_and_partial_studies_disclose_absent_records(self):
        empty = ParsedReport(render_report([], [], {"expected_runs": 6, "status": "partial"}))
        self.assertEqual(empty.payload()["coverage"]["missing_rows"], 6)
        self.assertIn("No result rows", " ".join(empty.visible))
        partial = ParsedReport(render_report([sample_row()], [sample_case()], {"expected_runs": 8}))
        self.assertEqual(
            partial.payload()["coverage"],
            {"recorded_rows": 1, "expected_rows": 8, "missing_rows": 7, "extra_rows": 0},
        )
        self.assertIn("7 scheduled rows are absent", " ".join(partial.visible))

    def test_exact_and_approximate_evidence_and_trace_cap_are_visible(self):
        parsed = ParsedReport(render_report([sample_row()], [sample_case()], {}))
        detail = parsed.payload()["presentation"][0]
        self.assertEqual(detail["quantities"]["reference"], {"exact": "1/3", "approx": "0.333333"})
        self.assertEqual(detail["quantities"]["value"]["exact"], "1/3")
        self.assertIn("2 of 21", detail["trace_note"])
        self.assertIn("truncated", detail["trace_note"].lower())
        self.assertEqual(len(detail["samples"]), 2)
        self.assertEqual(detail["samples"][0]["x"], 0.25)

    def test_segment_aware_plot_retains_a_narrow_nonzero_support(self):
        left, right = F(1, 2), F(1, 2) + F(1, 2**40)
        case = Case(
            "needle",
            "bumps",
            (
                Segment(F(0), left, (F(0),)),
                Segment(left, right, (F(0), F(4), F(-4))),
                Segment(right, F(1), (F(0),)),
            ),
            (right - left) * F(2, 3),
        )
        parsed = ParsedReport(render_report([], [case], {}))
        segments = parsed.payload()["plots"]["needle"]["segments"]
        self.assertEqual(len(segments), 3)
        self.assertTrue(any(p[1] == 1.0 for p in segments[1]["points"]))
        self.assertEqual(segments[1]["left"], "1/2")
        self.assertEqual(segments[1]["points"][0][2], 0.0)
        self.assertEqual(segments[1]["points"][-1][2], 1.0)

    def test_huge_rationals_produce_finite_plot_coordinates(self):
        huge = F(2**1023)
        case = Case("huge", "polynomial", (Segment(F(0), F(1), (huge,)),), huge)
        parsed = ParsedReport(render_report([], [case], {"elapsed_seconds": float("nan")}))
        data = parsed.payload()
        self.assertNotEqual(data["manifest"]["elapsed_seconds"], float("nan"))
        self.assertTrue(
            all(
                math.isfinite(v)
                for s in data["plots"]["huge"]["segments"]
                for p in s["points"]
                for v in p
            )
        )

    def test_missing_case_or_malformed_trace_retains_row_without_fake_curve(self):
        row = sample_row()
        row["trace"] = [{"x": "nan", "y": "1"}, {"x": "3/4", "y": "NaN"}]
        parsed = ParsedReport(render_report([row], [], {}))
        self.assertEqual(parsed.payload()["rows"][0], row)
        self.assertEqual(parsed.payload()["presentation"][0]["samples"], [])
        self.assertIn("unavailable", parsed.payload()["presentation"][0]["plot_note"])

    def test_template_tokens_in_metadata_do_not_change_raw_evidence(self):
        row = sample_row()
        row["message"] = "@@ROWS@@ @@MATRIX@@ @@DATA@@"
        parsed = ParsedReport(render_report([row], [sample_case()], {}))
        self.assertEqual(parsed.payload()["rows"][0]["message"], row["message"])

    def test_malformed_case_id_is_retained_but_not_used_to_lookup_a_curve(self):
        row = sample_row()
        row["case_id"] = {"untrusted": "identifier"}
        parsed = ParsedReport(render_report([row], [], {}))
        self.assertEqual(parsed.payload()["rows"][0]["case_id"], row["case_id"])
        self.assertEqual(parsed.payload()["presentation"][0]["samples"], [])

    def test_target_attainability_is_prominent_and_exact_grid_error_is_retained(self):
        row = sample_row()
        row["target_diagnostics"] = {
            "target_attainable": False,
            "zero_meets_target": False,
            "output_precision_bits": 53,
            "closest_representable_error": "1/27021597764222976",
        }
        parsed = ParsedReport(render_report([row], [sample_case()], {}))
        self.assertIn("1 output-grid-unattainable targets", " ".join(parsed.visible))
        self.assertEqual(
            parsed.payload()["presentation"][0]["quantities"]["closest_representable_error"][
                "exact"
            ],
            "1/27021597764222976",
        )

    def test_started_count_is_not_substituted_for_unknown_completed_count(self):
        row = sample_row()
        del row["work"]["completed_evaluations"]
        parsed = ParsedReport(render_report([row], [sample_case()], {}))
        self.assertIn("2 of unknown completed", parsed.payload()["presentation"][0]["trace_note"])

    @unittest.skipUnless(shutil.which("node"), "optional JavaScript runtime is unavailable")
    def test_browser_script_retains_malformed_ids_without_prototype_lookup_or_coercion(self):
        # Minimal DOM boundary: exercise the emitted script's initial rendering,
        # and inspect its output rather than asserting interactions with doubles.
        harness = r"""
const fs=require('fs'),input=JSON.parse(fs.readFileSync(0,'utf8')),elements=new Map();
const make=()=>({value:'',textContent:'',innerHTML:'',disabled:false,
 addEventListener(){},append(){},querySelectorAll(){return []}});
global.document={getElementById(id){if(!elements.has(id))elements.set(id,make());return elements.get(id)},createElement:make};
document.getElementById('study-data').textContent=JSON.stringify(input.payload);
eval(input.script);
console.log(document.getElementById('detail-content').innerHTML);
"""
        for identifier in ["__proto__", {"toString": "untrusted", "valueOf": None}]:
            with self.subTest(identifier=identifier):
                row = sample_row()
                row["case_id"] = identifier
                parsed = ParsedReport(render_report([row], [], {}))
                result = subprocess.run(
                    [shutil.which("node"), "-e", harness],
                    input=json.dumps(
                        {"payload": parsed.payload(), "script": parsed.scripts[-1]["text"]}
                    ),
                    text=True,
                    capture_output=True,
                    timeout=10,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Selected evidence", result.stdout)

    def test_evidence_rationals_reject_exponents_and_bound_integer_size_before_parsing(self):
        for value in ["1e10000", "0.25", "1/0", "9" * 4934, "1/" + "9" * 4934]:
            self.assertIsNone(_fraction(value))
        self.assertIsNotNone(_fraction("1/" + "1" * 4900))
        self.assertEqual(_fraction("-7/16"), F(-7, 16))

    def test_changed_value_is_readjudicated_instead_of_trusting_stale_accuracy(self):
        row = sample_row()
        row["value"] = "9999"
        parsed = ParsedReport(render_report([row], [sample_case()], {}))
        self.assertEqual(
            parsed.payload()["summary"]["in_contract"]["accuracy_rate"]["numerator"], 0
        )
        evidence = parsed.payload()["presentation"][0]
        self.assertEqual(evidence["labels"]["accuracy"], "inaccurate")
        self.assertEqual(evidence["quantities"]["error_lower"]["exact"], "29996/3")
        self.assertIn("disagrees", evidence["integrity_note"])
        self.assertEqual(parsed.payload()["rows"][0], row)

    def test_absent_or_invalid_case_cannot_validate_a_recorded_accuracy_claim(self):
        for cases in [[], [Case("square", "polynomial", sample_case().segments, F(2))]]:
            with self.subTest(cases=cases):
                parsed = ParsedReport(render_report([sample_row()], cases, {}))
                self.assertEqual(
                    parsed.payload()["presentation"][0]["labels"]["accuracy"], "unscorable"
                )

    def test_blind_multisegment_tanhsinh_is_excluded_even_if_raw_applicability_is_wrong(self):
        case = Case(
            "square",
            "polynomial",
            (Segment(F(0), F(1, 2), (F(0),)), Segment(F(1, 2), F(1), (F(0),))),
            F(0),
        )
        row = sample_row()
        row["method"] = "scipy_tanhsinh"
        parsed = ParsedReport(render_report([row], [case], {}))
        self.assertEqual(parsed.payload()["summary"]["in_contract"]["total_rows"], 0)
        self.assertEqual(
            parsed.payload()["presentation"][0]["labels"]["applicability"], "exploratory"
        )

    def test_inconsistent_row_and_config_remain_in_denominator_but_unscorable(self):
        row = sample_row()
        row["config"]["track"] = "split"
        parsed = ParsedReport(render_report([row], [sample_case()], {}))
        self.assertEqual(parsed.payload()["summary"]["in_contract"]["total_rows"], 1)
        self.assertEqual(parsed.payload()["presentation"][0]["labels"]["accuracy"], "unscorable")
        self.assertIn("configuration", parsed.payload()["presentation"][0]["integrity_note"])

    def test_duplicate_case_identifiers_cannot_select_an_arbitrary_reference(self):
        with self.assertRaisesRegex(ValueError, "duplicate case"):
            render_report([sample_row()], [sample_case(), sample_case()], {})

    def test_mixed_settings_are_prominent_and_can_be_filtered(self):
        a, b = sample_row(), sample_row()
        b["config"]["callback_mode"] = "native_horner"
        parsed = ParsedReport(render_report([a, b], [sample_case()], {}))
        self.assertIn("Mixed settings", " ".join(parsed.visible))
        self.assertEqual(parsed.ids["configuration-filter"][0], "select")
        self.assertNotEqual(
            parsed.payload()["presentation"][0]["configuration_id"],
            parsed.payload()["presentation"][1]["configuration_id"],
        )

    def test_target_stratified_scores_are_available_as_an_inspectable_table(self):
        row = sample_row()
        row["target_diagnostics"] = {"target_attainable": True, "zero_meets_target": False}
        parsed = ParsedReport(render_report([row], [sample_case()], {}))
        self.assertEqual(parsed.ids["target-strata"][0], "table")
        self.assertIn("zero_insufficient", " ".join(parsed.visible))

    def test_posthoc_selection_is_visible(self):
        html = render_report(
            [sample_row()], [sample_case()], {"selection": {"type": "post_hoc_explanatory"}}
        )
        visible = " ".join(ParsedReport(html).visible)
        self.assertIn("Post-hoc explanatory selection", visible)
        self.assertIn("do not replace the frozen study", visible)

    def test_readable_default_type_sizes(self):
        html = render_report([sample_row()], [sample_case()], {})
        self.assertIn("font:16px/1.55 system-ui", html)
        self.assertNotIn("font-size:10px", html)
        self.assertNotIn("font-size:11px", html)


if __name__ == "__main__":
    unittest.main()
