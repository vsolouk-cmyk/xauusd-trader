import csv
import json
import subprocess
import sys
from pathlib import Path


def test_stage171d_smoke(tmp_path: Path):
    root = tmp_path
    app_dir = root / "app"
    app_dir.mkdir()
    src = Path(__file__).resolve().parents[1] / "app" / "stage171d_h64l_shadow_scheduler_and_logger.py"
    dst = app_dir / src.name
    dst.write_text(src.read_text(), encoding="utf-8")

    data_dir = root / "data" / "macro_regime" / "normalized"
    data_dir.mkdir(parents=True)
    dataset = data_dir / "stage64k_full_scope_lag_safe_feature_dataset.csv"
    with dataset.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "feature_date_utc",
                "sample_available_after_utc",
                "gold_sma20_over_50",
                "dxy_ret_20d",
                "real_yield_change_20d",
                "etf_flow_tonnes_3m",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "feature_date_utc": "2026-07-09",
                "sample_available_after_utc": "2026-07-10T00:00:00Z",
                "gold_sma20_over_50": "1.0",
                "dxy_ret_20d": "-0.01",
                "real_yield_change_20d": "-0.02",
                "etf_flow_tonnes_3m": "5.0",
            }
        )

    rule_dir = root / "reports" / "stage171b_h64l_exact_rule_extraction_and_shadow_start"
    rule_dir.mkdir(parents=True)
    (rule_dir / "stage171b_h64l_locked_rule_candidate.json").write_text(
        json.dumps({"rule_id": "H64L_TEST", "exact_rule_locked": False, "confidence": "TEST"}),
        encoding="utf-8",
    )

    subprocess.run([sys.executable, str(dst), "run-once", "--root", str(root)], check=True)

    summary = root / "reports" / "stage171d_h64l_shadow_scheduler_and_logger" / "stage171d_h64l_shadow_scheduler_summary.json"
    assert summary.exists()
    obj = json.loads(summary.read_text())
    assert obj["order_routing_allowed"] is False
    assert obj["demo_release_allowed"] is False
    assert obj["current_shadow"]["h64l_shadow_signal"] == "YES"
    assert (root / "data" / "forward_shadow" / "h64l_manual_shadow_log.csv").exists()

    plist = tmp_path / "test.plist"
    subprocess.run([
        sys.executable,
        str(dst),
        "write-launchd-plist",
        "--root",
        str(root),
        "--plist-path",
        str(plist),
        "--hour",
        "9",
        "--minute",
        "15",
    ], check=True)
    assert plist.exists()
