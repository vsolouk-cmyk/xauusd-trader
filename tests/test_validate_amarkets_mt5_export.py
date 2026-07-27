from __future__ import annotations

import importlib.util
import tempfile
import unittest
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "validate_amarkets_mt5_export.py"
spec = importlib.util.spec_from_file_location("validator", MODULE_PATH)
validator = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = validator
spec.loader.exec_module(validator)

HEADER = "\t".join(validator.EXPECTED) + "\n"


class ValidatorTests(unittest.TestCase):
    def write(self, body: str) -> Path:
        directory = Path(tempfile.mkdtemp())
        path = directory / "data.csv"
        path.write_text(HEADER + body, encoding="utf-8")
        return path

    def test_valid(self):
        path = self.write(
            "2026.07.24\t10:00\t4000\t4010\t3990\t4005\t10\t20\t0\n"
            "2026.07.24\t11:00\t4005\t4015\t4000\t4010\t12\t18\t0\n"
        )
        result = validator.validate(path)
        self.assertTrue(result.pass_)
        self.assertEqual(result.rows, 2)

    def test_duplicate(self):
        path = self.write(
            "2026.07.24\t10:00\t4000\t4010\t3990\t4005\t10\t20\t0\n"
            "2026.07.24\t10:00\t4005\t4015\t4000\t4010\t12\t18\t0\n"
        )
        result = validator.validate(path)
        self.assertFalse(result.pass_)
        self.assertEqual(result.duplicate_timestamps, 1)

    def test_invalid_ohlc(self):
        path = self.write("2026.07.24\t10:00\t4000\t3999\t3990\t4005\t10\t20\t0\n")
        result = validator.validate(path)
        self.assertFalse(result.pass_)
        self.assertEqual(result.invalid_ohlc, 1)

    def test_bad_header(self):
        directory = Path(tempfile.mkdtemp())
        path = directory / "data.csv"
        path.write_text("bad\theader\n", encoding="utf-8")
        result = validator.validate(path)
        self.assertFalse(result.pass_)
        self.assertIn("unexpected header", result.error or "")


if __name__ == "__main__":
    unittest.main()
