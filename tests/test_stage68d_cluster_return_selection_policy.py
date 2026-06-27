#!/usr/bin/env python3
import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "app" / "stage68d_cluster_return_selection_policy.py"
CONFIG = Path(__file__).resolve().parents[1] / "configs" / "stage68d_cluster_return_selection_policy.json"


def write_sample(root: Path):
    p = root / "reports/stage68c_return_incremental_value_audit"
    p.mkdir(parents=True, exist_ok=True)
    f = p / "stage68c_rule_entry_returns.csv"
    cols = ["rule_key","label","type","horizon_trading_days","entry_index","exit_index","entry_date","exit_date","entry_price","exit_price","gross_return_bps","net_return_bps","cost_bps_total","same_day_other_rules","is_same_day_unique"]
    rows = [
        ["h64l_v2","H64L","primary",120,0,10,"2020-01-01","2020-06-01",100,110,1000,950,50,"",True],
        ["d1_backup","D1","backup",60,0,10,"2020-01-01","2020-04-01",100,105,500,450,50,"",False],
        ["d3_h60","D3","comp",60,0,10,"2020-04-15","2020-07-15",100,103,300,250,50,"",True],
        ["d4_backup","D4","backup",60,0,10,"2020-10-01","2021-01-01",100,101,100,50,50,"",True],
        ["d3_h60","D3","comp",60,0,10,"2021-02-01","2021-05-01",100,98,-200,-250,50,"",True],
    ]
    with f.open("w", newline="", encoding="utf-8") as out:
        w = csv.writer(out)
        w.writerow(cols)
        w.writerows(rows)


def main():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        write_sample(root)
        out = root / "reports/stage68d_cluster_return_selection_policy"
        res = subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), "--config", str(CONFIG), "--out", str(out)], text=True, capture_output=True)
        assert res.returncode == 0, res.stderr + res.stdout
        summary = json.loads((out / "stage68d_cluster_return_selection_policy_summary.json").read_text())
        assert summary["status"] == "STAGE68D_COMPLETE_NO_PROMOTION"
        assert summary["input_entries"]["raw_rule_entry_count"] == 5
        assert (out / "stage68d_policy_comparison.csv").exists()
        assert (out / "stage68d_selected_cluster_entries.csv").exists()
    print("Stage68D tests passed")

if __name__ == "__main__":
    main()
