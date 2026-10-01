"""Report tests inspect emitted evidence and safe HTML, not implementation text."""

from copy import deepcopy
from dataclasses import asdict
from fractions import Fraction as F
from html.parser import HTMLParser
import json
import math
import shutil
import subprocess
import unittest

from quadaudit.adapters import RunConfig
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
        count = partial.payload()["coverage"]
        self.assertEqual(count["recorded_rows"], 1)
        self.assertEqual(count["expected_rows"], 8)
        self.assertIn("status", count)
        self.assertEqual(count["status"], "unverified")
        self.assertIn("Coverage unverified", " ".join(partial.visible))

    def test_duplicate_replacing_a_missing_case_cannot_claim_complete_coverage(self):
        row = sample_row()
        row["config"] = asdict(RunConfig(**row["config"]))
        other = Case("other", "polynomial", sample_case().segments, F(1, 3))
        rows = [row, deepcopy(row)]
        manifest = {
            "complete": True,
            "expected_runs": 2,
            "completed_runs": 2,
            "protocol": {"configs": [row["config"]]},
        }
        parsed = ParsedReport(render_report(rows, [sample_case(), other], manifest))
        data = parsed.payload()
        self.assertIn("status", data["coverage"])
        self.assertEqual(data["coverage"]["status"], "invalid")
        self.assertEqual(data["coverage"]["duplicate_rows"], 1)
        self.assertEqual(data["coverage"]["missing_rows"], 1)
        self.assertEqual(data["rows"], rows)
        self.assertEqual(data["summary"]["total_rows"], 2)
        self.assertIn("Coverage invalid", " ".join(parsed.visible))
        self.assertIn("counts and rates cover recorded rows", " ".join(parsed.visible))

    def test_intentional_partial_report_retains_missing_schedule_identity(self):
        row = sample_row()
        row["config"] = asdict(RunConfig(**row["config"]))
        other = Case("other", "polynomial", sample_case().segments, F(1, 3))
        manifest = {
            "complete": False,
            "expected_runs": 2,
            "completed_runs": 1,
            "protocol": {"configs": [row["config"]]},
        }
        parsed = ParsedReport(render_report([row], [sample_case(), other], manifest))
        data = parsed.payload()
        self.assertIn("status", data["coverage"])
        self.assertEqual(data["coverage"]["status"], "partial")
        self.assertEqual(data["coverage"]["missing_rows"], 1)
        self.assertEqual(data["coverage"]["duplicate_rows"], 0)
        self.assertIn("Coverage partial", " ".join(parsed.visible))
        self.assertIn("coverage-json", parsed.ids)

    def test_verified_complete_schedule_is_labeled_complete(self):
        row = sample_row()
        row["config"] = asdict(RunConfig(**row["config"]))
        manifest = {
            "complete": True,
            "expected_runs": 1,
            "completed_runs": 1,
            "protocol": {"configs": [row["config"]]},
        }
        parsed = ParsedReport(render_report([row], [sample_case()], manifest))
        self.assertIn("status", parsed.payload()["coverage"])
        self.assertEqual(parsed.payload()["coverage"]["status"], "complete")
        self.assertIn("identity coverage complete", " ".join(parsed.visible))

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

    def test_contradictory_target_diagnostics_are_recomputed_and_raw_retained(self):
        row = sample_row()
        row["target_diagnostics"] = {
            "target_attainable": False,
            "zero_meets_target": False,
            "output_precision_bits": 53,
            "closest_representable_error": "1/27021597764222976",
        }
        parsed = ParsedReport(render_report([row], [sample_case()], {}))
        data = parsed.payload()
        self.assertIn("0 output-grid-unattainable targets", " ".join(parsed.visible))
        self.assertEqual(data["presentation"][0]["labels"]["target_attainability"], "attainable")
        self.assertIn(
            "Recorded target diagnostics disagree", data["presentation"][0]["integrity_note"]
        )
        self.assertEqual(data["rows"][0], row)
        self.assertEqual(
            parsed.payload()["presentation"][0]["quantities"]["closest_representable_error"][
                "exact"
            ],
            "1/54043195528445952",
        )

    def test_correct_diagnostics_are_preserved_without_an_integrity_warning(self):
        from quadaudit.adapters import RunConfig, target_diagnostics

        row = sample_row()
        row["target_diagnostics"] = target_diagnostics(
            sample_case(), RunConfig(tolerance=row["config"]["tolerance"])
        )
        before = deepcopy(row)
        data = ParsedReport(render_report([row], [sample_case()], {})).payload()
        self.assertEqual(row, before)
        self.assertEqual(data["rows"][0], before)
        self.assertEqual(data["presentation"][0]["integrity_note"], "")
        self.assertEqual(data["presentation"][0]["labels"]["target_attainability"], "attainable")

    def test_zero_baseline_and_grid_use_verified_reference_and_target(self):
        for tolerance, attainable, zero in [
            ("1", "attainable", "zero_sufficient"),
            ("1/100000000000000000000", "unattainable", "zero_insufficient"),
        ]:
            with self.subTest(tolerance=tolerance):
                row = sample_row()
                row["config"]["tolerance"] = tolerance
                row["target_diagnostics"] = {"target_attainable": True, "zero_meets_target": False}
                data = ParsedReport(render_report([row], [sample_case()], {})).payload()
                labels = data["presentation"][0]["labels"]
                self.assertEqual(labels["target_attainability"], attainable)
                self.assertEqual(labels["zero_target"], zero)
                self.assertEqual(data["summary"]["target_strata"][0]["zero_target"], zero)

    def test_mpmath_grid_uses_configured_output_precision_not_recorded_diagnostics(self):
        row = sample_row()
        row["method"] = row["config"]["method"] = "mpmath_tanhsinh"
        row["config"].update(precision=80, tolerance="1/100000000000000000000")
        row["target_diagnostics"] = {
            "output_precision_bits": 53,
            "target_attainable": False,
            "closest_representable_error": "1/54043195528445952",
        }
        data = ParsedReport(render_report([row], [sample_case()], {})).payload()
        evidence = data["presentation"][0]
        self.assertEqual(evidence["labels"]["target_attainability"], "attainable")
        self.assertEqual(
            evidence["quantities"]["closest_representable_error"]["exact"],
            "1/7253554917687775048237056",
        )
        self.assertIn("Recorded target diagnostics disagree", evidence["integrity_note"])

    def test_unknown_or_malformed_output_precision_does_not_trust_grid_metadata(self):
        for method, precision in [
            ("future_solver", 80),
            ("mpmath_tanhsinh", None),
            ("mpmath_tanhsinh", True),
            ("mpmath_tanhsinh", "80"),
            ("mpmath_tanhsinh", 19),
            ("mpmath_tanhsinh", 513),
            ("mpmath_tanhsinh", 10**20),
        ]:
            with self.subTest(method=method, precision=precision):
                row = sample_row()
                row["method"] = row["config"]["method"] = method
                row["config"]["precision"] = precision
                row["target_diagnostics"] = {
                    "target_attainable": True,
                    "zero_meets_target": True,
                    "output_precision_bits": 53,
                    "closest_representable_error": "0",
                }
                data = ParsedReport(render_report([row], [sample_case()], {})).payload()
                detail = data["presentation"][0]
                self.assertEqual(detail["labels"]["target_attainability"], "unknown")
                self.assertEqual(detail["labels"]["zero_target"], "zero_insufficient")
                self.assertIsNone(detail["quantities"]["closest_representable_error"]["exact"])
                self.assertIn("output precision", detail["integrity_note"])

    def test_unverified_case_target_or_configuration_cannot_validate_diagnostics(self):
        for mutation in ("missing_case", "bad_reference", "target", "track", "family"):
            with self.subTest(mutation=mutation):
                row = sample_row()
                row["target_diagnostics"] = {"target_attainable": True, "zero_meets_target": True}
                cases = [sample_case()]
                if mutation == "missing_case":
                    cases = []
                elif mutation == "bad_reference":
                    cases = [Case("square", "polynomial", sample_case().segments, F(2))]
                elif mutation == "target":
                    row["config"]["tolerance"] = "nan"
                elif mutation == "track":
                    row["config"]["track"] = "split"
                elif mutation == "family":
                    row["family"] = "wrong"
                detail = ParsedReport(render_report([row], cases, {})).payload()["presentation"][0]
                self.assertEqual(detail["labels"]["target_attainability"], "unknown")
                self.assertEqual(detail["labels"]["zero_target"], "unknown")
                self.assertIsNone(detail["quantities"]["closest_representable_error"]["exact"])

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
                    # Windows-hosted Node cold starts can exceed 10s. Keep a
                    # bounded wait and retain every rendering assertion.
                    timeout=60,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Selected evidence", result.stdout)

    @unittest.skipUnless(shutil.which("node"), "optional JavaScript runtime is unavailable")
    def test_browser_detail_shows_verified_output_precision_without_raw_fallback(self):
        harness = r"""
const fs=require('fs'),input=JSON.parse(fs.readFileSync(0,'utf8')),elements=new Map();
const make=()=>({value:'',textContent:'',innerHTML:'',disabled:false,
 addEventListener(){},append(){},querySelectorAll(){return []}});
global.document={getElementById(id){if(!elements.has(id))elements.set(id,make());return elements.get(id)},createElement:make};
document.getElementById('study-data').textContent=JSON.stringify(input.payload);
eval(input.script);
console.log(document.getElementById('detail-content').innerHTML);
"""
        for precision, expected in [(80, "80"), ("malformed", "unknown")]:
            with self.subTest(precision=precision):
                row = sample_row()
                row["method"] = row["config"]["method"] = "mpmath_tanhsinh"
                row["config"]["precision"] = precision
                row["target_diagnostics"] = {"output_precision_bits": 53}
                row["output_precision_bits"] = 53
                parsed = ParsedReport(render_report([row], [sample_case()], {}))
                result = subprocess.run(
                    [shutil.which("node"), "-e", harness],
                    input=json.dumps(
                        {"payload": parsed.payload(), "script": parsed.scripts[-1]["text"]}
                    ),
                    text=True,
                    capture_output=True,
                    timeout=60,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"Output precision: {expected} bits", result.stdout)
                self.assertNotIn("Output precision: 53 bits", result.stdout)

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
