from pathlib import Path
import csv
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.stage137_fuzzy_live_schema_bridge_discovery import run, similarity, read_live_signal

def make_dataset(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["utc_time", "fwd_ret_bps_h120", "dxy_ret_20d", "real_yield_change_20d", "cot_mm_net_z"]
    rows = []
    for i in range(260):
        good = i % 4 == 0 or i > 220
        rows.append({
            "utc_time": f"2026-01-{(i%28)+1:02d} 00:00:00+00:00",
            "fwd_ret_bps_h120": "22" if good else "-2",
            "dxy_ret_20d": "-2" if good else "3",
            "real_yield_change_20d": "-1" if good else "2",
            "cot_mm_net_z": "0.2" if good else "1.5",
        })
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

def test_similarity_aliases():
    assert similarity("dxy_ret_20d", "Dollar Index Return 20D") >= 0.42
    assert similarity("real_yield_change_20d", "real yield delta 20d") >= 0.42

def test_run_fuzzy_bridge(tmp_path):
    root = tmp_path
    ds = root / "data/fundamental_event_inbox/features/stage117_joined_macro_cot_dollar_h1_research_dataset.csv"
    make_dataset(ds)
    mt5 = tmp_path / "MQL5/Files"
    mt5.mkdir(parents=True)
    (mt5 / "unified_observer_signal.csv").write_text(
        "feature_date,Dollar Index Return 20D,real yield delta 20d,cot mm net z\n"
        "2026-06-30,-2,-1,0.2\n",
        encoding="utf-8"
    )
    summary = run(root, ds, mt5, "unified_observer_signal.csv", 0, 5, 1.0, 0.45, 0.42, 3, True)
    assert summary["mapped_features"] >= 2
    assert summary["candidate_rows"] > 0
    assert Path(summary["mt5_kv"]).exists()
    assert "STAGE137" in summary["decision"]

def test_missing_live_file(tmp_path):
    root = tmp_path
    ds = root / "data/fundamental_event_inbox/features/stage117_joined_macro_cot_dollar_h1_research_dataset.csv"
    make_dataset(ds)
    mt5 = tmp_path / "MQL5/Files"
    mt5.mkdir(parents=True)
    summary = run(root, ds, mt5, "missing.csv", 0, 5, 1.0, 0.45, 0.42, 3, False)
    assert summary["decision"] == "STAGE137_LIVE_SIGNAL_FILE_MISSING_OR_EMPTY"
