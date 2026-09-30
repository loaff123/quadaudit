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
