from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.stage128b_compact_dashboard_indicator_write_hotfix import run, INDICATOR_NAME

def test_indicator_written(tmp_path):
    root = tmp_path
    mt5_files = tmp_path / "MQL5/Files"
    mt5_ind = tmp_path / "MQL5/Indicators"
    summary = run(root, mt5_files, mt5_ind)
    assert summary["status"] == "STAGE128B_COMPLETE_INDICATOR_WRITTEN_NO_ORDER"
    assert (mt5_ind / INDICATOR_NAME).exists()
    assert (mt5_ind / "Advisors/XAUUSD" / INDICATOR_NAME).exists()
    assert (mt5_files / "xauusd_stage128_forward_shadow_and_megascan_status_kv.csv").exists()
    assert "NO_ORDER_SEND" in summary["hard_blocks"]
