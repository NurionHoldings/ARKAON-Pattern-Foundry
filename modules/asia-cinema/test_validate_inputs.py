"""Standard-library tests for isolated PR-A validator."""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).with_name("validate_inputs.py")
spec = importlib.util.spec_from_file_location("asia_cinema_validator", MODULE)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)

class InputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        assets = {}
        for name, raw in (
            ("reference", b"reference"),
            ("symbol_mask", b"mask"),
            ("slogan", validator.SLOGAN.encode("utf-8")),
        ):
            (self.root / name).write_bytes(raw)
            assets[name] = {"path": name, "sha256": hashlib.sha256(raw).hexdigest()}
        assets["slogan"]["status"] = "approved"
        self.data = {"assets": assets}
        self.path = self.root / "manifest.json"

    def check(self):
        self.path.write_text(json.dumps(self.data), encoding="utf-8")
        return validator.validate(self.path)

    def test_valid(self):
        self.assertEqual(self.check()["status"], "PASS")

    def test_missing(self):
        del self.data["assets"]["reference"]
        self.assertEqual(self.check()["status"], "FAIL")

    def test_tampered(self):
        (self.root / "symbol_mask").write_bytes(b"changed")
        self.assertIn("sha256 mismatch", str(self.check()["errors"]))

    def test_unapproved(self):
        self.data["assets"]["slogan"]["status"] = "pending"
        self.assertEqual(self.check()["status"], "FAIL")

    def test_invalid_utf8(self):
        raw = b"\\xff"
        (self.root / "slogan").write_bytes(raw)
        self.data["assets"]["slogan"]["sha256"] = hashlib.sha256(raw).hexdigest()
        self.assertEqual(self.check()["status"], "FAIL")

    def test_path_escape(self):
        self.data["assets"]["reference"]["path"] = "../outside"
        self.assertEqual(self.check()["status"], "FAIL")

if __name__ == "__main__":
    unittest.main()
