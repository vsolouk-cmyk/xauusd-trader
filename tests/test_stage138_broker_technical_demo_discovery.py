from pathlib import Path
import csv
import math
import sys
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.stage138_broker_technical_demo_discovery import run, normalize_bars, read_table, add_features

def make_mt5_tab(path: Path, n=650):
    path.parent.mkdir(parents=True, exist_ok=True)
    base = datetime(2026, 1, 1)
    price = 2000.0
    lines = ["<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>"]
    for i in range(n):
        drift = 0.8 if (i % 50) < 35 else -0.25
        price += drift + math.sin(i / 10.0) * 0.15
        dt = base + timedelta(hours=i)
        lines.append(f"{dt:%Y.%m.%d}\t{dt:%H:%M:%S}\t{price-0.5:.2f}\t{price+1.5:.2f}\t{price-1.5:.2f}\t{price:.2f}\t1000\t0\t35")
    path.write_text("\n".join(lines), encoding="utf-8")

def test_mt5_tab_parser_normalizes_rows(tmp_path):
    p = tmp_path / "amarkets_xauusd_1h.csv"
    make_mt5_tab(p, 400)
    raw = read_table(p)
    bars = normalize_bars(raw)
    assert len(raw) == 400
    assert len(bars) == 400
    assert bars[-1]["close"] > 0
    assert bars[0]["utc_time"].year == 2026

def test_run_writes_stage134_compatible_kv_from_mt5_tab(tmp_path):
    root = tmp_path
    bars = tmp_path / "Downloads/xauusd_fundamental_event_inbox/amarkets_xauusd_1h.csv"
    make_mt5_tab(bars, 700)
    mt5 = tmp_path / "MQL5/Files"
    mt5.mkdir(parents=True)
    summary = run(root, bars, mt5, horizon=24, min_events=10, min_mean_bps=-5.0, min_hit=0.40, max_pair_features=5, write_mt5=True)
    assert summary["raw_row_count"] == 700
    assert summary["bar_count"] == 700
    assert Path(summary["mt5_kv"]).exists()
    text = Path(summary["mt5_kv"]).read_text(encoding="utf-8")
    assert "allow_trading|false" in text
    assert "order_send|false" in text

def test_explicit_missing_bar_file_raises(tmp_path):
    root = tmp_path
    mt5 = tmp_path / "MQL5/Files"
    mt5.mkdir(parents=True)
    try:
        run(root, root/"explicit_missing.csv", mt5, 24, 10, 0.0, 0.4, 5, False)
    except FileNotFoundError:
        return
    assert False, "expected FileNotFoundError"
