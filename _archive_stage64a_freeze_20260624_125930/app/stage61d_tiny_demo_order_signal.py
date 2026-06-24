#!/usr/bin/env python3
"""Stage61D tiny demo order signal generator.

This tool prepares a single demo-only signal CSV for the already-compiled
Stage61_DemoExecutionHarness EA. It does not connect to a broker and does not
send orders. It deliberately requires explicit CLI acknowledgement before it
creates the MT5-ready armed signal file.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

STAGE = "Stage61D_TINY_DEMO_ORDER_TEST_NO_PROMOTION"
SAFE_HEADER = [
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


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(tzinfo=None).isoformat() + "Z"


def load_json(path: Path, default: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if not path.exists():
        return {} if default is None else dict(default)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def check_stage61c2(summary_path: Path, cfg: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], List[Dict[str, Any]]]:
    checks: List[Dict[str, Any]] = []
    require = bool(cfg.get("require_stage61c2_parse_ok", True))
    required_statuses = set(cfg.get("required_stage61c2_statuses", []))
    summary = load_json(summary_path, {})
    found = bool(summary)
    checks.append({
        "check": "stage61c2_summary_found",
        "passed": found or not require,
        "severity": "HIGH" if require else "LOW",
        "observed": str(summary_path) if found else None,
        "expected": "Stage61C2 telemetry summary exists before tiny demo order design",
    })
    telemetry = summary.get("telemetry", {}) if isinstance(summary, dict) else {}
    observed_status = telemetry.get("status") or summary.get("status")
    status_ok = (not require) or (observed_status in required_statuses)
    checks.append({
        "check": "stage61c2_parse_status_ok",
        "passed": status_ok,
        "severity": "HIGH" if require else "LOW",
        "observed": observed_status,
        "expected": sorted(required_statuses),
    })
    orders_created = int(summary.get("orders_created", 0) or telemetry.get("orders_created", 0) or 0)
    checks.append({
        "check": "stage61c2_no_orders_created",
        "passed": orders_created == 0,
        "severity": "HIGH",
        "observed": orders_created,
        "expected": 0,
    })
    return all(c["passed"] for c in checks if c.get("severity") == "HIGH"), summary, checks


def build_signal(cfg: Dict[str, Any]) -> Dict[str, str]:
    now = utc_now()
    expires = now + timedelta(minutes=int(cfg.get("expires_minutes", 60)))
    symbol = str(cfg.get("symbol", "XAUUSD"))
    direction = str(cfg.get("direction", "BUY")).upper()
    lot = float(cfg.get("lot", 0.01))
    max_lot = float(cfg.get("hard_blocks", {}).get("max_lot", 0.01))
    if direction not in {"BUY", "SELL"}:
        raise ValueError(f"direction must be BUY or SELL, got {direction!r}")
    if lot <= 0 or lot > max_lot:
        raise ValueError(f"lot must be >0 and <= configured max_lot={max_lot}, got {lot}")
    return {
        "signal_id": f"S61D_TINY_DEMO_{now.strftime('%Y%m%dT%H%M%SZ')}",
        "candidate_id": "S61D_TINY_DEMO_ORDER_TEST_SIGNAL",
        "base_candidate_id": "STAGE61D_EXECUTION_PLUMBING_ONLY",
        "context_tag": "DEMO_EXECUTION_SANDBOX_ONLY_NO_EDGE",
        "entry_time_utc": iso_z(now),
        "direction": direction,
        "symbol": symbol,
        "lot": f"{lot:.2f}",
        "max_spread_cost_bps": str(float(cfg.get("max_spread_cost_bps", 3.5))),
        "horizon_m5_bars": str(int(cfg.get("horizon_m5_bars", 1))),
        "expires_utc": iso_z(expires),
        "status": "READY",
        "comment": "Stage61D tiny demo order plumbing test only; no edge promotion; demo account only",
    }


def write_signal_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SAFE_HEADER)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in SAFE_HEADER})


def write_checks(path: Path, checks: List[Dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    fields = ["check", "passed", "severity", "observed", "expected"]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for c in checks:
            writer.writerow({
                "check": c.get("check"),
                "passed": c.get("passed"),
                "severity": c.get("severity"),
                "observed": json.dumps(c.get("observed"), ensure_ascii=False) if isinstance(c.get("observed"), (dict, list)) else c.get("observed"),
                "expected": json.dumps(c.get("expected"), ensure_ascii=False) if isinstance(c.get("expected"), (dict, list)) else c.get("expected"),
            })


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", default="configs/stage61d_tiny_demo_order_test.json")
    ap.add_argument("--stage61c2-summary", default="reports/stage61_demo_parse_telemetry/stage61c2_demo_ea_telemetry_summary.json")
    ap.add_argument("--out", default="reports/stage61_demo_tiny_order")
    ap.add_argument("--arm-demo-order", action="store_true", help="Create MT5-ready one-row demo signal file")
    ap.add_argument("--i-understand-demo-order", action="store_true", help="Required acknowledgement for armed demo signal generation")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    out = (root / args.out).resolve()
    ensure_dir(out)
    cfg = load_json((root / args.config).resolve())

    stage_ok, telemetry_summary, checks = check_stage61c2((root / args.stage61c2_summary).resolve(), cfg)

    hard_blocks = cfg.get("hard_blocks", {})
    checks.extend([
        {"check": "live_blocked_by_policy", "passed": not bool(hard_blocks.get("allow_live", False)), "severity": "HIGH", "observed": hard_blocks.get("allow_live", False), "expected": False},
        {"check": "paper_live_blocked_by_policy", "passed": not bool(hard_blocks.get("allow_paper_live", False)), "severity": "HIGH", "observed": hard_blocks.get("allow_paper_live", False), "expected": False},
        {"check": "non_demo_blocked_by_policy", "passed": not bool(hard_blocks.get("allow_non_demo", False)), "severity": "HIGH", "observed": hard_blocks.get("allow_non_demo", False), "expected": False},
        {"check": "single_order_file_limit", "passed": int(hard_blocks.get("max_orders_in_file", 1)) == 1, "severity": "HIGH", "observed": hard_blocks.get("max_orders_in_file", 1), "expected": 1},
    ])

    armed = bool(args.arm_demo_order and args.i_understand_demo_order)
    arm_requested_incomplete = bool(args.arm_demo_order and not args.i_understand_demo_order)
    signal_row: Dict[str, str] | None = None
    mt5_file = out / "mt5_files" / str(cfg.get("signal_file_name", "stage61_demo_signals.csv"))
    preview_file = out / "stage61d_tiny_demo_signal_preview.csv"
    decision = "DEMO_ORDER_SIGNAL_PREVIEW_ONLY_NO_ORDER_NO_PROMOTION"
    status = "TINY_DEMO_ORDER_SIGNAL_PREVIEW_COMPLETE_NO_PROMOTION"
    next_step = "REVIEW_PREVIEW_THEN_RERUN_WITH_EXPLICIT_ARM_FLAGS_IF_YOU_ACCEPT_DEMO_ORDER_TEST"
    exported_demo_signals = 0

    if not stage_ok:
        decision = "BLOCKED_STAGE61C2_PARSE_TELEMETRY_NOT_READY_NO_PROMOTION"
        status = "TINY_DEMO_ORDER_SIGNAL_BLOCKED_NO_PROMOTION"
        next_step = "FIX_STAGE61C2_PARSE_TELEMETRY_BEFORE_DEMO_ORDER_TEST"
    elif arm_requested_incomplete:
        decision = "BLOCKED_MISSING_EXPLICIT_DEMO_ORDER_ACK_NO_PROMOTION"
        status = "TINY_DEMO_ORDER_SIGNAL_BLOCKED_NO_PROMOTION"
        next_step = "RERUN_WITH_BOTH_ARM_FLAGS_ONLY_IF_YOU_ACCEPT_TINY_DEMO_ORDER_TEST"
    else:
        signal_row = build_signal(cfg)
        write_signal_csv(preview_file, [signal_row])
        if armed:
            write_signal_csv(mt5_file, [signal_row])
            exported_demo_signals = 1
            decision = "TINY_DEMO_ORDER_SIGNAL_ARMED_FOR_MT5_DEMO_ONLY_NO_EDGE_PROMOTION"
            status = "TINY_DEMO_ORDER_SIGNAL_ARMED_NO_PROMOTION"
            next_step = "COPY_SIGNAL_TO_MT5_FILES_SET_EA_ALLOWTRADING_TRUE_ON_DEMO_ONLY_THEN_OBSERVE_AND_DISABLE"
        else:
            # Do not create mt5_files armed signal without acknowledgement.
            if mt5_file.exists():
                try:
                    mt5_file.unlink()
                except OSError:
                    pass

    failed_high = [c["check"] for c in checks if c.get("severity") == "HIGH" and not c.get("passed")]
    summary = {
        "stage": STAGE,
        "status": status,
        "promotion": "NO_GO",
        "EA": "DEMO_HARNESS_ONLY",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "decision": decision,
        "next_allowed_step": next_step,
        "root": str(root),
        "config": str((root / args.config).resolve()),
        "stage61c2_summary": str((root / args.stage61c2_summary).resolve()),
        "armed": armed,
        "exported_demo_signals": exported_demo_signals,
        "preview_file": str(preview_file) if signal_row else None,
        "mt5_signal_file": str(mt5_file) if armed else None,
        "signal": signal_row,
        "ea_settings_required": cfg.get("ea_settings_required", {}),
        "hard_blocks": ["NO_LIVE", "NO_PAPER_LIVE", "DEMO_ACCOUNT_ONLY", "TINY_LOT_ONLY", "ONE_SIGNAL_ONLY"],
        "checks": checks,
        "failed_high_checks": failed_high,
        "orders_created_by_python": 0,
        "broker_connection_by_python": "DISABLED",
        "generated_utc": iso_z(utc_now()),
    }
    (out / "stage61d_tiny_demo_order_signal_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_checks(out / "stage61d_tiny_demo_order_signal_checks.csv", checks)
    report = [
        "# Stage61D Tiny Demo Order Signal",
        "",
        f"- status: `{status}`",
        f"- decision: `{decision}`",
        f"- next_allowed_step: `{next_step}`",
        "- promotion: `NO_GO`",
        "- EA: `DEMO_HARNESS_ONLY`",
        "- paper_live: `NO_GO`",
        "- live: `NO_GO`",
        "",
        "## Output",
        f"- armed: `{armed}`",
        f"- exported_demo_signals: `{exported_demo_signals}`",
        f"- preview_file: `{preview_file if signal_row else None}`",
        f"- mt5_signal_file: `{mt5_file if armed else None}`",
        "- orders_created_by_python: `0`",
        "- broker_connection_by_python: `DISABLED`",
        "",
        "## Required MT5 EA settings for the armed run",
    ]
    for k, v in cfg.get("ea_settings_required", {}).items():
        report.append(f"- `{k}` = `{v}`")
    report.extend([
        "",
        "## Interpretation",
        "Stage61D only prepares a one-signal CSV for a tiny demo-account order plumbing test. It does not authorize paper-live, live trading, unrestricted order submission, or edge promotion.",
    ])
    (out / "stage61d_tiny_demo_order_signal_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
