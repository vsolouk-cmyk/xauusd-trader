from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.stage132_unified_observer_ea_telemetry_writer_patch import patch_mql5_source, run, HEARTBEAT_KV

def test_patch_adds_block_and_calls():
    src = """
#property strict
int OnInit()
{
   return(INIT_SUCCEEDED);
}
void OnTick()
{
   int x = 1;
}
"""
    patched, meta = patch_mql5_source(src)
    assert "STAGE132_TELEMETRY_BLOCK_BEGIN" in patched
    assert 'Stage132_WriteTelemetryNow("OnInit");' in patched
    assert 'Stage132_WriteTelemetryIfDue("OnTick");' in patched
    assert not meta["forbidden_added_tokens"]

def test_patch_idempotent():
    src = """
#property strict
int OnInit()
{
   return(INIT_SUCCEEDED);
}
"""
    p1, _ = patch_mql5_source(src)
    p2, meta2 = patch_mql5_source(p1)
    assert p2.count("STAGE132_TELEMETRY_BLOCK_BEGIN") == 1
    assert p2.count('Stage132_WriteTelemetryNow("OnInit");') == 1
    assert meta2["already_patched"] is True

def test_run_patches_fake_ea_and_copies(tmp_path):
    root = tmp_path
    repo_dir = root / "mql5/Experts/Advisors/XAUUSD"
    mt5_files = tmp_path / "MQL5/Files"
    mt5_experts = tmp_path / "MQL5/Experts/Advisors/XAUUSD"
    repo_dir.mkdir(parents=True)
    mt5_files.mkdir(parents=True)
    ea = repo_dir / "Unified_ObserverOnly_EA.mq5"
    ea.write_text("int OnInit(){return(INIT_SUCCEEDED);}\nvoid OnTick(){int x=1;}\n", encoding="utf-8")
    summary = run(root, mt5_files, mt5_experts, str(ea), True, True, 180, True)
    assert summary["selected_source"].endswith("Unified_ObserverOnly_EA.mq5")
    assert summary["patch_result"]["changed"] is True
    assert Path(summary["mt5_ea_written"]).exists()
    assert "STAGE132_TELEMETRY_BLOCK_BEGIN" in ea.read_text(encoding="utf-8")
    assert Path(summary["mt5_status_kv"]).exists()

def test_collects_fresh_ea_heartbeat(tmp_path):
    root = tmp_path
    mt5_files = tmp_path / "MQL5/Files"
    mt5_experts = tmp_path / "MQL5/Experts"
    mt5_files.mkdir(parents=True)
    mt5_experts.mkdir(parents=True)
    (mt5_files / HEARTBEAT_KV).write_text(
        "stage|Stage132_UNIFIED_OBSERVER_EA_TELEMETRY_WRITER\n"
        "status|UNIFIED_OBSERVER_EA_RUNTIME_ALIVE_NO_ORDER\n"
        "allow_trading|false\n"
        "order_send|false\n"
        "symbol|XAUUSD\n"
        "period|16385\n",
        encoding="utf-8"
    )
    summary = run(root, mt5_files, mt5_experts, None, False, False, 999999, False)
    assert summary["ea_heartbeat_exists"] is True
    assert summary["ea_heartbeat_fresh"] is True
    assert "CONFIRMED" in summary["decision"]
