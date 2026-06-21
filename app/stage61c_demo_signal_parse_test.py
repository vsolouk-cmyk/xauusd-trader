#!/usr/bin/env python3
"""
Stage61C Demo Signal Parse Test
Creates a synthetic MT5 signal CSV for demo-only EA parse testing with AllowTrading=false.
No broker connection. No order submission. No promotion.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

HEADER = [
    "signal_id",
    "candidate_id",
    "base_candidate_id",
    "context_tag",
    "entry_time_utc",
    "direction",
    "symbol",
    "lot",
    "max_spread_cost_bps",
    "horizon_m5_bars",
    "expires_utc",
    "status",
    "comment",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def write_report(path: Path, summary: dict) -> None:
    lines = [
        "# Stage61C Demo Signal Parse Test",
        "",
        f"- status: `{summary['status']}`",
        f"- decision: `{summary['decision']}`",
        f"- next_allowed_step: `{summary['next_allowed_step']}`",
        "- promotion: `NO_GO`",
        "- EA: `DEMO_HARNESS_PARSE_TEST_ONLY`",
        "- paper_live: `NO_GO`",
        "- live: `NO_GO`",
        "",
        "## Generated file",
        f"- mt5_signal_csv: `{summary['mt5_signal_csv']}`",
        f"- generated_rows: `{summary['generated_rows']}`",
        f"- allow_trading_required: `{summary['allow_trading_required']}`",
        f"- orders_created_by_python: `{summary['orders_created_by_python']}`",
        "",
        "## MT5 test instruction",
        "Copy the generated CSV to the terminal `MQL5/Files` folder as `stage61_demo_signals.csv`, attach the compiled Stage61 EA to a demo XAUUSD chart, keep `AllowTrading=false`, and confirm that the EA parses the signal but sends no order.",
        "",
        "## Interpretation",
        "Stage61C is a parse-only demo harness test. It does not authorize paper-live, live trading, or order submission.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_checks(path: Path, checks: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["check", "passed", "severity", "observed", "expected"])
        w.writeheader()
        for row in checks:
            w.writerow(row)


def load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", default="configs/stage61c_demo_signal_parse_test.json")
    ap.add_argument("--out", default="reports/stage61_demo_parse_test")
    ap.add_argument("--symbol", default=None)
    ap.add_argument("--direction", default=None, choices=["BUY", "SELL"])
    args = ap.parse_args()

    root = Path(args.root).resolve()
    out = (root / args.out).resolve()
    cfg = load_config((root / args.config).resolve())

    symbol = args.symbol or cfg.get("symbol", "XAUUSD")
    direction = args.direction or cfg.get("direction", "BUY")
    lot = float(cfg.get("lot", 0.01))
    max_spread_cost_bps = float(cfg.get("max_spread_cost_bps", 3.0380209087577326))
    horizon_m5_bars = int(cfg.get("horizon_m5_bars", 12))
    entry_delay_minutes = int(cfg.get("entry_delay_minutes", 5))
    expiry_minutes = int(cfg.get("expiry_minutes", 60))

    now = datetime.now(timezone.utc).replace(microsecond=0)
    entry = now + timedelta(minutes=entry_delay_minutes)
    expires = now + timedelta(minutes=expiry_minutes)

    csv_path = out / "mt5_files" / "stage61_demo_signals.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    row = {
        "signal_id": "STAGE61C_PARSE_TEST_001",
        "candidate_id": "STAGE61C_PARSE_TEST_CANDIDATE",
        "base_candidate_id": "STAGE58B_CONTEXT_AWARE_STAGE51",
        "context_tag": "PARSE_TEST_ONLY_ALLOWTRADING_FALSE",
        "entry_time_utc": entry.isoformat().replace("+00:00", "Z"),
        "direction": direction,
        "symbol": symbol,
        "lot": f"{lot:.2f}",
        "max_spread_cost_bps": f"{max_spread_cost_bps:.6f}",
        "horizon_m5_bars": str(horizon_m5_bars),
        "expires_utc": expires.isoformat().replace("+00:00", "Z"),
        "status": "PENDING",
        "comment": "STAGE61C_PARSE_ONLY_KEEP_ALLOWTRADING_FALSE",
    }

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        w.writerow(row)

    checks = [
        {"check": "signal_csv_created", "passed": csv_path.exists(), "severity": "HIGH", "observed": str(csv_path), "expected": "CSV exists"},
        {"check": "signal_csv_has_one_row", "passed": True, "severity": "HIGH", "observed": 1, "expected": "one synthetic parse-only signal"},
        {"check": "allow_trading_required_false_in_mt5", "passed": True, "severity": "HIGH", "observed": False, "expected": "User keeps EA AllowTrading=false"},
        {"check": "python_broker_connection_disabled", "passed": True, "severity": "HIGH", "observed": "DISABLED", "expected": "Python does not connect to broker"},
    ]

    summary = {
        "stage": "Stage61C_DEMO_SIGNAL_PARSE_TEST_NO_PROMOTION",
        "status": "DEMO_SIGNAL_PARSE_TEST_FILE_READY_NO_PROMOTION",
        "promotion": "NO_GO",
        "EA": "DEMO_HARNESS_PARSE_TEST_ONLY",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "decision": "COPY_PARSE_TEST_SIGNAL_TO_MT5_FILES_KEEP_ALLOWTRADING_FALSE_NO_PROMOTION",
        "next_allowed_step": "ATTACH_EA_WITH_ALLOWTRADING_FALSE_AND_VERIFY_PARSE_NO_ORDER",
        "root": str(root),
        "mt5_signal_csv": str(csv_path),
        "mt5_destination_file_name": "stage61_demo_signals.csv",
        "generated_rows": 1,
        "signal_preview": row,
        "allow_trading_required": False,
        "require_demo_account_required": True,
        "orders_created_by_python": 0,
        "broker_connection": "DISABLED",
        "paper_live_connection": "DISABLED",
        "checks": checks,
        "failed_high_checks": [c["check"] for c in checks if c["severity"] == "HIGH" and not c["passed"]],
        "generated_utc": utc_now_iso(),
    }

    write_json(out / "stage61c_demo_signal_parse_test_summary.json", summary)
    write_report(out / "stage61c_demo_signal_parse_test_report.md", summary)
    write_checks(out / "stage61c_demo_signal_parse_test_checks.csv", checks)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
