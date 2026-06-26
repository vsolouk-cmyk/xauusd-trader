import json
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import pandas as pd

import stage67b_manual_persistent_data_refresh_multi_readiness as s67


def test_mt5_angle_bracket_headers_parse_to_d1():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        src = p / "amarkets_xauusd_5m.csv"
        tgt = p / "gold_d1.csv"
        src.write_text(
            "<DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<TICKVOL>,<VOL>,<SPREAD>\n"
            "2026.06.25,00:00:00,3300,3310,3290,3305,10,0,25\n"
            "2026.06.25,00:05:00,3305,3320,3300,3315,11,0,24\n",
            encoding="utf-8",
        )
        res = s67.import_gold_m5_to_d1(src, tgt)
        assert res["status"] == "PASS", res
        out = pd.read_csv(tgt)
        assert len(out) == 1
        assert out.loc[0, "date_utc"] == "2026-06-25"
        assert float(out.loc[0, "open"]) == 3300
        assert float(out.loc[0, "high"]) == 3320
        assert float(out.loc[0, "low"]) == 3290
        assert float(out.loc[0, "close"]) == 3315


def test_persistent_merge_preserves_history_with_one_new_row():
    existing = pd.DataFrame({"date_utc": ["2026-06-24"], "dxy": [100.0]})
    incoming = pd.DataFrame({"date_utc": ["2026-06-25"], "dxy": [101.0]})
    merged = s67.merge_by_date(existing, incoming)
    assert list(merged["date_utc"]) == ["2026-06-24", "2026-06-25"]
    assert float(merged.loc[merged["date_utc"] == "2026-06-25", "dxy"].iloc[0]) == 101.0


def test_normalize_fred_series():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        src = p / "real_yield.csv"
        tgt = p / "target.csv"
        src.write_text("DATE,DFII10\n2026-06-24,1.88\n2026-06-25,1.91\n", encoding="utf-8")
        res = s67.normalize_exogenous(src, tgt, "real_yield")
        assert res["status"] == "PASS", res
        out = pd.read_csv(tgt)
        assert list(out.columns) == ["date_utc", "real_yield"]
        assert out["date_utc"].iloc[-1] == "2026-06-25"


if __name__ == "__main__":
    test_mt5_angle_bracket_headers_parse_to_d1()
    test_persistent_merge_preserves_history_with_one_new_row()
    test_normalize_fred_series()
    print("Stage67B tests passed")
