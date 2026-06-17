#!/usr/bin/env python3
"""
Stage40B_SURVIVOR_PATH_STABILITY_AUDIT

Dedicated research-only audit for Stage40 parallel megascan strict survivors.
It reads the Stage40 megascan summary JSON and event rows, then rechecks the
survivor(s) at event level for path risk, chronological split stability,
quarter stability, year/month concentration, contribution concentration, and
slippage-16 survival.

This script cannot promote to EA, paper-live, or live. All outputs are research
watch / no-promotion decisions.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

STAGE = "Stage40B_SURVIVOR_PATH_STABILITY_AUDIT"
DECISION_SCOPE = "RESEARCH_STAGE_ONLY_NO_PROMOTION"
NO_GO = "NO_GO"
STRICT_INPUT = "STRICT_PARALLEL_THESIS_WATCH_ONLY_NO_PROMOTION"

TIME_COL_CANDIDATES = [
    "entry_ts", "entry_utc", "utc_time", "timestamp", "ts_utc", "time", "datetime", "date", "bar_time", "open_time"
]


def to_num(s: Any) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def finite_float(x: Any, default: float = np.nan) -> float:
    try:
        v = float(x)
        return v if math.isfinite(v) else default
    except Exception:
        return default


def norm_text(x: Any) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip()


def load_json(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Missing JSON file: {path}")
    return json.loads(p.read_text(encoding="utf-8"))


def read_csv_if_exists(path: Optional[str]) -> Optional[pd.DataFrame]:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    return pd.read_csv(p)


def extract_rows_from_json(summary: Dict[str, Any]) -> pd.DataFrame:
    rows = summary.get("top_rows_by_h1_benchmark_cost_residual") or summary.get("top_rows") or []
    if not isinstance(rows, list):
        rows = []
    return pd.DataFrame(rows)


def survivor_specs(summary_json: Dict[str, Any], summary_csv: Optional[pd.DataFrame]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    source = "summary_json_top_rows"
    df = extract_rows_from_json(summary_json)
    if summary_csv is not None and not summary_csv.empty:
        # Prefer the full CSV when available because JSON may contain only top rows.
        source = "summary_csv"
        df = summary_csv.copy()
    if df.empty or "classification" not in df.columns:
        return pd.DataFrame(), {"source": source, "loaded_rows": int(len(df)), "strict_rows": 0}
    survivors = df[df["classification"].astype(str) == STRICT_INPUT].copy()
    return survivors.reset_index(drop=True), {
        "source": source,
        "loaded_rows": int(len(df)),
        "strict_rows": int(len(survivors)),
        "classification_counts": {str(k): int(v) for k, v in df["classification"].value_counts(dropna=False).to_dict().items()},
    }


def add_event_time_or_order(events: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    ev = events.copy()
    meta: Dict[str, Any] = {"time_column": None, "mode": None, "bad_time_rows_dropped": 0}
    for col in TIME_COL_CANDIDATES:
        if col in ev.columns:
            t = pd.to_datetime(ev[col], errors="coerce", utc=True)
            bad = int(t.isna().sum())
            good = ev.loc[t.notna()].copy()
            good["_event_time"] = t.loc[t.notna()].values
            meta.update({"time_column": col, "mode": "timestamp_column", "bad_time_rows_dropped": bad})
            if not good.empty:
                return good.sort_values("_event_time").reset_index(drop=True), meta
    # Stage40 megascan event rows are emitted in original chronological order per candidate.
    # If no explicit timestamp exists, preserve file order as a chronology proxy and keep an audit flag.
    ev["_event_order"] = np.arange(len(ev), dtype=int)
    ev["_event_time"] = ev["_event_order"]
    meta.update({"time_column": None, "mode": "row_order_fallback", "bad_time_rows_dropped": 0})
    return ev.reset_index(drop=True), meta


def match_events(events: pd.DataFrame, spec: pd.Series) -> pd.DataFrame:
    if events.empty:
        return events.copy()
    mask = pd.Series(True, index=events.index)
    for col in ["family", "candidate", "side"]:
        if col in events.columns and col in spec.index:
            mask &= events[col].astype(str) == str(spec.get(col))
    if "horizon_hours" in events.columns and "horizon_hours" in spec.index:
        mask &= to_num(events["horizon_hours"]) == finite_float(spec.get("horizon_hours"))
    if "params_json" in events.columns and "params_json" in spec.index:
        # Params are deterministic JSON from Stage40. If not exact due to whitespace, skip strict matching.
        wanted = norm_text(spec.get("params_json"))
        if wanted:
            same = events["params_json"].astype(str) == wanted
            if same.any():
                mask &= same
    ev = events[mask].copy()
    if "_event_time" in ev.columns:
        ev = ev.sort_values("_event_time")
    return ev.reset_index(drop=True)


def metric_summary(ev: pd.DataFrame, cost_bps: float, prefix: str = "") -> Dict[str, Any]:
    out: Dict[str, Any] = {f"{prefix}n": int(len(ev))}
    if ev.empty:
        fields = [
            "mean_final_bps", "median_final_bps", "cost_mean_bps", "hit_rate_pct", "median_mae_bps",
            "mean_mae_bps", "median_mfe_bps", "mean_mfe_bps", "touch_stop_100bps_pct",
            "touch_target_100bps_pct", "mean_after_cost_plus_slip16_bps", "worst_loss_bps",
            "best_win_bps", "positive_sum_bps", "negative_sum_bps", "top3_win_share_pct",
        ]
        for f in fields:
            out[f"{prefix}{f}"] = np.nan
        return out
    final = to_num(ev.get("final_bps", pd.Series(dtype=float)))
    cost_final = to_num(ev.get("cost_stressed_final_bps", final - cost_bps))
    mae = to_num(ev.get("mae_bps", pd.Series(dtype=float)))
    mfe = to_num(ev.get("mfe_bps", pd.Series(dtype=float)))
    out[f"{prefix}mean_final_bps"] = float(final.mean())
    out[f"{prefix}median_final_bps"] = float(final.median())
    out[f"{prefix}cost_mean_bps"] = float(cost_final.mean())
    out[f"{prefix}cost_median_bps"] = float(cost_final.median())
    out[f"{prefix}hit_rate_pct"] = float((cost_final > 0).mean() * 100.0)
    out[f"{prefix}median_mae_bps"] = float(mae.median()) if len(mae.dropna()) else np.nan
    out[f"{prefix}mean_mae_bps"] = float(mae.mean()) if len(mae.dropna()) else np.nan
    out[f"{prefix}median_mfe_bps"] = float(mfe.median()) if len(mfe.dropna()) else np.nan
    out[f"{prefix}mean_mfe_bps"] = float(mfe.mean()) if len(mfe.dropna()) else np.nan
    if "touch_stop_100bps" in ev.columns:
        out[f"{prefix}touch_stop_100bps_pct"] = float(to_num(ev["touch_stop_100bps"]).fillna(0).mean() * 100.0)
    elif len(mae.dropna()):
        out[f"{prefix}touch_stop_100bps_pct"] = float((mae <= -100.0).mean() * 100.0)
    else:
        out[f"{prefix}touch_stop_100bps_pct"] = np.nan
    if "touch_target_100bps" in ev.columns:
        out[f"{prefix}touch_target_100bps_pct"] = float(to_num(ev["touch_target_100bps"]).fillna(0).mean() * 100.0)
    elif len(mfe.dropna()):
        out[f"{prefix}touch_target_100bps_pct"] = float((mfe >= 100.0).mean() * 100.0)
    else:
        out[f"{prefix}touch_target_100bps_pct"] = np.nan
    out[f"{prefix}mean_after_cost_plus_slip16_bps"] = float((cost_final - 16.0).mean())
    out[f"{prefix}worst_loss_bps"] = float(cost_final.min())
    out[f"{prefix}best_win_bps"] = float(cost_final.max())
    pos = cost_final[cost_final > 0].sort_values(ascending=False)
    neg = cost_final[cost_final < 0]
    out[f"{prefix}positive_sum_bps"] = float(pos.sum()) if len(pos) else 0.0
    out[f"{prefix}negative_sum_bps"] = float(neg.sum()) if len(neg) else 0.0
    out[f"{prefix}top3_win_share_pct"] = float(pos.iloc[:3].sum() / pos.sum() * 100.0) if float(pos.sum()) > 0 else np.nan
    return out


def chronological_splits(ev: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    n = len(ev)
    if n == 0:
        return {k: ev.copy() for k in ["train", "oos", "first_half", "second_half", "q1", "q2", "q3", "q4", "recent_third"]}
    train_end = max(1, int(math.floor(n * 0.67)))
    half = max(1, n // 2)
    q1_end = max(1, int(math.floor(n * 0.25)))
    q2_end = max(q1_end + 1, int(math.floor(n * 0.50)))
    q3_end = max(q2_end + 1, int(math.floor(n * 0.75)))
    recent_start = max(0, int(math.floor(n * 0.67)))
    return {
        "train": ev.iloc[:train_end],
        "oos": ev.iloc[train_end:],
        "first_half": ev.iloc[:half],
        "second_half": ev.iloc[half:],
        "q1": ev.iloc[:q1_end],
        "q2": ev.iloc[q1_end:q2_end],
        "q3": ev.iloc[q2_end:q3_end],
        "q4": ev.iloc[q3_end:],
        "recent_third": ev.iloc[recent_start:],
    }


def bootstrap_mean_ci(values: pd.Series, seed: int = 401, n_boot: int = 1000) -> Dict[str, Any]:
    x = to_num(values).dropna().to_numpy(dtype=float)
    out = {"boot_n": int(len(x)), "boot_mean_bps": np.nan, "boot_p05_bps": np.nan, "boot_p10_bps": np.nan, "boot_p50_bps": np.nan, "boot_p90_bps": np.nan, "boot_p95_bps": np.nan, "boot_prob_mean_gt_0_pct": np.nan, "boot_prob_mean_gt_10_pct": np.nan}
    if len(x) < 5:
        return out
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), size=(n_boot, len(x)))
    means = x[idx].mean(axis=1)
    out.update({
        "boot_mean_bps": float(x.mean()),
        "boot_p05_bps": float(np.percentile(means, 5)),
        "boot_p10_bps": float(np.percentile(means, 10)),
        "boot_p50_bps": float(np.percentile(means, 50)),
        "boot_p90_bps": float(np.percentile(means, 90)),
        "boot_p95_bps": float(np.percentile(means, 95)),
        "boot_prob_mean_gt_0_pct": float((means > 0).mean() * 100.0),
        "boot_prob_mean_gt_10_pct": float((means > 10).mean() * 100.0),
    })
    return out


def year_month_audit(ev: pd.DataFrame, cost_bps: float, spec_id: int) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    out: Dict[str, Any] = {}
    for dim in ["year", "month", "weekday", "session_utc", "hour_utc"]:
        if dim not in ev.columns:
            continue
        for val, g in ev.groupby(dim, dropna=False):
            r = {"spec_id": spec_id, "dimension": dim, "bucket": str(val)}
            r.update(metric_summary(g, cost_bps, ""))
            rows.append(r)
    if "year" in ev.columns:
        year_means = []
        for _, g in ev.groupby("year", dropna=False):
            if len(g):
                year_means.append(metric_summary(g, cost_bps, "")["cost_mean_bps"])
        out["year_bucket_count"] = int(len(year_means))
        out["worst_year_cost_mean_bps"] = float(np.nanmin(year_means)) if year_means else np.nan
    else:
        out["year_bucket_count"] = 0
        out["worst_year_cost_mean_bps"] = np.nan
    return pd.DataFrame(rows), out


def decide(row: Dict[str, Any], args: argparse.Namespace) -> Tuple[str, str, str]:
    hard: List[str] = []
    flags: List[str] = []
    def lt(key: str, threshold: float, reason: str):
        v = finite_float(row.get(key))
        if not math.isfinite(v) or v < threshold:
            hard.append(reason)
    def gt_abs(key: str, threshold: float, reason: str):
        v = finite_float(row.get(key))
        if math.isfinite(v) and abs(v) > threshold:
            hard.append(reason)
    def gt(key: str, threshold: float, reason: str):
        v = finite_float(row.get(key))
        if math.isfinite(v) and v > threshold:
            hard.append(reason)

    lt("full_n", args.min_events, "events_floor")
    lt("train_n", args.min_train_events, "train_events_floor")
    lt("oos_n", args.min_oos_events, "oos_events_floor")
    lt("source_h1_benchmark_cost_adjusted_residual_bps", args.min_h1_cost_residual_bps, "h1_residual_floor")
    lt("full_cost_mean_bps", args.min_full_cost_mean_bps, "full_cost_floor")
    lt("train_cost_mean_bps", args.min_train_cost_mean_bps, "train_cost_floor")
    lt("oos_cost_mean_bps", args.min_oos_cost_mean_bps, "oos_cost_floor")
    lt("full_mean_after_cost_plus_slip16_bps", args.min_full_slip16_mean_bps, "full_slip16_floor")
    lt("train_mean_after_cost_plus_slip16_bps", args.min_train_slip16_mean_bps, "train_slip16_floor")
    lt("oos_mean_after_cost_plus_slip16_bps", args.min_oos_slip16_mean_bps, "oos_slip16_floor")
    lt("worst_quarter_cost_mean_bps", args.min_worst_quarter_cost_bps, "worst_quarter_cost_floor")
    lt("worst_quarter_slip16_mean_bps", args.min_worst_quarter_slip16_bps, "worst_quarter_slip16_floor")
    lt("source_ex2025_cost_mean_bps", args.min_ex2025_cost_mean_bps, "ex2025_floor")
    lt("source_leave_one_year_out_min_cost_mean_bps", args.min_loyo_cost_mean_bps, "loyo_floor")
    lt("boot_p10_bps", args.min_boot_p10_bps, "bootstrap_p10_floor")
    lt("boot_prob_mean_gt_0_pct", args.min_boot_prob_mean_gt_0_pct, "bootstrap_prob_floor")
    gt_abs("full_median_mae_bps", args.max_full_median_mae_abs_bps, "full_median_mae_cap")
    gt_abs("oos_median_mae_bps", args.max_oos_median_mae_abs_bps, "oos_median_mae_cap")
    gt("full_touch_stop_100bps_pct", args.max_full_touch_stop_100_pct, "full_stop100_cap")
    gt("oos_touch_stop_100bps_pct", args.max_oos_touch_stop_100_pct, "oos_stop100_cap")
    gt("top3_win_share_pct", args.max_top3_win_share_pct, "win_concentration_cap")

    gap = finite_float(row.get("oos_train_gap_bps"))
    ratio = finite_float(row.get("oos_train_ratio"))
    q4ratio = finite_float(row.get("q4_to_full_cost_ratio"))
    if math.isfinite(gap) and gap > args.max_oos_train_gap_bps:
        flags.append("oos_train_gap_high")
    if math.isfinite(ratio) and ratio > args.max_oos_train_ratio:
        flags.append("oos_train_ratio_high")
    if math.isfinite(q4ratio) and q4ratio > args.max_q4_full_ratio:
        flags.append("q4_full_ratio_high")

    if hard:
        return "FAIL_STAGE40B_SURVIVOR_AUDIT_NO_PROMOTION", ";".join(hard), ";".join(flags)
    if flags:
        return "RECENCY_OR_CONCENTRATION_WATCH_ONLY_NO_PROMOTION", "", ";".join(flags)
    return "STRICT_STAGE40B_SURVIVOR_WATCH_ONLY_NO_PROMOTION", "", ""


def evaluate_survivor(spec_id: int, spec: pd.Series, ev: pd.DataFrame, cost_bps: float, args: argparse.Namespace) -> Tuple[Dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    row: Dict[str, Any] = {
        "stage": STAGE,
        "decision_scope": DECISION_SCOPE,
        "promotion": NO_GO,
        "ea": NO_GO,
        "paper_live": NO_GO,
        "live": NO_GO,
        "spec_id": spec_id,
        "family": spec.get("family", ""),
        "candidate": spec.get("candidate", ""),
        "side": spec.get("side", ""),
        "horizon_hours": spec.get("horizon_hours", np.nan),
        "params_json": spec.get("params_json", ""),
        "source_stage40_classification": spec.get("classification", ""),
        "source_h1_benchmark_cost_adjusted_residual_bps": finite_float(spec.get("h1_benchmark_cost_adjusted_residual_bps")),
        "source_cost_stressed_mean_bps": finite_float(spec.get("cost_stressed_mean_bps")),
        "source_event_clock_n": int(finite_float(spec.get("event_clock_n"), 0)),
        "source_ex2025_cost_mean_bps": finite_float(spec.get("ex2025_cost_mean_bps")),
        "source_leave_one_year_out_min_cost_mean_bps": finite_float(spec.get("leave_one_year_out_min_cost_mean_bps")),
        "source_worst_quarter_cost_mean_bps": finite_float(spec.get("worst_quarter_cost_mean_bps")),
        "source_worst_quarter_slip16_mean_bps": finite_float(spec.get("worst_quarter_slip16_mean_bps")),
    }
    row.update(metric_summary(ev, cost_bps, "full_"))
    splits = chronological_splits(ev)
    split_rows: List[Dict[str, Any]] = []
    for name, g in splits.items():
        sr = {"spec_id": spec_id, "candidate": row["candidate"], "segment": name}
        sr.update(metric_summary(g, cost_bps, ""))
        split_rows.append(sr)
        row.update(metric_summary(g, cost_bps, f"{name}_"))
    q_costs = [finite_float(row.get(f"q{i}_cost_mean_bps")) for i in range(1, 5)]
    q_slip = [finite_float(row.get(f"q{i}_mean_after_cost_plus_slip16_bps")) for i in range(1, 5)]
    row["worst_quarter_cost_mean_bps"] = float(np.nanmin(q_costs)) if any(math.isfinite(x) for x in q_costs) else np.nan
    row["worst_quarter_slip16_mean_bps"] = float(np.nanmin(q_slip)) if any(math.isfinite(x) for x in q_slip) else np.nan
    row["oos_train_gap_bps"] = finite_float(row.get("oos_cost_mean_bps")) - finite_float(row.get("train_cost_mean_bps"))
    denom = max(abs(finite_float(row.get("train_cost_mean_bps"))), args.ratio_floor_bps)
    row["oos_train_ratio"] = finite_float(row.get("oos_cost_mean_bps")) / denom if denom else np.nan
    full_cost = finite_float(row.get("full_cost_mean_bps"))
    row["q4_to_full_cost_ratio"] = finite_float(row.get("q4_cost_mean_bps")) / max(abs(full_cost), args.ratio_floor_bps)

    cost_series = to_num(ev.get("cost_stressed_final_bps", ev.get("final_bps", pd.Series(dtype=float)) - cost_bps))
    row.update(bootstrap_mean_ci(cost_series, seed=args.bootstrap_seed, n_boot=args.bootstrap_iterations))
    bucket_df, bucket_stats = year_month_audit(ev, cost_bps, spec_id)
    row.update(bucket_stats)
    classification, hard, flags = decide(row, args)
    row["classification"] = classification
    row["hard_fail_reasons"] = hard
    row["audit_flags"] = flags
    audited_ev = ev.copy()
    audited_ev.insert(0, "spec_id", spec_id)
    audited_ev.insert(1, "stage40b_classification", classification)
    return row, pd.DataFrame(split_rows), bucket_df, audited_ev


def write_markdown(path: Path, summary: Dict[str, Any], results: pd.DataFrame, split_df: pd.DataFrame, bucket_df: pd.DataFrame) -> None:
    lines: List[str] = []
    lines.append(f"# {STAGE}")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append("```text")
    lines.append(f"scope = {DECISION_SCOPE}")
    lines.append(f"promotion = {NO_GO}")
    lines.append(f"EA = {NO_GO}")
    lines.append(f"paper_live = {NO_GO}")
    lines.append(f"live = {NO_GO}")
    lines.append("```")
    lines.append("")
    lines.append("Stage40B is a dedicated research-only audit for strict Stage40 parallel-megascan survivors. It is not a promotion gate.")
    lines.append("")
    lines.append("## Input audit")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(summary.get("input_audit", {}), indent=2, ensure_ascii=False))
    lines.append("```")
    lines.append("")
    lines.append("## Classification counts")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(summary.get("classification_counts", {}), indent=2, ensure_ascii=False))
    lines.append("```")
    lines.append("")
    if not results.empty:
        cols = [
            "classification", "family", "candidate", "side", "horizon_hours", "full_n",
            "full_cost_mean_bps", "train_cost_mean_bps", "oos_cost_mean_bps",
            "worst_quarter_cost_mean_bps", "worst_quarter_slip16_mean_bps",
            "boot_p10_bps", "boot_prob_mean_gt_0_pct", "full_median_mae_bps",
            "oos_median_mae_bps", "full_touch_stop_100bps_pct", "oos_touch_stop_100bps_pct",
            "hard_fail_reasons", "audit_flags",
        ]
        present = [c for c in cols if c in results.columns]
        lines.append("## Survivor audit summary")
        lines.append("")
        lines.append(results[present].to_markdown(index=False))
        lines.append("")
    if not split_df.empty:
        lines.append("## Split audit")
        lines.append("")
        cols = [c for c in ["spec_id", "candidate", "segment", "n", "cost_mean_bps", "hit_rate_pct", "median_mae_bps", "touch_stop_100bps_pct", "mean_after_cost_plus_slip16_bps"] if c in split_df.columns]
        lines.append(split_df[cols].to_markdown(index=False))
        lines.append("")
    if not bucket_df.empty:
        lines.append("## Worst year/session buckets")
        lines.append("")
        b = bucket_df.copy()
        if "cost_mean_bps" in b.columns:
            b = b.sort_values("cost_mean_bps", ascending=True).head(20)
        cols = [c for c in ["spec_id", "dimension", "bucket", "n", "cost_mean_bps", "hit_rate_pct", "median_mae_bps", "touch_stop_100bps_pct", "mean_after_cost_plus_slip16_bps"] if c in b.columns]
        lines.append(b[cols].to_markdown(index=False))
        lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("- `STRICT_STAGE40B_SURVIVOR_WATCH_ONLY_NO_PROMOTION` means a survivor remains research-watch only and may proceed to a separate execution-feasibility audit.")
    lines.append("- `RECENCY_OR_CONCENTRATION_WATCH_ONLY_NO_PROMOTION` means the row still has positive behavior but is too dominated by recent/OOS or concentrated wins.")
    lines.append("- `FAIL_STAGE40B_SURVIVOR_AUDIT_NO_PROMOTION` means archive that survivor; do not add filters to rescue it.")
    lines.append("- All rows remain `NO_GO` for EA, paper-live, and live.")
    lines.append("")
    lines.append("## Next allowed step")
    lines.append("")
    lines.append("Only if one or more rows are `STRICT_STAGE40B_SURVIVOR_WATCH_ONLY_NO_PROMOTION`, run a separate Stage40C execution-feasibility / lower-timeframe confirmation audit. Otherwise archive Stage40.")
    path.write_text("\n".join(lines), encoding="utf-8")


def run(args: argparse.Namespace) -> None:
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_json = load_json(args.stage40_summary_json)
    summary_csv = read_csv_if_exists(args.stage40_summary_csv)
    survivors, survivor_audit = survivor_specs(summary_json, summary_csv)
    events_raw = read_csv_if_exists(args.stage40_events)
    if events_raw is None:
        events_raw = pd.DataFrame()
    events, event_time_meta = add_event_time_or_order(events_raw) if not events_raw.empty else (events_raw, {"mode": "missing_events_file"})

    result_rows: List[Dict[str, Any]] = []
    split_parts: List[pd.DataFrame] = []
    bucket_parts: List[pd.DataFrame] = []
    event_parts: List[pd.DataFrame] = []

    for i, spec in survivors.iterrows():
        spec_id = int(i + 1)
        ev = match_events(events, spec) if not events.empty else pd.DataFrame()
        row, split_df, bucket_df, aud_ev = evaluate_survivor(spec_id, spec, ev, args.cost_bps, args)
        result_rows.append(row)
        if not split_df.empty:
            split_parts.append(split_df)
        if not bucket_df.empty:
            bucket_parts.append(bucket_df)
        if not aud_ev.empty:
            event_parts.append(aud_ev)

    results = pd.DataFrame(result_rows)
    split_df = pd.concat(split_parts, ignore_index=True) if split_parts else pd.DataFrame()
    bucket_df = pd.concat(bucket_parts, ignore_index=True) if bucket_parts else pd.DataFrame()
    audited_events = pd.concat(event_parts, ignore_index=True) if event_parts else pd.DataFrame()

    if not results.empty:
        class_counts = {str(k): int(v) for k, v in results["classification"].value_counts(dropna=False).to_dict().items()}
    else:
        class_counts = {"NO_STRICT_STAGE40_SURVIVORS_TO_AUDIT": 1}

    paths = {
        "summary_csv": out_dir / "stage40b_survivor_path_stability_summary.csv",
        "split_csv": out_dir / "stage40b_survivor_split_audit.csv",
        "bucket_csv": out_dir / "stage40b_survivor_bucket_audit.csv",
        "events_csv": out_dir / "stage40b_survivor_audited_events.csv",
        "summary_json": out_dir / "stage40b_survivor_path_stability_summary.json",
        "markdown": out_dir / "stage40b_survivor_path_stability_audit.md",
    }
    results.to_csv(paths["summary_csv"], index=False)
    split_df.to_csv(paths["split_csv"], index=False)
    bucket_df.to_csv(paths["bucket_csv"], index=False)
    audited_events.to_csv(paths["events_csv"], index=False)

    summary = {
        "stage": STAGE,
        "decision_scope": DECISION_SCOPE,
        "promotion": NO_GO,
        "ea": NO_GO,
        "paper_live": NO_GO,
        "live": NO_GO,
        "parameters": vars(args),
        "input_audit": {
            "stage40_summary_json": {
                "path": args.stage40_summary_json,
                "loaded": True,
                "classification_counts": summary_json.get("classification_counts", {}),
                "strict_parallel_thesis_watch_count": summary_json.get("strict_parallel_thesis_watch_count"),
                "soft_parallel_thesis_watch_count": summary_json.get("soft_parallel_thesis_watch_count"),
            },
            "stage40_summary_source": survivor_audit,
            "stage40_events": {
                "path": args.stage40_events,
                "loaded": bool(not events_raw.empty),
                "rows": int(len(events_raw)),
                "columns": list(events_raw.columns) if not events_raw.empty else [],
                "event_time_meta": event_time_meta,
            },
        },
        "classification_counts": class_counts,
        "strict_stage40b_survivor_watch_count": int((results.get("classification", pd.Series(dtype=str)) == "STRICT_STAGE40B_SURVIVOR_WATCH_ONLY_NO_PROMOTION").sum()) if not results.empty else 0,
        "recency_or_concentration_watch_count": int((results.get("classification", pd.Series(dtype=str)) == "RECENCY_OR_CONCENTRATION_WATCH_ONLY_NO_PROMOTION").sum()) if not results.empty else 0,
        "outputs": {k: str(v) for k, v in paths.items()},
        "top_rows": results.replace({np.nan: None}).to_dict(orient="records") if not results.empty else [],
    }
    paths["summary_json"].write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(paths["markdown"], summary, results, split_df, bucket_df)
    print(json.dumps({
        "stage": STAGE,
        "promotion": NO_GO,
        "strict_stage40b_survivor_watch_count": summary["strict_stage40b_survivor_watch_count"],
        "classification_counts": class_counts,
        "summary_json": str(paths["summary_json"]),
        "markdown": str(paths["markdown"]),
    }, indent=2))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=STAGE)
    p.add_argument("--stage40-summary-json", required=True)
    p.add_argument("--stage40-events", required=True)
    p.add_argument("--stage40-summary-csv", default="")
    p.add_argument("--cost-bps", type=float, default=8.0)
    p.add_argument("--output-dir", default="reports/stage40b")
    p.add_argument("--min-events", type=int, default=40)
    p.add_argument("--min-train-events", type=int, default=20)
    p.add_argument("--min-oos-events", type=int, default=10)
    p.add_argument("--min-h1-cost-residual-bps", type=float, default=15.0)
    p.add_argument("--min-full-cost-mean-bps", type=float, default=20.0)
    p.add_argument("--min-train-cost-mean-bps", type=float, default=15.0)
    p.add_argument("--min-oos-cost-mean-bps", type=float, default=15.0)
    p.add_argument("--min-full-slip16-mean-bps", type=float, default=10.0)
    p.add_argument("--min-train-slip16-mean-bps", type=float, default=0.0)
    p.add_argument("--min-oos-slip16-mean-bps", type=float, default=10.0)
    p.add_argument("--min-ex2025-cost-mean-bps", type=float, default=10.0)
    p.add_argument("--min-loyo-cost-mean-bps", type=float, default=10.0)
    p.add_argument("--min-worst-quarter-cost-bps", type=float, default=0.0)
    p.add_argument("--min-worst-quarter-slip16-bps", type=float, default=0.0)
    p.add_argument("--min-boot-p10-bps", type=float, default=0.0)
    p.add_argument("--min-boot-prob-mean-gt-0-pct", type=float, default=80.0)
    p.add_argument("--max-full-median-mae-abs-bps", type=float, default=120.0)
    p.add_argument("--max-oos-median-mae-abs-bps", type=float, default=130.0)
    p.add_argument("--max-full-touch-stop-100-pct", type=float, default=50.0)
    p.add_argument("--max-oos-touch-stop-100-pct", type=float, default=55.0)
    p.add_argument("--max-top3-win-share-pct", type=float, default=35.0)
    p.add_argument("--max-oos-train-gap-bps", type=float, default=80.0)
    p.add_argument("--max-oos-train-ratio", type=float, default=3.0)
    p.add_argument("--max-q4-full-ratio", type=float, default=3.0)
    p.add_argument("--ratio-floor-bps", type=float, default=10.0)
    p.add_argument("--bootstrap-iterations", type=int, default=1000)
    p.add_argument("--bootstrap-seed", type=int, default=402)
    return p.parse_args()


def main() -> None:
    run(parse_args())


if __name__ == "__main__":
    main()
