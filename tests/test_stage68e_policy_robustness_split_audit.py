#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def test_stage68e_smoke() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "app").mkdir()
        (root / "configs").mkdir()
        reports = root / "reports" / "stage68d_cluster_return_selection_policy"
        reports.mkdir(parents=True)
        csv_path = reports / "stage68d_selected_cluster_entries.csv"
        csv_path.write_text(
            "policy_id,cluster_id,cluster_start,cluster_end,cluster_entry_count,cluster_rules,selected_rule,selected_entry_date,selected_exit_date,selected_net_return_bps\n"
            "QUALITY_FIRST_EXCLUDE_D1,1,2011-01-01,2011-01-05,1,h64l,h64l_v2,2011-01-01,2011-04-01,100\n"
            "QUALITY_FIRST_EXCLUDE_D1,2,2015-01-01,2015-01-05,1,d3,d3_h60,2015-01-01,2015-04-01,-50\n"
            "QUALITY_FIRST_EXCLUDE_D1,3,2019-01-01,2019-01-05,1,d4,d4_backup,2019-01-01,2019-04-01,200\n"
            "QUALITY_FIRST_EXCLUDE_D1,4,2023-01-01,2023-01-05,1,h64l,h64l_v2,2023-01-01,2023-04-01,300\n"
            "D1_REFERENCE_ONLY,1,2011-01-01,2011-01-05,1,d1,d1_backup,2011-01-01,2011-04-01,80\n"
            "D1_REFERENCE_ONLY,2,2015-01-01,2015-01-05,1,d1,d1_backup,2015-01-01,2015-04-01,60\n"
            "D1_REFERENCE_ONLY,3,2019-01-01,2019-01-05,1,d1,d1_backup,2019-01-01,2019-04-01,70\n"
            "D1_REFERENCE_ONLY,4,2023-01-01,2023-01-05,1,d1,d1_backup,2023-01-01,2023-04-01,90\n",
            encoding="utf-8",
        )
        cfg = root / "configs" / "stage68e_policy_robustness_split_audit.json"
        cfg.write_text(json.dumps({
            "selected_cluster_entries_csv": "reports/stage68d_cluster_return_selection_policy/stage68d_selected_cluster_entries.csv",
            "candidate_policy": "QUALITY_FIRST_EXCLUDE_D1",
            "constraints": {
                "min_entry_count": 1,
                "min_mean_net_return_bps": 1,
                "min_win_rate": 0.1,
                "min_positive_period_share": 0.5,
                "min_positive_year_share": 0.5,
                "max_abs_worst_3_entry_sum_bps": 1000,
                "max_recent_period_share_of_total_return": 1.0
            }
        }), encoding="utf-8")
        script = Path(__file__).resolve().parents[1] / "app" / "stage68e_policy_robustness_split_audit.py"
        out = root / "reports" / "stage68e_policy_robustness_split_audit"
        res = subprocess.run([sys.executable, str(script), "--root", str(root), "--config", str(cfg), "--out", str(out)], capture_output=True, text=True)
        assert res.returncode == 0, res.stderr + res.stdout
        summary = json.loads((out / "stage68e_policy_robustness_split_audit_summary.json").read_text(encoding="utf-8"))
        assert summary["status"] == "STAGE68E_COMPLETE_NO_PROMOTION"
        assert (out / "stage68e_policy_period_metrics.csv").exists()


if __name__ == "__main__":
    test_stage68e_smoke()
    print("Stage68E tests passed")
