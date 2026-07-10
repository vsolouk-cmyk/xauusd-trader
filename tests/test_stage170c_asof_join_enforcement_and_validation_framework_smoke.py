import json
import subprocess
import sys
from pathlib import Path


def test_stage170c_smoke(tmp_path):
    root = tmp_path
    bars = tmp_path / "bars.tsv"
    bars.write_text("<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>\n" + "\n".join([
        f"2022.01.{(i%28)+1:02d}\t{(i%24):02d}:00:00\t2000\t2001\t1999\t2000.5\t1\t0\t20" for i in range(900)
    ]), encoding="utf-8")
    event = tmp_path / "event.csv"
    event.write_text("time_bucket_utc,event_count,gold_long_pressure,gold_short_pressure,shock_abs,event_shock_regime\n2022-01-01T00:00:00Z,1,10,0,10,GOLD_LONG_EVENT_PRESSURE\n", encoding="utf-8")
    contract = tmp_path / "contract.csv"
    contract.write_text("source_id,historical_asof_status,observed_time_field,available_time_field,embargo_policy,blocking_issue,required_test\nFRED_MACRO_DAILY_PANEL,LOW,observation_date,MISSING_OR_ASSUMED,no same-day macro,latest revised values can leak,fred_vintage_test\nAMARKETS_M5_BROKER_BARS,MEDIUM_HIGH,<DATE>+<TIME>,bar_close_time_utc,no same bar,must enforce completed bar,bar_test\n", encoding="utf-8")
    stage170b = tmp_path / "stage170b.json"
    stage170b.write_text(json.dumps({"decision":"STAGE170B_DATA_CONTRACT_REQUIRED_BEFORE_NEW_DISCOVERY","methodology_gate":{"new_discovery_allowed":False}}), encoding="utf-8")

    script = Path(__file__).resolve().parents[1] / "app" / "stage170c_asof_join_enforcement_and_validation_framework.py"
    subprocess.check_call([
        sys.executable, str(script),
        "--root", str(root),
        "--bars-m5", str(bars),
        "--event-panel", str(event),
        "--stage170b-summary", str(stage170b),
        "--data-asof-contract", str(contract),
    ])

    out = root / "reports" / "stage170c_asof_join_enforcement_and_validation_framework"
    summary = json.loads((out / "stage170c_asof_enforcement_summary.json").read_text(encoding="utf-8"))
    assert summary["order_routing_allowed"] is False
    assert summary["demo_release_allowed"] is False
    assert summary["decision"] == "STAGE170C_ASOF_ENFORCEMENT_BLOCKS_NEW_DISCOVERY"
    assert summary["contract_enforcement"]["blocking_new_discovery_rows"] >= 1
    assert (out / "stage170c_data_contract_enforcement_report.csv").exists()
    assert (out / "stage170c_purged_walk_forward_folds.csv").exists()
