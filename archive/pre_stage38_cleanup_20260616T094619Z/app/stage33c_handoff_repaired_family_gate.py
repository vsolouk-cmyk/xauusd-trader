"""
XAUUSD Stage33C — Handoff Repaired Family Gate

Purpose:
    After Stage33B rejects the full h13/h14/h15 handoff family, test the
    repaired h13+h14 family only. This is a research-only acceleration gate.

Inputs:
    data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_signal_ledger.csv
    data/reports/stage33b_pre_commercial_family_robustness_gate/stage33b_summary.json

Outputs:
    data/reports/stage33c_handoff_repaired_family_gate/stage33c_handoff_repaired_family_gate.md
    data/reports/stage33c_handoff_repaired_family_gate/stage33c_summary.json
    data/reports/stage33c_handoff_repaired_family_gate/repaired_family_diagnostics.csv
    data/reports/stage33c_handoff_repaired_family_gate/repaired_member_split_summary.csv
    data/reports/stage33c_handoff_repaired_family_gate/repaired_tail_batch_summary.csv
    data/reports/stage33c_handoff_repaired_family_gate/repaired_cost_sensitivity_summary.csv

No EA, paper-live, or order authorization is produced by this stage.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

REPAIRED_CANDIDATES = [
    "handoff_align_follow_h13_tp06_sl065",
    "handoff_align_follow_h14_tp06_sl065",
]
EXCLUDED_CANDIDATES = ["handoff_align_follow_h15_tp06_sl065"]
SIBLING_GROUP = "session_handoff_imbalance_v1::handoff_align_follow_h13_h14_repaired_tp06_sl065"
FAMILY = "session_handoff_imbalance_v1"

DEFAULT_LEDGER = Path("data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_signal_ledger.csv")
DEFAULT_STAGE33B_SUMMARY = Path("data/reports/stage33b_pre_commercial_family_robustness_gate/stage33b_summary.json")
DEFAULT_OUT_DIR = Path("data/reports/stage33c_handoff_repaired_family_gate")


@dataclass
class Thresholds:
    min_effective_events: int = 24
    min_member_count: int = 2
    min_good_members: int = 2
    min_family_pf_x4: float = 1.45
    min_family_win_rate: float = 0.60
    min_family_tail_pf_x4: float = 1.0
    max_drawdown_x4: float = -35.0
    min_cost_stress_pf_x4: float = 1.15
    min_cost_stress_win_rate: float = 0.52
    max_weak_member_count: int = 0
    min_member_signal_count: int = 8
    min_member_pf_x4: float = 1.2
    min_member_win_rate: float = 0.55
    tail_n: int = 10
    batch_size: int = 10


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def infer_col(cols: Iterable[str], candidates: Iterable[str]) -> Optional[str]:
    lookup = {str(c).lower(): c for c in cols}
    for name in candidates:
        if name.lower() in lookup:
            return lookup[name.lower()]
    return None


def normalize_ledger(path: Path) -> Tuple[pd.DataFrame, dict]:
    info = {
        "ledger_path": str(path),
        "ledger_exists": path.exists(),
        "ledger_rows": 0,
        "normalized_ledger_rows": 0,
        "ledger_available": False,
        "ledger_column_map": {},
    }
    if not path.exists():
        info["ledger_column_map"] = {"error": "ledger_file_missing"}
        return pd.DataFrame(), info

    raw = pd.read_csv(path)
    info["ledger_rows"] = int(len(raw))
    cols = list(raw.columns)
    candidate_col = infer_col(cols, ["candidate", "candidate_id", "variant", "spec", "spec_id"])
    family_col = infer_col(cols, ["family", "family_id", "pattern_family"])
    ts_col = infer_col(cols, ["entry_time", "entry_time_utc", "timestamp", "signal_ts_utc", "ts_utc", "time", "datetime"])
    direction_col = infer_col(cols, ["direction", "side", "signal_direction"])
    net_col = infer_col(cols, ["net_x4", "net_R_x4", "net_r_x4", "net", "r", "outcome_net_x4"])

    info["ledger_column_map"] = {
        "candidate_col": str(candidate_col),
        "family_col": str(family_col),
        "timestamp_col": str(ts_col),
        "direction_col": str(direction_col),
        "net_col": str(net_col),
    }
    missing = [name for name, col in [("candidate", candidate_col), ("timestamp", ts_col), ("direction", direction_col), ("net", net_col)] if col is None]
    if missing:
        info["ledger_column_map"]["error"] = "missing_required_ledger_columns:" + ",".join(missing)
        return pd.DataFrame(), info

    df = pd.DataFrame({
        "candidate": raw[candidate_col].astype(str),
        "family": raw[family_col].astype(str) if family_col is not None else FAMILY,
        "entry_time": pd.to_datetime(raw[ts_col], utc=True, errors="coerce"),
        "direction": raw[direction_col].astype(str),
        "net_x4": pd.to_numeric(raw[net_col], errors="coerce"),
    })
    df = df.dropna(subset=["entry_time", "net_x4"]).copy()
    df = df[df["candidate"].isin(REPAIRED_CANDIDATES + EXCLUDED_CANDIDATES)].copy()
    df["hour"] = df["entry_time"].dt.hour
    df["weekday"] = df["entry_time"].dt.day_name().str.lower()
    info["normalized_ledger_rows"] = int(len(df))
    info["ledger_available"] = bool(len(df) > 0)
    return df, info


def metrics(values: pd.Series, tail_n: int = 10) -> Dict[str, float]:
    vals = pd.to_numeric(values, errors="coerce").dropna().astype(float).tolist()
    n = len(vals)
    if n == 0:
        return {
            "signal_count": 0,
            "pf_x4": math.nan,
            "avg_net_x4": math.nan,
            "win_rate_x4": math.nan,
            "tail_pf_x4": math.nan,
            "max_drawdown_x4": math.nan,
        }
    pos = sum(v for v in vals if v > 0)
    neg = -sum(v for v in vals if v < 0)
    pf = pos / neg if neg > 0 else (math.inf if pos > 0 else math.nan)
    wins = sum(1 for v in vals if v > 0)
    avg = sum(vals) / n
    # Max drawdown on cumulative net sequence.
    peak = 0.0
    cum = 0.0
    max_dd = 0.0
    for v in vals:
        cum += v
        peak = max(peak, cum)
        max_dd = min(max_dd, cum - peak)
    tail_vals = vals[-tail_n:] if n >= 1 else []
    tail_pos = sum(v for v in tail_vals if v > 0)
    tail_neg = -sum(v for v in tail_vals if v < 0)
    tail_pf = tail_pos / tail_neg if tail_neg > 0 else (math.inf if tail_pos > 0 else math.nan)
    return {
        "signal_count": int(n),
        "pf_x4": float(pf),
        "avg_net_x4": float(avg),
        "win_rate_x4": float(wins / n),
        "tail_pf_x4": float(tail_pf),
        "max_drawdown_x4": float(max_dd),
    }


def qualify_member(row: dict, th: Thresholds) -> str:
    if row["signal_count"] >= th.min_member_signal_count and row["pf_x4"] >= th.min_member_pf_x4 and row["win_rate_x4"] >= th.min_member_win_rate:
        return "GOOD_MEMBER"
    return "WEAK_OR_REPAIR_MEMBER"


def batch_summary(df: pd.DataFrame, th: Thresholds) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    rows = []
    ordered = df.sort_values("entry_time").reset_index(drop=True)
    for i in range(0, len(ordered), th.batch_size):
        chunk = ordered.iloc[i : i + th.batch_size]
        m = metrics(chunk["net_x4"], th.tail_n)
        rows.append({
            "batch_index": int(i // th.batch_size + 1),
            "start_ts": chunk["entry_time"].iloc[0].strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end_ts": chunk["entry_time"].iloc[-1].strftime("%Y-%m-%dT%H:%M:%SZ"),
            **m,
            "sibling_group": SIBLING_GROUP,
        })
    return pd.DataFrame(rows)


def cost_summary(df: pd.DataFrame, th: Thresholds) -> pd.DataFrame:
    rows = []
    for penalty in [0.0, 0.25, 0.5, 0.75, 1.0]:
        adjusted = df["net_x4"] - penalty
        rows.append({"cost_penalty_x4": penalty, **metrics(adjusted, th.tail_n), "sibling_group": SIBLING_GROUP})
    return pd.DataFrame(rows)


def finite(v: float) -> float:
    if isinstance(v, (int, float)) and math.isinf(v):
        return 999999.0
    return v


def md_table(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "No rows."
    show = df.copy()
    for c in show.columns:
        if pd.api.types.is_float_dtype(show[c]):
            show[c] = show[c].map(lambda x: "" if pd.isna(x) else ("inf" if math.isinf(float(x)) else round(float(x), 6)))
    return show.to_markdown(index=False)


def run(args: argparse.Namespace) -> dict:
    th = Thresholds(
        min_effective_events=args.min_effective_events,
        min_family_pf_x4=args.min_family_pf_x4,
        min_family_win_rate=args.min_family_win_rate,
        min_family_tail_pf_x4=args.min_family_tail_pf_x4,
        max_drawdown_x4=args.max_drawdown_x4,
        min_cost_stress_pf_x4=args.min_cost_stress_pf_x4,
    )
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ledger, ledger_info = normalize_ledger(Path(args.ledger))
    stage33b_summary = read_json(Path(args.stage33b_summary))

    repaired = ledger[ledger["candidate"].isin(REPAIRED_CANDIDATES)].copy() if not ledger.empty else pd.DataFrame()
    repaired = repaired.drop_duplicates(subset=["entry_time", "direction", "candidate"]).sort_values("entry_time") if not repaired.empty else repaired
    # Deduplicate family-level simultaneous h13/h14 signals by timestamp+direction, keeping the better realized net.
    if not repaired.empty:
        family_events = repaired.sort_values("net_x4", ascending=False).drop_duplicates(subset=["entry_time", "direction"]).sort_values("entry_time")
    else:
        family_events = repaired

    member_rows = []
    for cand in REPAIRED_CANDIDATES:
        cdf = repaired[repaired["candidate"] == cand] if not repaired.empty else pd.DataFrame()
        m = metrics(cdf["net_x4"] if not cdf.empty else pd.Series(dtype=float), th.tail_n)
        row = {"candidate": cand, **m, "sibling_group": SIBLING_GROUP}
        row["member_quality"] = qualify_member(row, th)
        member_rows.append(row)
    member_df = pd.DataFrame(member_rows)

    fam = metrics(family_events["net_x4"] if not family_events.empty else pd.Series(dtype=float), th.tail_n)
    good_members = int((member_df["member_quality"] == "GOOD_MEMBER").sum()) if not member_df.empty else 0
    weak_members = int((member_df["member_quality"] != "GOOD_MEMBER").sum()) if not member_df.empty else len(REPAIRED_CANDIDATES)
    cost_df = cost_summary(family_events, th) if not family_events.empty else pd.DataFrame()
    tail_df = batch_summary(family_events, th) if not family_events.empty else pd.DataFrame()
    cost_1 = cost_df[cost_df["cost_penalty_x4"] == 1.0].iloc[0].to_dict() if not cost_df.empty else {}
    last_batch = tail_df.iloc[-1].to_dict() if not tail_df.empty else {}

    passes = bool(
        fam["signal_count"] >= th.min_effective_events
        and good_members >= th.min_good_members
        and weak_members <= th.max_weak_member_count
        and fam["pf_x4"] >= th.min_family_pf_x4
        and fam["win_rate_x4"] >= th.min_family_win_rate
        and fam["tail_pf_x4"] >= th.min_family_tail_pf_x4
        and fam["max_drawdown_x4"] >= th.max_drawdown_x4
        and cost_1.get("pf_x4", -999) >= th.min_cost_stress_pf_x4
        and cost_1.get("win_rate_x4", -999) >= th.min_cost_stress_win_rate
    )
    near_miss = bool(
        not passes
        and fam["signal_count"] >= th.min_effective_events
        and good_members >= th.min_good_members
        and fam["pf_x4"] >= th.min_family_pf_x4
        and fam["win_rate_x4"] >= th.min_family_win_rate
        and fam["max_drawdown_x4"] >= th.max_drawdown_x4
    )

    if not ledger_info.get("ledger_available"):
        decision = "STAGE33C_LEDGER_MISSING_RESEARCH_ONLY"
        next_stage = "FIX_LEDGER_INPUTS"
    elif passes:
        decision = "STAGE33C_REPAIRED_FAMILY_PRE_PAPER_RESEARCH_CANDIDATE_ONLY"
        next_stage = "RUN_STAGE33D_STRICT_COST_AWARE_PRE_PAPER_GATE_NO_EA_NO_PAPER_LIVE"
    elif near_miss:
        decision = "STAGE33C_REPAIRED_FAMILY_NEAR_MISS_KEEP_SHORT_SHADOW_RESEARCH_ONLY"
        next_stage = "COLLECT_SHORT_BATCH_OR_TIGHTEN_H13_H14_FILTERS_NO_EA_NO_PAPER_LIVE"
    else:
        decision = "STAGE33C_REPAIRED_FAMILY_FAIL_REPAIR_OR_KILL_RESEARCH_ONLY"
        next_stage = "RETURN_TO_STAGE32B_INTAKE_EXPANSION_OR_REPAIR"

    diag_df = pd.DataFrame([
        {
            "sibling_group": SIBLING_GROUP,
            "family": FAMILY,
            "included_candidates": ";".join(REPAIRED_CANDIDATES),
            "excluded_candidates": ";".join(EXCLUDED_CANDIDATES),
            "raw_repaired_rows": int(len(repaired)),
            "effective_event_count": int(fam["signal_count"]),
            "family_pf_x4": fam["pf_x4"],
            "family_avg_net_x4": fam["avg_net_x4"],
            "family_win_rate_x4": fam["win_rate_x4"],
            "family_tail_pf_x4": fam["tail_pf_x4"],
            "family_max_drawdown_x4": fam["max_drawdown_x4"],
            "cost_1_pf_x4": cost_1.get("pf_x4"),
            "cost_1_avg_net_x4": cost_1.get("avg_net_x4"),
            "cost_1_win_rate_x4": cost_1.get("win_rate_x4"),
            "last_batch_pf_x4": last_batch.get("pf_x4"),
            "last_batch_avg_net_x4": last_batch.get("avg_net_x4"),
            "last_batch_win_rate_x4": last_batch.get("win_rate_x4"),
            "good_member_count": good_members,
            "weak_member_count": weak_members,
            "stage33c_decision": decision,
            "next_stage": next_stage,
            "passes_repaired_prepaper_research_gate": passes,
            "commercial_status": "RESEARCH_ONLY_NO_EA_NO_PAPER_LIVE_NO_ORDER",
        }
    ])

    # Write CSV/JSON outputs.
    diag_df.to_csv(out_dir / "repaired_family_diagnostics.csv", index=False)
    member_df.to_csv(out_dir / "repaired_member_split_summary.csv", index=False)
    cost_df.to_csv(out_dir / "repaired_cost_sensitivity_summary.csv", index=False)
    tail_df.to_csv(out_dir / "repaired_tail_batch_summary.csv", index=False)
    if not family_events.empty:
        family_events.to_csv(out_dir / "repaired_family_events.csv", index=False)

    summary = {
        "generated_utc": now_utc(),
        "decision": decision,
        "execution_status": "RESEARCH_ONLY",
        "commercial_transition_authorized": False,
        "no_ea_change": True,
        "no_paper_live": True,
        "no_order_authorization": True,
        "primary_objective": "REPAIR_HANDED_OFF_H13_H14_FAMILY_TO_REDUCE_TIME_TO_DECISION",
        "recommended_next_stage": next_stage,
        "stage33b_decision": stage33b_summary.get("decision"),
        "ledger_available": ledger_info.get("ledger_available"),
        "ledger_rows": ledger_info.get("ledger_rows"),
        "normalized_ledger_rows": ledger_info.get("normalized_ledger_rows"),
        "ledger_column_map": ledger_info.get("ledger_column_map"),
        "included_candidates": REPAIRED_CANDIDATES,
        "excluded_candidates": EXCLUDED_CANDIDATES,
        "effective_event_count": int(fam["signal_count"]),
        "good_member_count": good_members,
        "weak_member_count": weak_members,
        "family_pf_x4": fam["pf_x4"],
        "family_win_rate_x4": fam["win_rate_x4"],
        "family_tail_pf_x4": fam["tail_pf_x4"],
        "family_max_drawdown_x4": fam["max_drawdown_x4"],
        "cost_1_pf_x4": cost_1.get("pf_x4"),
        "last_batch_pf_x4": last_batch.get("pf_x4"),
        "thresholds": th.__dict__,
    }
    (out_dir / "stage33c_summary.json").write_text(json.dumps(summary, indent=2, default=lambda x: None if pd.isna(x) else x))

    md = f"""# XAUUSD Stage33C — Handoff Repaired Family Gate

Generated UTC: {summary['generated_utc']}

## Decision

```text
DECISION = {decision}
EXECUTION_STATUS = RESEARCH_ONLY
COMMERCIAL_TRANSITION_AUTHORIZED = False
NO_EA_CHANGE = True
NO_PAPER_LIVE = True
NO_ORDER_AUTHORIZATION = True
PRIMARY_OBJECTIVE = REPAIR_HANDED_OFF_H13_H14_FAMILY_TO_REDUCE_TIME_TO_DECISION
RECOMMENDED_NEXT_STAGE = {next_stage}
```

## Why this stage exists

Stage33B rejected the full h13/h14/h15 family because the h15 sibling and the latest tail batch weakened robustness. Stage33C tests the repaired h13+h14 family only. It does not authorize EA, paper-live, or orders.

## Summary

```text
stage33b_decision = {summary.get('stage33b_decision')}
ledger_available = {summary['ledger_available']}
ledger_rows = {summary['ledger_rows']}
normalized_ledger_rows = {summary['normalized_ledger_rows']}
included_candidates = {', '.join(REPAIRED_CANDIDATES)}
excluded_candidates = {', '.join(EXCLUDED_CANDIDATES)}
effective_event_count = {summary['effective_event_count']}
good_member_count = {summary['good_member_count']}
weak_member_count = {summary['weak_member_count']}
family_pf_x4 = {round(summary['family_pf_x4'], 6) if summary['family_pf_x4'] == summary['family_pf_x4'] else 'nan'}
family_win_rate_x4 = {round(summary['family_win_rate_x4'], 6) if summary['family_win_rate_x4'] == summary['family_win_rate_x4'] else 'nan'}
family_tail_pf_x4 = {round(summary['family_tail_pf_x4'], 6) if summary['family_tail_pf_x4'] == summary['family_tail_pf_x4'] else 'nan'}
family_max_drawdown_x4 = {round(summary['family_max_drawdown_x4'], 6) if summary['family_max_drawdown_x4'] == summary['family_max_drawdown_x4'] else 'nan'}
cost_1_pf_x4 = {round(summary['cost_1_pf_x4'], 6) if summary.get('cost_1_pf_x4') == summary.get('cost_1_pf_x4') else 'nan'}
last_batch_pf_x4 = {round(summary['last_batch_pf_x4'], 6) if summary.get('last_batch_pf_x4') == summary.get('last_batch_pf_x4') else 'nan'}
```

## Repaired family diagnostics

{md_table(diag_df)}

## Repaired member split summary

{md_table(member_df)}

## Cost sensitivity summary

{md_table(cost_df)}

## Tail batch summary

{md_table(tail_df)}

## Operational interpretation

```text
1. If h13+h14 pass, move only to a stricter pre-paper research gate; no execution authorization.
2. If h13+h14 fail or only near-miss, do not wait for h15 or single-variant N=40.
3. Stage32F remains a background collector only.
4. This stage exists to reduce time-to-decision and enforce kill/repair discipline.
```

## Output files

- `{out_dir / 'stage33c_handoff_repaired_family_gate.md'}`
- `{out_dir / 'stage33c_summary.json'}`
- `{out_dir / 'repaired_family_diagnostics.csv'}`
- `{out_dir / 'repaired_member_split_summary.csv'}`
- `{out_dir / 'repaired_cost_sensitivity_summary.csv'}`
- `{out_dir / 'repaired_tail_batch_summary.csv'}`
"""
    (out_dir / "stage33c_handoff_repaired_family_gate.md").write_text(md)
    print(f"DECISION={decision}")
    print(f"RECOMMENDED_NEXT_STAGE={next_stage}")
    print(f"REPORT={out_dir / 'stage33c_handoff_repaired_family_gate.md'}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage33C Handoff repaired family gate")
    parser.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    parser.add_argument("--stage33b-summary", default=str(DEFAULT_STAGE33B_SUMMARY))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--min-effective-events", type=int, default=24)
    parser.add_argument("--min-family-pf-x4", type=float, default=1.45)
    parser.add_argument("--min-family-win-rate", type=float, default=0.60)
    parser.add_argument("--min-family-tail-pf-x4", type=float, default=1.0)
    parser.add_argument("--max-drawdown-x4", type=float, default=-35.0)
    parser.add_argument("--min-cost-stress-pf-x4", type=float, default=1.15)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
