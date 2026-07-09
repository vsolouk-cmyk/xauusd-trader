from pathlib import Path
import json
import subprocess
import sys


def test_stage170a_smoke(tmp_path: Path):
    root = tmp_path / "repo"
    app = root / "app"
    reports168 = root / "reports" / "stage168_gdelt_reaction_rulespace_rebuild"
    reports169 = root / "reports" / "stage169_event_branch_kill_and_current_guard"
    reports168.mkdir(parents=True)
    reports169.mkdir(parents=True)
    bars = tmp_path / "amarkets_xauusd_5m.csv"
    bars.write_text("<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>\n2026.01.01\t00:00:00\t2000\t2001\t1999\t2000.5\t1\t0\t20\n", encoding="utf-8")
    event_panel = root / "reports" / "stage166_current_event_shock_overlay" / "stage166_current_event_intraday_panel.csv"
    event_panel.parent.mkdir(parents=True)
    event_panel.write_text("time_bucket_utc,event_count,gold_long_pressure,gold_short_pressure,shock_abs\n2026-01-01T00:00:00Z,1,10,0,10\n", encoding="utf-8")
    s168 = reports168 / "stage168_gdelt_reaction_rulespace_summary.json"
    s168.write_text(json.dumps({
        "stage": "Stage168_GDELT_REACTION_RULESPACE_REBUILD",
        "decision": "STAGE168_NO_COMMERCIAL_GDELT_REACTION_CANDIDATE_KILL_OR_REDESIGN_EVENT_THESIS",
        "order_routing_allowed": False,
        "demo_release_allowed": False,
        "evaluation_context": {"score_count": 7500, "shortlist_count": 0, "rule_spec_count": 7500},
        "event_panel_health": {"event_overlay_trainable": True},
        "split_meta": {"holdout_start_utc": "2025-08-13 13:25:00+00:00", "holdout_pct": 0.2}
    }), encoding="utf-8")
    s169 = reports169 / "stage169_event_branch_kill_and_current_guard_summary.json"
    s169.write_text(json.dumps({
        "stage": "Stage169_EVENT_BRANCH_KILL_AND_CURRENT_EVENT_GUARD",
        "decision": "STAGE169_KILL_GDELT_REACTION_ALPHA_KEEP_CURRENT_EVENT_GUARD_ONLY",
        "order_routing_allowed": False,
        "demo_release_allowed": False,
        "current_guard": {"guard_state": "EVENT_GUARD_LOW"},
        "event_meta": {"train_nonzero_shock_hours": 1124}
    }), encoding="utf-8")

    script = Path(__file__).resolve().parents[1] / "app" / "stage170a_methodology_temporal_integrity_audit.py"
    proc = subprocess.run([
        sys.executable, str(script),
        "--root", str(root),
        "--bars-m5", str(bars),
        "--event-panel", str(event_panel),
        "--stage168-summary", str(s168),
        "--stage169-summary", str(s169),
        "--out-dir", str(tmp_path / "out"),
    ], text=True, capture_output=True, check=True)
    out = json.loads(proc.stdout)
    assert out["decision"] == "STAGE170A_METHOD_AUDIT_REQUIRED_BEFORE_NEW_DISCOVERY"
    assert (tmp_path / "out" / "stage170a_methodology_audit_summary.json").exists()
    assert (tmp_path / "out" / "stage170a_decision.md").exists()
