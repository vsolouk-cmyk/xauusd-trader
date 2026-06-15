from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

REPORT_DIR = Path("data/reports/stage33e_short_confirmation_recency_filter")
STAGE33D_SUMMARY = Path("data/reports/stage33d_strict_cost_aware_pre_paper_gate/stage33d_summary.json")
STAGE33C_SUMMARY = Path("data/reports/stage33c_handoff_repaired_family_gate/stage33c_summary.json")
LEDGER_PATH = Path("data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_signal_ledger.csv")

INCLUDED_DEFAULT = [
    "handoff_align_follow_h13_tp06_sl065",
    "handoff_align_follow_h14_tp06_sl065",
]
EXCLUDED_DEFAULT = ["handoff_align_follow_h15_tp06_sl065"]

THRESHOLDS = {
    "min_confirmation_events": 5,
    "target_confirmation_events": 10,
    "min_confirmation_pf_x4": 1.25,
    "min_confirmation_avg_net_x4": 0.0,
    "min_confirmation_win_rate_x4": 0.55,
    "max_confirmation_drawdown_x4": -15.0,
    "min_recovery_ratio": 0.65,
    "min_core_pf_x4": 2.0,
    "min_cost_1_pf_x4": 1.25,
    "min_core_win_rate_x4": 0.65,
    "min_core_avg_net_x4": 0.75,
    "max_core_drawdown_x4": -25.0,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def find_col(cols: Iterable[str], candidates: Iterable[str]) -> Optional[str]:
    lower = {c.lower(): c for c in cols}
    for name in candidates:
        if name in cols:
            return name
        if name.lower() in lower:
            return lower[name.lower()]
    return None


def normalize_ledger(path: Path, included: List[str]) -> Tuple[pd.DataFrame, Dict[str, str]]:
    if not path.exists():
        return pd.DataFrame(), {"error": "ledger_missing", "path": str(path)}
    raw = pd.read_csv(path)
    cols = list(raw.columns)
    candidate_col = find_col(cols, ["candidate", "variant", "candidate_id", "spec", "name"])
    family_col = find_col(cols, ["family", "family_id", "pattern_family"])
    ts_col = find_col(cols, [
        "entry_time", "entry_time_utc", "timestamp", "signal_ts_utc", "ts_utc", "time", "datetime", "bar_time"
    ])
    direction_col = find_col(cols, ["direction", "side", "signal_direction"])
    net_col = find_col(cols, ["net_x4", "net", "outcome_x4", "r_x4", "pnl_x4", "score_x4"])
    colmap = {
        "candidate_col": str(candidate_col),
        "family_col": str(family_col),
        "timestamp_col": str(ts_col),
        "direction_col": str(direction_col),
        "net_col": str(net_col),
    }
    if not candidate_col or not ts_col or not direction_col or not net_col:
        colmap["error"] = "missing_required_ledger_columns"
        colmap["available_columns"] = ",".join(cols)
        return pd.DataFrame(), colmap
    df = pd.DataFrame({
        "candidate": raw[candidate_col].astype(str),
        "timestamp": pd.to_datetime(raw[ts_col], errors="coerce", utc=True),
        "direction": raw[direction_col].astype(str),
        "net_x4": pd.to_numeric(raw[net_col], errors="coerce"),
    })
    if family_col:
        df["family"] = raw[family_col].astype(str)
    else:
        df["family"] = "unknown"
    df = df[df["candidate"].isin(included)].copy()
    df = df.dropna(subset=["timestamp", "net_x4"])
    # Effective family event: do not double-count identical timestamp+direction signals.
    df = df.sort_values(["timestamp", "candidate", "direction"]).drop_duplicates(["timestamp", "direction"], keep="first")
    df["is_win"] = df["net_x4"] > 0
    df["event_key"] = df["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ") + "|" + df["direction"].astype(str)
    return df.reset_index(drop=True), colmap


def metrics(df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return {
            "signal_count": 0,
            "pf_x4": None,
            "avg_net_x4": None,
            "win_rate_x4": None,
            "max_drawdown_x4": None,
        }
    x = pd.to_numeric(df["net_x4"], errors="coerce").dropna()
    if x.empty:
        return {"signal_count": 0, "pf_x4": None, "avg_net_x4": None, "win_rate_x4": None, "max_drawdown_x4": None}
    gains = x[x > 0].sum()
    losses = -x[x < 0].sum()
    if losses == 0:
        pf = math.inf if gains > 0 else None
    else:
        pf = float(gains / losses)
    equity = x.cumsum()
    running_max = equity.cummax()
    dd = equity - running_max
    return {
        "signal_count": int(len(x)),
        "pf_x4": None if pf is None else float(pf),
        "avg_net_x4": float(x.mean()),
        "win_rate_x4": float((x > 0).mean()),
        "max_drawdown_x4": float(dd.min()) if len(dd) else 0.0,
        "sum_net_x4": float(x.sum()),
    }


def rolling_batch_summary(df: pd.DataFrame, batch_size: int = 5) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    rows = []
    sorted_df = df.sort_values("timestamp").reset_index(drop=True)
    for i in range(0, len(sorted_df), batch_size):
        part = sorted_df.iloc[i:i + batch_size]
        m = metrics(part)
        rows.append({
            "batch_index": int(i / batch_size) + 1,
            "start_ts": part["timestamp"].min().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end_ts": part["timestamp"].max().strftime("%Y-%m-%dT%H:%M:%SZ"),
            **m,
        })
    return pd.DataFrame(rows)


def cost_summary(df: pd.DataFrame, penalties=(0.0, 0.25, 0.5, 0.75, 1.0)) -> pd.DataFrame:
    rows = []
    for p in penalties:
        x = df.copy()
        if not x.empty:
            x["net_x4"] = x["net_x4"] - float(p)
        m = metrics(x)
        rows.append({"cost_penalty_x4": float(p), **m})
    return pd.DataFrame(rows)


def recency_filter_tests(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    rows = []
    tests = []
    tests.append(("FULL_H13_H14", df, "primary_repaired_family"))
    for cand in INCLUDED_DEFAULT:
        tests.append((f"{cand}_ONLY", df[df["candidate"] == cand], "member_only_diagnostic"))
    if len(df) > 5:
        tests.append(("EXCLUDE_LAST_5_EVENTS_DIAGNOSTIC_ONLY", df.iloc[:-5].copy(), "diagnostic_only_not_trade_rule"))
    if len(df) > 10:
        tests.append(("LAST_10_EVENTS_ONLY", df.iloc[-10:].copy(), "recency_state_diagnostic"))
    if len(df) > 5:
        tests.append(("LAST_5_EVENTS_ONLY", df.iloc[-5:].copy(), "confirmation_window_diagnostic"))
    for name, part, purpose in tests:
        m = metrics(part)
        rows.append({"test_name": name, "purpose": purpose, **m})
    return pd.DataFrame(rows)


def safe_float(v) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stage33d = read_json(STAGE33D_SUMMARY)
    stage33c = read_json(STAGE33C_SUMMARY)
    included = stage33c.get("included_candidates") or INCLUDED_DEFAULT
    excluded = stage33c.get("excluded_candidates") or EXCLUDED_DEFAULT

    ledger, colmap = normalize_ledger(LEDGER_PATH, included)
    batch_df = rolling_batch_summary(ledger, batch_size=5)
    cost_df = cost_summary(ledger)
    recency_tests_df = recency_filter_tests(ledger)

    for name, df in [
        ("short_confirmation_batch_summary.csv", batch_df),
        ("short_confirmation_cost_summary.csv", cost_df),
        ("recency_filter_diagnostics.csv", recency_tests_df),
        ("repaired_family_effective_ledger.csv", ledger),
    ]:
        df.to_csv(REPORT_DIR / name, index=False)
        df.to_json(REPORT_DIR / name.replace(".csv", ".json"), orient="records", indent=2)

    stage33d_decision = stage33d.get("decision", "UNKNOWN")
    core_pf = safe_float(stage33d.get("family_pf_x4"))
    core_avg = safe_float(stage33d.get("family_avg_net_x4"))
    core_wr = safe_float(stage33d.get("family_win_rate_x4"))
    dd = safe_float(stage33d.get("family_max_drawdown_x4"))
    cost1_pf = safe_float(stage33d.get("cost_1_pf_x4"))
    last_pf = safe_float(stage33d.get("last_batch_pf_x4"))
    last_avg = safe_float(stage33d.get("last_batch_avg_net_x4"))
    degradation = safe_float(stage33d.get("recent_degradation_ratio"))
    fatal_failed = stage33d.get("fatal_failed_gates") or []

    strong_core = (
        core_pf is not None and core_pf >= THRESHOLDS["min_core_pf_x4"] and
        core_avg is not None and core_avg >= THRESHOLDS["min_core_avg_net_x4"] and
        core_wr is not None and core_wr >= THRESHOLDS["min_core_win_rate_x4"] and
        cost1_pf is not None and cost1_pf >= THRESHOLDS["min_cost_1_pf_x4"] and
        dd is not None and dd >= THRESHOLDS["max_core_drawdown_x4"]
    )
    blocked_recent = "BLOCKED_RECENT_DEGRADATION" in stage33d_decision or any(
        g in set(fatal_failed) for g in ["last_batch_pf", "last_batch_avg", "recent_degradation_ratio"]
    )

    if not ledger.empty and strong_core and blocked_recent:
        decision = "STAGE33E_SHORT_CONFIRMATION_SHADOW_ACTIVE_RESEARCH_ONLY"
        next_stage = "COLLECT_NEXT_5_TO_10_H13_H14_EVENTS_THEN_RERUN_STAGE33D_STAGE33E_NO_EA_NO_PAPER_LIVE"
        commercial_transition_authorized = False
    elif not ledger.empty and strong_core:
        decision = "STAGE33E_READY_TO_RERUN_STAGE33D_OR_STAGE33D_PASS_CANDIDATE_RESEARCH_ONLY"
        next_stage = "RERUN_STAGE33D_OR_PREPARE_STRICT_PRE_PAPER_RESEARCH_DESIGN_NO_EXECUTION"
        commercial_transition_authorized = False
    else:
        decision = "STAGE33E_REPAIR_OR_KILL_RESEARCH_ONLY"
        next_stage = "RETURN_TO_STAGE32B_INTAKE_EXPANSION_OR_REPAIR"
        commercial_transition_authorized = False

    latest_batch = batch_df.tail(1).to_dict("records") if not batch_df.empty else []
    last_event_ts = None
    if not ledger.empty:
        last_event_ts = ledger["timestamp"].max().strftime("%Y-%m-%dT%H:%M:%SZ")

    confirmation_plan = pd.DataFrame([
        {
            "plan_item": "NEXT_BATCH_CONFIRMATION_REQUIREMENT",
            "included_candidates": ";".join(included),
            "excluded_candidates": ";".join(excluded),
            "start_after_event_ts": last_event_ts,
            "min_new_effective_events": THRESHOLDS["min_confirmation_events"],
            "target_new_effective_events": THRESHOLDS["target_confirmation_events"],
            "pass_pf_x4": f">= {THRESHOLDS['min_confirmation_pf_x4']}",
            "pass_avg_net_x4": f">= {THRESHOLDS['min_confirmation_avg_net_x4']}",
            "pass_win_rate_x4": f">= {THRESHOLDS['min_confirmation_win_rate_x4']}",
            "pass_drawdown_x4": f">= {THRESHOLDS['max_confirmation_drawdown_x4']}",
            "pass_recovery_ratio": f">= {THRESHOLDS['min_recovery_ratio']}",
            "commercial_status": "RESEARCH_ONLY_NO_EA_NO_PAPER_LIVE_NO_ORDER",
        }
    ])
    confirmation_plan.to_csv(REPORT_DIR / "short_confirmation_plan.csv", index=False)
    confirmation_plan.to_json(REPORT_DIR / "short_confirmation_plan.json", orient="records", indent=2)

    summary = {
        "generated_utc": utc_now(),
        "decision": decision,
        "execution_status": "RESEARCH_ONLY",
        "commercial_transition_authorized": commercial_transition_authorized,
        "no_ea_change": True,
        "no_paper_live": True,
        "no_order_authorization": True,
        "primary_objective": "SHORT_CONFIRMATION_SHADOW_AND_RECENCY_FILTER_DIAGNOSTICS_TO_PROTECT_FAST_COMMERCIAL_PATH",
        "recommended_next_stage": next_stage,
        "stage33d_decision": stage33d_decision,
        "ledger_available": not ledger.empty,
        "ledger_rows": int(len(ledger)),
        "ledger_column_map": colmap,
        "included_candidates": included,
        "excluded_candidates": excluded,
        "strong_core": bool(strong_core),
        "blocked_recent_degradation": bool(blocked_recent),
        "family_pf_x4": core_pf,
        "family_avg_net_x4": core_avg,
        "family_win_rate_x4": core_wr,
        "family_max_drawdown_x4": dd,
        "cost_1_pf_x4": cost1_pf,
        "last_batch_pf_x4": last_pf,
        "last_batch_avg_net_x4": last_avg,
        "recent_degradation_ratio": degradation,
        "fatal_failed_gates": fatal_failed,
        "last_effective_event_ts": last_event_ts,
        "short_confirmation_min_new_events": THRESHOLDS["min_confirmation_events"],
        "short_confirmation_target_new_events": THRESHOLDS["target_confirmation_events"],
    }
    write_json(REPORT_DIR / "stage33e_summary.json", summary)

    md = []
    md.append("# XAUUSD Stage33E — Short Confirmation Shadow & Recency Filter Diagnostics\n")
    md.append(f"Generated UTC: {summary['generated_utc']}\n")
    md.append("## Decision\n")
    md.append("```text\n")
    for k in ["decision", "execution_status", "commercial_transition_authorized", "no_ea_change", "no_paper_live", "no_order_authorization", "primary_objective", "recommended_next_stage"]:
        md.append(f"{k.upper()} = {summary[k]}\n")
    md.append("```\n")
    md.append("## Why this stage exists\n")
    md.append("Stage33D blocked the repaired h13+h14 family because the most recent batch degraded despite strong aggregate and cost-stressed metrics. Stage33E keeps the family alive only as a short confirmation shadow and creates recency-filter diagnostics. It does not authorize EA, paper-live, or orders.\n")
    md.append("## Summary\n")
    md.append("```text\n")
    for k in ["stage33d_decision", "ledger_available", "ledger_rows", "strong_core", "blocked_recent_degradation", "family_pf_x4", "family_win_rate_x4", "cost_1_pf_x4", "last_batch_pf_x4", "last_batch_avg_net_x4", "recent_degradation_ratio", "last_effective_event_ts", "short_confirmation_min_new_events", "short_confirmation_target_new_events"]:
        md.append(f"{k} = {summary.get(k)}\n")
    md.append("```\n")
    md.append("## Short confirmation plan\n\n")
    md.append(confirmation_plan.to_markdown(index=False))
    md.append("\n\n## Recent batch diagnostics\n\n")
    if latest_batch:
        md.append(pd.DataFrame(latest_batch).to_markdown(index=False))
    else:
        md.append("No rows.")
    md.append("\n\n## Recency filter diagnostics\n\n")
    if not recency_tests_df.empty:
        md.append(recency_tests_df.to_markdown(index=False))
    else:
        md.append("No rows.")
    md.append("\n\n## Cost summary\n\n")
    if not cost_df.empty:
        md.append(cost_df.to_markdown(index=False))
    else:
        md.append("No rows.")
    md.append("\n\n## Operational interpretation\n\n")
    md.append("```text\n")
    md.append("1. Stage33E keeps h13+h14 alive only as a short confirmation shadow.\n")
    md.append("2. It blocks EA, paper-live, and orders.\n")
    md.append("3. The next decision requires at least 5 new effective h13/h14 events and preferably 10.\n")
    md.append("4. If the next confirmation batch remains weak, kill/repair this family and return to intake expansion.\n")
    md.append("```\n")
    md.append("\n## Output files\n\n")
    for p in [
        "stage33e_short_confirmation_recency_filter.md",
        "stage33e_summary.json",
        "short_confirmation_plan.csv",
        "short_confirmation_batch_summary.csv",
        "short_confirmation_cost_summary.csv",
        "recency_filter_diagnostics.csv",
        "repaired_family_effective_ledger.csv",
    ]:
        md.append(f"- `data/reports/stage33e_short_confirmation_recency_filter/{p}`\n")
    (REPORT_DIR / "stage33e_short_confirmation_recency_filter.md").write_text("".join(md), encoding="utf-8")

    print(f"DECISION={decision}")
    print(f"STRONG_CORE={strong_core}")
    print(f"BLOCKED_RECENT_DEGRADATION={blocked_recent}")
    print(f"LEDGER_ROWS={len(ledger)}")
    print(f"REPORT={REPORT_DIR / 'stage33e_short_confirmation_recency_filter.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
