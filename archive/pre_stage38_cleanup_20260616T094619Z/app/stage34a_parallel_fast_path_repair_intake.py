"""Stage34A — Parallel Fast-Path Repair / Intake Gate for XAUUSD research.

Purpose:
    Do not wait passively for Stage33E short-confirmation events.
    While Stage32F/Stage33E collect background samples, evaluate existing dense
    forward ledger for repaired sibling groups and alternative fast-path families.

This module is research-only. It never authorizes EA, paper-live, or orders.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Dict, Any, Tuple

import pandas as pd

ROOT = Path(".")
LEDGER_PATH = ROOT / "data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_signal_ledger.csv"
STAGE33E_LEDGER_PATH = ROOT / "data/reports/stage33e_short_confirmation_recency_filter/repaired_family_effective_ledger.csv"
OUT_DIR = ROOT / "data/reports/stage34a_parallel_fast_path_repair_intake"

REPORT_PATH = OUT_DIR / "stage34a_parallel_fast_path_repair_intake.md"
SUMMARY_PATH = OUT_DIR / "stage34a_summary.json"
CANDIDATE_SET_PATH = OUT_DIR / "candidate_set_diagnostics.csv"
ACCELERATION_QUEUE_PATH = OUT_DIR / "parallel_acceleration_queue.csv"
REPAIR_OR_KILL_PATH = OUT_DIR / "repair_or_kill_queue.csv"
MEMBER_QUALITY_PATH = OUT_DIR / "member_quality_summary.csv"

# Conservative research thresholds. These do not authorize execution.
MIN_REVIEW_EVENTS = 24
MIN_ACCEL_EVENTS = 14
MIN_GOOD_MEMBERS = 2
MIN_CORE_PF = 1.45
MIN_CORE_WR = 0.60
MIN_CORE_AVG = 0.50
MIN_TAIL_PF = 1.00
MIN_COST1_PF = 1.15
MAX_DRAWDOWN = -35.0
MIN_LAST5_PF = 1.00
MIN_LAST5_AVG = 0.0
MIN_CANDIDATE_EVENTS = 8
MIN_MEMBER_PF = 1.20
MIN_MEMBER_WR = 0.55
TAIL_N = 10
LAST_N = 5
COST_STRESS_X4 = 1.0


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def safe_pf(values: Iterable[float]) -> float:
    vals = [float(v) for v in values if pd.notna(v)]
    gains = sum(v for v in vals if v > 0)
    losses = -sum(v for v in vals if v < 0)
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


def max_drawdown(values: Iterable[float]) -> float:
    equity = 0.0
    peak = 0.0
    mdd = 0.0
    for v in values:
        if pd.isna(v):
            continue
        equity += float(v)
        peak = max(peak, equity)
        mdd = min(mdd, equity - peak)
    return float(mdd)


def metrics(values: Iterable[float]) -> Dict[str, float]:
    vals = [float(v) for v in values if pd.notna(v)]
    if not vals:
        return {
            "signal_count": 0,
            "pf_x4": 0.0,
            "avg_net_x4": 0.0,
            "win_rate_x4": 0.0,
            "tail_pf_x4": 0.0,
            "max_drawdown_x4": 0.0,
            "sum_net_x4": 0.0,
        }
    tail_vals = vals[-TAIL_N:]
    return {
        "signal_count": len(vals),
        "pf_x4": safe_pf(vals),
        "avg_net_x4": sum(vals) / len(vals),
        "win_rate_x4": sum(1 for v in vals if v > 0) / len(vals),
        "tail_pf_x4": safe_pf(tail_vals),
        "max_drawdown_x4": max_drawdown(vals),
        "sum_net_x4": sum(vals),
    }


def normalize_candidate_group(candidate: str, family: str) -> str:
    c = str(candidate)
    f = str(family)
    # Replace explicit hours with hX and weekdays with WEEKDAY to form sibling groups.
    c = re.sub(r"_h\d+", "_hX", c)
    c = re.sub(r"calendar_drop_(monday|tuesday|wednesday|thursday|friday|saturday|sunday)_", "calendar_drop_WEEKDAY_", c)
    return f"{f}::{c}"


def find_col(cols: Iterable[str], candidates: List[str]) -> str | None:
    lower_map = {str(c).lower(): c for c in cols}
    for name in candidates:
        if name.lower() in lower_map:
            return lower_map[name.lower()]
    return None


def load_ledger(path: Path) -> Tuple[pd.DataFrame, Dict[str, str | None]]:
    if not path.exists():
        return pd.DataFrame(), {"error": f"missing_file:{path}"}
    df = pd.read_csv(path)
    colmap = {
        "candidate": find_col(df.columns, ["candidate", "candidate_id", "variant", "spec", "name"]),
        "family": find_col(df.columns, ["family", "family_id", "pattern_family"]),
        "timestamp": find_col(df.columns, ["entry_time", "entry_time_utc", "timestamp", "signal_ts_utc", "ts_utc", "time"]),
        "direction": find_col(df.columns, ["direction", "side", "dir"]),
        "net": find_col(df.columns, ["net_x4", "net_r_x4", "net", "outcome_net_x4", "r_x4"]),
    }
    required = ["candidate", "family", "timestamp", "direction", "net"]
    missing = [k for k in required if not colmap.get(k)]
    if missing:
        colmap["error"] = "missing_required_ledger_columns:" + ",".join(missing)
        return pd.DataFrame(), colmap

    out = pd.DataFrame({
        "candidate": df[colmap["candidate"]].astype(str),
        "family": df[colmap["family"]].astype(str),
        "entry_time": pd.to_datetime(df[colmap["timestamp"]], utc=True, errors="coerce"),
        "direction": df[colmap["direction"]].astype(str),
        "net_x4": pd.to_numeric(df[colmap["net"]], errors="coerce"),
    }).dropna(subset=["entry_time", "net_x4"])
    out = out.sort_values("entry_time").reset_index(drop=True)
    out["sibling_group"] = [normalize_candidate_group(c, f) for c, f in zip(out["candidate"], out["family"])]
    return out, colmap


def dedup_events(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    x = df.copy()
    x["event_key"] = x["entry_time"].astype(str) + "|" + x["direction"].astype(str)
    # If sibling variants fire same timestamp/direction, average net to avoid inflated family count.
    d = (
        x.groupby(["event_key", "entry_time", "direction"], as_index=False)
        .agg(net_x4=("net_x4", "mean"), candidates=("candidate", lambda s: ";".join(sorted(set(map(str, s))))), family=("family", "first"))
        .sort_values("entry_time")
        .reset_index(drop=True)
    )
    return d


def member_quality(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (group, cand), g in df.groupby(["sibling_group", "candidate"]):
        m = metrics(g.sort_values("entry_time")["net_x4"])
        if m["signal_count"] >= MIN_CANDIDATE_EVENTS and m["pf_x4"] >= MIN_MEMBER_PF and m["win_rate_x4"] >= MIN_MEMBER_WR and m["avg_net_x4"] > 0:
            q = "GOOD_MEMBER"
        elif m["signal_count"] >= MIN_CANDIDATE_EVENTS and m["pf_x4"] >= 1.0 and m["avg_net_x4"] >= 0:
            q = "SECONDARY_MEMBER"
        else:
            q = "WEAK_OR_REPAIR_MEMBER"
        rows.append({
            "sibling_group": group,
            "candidate": cand,
            "family": g["family"].iloc[0],
            **m,
            "member_quality": q,
        })
    return pd.DataFrame(rows).sort_values(["sibling_group", "member_quality", "pf_x4"], ascending=[True, True, False]) if rows else pd.DataFrame()


def evaluate_set(df: pd.DataFrame, group_name: str, set_name: str, candidates: List[str], member_df: pd.DataFrame) -> Dict[str, Any]:
    subset = df[df["candidate"].isin(candidates)].copy().sort_values("entry_time")
    effective = dedup_events(subset)
    vals = list(effective["net_x4"])
    m = metrics(vals)
    cost_vals = [v - COST_STRESS_X4 for v in vals]
    cost_m = metrics(cost_vals)
    last_vals = vals[-LAST_N:]
    last_m = metrics(last_vals)

    members = member_df[(member_df["sibling_group"] == group_name) & (member_df["candidate"].isin(candidates))]
    good_members = int((members["member_quality"] == "GOOD_MEMBER").sum()) if not members.empty else 0
    weak_members = int((members["member_quality"] == "WEAK_OR_REPAIR_MEMBER").sum()) if not members.empty else 0
    secondary_members = int((members["member_quality"] == "SECONDARY_MEMBER").sum()) if not members.empty else 0

    core_pass = (
        m["signal_count"] >= MIN_REVIEW_EVENTS and
        good_members >= MIN_GOOD_MEMBERS and
        m["pf_x4"] >= MIN_CORE_PF and
        m["win_rate_x4"] >= MIN_CORE_WR and
        m["avg_net_x4"] >= MIN_CORE_AVG and
        m["tail_pf_x4"] >= MIN_TAIL_PF and
        m["max_drawdown_x4"] >= MAX_DRAWDOWN and
        cost_m["pf_x4"] >= MIN_COST1_PF
    )
    recent_pass = (last_m["pf_x4"] >= MIN_LAST5_PF and last_m["avg_net_x4"] >= MIN_LAST5_AVG) if last_m["signal_count"] >= LAST_N else False

    if core_pass and recent_pass:
        decision = "PRECOMMERCIAL_REVIEW_CANDIDATE_RESEARCH_ONLY"
        next_action = "RUN_STRICT_PREPAPER_GATE_NO_EA_NO_PAPER_LIVE"
    elif core_pass and not recent_pass:
        decision = "SHORT_CONFIRMATION_SHADOW_RESEARCH_ONLY"
        next_action = "COLLECT_5_TO_10_NEW_EVENTS_THEN_RERUN_STAGE33D_E"
    elif m["signal_count"] >= MIN_ACCEL_EVENTS and good_members >= 1 and m["pf_x4"] >= 1.20 and m["avg_net_x4"] > 0:
        decision = "ACCELERATE_COLLECTION_RESEARCH_ONLY"
        next_action = "KEEP_IN_PARALLEL_COLLECTION_QUEUE"
    else:
        decision = "REPAIR_OR_KILL_RESEARCH_ONLY"
        next_action = "MOVE_TO_REPAIR_OR_KILL_DO_NOT_WAIT"

    return {
        "sibling_group": group_name,
        "set_name": set_name,
        "candidate_list": ";".join(candidates),
        "member_count": len(candidates),
        "raw_rows": int(len(subset)),
        "effective_event_count": int(m["signal_count"]),
        "good_member_count": good_members,
        "secondary_member_count": secondary_members,
        "weak_member_count": weak_members,
        "pf_x4": m["pf_x4"],
        "avg_net_x4": m["avg_net_x4"],
        "win_rate_x4": m["win_rate_x4"],
        "tail_pf_x4": m["tail_pf_x4"],
        "max_drawdown_x4": m["max_drawdown_x4"],
        "cost_1_pf_x4": cost_m["pf_x4"],
        "cost_1_avg_net_x4": cost_m["avg_net_x4"],
        "last5_signal_count": last_m["signal_count"],
        "last5_pf_x4": last_m["pf_x4"],
        "last5_avg_net_x4": last_m["avg_net_x4"],
        "last5_win_rate_x4": last_m["win_rate_x4"],
        "stage34a_decision": decision,
        "next_action": next_action,
        "commercial_status": "RESEARCH_ONLY_NO_EA_NO_PAPER_LIVE_NO_ORDER",
    }


def candidate_sets(df: pd.DataFrame, members: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for group_name, g in df.groupby("sibling_group"):
        all_candidates = sorted(g["candidate"].unique())
        if not all_candidates:
            continue
        rows.append(evaluate_set(df, group_name, "FULL_SIBLING_GROUP", all_candidates, members))

        gm = members[(members["sibling_group"] == group_name) & (members["member_quality"] == "GOOD_MEMBER")]
        good_candidates = sorted(gm["candidate"].unique())
        if len(good_candidates) >= 2 and set(good_candidates) != set(all_candidates):
            rows.append(evaluate_set(df, group_name, "GOOD_MEMBERS_ONLY_REPAIR", good_candidates, members))

        # Single best candidate diagnostics are allowed, but never promote to paper from here.
        for cand in good_candidates:
            rows.append(evaluate_set(df, group_name, f"SINGLE_GOOD_MEMBER_DIAGNOSTIC::{cand}", [cand], members))

    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    return out.sort_values(
        ["stage34a_decision", "pf_x4", "effective_event_count"],
        ascending=[True, False, False],
    ).reset_index(drop=True)


def fmt_num(v: Any, nd: int = 6) -> str:
    if isinstance(v, (float, int)):
        if math.isinf(float(v)):
            return "inf"
        return f"{float(v):.{nd}f}".rstrip("0").rstrip(".")
    return str(v)


def write_report(summary: Dict[str, Any], diagnostics: pd.DataFrame, accel: pd.DataFrame, repair: pd.DataFrame) -> None:
    lines = []
    lines.append("# XAUUSD Stage34A — Parallel Fast-Path Repair / Intake Gate")
    lines.append("")
    lines.append(f"Generated UTC: {summary['generated_utc']}")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append("```text")
    for key in [
        "decision", "execution_status", "commercial_transition_authorized", "no_ea_change", "no_paper_live", "no_order_authorization", "primary_objective", "recommended_next_stage",
    ]:
        lines.append(f"{key.upper()} = {summary[key]}")
    lines.append("```")
    lines.append("")
    lines.append("## Why this stage exists")
    lines.append("")
    lines.append("Stage33E waits for a short h13+h14 confirmation batch. This stage prevents passive waiting by evaluating repaired sibling groups and alternative dense-family paths in parallel. It is research-only and does not authorize EA, paper-live, or orders.")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("```text")
    for key in ["ledger_available", "ledger_rows", "normalized_ledger_rows", "member_rows", "candidate_set_rows", "precommercial_review_rows", "short_confirmation_rows", "accelerate_collection_rows", "repair_or_kill_rows"]:
        lines.append(f"{key} = {summary[key]}")
    lines.append("```")
    lines.append("")
    lines.append("## Parallel acceleration queue")
    lines.append("")
    if accel.empty:
        lines.append("No rows.")
    else:
        show_cols = ["set_name", "sibling_group", "candidate_list", "effective_event_count", "good_member_count", "weak_member_count", "pf_x4", "avg_net_x4", "win_rate_x4", "tail_pf_x4", "cost_1_pf_x4", "last5_pf_x4", "stage34a_decision", "next_action"]
        lines.append(accel[show_cols].to_markdown(index=False))
    lines.append("")
    lines.append("## Repair / kill queue")
    lines.append("")
    if repair.empty:
        lines.append("No rows.")
    else:
        show_cols = ["set_name", "sibling_group", "candidate_list", "effective_event_count", "pf_x4", "avg_net_x4", "win_rate_x4", "last5_pf_x4", "stage34a_decision", "next_action"]
        lines.append(repair[show_cols].to_markdown(index=False))
    lines.append("")
    lines.append("## Operational interpretation")
    lines.append("")
    lines.append("```text")
    lines.append("1. Do not wait passively for Stage33E; keep scanning repaired sibling groups in parallel.")
    lines.append("2. Stage32F remains background collection only.")
    lines.append("3. Families that fail this gate should be killed or repaired quickly; no single-variant N=40 waiting by default.")
    lines.append("4. No EA/paper-live/order transition is authorized here.")
    lines.append("```")
    lines.append("")
    lines.append("## Output files")
    lines.append("")
    for p in [REPORT_PATH, SUMMARY_PATH, CANDIDATE_SET_PATH, ACCELERATION_QUEUE_PATH, REPAIR_OR_KILL_PATH, MEMBER_QUALITY_PATH]:
        lines.append(f"- `{p}`")
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ledger, colmap = load_ledger(LEDGER_PATH)
    ledger_available = not ledger.empty

    if not ledger_available:
        diagnostics = pd.DataFrame()
        members = pd.DataFrame()
    else:
        members = member_quality(ledger)
        diagnostics = candidate_sets(ledger, members)

    if not members.empty:
        members.to_csv(MEMBER_QUALITY_PATH, index=False)
    else:
        pd.DataFrame().to_csv(MEMBER_QUALITY_PATH, index=False)

    if not diagnostics.empty:
        diagnostics.to_csv(CANDIDATE_SET_PATH, index=False)
    else:
        pd.DataFrame().to_csv(CANDIDATE_SET_PATH, index=False)

    precommercial = diagnostics[diagnostics["stage34a_decision"] == "PRECOMMERCIAL_REVIEW_CANDIDATE_RESEARCH_ONLY"].copy() if not diagnostics.empty else pd.DataFrame()
    shortconf = diagnostics[diagnostics["stage34a_decision"] == "SHORT_CONFIRMATION_SHADOW_RESEARCH_ONLY"].copy() if not diagnostics.empty else pd.DataFrame()
    accel = diagnostics[diagnostics["stage34a_decision"].isin(["PRECOMMERCIAL_REVIEW_CANDIDATE_RESEARCH_ONLY", "SHORT_CONFIRMATION_SHADOW_RESEARCH_ONLY", "ACCELERATE_COLLECTION_RESEARCH_ONLY"])].copy() if not diagnostics.empty else pd.DataFrame()
    repair = diagnostics[diagnostics["stage34a_decision"] == "REPAIR_OR_KILL_RESEARCH_ONLY"].copy() if not diagnostics.empty else pd.DataFrame()

    accel.to_csv(ACCELERATION_QUEUE_PATH, index=False)
    repair.to_csv(REPAIR_OR_KILL_PATH, index=False)

    if len(precommercial) > 0:
        decision = "STAGE34A_HAS_PRECOMMERCIAL_REVIEW_CANDIDATE_RESEARCH_ONLY"
        next_stage = "RUN_STRICT_PREPAPER_GATE_ON_TOP_CANDIDATE_NO_EA_NO_PAPER_LIVE"
    elif len(shortconf) > 0:
        decision = "STAGE34A_HAS_SHORT_CONFIRMATION_FAST_PATH_RESEARCH_ONLY"
        next_stage = "CONTINUE_STAGE33E_CONFIRMATION_AND_REPAIR_FILTERS_IN_PARALLEL"
    elif len(accel) > 0:
        decision = "STAGE34A_HAS_ACCELERATION_CANDIDATES_RESEARCH_ONLY"
        next_stage = "KEEP_PARALLEL_COLLECTION_AND_RERUN_STAGE34A"
    else:
        decision = "STAGE34A_NO_FAST_PATH_RETURN_TO_INTAKE_EXPANSION_RESEARCH_ONLY"
        next_stage = "RETURN_TO_STAGE32B_INTAKE_EXPANSION_OR_NEW_DENSE_FAMILY_DISCOVERY"

    summary = {
        "generated_utc": now_utc(),
        "decision": decision,
        "execution_status": "RESEARCH_ONLY",
        "commercial_transition_authorized": False,
        "no_ea_change": True,
        "no_paper_live": True,
        "no_order_authorization": True,
        "primary_objective": "PARALLEL_REPAIR_INTAKE_TO_REDUCE_TIME_TO_COMMERCIAL_DECISION",
        "recommended_next_stage": next_stage,
        "ledger_path": str(LEDGER_PATH),
        "ledger_available": bool(ledger_available),
        "ledger_rows": int(len(pd.read_csv(LEDGER_PATH))) if LEDGER_PATH.exists() else 0,
        "normalized_ledger_rows": int(len(ledger)) if ledger_available else 0,
        "ledger_column_map": colmap,
        "member_rows": int(len(members)),
        "candidate_set_rows": int(len(diagnostics)),
        "precommercial_review_rows": int(len(precommercial)),
        "short_confirmation_rows": int(len(shortconf)),
        "accelerate_collection_rows": int(len(accel)),
        "repair_or_kill_rows": int(len(repair)),
        "thresholds": {
            "min_review_events": MIN_REVIEW_EVENTS,
            "min_accel_events": MIN_ACCEL_EVENTS,
            "min_good_members": MIN_GOOD_MEMBERS,
            "min_core_pf": MIN_CORE_PF,
            "min_core_wr": MIN_CORE_WR,
            "min_core_avg": MIN_CORE_AVG,
            "min_tail_pf": MIN_TAIL_PF,
            "min_cost1_pf": MIN_COST1_PF,
            "max_drawdown": MAX_DRAWDOWN,
            "min_last5_pf": MIN_LAST5_PF,
            "min_last5_avg": MIN_LAST5_AVG,
        },
    }

    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(summary, diagnostics, accel, repair)

    print(f"DECISION={decision}")
    print(f"ACCELERATION_QUEUE_ROWS={len(accel)}")
    print(f"PRECOMMERCIAL_REVIEW_ROWS={len(precommercial)}")
    print(f"SHORT_CONFIRMATION_ROWS={len(shortconf)}")
    print(f"REPORT={REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
