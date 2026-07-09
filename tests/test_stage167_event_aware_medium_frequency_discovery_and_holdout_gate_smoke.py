from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("stage167", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_stage167_smoke(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    app_path = Path(__file__).resolve().parents[1] / "app" / "stage167_event_aware_medium_frequency_discovery_and_holdout_gate.py"
    mod = load_module(app_path)

    n = 2500
    ts = pd.date_range("2025-01-01", periods=n, freq="5min", tz="UTC")
    price = 2300.0
    rows = []
    for i, t in enumerate(ts):
        drift = 0.015 if (i % 60 < 25) else -0.005
        price += drift
        rows.append({
            "time_utc": t.isoformat(),
            "open": price - 0.03,
            "high": price + 0.08,
            "low": price - 0.08,
            "close": price,
            "volume": 100 + i % 10,
            "spread": 25,
        })
    bars_path = tmp_path / "bars.csv"
    pd.DataFrame(rows).to_csv(bars_path, index=False)

    event_dir = root / "reports" / "stage166_current_event_shock_overlay"
    event_dir.mkdir(parents=True)
    events = pd.DataFrame({
        "time_utc": ts[::12].astype(str),
        "gold_long_pressure": [5.0 if i % 5 in (0, 1, 2) else 0.0 for i in range(len(ts[::12]))],
        "gold_short_pressure": [0.0 for _ in range(len(ts[::12]))],
        "shock_abs": [5.0 if i % 5 in (0, 1, 2) else 0.0 for i in range(len(ts[::12]))],
        "event_side_bias": ["LONG" if i % 5 in (0, 1, 2) else "NONE" for i in range(len(ts[::12]))],
        "event_shock_regime": ["EVENT_SAFE_HAVEN_LONG_PRESSURE" if i % 5 in (0, 1, 2) else "EVENT_NEUTRAL" for i in range(len(ts[::12]))],
        "event_count": [1 for _ in range(len(ts[::12]))],
    })
    events.to_csv(event_dir / "stage166_current_event_intraday_panel.csv", index=False)

    args = SimpleNamespace(
        root=str(root),
        bars_m5=str(bars_path),
        event_panel="",
        timestamp_shift_hours=0.0,
        holdout_pct=0.20,
        cost_bps=0.5,
        spread_point_size=0.01,
        min_train_events=5,
        min_holdout_events=2,
        min_train_mean_bps=-999.0,
        min_holdout_mean_bps=-999.0,
        min_train_hit_rate=0.0,
        min_holdout_hit_rate=0.0,
        min_holdout_p10_bps=-999.0,
        max_event_dependency_ratio=1.0,
        max_top_trade_exports=5,
    )
    summary = mod.run(args)
    assert summary["status"] == "STAGE167_COMPLETE_EVENT_AWARE_HOLDOUT_GATE_READY"
    assert Path(summary["outputs"]["summary_json"]).exists()
    assert Path(summary["outputs"]["all_rule_scores_csv"]).exists()
    assert Path(summary["outputs"]["holdout_map_json"]).exists()
    loaded = json.loads(Path(summary["outputs"]["summary_json"]).read_text())
    assert loaded["evaluation_context"]["score_count"] > 0
