import importlib.util
import tempfile
import time
import unittest
from pathlib import Path
from fractions import Fraction as F
from quadaudit.model import Case, Segment
from quadaudit.adapters import RunConfig
from quadaudit.runner import IsolatedRunner, experiment, read_results


def special_worker(conn, memory_mb):
    conn.send({"ready": True, "memory_limit": {"enforced": False}})
    while True:
        task = conn.recv()
        if task is None:
            return
        if task[0]["case_id"] == "sleep":
            time.sleep(20)
        elif task[0]["case_id"] == "crash":
            conn.close()
            return
        else:
            from quadaudit.adapters import run_case, RunConfig
            from quadaudit.model import Case

            conn.send(run_case(Case.from_dict(task[0]), RunConfig(**task[1])))


def case(name="square"):
    return Case(name, "power", (Segment(F(0), F(1), (F(0), F(0), F(1))),), F(1, 3))


@unittest.skipUnless(
    all(importlib.util.find_spec(m) for m in ("scipy", "numpy", "mpmath")),
    "optional solver dependencies not installed",
)
class RunnerTests(unittest.TestCase):
    def test_timeout_then_recovery(self):
        with IsolatedRunner(timeout_seconds=0.2, worker_target=special_worker) as runner:
            self.assertEqual(runner.run(case("sleep"), RunConfig())["outcome"], "timeout")
            runner.timeout_seconds = 5
            self.assertEqual(runner.run(case(), RunConfig())["outcome"], "returned")

    def test_crash_then_recovery(self):
        with IsolatedRunner(timeout_seconds=5, worker_target=special_worker) as runner:
            self.assertEqual(runner.run(case("crash"), RunConfig())["outcome"], "worker_crash")
            self.assertEqual(runner.run(case(), RunConfig())["outcome"], "returned")

    def test_real_isolation(self):
        with IsolatedRunner(timeout_seconds=10) as runner:
            r = runner.run(case(), RunConfig())
            self.assertEqual(r["outcome"], "returned", r)
            self.assertIn("memory_limit", r["isolation"])

    def test_experiment_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            m = experiment([case()], [RunConfig()], Path(d), timeout_seconds=10)
            self.assertTrue(m["complete"])
            self.assertEqual(m["expected_runs"], 1)
            self.assertEqual(len(list(read_results(Path(d) / "results.jsonl"))), 1)
            self.assertTrue((Path(d) / "corpus.jsonl").exists())

    def test_modified_evidence_hash_rejected(self):
        from quadaudit.runner import verify_experiment_artifacts

        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            experiment([case()], [RunConfig()], path, timeout_seconds=10)
            self.assertTrue(verify_experiment_artifacts(path)["complete"])
            with (path / "results.jsonl").open("a") as f:
                f.write("{}\n")
            with self.assertRaises(ValueError):
                verify_experiment_artifacts(path)

    def test_source_state_captured_before_generated_files(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            with patch(
                "quadaudit.runner._environment",
                side_effect=lambda: {"artifacts_already_exist": (path / "corpus.jsonl").exists()},
            ):
                manifest = experiment([case()], [RunConfig()], path)
            self.assertFalse(manifest["environment"]["artifacts_already_exist"])


class ArtifactScheduleTests(unittest.TestCase):
    """Rehashed artifacts must still describe the declared execution schedule."""

    def write_artifacts(
        self,
        directory,
        rows=None,
        *,
        complete=True,
        expected=2,
        completed=None,
        protocol=None,
        embedded_protocol=None,
    ):
        import hashlib
        from dataclasses import asdict
        from quadaudit.adapters import empty_result
        from quadaudit.runner import canonical

        cases = [
            Case("square", "polynomial", (Segment(F(0), F(1), (F(0), F(0), F(1))),), F(1, 3)),
            Case("line", "polynomial", (Segment(F(0), F(1), (F(0), F(1))),), F(1, 2)),
        ]
        config = RunConfig()
        if rows is None:
            rows = [empty_result(c, config) for c in cases]
        if protocol is None:
            protocol = {"configs": [asdict(config)], "timeout_seconds": 10}
        if embedded_protocol is None:
            embedded_protocol = protocol
        blobs = {
            "corpus": b"".join(canonical(c.to_dict()) for c in cases),
            "protocol": canonical(protocol),
            "results": b"".join(canonical(row) for row in rows),
        }
        manifest = {
            "schema": "quadaudit.experiment.v1",
            "complete": complete,
            "expected_runs": expected,
            "completed_runs": len(rows) if completed is None else completed,
            "case_count": len(cases),
            "protocol": embedded_protocol,
        }
        for kind, blob in blobs.items():
            suffix = ".json" if kind == "protocol" else ".jsonl"
            (directory / (kind + suffix)).write_bytes(blob)
            manifest[kind + "_sha256"] = hashlib.sha256(blob).hexdigest()
        (directory / "manifest.json").write_bytes(canonical(manifest))
        return rows, manifest

    def test_same_count_rehashed_duplicate_cannot_replace_missing_run(self):
        from quadaudit.runner import verify_experiment_artifacts

        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            rows, _ = self.write_artifacts(path)
            self.write_artifacts(path, [rows[0], rows[0]])
            with self.assertRaisesRegex(ValueError, "schedule|duplicate"):
                verify_experiment_artifacts(path)

    def test_rehashed_protocol_must_match_embedded_protocol(self):
        from copy import deepcopy
        from quadaudit.runner import verify_experiment_artifacts

        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            _, manifest = self.write_artifacts(path)
            changed = deepcopy(manifest["protocol"])
            changed["timeout_seconds"] = 20
            self.write_artifacts(path, protocol=changed, embedded_protocol=manifest["protocol"])
            with self.assertRaisesRegex(ValueError, "protocol"):
                verify_experiment_artifacts(path)

    def test_expected_runs_must_match_explicit_schedule(self):
        from quadaudit.runner import verify_experiment_artifacts

        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            rows, _ = self.write_artifacts(path)
            self.write_artifacts(path, rows[:1], expected=1)
            with self.assertRaisesRegex(ValueError, "schedule|expected"):
                verify_experiment_artifacts(path)

    def test_recorded_count_must_match_manifest_even_when_partial(self):
        from quadaudit.runner import verify_experiment_artifacts

        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            self.write_artifacts(path, complete=False, completed=1)
            with self.assertRaisesRegex(ValueError, "count|completed"):
                verify_experiment_artifacts(path)

    def test_coherent_partial_experiment_is_allowed(self):
        from quadaudit.runner import verify_experiment_artifacts

        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            rows, _ = self.write_artifacts(path)
            self.write_artifacts(path, rows[:1], complete=False)
            self.assertFalse(verify_experiment_artifacts(path)["complete"])

    def test_cli_refuses_rehashed_duplicate_without_creating_report(self):
        import contextlib
        import io
        from quadaudit.cli import main

        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            rows, _ = self.write_artifacts(path)
            self.write_artifacts(path, [rows[0], rows[0]])
            with (
                contextlib.redirect_stderr(io.StringIO()),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                code = main(["report", str(path)])
            self.assertEqual(code, 2)
            self.assertFalse((path / "report.html").exists())

    def test_malformed_rehashed_schedule_is_rejected(self):
        from quadaudit.runner import verify_experiment_artifacts

        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            self.write_artifacts(path, protocol={})
            with self.assertRaisesRegex(ValueError, "schedule|configs"):
                verify_experiment_artifacts(path)

    def test_cli_renders_coherent_partial_experiment(self):
        import contextlib
        import io
        from quadaudit.cli import main

        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            rows, _ = self.write_artifacts(path)
            self.write_artifacts(path, rows[:1], complete=False)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["report", str(path)]), 0)
            report = (path / "report.html").read_text(encoding="utf-8")
            self.assertIn('"status":"partial"', report)
            self.assertIn('"missing_rows":1', report)
