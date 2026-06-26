from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.stage70c_k06_no_order_shadow_candidate import run


def write_config(root: Path) -> Path:
    cfg_dir = root / "configs"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg = {
        "champion": {
            "thesis_id": "K06_RESILIENT_GOLD_VS_DXY",
            "family": "GOLD_RESILIENCE_AGAINST_DXY",
            "direction": "long",
            "horizon_trading_days": 120,
            "conditions": [
                {"column": "gold_sma20_over_50", "operator": ">", "threshold": 0.0},
                {"column": "dxy_ret_20d", "operator": ">", "threshold": 0.0},
                {"column": "real_yield_change_20d", "operator": "<", "threshold": 0.0}
            ],
            "stage70b_required_disposition": "PROMOTE_TO_NO_ORDER_SHADOW_CANDIDATE"
        },
        "inputs": {
            "macro_dataset": "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv",
            "stage70b_summary": "reports/stage70b_champion_hard_audit/stage70b_champion_hard_audit_summary.json"
        },
        "outputs": {"ledger_csv": "data/forward_shadow/stage70c_k06_no_order_shadow_candidate_ledger.csv"},
        "decision_policy": {
            "inactive_decision": "STAGE70C_K06_SHADOW_WAIT_SIGNAL_NO_ORDER",
            "active_decision": "STAGE70C_K06_SHADOW_SIGNAL_ACTIVE_REVIEW_ONLY_NO_ORDER",
            "data_issue_decision": "STAGE70C_INPUT_OR_DATA_ISSUE_STOP_NO_ORDER"
        },
        "hard_blocks": ["NO_ORDER_AUTHORIZATION_FROM_STAGE70C"],
        "operator_instructions": [],
        "backlog_policy": {"mode": "CONTROLLED_BACKLOG_NON_INTERRUPTIVE"}
    }
    p = cfg_dir / "stage70c_k06_no_order_shadow_candidate.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    return p


def prepare_root(active: bool = True) -> tuple[TemporaryDirectory, Path, Path]:
    td = TemporaryDirectory()
    root = Path(td.name)
    macro_dir = root / "data/macro_regime/normalized"
    macro_dir.mkdir(parents=True, exist_ok=True)
    if active:
        row = {"feature_date_utc": "2026-06-26", "gold_sma20_over_50": 0.1, "dxy_ret_20d": 0.02, "real_yield_change_20d": -0.01, "gold_close": 2400}
    else:
        row = {"feature_date_utc": "2026-06-26", "gold_sma20_over_50": -0.1, "dxy_ret_20d": 0.02, "real_yield_change_20d": 0.01, "gold_close": 2400}
    pd.DataFrame([row]).to_csv(macro_dir / "stage64k_full_scope_lag_safe_feature_dataset.csv", index=False)
    s70b = root / "reports/stage70b_champion_hard_audit"
    s70b.mkdir(parents=True, exist_ok=True)
    (s70b / "stage70b_champion_hard_audit_summary.json").write_text(json.dumps({"disposition": "PROMOTE_TO_NO_ORDER_SHADOW_CANDIDATE"}), encoding="utf-8")
    cfg = write_config(root)
    return td, root, cfg


def test_active_decision():
    td, root, cfg = prepare_root(active=True)
    try:
        out = root / "reports/out"
        summary = run(root, cfg, out)
        assert summary["decision"] == "STAGE70C_K06_SHADOW_SIGNAL_ACTIVE_REVIEW_ONLY_NO_ORDER"
        assert summary["policy_selection"]["policy_signal_active"] is True
        assert summary["policy_selection"]["ticket_generation_allowed_here"] is False
        assert (root / "data/forward_shadow/stage70c_k06_no_order_shadow_candidate_ledger.csv").exists()
    finally:
        td.cleanup()


def test_inactive_decision():
    td, root, cfg = prepare_root(active=False)
    try:
        out = root / "reports/out"
        summary = run(root, cfg, out)
        assert summary["decision"] == "STAGE70C_K06_SHADOW_WAIT_SIGNAL_NO_ORDER"
        assert summary["policy_selection"]["policy_signal_active"] is False
        assert "gold_sma20_over_50" in ";".join(summary["latest_signal_snapshot"]["rule_failures"])
    finally:
        td.cleanup()


if __name__ == "__main__":
    test_active_decision()
    test_inactive_decision()
    print("Stage70C tests passed")
