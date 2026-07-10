import json
import subprocess
import sys
from pathlib import Path


def test_stage171b_smoke(tmp_path: Path):
    root = tmp_path / "repo"
    (root / "data/macro_regime/normalized").mkdir(parents=True)
    (root / "reports/stage171_h64l_rescue_parallel_track").mkdir(parents=True)
    (root / "reports/stage170b_data_asof_contract_validation_redesign").mkdir(parents=True)
    (root / "data/macro_regime/normalized/stage64r_h64l_locked_rule.md").write_text(
        "H64L macro_tailwind gold_sma20 dxy_ret_20d real_yield_change_20d etf_flow z=4.9",
        encoding="utf-8",
    )
    triage = root / "reports/stage171_h64l_rescue_parallel_track/stage171_h64l_feature_blocker_triage.csv"
    triage.write_text(
        "feature,contract_source,status,verdict,risk\n"
        "dxy_ret_20d,FRED_MACRO_DAILY_PANEL,LOW,H64L_FEATURE_BLOCKED_OR_NEEDS_MECHANICAL_ASOF_FIX,availability\n",
        encoding="utf-8",
    )
    summary = root / "reports/stage171_h64l_rescue_parallel_track/stage171_h64l_rescue_parallel_track_summary.json"
    summary.write_text(json.dumps({"decision":"STAGE171_H64L_PARALLEL_TRACK_WITH_TARGETED_ASOF_FIXES_REQUIRED","h64l_clues":{"exact_rule_locked":False}}), encoding="utf-8")
    contract = root / "reports/stage170b_data_asof_contract_validation_redesign/stage170b_data_asof_contract.csv"
    contract.write_text("source_id,historical_asof_status,blocking_issue\nFRED_MACRO_DAILY_PANEL,LOW,lookahead\n", encoding="utf-8")

    script = Path(__file__).resolve().parents[1] / "app" / "stage171b_h64l_exact_rule_extraction_and_shadow_start.py"
    result = subprocess.run([
        sys.executable, str(script),
        "--root", str(root),
        "--stage171-summary", str(summary),
        "--stage171-triage", str(triage),
        "--data-asof-contract", str(contract),
    ], text=True, capture_output=True, check=True)
    assert "Stage171B_H64L_EXACT_RULE_EXTRACTION" in result.stdout
    out = root / "reports/stage171b_h64l_exact_rule_extraction_and_shadow_start"
    assert (out / "stage171b_h64l_exact_rule_extraction_summary.json").exists()
    assert (out / "stage171b_h64l_manual_shadow_log_template.csv").exists()
