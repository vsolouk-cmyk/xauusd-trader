#!/usr/bin/env python3
"""Stage61D3 EA-compatible tiny demo signal generator.

Writes the exact 16-column CSV schema consumed by Stage61_DemoExecutionHarness.mq5.
This script does not connect to a broker and does not submit orders.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

HEADER = [
    "signal_id",
    "candidate_id",
    "base_candidate_id",
    "context_tag",
    "signal_time_utc",
    "entry_time_utc",
    "symbol",
    "side",
    "lot",
    "sl_points",
    "tp_points",
    "max_spread_points",
    "max_hold_minutes",
    "expiry_utc",
    "magic",
    "comment",
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_csv(path: Path, cfg: Dict[str, Any]) -> Dict[str, Any]:
    now = utc_now()
    ttl_minutes = int(cfg.get("ttl_minutes", 240))
    expires = now + timedelta(minutes=ttl_minutes)
    side = str(cfg.get("side", cfg.get("direction", "BUY"))).upper().strip()
    if side not in {"BUY", "SELL"}:
        raise ValueError(f"side must be BUY or SELL, got {side!r}")
    lot = float(cfg.get("lot", 0.01))
    if lot <= 0 or lot > float(cfg.get("max_allowed_lot", 0.01)):
        raise ValueError(f"lot must be >0 and <= max_allowed_lot, got {lot}")

    signal_id = "S61D3_TINY_DEMO_" + now.strftime("%Y%m%dT%H%M%SZ")
    row: Dict[str, Any] = {
        "signal_id": signal_id,
        "candidate_id": "S61D3_TINY_DEMO_ORDER_TEST_SIGNAL",
        "base_candidate_id": "STAGE61D3_EXECUTION_PLUMBING_ONLY",
        "context_tag": "DEMO_EXECUTION_SANDBOX_ONLY_NO_EDGE",
        "signal_time_utc": iso_z(now),
        "entry_time_utc": iso_z(now),
        "symbol": str(cfg.get("trade_symbol", "XAUUSD")),
        "side": side,
        "lot": f"{lot:.2f}",
        "sl_points": int(cfg.get("sl_points", 500)),
        "tp_points": int(cfg.get("tp_points", 500)),
        "max_spread_points": int(cfg.get("max_spread_points", 60)),
        "max_hold_minutes": int(cfg.get("max_hold_minutes", 10)),
        "expiry_utc": iso_z(expires),
        "magic": int(cfg.get("magic", 610058)),
        "comment": str(cfg.get("comment", "Stage61D3 tiny demo order plumbing test only")),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADER)
        writer.writeheader()
        writer.writerow(row)
    return row


def validate_csv(path: Path) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    exists = path.exists()
    checks.append({"check": "signal_csv_exists", "passed": exists, "severity": "HIGH", "observed": str(path), "expected": "file exists"})
    if not exists:
        return checks
    size = path.stat().st_size
    checks.append({"check": "signal_csv_nonzero_size", "passed": size > 0, "severity": "HIGH", "observed": size, "expected": ">0 bytes"})
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or []
    checks.append({"check": "ea_compatible_16_column_header", "passed": fieldnames == HEADER, "severity": "HIGH", "observed": fieldnames, "expected": HEADER})
    checks.append({"check": "exactly_one_signal_row", "passed": len(rows) == 1, "severity": "HIGH", "observed": len(rows), "expected": 1})
    if rows:
        r = rows[0]
        checks.append({"check": "side_supported_by_ea", "passed": r.get("side") in {"BUY", "SELL"}, "severity": "HIGH", "observed": r.get("side"), "expected": "BUY or SELL"})
        checks.append({"check": "symbol_is_xauusd", "passed": str(r.get("symbol", "")).upper() == "XAUUSD", "severity": "HIGH", "observed": r.get("symbol"), "expected": "XAUUSD"})
        try:
            lot = float(r.get("lot", "nan"))
            ok = 0 < lot <= 0.01
        except Exception:
            lot, ok = r.get("lot"), False
        checks.append({"check": "tiny_lot", "passed": ok, "severity": "HIGH", "observed": lot, "expected": "0 < lot <= 0.01"})
        try:
            exp = datetime.fromisoformat(str(r.get("expiry_utc", "")).replace("Z", "+00:00"))
            ok = exp > datetime.now(timezone.utc)
            obs: Any = r.get("expiry_utc")
        except Exception as exc:
            ok, obs = False, repr(exc)
        checks.append({"check": "expiry_in_future", "passed": ok, "severity": "HIGH", "observed": obs, "expected": "future UTC expiry"})
    return checks


def write_outputs(out: Path, row: Dict[str, Any], checks: List[Dict[str, Any]], signal_path: Path, cfg: Dict[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    failed_high = [c for c in checks if c.get("severity") == "HIGH" and not c.get("passed")]
    status = "EA_COMPATIBLE_TINY_DEMO_SIGNAL_READY_NO_PROMOTION" if not failed_high else "EA_COMPATIBLE_TINY_DEMO_SIGNAL_FAILED_CHECKS_NO_PROMOTION"
    decision = "COPY_EA_COMPATIBLE_SIGNAL_TO_MT5_FILES_AND_RUN_STAGE61_DEMOEXECUTIONHARNESS" if not failed_high else "FIX_SIGNAL_CSV_BEFORE_MT5"
    summary = {
        "stage": "Stage61D3_EA_COMPATIBLE_TINY_DEMO_SIGNAL_NO_PROMOTION",
        "status": status,
        "promotion": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "decision": decision,
        "next_allowed_step": "MT5_TINY_DEMO_ORDER_TEST_WITH_STAGE61_DEMOEXECUTIONHARNESS_ALLOWTRADING_TRUE" if not failed_high else "REGENERATE_SIGNAL",
        "signal_csv": str(signal_path),
        "mt5_destination_file_name": cfg.get("output_file_name", "stage61_demo_signals.csv"),
        "required_ea": "Stage61_DemoExecutionHarness",
        "do_not_use_ea": "Stage61_DemoExecutionHarness_Telemetry",
        "schema_contract": "16-column EA-compatible CSV: side is column 8, lot is column 9",
        "signal_row": row,
        "checks": checks,
        "failed_high_checks": failed_high,
        "orders_created_by_python": 0,
        "generated_utc": iso_z(datetime.now(timezone.utc)),
    }
    (out / "stage61d3_ea_compatible_tiny_demo_signal_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with (out / "stage61d3_ea_compatible_tiny_demo_signal_checks.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["check", "passed", "severity", "observed", "expected"])
        writer.writeheader()
        for c in checks:
            writer.writerow(c)
    report = [
        "# Stage61D3 EA-Compatible Tiny Demo Signal",
        "",
        f"- status: `{status}`",
        f"- decision: `{decision}`",
        "- promotion: `NO_GO`",
        "- paper_live: `NO_GO`",
        "- live: `NO_GO`",
        "",
        "## Why this hotfix exists",
        "",
        "The previous Stage61D2 CSV used a 13-column exporter schema. The compiled Stage61_DemoExecutionHarness expects a 16-column execution schema, so it read `lot` as `side` and printed `unsupported side ... 0.01`. This hotfix writes the exact 16-column schema consumed by the EA.",
        "",
        "## Signal file",
        "",
        f"- generated: `{signal_path}`",
        f"- destination in MT5 `MQL5/Files`: `{cfg.get('output_file_name', 'stage61_demo_signals.csv')}`",
        f"- signal_id: `{row.get('signal_id')}`",
        f"- side: `{row.get('side')}`",
        f"- lot: `{row.get('lot')}`",
        f"- expiry_utc: `{row.get('expiry_utc')}`",
        "",
        "## MT5 order-test settings",
        "",
        "- Detach `Stage61_DemoExecutionHarness_Telemetry`.",
        "- Attach `Stage61_DemoExecutionHarness`.",
        "- `RequireDemoAccount=true`.",
        "- `AllowTrading=true` only for this tiny demo test.",
        "- `FixedLot=0.01`, `MaxOpenPositions=1`, `MaxOrdersPerDay=1`.",
        "- Immediately after the test, set `AllowTrading=false`.",
    ]
    (out / "stage61d3_ea_compatible_tiny_demo_signal_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", default="reports/stage61_demo_tiny_order")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    cfg = load_json(root / args.config)
    out = root / args.out
    signal_path = out / "mt5_files" / str(cfg.get("output_file_name", "stage61_demo_signals.csv"))
    row = write_csv(signal_path, cfg)
    checks = validate_csv(signal_path)
    write_outputs(out, row, checks, signal_path, cfg)


if __name__ == "__main__":
    main()
