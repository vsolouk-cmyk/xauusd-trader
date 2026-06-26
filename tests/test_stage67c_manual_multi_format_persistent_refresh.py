import importlib.util
from pathlib import Path
import tempfile
import pandas as pd
import json

SCRIPT = Path(__file__).resolve().parents[1] / "app" / "stage67c_manual_multi_format_persistent_refresh.py"
spec = importlib.util.spec_from_file_location("s67c", SCRIPT)
s67c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s67c)


def test_mt5_angle_bracket_header_parse():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "amarkets_xauusd_5m.csv"
        p.write_text("<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>\n2026.06.25\t00:00:00\t2300\t2301\t2299\t2300.5\t1\t0\t12\n", encoding="utf-8")
        df, info = s67c.canonicalize_mt5_gold_m5(p)
        assert len(df) == 1
        assert float(df.iloc[0]["close"]) == 2300.5
        assert info["rows"] == 1


def test_merge_never_truncates_existing_history():
    existing = pd.DataFrame({"date_utc": ["2020-01-01", "2020-01-02"], "dxy": [1.0, 2.0]})
    incoming = pd.DataFrame({"date_utc": ["2020-01-02"], "dxy": [2.5]})
    combined, info = s67c.merge_on_key(existing, incoming)
    assert len(combined) == 2
    assert combined.loc[combined["date_utc"] == "2020-01-02", "dxy"].iloc[0] == 2.5
    assert info["after_rows"] >= info["before_rows"]


def test_fred_csv_parse():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "DFII10.csv"
        p.write_text("observation_date,DFII10\n2026-06-25,1.75\n", encoding="utf-8")
        df, info = s67c.canonicalize_market_csv(p, "real_yield")
        assert len(df) == 1
        assert df.iloc[0]["real_yield"] == 1.75

if __name__ == "__main__":
    test_mt5_angle_bracket_header_parse()
    test_merge_never_truncates_existing_history()
    test_fred_csv_parse()
    print("Stage67C tests passed")
