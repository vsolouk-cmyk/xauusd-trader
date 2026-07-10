from pathlib import Path
import json
import subprocess
import sys


def test_stage171_smoke(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    reports = root / "reports" / "stage170b_data_asof_contract_validation_redesign"
    reports.mkdir(parents=True)
    contract = reports / "stage170b_data_asof_contract.csv"
    contract.write_text(
        "source_id,source_group,historical_asof_status,blocking_issue,owner_action\n"
        "AMARKETS_M5_BROKER_BARS,broker,MEDIUM_HIGH if completed-bar rule is enforced,must lock execution timestamp,codify\n"
        "FRED_MACRO_DAILY_PANEL,macro,LOW until vintage/available_time is added,lookahead risk,add vintage\n"
        "ETF_GLD_WGC_CENTRAL_BANK_GOLD,flow,LOW to MEDIUM until publication lag is explicit,calendar date is not availability date,populate\n",
        encoding="utf-8",
    )
    stage64 = root / "reports" / "stage64r_h64l_test"
    stage64.mkdir(parents=True)
    (stage64 / "h64l_locked_rule_v1.json").write_text('{"rule":"H64L"}', encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "app" / "stage171_h64l_rescue_parallel_track.py"
    out = tmp_path / "out"
    subprocess.check_call([sys.executable, str(script), "--root", str(root), "--output-dir", str(out)])
    summary = json.loads((out / "stage171_h64l_rescue_parallel_track_summary.json").read_text(encoding="utf-8"))
    assert summary["order_routing_allowed"] is False
    assert summary["demo_release_allowed"] is False
    assert summary["parallel_track_policy"]["manual_shadow_starts_day_one"] is True
    assert (out / "stage171_h64l_manual_shadow_checklist.csv").exists()
