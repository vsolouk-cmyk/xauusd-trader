from __future__ import annotations

import argparse
import csv
import datetime as dt
import importlib.util
import json
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "stage171f_h64l_4h_macro_gdelt_orchestrator.py"
spec = importlib.util.spec_from_file_location("stage171f", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def write_feature_csv(path: Path, date: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "feature_date_utc", "sample_available_after_utc", "gold_sma20_over_50",
            "dxy_ret_20d", "real_yield_change_20d", "etf_flow_tonnes_3m",
        ])
        w.writeheader()
        w.writerow({
            "feature_date_utc": date,
            "sample_available_after_utc": f"{date}T23:59:59Z",
            "gold_sma20_over_50": 0.1,
            "dxy_ret_20d": -0.1,
            "real_yield_change_20d": -0.1,
            "etf_flow_tonnes_3m": 1.0,
        })


def make_root(tmp_path: Path, fresh: bool) -> Path:
    root = tmp_path / "repo"
    (root / "app").mkdir(parents=True)
    (root / "configs").mkdir(parents=True)
    today = dt.datetime.now(dt.timezone.utc).date()
    feature_date = today.isoformat() if fresh else (today - dt.timedelta(days=20)).isoformat()
    write_feature_csv(root / "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv", feature_date)
    rule = root / "reports/stage171e_h64l_exact_rule_lock_from_archive/stage171e_h64l_exact_locked_rule.json"
    rule.parent.mkdir(parents=True)
    rule.write_text(json.dumps({"exact_rule_locked": True}), encoding="utf-8")
    shadow = root / "app/stage171d_h64l_shadow_scheduler_and_logger.py"
    shadow.write_text(
        "from pathlib import Path\n"
        "import argparse\n"
        "p=argparse.ArgumentParser(); p.add_argument('mode'); p.add_argument('--root'); p.add_argument('--macro-dataset'); p.add_argument('--locked-rule-candidate'); p.add_argument('--ledger-csv'); p.add_argument('--operator-note'); a=p.parse_args(); "
        "q=Path(a.ledger_csv); q.parent.mkdir(parents=True, exist_ok=True); q.write_text('ok\\n'); print('shadow-ok')\n",
        encoding="utf-8",
    )
    cfg = {
        "interval_seconds": 14400,
        "report_dir": "reports/stage171f_h64l_4h_macro_gdelt_orchestrator",
        "lock_file": "data/forward_shadow/stage171f.lock",
        "feature_dataset": "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv",
        "max_feature_age_days": 3,
        "locked_rule": "reports/stage171e_h64l_exact_rule_lock_from_archive/stage171e_h64l_exact_locked_rule.json",
        "shadow_script": "app/stage171d_h64l_shadow_scheduler_and_logger.py",
        "shadow_ledger": "data/forward_shadow/h64l_manual_shadow_log.csv",
        "local_pipeline": [],
        "amarkets_manual_files": [],
        "gdelt": {"enabled": False},
    }
    (root / "configs/stage171f.json").write_text(json.dumps(cfg), encoding="utf-8")
    return root


def test_fresh_dataset_runs_shadow(tmp_path: Path) -> None:
    root = make_root(tmp_path, fresh=True)
    rc = mod.run_once(argparse.Namespace(root=str(root), config="configs/stage171f.json"))
    assert rc == 0
    summary = json.loads((root / "reports/stage171f_h64l_4h_macro_gdelt_orchestrator/stage171f_orchestrator_summary.json").read_text())
    assert summary["decision"] == "STAGE171F_4H_REFRESH_AND_SHADOW_COMPLETE_NO_ORDER"
    assert summary["shadow_run"]["ok"] is True
    assert summary["order_routing_allowed"] is False


def test_stale_dataset_blocks_shadow(tmp_path: Path) -> None:
    root = make_root(tmp_path, fresh=False)
    rc = mod.run_once(argparse.Namespace(root=str(root), config="configs/stage171f.json"))
    assert rc == 2
    summary = json.loads((root / "reports/stage171f_h64l_4h_macro_gdelt_orchestrator/stage171f_orchestrator_summary.json").read_text())
    assert summary["decision"] == "STAGE171F_MACRO_FEATURE_DATA_STALE_SHADOW_BLOCKED"
    assert summary["shadow_run"]["skipped"] is True


def test_gdelt_merge_upserts_by_hour(tmp_path: Path) -> None:
    existing = tmp_path / "existing.csv"
    incoming = tmp_path / "incoming.csv"
    for path, rows in [
        (existing, [
            {"time_bucket_utc": "2026-01-01T00:00:00Z", "shock_abs": "1"},
            {"time_bucket_utc": "2026-01-01T01:00:00Z", "shock_abs": "2"},
        ]),
        (incoming, [
            {"time_bucket_utc": "2026-01-01T01:00:00Z", "shock_abs": "20"},
            {"time_bucket_utc": "2026-01-01T02:00:00Z", "shock_abs": "3"},
        ]),
    ]:
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["time_bucket_utc", "shock_abs"])
            w.writeheader(); w.writerows(rows)
    result = mod.merge_gdelt_panel(existing, incoming)
    assert result["ok"] is True
    rows = list(csv.DictReader(existing.open()))
    assert len(rows) == 3
    assert rows[1]["shock_abs"] == "20"
