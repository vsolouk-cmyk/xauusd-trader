from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.stage71_locked_historical_forward_test import run


def test_stage71_locked_historical_forward(tmp_path: Path) -> None:
    data_dir = tmp_path / "data/macro_regime/normalized"
    data_dir.mkdir(parents=True)
    dates = pd.bdate_range("2011-01-03", periods=4200)
    price = []
    p = 1000.0
    for i, _ in enumerate(dates):
        p *= 1.0007 if (i // 120) % 2 == 0 else 0.9998
        price.append(p)
    df = pd.DataFrame({
        "feature_date_utc": dates.strftime("%Y-%m-%d"),
        "gold_close": price,
        "gold_sma20_over_50": [0.1 if (i // 140) % 2 == 0 else -0.1 for i in range(len(dates))],
        "gold_sma50_over_200": [0.1 for _ in dates],
        "dxy_ret_20d": [0.02 for _ in dates],
        "dxy_sma20_over_50": [-0.01 for _ in dates],
        "real_yield_change_20d": [-0.02 if (i // 140) % 2 == 0 else 0.02 for i in range(len(dates))],
        "dxy": [100.0 for _ in dates],
        "real_yield": [1.0 for _ in dates],
        "vix": [20.0 for _ in dates],
        "etf_flow_tonnes_3m": [1.0 for _ in dates],
        "central_bank_demand_tonnes_3m": [1.0 for _ in dates],
    })
    df.to_csv(data_dir / "stage64k_full_scope_lag_safe_feature_dataset.csv", index=False)

    cfg = json.loads((ROOT / "configs/stage71_locked_historical_forward_test.json").read_text())
    cfg_path = tmp_path / "configs/stage71_locked_historical_forward_test.json"
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text(json.dumps(cfg))
    out = tmp_path / "reports/stage71"
    summary = run(tmp_path, cfg_path, out)
    assert summary["status"] == "STAGE71_COMPLETE_NO_PROMOTION"
    assert Path(summary["outputs"]["summary_json"]).exists()
    assert Path(summary["outputs"]["split_metrics_csv"]).exists()
    assert Path(summary["outputs"]["temporal_compatibility_csv"]).exists()
    assert summary["champion"]["thesis_id"] == "K06_RESILIENT_GOLD_VS_DXY"
    assert summary["macro_dataset"]["rows_used"] > 3000


if __name__ == "__main__":
    test_stage71_locked_historical_forward(Path("/tmp/stage71_test"))
    print("Stage71 tests passed")
