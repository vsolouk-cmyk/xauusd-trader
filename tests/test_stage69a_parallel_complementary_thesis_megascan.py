from pathlib import Path
import json
import tempfile
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.stage69a_parallel_complementary_thesis_megascan import run


def test_stage69a_smoke():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "data/macro_regime/normalized").mkdir(parents=True)
        (root / "configs").mkdir()
        dates = pd.bdate_range("2020-01-01", periods=260, tz="UTC")
        rows = []
        price = 100.0
        for i, dt in enumerate(dates):
            price *= 1.001 if i < 180 else 0.999
            rows.append({
                "feature_date_utc": dt.strftime("%Y-%m-%d"),
                "gold_close": price,
                "gold_sma20_over_50": 1.0 if i % 3 != 0 else -1.0,
                "gold_sma50_over_200": 1.0,
                "dxy_ret_20d": -0.01 if i % 4 != 0 else 0.01,
                "dxy_sma20_over_50": -0.01 if i % 5 != 0 else 0.01,
                "real_yield_change_20d": -0.05 if i % 6 != 0 else 0.05,
                "vix_change_20d": 1.0 if i % 7 != 0 else -1.0,
                "etf_flow_tonnes_3m": 10.0,
                "central_bank_demand_tonnes_3m": 5.0,
            })
        pd.DataFrame(rows).to_csv(root / "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv", index=False)
        cfg = {
            "macro_path": "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv",
            "horizons_trading_days": [10, 20],
            "cost_bps_total": 10.0,
            "shortlist_min_entries": 3,
            "shortlist_min_mean_net_return_bps": -999.0,
            "shortlist_min_win_rate": 0.0,
            "shortlist_min_positive_period_share": 0.0,
            "shortlist_max_year_share": 1.0,
        }
        (root / "configs/stage69a_parallel_complementary_thesis_megascan.json").write_text(json.dumps(cfg))
        out = root / "reports/stage69a"
        summary = run(root, root / "configs/stage69a_parallel_complementary_thesis_megascan.json", out)
        assert summary["status"] == "STAGE69A_COMPLETE_NO_PROMOTION"
        assert summary["scan"]["candidate_count"] > 0
        assert (out / "stage69a_parallel_complementary_thesis_megascan_candidates.csv").exists()
        assert (out / "stage69a_parallel_complementary_thesis_megascan_summary.json").exists()


if __name__ == "__main__":
    test_stage69a_smoke()
    print("Stage69A tests passed")
