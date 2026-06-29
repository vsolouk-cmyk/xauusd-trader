from pathlib import Path
import importlib.util

MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "stage126b_indicator_visibility_and_overlay_layout_hotfix.py"

spec = importlib.util.spec_from_file_location("stage126b", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_indicator_sources_have_expected_filenames_and_offsets():
    assert 'xauusd_stage124f_rule8_overlay_kv.csv' in mod.RULE8_INDICATOR
    assert 'xauusd_stage126_rule9_frontier_status_kv.csv' in mod.RULE9_INDICATOR
    assert 'InpY = 360' in mod.RULE8_INDICATOR
    assert 'InpY = 450' in mod.RULE9_INDICATOR
    assert 'OrderSend' not in mod.RULE8_INDICATOR
    assert 'OrderSend' not in mod.RULE9_INDICATOR
    assert 'CTrade' not in mod.RULE8_INDICATOR
    assert 'CTrade' not in mod.RULE9_INDICATOR


def test_run_writes_repo_indicators(tmp_path):
    mt5_files = tmp_path / "MQL5" / "Files"
    mt5_files.mkdir(parents=True)
    (mt5_files / "xauusd_stage124f_rule8_overlay_kv.csv").write_text("rule_id,abc\n", encoding="utf-8")
    (mt5_files / "xauusd_stage126_rule9_frontier_status_kv.csv").write_text("rule_id,def\n", encoding="utf-8")
    summary = mod.run(tmp_path, mt5_files, tmp_path / "MT5Indicators", tmp_path / "MT5Indicators" / "Advisors" / "XAUUSD", True)
    assert summary["status"] == mod.STATUS_OK
    assert Path(summary["repo_rule8_indicator"]).exists()
    assert Path(summary["repo_rule9_indicator"]).exists()
    assert Path(summary["mt5_root_rule9_indicator"]).exists()
    assert Path(summary["mt5_nested_rule9_indicator"]).exists()
    assert summary["rule8_status_file_exists"] is True
    assert summary["rule9_status_file_exists"] is True
