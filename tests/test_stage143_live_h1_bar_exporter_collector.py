from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.stage143_live_h1_bar_exporter_collector import collect, DEFAULT_BARS_FILE, DEFAULT_KV_FILE, read_mt5_tab_bars

def test_parse_mt5_tab_bars(tmp_path):
    p = tmp_path / DEFAULT_BARS_FILE
    p.write_text(
        "<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>\n"
        "2026.07.01\t10:00:00\t3971.64\t3978.02\t3960.04\t3975.83\t5206\t0\t33\n"
        "2026.07.01\t11:00:00\t3975.60\t3984.14\t3969.21\t3976.95\t2833\t0\t33\n",
        encoding="utf-8"
    )
    rows, meta = read_mt5_tab_bars(p)
    assert len(rows) == 2
    assert rows[-1]["utc_time"].isoformat().startswith("2026-07-01T11:00:00")

def test_missing_export_file(tmp_path):
    root = tmp_path
    mt5_files = tmp_path / "MQL5/Files"
    mt5_ind = tmp_path / "MQL5/Indicators/XAUUSD"
    mt5_files.mkdir(parents=True)
    mt5_ind.mkdir(parents=True)
    summary = collect(root, mt5_files, mt5_ind, DEFAULT_BARS_FILE, DEFAULT_KV_FILE, 240, False, False)
    assert summary["decision"] == "STAGE143_EXPORT_FILE_MISSING_ATTACH_INDICATOR"

def test_ready_export_file(tmp_path):
    root = tmp_path
    mt5_files = tmp_path / "MQL5/Files"
    mt5_ind = tmp_path / "MQL5/Indicators/XAUUSD"
    mt5_files.mkdir(parents=True)
    mt5_ind.mkdir(parents=True)
    lines = ["<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>"]
    for i in range(120):
        lines.append(f"2026.07.01\t{i%24:02d}:00:00\t1\t2\t0.5\t1.5\t100\t0\t30")
    (mt5_files / DEFAULT_BARS_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")
    (mt5_files / DEFAULT_KV_FILE).write_text(
        "generated_utc|2026-07-01T12:00:00Z\n"
        "symbol|XAUUSD\n"
        "period|H1\n"
        "bars_written|120\n"
        "last_closed_bar_utc|2026-07-01T10:00:00Z\n",
        encoding="utf-8"
    )
    summary = collect(root, mt5_files, mt5_ind, DEFAULT_BARS_FILE, DEFAULT_KV_FILE, 240, False, True)
    assert summary["decision"] == "STAGE143_LIVE_H1_EXPORT_READY_FOR_STAGE138"
    assert summary["bar_count"] == 120
    assert Path(summary["mt5_collector_status_kv"]).exists()
