from pathlib import Path
import csv
import json
import tempfile
import subprocess
import sys
import pandas as pd

BANNED = ["OrderSend", "CTrade", "Buy(", "Sell(", "PositionOpen"]

def main():
    root = Path(__file__).resolve().parents[1]
    ea = root / "mt5" / "K06_ObserverOnly_EA.mq5"
    text = ea.read_text(encoding="utf-8")
    for token in BANNED:
        assert token not in text, f"banned token present in EA text: {token}"

    with tempfile.TemporaryDirectory() as td:
        r = Path(td)
        (r/"app").mkdir()
        (r/"configs").mkdir()
        (r/"data/macro_regime/normalized").mkdir(parents=True)
        (r/"reports/stage70b_champion_hard_audit").mkdir(parents=True)
        (r/"reports/stage71_locked_historical_forward_test").mkdir(parents=True)
        (r/"reports/stage72_historical_daily_replay").mkdir(parents=True)
        (r/"reports/stage73b_corrected_asof_validation_bridge").mkdir(parents=True)
        (r/"reports/stage75_historical_activation_drill").mkdir(parents=True)
        for src in (root/"app").glob("stage76d_*.py"):
            (r/"app"/src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        cfg = {
            "macro_path": "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv",
            "bridge_csv_path": "data/mt5_bridge/k06_observer_signal.csv",
            "wide_reference_csv_path": "data/mt5_bridge/k06_observer_signal_wide_reference.csv"
        }
        (r/"configs/stage76d_k06_mt5_observer_bridge_schema_fix.json").write_text(json.dumps(cfg), encoding="utf-8")
        rows = pd.DataFrame([
            {"feature_date_utc":"2026-06-26","gold_close":4045.53,"gold_sma20_over_50":-0.05,"dxy_ret_20d":0.02,"real_yield_change_20d":0.16}
        ])
        rows.to_csv(r/"data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv", index=False)
        locks = [
            ("reports/stage70b_champion_hard_audit/stage70b_champion_hard_audit_summary.json","PROMOTE_TO_NO_ORDER_SHADOW_CANDIDATE"),
            ("reports/stage71_locked_historical_forward_test/stage71_locked_historical_forward_test_summary.json","K06_PASSES_LOCKED_HISTORICAL_FORWARD"),
            ("reports/stage72_historical_daily_replay/stage72_historical_daily_replay_summary.json","K06_PASSES_HISTORICAL_DAILY_REPLAY"),
            ("reports/stage73b_corrected_asof_validation_bridge/stage73b_corrected_asof_validation_bridge_summary.json","K06_PASSES_CORRECTED_ASOF_VALIDATION"),
            ("reports/stage75_historical_activation_drill/stage75_historical_activation_drill_summary.json","K06_PASSES_HISTORICAL_ACTIVATION_DRILL"),
        ]
        for rel, disp in locks:
            p = r/rel
            p.write_text(json.dumps({"disposition": disp}), encoding="utf-8")
        cmd = [sys.executable, str(r/"app/stage76d_k06_mt5_observer_bridge_schema_fix.py"), "--root", str(r), "--config", "configs/stage76d_k06_mt5_observer_bridge_schema_fix.json", "--out", "reports/stage76d"]
        subprocess.check_call(cmd)
        kv = r/"data/mt5_bridge/k06_observer_signal.csv"
        assert kv.exists()
        d = {}
        with kv.open(newline="", encoding="utf-8") as f:
            for row in csv.reader(f):
                if len(row) >= 2:
                    d[row[0]] = row[1]
        assert d["schema_version"] == "stage76d_key_value_v2"
        assert d["thesis_id"] == "K06_RESILIENT_GOLD_VS_DXY"
        assert d["latest_feature_date_utc"] == "2026-06-26"
        assert d["signal_active"] == "false"
        assert d["ea_mode"] == "OBSERVER_ONLY_NO_TRADE"
    print("Stage76D tests passed")

if __name__ == "__main__":
    main()
