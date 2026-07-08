import json
from pathlib import Path

import pandas as pd

from app.stage158_trade_attribution_audit import load_m5_bars, main


def test_amarkets_tab_loader_without_header(tmp_path: Path):
    bars = tmp_path / "amarkets_xauusd_5m.csv"
    bars.write_text(
        "2026.07.07\t21:30:00\t4141.47\t4141.57\t4136.03\t4138.67\t424\t0\t37\n"
        "2026.07.07\t21:35:00\t4138.67\t4145.00\t4137.00\t4144.00\t425\t0\t38\n",
        encoding="utf-8",
    )
    df, info = load_m5_bars(bars, -3)
    assert info["bar_count"] == 2
    assert info["detected_separator"] == "tab"
    assert str(df["utc_time"].iloc[0]) == "2026-07-07 18:30:00"
    assert float(df["close"].iloc[-1]) == 4144.0


def test_stage158b_writes_mfe_mae_outputs(tmp_path: Path):
    root = tmp_path
    bars = tmp_path / "bars.csv"
    bars.write_text(
        "2026.07.07\t21:30:00\t100.0\t101.0\t99.0\t100.5\t1\t0\t10\n"
        "2026.07.07\t21:35:00\t100.5\t103.0\t100.0\t102.0\t1\t0\t10\n"
        "2026.07.07\t21:40:00\t102.0\t102.5\t98.0\t99.0\t1\t0\t10\n",
        encoding="utf-8",
    )
    ledger = tmp_path / "ledger.csv"
    pd.DataFrame([
        {
            "audit_order": 1,
            "signal_key": "2026-07-07T18:30:00Z|R_GEQ35",
            "rule_id": "R_GEQ35",
            "feature_date": "2026-07-07T18:30:00Z",
            "entry_time": "2026-07-07T21:31:00Z",
            "exit_time": "2026-07-07T21:40:00Z",
            "entry_price": 100.0,
            "exit_price": 99.0,
            "net_profit": -1.0,
            "bps_move": -100.0,
            "outcome": "LOSS",
        }
    ]).to_csv(ledger, index=False)
    scores = tmp_path / "scores.csv"
    pd.DataFrame([{"rule_id": "R_GEQ35", "validation_mean_bps": 2.5, "tail_mean_bps": 1.5}]).to_csv(scores, index=False)
    risk = tmp_path / "risk.json"
    risk.write_text(json.dumps({"gate_decision": "FREEZE", "recommended_action": "REPAIR"}), encoding="utf-8")
    out_dir = tmp_path / "out"
    rc = main([
        "--root", str(root),
        "--clean-ledger", str(ledger),
        "--score-csv", str(scores),
        "--risk-summary", str(risk),
        "--bars-m5", str(bars),
        "--timestamp-shift-hours", "-3",
        "--entry-time-shift-hours", "-3",
        "--output-dir", str(out_dir),
    ])
    assert rc == 0
    summary = json.loads((out_dir / "stage158_trade_attribution_audit_summary.json").read_text())
    assert summary["bar_count"] == 3
    trades = pd.read_csv(out_dir / "stage158_trade_attribution_audit_trades.csv")
    assert int(trades["bar_window_count"].iloc[0]) >= 1
    assert "mfe_bps" in trades.columns
    assert trades["diagnosis"].iloc[0] in {"EXIT_FAIL", "EXECUTION_OR_EXIT_FAIL", "RULE_FAIL", "SMALL_N_UNRESOLVED"}


def test_stale_contamination_detection(tmp_path: Path):
    bars = tmp_path / "bars.csv"
    bars.write_text("2026.07.07\t21:30:00\t100\t101\t99\t100\t1\t0\t10\n", encoding="utf-8")
    ledger = tmp_path / "ledger.csv"
    pd.DataFrame([
        {
            "rule_id": "R_GEQ35",
            "feature_date": "2026-07-07T10:00:00Z",
            "entry_time": "2026-07-07T21:30:00Z",
            "exit_time": "2026-07-07T21:35:00Z",
            "entry_price": 100.0,
            "exit_price": 99.0,
            "net_profit": -1.0,
            "bps_move": -100.0,
            "outcome": "LOSS",
        }
    ]).to_csv(ledger, index=False)
    scores = tmp_path / "scores.csv"
    pd.DataFrame([{"rule_id": "R_GEQ35"}]).to_csv(scores, index=False)
    risk = tmp_path / "risk.json"
    risk.write_text("{}", encoding="utf-8")
    out_dir = tmp_path / "out"
    main([
        "--root", str(tmp_path),
        "--clean-ledger", str(ledger),
        "--score-csv", str(scores),
        "--risk-summary", str(risk),
        "--bars-m5", str(bars),
        "--timestamp-shift-hours", "-3",
        "--entry-time-shift-hours", "-3",
        "--max-signal-age-sec", "7200",
        "--output-dir", str(out_dir),
    ])
    diag = pd.read_csv(out_dir / "stage158_diagnosis_summary.csv")
    assert "STALE_CONTAMINATED" in set(diag["diagnosis"])
