import json
import subprocess
import sys
from pathlib import Path

import pandas as pd


def test_stage169b_handles_tab_separated_amarkets_and_uses_fast_split(tmp_path):
    root = tmp_path / "repo"
    reports = root / "reports" / "stage168_gdelt_reaction_rulespace_rebuild"
    reports.mkdir(parents=True)
    (reports / "stage168_gdelt_reaction_rulespace_summary.json").write_text(json.dumps({
        "decision": "STAGE168_NO_COMMERCIAL_GDELT_REACTION_CANDIDATE_KILL_OR_REDESIGN_EVENT_THESIS",
        "evaluation_context": {"score_count": 7500, "shortlist_count": 0},
        "event_panel_health": {"event_overlay_trainable": True},
        "split_meta": {"holdout_start_utc": "2023-01-02T00:00:00Z"},
    }), encoding="utf-8")

    bars_path = tmp_path / "amarkets_m5.tsv"
    bars_path.write_text(
        "<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>\n"
        "2023.01.01\t03:00:00\t1800\t1801\t1799\t1800.5\t10\t0\t15\n"
        "2023.01.01\t03:05:00\t1800\t1801\t1799\t1800.5\t10\t0\t15\n",
        encoding="utf-8",
    )

    panel = pd.DataFrame({
        "time_bucket_utc": pd.date_range("2023-01-01", periods=100, freq="1h", tz="UTC"),
        "shock_abs": [0]*20 + [10, 20, 30, 40, 50]*16,
        "gold_long_pressure": [0]*20 + [5, 15, 25, 35, 45]*16,
        "gold_short_pressure": [0]*100,
        "event_count": [0]*20 + [1]*80,
        "event_shock_regime": ["NONE"]*20 + ["EVENT"]*80,
    })
    panel_path = tmp_path / "event_panel.csv"
    panel.to_csv(panel_path, index=False)

    script = Path(__file__).resolve().parents[1] / "app" / "stage169_event_branch_kill_and_current_guard.py"
    res = subprocess.run([
        sys.executable, str(script),
        "--root", str(root),
        "--bars-m5", str(bars_path),
        "--event-panel", str(panel_path),
        "--recent-hours", "48",
    ], capture_output=True, text=True, check=True)
    assert "STAGE169_KILL_GDELT_REACTION_ALPHA_KEEP_CURRENT_EVENT_GUARD_ONLY" in res.stdout

    out = root / "reports" / "stage169_event_branch_kill_and_current_guard" / "stage169_event_branch_kill_and_current_guard_summary.json"
    summary = json.loads(out.read_text())
    assert summary["status"] == "STAGE169B_COMPLETE_EVENT_BRANCH_DECISION_READY_FAST_LOADER"
    assert summary["bars_fast_meta"]["bars_loaded_for_split"] is False
    assert summary["bars_fast_meta"]["bars_fast_meta"]["detected_separator"] == "tab"
    assert summary["demo_release_allowed"] is False
    assert summary["order_routing_allowed"] is False
