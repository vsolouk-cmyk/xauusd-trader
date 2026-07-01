from pathlib import Path
import csv
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.stage136_live_signal_broad_discovery import run, read_live_signal

def make_dataset(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["utc_time", "fwd_ret_bps_h120", "feat_a", "feat_b", "feat_c"]
    rows = []
    for i in range(240):
        good = i % 4 == 0 or i > 220
        rows.append({
            "utc_time": f"2026-01-{(i%28)+1:02d} 00:00:00+00:00",
            "fwd_ret_bps_h120": "25" if good else "-2",
            "feat_a": "10" if good else "1",
            "feat_b": "5" if good else "8",
            "feat_c": str(i % 11),
        })
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

def test_read_live_signal_header_row(tmp_path):
    p = tmp_path / "unified_observer_signal.csv"
    p.write_text("feature_date,feat_a,feat_b\n2026-06-30,10,5\n", encoding="utf-8")
    d = read_live_signal(p)
    assert d["feat_a"] == "10"
    assert d["feature_date"] == "2026-06-30"

def test_run_selects_current_active_candidate(tmp_path):
    root = tmp_path
    ds = root / "data/fundamental_event_inbox/features/stage117_joined_macro_cot_dollar_h1_research_dataset.csv"
    make_dataset(ds)
    mt5 = tmp_path / "MQL5/Files"
    mt5.mkdir(parents=True)
    (mt5 / "unified_observer_signal.csv").write_text("feature_date,feat_a,feat_b,feat_c\n2026-06-30,10,5,1\n", encoding="utf-8")
    summary = run(root, ds, mt5, "unified_observer_signal.csv", 0, 5, 1.0, 0.45, 3, True)
    assert summary["candidate_rows"] > 0
    assert Path(summary["mt5_kv"]).exists()
    assert "STAGE136" in summary["decision"]

def test_missing_live_signal_summary(tmp_path):
    root = tmp_path
    ds = root / "data/fundamental_event_inbox/features/stage117_joined_macro_cot_dollar_h1_research_dataset.csv"
    make_dataset(ds)
    mt5 = tmp_path / "MQL5/Files"
    mt5.mkdir(parents=True)
    summary = run(root, ds, mt5, "missing.csv", 0, 5, 1.0, 0.45, 3, False)
    assert summary["decision"] == "STAGE136_LIVE_SIGNAL_FILE_MISSING_OR_EMPTY"
