from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.stage72_historical_daily_replay import run, DEFAULT_CONFIG


def write_macro(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "feature_date_utc", "gold_close", "gold_sma20_over_50", "dxy_ret_20d", "real_yield_change_20d",
        "dxy", "real_yield", "vix", "etf_flow_tonnes_3m", "central_bank_demand_tonnes_3m",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        # 320 pseudo trading rows, enough for two 20-day horizons in test config.
        for i in range(320):
            year = 2020 + i // 250
            day = (i % 250) + 1
            date = f"{year}-01-{1 + (day % 28):02d}" if i < 28 else f"{year}-{1 + ((i // 28) % 12):02d}-{1 + (day % 28):02d}"
            active_block = 10 <= i < 35 or 80 <= i < 105 or 170 <= i < 195 or 250 <= i < 275
            w.writerow({
                "feature_date_utc": date,
                "gold_close": 1000 + i * 2,
                "gold_sma20_over_50": 1.0 if active_block else -1.0,
                "dxy_ret_20d": 0.01 if active_block else -0.01,
                "real_yield_change_20d": -0.01 if active_block else 0.01,
                "dxy": 100,
                "real_yield": 1,
                "vix": 20,
                "etf_flow_tonnes_3m": 1,
                "central_bank_demand_tonnes_3m": 1,
            })


def test_stage72_runs_and_writes_outputs() -> None:
    with TemporaryDirectory() as td:
        root = Path(td)
        macro = root / "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv"
        write_macro(macro)
        cfg = json.loads(json.dumps(DEFAULT_CONFIG))
        cfg["replay_start"] = "2020-01-01"
        cfg["locked_final_holdout_start"] = "2020-01-01"
        cfg["rule"]["horizon_trading_days"] = 20
        cfg["rule"]["entry_cooldown_trading_days"] = 20
        cfg["decision_constraints"]["min_replay_rows"] = 100
        cfg["decision_constraints"]["min_matured_events"] = 2
        cfg["decision_constraints"]["min_final_holdout_matured_events"] = 2
        cfg["decision_constraints"]["min_mean_net_return_bps"] = -1000
        cfg["decision_constraints"]["min_win_rate"] = 0.0
        cfg["decision_constraints"]["min_final_holdout_mean_net_bps"] = -1000
        out = root / "reports/stage72"
        summary = run(root, cfg, out)
        assert summary["status"] == "STAGE72_COMPLETE_NO_PROMOTION"
        assert summary["historical_daily_replay"]["replay_rows"] >= 100
        assert (out / "stage72_historical_daily_replay_summary.json").exists()
        assert (out / "stage72_k06_historical_daily_ledger.csv").exists()
        assert (out / "stage72_k06_activation_events.csv").exists()
        assert (out / "stage72_k06_matured_outcomes.csv").exists()


if __name__ == "__main__":
    test_stage72_runs_and_writes_outputs()
    print("Stage72 tests passed")
