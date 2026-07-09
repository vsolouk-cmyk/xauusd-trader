import json
import subprocess
import sys
from pathlib import Path


def test_stage170b_smoke(tmp_path):
    root = tmp_path
    bars = tmp_path / "bars.tsv"
    bars.write_text("<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>\n2026.01.01\t00:00:00\t2000\t2001\t1999\t2000.5\t1\t0\t20\n", encoding="utf-8")
    event = tmp_path / "event.csv"
    event.write_text("time_bucket_utc,event_count,gold_long_pressure,gold_short_pressure,shock_abs,event_shock_regime\n2026-01-01T00:00:00Z,1,10,0,10,GOLD_LONG_EVENT_PRESSURE\n", encoding="utf-8")

    script = Path(__file__).resolve().parents[1] / "app" / "stage170b_data_asof_contract_validation_redesign.py"
    subprocess.check_call([
        sys.executable,
        str(script),
        "--root", str(root),
        "--bars-m5", str(bars),
        "--event-panel", str(event),
        "--event-inbox", str(tmp_path),
    ])

    summary_path = root / "reports" / "stage170b_data_asof_contract_validation_redesign" / "stage170b_data_asof_contract_summary.json"
    decision_path = root / "reports" / "stage170b_data_asof_contract_validation_redesign" / "stage170b_decision.md"
    contract_path = root / "reports" / "stage170b_data_asof_contract_validation_redesign" / "stage170b_data_asof_contract.csv"
    assert summary_path.exists()
    assert decision_path.exists()
    assert contract_path.exists()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["decision"] == "STAGE170B_DATA_CONTRACT_REQUIRED_BEFORE_NEW_DISCOVERY"
    assert summary["order_routing_allowed"] is False
    assert summary["demo_release_allowed"] is False
    assert summary["inspections"]["bars_m5"]["separator"] == "tab"
