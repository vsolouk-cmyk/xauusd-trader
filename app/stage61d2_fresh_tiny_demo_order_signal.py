#!/usr/bin/env python3
"""Stage61D2 fresh tiny demo order signal generator and CSV validator.

Creates a fresh MT5 signal CSV for a single tiny DEMO order plumbing test.
It does not connect to a broker and does not submit orders.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, List

HEADER = [
    "signal_id", "candidate_id", "base_candidate_id", "context_tag", "entry_time_utc",
    "direction", "symbol", "lot", "max_spread_cost_bps", "horizon_m5_bars",
    "expires_utc", "status", "comment"
]


def utc_now_no_seconds() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(microsecond=0)


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_signal(path: Path, cfg: Dict[str, Any]) -> Dict[str, Any]:
    now = utc_now_no_seconds()
    ttl = int(cfg.get("ttl_minutes", 240))
    expires = now + timedelta(minutes=ttl)
    signal_id = "S61D2_TINY_DEMO_" + now.strftime("%Y%m%dT%H%M%SZ")
    row = {
        "signal_id": signal_id,
        "candidate_id": "S61D2_TINY_DEMO_ORDER_TEST_SIGNAL",
        "base_candidate_id": "STAGE61D2_EXECUTION_PLUMBING_ONLY",
        "context_tag": "DEMO_EXECUTION_SANDBOX_ONLY_NO_EDGE",
        "entry_time_utc": iso_z(now),
        "direction": str(cfg.get("direction", "BUY")).upper(),
        "symbol": str(cfg.get("trade_symbol", "XAUUSD")),
        "lot": str(cfg.get("lot", 0.01)),
        "max_spread_cost_bps": str(cfg.get("max_spread_cost_bps", 3.5)),
        "horizon_m5_bars": str(cfg.get("horizon_m5_bars", 1)),
        "expires_utc": iso_z(expires),
        "status": str(cfg.get("status", "READY")),
        "comment": str(cfg.get("comment", "Stage61D2 tiny demo order plumbing test only")),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADER)
        writer.writeheader()
        writer.writerow(row)
    return row


def validate_signal(path: Path) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    exists = path.exists()
    checks.append({"check": "signal_csv_exists", "passed": exists, "severity": "HIGH", "observed": str(path), "expected": "file exists"})
    if not exists:
        return checks
    size = path.stat().st_size
    checks.append({"check": "signal_csv_nonzero_size", "passed": size > 0, "severity": "HIGH", "observed": size, "expected": ">0 bytes"})
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        checks.append({"check": "signal_csv_header_exact", "passed": reader.fieldnames == HEADER, "severity": "HIGH", "observed": reader.fieldnames, "expected": HEADER})
        rows = list(reader)
    checks.append({"check": "signal_csv_one_row", "passed": len(rows) == 1, "severity": "HIGH", "observed": len(rows), "expected": 1})
    if rows:
        row = rows[0]
        checks.append({"check": "signal_status_ready", "passed": row.get("status") == "READY", "severity": "HIGH", "observed": row.get("status"), "expected": "READY"})
        checks.append({"check": "signal_lot_tiny", "passed": float(row.get("lot", "0") or 0) <= 0.01, "severity": "HIGH", "observed": row.get("lot"), "expected": "<=0.01"})
        try:
            exp = datetime.fromisoformat(row["expires_utc"].replace("Z", "+00:00"))
            checks.append({"check": "signal_not_expired_at_generation", "passed": exp > datetime.now(timezone.utc), "severity": "HIGH", "observed": row.get("expires_utc"), "expected": "future expiry"})
        except Exception as e:
            checks.append({"check": "signal_expiry_parse", "passed": False, "severity": "HIGH", "observed": repr(e), "expected": "parseable UTC expiry"})
    return checks


def write_outputs(out: Path, cfg: Dict[str, Any], row: Dict[str, Any], checks: List[Dict[str, Any]], signal_path: Path, mt5_files_dir: str | None) -> None:
    out.mkdir(parents=True, exist_ok=True)
    failed_high = [c for c in checks if c.get("severity") == "HIGH" and not c.get("passed")]
    summary = {
        "stage": "Stage61D2_FRESH_TINY_DEMO_ORDER_SIGNAL_NO_PROMOTION",
        "status": "FRESH_TINY_DEMO_SIGNAL_READY_NO_PROMOTION" if not failed_high else "FRESH_TINY_DEMO_SIGNAL_FAILED_CHECKS_NO_PROMOTION",
        "promotion": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "decision": "COPY_FRESH_SIGNAL_TO_MT5_FILES_AND_USE_ORDER_HARNESS_NOT_TELEMETRY" if not failed_high else "FIX_SIGNAL_FILE_BEFORE_MT5_ORDER_TEST",
        "next_allowed_step": "MT5_TINY_DEMO_ORDER_TEST_WITH_STAGE61_DEMOEXECUTIONHARNESS_ALLOWTRADING_TRUE" if not failed_high else "REGENERATE_SIGNAL",
        "signal_csv": str(signal_path),
        "mt5_destination_file_name": cfg.get("output_file_name", "stage61_demo_signals.csv"),
        "mt5_files_dir_hint": mt5_files_dir,
        "required_ea_for_order_test": cfg.get("required_ea_for_order_test", "Stage61_DemoExecutionHarness"),
        "do_not_use_for_order_test": cfg.get("do_not_use_for_order_test", "Stage61_DemoExecutionHarness_Telemetry"),
        "signal_row": row,
        "checks": checks,
        "failed_high_checks": failed_high,
        "orders_created_by_python": 0,
        "generated_utc": iso_z(datetime.now(timezone.utc)),
    }
    (out / "stage61d2_fresh_tiny_demo_order_signal_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with (out / "stage61d2_fresh_tiny_demo_order_signal_checks.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["check", "passed", "severity", "observed", "expected"])
        writer.writeheader()
        for c in checks:
            writer.writerow(c)
    report = [
        "# Stage61D2 Fresh Tiny Demo Order Signal",
        "",
        f"- status: `{summary['status']}`",
        f"- decision: `{summary['decision']}`",
        f"- next_allowed_step: `{summary['next_allowed_step']}`",
        "- promotion: `NO_GO`",
        "- paper_live: `NO_GO`",
        "- live: `NO_GO`",
        "",
        "## Critical separation",
        "",
        "For the actual tiny demo order test, attach `Stage61_DemoExecutionHarness`, not `Stage61_DemoExecutionHarness_Telemetry`. The telemetry EA intentionally never sends orders.",
        "",
        "## Signal file",
        "",
        f"- generated: `{signal_path}`",
        f"- destination file name in MT5 `MQL5/Files`: `{cfg.get('output_file_name', 'stage61_demo_signals.csv')}`",
        f"- signal_id: `{row.get('signal_id')}`",
        f"- expires_utc: `{row.get('expires_utc')}`",
        f"- lot: `{row.get('lot')}`",
        "",
        "## MT5 settings for tiny demo order",
        "",
        "- EA: `Stage61_DemoExecutionHarness`",
        "- Account: AMarkets demo only",
        "- `RequireDemoAccount=true`",
        "- `AllowTrading=true` only for this tiny demo order test",
        "- `FixedLot=0.01`",
        "- `MaxOpenPositions=1`",
        "- `MaxOrdersPerDay=1`",
        "",
        "Immediately after the test, set `AllowTrading=false` again.",
    ]
    (out / "stage61d2_fresh_tiny_demo_order_signal_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", default="reports/stage61_demo_tiny_order")
    ap.add_argument("--mt5-files-dir", default=None, help="Optional actual MT5 MQL5/Files directory path for report hint only.")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    cfg = load_json(root / args.config)
    out = root / args.out
    signal_path = out / "mt5_files" / cfg.get("output_file_name", "stage61_demo_signals.csv")
    row = write_signal(signal_path, cfg)
    checks = validate_signal(signal_path)
    write_outputs(out, cfg, row, checks, signal_path, args.mt5_files_dir)


if __name__ == "__main__":
    main()
