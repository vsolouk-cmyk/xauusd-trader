import csv
import json
import subprocess
import sys
from pathlib import Path


def test_stage171d2_reads_stage171e_exact_lock_metadata(tmp_path: Path):
    root = tmp_path
    app_dir = root / "app"
    app_dir.mkdir()
    src = Path(__file__).resolve().parents[1] / "app" / "stage171d_h64l_shadow_scheduler_and_logger.py"
    dst = app_dir / "stage171d_h64l_shadow_scheduler_and_logger.py"
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    data_dir = root / "data/macro_regime/normalized"
    data_dir.mkdir(parents=True)
    dataset = data_dir / "stage64k_full_scope_lag_safe_feature_dataset.csv"
    dataset.write_text(
        "feature_date_utc,sample_available_after_utc,gold_sma20_over_50,dxy_ret_20d,real_yield_change_20d,etf_flow_tonnes_3m\n"
        "2026-06-26,2026-06-26T23:59:59Z,-0.05,0.01,0.16,123.4\n",
        encoding="utf-8",
    )

    rule_dir = root / "reports/stage171e_h64l_exact_rule_lock_from_archive"
    rule_dir.mkdir(parents=True)
    rule = rule_dir / "stage171e_h64l_exact_locked_rule.json"
    rule.write_text(json.dumps({
        "selected_evidence_path": "archive/_local_archive_final_cleanup/configs_inactive/h64l_locked_rule_v2_stage66a3_exact_reconciled.json",
        "selected_evidence_strength": "AUTHORITATIVE_LOCKED_RULE_V2_NAME",
        "exact_rule_locked": True,
        "exact_rule_lock_confidence": "HIGH_FROM_ARCHIVED_LOCKED_RULE",
        "conditions": [],
    }), encoding="utf-8")

    ledger = root / "data/forward_shadow/h64l_manual_shadow_log.csv"
    cmd = [
        sys.executable, str(dst), "run-once",
        "--root", str(root),
        "--macro-dataset", str(dataset),
        "--locked-rule-candidate", str(rule),
        "--ledger-csv", str(ledger),
        "--operator-note", "smoke",
    ]
    subprocess.run(cmd, check=True, cwd=str(root), capture_output=True, text=True)
    rows = list(csv.DictReader(ledger.open(encoding="utf-8")))
    assert rows
    row = rows[-1]
    assert row["exact_rule_locked"] == "True"
    assert row["rule_id"] == "H64L_EXACT_LOCKED_RULE_V2_STAGE66A3"
    assert row["rule_confidence"] == "HIGH_FROM_ARCHIVED_LOCKED_RULE"
    assert row["h64l_shadow_signal"] == "NO"

    summary = json.loads((root / "reports/stage171d_h64l_shadow_scheduler_and_logger/stage171d_h64l_shadow_scheduler_summary.json").read_text(encoding="utf-8"))
    assert summary["rule_candidate"]["selected_evidence_strength"] == "AUTHORITATIVE_LOCKED_RULE_V2_NAME"
