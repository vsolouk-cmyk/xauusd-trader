
"""
Stage33A — Dense Family Robustness & Sample Acceleration Gate

Purpose
-------
Stage32F is an operational monitor. It is intentionally slow because it waits for
individual forward samples. Stage33A is a decision-acceleration gate: it tests
whether nearby dense variants can be treated as a robust family, so the project
can avoid waiting weeks for a single narrow variant to reach 40 samples.

This stage DOES NOT authorize EA, paper/live, or orders.

Inputs, in priority order
-------------------------
- data/reports/stage32e_extended_dense_shadow_monitor/extended_shadow_focus_queue.csv
- data/reports/stage32d_dense_forward_review/dense_review_candidate_diagnostics.csv
- data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_candidate_summary.csv
- data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_signal_ledger.csv (optional)

Outputs
-------
- data/reports/stage33a_dense_family_robustness_gate/stage33a_dense_family_robustness_gate.md
- family_robustness_summary.csv/json
- candidate_family_membership.csv/json
- pre_commercial_acceleration_queue.csv/json
- stage33a_summary.json
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

DEFAULT_OUT_DIR = Path("data/reports/stage33a_dense_family_robustness_gate")
DEFAULT_STAGE32E_FOCUS = Path("data/reports/stage32e_extended_dense_shadow_monitor/extended_shadow_focus_queue.csv")
DEFAULT_STAGE32D_DIAG = Path("data/reports/stage32d_dense_forward_review/dense_review_candidate_diagnostics.csv")
DEFAULT_STAGE32C_CAND = Path("data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_candidate_summary.csv")
DEFAULT_STAGE32C_LEDGER = Path("data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_signal_ledger.csv")

# Conservative, decision-acceleration thresholds. These are not live/paper gates.
MIN_FAMILY_EFFECTIVE_SIGNALS = 24
MIN_GOOD_SIBLINGS = 2
MIN_FAMILY_PF_X4 = 1.35
MIN_FAMILY_WIN_RATE = 0.58
MIN_FAMILY_TAIL_PF_X4 = 1.00
MAX_ALLOWED_DRAWDOWN_X4 = -35.0
MIN_MEMBER_SIGNALS_FOR_GOOD = 10


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception as exc:
        raise RuntimeError(f"Failed to read CSV: {path}: {exc}") from exc


def _first_existing(cols: Sequence[str], df: pd.DataFrame) -> Optional[str]:
    for c in cols:
        if c in df.columns:
            return c
    return None


def _to_num(series: pd.Series, default: float = 0.0) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(default)


def _candidate_col(df: pd.DataFrame) -> Optional[str]:
    return _first_existing(["candidate", "candidate_id", "spec_id", "variant", "name"], df)


def _family_col(df: pd.DataFrame) -> Optional[str]:
    return _first_existing(["family", "family_id", "family_name"], df)


def _signal_col(df: pd.DataFrame) -> Optional[str]:
    return _first_existing(["signal_count", "signals", "n", "count", "resolved", "resolved_count"], df)


def _pf_col(df: pd.DataFrame) -> Optional[str]:
    return _first_existing(["pf_x4", "profit_factor_x4", "pf", "profit_factor"], df)


def _avg_col(df: pd.DataFrame) -> Optional[str]:
    return _first_existing(["avg_net_x4", "avg_x4", "avg_net", "mean_net_x4"], df)


def _win_col(df: pd.DataFrame) -> Optional[str]:
    return _first_existing(["win_rate_x4", "win_rate", "wr", "winrate"], df)


def _tail_pf_col(df: pd.DataFrame) -> Optional[str]:
    return _first_existing(["tail_pf_x4", "tail_pf", "recent_pf_x4"], df)


def _dd_col(df: pd.DataFrame) -> Optional[str]:
    return _first_existing(["max_drawdown_x4", "max_dd_x4", "drawdown_x4", "max_drawdown"], df)


def normalize_candidate_frame(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    if df.empty:
        return df
    c_col = _candidate_col(df)
    if not c_col:
        raise RuntimeError(f"{source_name} does not contain a candidate/spec column. Columns={list(df.columns)}")
    fam_col = _family_col(df)
    sig_col = _signal_col(df)
    pf_col = _pf_col(df)
    avg_col = _avg_col(df)
    win_col = _win_col(df)
    tail_col = _tail_pf_col(df)
    dd_col = _dd_col(df)

    out = pd.DataFrame()
    out["candidate"] = df[c_col].astype(str)
    if fam_col:
        out["family"] = df[fam_col].astype(str)
    else:
        out["family"] = out["candidate"].map(infer_family)
    out["signal_count"] = _to_num(df[sig_col], 0).astype(int) if sig_col else 0
    out["pf_x4"] = _to_num(df[pf_col], 0.0) if pf_col else 0.0
    out["avg_net_x4"] = _to_num(df[avg_col], 0.0) if avg_col else 0.0
    out["win_rate_x4"] = _to_num(df[win_col], 0.0) if win_col else 0.0
    out["tail_pf_x4"] = _to_num(df[tail_col], 0.0) if tail_col else 0.0
    out["max_drawdown_x4"] = _to_num(df[dd_col], 0.0) if dd_col else 0.0
    out["source"] = source_name

    if "monitor_role" in df.columns:
        out["monitor_role"] = df["monitor_role"].astype(str)
    elif "role" in df.columns:
        out["monitor_role"] = df["role"].astype(str)
    else:
        out["monitor_role"] = "UNKNOWN"

    if "next_action" in df.columns:
        out["stage32_next_action"] = df["next_action"].astype(str)
    elif "stage32d_decision" in df.columns:
        out["stage32_next_action"] = df["stage32d_decision"].astype(str)
    else:
        out["stage32_next_action"] = "UNKNOWN"

    out["hour"] = out["candidate"].map(extract_hour)
    out["weekday"] = out["candidate"].map(extract_weekday)
    out["sibling_group"] = out.apply(lambda r: sibling_group(str(r["candidate"]), str(r["family"])), axis=1)
    return out


def extract_hour(candidate: str) -> Optional[int]:
    m = re.search(r"(?:^|_)h(\d{1,2})(?:_|$)", candidate)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def extract_weekday(candidate: str) -> str:
    for wd in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
        if wd in candidate.lower():
            return wd
    return "none"


def infer_family(candidate: str) -> str:
    c = candidate.lower()
    if "handoff" in c:
        return "session_handoff_imbalance_v1"
    if "calendar" in c:
        return "calendar_time_risk_proxy_v1"
    if "vol_trans" in c or "volatility" in c:
        return "volatility_transition_v1"
    if "range" in c:
        return "range_regime_v1"
    return "unknown_family"


def sibling_group(candidate: str, family: str) -> str:
    c = candidate.lower()
    # Normalize hour-specific siblings: h13/h14/h15 -> hX.
    c = re.sub(r"_h\d{1,2}_", "_hX_", c)
    c = re.sub(r"_h\d{1,2}$", "_hX", c)
    # Normalize weekday when we want broader repair, but keep calendar weekday in subgroup via family suffix.
    if "calendar_drop" in c:
        # Separate hour-sibling and weekday-sibling enough for diagnostics.
        # friday h9/h13 and monday h13 are related but not identical.
        c = re.sub(r"calendar_drop_(monday|tuesday|wednesday|thursday|friday)", "calendar_drop_WEEKDAY", c)
    return f"{family}::{c}"


def load_candidates(stage32e_focus: Path, stage32d_diag: Path, stage32c_cand: Path) -> pd.DataFrame:
    frames: List[pd.DataFrame] = []
    for path, name in [
        (stage32e_focus, "stage32e_focus"),
        (stage32d_diag, "stage32d_diagnostics"),
        (stage32c_cand, "stage32c_candidate_summary"),
    ]:
        df = _read_csv(path)
        if not df.empty:
            frames.append(normalize_candidate_frame(df, name))
    if not frames:
        return pd.DataFrame()
    all_df = pd.concat(frames, ignore_index=True)
    # Prefer freshest/operational Stage32E rows, then Stage32D, then Stage32C. Deduplicate by candidate.
    priority = {"stage32e_focus": 0, "stage32d_diagnostics": 1, "stage32c_candidate_summary": 2}
    all_df["_source_priority"] = all_df["source"].map(priority).fillna(9).astype(int)
    all_df = all_df.sort_values(["candidate", "_source_priority"]).drop_duplicates("candidate", keep="first")
    all_df = all_df.drop(columns=["_source_priority"])
    return all_df.sort_values(["family", "sibling_group", "candidate"]).reset_index(drop=True)


def load_ledger(ledger_path: Path) -> pd.DataFrame:
    df = _read_csv(ledger_path)
    if df.empty:
        return df
    c_col = _candidate_col(df)
    if not c_col:
        return pd.DataFrame()
    out = df.copy()
    out["candidate"] = out[c_col].astype(str)
    out["family"] = out["candidate"].map(infer_family) if "family" not in out.columns else out["family"].astype(str)
    out["sibling_group"] = out.apply(lambda r: sibling_group(str(r["candidate"]), str(r["family"])), axis=1)
    return out


def ledger_effective_count(ledger: pd.DataFrame, candidates: Sequence[str]) -> Optional[int]:
    if ledger.empty:
        return None
    sub = ledger[ledger["candidate"].isin(list(candidates))].copy()
    if sub.empty:
        return 0
    time_col = _first_existing(["signal_ts_utc", "ts_utc", "entry_ts_utc", "bar_ts_utc", "timestamp", "time"], sub)
    dir_col = _first_existing(["direction", "side", "signal_direction"], sub)
    resolved_col = _first_existing(["resolved", "is_resolved", "status"], sub)
    if resolved_col:
        # Best effort: keep rows not explicitly unresolved/pending.
        vals = sub[resolved_col].astype(str).str.lower()
        sub = sub[~vals.isin(["false", "0", "pending", "unresolved", "open", "nan"])]
    if time_col:
        keys = [time_col]
        if dir_col:
            keys.append(dir_col)
        # Same timestamp+direction across siblings is probably overlapping evidence.
        return int(sub.drop_duplicates(keys).shape[0])
    return int(sub.shape[0])


def harmonic_pf(values: pd.Series, weights: pd.Series) -> float:
    values = pd.to_numeric(values, errors="coerce").replace([math.inf, -math.inf], pd.NA).dropna()
    if values.empty:
        return 0.0
    # Use weighted arithmetic for PF; harmonic can punish too much when one weak sibling is background.
    return float((pd.to_numeric(weights, errors="coerce").fillna(0).loc[values.index] * values).sum() / max(pd.to_numeric(weights, errors="coerce").fillna(0).loc[values.index].sum(), 1))


def classify_member(row: pd.Series) -> str:
    sig = int(row.get("signal_count", 0) or 0)
    pf = float(row.get("pf_x4", 0) or 0)
    wr = float(row.get("win_rate_x4", 0) or 0)
    avg = float(row.get("avg_net_x4", 0) or 0)
    tail = float(row.get("tail_pf_x4", 0) or 0)
    dd = float(row.get("max_drawdown_x4", 0) or 0)
    if sig >= MIN_MEMBER_SIGNALS_FOR_GOOD and pf >= 1.25 and wr >= 0.55 and avg >= 0 and (tail >= 0.75 or tail == 0) and dd >= MAX_ALLOWED_DRAWDOWN_X4:
        return "GOOD_SIBLING"
    if sig >= MIN_MEMBER_SIGNALS_FOR_GOOD and pf >= 1.10 and wr >= 0.52 and avg >= 0:
        return "SECONDARY_SIBLING"
    if pf < 1.0 or avg < 0:
        return "WEAK_OR_REPAIR_SIBLING"
    return "INSUFFICIENT_OR_MIXED"


def family_summary(candidates: pd.DataFrame, ledger: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if candidates.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    members = candidates.copy()
    members["member_quality"] = members.apply(classify_member, axis=1)

    rows = []
    for group, sub in members.groupby("sibling_group", dropna=False):
        sub = sub.copy()
        cand_list = sub["candidate"].astype(str).tolist()
        raw_signal_sum = int(sub["signal_count"].sum())
        max_member_signals = int(sub["signal_count"].max()) if not sub.empty else 0
        ledger_eff = ledger_effective_count(ledger, cand_list)
        if ledger_eff is not None and ledger_eff > 0:
            effective_signals = ledger_eff
            evidence_basis = "ledger_dedup_timestamp_direction"
        else:
            # Conservative fallback: do not fully sum siblings without a ledger.
            # Use 75% of the sum, bounded below by max member count.
            effective_signals = max(max_member_signals, int(math.ceil(raw_signal_sum * 0.75)))
            evidence_basis = "summary_conservative_75pct_sum"

        weights = sub["signal_count"].clip(lower=1)
        pf = harmonic_pf(sub["pf_x4"], weights)
        wr = float((weights * sub["win_rate_x4"]).sum() / max(weights.sum(), 1))
        avg = float((weights * sub["avg_net_x4"]).sum() / max(weights.sum(), 1))
        tail = harmonic_pf(sub["tail_pf_x4"].replace(0, pd.NA).fillna(sub["pf_x4"]), weights)
        dd = float(sub["max_drawdown_x4"].min()) if "max_drawdown_x4" in sub.columns else 0.0
        good = int((sub["member_quality"] == "GOOD_SIBLING").sum())
        secondary = int((sub["member_quality"] == "SECONDARY_SIBLING").sum())
        weak = int((sub["member_quality"] == "WEAK_OR_REPAIR_SIBLING").sum())
        families = ",".join(sorted(set(sub["family"].astype(str))))
        hours = ",".join(str(int(h)) for h in sorted(set(sub["hour"].dropna().astype(int)))) if sub["hour"].notna().any() else "none"
        weekdays = ",".join(sorted(set(sub["weekday"].astype(str))))

        if (
            effective_signals >= MIN_FAMILY_EFFECTIVE_SIGNALS
            and good >= MIN_GOOD_SIBLINGS
            and pf >= MIN_FAMILY_PF_X4
            and wr >= MIN_FAMILY_WIN_RATE
            and tail >= MIN_FAMILY_TAIL_PF_X4
            and dd >= MAX_ALLOWED_DRAWDOWN_X4
        ):
            decision = "FAMILY_PRE_COMMERCIAL_ACCELERATION_REVIEW_RESEARCH_ONLY"
            next_action = "RUN_STAGE33B_PRE_COMMERCIAL_ROBUSTNESS_ON_FAMILY_NO_EA_NO_PAPER_LIVE"
        elif good >= MIN_GOOD_SIBLINGS and effective_signals >= 20 and pf >= 1.20 and wr >= 0.55:
            decision = "FAMILY_ACCELERATE_COLLECTION_AND_ROBUSTNESS_DIAGNOSTICS"
            next_action = "KEEP_STAGE32F_MONITORING_BUT_RUN_STAGE33B_DIAGNOSTICS_IN_PARALLEL"
        elif good >= 1 and secondary >= 1:
            decision = "MIXED_FAMILY_REQUIRES_TIGHTENING"
            next_action = "TIGHTEN_HOURS_OR_FILTERS_BEFORE_PRE_COMMERCIAL_REVIEW"
        elif weak >= max(1, len(sub) // 2):
            decision = "FAMILY_REPAIR_OR_KILL_CANDIDATE"
            next_action = "MOVE_TO_REPAIR_OR_KILL_IF_NEXT_BATCH_NOT_IMPROVED"
        else:
            decision = "KEEP_BACKGROUND_COLLECTION_ONLY"
            next_action = "DO_NOT_WAIT_FOR_THIS_FAMILY_AS_PRIMARY_FAST_PATH"

        rows.append({
            "sibling_group": group,
            "families": families,
            "member_count": int(len(sub)),
            "candidate_list": ";".join(cand_list),
            "hours": hours,
            "weekdays": weekdays,
            "raw_signal_sum": raw_signal_sum,
            "max_member_signals": max_member_signals,
            "effective_signal_count": int(effective_signals),
            "evidence_basis": evidence_basis,
            "good_sibling_count": good,
            "secondary_sibling_count": secondary,
            "weak_or_repair_count": weak,
            "family_pf_x4": round(pf, 6),
            "family_avg_net_x4": round(avg, 6),
            "family_win_rate_x4": round(wr, 6),
            "family_tail_pf_x4": round(tail, 6),
            "family_max_drawdown_x4": round(dd, 6),
            "stage33a_decision": decision,
            "next_action": next_action,
        })

    summary = pd.DataFrame(rows)
    if not summary.empty:
        priority = {
            "FAMILY_PRE_COMMERCIAL_ACCELERATION_REVIEW_RESEARCH_ONLY": 0,
            "FAMILY_ACCELERATE_COLLECTION_AND_ROBUSTNESS_DIAGNOSTICS": 1,
            "MIXED_FAMILY_REQUIRES_TIGHTENING": 2,
            "KEEP_BACKGROUND_COLLECTION_ONLY": 3,
            "FAMILY_REPAIR_OR_KILL_CANDIDATE": 4,
        }
        summary["_p"] = summary["stage33a_decision"].map(priority).fillna(9).astype(int)
        summary = summary.sort_values(["_p", "effective_signal_count", "family_pf_x4"], ascending=[True, False, False]).drop(columns=["_p"]).reset_index(drop=True)
        summary.insert(0, "rank", range(1, len(summary) + 1))

    queue = summary[summary["stage33a_decision"].isin([
        "FAMILY_PRE_COMMERCIAL_ACCELERATION_REVIEW_RESEARCH_ONLY",
        "FAMILY_ACCELERATE_COLLECTION_AND_ROBUSTNESS_DIAGNOSTICS",
    ])].copy()
    if not queue.empty:
        queue = queue.reset_index(drop=True)
        queue.insert(0, "queue_rank", range(1, len(queue) + 1))
        queue["commercial_status"] = "RESEARCH_ONLY_NO_EA_NO_PAPER_LIVE_NO_ORDER"

    return summary, members, queue


def write_outputs(out_dir: Path, family_df: pd.DataFrame, members_df: pd.DataFrame, queue_df: pd.DataFrame, summary: Dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    family_csv = out_dir / "family_robustness_summary.csv"
    members_csv = out_dir / "candidate_family_membership.csv"
    queue_csv = out_dir / "pre_commercial_acceleration_queue.csv"
    family_json = out_dir / "family_robustness_summary.json"
    members_json = out_dir / "candidate_family_membership.json"
    queue_json = out_dir / "pre_commercial_acceleration_queue.json"
    summary_json = out_dir / "stage33a_summary.json"
    report_md = out_dir / "stage33a_dense_family_robustness_gate.md"

    family_df.to_csv(family_csv, index=False)
    members_df.to_csv(members_csv, index=False)
    queue_df.to_csv(queue_csv, index=False)
    family_json.write_text(family_df.to_json(orient="records", indent=2), encoding="utf-8")
    members_json.write_text(members_df.to_json(orient="records", indent=2), encoding="utf-8")
    queue_json.write_text(queue_df.to_json(orient="records", indent=2), encoding="utf-8")
    summary_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = []
    lines.append("# XAUUSD Stage33A — Dense Family Robustness & Sample Acceleration Gate")
    lines.append("")
    lines.append(f"Generated UTC: {summary['generated_utc']}")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append("```text")
    for k in [
        "decision", "execution_status", "commercial_transition_authorized", "no_ea_change",
        "no_paper_live", "no_order_authorization", "primary_objective", "recommended_next_stage",
    ]:
        lines.append(f"{k.upper()} = {summary.get(k)}")
    lines.append("```")
    lines.append("")
    lines.append("## Why this stage exists")
    lines.append("")
    lines.append("Stage32F is intentionally slow because it waits for single-variant forward samples. Stage33A tests whether sibling variants can be treated as a robust family so the project can reduce time-to-decision without authorizing execution.")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("```text")
    for k in [
        "candidate_rows", "family_group_rows", "acceleration_queue_rows", "pre_commercial_family_review_rows",
        "accelerate_diagnostics_rows", "repair_or_kill_rows", "min_family_effective_signals",
        "min_good_siblings", "min_family_pf_x4", "min_family_win_rate",
    ]:
        lines.append(f"{k} = {summary.get(k)}")
    lines.append("```")
    lines.append("")
    lines.append("## Family robustness summary")
    lines.append("")
    lines.append(df_to_md(family_df))
    lines.append("")
    lines.append("## Pre-commercial acceleration queue")
    lines.append("")
    if queue_df.empty:
        lines.append("No family is ready for pre-commercial acceleration diagnostics yet.")
    else:
        lines.append(df_to_md(queue_df))
    lines.append("")
    lines.append("## Operational interpretation")
    lines.append("")
    lines.append("```text")
    lines.append("1. Stage32F remains useful only as automated sample collection, not as the sole decision path.")
    lines.append("2. Family-level candidates can move to Stage33B diagnostics before any EA/paper/live decision.")
    lines.append("3. If a family fails Stage33B, kill or repair it quickly instead of waiting weeks for single-variant N=40.")
    lines.append("4. No EA/paper/live/order transition is authorized by Stage33A.")
    lines.append("```")
    lines.append("")
    lines.append("## Output files")
    lines.append("")
    for p in [report_md, family_csv, members_csv, queue_csv, summary_json]:
        lines.append(f"- `{p}`")
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def df_to_md(df: pd.DataFrame, max_rows: int = 20) -> str:
    if df.empty:
        return "_No rows._"
    show = df.head(max_rows).copy()
    # Keep report readable: shorten long lists.
    for col in show.columns:
        if show[col].dtype == object:
            show[col] = show[col].astype(str).map(lambda x: x if len(x) <= 96 else x[:93] + "...")
    return show.to_markdown(index=False)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Stage33A dense family robustness and sample acceleration gate")
    ap.add_argument("--stage32e-focus", default=str(DEFAULT_STAGE32E_FOCUS))
    ap.add_argument("--stage32d-diagnostics", default=str(DEFAULT_STAGE32D_DIAG))
    ap.add_argument("--stage32c-candidate-summary", default=str(DEFAULT_STAGE32C_CAND))
    ap.add_argument("--stage32c-ledger", default=str(DEFAULT_STAGE32C_LEDGER))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = ap.parse_args(argv)

    out_dir = Path(args.out_dir)
    generated_utc = utc_now()

    candidates = load_candidates(Path(args.stage32e_focus), Path(args.stage32d_diagnostics), Path(args.stage32c_candidate_summary))
    if candidates.empty:
        out_dir.mkdir(parents=True, exist_ok=True)
        summary = {
            "generated_utc": generated_utc,
            "decision": "STAGE33A_NO_INPUT_CANDIDATES",
            "execution_status": "RESEARCH_ONLY",
            "commercial_transition_authorized": False,
            "no_ea_change": True,
            "no_paper_live": True,
            "no_order_authorization": True,
            "candidate_rows": 0,
            "family_group_rows": 0,
            "acceleration_queue_rows": 0,
            "recommended_next_stage": "RERUN_STAGE32C_D_E_OR_CHECK_INPUT_PATHS",
        }
        write_outputs(out_dir, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), summary)
        print("DECISION=STAGE33A_NO_INPUT_CANDIDATES")
        print(f"REPORT={out_dir / 'stage33a_dense_family_robustness_gate.md'}")
        return 2

    ledger = load_ledger(Path(args.stage32c_ledger))
    family_df, members_df, queue_df = family_summary(candidates, ledger)

    pre_rows = int((family_df["stage33a_decision"] == "FAMILY_PRE_COMMERCIAL_ACCELERATION_REVIEW_RESEARCH_ONLY").sum()) if not family_df.empty else 0
    accel_rows = int((family_df["stage33a_decision"] == "FAMILY_ACCELERATE_COLLECTION_AND_ROBUSTNESS_DIAGNOSTICS").sum()) if not family_df.empty else 0
    repair_rows = int((family_df["stage33a_decision"] == "FAMILY_REPAIR_OR_KILL_CANDIDATE").sum()) if not family_df.empty else 0

    if pre_rows > 0:
        decision = "STAGE33A_HAS_FAMILY_PRE_COMMERCIAL_ACCELERATION_REVIEW_RESEARCH_ONLY"
        recommended = "RUN_STAGE33B_PRE_COMMERCIAL_FAMILY_ROBUSTNESS_GATE"
    elif accel_rows > 0:
        decision = "STAGE33A_HAS_FAMILY_ACCELERATION_DIAGNOSTICS_RESEARCH_ONLY"
        recommended = "RUN_STAGE33B_DIAGNOSTICS_IN_PARALLEL_WITH_STAGE32F"
    elif repair_rows > 0:
        decision = "STAGE33A_REPAIR_OR_KILL_WEAK_FAMILIES_RESEARCH_ONLY"
        recommended = "RUN_INTAKE_REPAIR_OR_EXPANSION_DO_NOT_WAIT_FOR_STAGE32F_ONLY"
    else:
        decision = "STAGE33A_NO_ACCELERATION_FAMILY_KEEP_BACKGROUND_ONLY"
        recommended = "RETURN_TO_STAGE32B_INTAKE_EXPANSION_OR_NEW_BASELINE_FAMILY_DISCOVERY"

    summary = {
        "generated_utc": generated_utc,
        "decision": decision,
        "execution_status": "RESEARCH_ONLY",
        "commercial_transition_authorized": False,
        "no_ea_change": True,
        "no_paper_live": True,
        "no_order_authorization": True,
        "primary_objective": "REDUCE_TIME_TO_DECISION_USING_DENSE_FAMILY_ROBUSTNESS_NOT_SINGLE_VARIANT_WAITING",
        "recommended_next_stage": recommended,
        "candidate_rows": int(len(candidates)),
        "family_group_rows": int(len(family_df)),
        "acceleration_queue_rows": int(len(queue_df)),
        "pre_commercial_family_review_rows": pre_rows,
        "accelerate_diagnostics_rows": accel_rows,
        "repair_or_kill_rows": repair_rows,
        "min_family_effective_signals": MIN_FAMILY_EFFECTIVE_SIGNALS,
        "min_good_siblings": MIN_GOOD_SIBLINGS,
        "min_family_pf_x4": MIN_FAMILY_PF_X4,
        "min_family_win_rate": MIN_FAMILY_WIN_RATE,
        "min_family_tail_pf_x4": MIN_FAMILY_TAIL_PF_X4,
        "max_allowed_drawdown_x4": MAX_ALLOWED_DRAWDOWN_X4,
        "stage32e_focus_path": str(Path(args.stage32e_focus)),
        "stage32d_diagnostics_path": str(Path(args.stage32d_diagnostics)),
        "stage32c_candidate_summary_path": str(Path(args.stage32c_candidate_summary)),
        "stage32c_ledger_path": str(Path(args.stage32c_ledger)),
        "ledger_available": bool(not ledger.empty),
    }
    write_outputs(out_dir, family_df, members_df, queue_df, summary)

    print(f"DECISION={decision}")
    print(f"ACCELERATION_QUEUE_ROWS={len(queue_df)}")
    print(f"PRE_COMMERCIAL_FAMILY_REVIEW_ROWS={pre_rows}")
    print(f"RECOMMENDED_NEXT_STAGE={recommended}")
    print(f"REPORT={out_dir / 'stage33a_dense_family_robustness_gate.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
