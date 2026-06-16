"""
Stage33B — Pre-Commercial Family Robustness Gate for XAUUSD dense families.

Purpose:
    Validate Stage33A family-level acceleration candidates before any EA/paper/live/order step.
    This stage is research-only and explicitly does not authorize execution.

Inputs expected under repo root:
    data/reports/stage33a_dense_family_robustness_gate/pre_commercial_acceleration_queue.csv
    data/reports/stage33a_dense_family_robustness_gate/stage33a_summary.json
    data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_signal_ledger.csv

Outputs:
    data/reports/stage33b_pre_commercial_family_robustness_gate/stage33b_pre_commercial_family_robustness_gate.md
    data/reports/stage33b_pre_commercial_family_robustness_gate/stage33b_summary.json
    data/reports/stage33b_pre_commercial_family_robustness_gate/family_robustness_diagnostics.csv/json
    data/reports/stage33b_pre_commercial_family_robustness_gate/member_split_summary.csv/json
    data/reports/stage33b_pre_commercial_family_robustness_gate/hour_split_summary.csv/json
    data/reports/stage33b_pre_commercial_family_robustness_gate/weekday_split_summary.csv/json
    data/reports/stage33b_pre_commercial_family_robustness_gate/tail_batch_summary.csv/json
    data/reports/stage33b_pre_commercial_family_robustness_gate/cost_sensitivity_summary.csv/json

Notes:
    - Uses timestamp+direction event deduplication to reduce sibling overlap inflation.
    - Uses cost stress as a conservative proxy if exact spread/slippage columns are unavailable.
    - Research-only: commercial_transition_authorized is always False.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd


REPORT_DIR = Path("data/reports/stage33b_pre_commercial_family_robustness_gate")
STAGE33A_DIR = Path("data/reports/stage33a_dense_family_robustness_gate")
DEFAULT_QUEUE = STAGE33A_DIR / "pre_commercial_acceleration_queue.csv"
DEFAULT_STAGE33A_SUMMARY = STAGE33A_DIR / "stage33a_summary.json"
DEFAULT_LEDGER = Path("data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_signal_ledger.csv")

COST_STRESS_X4 = [0.0, 0.25, 0.50, 0.75, 1.00]


@dataclass(frozen=True)
class Thresholds:
    min_effective_events: int = 36
    min_member_count: int = 2
    min_good_members: int = 2
    min_family_pf_x4: float = 1.35
    min_family_win_rate: float = 0.58
    min_family_tail_pf_x4: float = 1.00
    max_drawdown_x4: float = -35.0
    min_cost_stress_pf_x4: float = 1.10
    min_cost_stress_win_rate: float = 0.52
    max_weak_member_count: int = 1
    min_member_signal_count: int = 8
    min_member_pf_x4: float = 1.20
    min_member_win_rate: float = 0.55
    tail_n: int = 10
    batch_size: int = 10


TH = Thresholds()


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_report_dir() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def read_csv_if_exists(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def write_table(df: pd.DataFrame, stem: str) -> None:
    csv_path = REPORT_DIR / f"{stem}.csv"
    json_path = REPORT_DIR / f"{stem}.json"
    df.to_csv(csv_path, index=False)
    df.to_json(json_path, orient="records", force_ascii=False, indent=2)


def find_column(df: pd.DataFrame, candidates: Sequence[str], contains: Sequence[str] = ()) -> Optional[str]:
    lower_map = {str(c).lower(): c for c in df.columns}
    for name in candidates:
        if name.lower() in lower_map:
            return lower_map[name.lower()]
    if contains:
        for c in df.columns:
            lc = str(c).lower()
            if all(token.lower() in lc for token in contains):
                return c
    return None


def parse_candidate_list(value: Any) -> List[str]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return []
    text = str(value)
    parts = [p.strip() for p in re.split(r"[;,]", text) if p.strip()]
    # Drop ellipsis artifacts if any table truncation leaked into CSV. Real CSV should be complete.
    return [p for p in parts if p not in {"...", "…"}]


def safe_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def profit_factor(values: Iterable[float]) -> float:
    vals = [float(v) for v in values if pd.notna(v)]
    gains = sum(v for v in vals if v > 0)
    losses = -sum(v for v in vals if v < 0)
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


def max_drawdown(values: Iterable[float]) -> float:
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for v in values:
        if pd.isna(v):
            continue
        equity += float(v)
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return worst


def metrics(values: Iterable[float], tail_n: int = TH.tail_n) -> Dict[str, float]:
    vals = [float(v) for v in values if pd.notna(v)]
    if not vals:
        return {
            "signal_count": 0,
            "pf_x4": 0.0,
            "avg_net_x4": 0.0,
            "win_rate_x4": 0.0,
            "tail_pf_x4": 0.0,
            "max_drawdown_x4": 0.0,
        }
    tail_vals = vals[-tail_n:]
    return {
        "signal_count": int(len(vals)),
        "pf_x4": profit_factor(vals),
        "avg_net_x4": sum(vals) / len(vals),
        "win_rate_x4": sum(1 for v in vals if v > 0) / len(vals),
        "tail_pf_x4": profit_factor(tail_vals),
        "max_drawdown_x4": max_drawdown(vals),
    }


def normalize_ledger(ledger: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, str]]:
    if ledger.empty:
        return ledger, {}

    candidate_col = find_column(
        ledger,
        ["candidate", "candidate_id", "spec", "spec_id", "variant", "strategy", "signal_name"],
        contains=("candidate",),
    )
    family_col = find_column(ledger, ["family", "family_id", "pattern_family"], contains=("family",))
    # Stage32C ledger writes signal timestamps under `entry_time`. Earlier Stage33B only
    # searched generic ts/timestamp columns, which made real Stage32C ledgers look
    # unavailable even when rows existed. Keep broader aliases for forward compatibility.
    ts_col = find_column(
        ledger,
        [
            "entry_time",
            "entry_time_utc",
            "signal_entry_time",
            "signal_ts_utc",
            "signal_time_utc",
            "signal_ts",
            "ts_utc",
            "timestamp",
            "time",
            "datetime",
        ],
        contains=("time",),
    )
    direction_col = find_column(
        ledger,
        ["direction", "side", "signal_direction", "dir"],
        contains=("direction",),
    )
    net_col = find_column(
        ledger,
        ["net_x4", "outcome_net_x4", "resolved_net_x4", "net_result_x4", "result_x4", "r_x4", "pnl_x4"],
        contains=("net", "x4"),
    )

    if net_col is None:
        # Fallback: any x4 result-like column.
        net_col = find_column(ledger, [], contains=("x4",))
    if candidate_col is None or ts_col is None or net_col is None:
        return pd.DataFrame(), {
            "candidate_col": str(candidate_col),
            "family_col": str(family_col),
            "timestamp_col": str(ts_col),
            "direction_col": str(direction_col),
            "net_col": str(net_col),
            "error": "missing_required_ledger_columns",
        }

    out = ledger.copy()
    out["__candidate"] = out[candidate_col].astype(str)
    out["__family"] = out[family_col].astype(str) if family_col is not None else "unknown"
    out["__ts"] = pd.to_datetime(out[ts_col], errors="coerce", utc=True)
    out["__direction"] = out[direction_col].astype(str) if direction_col is not None else "na"
    out["__net_x4"] = safe_numeric(out[net_col])
    out = out.dropna(subset=["__ts", "__net_x4"])
    out = out.sort_values("__ts").reset_index(drop=True)
    return out, {
        "candidate_col": str(candidate_col),
        "family_col": str(family_col),
        "timestamp_col": str(ts_col),
        "direction_col": str(direction_col),
        "net_col": str(net_col),
    }


def dedup_family_events(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    tmp = df.copy()
    tmp["__event_key"] = tmp["__ts"].dt.strftime("%Y-%m-%dT%H:%M:%SZ") + "|" + tmp["__direction"].astype(str)
    grouped = []
    for key, g in tmp.groupby("__event_key", sort=True):
        g = g.sort_values("__ts")
        row = {
            "event_key": key,
            "signal_ts_utc": g["__ts"].iloc[0].strftime("%Y-%m-%dT%H:%M:%SZ"),
            "direction": str(g["__direction"].iloc[0]),
            "members_fired": ";".join(sorted(g["__candidate"].unique())),
            "member_fire_count": int(g["__candidate"].nunique()),
            # Mean avoids selecting the best sibling and reduces overlap inflation.
            "family_event_net_x4": float(g["__net_x4"].mean()),
            "family_event_net_min_x4": float(g["__net_x4"].min()),
            "family_event_net_max_x4": float(g["__net_x4"].max()),
        }
        grouped.append(row)
    return pd.DataFrame(grouped).sort_values("signal_ts_utc").reset_index(drop=True)


def summarize_split(df: pd.DataFrame, group_col: str, value_col: str = "family_event_net_x4") -> pd.DataFrame:
    rows = []
    if df.empty or group_col not in df.columns:
        return pd.DataFrame()
    for key, g in df.groupby(group_col, dropna=False, sort=True):
        m = metrics(g[value_col].tolist())
        rows.append({group_col: key, **m})
    return pd.DataFrame(rows)


def evaluate_member_quality(member_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if member_df.empty:
        return pd.DataFrame()
    for cand, g in member_df.groupby("__candidate", sort=True):
        m = metrics(g["__net_x4"].tolist())
        if (
            m["signal_count"] >= TH.min_member_signal_count
            and m["pf_x4"] >= TH.min_member_pf_x4
            and m["win_rate_x4"] >= TH.min_member_win_rate
        ):
            quality = "GOOD_MEMBER"
        elif m["pf_x4"] >= 1.0 and m["avg_net_x4"] >= 0:
            quality = "SECONDARY_MEMBER"
        else:
            quality = "WEAK_OR_REPAIR_MEMBER"
        rows.append({"candidate": cand, **m, "member_quality": quality})
    return pd.DataFrame(rows).sort_values(["member_quality", "pf_x4"], ascending=[True, False])


def cost_sensitivity(event_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if event_df.empty:
        return pd.DataFrame()
    vals = event_df["family_event_net_x4"].astype(float).tolist()
    for c in COST_STRESS_X4:
        stressed = [v - c for v in vals]
        m = metrics(stressed)
        rows.append({"cost_penalty_x4": c, **m})
    return pd.DataFrame(rows)


def tail_batches(event_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if event_df.empty:
        return pd.DataFrame()
    df = event_df.sort_values("signal_ts_utc").reset_index(drop=True).copy()
    for i in range(0, len(df), TH.batch_size):
        g = df.iloc[i : i + TH.batch_size]
        m = metrics(g["family_event_net_x4"].tolist())
        rows.append(
            {
                "batch_index": i // TH.batch_size + 1,
                "start_ts": g["signal_ts_utc"].iloc[0],
                "end_ts": g["signal_ts_utc"].iloc[-1],
                **m,
            }
        )
    return pd.DataFrame(rows)


def decision_for_family(fam_metrics: Dict[str, float], member_summary: pd.DataFrame, cost_df: pd.DataFrame) -> Tuple[str, str, bool]:
    good_members = int((member_summary.get("member_quality", pd.Series(dtype=str)) == "GOOD_MEMBER").sum()) if not member_summary.empty else 0
    weak_members = int((member_summary.get("member_quality", pd.Series(dtype=str)) == "WEAK_OR_REPAIR_MEMBER").sum()) if not member_summary.empty else 0
    member_count = int(len(member_summary))

    core_pass = (
        fam_metrics["signal_count"] >= TH.min_effective_events
        and member_count >= TH.min_member_count
        and good_members >= TH.min_good_members
        and weak_members <= TH.max_weak_member_count
        and fam_metrics["pf_x4"] >= TH.min_family_pf_x4
        and fam_metrics["win_rate_x4"] >= TH.min_family_win_rate
        and fam_metrics["tail_pf_x4"] >= TH.min_family_tail_pf_x4
        and fam_metrics["max_drawdown_x4"] >= TH.max_drawdown_x4
    )

    cost_pass = False
    if not cost_df.empty:
        row = cost_df.loc[cost_df["cost_penalty_x4"] == 0.50]
        if not row.empty:
            cost_pass = bool(
                float(row["pf_x4"].iloc[0]) >= TH.min_cost_stress_pf_x4
                and float(row["win_rate_x4"].iloc[0]) >= TH.min_cost_stress_win_rate
                and float(row["avg_net_x4"].iloc[0]) > 0
            )

    if core_pass and cost_pass:
        return (
            "STAGE33B_FAMILY_PRE_COMMERCIAL_ROBUSTNESS_CANDIDATE_RESEARCH_ONLY",
            "RUN_STAGE33C_STRICT_COST_AWARE_PRE_PAPER_GATE_NO_EA_NO_PAPER_LIVE",
            True,
        )
    if core_pass and not cost_pass:
        return (
            "STAGE33B_CORE_ROBUST_BUT_COST_STRESS_INCONCLUSIVE_RESEARCH_ONLY",
            "RUN_COST_SPREAD_AWARE_REPAIR_OR_COLLECT_MORE_COST_DATA_NO_EA_NO_PAPER_LIVE",
            False,
        )
    return (
        "STAGE33B_FAMILY_REPAIR_OR_KILL_RESEARCH_ONLY",
        "KILL_OR_REPAIR_FAMILY_DO_NOT_WAIT_FOR_SINGLE_VARIANT_N40",
        False,
    )


def process_family(queue_row: pd.Series, ledger: pd.DataFrame) -> Dict[str, Any]:
    candidates = parse_candidate_list(queue_row.get("candidate_list"))
    sibling_group = str(queue_row.get("sibling_group", "unknown"))
    family_name = str(queue_row.get("families", queue_row.get("family", "unknown")))

    raw = ledger[ledger["__candidate"].isin(candidates)].copy()
    event_df = dedup_family_events(raw)
    if not event_df.empty:
        event_df["hour_utc"] = pd.to_datetime(event_df["signal_ts_utc"], utc=True).dt.hour
        event_df["weekday_utc"] = pd.to_datetime(event_df["signal_ts_utc"], utc=True).dt.day_name().str.lower()

    fam_m = metrics(event_df["family_event_net_x4"].tolist() if not event_df.empty else [])
    member_summary = evaluate_member_quality(raw)
    hour_summary = summarize_split(event_df, "hour_utc")
    weekday_summary = summarize_split(event_df, "weekday_utc")
    batch_summary = tail_batches(event_df)
    cost_df = cost_sensitivity(event_df)
    decision, next_action, passes_precommercial_research = decision_for_family(fam_m, member_summary, cost_df)

    diagnostic = {
        "sibling_group": sibling_group,
        "families": family_name,
        "candidate_list": ";".join(candidates),
        "member_count": len(candidates),
        "raw_ledger_rows": int(len(raw)),
        "effective_event_count": int(fam_m["signal_count"]),
        "family_pf_x4": fam_m["pf_x4"],
        "family_avg_net_x4": fam_m["avg_net_x4"],
        "family_win_rate_x4": fam_m["win_rate_x4"],
        "family_tail_pf_x4": fam_m["tail_pf_x4"],
        "family_max_drawdown_x4": fam_m["max_drawdown_x4"],
        "good_member_count": int((member_summary.get("member_quality", pd.Series(dtype=str)) == "GOOD_MEMBER").sum()) if not member_summary.empty else 0,
        "secondary_member_count": int((member_summary.get("member_quality", pd.Series(dtype=str)) == "SECONDARY_MEMBER").sum()) if not member_summary.empty else 0,
        "weak_member_count": int((member_summary.get("member_quality", pd.Series(dtype=str)) == "WEAK_OR_REPAIR_MEMBER").sum()) if not member_summary.empty else 0,
        "stage33b_decision": decision,
        "next_action": next_action,
        "passes_precommercial_research_gate": passes_precommercial_research,
        "commercial_status": "RESEARCH_ONLY_NO_EA_NO_PAPER_LIVE_NO_ORDER",
    }
    return {
        "diagnostic": diagnostic,
        "events": event_df,
        "member_summary": member_summary.assign(sibling_group=sibling_group) if not member_summary.empty else member_summary,
        "hour_summary": hour_summary.assign(sibling_group=sibling_group) if not hour_summary.empty else hour_summary,
        "weekday_summary": weekday_summary.assign(sibling_group=sibling_group) if not weekday_summary.empty else weekday_summary,
        "batch_summary": batch_summary.assign(sibling_group=sibling_group) if not batch_summary.empty else batch_summary,
        "cost_sensitivity": cost_df.assign(sibling_group=sibling_group) if not cost_df.empty else cost_df,
    }


def markdown_table(df: pd.DataFrame, max_rows: int = 20) -> str:
    if df.empty:
        return "No rows."
    return df.head(max_rows).to_markdown(index=False)


def build_report(summary: Dict[str, Any], diagnostics: pd.DataFrame, member_summary: pd.DataFrame, cost_summary: pd.DataFrame, batch_summary: pd.DataFrame) -> str:
    return f"""# XAUUSD Stage33B — Pre-Commercial Family Robustness Gate

Generated UTC: {summary['generated_utc']}

## Decision

```text
DECISION = {summary['decision']}
EXECUTION_STATUS = RESEARCH_ONLY
COMMERCIAL_TRANSITION_AUTHORIZED = False
NO_EA_CHANGE = True
NO_PAPER_LIVE = True
NO_ORDER_AUTHORIZATION = True
PRIMARY_OBJECTIVE = STRICT_FAMILY_ROBUSTNESS_BEFORE_ANY_PRE_PAPER_STEP
RECOMMENDED_NEXT_STAGE = {summary['recommended_next_stage']}
```

## Why this stage exists

Stage33A reduced time-to-decision by promoting a dense sibling family for review. Stage33B stress-tests that family before any EA, paper-live, or order-routing work. It checks member consistency, deduplicated family events, hour/day splits, tail batches, drawdown, and cost sensitivity.

## Summary

```text
stage33a_decision = {summary.get('stage33a_decision')}
family_review_rows = {summary['family_review_rows']}
precommercial_research_candidate_rows = {summary['precommercial_research_candidate_rows']}
repair_or_kill_rows = {summary['repair_or_kill_rows']}
ledger_available = {summary['ledger_available']}
ledger_rows = {summary['ledger_rows']}
min_effective_events = {TH.min_effective_events}
min_good_members = {TH.min_good_members}
min_family_pf_x4 = {TH.min_family_pf_x4}
min_family_win_rate = {TH.min_family_win_rate}
min_cost_stress_pf_x4 = {TH.min_cost_stress_pf_x4}
```

## Family diagnostics

{markdown_table(diagnostics)}

## Member split summary

{markdown_table(member_summary)}

## Cost sensitivity summary

{markdown_table(cost_summary)}

## Tail batch summary

{markdown_table(batch_summary)}

## Operational interpretation

```text
1. This stage can accelerate decision-making, but it does not authorize commercial transition.
2. A passing family moves only to a stricter cost-aware pre-paper gate.
3. A failing family should be killed or repaired quickly; do not wait weeks for single-variant N=40.
4. Stage32F remains a background collector only.
```

## Output files

- `data/reports/stage33b_pre_commercial_family_robustness_gate/stage33b_pre_commercial_family_robustness_gate.md`
- `data/reports/stage33b_pre_commercial_family_robustness_gate/stage33b_summary.json`
- `data/reports/stage33b_pre_commercial_family_robustness_gate/family_robustness_diagnostics.csv`
- `data/reports/stage33b_pre_commercial_family_robustness_gate/member_split_summary.csv`
- `data/reports/stage33b_pre_commercial_family_robustness_gate/hour_split_summary.csv`
- `data/reports/stage33b_pre_commercial_family_robustness_gate/weekday_split_summary.csv`
- `data/reports/stage33b_pre_commercial_family_robustness_gate/tail_batch_summary.csv`
- `data/reports/stage33b_pre_commercial_family_robustness_gate/cost_sensitivity_summary.csv`
"""


def run(args: argparse.Namespace) -> Dict[str, Any]:
    ensure_report_dir()
    queue_path = Path(args.queue)
    stage33a_summary_path = Path(args.stage33a_summary)
    ledger_path = Path(args.ledger)

    stage33a_summary = read_json(stage33a_summary_path)
    queue = read_csv_if_exists(queue_path)
    raw_ledger = read_csv_if_exists(ledger_path)
    ledger, column_map = normalize_ledger(raw_ledger)

    all_diagnostics: List[Dict[str, Any]] = []
    member_parts: List[pd.DataFrame] = []
    hour_parts: List[pd.DataFrame] = []
    weekday_parts: List[pd.DataFrame] = []
    batch_parts: List[pd.DataFrame] = []
    cost_parts: List[pd.DataFrame] = []

    if not queue.empty and not ledger.empty:
        for _, row in queue.iterrows():
            result = process_family(row, ledger)
            all_diagnostics.append(result["diagnostic"])
            for key, store in [
                ("member_summary", member_parts),
                ("hour_summary", hour_parts),
                ("weekday_summary", weekday_parts),
                ("batch_summary", batch_parts),
                ("cost_sensitivity", cost_parts),
            ]:
                df = result[key]
                if not df.empty:
                    store.append(df)

    diagnostics = pd.DataFrame(all_diagnostics)
    member_summary = pd.concat(member_parts, ignore_index=True) if member_parts else pd.DataFrame()
    hour_summary = pd.concat(hour_parts, ignore_index=True) if hour_parts else pd.DataFrame()
    weekday_summary = pd.concat(weekday_parts, ignore_index=True) if weekday_parts else pd.DataFrame()
    batch_summary = pd.concat(batch_parts, ignore_index=True) if batch_parts else pd.DataFrame()
    cost_summary = pd.concat(cost_parts, ignore_index=True) if cost_parts else pd.DataFrame()

    if diagnostics.empty:
        decision = "STAGE33B_NO_REVIEWABLE_FAMILY_OR_LEDGER_MISSING_RESEARCH_ONLY"
        next_stage = "RETURN_TO_STAGE33A_OR_FIX_LEDGER_INPUTS"
        pre_rows = 0
        repair_rows = 0
    else:
        pre_rows = int((diagnostics["stage33b_decision"] == "STAGE33B_FAMILY_PRE_COMMERCIAL_ROBUSTNESS_CANDIDATE_RESEARCH_ONLY").sum())
        repair_rows = int((diagnostics["stage33b_decision"] == "STAGE33B_FAMILY_REPAIR_OR_KILL_RESEARCH_ONLY").sum())
        inconclusive_rows = int((diagnostics["stage33b_decision"] == "STAGE33B_CORE_ROBUST_BUT_COST_STRESS_INCONCLUSIVE_RESEARCH_ONLY").sum())
        if pre_rows > 0:
            decision = "STAGE33B_HAS_PRE_COMMERCIAL_FAMILY_ROBUSTNESS_CANDIDATE_RESEARCH_ONLY"
            next_stage = "RUN_STAGE33C_STRICT_COST_AWARE_PRE_PAPER_GATE"
        elif inconclusive_rows > 0:
            decision = "STAGE33B_CORE_ROBUST_BUT_COST_STRESS_INCONCLUSIVE_RESEARCH_ONLY"
            next_stage = "RUN_COST_SPREAD_AWARE_REPAIR_OR_COLLECT_MORE_COST_DATA"
        else:
            decision = "STAGE33B_REPAIR_OR_KILL_FAMILY_RESEARCH_ONLY"
            next_stage = "RETURN_TO_STAGE32B_INTAKE_EXPANSION_OR_REPAIR"

    write_table(diagnostics, "family_robustness_diagnostics")
    write_table(member_summary, "member_split_summary")
    write_table(hour_summary, "hour_split_summary")
    write_table(weekday_summary, "weekday_split_summary")
    write_table(batch_summary, "tail_batch_summary")
    write_table(cost_summary, "cost_sensitivity_summary")

    summary = {
        "generated_utc": now_utc(),
        "decision": decision,
        "execution_status": "RESEARCH_ONLY",
        "commercial_transition_authorized": False,
        "no_ea_change": True,
        "no_paper_live": True,
        "no_order_authorization": True,
        "primary_objective": "STRICT_FAMILY_ROBUSTNESS_BEFORE_ANY_PRE_PAPER_STEP",
        "recommended_next_stage": next_stage,
        "stage33a_decision": stage33a_summary.get("decision"),
        "family_review_rows": int(len(diagnostics)),
        "precommercial_research_candidate_rows": pre_rows,
        "repair_or_kill_rows": repair_rows,
        "queue_path": str(queue_path),
        "stage33a_summary_path": str(stage33a_summary_path),
        "ledger_path": str(ledger_path),
        "ledger_available": bool(not ledger.empty),
        "ledger_rows": int(len(raw_ledger)) if raw_ledger is not None else 0,
        "normalized_ledger_rows": int(len(ledger)),
        "ledger_column_map": column_map,
        "thresholds": TH.__dict__,
    }
    with (REPORT_DIR / "stage33b_summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    report = build_report(summary, diagnostics, member_summary, cost_summary, batch_summary)
    (REPORT_DIR / "stage33b_pre_commercial_family_robustness_gate.md").write_text(report, encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Stage33B pre-commercial family robustness gate")
    p.add_argument("--queue", default=str(DEFAULT_QUEUE))
    p.add_argument("--stage33a-summary", default=str(DEFAULT_STAGE33A_SUMMARY))
    p.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    return p.parse_args()


def main() -> None:
    summary = run(parse_args())
    print(f"DECISION={summary['decision']}")
    print(f"PRECOMMERCIAL_RESEARCH_CANDIDATE_ROWS={summary['precommercial_research_candidate_rows']}")
    print(f"REPAIR_OR_KILL_ROWS={summary['repair_or_kill_rows']}")
    print(f"RECOMMENDED_NEXT_STAGE={summary['recommended_next_stage']}")
    print(f"REPORT={REPORT_DIR / 'stage33b_pre_commercial_family_robustness_gate.md'}")


if __name__ == "__main__":
    main()
