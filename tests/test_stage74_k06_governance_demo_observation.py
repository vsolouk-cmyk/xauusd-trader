from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def make_root(tmp_path: Path, active: bool) -> Path:
    root = tmp_path
    macro_dir = root / "data/macro_regime/normalized"
    macro_dir.mkdir(parents=True, exist_ok=True)
    if active:
        gold_trend, dxy_ret, real_yield_change = 0.03, 0.02, -0.05
    else:
        gold_trend, dxy_ret, real_yield_change = -0.03, 0.02, 0.05
    df = pd.DataFrame(
        [
            {
                "feature_date_utc": "2026-06-25",
                "gold_close": 3300.0,
                "gold_sma20_over_50": 0.01,
                "dxy_ret_20d": 0.01,
                "real_yield_change_20d": -0.01,
            },
            {
                "feature_date_utc": "2026-06-26",
                "gold_close": 3310.0,
                "gold_sma20_over_50": gold_trend,
                "dxy_ret_20d": dxy_ret,
                "real_yield_change_20d": real_yield_change,
            },
        ]
    )
    df.to_csv(macro_dir / "stage64k_full_scope_lag_safe_feature_dataset.csv", index=False)
    locks = [
        ("reports/stage70b_champion_hard_audit/stage70b_champion_hard_audit_summary.json", "PROMOTE_TO_NO_ORDER_SHADOW_CANDIDATE"),
        ("reports/stage71_locked_historical_forward_test/stage71_locked_historical_forward_test_summary.json", "K06_PASSES_LOCKED_HISTORICAL_FORWARD"),
        ("reports/stage72_historical_daily_replay/stage72_historical_daily_replay_summary.json", "K06_PASSES_HISTORICAL_DAILY_REPLAY"),
        ("reports/stage73b_corrected_asof_validation_bridge/stage73b_corrected_asof_validation_bridge_summary.json", "K06_PASSES_CORRECTED_ASOF_VALIDATION"),
    ]
    for rel, disp in locks:
        payload = {"disposition": disp}
        if "stage71" in rel:
            payload["overall_metrics"] = {"mean_net_return_bps": 517.0, "win_rate": 0.82}
        if "stage72" in rel:
            payload["matured_outcome_metrics"] = {"mean_net_return_bps": 952.0, "win_rate": 0.91}
            payload["final_holdout_matured_outcome_metrics"] = {"mean_net_return_bps": 1283.0}
        if "stage73b" in rel:
            payload["asof_metrics"] = {"pre_asof_known_matured_calibration": {"mean_net_return_bps": 260.0, "win_rate": 0.78, "entry_rate_per_252d": 1.34}}
        write_json(root / rel, payload)
    cfg = {
        "macro_path": "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv",
        "current_date_utc": "2026-06-27",
        "max_stale_calendar_days": 7,
    }
    write_json(root / "configs/stage74_k06_governance_demo_observation.json", cfg)
    return root


def run_stage(root: Path) -> dict:
    script = Path(__file__).resolve().parents[1] / "app/stage74_k06_governance_demo_observation.py"
    out = root / "reports/stage74_k06_governance_demo_observation"
    subprocess.run(
        [sys.executable, str(script), "--root", str(root), "--config", "configs/stage74_k06_governance_demo_observation.json", "--out", str(out)],
        check=True,
        cwd=root,
    )
    return json.loads((out / "stage74_k06_governance_demo_observation_summary.json").read_text(encoding="utf-8"))


def test_wait_signal_when_inactive(tmp_path: Path) -> None:
    root = make_root(tmp_path, active=False)
    summary = run_stage(root)
    assert summary["decision"] == "STAGE74_K06_GOVERNANCE_READY_WAIT_SIGNAL_NO_ORDER"
    assert summary["latest_signal_snapshot"]["signal_active"] is False
    assert summary["issues"] == []
    assert Path(summary["outputs"]["ledger_csv"]).exists()


def test_activation_packet_when_active(tmp_path: Path) -> None:
    root = make_root(tmp_path, active=True)
    summary = run_stage(root)
    assert summary["decision"] == "STAGE74_K06_REVIEW_ONLY_ACTIVATION_PACKET_READY_NO_ORDER"
    assert summary["latest_signal_snapshot"]["signal_active"] is True
    assert summary["outputs"]["activation_packet_json"]
    assert Path(summary["outputs"]["activation_packet_json"]).exists()
    packet = json.loads(Path(summary["outputs"]["activation_packet_json"]).read_text(encoding="utf-8"))
    assert packet["packet_type"] == "REVIEW_ONLY_ACTIVATION_PACKET_NO_ORDER"
    assert "NO_ORDER_AUTHORIZATION_FROM_STAGE74" in packet["hard_blocks"]


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        test_wait_signal_when_inactive(p / "inactive")
        test_activation_packet_when_active(p / "active")
    print("Stage74 tests passed")
