from pathlib import Path
import json
import tempfile
import pandas as pd
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.stage70_known_thesis_convergence_runner import main


def test_stage70_runner_smoke():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        data_dir = root / "data/macro_regime/normalized"
        data_dir.mkdir(parents=True)
        n = 360
        dates = pd.bdate_range("2020-01-01", periods=n)
        price = [1500 + i * 2 for i in range(n)]
        df = pd.DataFrame({
            "feature_date_utc": dates.strftime("%Y-%m-%d"),
            "gold_close": price,
            "gold_sma20_over_50": [0.1] * n,
            "gold_sma50_over_200": [0.1] * n,
            "dxy_ret_20d": [-0.01 if i % 80 < 40 else 0.01 for i in range(n)],
            "dxy_sma20_over_50": [-0.01 if i % 90 < 45 else 0.01 for i in range(n)],
            "real_yield_change_20d": [-0.05 if i % 70 < 35 else 0.05 for i in range(n)],
            "vix_change_20d": [1.0 if i % 60 < 30 else -1.0 for i in range(n)],
            "etf_flow_tonnes_3m": [10.0] * n,
            "central_bank_demand_tonnes_3m": [5.0] * n,
        })
        macro = data_dir / "stage64k_full_scope_lag_safe_feature_dataset.csv"
        df.to_csv(macro, index=False)
        cfg_dir = root / "configs"
        cfg_dir.mkdir()
        cfg = cfg_dir / "stage70_known_thesis_convergence_runner.json"
        cfg.write_text(json.dumps({
            "macro_path": "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv",
            "min_entries": 1,
            "min_mean_net_return_bps": -9999,
            "min_win_rate": 0.0,
            "min_positive_period_share": 0.0,
            "max_year_entry_share": 1.0
        }))
        rc = main(["--root", str(root), "--config", str(cfg), "--out", "reports/stage70"])
        assert rc == 0
        summary = json.loads((root / "reports/stage70/stage70_known_thesis_convergence_runner_summary.json").read_text())
        assert summary["status"] == "STAGE70_COMPLETE_NO_PROMOTION"
        assert "locked_scope" in summary
        assert (root / "reports/stage70/stage70_known_thesis_catalog.csv").exists()
        assert (root / "reports/stage70/stage70_known_vs_old_thesis_scan_results.csv").exists()

if __name__ == "__main__":
    test_stage70_runner_smoke()
    print("Stage70 tests passed")
