#!/usr/bin/env python3
"""Validate Stage61 telemetry status exported by the MT5 EA from MQL5/Files/stage61_ea_status.csv."""
import argparse, csv, json
from datetime import datetime, timezone
from pathlib import Path

EXPECTED_OK = {"PARSE_OK_EMPTY_NO_ORDER", "PARSE_OK_TRADING_DISABLED_NO_ORDER"}


def read_status(path: Path):
    data = {}
    if not path.exists():
        return data, f"status_file_not_found: {path}"
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)
    for row in rows[1:]:
        if len(row) >= 2:
            data[row[0]] = row[1]
    return data, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--status-file", required=True, help="Path to stage61_ea_status.csv copied/exported from MT5 MQL5/Files")
    ap.add_argument("--out", default="reports/stage61_demo_parse_telemetry")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    out = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    status_path = Path(args.status_file).expanduser().resolve()
    data, err = read_status(status_path)
    checks = []
    def check(name, passed, severity, observed, expected):
        checks.append({"check": name, "passed": bool(passed), "severity": severity, "observed": observed, "expected": expected})
    check("status_file_present", err is None, "HIGH", str(status_path), "stage61_ea_status.csv exists")
    status = data.get("status")
    check("status_parse_ok", status in EXPECTED_OK, "HIGH", status, f"one of {sorted(EXPECTED_OK)}")
    check("require_demo_account_true", data.get("require_demo_account") == "true", "HIGH", data.get("require_demo_account"), "true")
    check("allow_trading_false", data.get("allow_trading") == "false", "HIGH", data.get("allow_trading"), "false during parse test")
    valid_rows = int(data.get("valid_rows", "0") or 0) if data.get("valid_rows", "0").isdigit() else 0
    check("valid_rows_nonnegative", valid_rows >= 0, "MEDIUM", valid_rows, ">=0")
    failed_high = [c["check"] for c in checks if c["severity"] == "HIGH" and not c["passed"]]
    decision = "STAGE61C2_PARSE_TELEMETRY_OK_READY_FOR_TINY_DEMO_ORDER_DESIGN_NO_PROMOTION" if not failed_high else "STAGE61C2_PARSE_TELEMETRY_NOT_READY_FIX_EA_OR_FILE_NO_PROMOTION"
    summary = {
        "stage": "Stage61C2_DEMO_EA_PARSE_TELEMETRY_NO_PROMOTION",
        "status": "DEMO_EA_PARSE_TELEMETRY_VALIDATION_COMPLETE_NO_PROMOTION",
        "promotion": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "decision": decision,
        "next_allowed_step": "DESIGN_STAGE61D_TINY_DEMO_ORDER_TEST_NO_PROMOTION" if not failed_high else "FIX_STAGE61_TELEMETRY_OR_SIGNAL_FILE_NO_PROMOTION",
        "status_file": str(status_path),
        "telemetry": data,
        "checks": checks,
        "failed_high_checks": failed_high,
        "orders_created": 0,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (out / "stage61c2_demo_ea_telemetry_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with (out / "stage61c2_demo_ea_telemetry_checks.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["check", "passed", "severity", "observed", "expected"])
        w.writeheader(); w.writerows(checks)
    report = [
        "# Stage61C2 Demo EA Parse Telemetry", "",
        f"- status: `{summary['status']}`",
        f"- decision: `{decision}`",
        f"- next_allowed_step: `{summary['next_allowed_step']}`",
        "- promotion: `NO_GO`", "- paper_live: `NO_GO`", "- live: `NO_GO`", "",
        "## Telemetry", "",
    ]
    for k in sorted(data): report.append(f"- `{k}`: `{data[k]}`")
    report += ["", "## Failed high checks", "", *(f"- `{x}`" for x in failed_high), "", "## Interpretation", "", "This validates EA file parse telemetry only. It does not authorize paper-live, live trading, or unrestricted order submission."]
    (out / "stage61c2_demo_ea_telemetry_report.md").write_text("\n".join(report), encoding="utf-8")
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
