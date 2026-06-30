from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.stage133_unified_observer_rule_state_telemetry_writer import patch_mql5_source, run, KV_FILE, LATEST_CSV

def sample_ea():
    return """
#property strict
string GetValue(const string &keys[], const string &vals[], int n, string key, string fallback="")
{
   return fallback;
}
void UpdateChartComment(const string &keys[], const string &vals[], int n)
{
}
void DisplaySignal()
{
   string keys[];
   string vals[];
   int n = 0;
   if(!ReadSignal(keys, vals, n)) return;

   UpdateChartComment(keys, vals, n);

   Print("Unified observer bridge");
}
"""

def test_patch_adds_rule_block_and_call():
    patched, meta = patch_mql5_source(sample_ea())
    assert "STAGE133_RULE_STATE_TELEMETRY_BLOCK_BEGIN" in patched
    assert 'Stage133_WriteRuleTelemetryIfDue(keys, vals, n, "DisplaySignal");' in patched
    assert not meta["forbidden_added_tokens"]

def test_patch_idempotent():
    p1, _ = patch_mql5_source(sample_ea())
    p2, meta2 = patch_mql5_source(p1)
    assert p2.count("STAGE133_RULE_STATE_TELEMETRY_BLOCK_BEGIN") == 1
    assert p2.count('Stage133_WriteRuleTelemetryIfDue(keys, vals, n, "DisplaySignal");') == 1
    assert meta2["already_patched"] is True

def test_run_patches_fake_ea_and_copies(tmp_path):
    root = tmp_path
    repo = root / "mt5"
    mt5_files = tmp_path / "MQL5/Files"
    mt5_experts = tmp_path / "MQL5/Experts/Advisors/XAUUSD"
    repo.mkdir(parents=True)
    mt5_files.mkdir(parents=True)
    ea = repo / "Unified_ObserverOnly_EA.mq5"
    ea.write_text(sample_ea(), encoding="utf-8")
    summary = run(root, mt5_files, mt5_experts, str(ea), True, True, 180, True)
    assert summary["patch_result"]["changed"] is True
    assert Path(summary["mt5_ea_written"]).exists()
    assert "STAGE133_RULE_STATE_TELEMETRY_BLOCK_BEGIN" in ea.read_text(encoding="utf-8")
    assert Path(summary["mt5_status_kv"]).exists()

def test_collects_fresh_rule_state(tmp_path):
    root = tmp_path
    mt5_files = tmp_path / "MQL5/Files"
    mt5_experts = tmp_path / "MQL5/Experts"
    mt5_files.mkdir(parents=True)
    mt5_experts.mkdir(parents=True)
    (mt5_files / KV_FILE).write_text(
        "stage|Stage133_UNIFIED_OBSERVER_RULE_STATE_TELEMETRY_WRITER\n"
        "status|RULE_STATE_TELEMETRY_ALIVE_NO_ORDER\n"
        "allow_trading|false\n"
        "order_send|false\n"
        "selected_rule_id|\n"
        "rule_count|7\n"
        "active_rule_count|0\n",
        encoding="utf-8"
    )
    (mt5_files / LATEST_CSV).write_text(
        "rule_id,rule_active\n"
        "K06,false\nK03,false\nK07,false\nS83_14,false\nS83_13,false\nC96_07,false\nS105_03,false\n",
        encoding="utf-8"
    )
    summary = run(root, mt5_files, mt5_experts, None, False, False, 999999, False)
    assert summary["rule_state_exists"] is True
    assert summary["rule_state_fresh"] is True
    assert summary["latest_rows"] == 7
    assert "CONFIRMED" in summary["decision"]
