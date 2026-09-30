"""Replaceable subprocess isolation and append-only experiment evidence."""

from __future__ import annotations
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import multiprocessing as mp
from pathlib import Path
import platform
import subprocess
import sys
import time
from .adapters import RunConfig, empty_result, run_case
from .model import Case
from . import __version__


def canonical(value) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
        + "\n"
    ).encode()


def _worker(conn, memory_mb):
    # Import cost is outside each measured case, but startup has its own bound.
    for name in ("scipy.integrate", "mpmath"):
        try:
            __import__(name)
        except ImportError:
            pass
    memory = {"requested_mb": memory_mb, "enforced": False, "mechanism": None}
    if memory_mb is not None:
        try:
            import resource

            resource.setrlimit(
                resource.RLIMIT_AS, (memory_mb * 1024 * 1024, memory_mb * 1024 * 1024)
            )
            memory.update(enforced=True, mechanism="RLIMIT_AS absolute virtual address space")
        except (ImportError, AttributeError, OSError, ValueError) as exc:
            memory["reason"] = str(exc)
    conn.send({"ready": True, "memory_limit": memory})
    while True:
        task = conn.recv()
        if task is None:
            break
        try:
            case = Case.from_dict(task[0])
            config = RunConfig(**task[1])
            conn.send(run_case(case, config))
        except BaseException as exc:
            conn.send({"worker_error": f"{type(exc).__name__}: {exc}"})
    conn.close()


class IsolatedRunner:
    def __init__(
        self, timeout_seconds: float = 10, memory_mb: int | None = None, worker_target=None
    ):
        if not 0 < timeout_seconds <= 3600:
            raise ValueError("timeout outside (0,3600]")
        if memory_mb is not None and (not isinstance(memory_mb, int) or memory_mb < 256):
            raise ValueError("memory ceiling must be at least 256 MiB")
        self.timeout_seconds = timeout_seconds
        self.memory_mb = memory_mb
        self.target = worker_target or _worker
        self.context = mp.get_context("spawn")
        self.process = None
        self.conn = None
        self.ready = None

    def _start(self):
        self.conn, child = self.context.Pipe()
        self.process = self.context.Process(
            target=self.target, args=(child, self.memory_mb), daemon=True
        )
        self.process.start()
        child.close()
        if not self.conn.poll(60):
            self.close()
            raise RuntimeError("worker startup timed out")
        self.ready = self.conn.recv()
        if not self.ready.get("ready"):
            self.close()
            raise RuntimeError("worker failed startup handshake")

    def run(self, case: Case, config: RunConfig) -> dict:
        if self.process is None:
            self._start()
        started = time.perf_counter()
        memory = self.ready["memory_limit"]
        out = None
        try:
            self.conn.send((case.to_dict(), asdict(config)))
            if self.conn.poll(self.timeout_seconds):
                out = self.conn.recv()
                if "worker_error" in out:
                    message = out["worker_error"]
                    out = empty_result(case, config)
                    out.update(outcome="worker_error", message=message)
            else:
                out = empty_result(case, config)
                out.update(
                    outcome="timeout",
                    message="Parent terminated the worker at the wall-clock deadline",
                )
                self.close()
        except (EOFError, BrokenPipeError, ConnectionResetError, OSError) as exc:
            out = empty_result(case, config)
            out.update(outcome="worker_crash", message=str(exc))
            self.close()
        out["isolation"] = {
            "process_start": "spawn",
            "timeout_seconds": self.timeout_seconds,
            "memory_limit": memory,
            "roundtrip_seconds": time.perf_counter() - started,
        }
        if out["outcome"] in ("timeout", "worker_crash", "worker_error"):
            # Never fabricate zero work when abrupt termination discarded the worker counters.
            out["work"] = {
                "budget": config.budget,
                "evaluations": None,
                "accounting": "unavailable_after_worker_termination",
            }
        return out

    def close(self):
        if self.process is not None:
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(2)
                if self.process.is_alive():
                    self.process.kill()
                    self.process.join(2)
            else:
                self.process.join()
            self.process.close()
            self.process = None
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _environment():
    versions = {}
    for name in ("scipy", "numpy", "mpmath"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    try:
        root = Path(__file__).resolve().parents[2]
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True))
    except (OSError, subprocess.SubprocessError):
        commit = None
        dirty = None
    return {
        "quadaudit": __version__,
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "dependencies": versions,
        "source_commit": commit,
        "source_dirty": dirty,
    }


def experiment(
    cases: list[Case],
    configs: list[RunConfig],
    output_dir: Path,
    timeout_seconds: float = 10,
    memory_mb: int | None = None,
    progress=None,
) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if (output_dir / "results.jsonl").exists():
        raise FileExistsError(
            "Refusing to overwrite existing experiment results; choose a fresh directory"
        )
    if len({c.case_id for c in cases}) != len(cases):
        raise ValueError("duplicate case IDs")
    encoded_configs = [canonical(asdict(c)) for c in configs]
    if len(set(encoded_configs)) != len(configs):
        raise ValueError("duplicate configurations")
    environment = _environment()
    corpus = b"".join(canonical(c.to_dict()) for c in cases)
    protocol = {
        "configs": [asdict(c) for c in configs],
        "timeout_seconds": timeout_seconds,
        "memory_mb": memory_mb,
        "order": "case-major then configuration order",
        "callback_cost_note": "Exact rational evaluation is expensive. Evaluation caps are not total computational fairness.",
        "timeout_accounting": "Abruptly terminated worker evaluation counts are unavailable, never reported as zero.",
    }
    (output_dir / "corpus.jsonl").write_bytes(corpus)
    (output_dir / "protocol.json").write_bytes(canonical(protocol))
    manifest = {
        "schema": "quadaudit.experiment.v1",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "complete": False,
        "expected_runs": len(cases) * len(configs),
        "completed_runs": 0,
        "corpus_sha256": hashlib.sha256(corpus).hexdigest(),
        "protocol_sha256": hashlib.sha256(canonical(protocol)).hexdigest(),
        "environment": environment,
        "case_count": len(cases),
        "protocol": protocol,
    }
    mpth = output_dir / "manifest.json"
    mpth.write_bytes(canonical(manifest))
    try:
        with (
            IsolatedRunner(timeout_seconds, memory_mb) as runner,
            (output_dir / "results.jsonl").open("w", encoding="utf-8") as f,
        ):
            for case in cases:
                for config in configs:
                    row = runner.run(case, config)
                    f.write(canonical(row).decode())
                    f.flush()
                    manifest["completed_runs"] += 1
                    if progress:
                        progress(manifest["completed_runs"], manifest["expected_runs"], row)
        manifest["complete"] = True
    finally:
        manifest["ended_at"] = datetime.now(timezone.utc).isoformat()
        result_path = output_dir / "results.jsonl"
        manifest["results_sha256"] = (
            hashlib.sha256(result_path.read_bytes()).hexdigest() if result_path.exists() else None
        )
        mpth.write_bytes(canonical(manifest))
    return manifest


MAX_RESULTS_BYTES = 256 * 1024 * 1024
MAX_RESULT_LINE_BYTES = 20 * 1024 * 1024


def verify_experiment_artifacts(directory: Path) -> dict:
    """Detect missing, truncated, or modified artifacts; hashes are integrity, not signatures."""
    directory = Path(directory)
    mpth = directory / "manifest.json"
    if mpth.stat().st_size > 1024 * 1024:
        raise ValueError("oversized experiment manifest")
    manifest = json.loads(mpth.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema") != "quadaudit.experiment.v1":
        raise ValueError("unsupported experiment manifest")
    for field in ("expected_runs", "completed_runs"):
        value = manifest.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 50000:
            raise ValueError("invalid manifest run count")
    if not isinstance(manifest.get("complete"), bool):
        raise ValueError("invalid completion marker")
    if manifest["completed_runs"] > manifest["expected_runs"] or (
        manifest["complete"] and manifest["completed_runs"] != manifest["expected_runs"]
    ):
        raise ValueError("inconsistent completion counts")
    for filename, key in (
        ("corpus.jsonl", "corpus_sha256"),
        ("protocol.json", "protocol_sha256"),
        ("results.jsonl", "results_sha256"),
    ):
        path = directory / filename
        if path.stat().st_size > MAX_RESULTS_BYTES:
            raise ValueError("oversized experiment artifact")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != manifest.get(key):
            raise ValueError(f"artifact hash mismatch: {filename}")
    return manifest


def read_results(path: Path):
    path = Path(path)
    if path.stat().st_size > MAX_RESULTS_BYTES:
        raise ValueError("results exceed256MiB input limit")
    with path.open(encoding="utf-8") as f:
        line_no = 0
        while True:
            line = f.readline(MAX_RESULT_LINE_BYTES + 1)
            if not line:
                break
            line_no += 1
            if len(line) > MAX_RESULT_LINE_BYTES or line_no > 50000:
                raise ValueError(f"oversized result row/count at {line_no}")
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at row {line_no}") from exc
            if not isinstance(row, dict) or row.get("schema") != "quadaudit.result.v1":
                raise ValueError(f"unsupported result schema at row {line_no}")
            yield row
