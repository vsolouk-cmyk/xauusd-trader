import json
import subprocess
import sys
from pathlib import Path


def test_stage171e_smoke(tmp_path):
    root = tmp_path / "repo"
    cfg = root / "archive/_local_archive_final_cleanup/configs_inactive"
    cfg.mkdir(parents=True)
    (cfg / "h64l_locked_rule_v2_stage66a3_exact_reconciled.json").write_text(json.dumps({
        "rule_id": "H64L_H1_FULL_MACRO_TAILWIND_LONG",
        "conditions": [
            "gold_sma20_over_50 > 0",
            "dxy_ret_20d < 0",
            "real_yield_change_20d < 0",
            "etf_flow_tonnes_3m > 0",
        ]
    }), encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "app" / "stage171e_h64l_exact_rule_lock_from_archive.py"
    out = subprocess.check_output([sys.executable, str(script), "--root", str(root)], text=True)
    payload = json.loads(out)
    assert payload["exact_rule_locked"] is True
    summary = root / "reports/stage171e_h64l_exact_rule_lock_from_archive/stage171e_h64l_exact_rule_lock_summary.json"
    assert summary.exists()
