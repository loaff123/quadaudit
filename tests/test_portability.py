"""Exercise byte preservation under Windows-style Git checkout conversion."""

import hashlib
from importlib.resources import files
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


@unittest.skipUnless(shutil.which("git"), "Git is required for checkout-policy verification")
class PortabilityTests(unittest.TestCase):
    def test_frozen_bytes_survive_autocrlf_checkout(self):
        payload = files("quadaudit").joinpath("data/core-v1.jsonl").read_bytes()
        source_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo, checkout = root / "repo", root / "checkout"
            repo.mkdir()
            checkout.mkdir()

            def git(*args):
                return subprocess.run(
                    ["git", *args],
                    cwd=repo,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

            git("init", "-q")
            git("config", "core.autocrlf", "true")
            attributes = source_root / ".gitattributes"
            if attributes.exists():
                shutil.copy2(attributes, repo / ".gitattributes")
            (repo / "frozen.jsonl").write_bytes(payload)
            binary = b"PK\x03\x04\0\0\n\r\nreference\0"
            (repo / "snapshot.zip").write_bytes(binary)
            git("add", "--all")
            git("checkout-index", "--all", "--prefix=" + checkout.as_posix() + "/")
            actual = (checkout / "frozen.jsonl").read_bytes()
            self.assertEqual(
                hashlib.sha256(actual).hexdigest(), hashlib.sha256(payload).hexdigest()
            )
            self.assertEqual((checkout / "snapshot.zip").read_bytes(), binary)
