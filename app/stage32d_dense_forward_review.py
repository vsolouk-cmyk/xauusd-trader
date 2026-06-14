"""
Stage32D — Dense Forward Review / Tightening Plan for XAUUSD.

Purpose:
- Inspect Stage32C dense forward-shadow candidates that reached the research review queue.
- Separate "reviewable for extended shadow" from "commercially usable".
- Produce a practical tightening/suppression plan so forward sample production focuses on the fastest safe path.

Inputs by default:
- data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_candidate_summary.csv
- data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_family_summary.csv
- data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_signal_ledger.csv
- data/reports/stage32c_dense_forward_shadow_tracker/stage32c_summary.json

Outputs:
- data/reports/stage32d_dense_forward_review/stage32d_dense_forward_review.md
- data/reports/stage32d_dense_forward_review/dense_review_candidate_diagnostics.csv/json
- data/reports/stage32d_dense_forward_review/dense_variant_tightening_plan.csv/json
- data/reports/stage32d_dense_forward_review/dense_family_action_plan.csv/json
- data/reports/stage32d_dense_forward_review/stage32d_summary.json

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
OUT_DIR = REPORT_ROOT / "stage32d_dense_forward_review"

DEFAULT_CANDIDATE_SUMMARY = STAGE32C_DIR / "dense_forward_candidate_summary.csv"
DEFAULT_FAMILY_SUMMARY = STAGE32C_DIR / "dense_forward_family_summary.csv"
DEFAULT_LEDGER = STAGE32C_DIR / "dense_forward_signal_ledger.csv"
DEFAULT_STAGE32C_SUMMARY = STAGE32C_DIR / "stage32c_summary.json"

DEFAULT_MIN_REVIEW_SIGNALS = int(os.getenv("STAGE32D_MIN_REVIEW_SIGNALS", "20"))
DEFAULT_EXTENDED_MIN_SIGNALS = int(os.getenv("STAGE32D_EXTENDED_MIN_SIGNALS", "40"))
DEFAULT_MIN_PF_X4 = float(os.getenv("STAGE32D_MIN_PF_X4", "1.25"))
DEFAULT_MIN_WIN_RATE = float(os.getenv("STAGE32D_MIN_WIN_RATE", "0.55"))
DEFAULT_MIN_AVG_NET_X4 = float(os.getenv("STAGE32D_MIN_AVG_NET_X4", "0"))
DEFAULT_TAIL_N = int(os.getenv("STAGE32D_TAIL_N", "10"))
DEFAULT_MAX_ALLOWED_DD_X4 = float(os.getenv("STAGE32D_MAX_ALLOWED_DD_X4", "-30"))


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
        if not text or text.lower() in {"nan", "none", "null", "inf", "infinity"}:
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
    return int(val)


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


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")


def parse_dt_text(value: Any) -> str:
    return str(value or "").strip()


def sort_key_dt(row: Dict[str, Any]) -> str:
    return parse_dt_text(row.get("entry_time") or row.get("latest_signal_ts") or "")


def pf(values: Sequence[float]) -> float:
    vals = [float(x) for x in values if math.isfinite(float(x))]
    if not vals:
        return 0.0
    pos = sum(x for x in vals if x > 0)
    neg = -sum(x for x in vals if x < 0)
    if neg == 0:
        return float("inf") if pos > 0 else 0.0
    return pos / neg


def max_drawdown(values: Sequence[float]) -> float:
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for value in values:
        equity += float(value)
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return worst


def max_losing_streak(values: Sequence[float]) -> int:
    cur = 0
    worst = 0
    for value in values:
        if float(value) < 0:
            cur += 1
            worst = max(worst, cur)
        else:
            cur = 0
    return worst


def unique_dates(rows: List[Dict[str, Any]]) -> int:
    dates = set()
    for row in rows:
        text = parse_dt_text(row.get("entry_time"))
        if len(text) >= 10:
            dates.add(text[:10])
    return len(dates)


def summarize_subset(rows: List[Dict[str, Any]], label: str) -> Dict[str, Any]:
    resolved = [r for r in rows if str(r.get("outcome_status")) == "RESOLVED_M1_REPLAY_SHADOW"]
    vals = [safe_float(r.get("net_x4")) for r in resolved]
    nets = [float(v) for v in vals if v is not None]
    return {
        f"{label}_count": len(resolved),
        f"{label}_pf_x4": round(pf(nets), 6) if math.isfinite(pf(nets)) else "inf",
        f"{label}_avg_net_x4": round(sum(nets) / len(nets), 6) if nets else 0.0,
        f"{label}_win_rate_x4": round(sum(1 for v in nets if v > 0) / len(nets), 6) if nets else 0.0,
    }


def decision_for_candidate(row: Dict[str, Any], diag: Dict[str, Any], args: argparse.Namespace) -> Tuple[str, str]:
    signals = safe_int(diag.get("signal_count"))
    pf_x4 = safe_float(diag.get("pf_x4"), 0.0) or 0.0
    avg = safe_float(diag.get("avg_net_x4"), 0.0) or 0.0
    wr = safe_float(diag.get("win_rate_x4"), 0.0) or 0.0
    tail_pf = safe_float(diag.get("tail_pf_x4"), 0.0) or 0.0
    tail_avg = safe_float(diag.get("tail_avg_net_x4"), 0.0) or 0.0
    dd = safe_float(diag.get("max_drawdown_x4"), 0.0) or 0.0
    readiness = str(row.get("readiness") or "")

    metric_pass = pf_x4 >= args.min_pf_x4 and avg > args.min_avg_net_x4 and wr >= args.min_win_rate
    tail_pass = signals < args.tail_n or tail_pf >= 1.0 and tail_avg >= 0
    dd_pass = dd >= args.max_allowed_drawdown_x4

    if signals >= args.extended_min_signals and metric_pass and tail_pass and dd_pass:
        return (
            "EXTENDED_REVIEW_READY_RESEARCH_ONLY",
            "Has enough dense forward samples and passes preliminary stability checks; still research/shadow only.",
        )
    if signals >= args.min_review_signals and metric_pass and dd_pass:
        return (
            "NEEDS_EXTENDED_DENSE_SHADOW_BEFORE_COMMERCIAL_REVIEW",
            f"Reviewable, but only {signals} samples; continue until at least {args.extended_min_signals} resolved samples.",
        )
    if "DENSE_FORWARD_REVIEW_QUEUE" in readiness:
        return (
            "REVIEW_FLAG_BUT_METRIC_WEAK_RECHECK",
            "Stage32C flagged it for review, but Stage32D stability thresholds are not fully satisfied.",
        )
    if signals > 0 and pf_x4 >= 1.5 and avg > 0:
        return (
            "PROMISING_LOW_N_ACCELERATE_COLLECTION",
            "Promising but below minimum review sample count; keep in dense collection.",
        )
    if signals > 0 and pf_x4 < 0.9 and avg < 0:
        return (
            "PAUSE_OR_REPAIR_BEFORE_PRIMARY_SHADOW",
            "Negative forward performance; do not keep as primary unless repaired or inverted thesis is tested.",
        )
    return (
        "KEEP_COLLECTING_OR_REPAIR_RESEARCH_ONLY",
        "No commercial action; keep collecting only if family remains useful for supply.",
    )


def diagnose_candidates(candidate_rows: List[Dict[str, Any]], ledger_rows: List[Dict[str, Any]], args: argparse.Namespace) -> List[Dict[str, Any]]:
    by_candidate: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in ledger_rows:
        by_candidate[str(row.get("candidate") or "UNKNOWN")].append(row)

    out: List[Dict[str, Any]] = []
    for row in candidate_rows:
        cand = str(row.get("candidate") or "UNKNOWN")
        rows = sorted(by_candidate.get(cand, []), key=sort_key_dt)
        resolved = [r for r in rows if str(r.get("outcome_status")) == "RESOLVED_M1_REPLAY_SHADOW"]
        nets_raw = [safe_float(r.get("net_x4")) for r in resolved]
        nets = [float(x) for x in nets_raw if x is not None]
        tail_nets = nets[-int(args.tail_n):]
        directions = defaultdict(list)
        hours = defaultdict(int)
        exit_counts = defaultdict(int)
        for r in resolved:
            directions[str(r.get("direction") or "")].append(r)
            hour = str(r.get("entry_hour") or "")
            if not hour:
                text = parse_dt_text(r.get("entry_time"))
                hour = text[11:13] if len(text) >= 13 else ""
            hours[hour] += 1
            exit_counts[str(r.get("exit_reason") or "")] += 1

        diag: Dict[str, Any] = {
            "candidate": cand,
            "family": row.get("family", ""),
            "signal_count": safe_int(row.get("signal_count"), len(rows)),
            "resolved_count": len(resolved),
            "first_signal_ts": sort_key_dt(rows[0]) if rows else "",
            "latest_signal_ts": row.get("latest_signal_ts") or (sort_key_dt(rows[-1]) if rows else ""),
            "days_active": unique_dates(resolved),
            "pf_x4": round(pf(nets), 6) if math.isfinite(pf(nets)) else "inf",
            "avg_net_x4": round(sum(nets) / len(nets), 6) if nets else 0.0,
            "median_net_x4": round(sorted(nets)[len(nets) // 2], 6) if nets else 0.0,
            "total_net_x4": round(sum(nets), 6) if nets else 0.0,
            "win_rate_x4": round(sum(1 for x in nets if x > 0) / len(nets), 6) if nets else 0.0,
            "max_win_x4": round(max(nets), 6) if nets else 0.0,
            "max_loss_x4": round(min(nets), 6) if nets else 0.0,
            "max_drawdown_x4": round(max_drawdown(nets), 6) if nets else 0.0,
            "max_losing_streak": max_losing_streak(nets),
            "tail_n": len(tail_nets),
            "tail_pf_x4": round(pf(tail_nets), 6) if math.isfinite(pf(tail_nets)) else "inf",
            "tail_avg_net_x4": round(sum(tail_nets) / len(tail_nets), 6) if tail_nets else 0.0,
            "exit_reason_counts_json": json.dumps(dict(exit_counts), sort_keys=True),
            "hour_counts_json": json.dumps(dict(hours), sort_keys=True),
            "stage32c_readiness": row.get("readiness", ""),
        }
        diag.update(summarize_subset(directions.get("1", []), "long"))
        diag.update(summarize_subset(directions.get("-1", []), "short"))
        decision, rationale = decision_for_candidate(row, diag, args)
        diag["stage32d_decision"] = decision
        diag["stage32d_rationale"] = rationale
        out.append(diag)

    def score(row: Dict[str, Any]) -> Tuple[int, float, int, float]:
        decision = str(row.get("stage32d_decision"))
        priority = {
            "EXTENDED_REVIEW_READY_RESEARCH_ONLY": 5,
            "NEEDS_EXTENDED_DENSE_SHADOW_BEFORE_COMMERCIAL_REVIEW": 4,
            "PROMISING_LOW_N_ACCELERATE_COLLECTION": 3,
            "REVIEW_FLAG_BUT_METRIC_WEAK_RECHECK": 2,
            "KEEP_COLLECTING_OR_REPAIR_RESEARCH_ONLY": 1,
            "PAUSE_OR_REPAIR_BEFORE_PRIMARY_SHADOW": 0,
        }.get(decision, 0)
        return (priority, safe_float(row.get("pf_x4"), 0.0) or 0.0, safe_int(row.get("signal_count")), safe_float(row.get("avg_net_x4"), 0.0) or 0.0)

    out.sort(key=score, reverse=True)
    for idx, row in enumerate(out, start=1):
        row["rank"] = idx
    return out


def build_tightening_plan(diags: List[Dict[str, Any]], family_rows: List[Dict[str, Any]], args: argparse.Namespace) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for d in diags:
        decision = str(d.get("stage32d_decision"))
        cand = str(d.get("candidate"))
        family = str(d.get("family"))
        signals = safe_int(d.get("signal_count"))
        pf_x4 = safe_float(d.get("pf_x4"), 0.0) or 0.0
        avg = safe_float(d.get("avg_net_x4"), 0.0) or 0.0
        tail_pf = safe_float(d.get("tail_pf_x4"), 0.0) or 0.0
        tail_avg = safe_float(d.get("tail_avg_net_x4"), 0.0) or 0.0

        if decision == "NEEDS_EXTENDED_DENSE_SHADOW_BEFORE_COMMERCIAL_REVIEW":
            action = "KEEP_PRIMARY_EXTENDED_SHADOW_COLLECT_TO_40"
            next_test = "Collect at least 40 resolved forward samples; then run Stage32D again. No EA/paper/live."
        elif decision == "EXTENDED_REVIEW_READY_RESEARCH_ONLY":
            action = "RUN_PRE_COMMERCIAL_ROBUSTNESS_REVIEW_RESEARCH_ONLY"
            next_test = "Run stricter drawdown/overlap/cost sensitivity before any transition discussion."
        elif decision == "PROMISING_LOW_N_ACCELERATE_COLLECTION":
            action = "ACCELERATE_FORWARD_SAMPLE_COLLECTION"
            next_test = "Keep in tracker; do not evaluate until minimum review sample count is reached."
        elif decision == "PAUSE_OR_REPAIR_BEFORE_PRIMARY_SHADOW":
            action = "PAUSE_PRIMARY_SHADOW_OR_TEST_INVERSION"
            next_test = "Move to repair queue; check direction inversion, hour suppression, and overlap with stronger variants."
        elif pf_x4 >= 1.0 and avg >= 0:
            action = "KEEP_SECONDARY_COLLECTION"
            next_test = "Continue collecting; not review-ready."
        else:
            action = "DEMOTE_TO_REPAIR_OR_BACKGROUND"
            next_test = "Do not consume primary attention until retested or repaired."

        rows.append({
            "rank": d.get("rank", ""),
            "candidate": cand,
            "family": family,
            "signal_count": signals,
            "pf_x4": d.get("pf_x4", ""),
            "avg_net_x4": d.get("avg_net_x4", ""),
            "win_rate_x4": d.get("win_rate_x4", ""),
            "tail_pf_x4": tail_pf,
            "tail_avg_net_x4": tail_avg,
            "max_drawdown_x4": d.get("max_drawdown_x4", ""),
            "stage32d_decision": decision,
            "action": action,
            "next_test": next_test,
            "commercial_status": "RESEARCH_SHADOW_ONLY_NO_EA_NO_PAPER_LIVE",
        })

    return rows


def build_family_plan(family_rows: List[Dict[str, Any]], diags: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_family: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for d in diags:
        by_family[str(d.get("family") or "UNKNOWN")].append(d)
    out: List[Dict[str, Any]] = []
    families = set(by_family.keys()) | {str(r.get("family") or "UNKNOWN") for r in family_rows}
    family_input = {str(r.get("family") or "UNKNOWN"): r for r in family_rows}
    for family in sorted(families):
        vals = by_family.get(family, [])
        input_row = family_input.get(family, {})
        reviewable = [v for v in vals if v.get("stage32d_decision") in {"NEEDS_EXTENDED_DENSE_SHADOW_BEFORE_COMMERCIAL_REVIEW", "EXTENDED_REVIEW_READY_RESEARCH_ONLY"}]
        promising = [v for v in vals if v.get("stage32d_decision") == "PROMISING_LOW_N_ACCELERATE_COLLECTION"]
        negative = [v for v in vals if v.get("stage32d_decision") == "PAUSE_OR_REPAIR_BEFORE_PRIMARY_SHADOW"]
        if reviewable:
            recommendation = "FOCUS_EXTENDED_SHADOW_ON_REVIEWABLE_VARIANT"
        elif promising:
            recommendation = "ACCELERATE_COLLECTION_FOR_PROMISING_LOW_N_VARIANTS"
        elif negative and len(negative) == len(vals):
            recommendation = "DEMOTE_FAMILY_TO_REPAIR"
        else:
            recommendation = str(input_row.get("recommendation") or "KEEP_BACKGROUND_COLLECTION")
        out.append({
            "family": family,
            "candidate_count": len(vals) or input_row.get("candidate_count", ""),
            "signal_count": sum(safe_int(v.get("signal_count")) for v in vals) or input_row.get("signal_count", ""),
            "reviewable_candidate_count": len(reviewable),
            "promising_low_n_count": len(promising),
            "negative_or_pause_count": len(negative),
            "recommendation": recommendation,
        })
    out.sort(key=lambda r: (safe_int(r.get("reviewable_candidate_count")), safe_int(r.get("promising_low_n_count")), safe_int(r.get("signal_count"))), reverse=True)
    return out


def markdown_table(rows: List[Dict[str, Any]], cols: Sequence[str], limit: int = 30) -> List[str]:
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for row in rows[:limit]:
        vals = []
        for col in cols:
            vals.append(str(row.get(col, "")).replace("\n", " "))
        lines.append("| " + " | ".join(vals) + " |")
    return lines


def write_report(summary: Dict[str, Any], diags: List[Dict[str, Any]], plan: List[Dict[str, Any]], family_plan: List[Dict[str, Any]]) -> None:
    lines: List[str] = []
    lines.append("# XAUUSD Stage32D — Dense Forward Review / Tightening Plan\n")
    lines.append(f"Generated UTC: {summary['generated_utc']}\n")
    lines.append("## Decision\n")
    lines.append("```text")
    for key in ["decision", "execution_status", "no_ea_change", "no_paper_live", "no_order_authorization", "commercial_goal", "primary_objective"]:
        lines.append(f"{key.upper()} = {summary.get(key)}")
    lines.append("```\n")
    lines.append("## Why this stage exists\n")
    lines.append("Stage32C found dense forward-shadow activity and at least one candidate reached the research review queue. Stage32D inspects that candidate and produces a tightening plan. It does not authorize EA, paper/live, or orders.\n")
    lines.append("## Summary\n")
    lines.append("```text")
    for key in [
        "candidate_summary_rows", "ledger_rows", "diagnostic_rows", "reviewable_needs_extended_count",
        "extended_review_ready_count", "promising_low_n_count", "pause_or_repair_count",
        "min_review_signals", "extended_min_signals", "min_pf_x4", "min_win_rate",
    ]:
        lines.append(f"{key} = {summary.get(key)}")
    lines.append("```\n")
    lines.append("## Candidate diagnostics\n")
    if diags:
        lines.extend(markdown_table(diags, ["rank", "candidate", "family", "signal_count", "pf_x4", "avg_net_x4", "win_rate_x4", "tail_pf_x4", "max_drawdown_x4", "stage32d_decision"], limit=40))
    else:
        lines.append("No candidate diagnostics available.\n")
    lines.append("\n## Tightening plan\n")
    if plan:
        lines.extend(markdown_table(plan, ["rank", "candidate", "family", "signal_count", "action", "next_test", "commercial_status"], limit=40))
    else:
        lines.append("No tightening plan available.\n")
    lines.append("\n## Family action plan\n")
    if family_plan:
        lines.extend(markdown_table(family_plan, ["family", "signal_count", "reviewable_candidate_count", "promising_low_n_count", "negative_or_pause_count", "recommendation"], limit=30))
    else:
        lines.append("No family action plan available.\n")
    lines.append("\n## Operational interpretation\n")
    lines.append("```text")
    lines.append("1. A Stage32C review flag is not a commercial transition gate.")
    lines.append("2. The current fast path is extended dense shadow on the best candidate while suppressing weak sibling variants.")
    lines.append("3. Do not start EA/paper/live/order routing from this stage.")
    lines.append("4. If the leading candidate survives extended shadow, the next stage should be a pre-commercial robustness gate.")
    lines.append("```\n")
    lines.append("## Output files\n")
    for p in [
        OUT_DIR / "stage32d_dense_forward_review.md",
        OUT_DIR / "dense_review_candidate_diagnostics.csv",
        OUT_DIR / "dense_variant_tightening_plan.csv",
        OUT_DIR / "dense_family_action_plan.csv",
        OUT_DIR / "stage32d_summary.json",
    ]:
        lines.append(f"- `{rel(p)}`")
    (OUT_DIR / "stage32d_dense_forward_review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Stage32D dense forward review/tightening plan.")
    parser.add_argument("--candidate-summary", default=os.getenv("STAGE32D_CANDIDATE_SUMMARY", str(DEFAULT_CANDIDATE_SUMMARY)))
    parser.add_argument("--family-summary", default=os.getenv("STAGE32D_FAMILY_SUMMARY", str(DEFAULT_FAMILY_SUMMARY)))
    parser.add_argument("--ledger", default=os.getenv("STAGE32D_LEDGER", str(DEFAULT_LEDGER)))
    parser.add_argument("--stage32c-summary", default=os.getenv("STAGE32D_STAGE32C_SUMMARY", str(DEFAULT_STAGE32C_SUMMARY)))
    parser.add_argument("--min-review-signals", type=int, default=DEFAULT_MIN_REVIEW_SIGNALS)
    parser.add_argument("--extended-min-signals", type=int, default=DEFAULT_EXTENDED_MIN_SIGNALS)
    parser.add_argument("--min-pf-x4", type=float, default=DEFAULT_MIN_PF_X4)
    parser.add_argument("--min-win-rate", type=float, default=DEFAULT_MIN_WIN_RATE)
    parser.add_argument("--min-avg-net-x4", type=float, default=DEFAULT_MIN_AVG_NET_X4)
    parser.add_argument("--tail-n", type=int, default=DEFAULT_TAIL_N)
    parser.add_argument("--max-allowed-drawdown-x4", type=float, default=DEFAULT_MAX_ALLOWED_DD_X4)
    return parser.parse_args(argv)


def run(args: Optional[argparse.Namespace] = None) -> Dict[str, Any]:
    ensure_dirs()
    args = args or parse_args()
    generated_utc = iso(utc_now())
    candidate_path = Path(args.candidate_summary)
    family_path = Path(args.family_summary)
    ledger_path = Path(args.ledger)
    stage32c_summary_path = Path(args.stage32c_summary)

    candidate_rows = read_csv(candidate_path)
    family_rows = read_csv(family_path)
    ledger_rows = read_csv(ledger_path)
    stage32c_summary = read_json(stage32c_summary_path)

    base_summary: Dict[str, Any] = {
        "generated_utc": generated_utc,
        "execution_status": "RESEARCH_SHADOW_ONLY",
        "no_ea_change": True,
        "no_paper_live": True,
        "no_order_authorization": True,
        "commercial_goal": COMMERCIAL_GOAL,
        "primary_objective": "TIGHTEN_DENSE_FORWARD_REVIEW_CANDIDATES_WITHOUT_COMMERCIAL_PROMOTION",
        "candidate_summary_path": rel(candidate_path),
        "family_summary_path": rel(family_path),
        "ledger_path": rel(ledger_path),
        "stage32c_summary_path": rel(stage32c_summary_path),
        "candidate_summary_rows": len(candidate_rows),
        "family_summary_rows": len(family_rows),
        "ledger_rows": len(ledger_rows),
        "stage32c_decision": stage32c_summary.get("decision", ""),
        "stage32c_review_queue_candidate_count": stage32c_summary.get("review_queue_candidate_count", ""),
        "min_review_signals": int(args.min_review_signals),
        "extended_min_signals": int(args.extended_min_signals),
        "min_pf_x4": float(args.min_pf_x4),
        "min_win_rate": float(args.min_win_rate),
        "min_avg_net_x4": float(args.min_avg_net_x4),
        "tail_n": int(args.tail_n),
        "max_allowed_drawdown_x4": float(args.max_allowed_drawdown_x4),
    }

    if not candidate_rows or not ledger_rows:
        summary = dict(base_summary)
        summary.update({
            "decision": "STAGE32D_BLOCKED_MISSING_STAGE32C_INPUTS_RESEARCH_SHADOW_ONLY",
            "diagnostic_rows": 0,
            "reviewable_needs_extended_count": 0,
            "extended_review_ready_count": 0,
            "promising_low_n_count": 0,
            "pause_or_repair_count": 0,
            "error": "Missing dense_forward_candidate_summary.csv or dense_forward_signal_ledger.csv.",
        })
        write_json(OUT_DIR / "stage32d_summary.json", summary)
        write_report(summary, [], [], [])
        return summary

    diags = diagnose_candidates(candidate_rows, ledger_rows, args)
    plan = build_tightening_plan(diags, family_rows, args)
    family_plan = build_family_plan(family_rows, diags)

    needs_extended = [d for d in diags if d.get("stage32d_decision") == "NEEDS_EXTENDED_DENSE_SHADOW_BEFORE_COMMERCIAL_REVIEW"]
    extended_ready = [d for d in diags if d.get("stage32d_decision") == "EXTENDED_REVIEW_READY_RESEARCH_ONLY"]
    promising_low_n = [d for d in diags if d.get("stage32d_decision") == "PROMISING_LOW_N_ACCELERATE_COLLECTION"]
    pause_or_repair = [d for d in diags if d.get("stage32d_decision") == "PAUSE_OR_REPAIR_BEFORE_PRIMARY_SHADOW"]

    if extended_ready:
        decision = "STAGE32D_HAS_EXTENDED_REVIEW_READY_CANDIDATE_RESEARCH_ONLY"
    elif needs_extended:
        decision = "STAGE32D_HAS_REVIEW_CANDIDATE_NEEDS_EXTENDED_SHADOW_RESEARCH_ONLY"
    elif promising_low_n:
        decision = "STAGE32D_HAS_PROMISING_LOW_N_DENSE_CANDIDATES_RESEARCH_ONLY"
    else:
        decision = "STAGE32D_NO_DENSE_REVIEW_CANDIDATE_KEEP_COLLECTING_RESEARCH_ONLY"

    summary = dict(base_summary)
    summary.update({
        "decision": decision,
        "diagnostic_rows": len(diags),
        "tightening_plan_rows": len(plan),
        "family_plan_rows": len(family_plan),
        "reviewable_needs_extended_count": len(needs_extended),
        "extended_review_ready_count": len(extended_ready),
        "promising_low_n_count": len(promising_low_n),
        "pause_or_repair_count": len(pause_or_repair),
        "leading_candidate": diags[0].get("candidate") if diags else "",
        "leading_candidate_decision": diags[0].get("stage32d_decision") if diags else "",
        "commercial_transition_authorized": False,
    })

    write_csv(OUT_DIR / "dense_review_candidate_diagnostics.csv", diags)
    write_json(OUT_DIR / "dense_review_candidate_diagnostics.json", diags)
    write_csv(OUT_DIR / "dense_variant_tightening_plan.csv", plan)
    write_json(OUT_DIR / "dense_variant_tightening_plan.json", plan)
    write_csv(OUT_DIR / "dense_family_action_plan.csv", family_plan)
    write_json(OUT_DIR / "dense_family_action_plan.json", family_plan)
    write_json(OUT_DIR / "stage32d_summary.json", summary)
    write_report(summary, diags, plan, family_plan)
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    summary = run(args)
    print(summary.get("decision"))
    print(f"report={rel(OUT_DIR / 'stage32d_dense_forward_review.md')}")
    print(f"tightening_plan={rel(OUT_DIR / 'dense_variant_tightening_plan.csv')}")
    return 0 if "ERROR" not in str(summary.get("decision")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
