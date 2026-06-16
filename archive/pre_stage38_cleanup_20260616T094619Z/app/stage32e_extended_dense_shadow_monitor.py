"""
Stage32E — Extended Dense Shadow Monitor for XAUUSD.

Purpose:
- Convert the Stage32D tightening plan into an operational extended-shadow focus queue.
- Keep the leading dense forward candidate under collection until the extended sample threshold is met.
- Suppress weak sibling variants from primary focus so forward sample production is not diluted.
- Identify a pre-commercial robustness queue only after extended sample and stability thresholds are met.

Inputs by default:
- data/reports/stage32d_dense_forward_review/dense_variant_tightening_plan.csv
- data/reports/stage32d_dense_forward_review/dense_review_candidate_diagnostics.csv
- data/reports/stage32d_dense_forward_review/dense_family_action_plan.csv
- data/reports/stage32d_dense_forward_review/stage32d_summary.json
- data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_signal_ledger.csv

Outputs:
- data/reports/stage32e_extended_dense_shadow_monitor/stage32e_extended_dense_shadow_monitor.md
- data/reports/stage32e_extended_dense_shadow_monitor/extended_shadow_focus_queue.csv/json
- data/reports/stage32e_extended_dense_shadow_monitor/suppressed_variant_plan.csv/json
- data/reports/stage32e_extended_dense_shadow_monitor/pre_commercial_robustness_queue.csv/json
- data/reports/stage32e_extended_dense_shadow_monitor/stage32e_summary.json

Safety:
- Research/shadow only.
- No EA changes.
- No paper/live.
- No order authorization.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

COMMERCIAL_GOAL = "FASTEST_SAFE_PATH_TO_COMMERCIALLY_USABLE_SYSTEM"
ROOT = Path.cwd()
REPORT_ROOT = ROOT / "data" / "reports"
STAGE32C_DIR = REPORT_ROOT / "stage32c_dense_forward_shadow_tracker"
STAGE32D_DIR = REPORT_ROOT / "stage32d_dense_forward_review"
OUT_DIR = REPORT_ROOT / "stage32e_extended_dense_shadow_monitor"

DEFAULT_TIGHTENING_PLAN = STAGE32D_DIR / "dense_variant_tightening_plan.csv"
DEFAULT_DIAGNOSTICS = STAGE32D_DIR / "dense_review_candidate_diagnostics.csv"
DEFAULT_FAMILY_PLAN = STAGE32D_DIR / "dense_family_action_plan.csv"
DEFAULT_STAGE32D_SUMMARY = STAGE32D_DIR / "stage32d_summary.json"
DEFAULT_LEDGER = STAGE32C_DIR / "dense_forward_signal_ledger.csv"

DEFAULT_EXTENDED_MIN_SIGNALS = int(os.getenv("STAGE32E_EXTENDED_MIN_SIGNALS", "40"))
DEFAULT_MIN_PF_X4 = float(os.getenv("STAGE32E_MIN_PF_X4", "1.25"))
DEFAULT_MIN_WIN_RATE = float(os.getenv("STAGE32E_MIN_WIN_RATE", "0.55"))
DEFAULT_MIN_AVG_NET_X4 = float(os.getenv("STAGE32E_MIN_AVG_NET_X4", "0"))
DEFAULT_MIN_TAIL_PF_X4 = float(os.getenv("STAGE32E_MIN_TAIL_PF_X4", "1.0"))
DEFAULT_MAX_ALLOWED_DD_X4 = float(os.getenv("STAGE32E_MAX_ALLOWED_DD_X4", "-30"))

PRIMARY_ACTION = "KEEP_PRIMARY_EXTENDED_SHADOW_COLLECT_TO_40"
ACCELERATE_ACTION = "ACCELERATE_FORWARD_SAMPLE_COLLECTION"
SECONDARY_ACTION = "KEEP_SECONDARY_COLLECTION"
PAUSE_ACTION_PREFIX = "PAUSE_PRIMARY_SHADOW"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def ensure_dirs() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)


def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    try:
        text = str(value).strip().replace(",", "")
        if not text or text.lower() in {"nan", "none", "null"}:
            return default
        val = float(text)
        if math.isnan(val) or math.isinf(val):
            return default
        return val
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    val = safe_float(value)
    if val is None:
        return default
    return int(round(val))


def read_csv(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        keys: List[str] = []
        seen = set()
        for row in rows:
            for key in row.keys():
                if key not in seen:
                    seen.add(key)
                    keys.append(key)
        fieldnames = keys or ["empty"]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}


def parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text.replace(" ", "T"))
    except Exception:
        return None


def ledger_stats(ledger_rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in ledger_rows:
        cand = str(row.get("candidate") or "").strip()
        if cand:
            groups[cand].append(row)
    out: Dict[str, Dict[str, Any]] = {}
    for cand, rows in groups.items():
        dates = [parse_dt(r.get("entry_time")) for r in rows]
        dates = [d for d in dates if d is not None]
        net_vals = [safe_float(r.get("net_x4")) for r in rows if str(r.get("outcome_status") or "") == "RESOLVED_M1_REPLAY_SHADOW"]
        vals = [float(v) for v in net_vals if v is not None]
        pos = sum(v for v in vals if v > 0)
        neg = -sum(v for v in vals if v < 0)
        pf = (pos / neg) if neg else (float("inf") if pos > 0 else 0.0)
        out[cand] = {
            "ledger_signal_rows": len(rows),
            "ledger_resolved_rows": len(vals),
            "ledger_first_signal_ts": min(dates).isoformat() if dates else "",
            "ledger_latest_signal_ts": max(dates).isoformat() if dates else "",
            "ledger_unique_signal_dates": len({d.date().isoformat() for d in dates}),
            "ledger_pf_x4": round(pf, 6) if math.isfinite(pf) else "inf",
            "ledger_avg_net_x4": round(sum(vals) / len(vals), 6) if vals else 0.0,
        }
    return out


def indexed(rows: List[Dict[str, Any]], key: str = "candidate") -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        val = str(row.get(key) or "").strip()
        if val and val not in out:
            out[val] = row
    return out


def metrics_pass(diag: Dict[str, Any], args: argparse.Namespace, signal_count: int) -> Tuple[bool, List[str]]:
    failures: List[str] = []
    pf_x4 = safe_float(diag.get("pf_x4"), 0.0) or 0.0
    avg_net = safe_float(diag.get("avg_net_x4"), 0.0) or 0.0
    wr = safe_float(diag.get("win_rate_x4"), 0.0) or 0.0
    tail_pf = safe_float(diag.get("tail_pf_x4"), 0.0) or 0.0
    dd = safe_float(diag.get("max_drawdown_x4"), 0.0) or 0.0
    if signal_count < int(args.extended_min_signals):
        failures.append("EXTENDED_SAMPLE_COUNT_BELOW_THRESHOLD")
    if pf_x4 < float(args.min_pf_x4):
        failures.append("PF_BELOW_THRESHOLD")
    if avg_net <= float(args.min_avg_net_x4):
        failures.append("AVG_NET_NOT_POSITIVE")
    if wr < float(args.min_win_rate):
        failures.append("WIN_RATE_BELOW_THRESHOLD")
    if tail_pf < float(args.min_tail_pf_x4):
        failures.append("TAIL_PF_BELOW_THRESHOLD")
    if dd < float(args.max_allowed_drawdown_x4):
        failures.append("DRAWDOWN_BEYOND_LIMIT")
    return (len(failures) == 0), failures


def build_focus_and_suppression(
    plan_rows: List[Dict[str, Any]],
    diag_rows: List[Dict[str, Any]],
    ledger_rows: List[Dict[str, Any]],
    args: argparse.Namespace,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    diag_by_candidate = indexed(diag_rows)
    ledger_by_candidate = ledger_stats(ledger_rows)
    focus_rows: List[Dict[str, Any]] = []
    suppressed_rows: List[Dict[str, Any]] = []
    pre_commercial_rows: List[Dict[str, Any]] = []

    for row in plan_rows:
        cand = str(row.get("candidate") or "").strip()
        if not cand:
            continue
        action = str(row.get("action") or "").strip()
        family = str(row.get("family") or "").strip()
        diag = diag_by_candidate.get(cand, {})
        signal_count = safe_int(row.get("signal_count") or diag.get("signal_count"), 0)
        remaining = max(0, int(args.extended_min_signals) - signal_count)
        passed, failures = metrics_pass(diag, args, signal_count)
        ledger_stats_row = ledger_by_candidate.get(cand, {})

        base = {
            "candidate": cand,
            "family": family,
            "stage32d_action": action,
            "signal_count": signal_count,
            "extended_min_signals": int(args.extended_min_signals),
            "remaining_to_extended_min": remaining,
            "pf_x4": diag.get("pf_x4", ""),
            "avg_net_x4": diag.get("avg_net_x4", ""),
            "win_rate_x4": diag.get("win_rate_x4", ""),
            "tail_pf_x4": diag.get("tail_pf_x4", ""),
            "max_drawdown_x4": diag.get("max_drawdown_x4", ""),
            "stage32d_decision": diag.get("stage32d_decision", ""),
            "ledger_latest_signal_ts": ledger_stats_row.get("ledger_latest_signal_ts", ""),
            "ledger_unique_signal_dates": ledger_stats_row.get("ledger_unique_signal_dates", ""),
            "metric_failures": ";".join(failures),
            "commercial_status": "RESEARCH_SHADOW_ONLY_NO_EA_NO_PAPER_LIVE",
        }

        if action == PRIMARY_ACTION:
            base.update({
                "priority": 1,
                "monitor_role": "PRIMARY_EXTENDED_SHADOW",
                "next_action": "KEEP_COLLECTING_UNTIL_40_RESOLVED_SAMPLES",
                "review_after": "RERUN_STAGE32D_AND_STAGE32E_AFTER_EACH_DATA_REFRESH",
            })
            focus_rows.append(base)
        elif action == ACCELERATE_ACTION:
            base.update({
                "priority": 2,
                "monitor_role": "PROMISING_LOW_N_ACCELERATION",
                "next_action": "KEEP_COLLECTING_UNTIL_MIN_REVIEW_SAMPLES_THEN_STAGE32D",
                "review_after": "RERUN_AFTER_NEW_AMARKETS_DATA",
            })
            focus_rows.append(base)
        elif action == SECONDARY_ACTION:
            base.update({
                "priority": 3,
                "monitor_role": "SECONDARY_COLLECTION",
                "next_action": "KEEP_AS_SECONDARY_ONLY_UNTIL_METRICS_IMPROVE",
                "review_after": "RERUN_AFTER_NEW_AMARKETS_DATA",
            })
            focus_rows.append(base)
        elif action.startswith(PAUSE_ACTION_PREFIX) or "PAUSE" in action:
            base.update({
                "suppression_role": "SUPPRESS_FROM_PRIMARY_EXTENDED_SHADOW",
                "next_action": "MOVE_TO_REPAIR_QUEUE_TEST_INVERSION_HOUR_SUPPRESSION_OVERLAP",
            })
            suppressed_rows.append(base)
        else:
            base.update({
                "priority": 9,
                "monitor_role": "BACKGROUND_COLLECTION",
                "next_action": "KEEP_BACKGROUND_ONLY",
                "review_after": "ONLY_IF_SIGNAL_DENSITY_OR_METRICS_IMPROVE",
            })
            focus_rows.append(base)

        if passed:
            pre = dict(base)
            pre.update({
                "pre_commercial_gate_status": "PRE_COMMERCIAL_ROBUSTNESS_QUEUE_RESEARCH_ONLY",
                "required_next_stage": "RUN_PRE_COMMERCIAL_ROBUSTNESS_GATE_BEFORE_ANY_PAPER_LIVE_DISCUSSION",
            })
            pre_commercial_rows.append(pre)

    focus_rows.sort(key=lambda r: (int(r.get("priority", 9)), -int(r.get("signal_count") or 0), str(r.get("candidate"))))
    suppressed_rows.sort(key=lambda r: (str(r.get("family")), str(r.get("candidate"))))
    pre_commercial_rows.sort(key=lambda r: (-int(r.get("signal_count") or 0), str(r.get("candidate"))))
    return focus_rows, suppressed_rows, pre_commercial_rows


def markdown_table(rows: List[Dict[str, Any]], cols: Sequence[str], limit: int = 30) -> List[str]:
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for row in rows[:limit]:
        vals = [str(row.get(c, "")).replace("|", "\\|").replace("\n", " ") for c in cols]
        lines.append("| " + " | ".join(vals) + " |")
    return lines


def write_report(summary: Dict[str, Any], focus_rows: List[Dict[str, Any]], suppressed_rows: List[Dict[str, Any]], pre_rows: List[Dict[str, Any]]) -> None:
    lines: List[str] = []
    lines.append("# XAUUSD Stage32E — Extended Dense Shadow Monitor\n")
    lines.append(f"Generated UTC: {summary['generated_utc']}\n")
    lines.append("## Decision\n")
    lines.append("```text")
    for key in ["decision", "execution_status", "no_ea_change", "no_paper_live", "no_order_authorization", "commercial_goal", "primary_objective"]:
        lines.append(f"{key.upper()} = {summary.get(key)}")
    lines.append("```\n")
    lines.append("## Why this stage exists\n")
    lines.append("Stage32D found one reviewable candidate that still needs extended shadow, plus two promising low-N siblings. Stage32E turns that plan into a repeatable monitor so the project keeps collecting the samples needed for the fastest safe commercial path without prematurely authorizing EA, paper/live, or orders.\n")
    lines.append("## Summary\n")
    lines.append("```text")
    for key in [
        "leading_candidate", "focus_queue_rows", "primary_extended_rows", "promising_low_n_rows", "secondary_collection_rows",
        "suppressed_variant_rows", "pre_commercial_robustness_queue_rows", "extended_min_signals", "leading_remaining_to_extended_min",
    ]:
        lines.append(f"{key} = {summary.get(key)}")
    lines.append("```\n")
    lines.append("## Extended shadow focus queue\n")
    if focus_rows:
        lines.extend(markdown_table(focus_rows, ["priority", "monitor_role", "candidate", "family", "signal_count", "remaining_to_extended_min", "pf_x4", "win_rate_x4", "tail_pf_x4", "max_drawdown_x4", "next_action"], limit=40))
    else:
        lines.append("No extended shadow focus candidates.\n")
    lines.append("\n## Suppressed / repair queue\n")
    if suppressed_rows:
        lines.extend(markdown_table(suppressed_rows, ["candidate", "family", "signal_count", "pf_x4", "avg_net_x4", "win_rate_x4", "tail_pf_x4", "max_drawdown_x4", "next_action"], limit=40))
    else:
        lines.append("No suppressed variants.\n")
    lines.append("\n## Pre-commercial robustness queue\n")
    if pre_rows:
        lines.extend(markdown_table(pre_rows, ["candidate", "family", "signal_count", "pf_x4", "avg_net_x4", "win_rate_x4", "tail_pf_x4", "max_drawdown_x4", "required_next_stage"], limit=20))
    else:
        lines.append("No candidate has met extended sample/stability thresholds yet.\n")
    lines.append("\n## Operational interpretation\n")
    lines.append("```text")
    lines.append("1. Continue active/shadow observation and Stage32C/32D/32E after each AMarkets data refresh.")
    lines.append("2. Keep the leading candidate in extended shadow until at least 40 resolved samples are reached.")
    lines.append("3. Suppress weak siblings from primary attention; repair/inversion tests can run later but should not dilute the fast path.")
    lines.append("4. No EA/paper/live/order transition is authorized by this stage.")
    lines.append("```\n")
    lines.append("## Output files\n")
    for p in [
        OUT_DIR / "stage32e_extended_dense_shadow_monitor.md",
        OUT_DIR / "extended_shadow_focus_queue.csv",
        OUT_DIR / "suppressed_variant_plan.csv",
        OUT_DIR / "pre_commercial_robustness_queue.csv",
        OUT_DIR / "stage32e_summary.json",
    ]:
        lines.append(f"- `{rel(p)}`")
    (OUT_DIR / "stage32e_extended_dense_shadow_monitor.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Stage32E extended dense shadow monitor.")
    parser.add_argument("--tightening-plan", default=os.getenv("STAGE32E_TIGHTENING_PLAN", str(DEFAULT_TIGHTENING_PLAN)))
    parser.add_argument("--diagnostics", default=os.getenv("STAGE32E_DIAGNOSTICS", str(DEFAULT_DIAGNOSTICS)))
    parser.add_argument("--family-plan", default=os.getenv("STAGE32E_FAMILY_PLAN", str(DEFAULT_FAMILY_PLAN)))
    parser.add_argument("--stage32d-summary", default=os.getenv("STAGE32E_STAGE32D_SUMMARY", str(DEFAULT_STAGE32D_SUMMARY)))
    parser.add_argument("--ledger", default=os.getenv("STAGE32E_LEDGER", str(DEFAULT_LEDGER)))
    parser.add_argument("--extended-min-signals", type=int, default=DEFAULT_EXTENDED_MIN_SIGNALS)
    parser.add_argument("--min-pf-x4", type=float, default=DEFAULT_MIN_PF_X4)
    parser.add_argument("--min-win-rate", type=float, default=DEFAULT_MIN_WIN_RATE)
    parser.add_argument("--min-avg-net-x4", type=float, default=DEFAULT_MIN_AVG_NET_X4)
    parser.add_argument("--min-tail-pf-x4", type=float, default=DEFAULT_MIN_TAIL_PF_X4)
    parser.add_argument("--max-allowed-drawdown-x4", type=float, default=DEFAULT_MAX_ALLOWED_DD_X4)
    return parser.parse_args(argv)


def run(args: Optional[argparse.Namespace] = None) -> Dict[str, Any]:
    ensure_dirs()
    args = args or parse_args()
    generated_utc = iso(utc_now())
    plan_path = Path(args.tightening_plan)
    diag_path = Path(args.diagnostics)
    family_plan_path = Path(args.family_plan)
    stage32d_summary_path = Path(args.stage32d_summary)
    ledger_path = Path(args.ledger)

    plan_rows = read_csv(plan_path)
    diag_rows = read_csv(diag_path)
    family_plan_rows = read_csv(family_plan_path)
    stage32d_summary = read_json(stage32d_summary_path)
    ledger_rows = read_csv(ledger_path)

    base_summary: Dict[str, Any] = {
        "generated_utc": generated_utc,
        "execution_status": "RESEARCH_SHADOW_ONLY",
        "no_ea_change": True,
        "no_paper_live": True,
        "no_order_authorization": True,
        "commercial_goal": COMMERCIAL_GOAL,
        "primary_objective": "EXTENDED_DENSE_SHADOW_COLLECTION_WITH_WEAK_SIBLING_SUPPRESSION",
        "tightening_plan_path": rel(plan_path),
        "diagnostics_path": rel(diag_path),
        "family_plan_path": rel(family_plan_path),
        "stage32d_summary_path": rel(stage32d_summary_path),
        "ledger_path": rel(ledger_path),
        "tightening_plan_rows": len(plan_rows),
        "diagnostic_rows": len(diag_rows),
        "family_plan_rows": len(family_plan_rows),
        "ledger_rows": len(ledger_rows),
        "extended_min_signals": int(args.extended_min_signals),
        "min_pf_x4": float(args.min_pf_x4),
        "min_win_rate": float(args.min_win_rate),
        "min_avg_net_x4": float(args.min_avg_net_x4),
        "min_tail_pf_x4": float(args.min_tail_pf_x4),
        "max_allowed_drawdown_x4": float(args.max_allowed_drawdown_x4),
        "stage32d_decision": stage32d_summary.get("decision", ""),
        "commercial_transition_authorized": False,
    }

    if not plan_rows or not diag_rows:
        summary = dict(base_summary)
        summary.update({
            "decision": "STAGE32E_BLOCKED_MISSING_STAGE32D_INPUTS_RESEARCH_ONLY",
            "leading_candidate": stage32d_summary.get("leading_candidate", ""),
            "focus_queue_rows": 0,
            "primary_extended_rows": 0,
            "promising_low_n_rows": 0,
            "secondary_collection_rows": 0,
            "suppressed_variant_rows": 0,
            "pre_commercial_robustness_queue_rows": 0,
            "leading_remaining_to_extended_min": "",
            "error": "Missing Stage32D tightening plan or diagnostics",
        })
        write_json(OUT_DIR / "stage32e_summary.json", summary)
        write_report(summary, [], [], [])
        return summary

    focus_rows, suppressed_rows, pre_rows = build_focus_and_suppression(plan_rows, diag_rows, ledger_rows, args)
    primary_rows = [r for r in focus_rows if r.get("monitor_role") == "PRIMARY_EXTENDED_SHADOW"]
    promising_rows = [r for r in focus_rows if r.get("monitor_role") == "PROMISING_LOW_N_ACCELERATION"]
    secondary_rows = [r for r in focus_rows if r.get("monitor_role") == "SECONDARY_COLLECTION"]
    leading_candidate = str(stage32d_summary.get("leading_candidate") or (primary_rows[0].get("candidate") if primary_rows else ""))
    leading_remaining = ""
    for row in focus_rows:
        if row.get("candidate") == leading_candidate:
            leading_remaining = row.get("remaining_to_extended_min", "")
            break

    if pre_rows:
        decision = "STAGE32E_HAS_PRE_COMMERCIAL_ROBUSTNESS_QUEUE_RESEARCH_ONLY"
    elif primary_rows:
        decision = "STAGE32E_EXTENDED_DENSE_SHADOW_ACTIVE_RESEARCH_ONLY"
    elif promising_rows:
        decision = "STAGE32E_PROMISING_LOW_N_COLLECTION_ACTIVE_RESEARCH_ONLY"
    else:
        decision = "STAGE32E_NO_EXTENDED_SHADOW_FOCUS_RESEARCH_ONLY"

    summary = dict(base_summary)
    summary.update({
        "decision": decision,
        "leading_candidate": leading_candidate,
        "focus_queue_rows": len(focus_rows),
        "primary_extended_rows": len(primary_rows),
        "promising_low_n_rows": len(promising_rows),
        "secondary_collection_rows": len(secondary_rows),
        "suppressed_variant_rows": len(suppressed_rows),
        "pre_commercial_robustness_queue_rows": len(pre_rows),
        "leading_remaining_to_extended_min": leading_remaining,
        "commercial_transition_authorized": False,
    })

    write_csv(OUT_DIR / "extended_shadow_focus_queue.csv", focus_rows)
    write_json(OUT_DIR / "extended_shadow_focus_queue.json", focus_rows)
    write_csv(OUT_DIR / "suppressed_variant_plan.csv", suppressed_rows)
    write_json(OUT_DIR / "suppressed_variant_plan.json", suppressed_rows)
    write_csv(OUT_DIR / "pre_commercial_robustness_queue.csv", pre_rows)
    write_json(OUT_DIR / "pre_commercial_robustness_queue.json", pre_rows)
    write_json(OUT_DIR / "stage32e_summary.json", summary)
    write_report(summary, focus_rows, suppressed_rows, pre_rows)
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    summary = run(args)
    print(summary.get("decision"))
    print(f"report={rel(OUT_DIR / 'stage32e_extended_dense_shadow_monitor.md')}")
    print(f"focus_queue={rel(OUT_DIR / 'extended_shadow_focus_queue.csv')}")
    print(f"suppressed={rel(OUT_DIR / 'suppressed_variant_plan.csv')}")
    return 0 if "ERROR" not in str(summary.get("decision")) and "BLOCKED" not in str(summary.get("decision")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
