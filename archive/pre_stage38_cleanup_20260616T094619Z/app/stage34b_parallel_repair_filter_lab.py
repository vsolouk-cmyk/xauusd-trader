#!/usr/bin/env python3
"""
XAUUSD Stage34B — Parallel Repair / Filter Lab

Research-only diagnostic stage. It uses the Stage32C dense forward ledger and
Stage34A context to test repaired subsets, inversion candidates, and kill/keep
decisions while Stage33E short confirmation runs in the background.

No EA, no paper-live, no order authorization.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

REPORT_DIR = Path("data/reports/stage34b_parallel_repair_filter_lab")
REPORT_DIR.mkdir(parents=True, exist_ok=True)

LEDGER_PATH = Path("data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_signal_ledger.csv")
STAGE34A_SUMMARY_PATH = Path("data/reports/stage34a_parallel_fast_path_repair_intake/stage34a_summary.json")
STAGE33E_SUMMARY_PATH = Path("data/reports/stage33e_short_confirmation_recency_filter/stage33e_summary.json")

MIN_REVIEW_EVENTS = 24
MIN_ACCEL_EVENTS = 14
MIN_PRECOMM_PF = 1.35
MIN_PRECOMM_WR = 0.58
MIN_PRECOMM_AVG = 0.25
MIN_PRECOMM_TAIL_PF = 1.0
MIN_PRECOMM_COST1_PF = 1.10
MIN_PRECOMM_LAST5_PF = 1.0
MIN_PRECOMM_LAST5_AVG = 0.0
MAX_DRAWDOWN = -35.0
TAIL_N = 10
LAST_N = 5

NO_EXECUTION_FLAGS = {
    "execution_status": "RESEARCH_ONLY",
    "commercial_transition_authorized": False,
    "no_ea_change": True,
    "no_paper_live": True,
    "no_order_authorization": True,
}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def find_col(cols: Iterable[str], candidates: Iterable[str]) -> Optional[str]:
    lower_map = {c.lower(): c for c in cols}
    for name in candidates:
        if name.lower() in lower_map:
            return lower_map[name.lower()]
    return None


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def normalize_ledger(path: Path) -> tuple[pd.DataFrame, dict]:
    if not path.exists():
        return pd.DataFrame(), {"error": "ledger_missing", "path": str(path)}

    raw = pd.read_csv(path)
    cols = raw.columns
    candidate_col = find_col(cols, ["candidate", "candidate_name", "variant", "spec", "name"])
    family_col = find_col(cols, ["family", "family_name", "pattern_family"])
    timestamp_col = find_col(cols, ["entry_time", "entry_time_utc", "timestamp", "signal_ts_utc", "ts_utc", "time", "datetime"])
    direction_col = find_col(cols, ["direction", "side", "signal_direction", "dir"])
    net_col = find_col(cols, ["net_x4", "net", "net_R", "r_net", "outcome_net_x4", "pnl_x4"])

    colmap = {
        "candidate_col": candidate_col,
        "family_col": family_col,
        "timestamp_col": timestamp_col,
        "direction_col": direction_col,
        "net_col": net_col,
    }
    required = [candidate_col, family_col, timestamp_col, direction_col, net_col]
    if any(c is None for c in required):
        colmap["error"] = "missing_required_ledger_columns"
        return pd.DataFrame(), colmap

    df = raw[[candidate_col, family_col, timestamp_col, direction_col, net_col]].copy()
    df.columns = ["candidate", "family", "entry_time", "direction", "net_x4"]
    df["candidate"] = df["candidate"].astype(str)
    df["family"] = df["family"].astype(str)
    df["direction"] = df["direction"].astype(str)
    df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True, errors="coerce")
    df["net_x4"] = pd.to_numeric(df["net_x4"], errors="coerce")
    df = df.dropna(subset=["entry_time", "net_x4"])
    df = df.sort_values(["entry_time", "candidate", "direction"]).reset_index(drop=True)
    return df, colmap


def profit_factor(values: pd.Series) -> float:
    vals = pd.to_numeric(values, errors="coerce").dropna()
    wins = vals[vals > 0].sum()
    losses = vals[vals < 0].sum()
    if losses == 0:
        if wins > 0:
            return float("inf")
        return 0.0
    return float(wins / abs(losses))


def max_drawdown(values: pd.Series) -> float:
    vals = pd.to_numeric(values, errors="coerce").fillna(0.0)
    if vals.empty:
        return 0.0
    equity = vals.cumsum()
    peak = equity.cummax()
    dd = equity - peak
    return float(dd.min())


def summarize_values(values: pd.Series) -> dict:
    vals = pd.to_numeric(values, errors="coerce").dropna()
    n = int(len(vals))
    if n == 0:
        return {
            "signal_count": 0,
            "pf_x4": 0.0,
            "avg_net_x4": 0.0,
            "win_rate_x4": 0.0,
            "tail_pf_x4": 0.0,
            "last5_pf_x4": 0.0,
            "last5_avg_net_x4": 0.0,
            "last5_win_rate_x4": 0.0,
            "max_drawdown_x4": 0.0,
            "sum_net_x4": 0.0,
        }
    tail = vals.tail(TAIL_N)
    last5 = vals.tail(LAST_N)
    return {
        "signal_count": n,
        "pf_x4": profit_factor(vals),
        "avg_net_x4": float(vals.mean()),
        "win_rate_x4": float((vals > 0).mean()),
        "tail_pf_x4": profit_factor(tail),
        "last5_pf_x4": profit_factor(last5),
        "last5_avg_net_x4": float(last5.mean()) if len(last5) else 0.0,
        "last5_win_rate_x4": float((last5 > 0).mean()) if len(last5) else 0.0,
        "max_drawdown_x4": max_drawdown(vals),
        "sum_net_x4": float(vals.sum()),
    }


def cost_stressed_pf(values: pd.Series, penalty: float = 1.0) -> float:
    vals = pd.to_numeric(values, errors="coerce").dropna() - penalty
    return profit_factor(vals)


@dataclass
class CandidateSet:
    set_name: str
    family: str
    sibling_group: str
    candidates: list[str]
    invert: bool = False
    purpose: str = "repair_filter"


def sibling_key(candidate: str, family: str) -> str:
    c = candidate
    if c.startswith("handoff_align_follow_h"):
        return f"{family}::handoff_align_follow_hX_tp06_sl065"
    if c.startswith("calendar_drop_"):
        return f"{family}::calendar_drop_WEEKDAY_hX_tp06_sl065"
    if c.startswith("vol_trans_follow_"):
        return f"{family}::vol_trans_follow_hX_low_to_high_hX_tp06_sl065"
    if c.startswith("vol_trans_fade_"):
        return f"{family}::vol_trans_fade_hX_low_to_high_hX_tp06_sl065"
    return f"{family}::{re.sub(r'h\\d+', 'hX', c)}"


def build_sets(df: pd.DataFrame) -> list[CandidateSet]:
    sets: list[CandidateSet] = []
    if df.empty:
        return sets

    candidates_by_family = df.groupby("family")["candidate"].unique().to_dict()
    all_candidates = sorted(df["candidate"].unique())

    # Handoff repaired/confirmation and raw group.
    handoff = [c for c in all_candidates if c.startswith("handoff_align_follow_h")]
    h13h14 = [c for c in handoff if "_h13_" in c or "_h14_" in c]
    h15 = [c for c in handoff if "_h15_" in c]
    if handoff:
        fam = df[df["candidate"].isin(handoff)]["family"].mode().iloc[0]
        group = f"{fam}::handoff_align_follow_hX_tp06_sl065"
        sets.append(CandidateSet("HANDOFF_FULL_H13_H14_H15", fam, group, sorted(handoff), False, "monitor_reference"))
        if h13h14:
            sets.append(CandidateSet("HANDOFF_REPAIRED_H13_H14_CONFIRMATION", fam, group, sorted(h13h14), False, "short_confirmation_reference"))
        for c in sorted(handoff):
            sets.append(CandidateSet(f"HANDOFF_SINGLE_MEMBER::{c}", fam, group, [c], False, "single_member_diagnostic"))

    # Calendar repair filters and inversion checks.
    calendar = [c for c in all_candidates if c.startswith("calendar_drop_")]
    if calendar:
        fam = df[df["candidate"].isin(calendar)]["family"].mode().iloc[0]
        group = f"{fam}::calendar_drop_WEEKDAY_hX_tp06_sl065"
        friday = [c for c in calendar if "friday" in c]
        monday = [c for c in calendar if "monday" in c]
        sets.append(CandidateSet("CALENDAR_FULL_RAW", fam, group, sorted(calendar), False, "calendar_repair"))
        sets.append(CandidateSet("CALENDAR_FULL_INVERTED", fam, group, sorted(calendar), True, "calendar_inversion_test"))
        if friday:
            sets.append(CandidateSet("CALENDAR_FRIDAY_ONLY_RAW", fam, group, sorted(friday), False, "calendar_repair"))
            sets.append(CandidateSet("CALENDAR_FRIDAY_ONLY_INVERTED", fam, group, sorted(friday), True, "calendar_inversion_test"))
        if monday:
            sets.append(CandidateSet("CALENDAR_MONDAY_ONLY_RAW", fam, group, sorted(monday), False, "calendar_repair"))
            sets.append(CandidateSet("CALENDAR_MONDAY_ONLY_INVERTED", fam, group, sorted(monday), True, "calendar_inversion_test"))
        for c in sorted(calendar):
            sets.append(CandidateSet(f"CALENDAR_SINGLE_RAW::{c}", fam, group, [c], False, "calendar_single"))
            sets.append(CandidateSet(f"CALENDAR_SINGLE_INVERTED::{c}", fam, group, [c], True, "calendar_single_inversion"))

    # Volatility transition follow/fade repair and inversion checks.
    for prefix in ["vol_trans_follow_", "vol_trans_fade_"]:
        group_members = [c for c in all_candidates if c.startswith(prefix)]
        if not group_members:
            continue
        fam = df[df["candidate"].isin(group_members)]["family"].mode().iloc[0]
        label = "follow" if "follow" in prefix else "fade"
        group = f"{fam}::vol_trans_{label}_hX_low_to_high_hX_tp06_sl065"
        sets.append(CandidateSet(f"VOL_TRANS_{label.upper()}_FULL_RAW", fam, group, sorted(group_members), False, "volatility_repair"))
        sets.append(CandidateSet(f"VOL_TRANS_{label.upper()}_FULL_INVERTED", fam, group, sorted(group_members), True, "volatility_inversion_test"))
        for c in sorted(group_members):
            sets.append(CandidateSet(f"VOL_TRANS_{label.upper()}_SINGLE_RAW::{c}", fam, group, [c], False, "volatility_single"))
            sets.append(CandidateSet(f"VOL_TRANS_{label.upper()}_SINGLE_INVERTED::{c}", fam, group, [c], True, "volatility_single_inversion"))

    # Generic fallback: all family groups.
    for fam, arr in candidates_by_family.items():
        members = sorted(arr)
        sets.append(CandidateSet(f"FAMILY_FULL_RAW::{fam}", fam, f"{fam}::ALL", members, False, "family_reference"))

    # Deduplicate set names.
    seen = set()
    out: list[CandidateSet] = []
    for s in sets:
        key = (s.set_name, tuple(s.candidates), s.invert)
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def evaluate_set(df: pd.DataFrame, cset: CandidateSet) -> dict:
    sub = df[df["candidate"].isin(cset.candidates)].copy()
    if sub.empty:
        return {}
    sub["effective_net_x4"] = sub["net_x4"] * (-1.0 if cset.invert else 1.0)
    sub["event_key"] = sub["entry_time"].dt.strftime("%Y-%m-%dT%H:%M:%SZ") + "|" + sub["direction"].astype(str)
    # Dedup timestamp+direction to avoid sibling double counting. Average is conservative for overlapping sibling signals.
    eff = (
        sub.groupby(["event_key", "entry_time", "direction"], as_index=False)
        .agg(effective_net_x4=("effective_net_x4", "mean"), member_rows=("candidate", "nunique"))
        .sort_values("entry_time")
    )
    metrics = summarize_values(eff["effective_net_x4"])
    cost1_pf = cost_stressed_pf(eff["effective_net_x4"], 1.0)
    member_count = len(cset.candidates)
    good_member_count = 0
    weak_member_count = 0
    for cand in cset.candidates:
        one = df[df["candidate"] == cand].copy()
        if one.empty:
            continue
        vals = one["net_x4"] * (-1.0 if cset.invert else 1.0)
        m = summarize_values(vals)
        if m["signal_count"] >= 8 and m["pf_x4"] >= 1.2 and m["win_rate_x4"] >= 0.55 and m["avg_net_x4"] > 0:
            good_member_count += 1
        elif m["pf_x4"] < 1.0 or m["avg_net_x4"] <= 0:
            weak_member_count += 1

    n = metrics["signal_count"]
    passes_core = (
        n >= MIN_REVIEW_EVENTS
        and metrics["pf_x4"] >= MIN_PRECOMM_PF
        and metrics["win_rate_x4"] >= MIN_PRECOMM_WR
        and metrics["avg_net_x4"] >= MIN_PRECOMM_AVG
        and metrics["tail_pf_x4"] >= MIN_PRECOMM_TAIL_PF
        and cost1_pf >= MIN_PRECOMM_COST1_PF
        and metrics["max_drawdown_x4"] >= MAX_DRAWDOWN
    )
    passes_last5 = metrics["last5_pf_x4"] >= MIN_PRECOMM_LAST5_PF and metrics["last5_avg_net_x4"] >= MIN_PRECOMM_LAST5_AVG
    member_ok = member_count >= 2 and good_member_count >= 2 and weak_member_count <= 1

    if passes_core and passes_last5 and member_ok:
        decision = "PRECOMMERCIAL_REPAIR_FILTER_REVIEW_CANDIDATE_RESEARCH_ONLY"
        next_action = "RUN_STRICT_PREPAPER_GATE_ON_REPAIRED_FILTER_NO_EA_NO_PAPER_LIVE"
        queue = "precommercial_repair_filter_review"
    elif passes_core and member_ok:
        decision = "SHORT_CONFIRMATION_SHADOW_RESEARCH_ONLY"
        next_action = "COLLECT_SHORT_CONFIRMATION_OR_APPLY_RECENCY_FILTER"
        queue = "short_confirmation"
    elif n >= MIN_ACCEL_EVENTS and metrics["pf_x4"] >= 1.15 and metrics["win_rate_x4"] >= 0.55 and metrics["avg_net_x4"] > 0:
        decision = "ACCELERATE_COLLECTION_RESEARCH_ONLY"
        next_action = "KEEP_IN_PARALLEL_COLLECTION_QUEUE"
        queue = "accelerate_collection"
    else:
        decision = "REPAIR_OR_KILL_RESEARCH_ONLY"
        next_action = "MOVE_TO_REPAIR_OR_KILL_DO_NOT_WAIT"
        queue = "repair_or_kill"

    return {
        "set_name": cset.set_name,
        "purpose": cset.purpose,
        "family": cset.family,
        "sibling_group": cset.sibling_group,
        "candidate_list": ";".join(cset.candidates),
        "invert_net": bool(cset.invert),
        "member_count": member_count,
        "good_member_count": good_member_count,
        "weak_member_count": weak_member_count,
        "raw_rows": int(len(sub)),
        "effective_event_count": n,
        **metrics,
        "cost_1_pf_x4": cost1_pf,
        "passes_core": bool(passes_core),
        "passes_last5": bool(passes_last5),
        "member_ok": bool(member_ok),
        "stage34b_decision": decision,
        "queue": queue,
        "next_action": next_action,
        "commercial_status": "RESEARCH_ONLY_NO_EA_NO_PAPER_LIVE_NO_ORDER",
    }


def safe_markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 50) -> str:
    if df.empty:
        return "No rows."
    view = df.loc[:, [c for c in columns if c in df.columns]].head(max_rows).copy()
    return view.to_markdown(index=False)


def main() -> int:
    generated = now_utc()
    stage34a_summary = load_json(STAGE34A_SUMMARY_PATH)
    stage33e_summary = load_json(STAGE33E_SUMMARY_PATH)
    ledger, colmap = normalize_ledger(LEDGER_PATH)

    if ledger.empty:
        diagnostics = pd.DataFrame()
    else:
        rows = []
        for cset in build_sets(ledger):
            rec = evaluate_set(ledger, cset)
            if rec:
                rows.append(rec)
        diagnostics = pd.DataFrame(rows)
        if not diagnostics.empty:
            diagnostics = diagnostics.sort_values(
                ["queue", "pf_x4", "effective_event_count"], ascending=[True, False, False]
            ).reset_index(drop=True)

    precomm = diagnostics[diagnostics.get("queue", pd.Series(dtype=str)) == "precommercial_repair_filter_review"].copy() if not diagnostics.empty else pd.DataFrame()
    short = diagnostics[diagnostics.get("queue", pd.Series(dtype=str)) == "short_confirmation"].copy() if not diagnostics.empty else pd.DataFrame()
    accel = diagnostics[diagnostics.get("queue", pd.Series(dtype=str)) == "accelerate_collection"].copy() if not diagnostics.empty else pd.DataFrame()
    kill = diagnostics[diagnostics.get("queue", pd.Series(dtype=str)) == "repair_or_kill"].copy() if not diagnostics.empty else pd.DataFrame()

    if not precomm.empty:
        decision = "STAGE34B_HAS_PRECOMMERCIAL_REPAIR_FILTER_REVIEW_CANDIDATE_RESEARCH_ONLY"
        next_stage = "RUN_STRICT_PREPAPER_GATE_ON_REPAIR_FILTER_CANDIDATE_NO_EA_NO_PAPER_LIVE"
    elif not short.empty:
        decision = "STAGE34B_HAS_SHORT_CONFIRMATION_REPAIR_FILTER_PATH_RESEARCH_ONLY"
        next_stage = "CONTINUE_SHORT_CONFIRMATION_AND_PARALLEL_ACCELERATION_NO_EA_NO_PAPER_LIVE"
    elif not accel.empty:
        decision = "STAGE34B_HAS_ACCELERATION_ONLY_NO_REVIEW_CANDIDATE_RESEARCH_ONLY"
        next_stage = "KEEP_ACCELERATION_BACKGROUND_AND_START_CONTROLLED_INTAKE_EXPANSION"
    else:
        decision = "STAGE34B_NO_FAST_PATH_REPAIR_FILTER_RETURN_TO_INTAKE_EXPANSION_RESEARCH_ONLY"
        next_stage = "RETURN_TO_STAGE32B_CONTROLLED_INTAKE_EXPANSION_OR_NEW_FAMILY_DISCOVERY"

    # Write CSV/JSON artifacts.
    diagnostics.to_csv(REPORT_DIR / "repair_filter_candidate_diagnostics.csv", index=False)
    precomm.to_csv(REPORT_DIR / "precommercial_repair_filter_queue.csv", index=False)
    short.to_csv(REPORT_DIR / "short_confirmation_repair_filter_queue.csv", index=False)
    accel.to_csv(REPORT_DIR / "parallel_acceleration_queue.csv", index=False)
    kill.to_csv(REPORT_DIR / "repair_or_kill_queue.csv", index=False)

    action_rows = []
    if not precomm.empty:
        action_rows.append({"priority": 1, "action": "RUN_STRICT_PREPAPER_GATE_ON_TOP_REPAIR_FILTER", "rationale": "A repaired/inverted/subset filter passed core, cost, and recency checks.", "execution_status": "RESEARCH_ONLY"})
    if not short.empty:
        action_rows.append({"priority": 2, "action": "KEEP_SHORT_CONFIRMATION_PATHS_ACTIVE", "rationale": "Core metrics are promising but recency/last5 is not yet safe.", "execution_status": "RESEARCH_ONLY"})
    if not accel.empty:
        action_rows.append({"priority": 3, "action": "KEEP_PARALLEL_ACCELERATION_QUEUE", "rationale": "Some paths are positive but not review-ready; collect only if cheap/background.", "execution_status": "RESEARCH_ONLY"})
    if not kill.empty:
        action_rows.append({"priority": 4, "action": "KILL_OR_REPAIR_WEAK_PATHS", "rationale": "Do not wait for weak or single-variant paths to reach N=40 by default.", "execution_status": "RESEARCH_ONLY"})
    action_plan = pd.DataFrame(action_rows)
    action_plan.to_csv(REPORT_DIR / "stage34b_action_plan.csv", index=False)

    summary = {
        "generated_utc": generated,
        "decision": decision,
        **NO_EXECUTION_FLAGS,
        "primary_objective": "PARALLEL_REPAIR_FILTER_LAB_TO_REDUCE_TIME_TO_COMMERCIAL_DECISION",
        "recommended_next_stage": next_stage,
        "stage34a_decision": stage34a_summary.get("decision"),
        "stage33e_decision": stage33e_summary.get("decision"),
        "ledger_path": str(LEDGER_PATH),
        "ledger_available": not ledger.empty,
        "ledger_rows": int(len(ledger)),
        "ledger_column_map": colmap,
        "candidate_set_rows": int(len(diagnostics)),
        "precommercial_repair_filter_rows": int(len(precomm)),
        "short_confirmation_rows": int(len(short)),
        "accelerate_collection_rows": int(len(accel)),
        "repair_or_kill_rows": int(len(kill)),
        "thresholds": {
            "min_review_events": MIN_REVIEW_EVENTS,
            "min_accel_events": MIN_ACCEL_EVENTS,
            "min_precomm_pf": MIN_PRECOMM_PF,
            "min_precomm_wr": MIN_PRECOMM_WR,
            "min_precomm_avg": MIN_PRECOMM_AVG,
            "min_precomm_tail_pf": MIN_PRECOMM_TAIL_PF,
            "min_precomm_cost1_pf": MIN_PRECOMM_COST1_PF,
            "min_precomm_last5_pf": MIN_PRECOMM_LAST5_PF,
            "min_precomm_last5_avg": MIN_PRECOMM_LAST5_AVG,
            "max_drawdown": MAX_DRAWDOWN,
        },
    }
    (REPORT_DIR / "stage34b_summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False, default=str))

    cols = [
        "set_name", "purpose", "candidate_list", "invert_net", "effective_event_count",
        "good_member_count", "weak_member_count", "pf_x4", "avg_net_x4", "win_rate_x4",
        "tail_pf_x4", "cost_1_pf_x4", "last5_pf_x4", "last5_avg_net_x4",
        "max_drawdown_x4", "stage34b_decision", "next_action",
    ]
    kill_cols = [
        "set_name", "candidate_list", "invert_net", "effective_event_count", "pf_x4", "avg_net_x4",
        "win_rate_x4", "last5_pf_x4", "stage34b_decision", "next_action",
    ]
    md = f"""# XAUUSD Stage34B — Parallel Repair / Filter Lab

Generated UTC: {generated}

## Decision

```text
DECISION = {decision}
EXECUTION_STATUS = RESEARCH_ONLY
COMMERCIAL_TRANSITION_AUTHORIZED = False
NO_EA_CHANGE = True
NO_PAPER_LIVE = True
NO_ORDER_AUTHORIZATION = True
PRIMARY_OBJECTIVE = PARALLEL_REPAIR_FILTER_LAB_TO_REDUCE_TIME_TO_COMMERCIAL_DECISION
RECOMMENDED_NEXT_STAGE = {next_stage}
```

## Why this stage exists

Stage33E waits for short confirmation on h13+h14. Stage34B prevents passive waiting by testing repaired subsets, inversion ideas, and alternative dense-family filters from the existing ledger. This is research-only and does not authorize EA, paper-live, or orders.

## Summary

```text
ledger_available = {not ledger.empty}
ledger_rows = {len(ledger)}
candidate_set_rows = {len(diagnostics)}
precommercial_repair_filter_rows = {len(precomm)}
short_confirmation_rows = {len(short)}
accelerate_collection_rows = {len(accel)}
repair_or_kill_rows = {len(kill)}
```

## Pre-commercial repair-filter queue

{safe_markdown_table(precomm, cols)}

## Short confirmation repair-filter queue

{safe_markdown_table(short, cols)}

## Parallel acceleration queue

{safe_markdown_table(accel, cols, max_rows=25)}

## Repair / kill queue

{safe_markdown_table(kill, kill_cols, max_rows=40)}

## Action plan

{safe_markdown_table(action_plan, ["priority", "action", "rationale", "execution_status"])}

## Operational interpretation

```text
1. Stage33E remains the main confirmation path for h13+h14, but Stage34B runs repair/intake diagnostics in parallel.
2. No path here authorizes EA, paper-live, or orders.
3. If no pre-commercial repair-filter candidate exists, do not wait passively; keep only cheap background collection and start controlled intake expansion.
4. Weak paths should be killed or repaired quickly; no default single-variant N=40 waiting.
```

## Output files

- `data/reports/stage34b_parallel_repair_filter_lab/stage34b_parallel_repair_filter_lab.md`
- `data/reports/stage34b_parallel_repair_filter_lab/stage34b_summary.json`
- `data/reports/stage34b_parallel_repair_filter_lab/repair_filter_candidate_diagnostics.csv`
- `data/reports/stage34b_parallel_repair_filter_lab/precommercial_repair_filter_queue.csv`
- `data/reports/stage34b_parallel_repair_filter_lab/short_confirmation_repair_filter_queue.csv`
- `data/reports/stage34b_parallel_repair_filter_lab/parallel_acceleration_queue.csv`
- `data/reports/stage34b_parallel_repair_filter_lab/repair_or_kill_queue.csv`
- `data/reports/stage34b_parallel_repair_filter_lab/stage34b_action_plan.csv`
"""
    (REPORT_DIR / "stage34b_parallel_repair_filter_lab.md").write_text(md)

    print(f"DECISION={decision}")
    print(f"PRECOMMERCIAL_REPAIR_FILTER_ROWS={len(precomm)}")
    print(f"SHORT_CONFIRMATION_ROWS={len(short)}")
    print(f"ACCELERATE_COLLECTION_ROWS={len(accel)}")
    print(f"REPAIR_OR_KILL_ROWS={len(kill)}")
    print(f"REPORT={REPORT_DIR / 'stage34b_parallel_repair_filter_lab.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
