from pathlib import Path
import json
import tempfile
import subprocess
import sys
import pandas as pd
import numpy as np

def main():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as td:
        r = Path(td)
        (r/"app").mkdir()
        (r/"configs").mkdir()
        (r/"data/macro_regime/normalized").mkdir(parents=True)
        for src in (root/"app").glob("stage77b_*.py"):
            (r/"app"/src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        (r/"configs/stage77b_corrected_portfolio_candidate_selection_historical_asof.json").write_text(
            (root/"configs/stage77b_corrected_portfolio_candidate_selection_historical_asof.json").read_text(encoding="utf-8"),
            encoding="utf-8"
        )

        dates = pd.bdate_range("2011-01-03", "2026-06-26")
        n = len(dates)
        price = 1000 + np.arange(n) * 0.7
        df = pd.DataFrame({
            "feature_date_utc": dates,
            "gold_close": price,
            "gold_sma20_over_50": 0.1,
            "dxy_ret_20d": 0.01,
            "real_yield_change_20d": -0.01,
            "dxy_sma20_over_50": -0.01,
            "vix_change_20d": 0.01,
            "central_bank_demand_tonnes_3m": 1.0,
            "etf_flow_tonnes_3m": 1.0,
        })
        df.to_csv(r/"data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv", index=False)

        subprocess.check_call([
            sys.executable,
            str(r/"app/stage77b_corrected_portfolio_candidate_selection_historical_asof.py"),
            "--root", str(r),
            "--config", "configs/stage77b_corrected_portfolio_candidate_selection_historical_asof.json",
            "--out", "reports/stage77b"
        ])
        s = json.loads((r/"reports/stage77b/stage77b_corrected_portfolio_candidate_selection_historical_asof_summary.json").read_text())
        assert s["status"] == "STAGE77B_COMPLETE_NO_PROMOTION"
        assert s["candidate_count"] == 9
        assert "K06_RESILIENT_GOLD_VS_DXY_H120" in s["selected_rule_ids"]
        cm = pd.read_csv(r/"reports/stage77b/stage77b_candidate_metrics.csv")
        k06 = cm[cm.rule_id == "K06_RESILIENT_GOLD_VS_DXY_H120"].iloc[0]
        assert int(k06["missing_required_feature_rows"]) == 0
    print("Stage77B tests passed")

if __name__ == "__main__":
    main()
