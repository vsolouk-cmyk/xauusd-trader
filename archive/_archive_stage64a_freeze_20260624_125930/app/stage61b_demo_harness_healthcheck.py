#!/usr/bin/env python3
"""
Stage61B demo harness healthcheck.

Creates a no-order MT5/Files signal CSV and a readiness report after the
Stage61 demo EA source has compiled in MetaEditor. This script does not connect
to MT5, broker APIs, or submit any order.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

CSV_FIELDS = [
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


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_empty_signal_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()


def write_checks(path: Path, checks: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["check", "passed", "severity", "observed", "expected"])
        writer.writeheader()
        for c in checks:
            row = dict(c)
            for k in ["observed", "expected"]:
                if not isinstance(row.get(k), str):
                    row[k] = json.dumps(row.get(k), ensure_ascii=False)
            writer.writerow(row)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", default="configs/stage61b_demo_harness_healthcheck.json")
    ap.add_argument("--stage61-config", default="configs/stage61_demo_execution_sandbox.json")
    ap.add_argument("--ea-source", default="mql5/Experts/Stage61_DemoExecutionHarness.mq5")
    ap.add_argument("--stage61-export-summary", default="reports/stage61_demo_execution_sandbox/stage61_demo_signal_exporter_summary.json")
    ap.add_argument("--compiled-ok", action="store_true", help="Set this only after MetaEditor compile succeeds on the MT5 machine.")
    ap.add_argument("--out", default="reports/stage61_demo_healthcheck")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    out = root / args.out
    cfg = load_json(root / args.config)
    stage61_cfg = load_json(root / args.stage61_config)

    ea_source = root / args.ea_source
    stage61_summary_path = root / args.stage61_export_summary
    stage61_summary = load_json(stage61_summary_path)

    mt5_file_name = cfg.get("mt5_signal_file_name") or stage61_cfg.get("mt5_signal_file_name") or "stage61_demo_signals.csv"
    generated_signal_csv = out / "mt5_files" / mt5_file_name
    write_empty_signal_csv(generated_signal_csv)

    checks = [
        {
            "check": "ea_source_present",
            "passed": ea_source.exists(),
            "severity": "HIGH",
            "observed": str(ea_source),
            "expected": "Stage61_DemoExecutionHarness.mq5 exists in repo",
        },
        {
            "check": "metaeditor_compile_confirmed_by_user",
            "passed": bool(args.compiled_ok),
            "severity": "HIGH",
            "observed": bool(args.compiled_ok),
            "expected": "Use --compiled-ok after successful MetaEditor compile",
        },
        {
            "check": "no_order_healthcheck_file_created",
            "passed": generated_signal_csv.exists(),
            "severity": "HIGH",
            "observed": str(generated_signal_csv),
            "expected": "Empty CSV with header only, safe for EA parse test",
        },
        {
            "check": "stage61_export_summary_optional",
            "passed": stage61_summary_path.exists(),
            "severity": "LOW",
            "observed": str(stage61_summary_path),
            "expected": "Optional exporter summary exists if Stage61 exporter has run",
        },
    ]

    failed_high = [c["check"] for c in checks if c["severity"] == "HIGH" and not c["passed"]]
    decision = "DEMO_HARNESS_HEALTHCHECK_READY_FOR_MT5_NO_ORDER_PARSE_TEST_NO_PROMOTION" if not failed_high else "DEMO_HARNESS_HEALTHCHECK_BLOCKED_NO_PROMOTION"
    next_step = "COPY_EMPTY_SIGNAL_CSV_TO_MT5_FILES_AND_ATTACH_EA_WITH_ALLOWTRADING_FALSE" if not failed_high else "FIX_FAILED_HEALTHCHECKS_BEFORE_MT5_PARSE_TEST"

    summary = {
        "stage": "Stage61B_DEMO_HARNESS_HEALTHCHECK_NO_PROMOTION",
        "status": "DEMO_HARNESS_HEALTHCHECK_COMPLETE_NO_PROMOTION",
        "promotion": "NO_GO",
        "EA": "DEMO_HARNESS_SOURCE_COMPILED" if args.compiled_ok else "NO_GO_UNTIL_COMPILE_CONFIRMED",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "decision": decision,
        "next_allowed_step": next_step,
        "root": str(root),
        "ea_source": str(ea_source),
        "metaeditor_compile_confirmed_by_user": bool(args.compiled_ok),
        "generated_mt5_signal_csv": str(generated_signal_csv),
        "mt5_destination_file_name": mt5_file_name,
        "orders_created": 0,
        "broker_connection": "DISABLED",
        "allow_trading_required_in_mt5": False,
        "healthcheck_mode": "EMPTY_SIGNAL_FILE_PARSE_TEST_ONLY",
        "stage61_export_summary_found": stage61_summary_path.exists(),
        "stage61_export_summary": stage61_summary if stage61_summary else None,
        "checks": checks,
        "failed_high_checks": failed_high,
        "generated_utc": utc_now(),
    }

    out.mkdir(parents=True, exist_ok=True)
    summary_path = out / "stage61b_demo_harness_healthcheck_summary.json"
    report_path = out / "stage61b_demo_harness_healthcheck_report.md"
    checks_path = out / "stage61b_demo_harness_healthcheck_checks.csv"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_checks(checks_path, checks)

    report = [
        "# Stage61B Demo Harness Healthcheck",
        "",
        f"- status: `{summary['status']}`",
        f"- decision: `{decision}`",
        f"- next_allowed_step: `{next_step}`",
        "- promotion: `NO_GO`",
        f"- EA: `{summary['EA']}`",
        "- paper_live: `NO_GO`",
        "- live: `NO_GO`",
        "",
        "## Healthcheck",
        f"- EA source: `{ea_source}`",
        f"- MetaEditor compile confirmed: `{bool(args.compiled_ok)}`",
        f"- Empty MT5 signal CSV: `{generated_signal_csv}`",
        "- orders_created: `0`",
        "- broker_connection: `DISABLED`",
        "",
        "## MT5 parse test",
        "Copy the generated empty CSV to the MT5 `MQL5/Files` folder as `stage61_demo_signals.csv`, attach the EA to a demo XAUUSD chart, keep `AllowTrading=false`, and verify that no order is sent.",
        "",
        "## Interpretation",
        "Stage61B verifies the demo harness plumbing up to a no-order file parse test. It does not authorize paper-live, live trading, or order submission.",
    ]
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")

    print(json.dumps({"decision": decision, "summary": str(summary_path), "report": str(report_path), "mt5_csv": str(generated_signal_csv)}, indent=2))


if __name__ == "__main__":
    main()
