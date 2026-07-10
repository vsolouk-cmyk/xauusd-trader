#!/usr/bin/env python3
"""
Stage171D — H64L Shadow Scheduler and Logger.

Purpose:
- Run the H64L manual shadow checklist in a repeatable, scheduled, log-only way.
- Append the current H64L condition state to a durable CSV ledger/template.
- Optionally write a macOS launchd plist for daily local scheduling.

Hard constraints:
- No MT5 signal file is written.
- No demo/live authorization is emitted.
- No threshold re-optimization is performed.
- This is operational shadow logging only.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import plistlib
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

STAGE = "Stage171D_H64L_SHADOW_SCHEDULER_AND_LOGGER"
DECISION_READY = "STAGE171D_H64L_SHADOW_LOGGER_READY_NO_ORDER"
DEFAULT_REPORT_DIR = "reports/stage171d_h64l_shadow_scheduler_and_logger"
DEFAULT_LEDGER = "data/forward_shadow/h64l_manual_shadow_log.csv"
DEFAULT_DATASET = "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv"
DEFAULT_RULE_CANDIDATE = "reports/stage171b_h64l_exact_rule_extraction_and_shadow_start/stage171b_h64l_locked_rule_candidate.json"
DEFAULT_STAGE171C_CHECKLIST = "reports/stage171c_h64l_evidence_shadow_checklist/stage171c_h64l_current_shadow_checklist.csv"

CONDITIONS = [
    {
        "feature": "gold_sma20_over_50",
        "operator": ">",
        "threshold": 0.0,
        "reason_if_fail": "gold trend not positive",
    },
    {
        "feature": "dxy_ret_20d",
        "operator": "<",
        "threshold": 0.0,
        "reason_if_fail": "DXY 20d return not negative",
    },
    {
        "feature": "real_yield_change_20d",
        "operator": "<",
        "threshold": 0.0,
        "reason_if_fail": "real yield 20d change not negative",
    },
    {
        "feature": "etf_flow_tonnes_3m",
        "operator": ">",
        "threshold": 0.0,
        "reason_if_fail": "ETF 3m flow not positive",
    },
]

LEDGER_FIELDS = [
    "run_utc",
    "stage",
    "feature_date_utc",
    "sample_available_after_utc",
    "rule_id",
    "exact_rule_locked",
    "rule_confidence",
    "gold_sma20_over_50",
    "gold_sma20_over_50_pass",
    "dxy_ret_20d",
    "dxy_ret_20d_pass",
    "real_yield_change_20d",
    "real_yield_change_20d_pass",
    "etf_flow_tonnes_3m",
    "etf_flow_tonnes_3m_pass",
    "h64l_all_conditions_pass",
    "h64l_shadow_signal",
    "order_action",
    "mt5_signal_written",
    "demo_live_authorized",
    "event_guard_policy",
    "fail_reasons",
    "source_dataset",
    "operator_note",
]

CHECKLIST_FIELDS = [
    "feature_date_utc",
    "sample_available_after_utc",
    "feature",
    "value",
    "operator",
    "threshold",
    "pass",
    "fail_reason",
    "source_dataset",
]


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def expand(root: Path, value: str | Path | None) -> Optional[Path]:
    if value is None:
        return None
    p = Path(value).expanduser()
    if not p.is_absolute():
        p = root / p
    return p


def detect_separator(path: Path) -> str:
    with path.open("r", encoding="utf-8-sig", errors="replace") as f:
        line = f.readline()
    candidates = ["\t", ",", ";", "|"]
    counts = {sep: line.count(sep) for sep in candidates}
    return max(counts, key=counts.get) if max(counts.values()) > 0 else ","


def read_csv_rows(path: Path, max_rows: Optional[int] = None) -> Tuple[List[Dict[str, str]], List[str], str]:
    sep = detect_separator(path)
    rows: List[Dict[str, str]] = []
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.DictReader(f, delimiter=sep)
        fieldnames = list(reader.fieldnames or [])
        for i, row in enumerate(reader):
            rows.append({k: (v if v is not None else "") for k, v in row.items()})
            if max_rows is not None and i + 1 >= max_rows:
                break
    return rows, fieldnames, sep


def parse_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    s = str(x).strip()
    if s == "" or s.lower() in {"none", "nan", "null"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def evaluate_condition(value: Optional[float], operator: str, threshold: float) -> bool:
    if value is None:
        return False
    if operator == ">":
        return value > threshold
    if operator == "<":
        return value < threshold
    if operator == ">=":
        return value >= threshold
    if operator == "<=":
        return value <= threshold
    if operator == "==":
        return value == threshold
    raise ValueError(f"Unsupported operator: {operator}")


def pick_latest_row(rows: List[Dict[str, str]]) -> Dict[str, str]:
    if not rows:
        raise ValueError("Macro feature dataset has no rows")
    # Keep rows where at least one H64L feature is known; prefer latest by feature_date_utc/date_utc if present.
    candidates = []
    for row in rows:
        known = sum(parse_float(row.get(cond["feature"])) is not None for cond in CONDITIONS)
        if known > 0:
            candidates.append((row.get("feature_date_utc") or row.get("date_utc") or "", known, row))
    if not candidates:
        return rows[-1]
    candidates.sort(key=lambda t: (t[0], t[1]))
    return candidates[-1][2]


def load_rule(rule_path: Optional[Path]) -> Dict[str, Any]:
    default = {
        "rule_id": "H64L_MANUAL_SHADOW_RECONSTRUCTED_CONDITIONS_PENDING_STAGE64R_CONFIRMATION",
        "exact_rule_locked": False,
        "confidence": "MEDIUM_PENDING_STAGE64R_RAW_CONFIRMATION",
        "conditions": [f"{c['feature']} {c['operator']} {c['threshold']}" for c in CONDITIONS],
        "event_guard_policy": "GDELT/news guard only; simple 30-minute blackout around FOMC/NFP/CPI for rescue track.",
    }
    if rule_path and rule_path.exists():
        try:
            obj = json.loads(rule_path.read_text(encoding="utf-8"))
            default.update(obj)
        except Exception as exc:  # keep logger running
            default["rule_load_warning"] = str(exc)
    return default


def ensure_csv_with_header(path: Path, fields: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.stat().st_size == 0:
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()


def append_row(path: Path, fields: List[str], row: Dict[str, Any]) -> None:
    ensure_csv_with_header(path, fields)
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writerow({k: row.get(k, "") for k in fields})


def write_csv(path: Path, fields: List[str], rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def build_checklist(latest: Dict[str, str], dataset_path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    feature_date = latest.get("feature_date_utc") or latest.get("date_utc") or ""
    available_after = latest.get("sample_available_after_utc") or latest.get("available_after_utc") or ""
    checklist = []
    pass_map: Dict[str, bool] = {}
    values: Dict[str, Optional[float]] = {}
    fail_reasons = []
    for cond in CONDITIONS:
        value = parse_float(latest.get(cond["feature"]))
        ok = evaluate_condition(value, cond["operator"], cond["threshold"])
        pass_map[cond["feature"]] = ok
        values[cond["feature"]] = value
        if not ok:
            fail_reasons.append(cond["reason_if_fail"])
        checklist.append(
            {
                "feature_date_utc": feature_date,
                "sample_available_after_utc": available_after,
                "feature": cond["feature"],
                "value": "" if value is None else value,
                "operator": cond["operator"],
                "threshold": cond["threshold"],
                "pass": ok,
                "fail_reason": "" if ok else cond["reason_if_fail"],
                "source_dataset": str(dataset_path),
            }
        )
    all_pass = all(pass_map.values())
    summary = {
        "feature_date_utc": feature_date,
        "sample_available_after_utc": available_after,
        "values": values,
        "pass_map": pass_map,
        "all_pass": all_pass,
        "fail_reasons": "; ".join(fail_reasons),
    }
    return checklist, summary


def run_once(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    report_dir = expand(root, args.report_dir) or (root / DEFAULT_REPORT_DIR)
    dataset_path = expand(root, args.macro_dataset) or (root / DEFAULT_DATASET)
    ledger_path = expand(root, args.ledger_csv) or (root / DEFAULT_LEDGER)
    rule_path = expand(root, args.locked_rule_candidate) if args.locked_rule_candidate else (root / DEFAULT_RULE_CANDIDATE)

    if not dataset_path.exists():
        raise FileNotFoundError(f"Macro feature dataset not found: {dataset_path}")

    rows, columns, sep = read_csv_rows(dataset_path)
    latest = pick_latest_row(rows)
    rule = load_rule(rule_path)
    checklist, shadow = build_checklist(latest, dataset_path)

    run_utc = utc_now_iso()
    row = {
        "run_utc": run_utc,
        "stage": STAGE,
        "feature_date_utc": shadow["feature_date_utc"],
        "sample_available_after_utc": shadow["sample_available_after_utc"],
        "rule_id": rule.get("rule_id", ""),
        "exact_rule_locked": rule.get("exact_rule_locked", False),
        "rule_confidence": rule.get("confidence", rule.get("rule_confidence", "")),
        "gold_sma20_over_50": shadow["values"].get("gold_sma20_over_50"),
        "gold_sma20_over_50_pass": shadow["pass_map"].get("gold_sma20_over_50"),
        "dxy_ret_20d": shadow["values"].get("dxy_ret_20d"),
        "dxy_ret_20d_pass": shadow["pass_map"].get("dxy_ret_20d"),
        "real_yield_change_20d": shadow["values"].get("real_yield_change_20d"),
        "real_yield_change_20d_pass": shadow["pass_map"].get("real_yield_change_20d"),
        "etf_flow_tonnes_3m": shadow["values"].get("etf_flow_tonnes_3m"),
        "etf_flow_tonnes_3m_pass": shadow["pass_map"].get("etf_flow_tonnes_3m"),
        "h64l_all_conditions_pass": shadow["all_pass"],
        "h64l_shadow_signal": "YES" if shadow["all_pass"] else "NO",
        "order_action": "NONE_LOG_ONLY",
        "mt5_signal_written": False,
        "demo_live_authorized": False,
        "event_guard_policy": rule.get("event_guard_policy", "GDELT/news guard only"),
        "fail_reasons": shadow["fail_reasons"],
        "source_dataset": str(dataset_path),
        "operator_note": args.operator_note or "",
    }

    append_row(ledger_path, LEDGER_FIELDS, row)
    write_csv(report_dir / "stage171d_h64l_current_shadow_checklist.csv", CHECKLIST_FIELDS, checklist)
    # Also maintain a local copy of the ledger in the report folder for easy upload.
    report_ledger = report_dir / "stage171d_h64l_manual_shadow_log.csv"
    append_row(report_ledger, LEDGER_FIELDS, row)

    summary = {
        "stage": STAGE,
        "generated_utc": run_utc,
        "root": str(root),
        "order_routing_allowed": False,
        "demo_release_allowed": False,
        "status": "STAGE171D_COMPLETE_LOG_ONLY_SHADOW_RUN",
        "decision": DECISION_READY,
        "recommended_action": "CONTINUE_DAILY_SHADOW_LOGGING; NO_ORDER; CONFIRM_EXACT_STAGE64R_RULE_BEFORE_DEMO_BRIDGE",
        "macro_dataset": {
            "path": str(dataset_path),
            "exists": dataset_path.exists(),
            "separator": "tab" if sep == "\t" else sep,
            "columns": columns,
            "rows": len(rows),
        },
        "rule_candidate": {
            "path": str(rule_path) if rule_path else None,
            "exists": bool(rule_path and rule_path.exists()),
            "rule_id": rule.get("rule_id"),
            "exact_rule_locked": rule.get("exact_rule_locked", False),
            "confidence": rule.get("confidence", rule.get("rule_confidence", "")),
        },
        "current_shadow": {
            "feature_date_utc": shadow["feature_date_utc"],
            "sample_available_after_utc": shadow["sample_available_after_utc"],
            "condition_pass_map": shadow["pass_map"],
            "h64l_shadow_signal": "YES" if shadow["all_pass"] else "NO",
            "fail_reasons": shadow["fail_reasons"],
            "order_action": "NONE_LOG_ONLY",
        },
        "outputs": {
            "summary_json": str(report_dir / "stage171d_h64l_shadow_scheduler_summary.json"),
            "decision_md": str(report_dir / "stage171d_decision.md"),
            "current_checklist_csv": str(report_dir / "stage171d_h64l_current_shadow_checklist.csv"),
            "report_shadow_log_csv": str(report_ledger),
            "durable_shadow_log_csv": str(ledger_path),
        },
        "next": [
            "Keep daily manual shadow logging running; log-only, no orders.",
            "Confirm exact H64L Stage64R locked rule from archived configs/reports.",
            "If exact rule is confirmed and a real shadow hit occurs, request specialist approval for limited 0.01-lot demo bridge review.",
        ],
    }

    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "stage171d_h64l_shadow_scheduler_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    decision_md = f"""# Stage171D H64L Shadow Scheduler and Logger

Generated UTC: `{run_utc}`

Decision: `{DECISION_READY}`
Recommended action: `CONTINUE_DAILY_SHADOW_LOGGING; NO_ORDER; CONFIRM_EXACT_STAGE64R_RULE_BEFORE_DEMO_BRIDGE`

## Scope

This is a scheduled/manual shadow logging stage. It creates no MT5 order signal, writes no execution instruction, and authorizes no demo/live order.

## Current H64L checklist

| feature | value | pass |
|---|---:|---:|
| gold_sma20_over_50 | {row['gold_sma20_over_50']} | {row['gold_sma20_over_50_pass']} |
| dxy_ret_20d | {row['dxy_ret_20d']} | {row['dxy_ret_20d_pass']} |
| real_yield_change_20d | {row['real_yield_change_20d']} | {row['real_yield_change_20d_pass']} |
| etf_flow_tonnes_3m | {row['etf_flow_tonnes_3m']} | {row['etf_flow_tonnes_3m_pass']} |

H64L shadow signal: `{row['h64l_shadow_signal']}`
Order action: `{row['order_action']}`

Fail reasons: `{row['fail_reasons']}`

## Outputs

- Durable log: `{ledger_path}`
- Report log: `{report_ledger}`
- Current checklist: `{report_dir / 'stage171d_h64l_current_shadow_checklist.csv'}`

## Next

Keep this scheduled daily. Do not bridge to demo until exact Stage64R rule evidence is confirmed and a real shadow hit appears.
"""
    (report_dir / "stage171d_decision.md").write_text(decision_md, encoding="utf-8")

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def write_launchd_plist(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    plist_path = Path(args.plist_path).expanduser() if args.plist_path else Path.home() / "Library/LaunchAgents/com.xauusd.stage171d.h64l-shadow.plist"
    python_path = args.python_path or sys.executable or "/usr/bin/python3"
    script_path = root / "app/stage171d_h64l_shadow_scheduler_and_logger.py"
    program_args = [
        python_path,
        str(script_path),
        "run-once",
        "--root",
        str(root),
        "--macro-dataset",
        str(root / DEFAULT_DATASET),
        "--locked-rule-candidate",
        str(root / DEFAULT_RULE_CANDIDATE),
        "--ledger-csv",
        str(root / DEFAULT_LEDGER),
        "--operator-note",
        "launchd_daily_shadow_run",
    ]
    out_dir = root / DEFAULT_REPORT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    plist = {
        "Label": args.label,
        "ProgramArguments": program_args,
        "WorkingDirectory": str(root),
        "StartCalendarInterval": {"Hour": int(args.hour), "Minute": int(args.minute)},
        "StandardOutPath": str(out_dir / "stage171d_launchd_stdout.log"),
        "StandardErrorPath": str(out_dir / "stage171d_launchd_stderr.log"),
        "RunAtLoad": bool(args.run_at_load),
    }
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    with plist_path.open("wb") as f:
        plistlib.dump(plist, f, sort_keys=False)
    summary = {
        "stage": STAGE,
        "generated_utc": utc_now_iso(),
        "decision": "STAGE171D_LAUNCHD_PLIST_WRITTEN_LOAD_MANUALLY",
        "plist_path": str(plist_path),
        "label": args.label,
        "hour": int(args.hour),
        "minute": int(args.minute),
        "load_command": f"launchctl load {plist_path}",
        "unload_command": f"launchctl unload {plist_path}",
        "note": "This writes a local macOS LaunchAgent only. It does not authorize trades.",
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Stage171D H64L shadow scheduler/logger")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run-once", help="Evaluate current H64L checklist and append log-only shadow row")
    p_run.add_argument("--root", default="~/Desktop/xauusd-trader")
    p_run.add_argument("--macro-dataset", default=DEFAULT_DATASET)
    p_run.add_argument("--locked-rule-candidate", default=DEFAULT_RULE_CANDIDATE)
    p_run.add_argument("--ledger-csv", default=DEFAULT_LEDGER)
    p_run.add_argument("--report-dir", default=DEFAULT_REPORT_DIR)
    p_run.add_argument("--operator-note", default="")
    p_run.set_defaults(func=run_once)

    p_plist = sub.add_parser("write-launchd-plist", help="Write macOS launchd plist for daily local shadow logging")
    p_plist.add_argument("--root", default="~/Desktop/xauusd-trader")
    p_plist.add_argument("--plist-path", default="~/Library/LaunchAgents/com.xauusd.stage171d.h64l-shadow.plist")
    p_plist.add_argument("--label", default="com.xauusd.stage171d.h64l-shadow")
    p_plist.add_argument("--hour", type=int, default=9)
    p_plist.add_argument("--minute", type=int, default=15)
    p_plist.add_argument("--python-path", default="")
    p_plist.add_argument("--run-at-load", action="store_true")
    p_plist.set_defaults(func=write_launchd_plist)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
