from pathlib import Path
import tempfile
import json
import importlib.util
import sys
import pandas as pd

MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "stage92_intraday_session_residual_thesis_discovery.py"
spec = importlib.util.spec_from_file_location("stage92", MODULE_PATH)
stage92 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = stage92
spec.loader.exec_module(stage92)


def test_normalize_amarkets_mt5_tab_headers():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "amarkets_xauusd_15m.csv"
        rows = ["<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>"]
        base = pd.Timestamp("2024-01-01 00:00:00")
        for i in range(12):
            t = base + pd.Timedelta(minutes=15*i)
            rows.append(f"{t:%Y.%m.%d}\t{t:%H:%M:%S}\t2000\t2001\t1999\t2000.5\t100\t0\t25")
        p.write_text("\n".join(rows), encoding="utf-8")
        df = stage92.normalize_intraday_csv(p)
        assert len(df) == 12
        assert {"utc_time", "open", "high", "low", "close", "spread"}.issubset(df.columns)
        assert stage92.infer_timeframe_from_median_delta(df) == "m15"


def test_load_preferred_intraday_finds_downloads_style_file():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        downloads = root / "Downloads"
        downloads.mkdir()
        p = downloads / "amarkets_xauusd_15m.csv"
        rows = ["<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>"]
        base = pd.Timestamp("2024-01-01 00:00:00")
        for i in range(20):
            t = base + pd.Timedelta(minutes=15*i)
            rows.append(f"{t:%Y.%m.%d}\t{t:%H:%M:%S}\t2000\t2001\t1999\t2000.5\t100\t0\t25")
        p.write_text("\n".join(rows), encoding="utf-8")
        cfg = {
            "preferred_timeframe": "m15",
            "intraday_files": {
                "m15": [str(downloads / "amarkets_xauusd_15m.csv")],
                "m5": [],
                "h1": []
            }
        }
        df, selected, inv = stage92.load_preferred_intraday(root, cfg)
        assert len(df) == 20
        assert selected["read_ok"] is True
        assert selected["inferred_timeframe"] == "m15"
        assert inv and inv[0]["read_ok"] is True


if __name__ == "__main__":
    test_normalize_amarkets_mt5_tab_headers()
    test_load_preferred_intraday_finds_downloads_style_file()
    print("Stage92B loader-fix tests passed")
