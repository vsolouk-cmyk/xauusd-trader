from pathlib import Path
import importlib.util

MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "stage126c_indicator_readability_and_pipe_kv_hotfix.py"

spec = importlib.util.spec_from_file_location("stage126c", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_indicators_support_pipe_and_comma_and_layout_is_readable():
    assert "ReadKvFlexible" in mod.RULE8_INDICATOR
    assert "ReadKvFlexible" in mod.RULE9_INDICATOR
    assert "ReadKvDelimited(fname, '|'" in mod.RULE9_INDICATOR
    assert "ReadKvDelimited(fname, ','" in mod.RULE9_INDICATOR
    assert "InpFontSize = 7" in mod.RULE8_INDICATOR
    assert "InpFontSize = 7" in mod.RULE9_INDICATOR
    assert "InpLineHeight = 22" in mod.RULE8_INDICATOR
    assert "InpLineHeight = 22" in mod.RULE9_INDICATOR
    assert "InpY = 430" in mod.RULE8_INDICATOR
    assert "InpY = 540" in mod.RULE9_INDICATOR


def test_no_order_surface_and_writes_files(tmp_path):
    assert "OrderSend" not in mod.RULE8_INDICATOR
    assert "OrderSend" not in mod.RULE9_INDICATOR
    assert "CTrade" not in mod.RULE8_INDICATOR
    assert "CTrade" not in mod.RULE9_INDICATOR
    mt5_files = tmp_path / "MQL5" / "Files"
    mt5_files.mkdir(parents=True)
    (mt5_files / "xauusd_stage124f_rule8_overlay_kv.csv").write_text("rule_id,abc\n", encoding="utf-8")
    (mt5_files / "xauusd_stage126_rule9_frontier_status_kv.csv").write_text("candidate_status|PASS\n", encoding="utf-8")
    summary = mod.run(tmp_path, mt5_files, tmp_path / "MT5Indicators", tmp_path / "MT5Indicators" / "Advisors" / "XAUUSD", True)
    assert summary["status"] == mod.STATUS_OK
    assert Path(summary["repo_rule8_indicator"]).exists()
    assert Path(summary["repo_rule9_indicator"]).exists()
    assert Path(summary["mt5_root_rule9_indicator"]).exists()
    assert summary["rule9_status_file_exists"] is True
