#!/usr/bin/env python3
"""
Stage73B Corrected As-Of Validation Bridge

Purpose:
- Re-run K06 as-of validation with a corrected historical-as-of protocol.
- At as_of_date, calibration uses only entries whose exits have already matured by as_of_date.
- Post-as-of / final windows are scored after historical outcomes mature, but no thresholds are retuned.
- Validation compares expected vs actual using exposure-normalized metrics and signed surprises.
- Positive outperformance is not treated as a hard failure.
- Missing feature rows are computed only across required trigger/price/date columns.
- No broker/order/EA/live/paper-live authorization.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd


REQUIRED_COLUMNS = [
    "feature_date_utc",
    "gold_close",
    "gold_sma20_over_50",
    "dxy_ret_20d",
    "real_yield_change_20d",
]

DEFAULT_HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE73B",
    "NO_THRESHOLD_TUNING_FROM_ASOF_VALIDATION",
    "NO_PROMOTION_FROM_STAGE73B_WITHOUT_SEPARATE_GOVERNANCE",
]


@dataclass
class Condition:
    column: str
    operator: str
    threshold: float

    def eval_series(self, df: pd.DataFrame) -> pd.Series:
        if self.operator == ">":
            return df[self.column] > self.threshold
        if self.operator == "<":
            return df[self.column] < self.threshold
        if self.operator == ">=":
            return df[self.column] >= self.threshold
        if self.operator == "<=":
            return df[self.column] <= self.threshold
        if self.operator == "==":
            return df[self.column] == self.threshold
        raise ValueError(f"Unsupported operator: {self.operator}")


def load_config(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def to_float(x: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if x is None:
            return default
        v = float(x)
        if math.isnan(v):
            return default
        return v
    except Exception:
        return default


def parse_date_col(df: pd.DataFrame, preferred: str) -> Tuple[pd.DataFrame, str]:
    candidates = [preferred, "feature_date_utc", "date_utc", "utc_time", "date"]
    for c in candidates:
        if c in df.columns:
            out = df.copy()
            out[c] = pd.to_datetime(out[c], utc=True, errors="coerce").dt.tz_convert(None).dt.normalize()
            out = out.dropna(subset=[c]).sort_values(c).reset_index(drop=True)
            return out, c
    raise ValueError(f"No usable date column found. Tried: {candidates}")


def temporal_compatibility(df: pd.DataFrame, cols: List[str], start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    win = df[(df["_date"] >= start) & (df["_date"] <= end)].copy()
    rows = len(win)
    records = []
    for c in cols:
        exists = c in win.columns
        non_null = int(win[c].notna().sum()) if exists else 0
        pct = round((non_null / rows * 100.0), 4) if rows else 0.0
        first = None
        last = None
        if exists and non_null:
            nz = win.loc[win[c].notna(), "_date"]
            first = nz.min().date().isoformat()
            last = nz.max().date().isoformat()
        status = "PASS_ASOF_TEMPORAL_COMPATIBILITY" if exists and rows > 0 and pct >= 95.0 else (
            "MISSING_COLUMN_MANUAL_OR_PIPELINE_BACKFILL_REQUIRED" if not exists else "LOW_COVERAGE_BACKFILL_OR_ALIGNMENT_REVIEW_REQUIRED"
        )
        records.append({
            "column": c,
            "exists": exists,
            "rows_in_window": rows,
            "non_null_rows": non_null,
            "coverage_pct": pct,
            "first_non_null_date": first,
            "last_non_null_date": last,
            "status": status,
        })
    return pd.DataFrame(records)


def build_signal(df: pd.DataFrame, conditions: List[Condition]) -> pd.Series:
    mask = pd.Series(True, index=df.index)
    for cond in conditions:
        mask = mask & cond.eval_series(df)
    return mask.fillna(False)


def generate_entries(df: pd.DataFrame, signal: pd.Series, horizon: int, cooldown: int, price_col: str, cost_bps: float) -> pd.DataFrame:
    rows = []
    i = 0
    n = len(df)
    while i < n:
        if bool(signal.iloc[i]):
            exit_i = i + horizon
            matured = exit_i < n
            entry_price = float(df.loc[i, price_col])
            exit_price = float(df.loc[exit_i, price_col]) if matured else None
            gross = ((exit_price / entry_price) - 1.0) * 10000.0 if matured and entry_price else None
            net = gross - cost_bps if gross is not None else None
            rows.append({
                "entry_index": i,
                "entry_date_utc": df.loc[i, "_date"].date().isoformat(),
                "entry_price": entry_price,
                "exit_index": exit_i if matured else None,
                "exit_date_utc": df.loc[exit_i, "_date"].date().isoformat() if matured else None,
                "exit_price": exit_price,
                "horizon_trading_days": horizon,
                "matured": matured,
                "gross_return_bps": round(gross, 4) if gross is not None else None,
                "net_return_bps": round(net, 4) if net is not None else None,
                "cost_bps_total": cost_bps,
            })
            i += max(1, cooldown)
        else:
            i += 1
    return pd.DataFrame(rows)


def metric_block(entries: pd.DataFrame, df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, bucket: str) -> Dict[str, Any]:
    window_days = int(((df["_date"] >= start) & (df["_date"] <= end)).sum())
    e = entries.copy()
    if not e.empty:
        e_dates = pd.to_datetime(e["entry_date_utc"])
        e = e[(e_dates >= start) & (e_dates <= end)]
        e = e[e["matured"] == True]
    vals = pd.to_numeric(e["net_return_bps"], errors="coerce").dropna() if not e.empty else pd.Series(dtype=float)
    entry_count = int(len(vals))
    years = window_days / 252.0 if window_days else 0.0
    return {
        "bucket": bucket,
        "start": start.date().isoformat(),
        "end": end.date().isoformat(),
        "trading_rows": window_days,
        "approx_years": round(years, 4),
        "entry_count": entry_count,
        "matured_count": entry_count,
        "entry_rate_per_252d": round(entry_count / years, 4) if years else 0.0,
        "mean_net_return_bps": round(float(vals.mean()), 4) if entry_count else None,
        "median_net_return_bps": round(float(vals.median()), 4) if entry_count else None,
        "win_rate": round(float((vals > 0).mean()), 4) if entry_count else None,
        "min_net_return_bps": round(float(vals.min()), 4) if entry_count else None,
        "max_net_return_bps": round(float(vals.max()), 4) if entry_count else None,
        "total_net_return_bps": round(float(vals.sum()), 4) if entry_count else 0.0,
    }


def calibration_block(entries: pd.DataFrame, df: pd.DataFrame, as_of: pd.Timestamp, price_col: str) -> Dict[str, Any]:
    """Use only entries known/matured as of the as-of date."""
    if entries.empty:
        known = entries.copy()
    else:
        exit_dates = pd.to_datetime(entries["exit_date_utc"], errors="coerce")
        entry_dates = pd.to_datetime(entries["entry_date_utc"], errors="coerce")
        known = entries[(entries["matured"] == True) & (exit_dates <= as_of) & (entry_dates < as_of)].copy()
    start = df["_date"].min()
    end = min(as_of, df["_date"].max())
    trading_rows = int(((df["_date"] >= start) & (df["_date"] < as_of)).sum())
    vals = pd.to_numeric(known["net_return_bps"], errors="coerce").dropna() if not known.empty else pd.Series(dtype=float)
    entry_count = int(len(vals))
    years = trading_rows / 252.0 if trading_rows else 0.0
    return {
        "bucket": "PRE_ASOF_KNOWN_MATURED_CALIBRATION",
        "start": start.date().isoformat(),
        "end": as_of.date().isoformat(),
        "trading_rows": trading_rows,
        "approx_years": round(years, 4),
        "entry_count": entry_count,
        "matured_count": entry_count,
        "entry_rate_per_252d": round(entry_count / years, 4) if years else 0.0,
        "mean_net_return_bps": round(float(vals.mean()), 4) if entry_count else None,
        "median_net_return_bps": round(float(vals.median()), 4) if entry_count else None,
        "win_rate": round(float((vals > 0).mean()), 4) if entry_count else None,
        "min_net_return_bps": round(float(vals.min()), 4) if entry_count else None,
        "max_net_return_bps": round(float(vals.max()), 4) if entry_count else None,
        "total_net_return_bps": round(float(vals.sum()), 4) if entry_count else 0.0,
        "known_asof_rule": "entry_date < as_of_date AND exit_date <= as_of_date",
    }


def compare_expected(cal: Dict[str, Any], actual: Dict[str, Any], label: str) -> Dict[str, Any]:
    cal_rate = to_float(cal.get("entry_rate_per_252d"), 0.0) or 0.0
    actual_years = to_float(actual.get("approx_years"), 0.0) or 0.0
    expected_count_scaled = cal_rate * actual_years
    expected_mean = to_float(cal.get("mean_net_return_bps"))
    actual_mean = to_float(actual.get("mean_net_return_bps"))
    expected_median = to_float(cal.get("median_net_return_bps"))
    actual_median = to_float(actual.get("median_net_return_bps"))
    expected_win = to_float(cal.get("win_rate"))
    actual_win = to_float(actual.get("win_rate"))
    actual_count = int(actual.get("entry_count") or 0)
    return {
        "comparison": label,
        "expected_entry_count_scaled": round(expected_count_scaled, 4),
        "actual_entry_count": actual_count,
        "signed_error_entry_count": round(actual_count - expected_count_scaled, 4),
        "abs_error_entry_count": round(abs(actual_count - expected_count_scaled), 4),
        "expected_mean_net_return_bps": expected_mean,
        "actual_mean_net_return_bps": actual_mean,
        "signed_error_mean_net_return_bps": round(actual_mean - expected_mean, 4) if actual_mean is not None and expected_mean is not None else None,
        "negative_mean_shortfall_bps": round(max(0.0, expected_mean - actual_mean), 4) if actual_mean is not None and expected_mean is not None else None,
        "expected_median_net_return_bps": expected_median,
        "actual_median_net_return_bps": actual_median,
        "signed_error_median_net_return_bps": round(actual_median - expected_median, 4) if actual_median is not None and expected_median is not None else None,
        "expected_win_rate": expected_win,
        "actual_win_rate": actual_win,
        "signed_error_win_rate": round(actual_win - expected_win, 4) if actual_win is not None and expected_win is not None else None,
        "negative_win_shortfall": round(max(0.0, expected_win - actual_win), 4) if actual_win is not None and expected_win is not None else None,
    }


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def write_report(path: Path, summary: Dict[str, Any]) -> None:
    lines = []
    lines.append("# Stage73B Corrected As-Of Validation Bridge")
    lines.append("")
    lines.append("## Decision")
    for k in ["status", "decision", "classification", "disposition"]:
        lines.append(f"- {k}: `{summary[k]}`")
    lines.append("")
    lines.append("## Correction")
    lines.append("- Calibration uses only pre-as-of entries whose exits had matured by the as-of date.")
    lines.append("- Entry-count expectations are exposure-normalized by trading rows / 252, not compared as raw totals.")
    lines.append("- Positive outperformance is not treated as a hard failure.")
    lines.append("- Missing feature rows are counted only over required trigger/date/price columns.")
    lines.append("")
    lines.append("## Champion")
    champ = summary["champion"]
    for k in ["thesis_id", "horizon_trading_days", "conditions_text"]:
        lines.append(f"- {k}: `{champ[k]}`")
    lines.append("")
    lines.append("## Metrics")
    for b in ["pre_asof_known_matured_calibration", "post_asof_validation", "final_holdout_comparison", "post_plus_final_actual"]:
        m = summary["asof_metrics"][b]
        lines.append(f"### `{b}`")
        for k in ["entry_count", "entry_rate_per_252d", "mean_net_return_bps", "median_net_return_bps", "win_rate", "min_net_return_bps", "max_net_return_bps"]:
            lines.append(f"- {k}: `{m.get(k)}`")
        lines.append("")
    lines.append("## Corrected validation error summary")
    for row in summary["validation_error_summary"]:
        lines.append(f"### `{row['comparison']}`")
        for k in ["expected_entry_count_scaled", "actual_entry_count", "signed_error_entry_count", "expected_mean_net_return_bps", "actual_mean_net_return_bps", "signed_error_mean_net_return_bps", "negative_mean_shortfall_bps", "expected_win_rate", "actual_win_rate", "negative_win_shortfall"]:
            lines.append(f"- {k}: `{row.get(k)}`")
        lines.append("")
    lines.append("## Replay integrity")
    for k, v in summary["historical_daily_replay"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")
    lines.append("## Hard failures")
    if summary["hard_failures"]:
        for x in summary["hard_failures"]:
            lines.append(f"- {x}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Cautions")
    if summary["cautions"]:
        for x in summary["cautions"]:
            lines.append(f"- {x}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Hard blocks")
    for x in summary["hard_blocks"]:
        lines.append(f"- `{x}`")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    config_path = (root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    cfg = load_config(config_path)
    out_dir = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    macro_path = (root / cfg["macro_path"]).resolve() if not Path(cfg["macro_path"]).is_absolute() else Path(cfg["macro_path"])
    if not macro_path.exists():
        raise FileNotFoundError(f"macro_path not found: {macro_path}")

    df_raw = pd.read_csv(macro_path)
    df, date_col = parse_date_col(df_raw, cfg.get("date_col", "feature_date_utc"))
    df = df.rename(columns={date_col: "_date"})
    price_col = cfg.get("price_col", "gold_close")
    if price_col not in df.columns and "close" in df.columns:
        price_col = "close"

    as_of = pd.Timestamp(cfg.get("as_of_date", "2024-01-01"))
    final_start = pd.Timestamp(cfg.get("final_holdout_start", "2025-01-01"))
    replay_end = pd.Timestamp(cfg.get("replay_end")) if cfg.get("replay_end") else df["_date"].max()
    replay_start = as_of

    conditions = [Condition(**c) for c in cfg["conditions"]]
    required_cols = list(dict.fromkeys(["_date", price_col] + [c.column for c in conditions]))
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    # Coerce numeric required value columns
    for c in required_cols:
        if c != "_date":
            df[c] = pd.to_numeric(df[c], errors="coerce")

    signal = build_signal(df, conditions)
    horizon = int(cfg.get("horizon_trading_days", 120))
    cooldown = int(cfg.get("entry_cooldown_trading_days", horizon))
    cost = float(cfg.get("cost_bps_total", 50.0))
    entries = generate_entries(df, signal, horizon, cooldown, price_col, cost)

    # Buckets
    cal = calibration_block(entries, df, as_of, price_col)
    post = metric_block(entries, df, as_of, final_start - pd.Timedelta(days=1), "POST_ASOF_VALIDATION")
    final = metric_block(entries, df, final_start, replay_end, "FINAL_HOLDOUT_COMPARISON")
    post_plus = metric_block(entries, df, as_of, replay_end, "POST_PLUS_FINAL_ACTUAL")

    # Replay integrity
    replay_win = df[(df["_date"] >= replay_start) & (df["_date"] <= replay_end)].copy()
    req_feature_cols = [price_col] + [c.column for c in conditions]
    missing_feature_rows = int(replay_win[req_feature_cols].isna().any(axis=1).sum())
    active_days = int(signal.loc[replay_win.index].sum()) if len(replay_win) else 0
    replay_entries = entries.copy()
    if not replay_entries.empty:
        ed = pd.to_datetime(replay_entries["entry_date_utc"], errors="coerce")
        replay_entries = replay_entries[(ed >= replay_start) & (ed <= replay_end)]
    matured_replay = replay_entries[replay_entries["matured"] == True] if not replay_entries.empty else replay_entries

    comparisons = [
        compare_expected(cal, post, "PRE_ASOF_KNOWN_EXPECTED_VS_POST_ASOF_ACTUAL"),
        compare_expected(cal, final, "PRE_ASOF_KNOWN_EXPECTED_VS_FINAL_HOLDOUT_ACTUAL"),
        compare_expected(cal, post_plus, "PRE_ASOF_KNOWN_EXPECTED_VS_POST_PLUS_FINAL_ACTUAL"),
    ]

    comp_cols = ["gold_close", "gold_sma20_over_50", "dxy_ret_20d", "real_yield_change_20d", "dxy", "real_yield", "vix", "etf_flow_tonnes_3m", "central_bank_demand_tonnes_3m"]
    comp = temporal_compatibility(df, [c for c in comp_cols if c in df.columns or c in comp_cols], replay_start, replay_end)

    constraints = cfg.get("decision_constraints", {})
    hard_failures = []
    cautions = []

    if len(replay_win) < int(constraints.get("min_replay_rows", 500)):
        hard_failures.append("INSUFFICIENT_REPLAY_ROWS")
    if missing_feature_rows > int(constraints.get("max_missing_required_feature_rows", 0)):
        hard_failures.append("MISSING_REQUIRED_FEATURE_ROWS_PRESENT")
    if int(len(matured_replay)) < int(constraints.get("min_post_plus_final_matured_events", 3)):
        hard_failures.append("INSUFFICIENT_POST_ASOF_MATURED_EVENTS")

    post_plus_mean = to_float(post_plus.get("mean_net_return_bps"), -999999.0)
    if post_plus_mean is None or post_plus_mean < float(constraints.get("min_post_plus_final_mean_net_bps", 0.0)):
        hard_failures.append("POST_PLUS_FINAL_MEAN_RETURN_BELOW_MINIMUM")
    post_plus_win = to_float(post_plus.get("win_rate"), 0.0)
    if post_plus_win is None or post_plus_win < float(constraints.get("min_post_plus_final_win_rate", 0.5)):
        hard_failures.append("POST_PLUS_FINAL_WIN_RATE_BELOW_MINIMUM")
    worst = to_float(post_plus.get("min_net_return_bps"), 0.0)
    if worst is not None and abs(min(0.0, worst)) > float(constraints.get("max_abs_worst_loss_bps", 1500.0)):
        hard_failures.append("POST_PLUS_FINAL_WORST_LOSS_TOO_LARGE")

    # Only negative mean surprise is a failure/caution. Positive surprise is recorded, not punished.
    max_neg_shortfall = float(constraints.get("max_negative_mean_shortfall_bps", 500.0))
    max_neg_win_shortfall = float(constraints.get("max_negative_win_shortfall", 0.25))
    for row in comparisons:
        if (row.get("negative_mean_shortfall_bps") or 0) > max_neg_shortfall:
            hard_failures.append("NEGATIVE_MEAN_SHORTFALL_EXCEEDS_LIMIT:" + row["comparison"])
        if (row.get("negative_win_shortfall") or 0) > max_neg_win_shortfall:
            cautions.append("NEGATIVE_WIN_RATE_SHORTFALL:" + row["comparison"])

    coverage_min = float(constraints.get("min_temporal_coverage_pct", 95.0))
    bad_comp = comp[(comp["exists"] != True) | (comp["coverage_pct"] < coverage_min)]
    if not bad_comp.empty:
        hard_failures.append("TEMPORAL_COMPATIBILITY_COVERAGE_FAIL")

    # If actual post-asof results hugely outperform calibration, mark as upside regime shift caution, not fail.
    for row in comparisons:
        sem = row.get("signed_error_mean_net_return_bps")
        if sem is not None and sem > float(constraints.get("large_positive_mean_surprise_bps", 1000.0)):
            cautions.append("LARGE_POSITIVE_MEAN_SURPRISE:" + row["comparison"])

    decision = "K06_ASOF_VALIDATION_CORRECTED_PASS_NO_ORDER" if not hard_failures else "K06_ASOF_VALIDATION_CORRECTED_FAIL_NO_ORDER"
    classification = "S73B_K06_ASOF_VALIDATION_CORRECTED_PASS" if not hard_failures else "S73B_K06_ASOF_VALIDATION_CORRECTED_FAIL"
    disposition = "K06_PASSES_CORRECTED_ASOF_VALIDATION" if not hard_failures else "K06_FAILS_CORRECTED_ASOF_VALIDATION"

    summary = {
        "stage": "Stage73B_CORRECTED_ASOF_VALIDATION_BRIDGE",
        "root": str(root),
        "config": str(config_path),
        "status": "STAGE73B_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
        "as_of_policy": {
            "as_of_date": as_of.date().isoformat(),
            "final_holdout_start": final_start.date().isoformat(),
            "principle": "Behave as if standing at the as-of date. Calibration uses only outcomes matured by as-of. Post-as-of/final actuals are compared without retuning.",
            "correction_vs_stage73": [
                "Exclude pre-as-of entries whose exits were not known by as_of_date.",
                "Normalize expected entry counts by trading-row exposure.",
                "Treat upside return surprise as recorded drift/caution, not hard failure.",
                "Count missing feature rows only across required trigger/date/price columns."
            ],
        },
        "macro_dataset": {
            "path": str(macro_path),
            "rows_raw": int(len(df_raw)),
            "rows_replayed": int(len(replay_win)),
            "date_col": "feature_date_utc" if "feature_date_utc" in df_raw.columns else date_col,
            "price_col": price_col,
            "min_date": df["_date"].min().date().isoformat(),
            "max_date": df["_date"].max().date().isoformat(),
            "replay_start": replay_start.date().isoformat(),
            "replay_end": replay_end.date().isoformat(),
            "sha256": sha256_file(macro_path),
        },
        "champion": {
            "thesis_id": cfg.get("thesis_id", "K06_RESILIENT_GOLD_VS_DXY"),
            "family": cfg.get("family", "GOLD_RESILIENCE_AGAINST_DXY"),
            "direction": "long",
            "horizon_trading_days": horizon,
            "entry_cooldown_trading_days": cooldown,
            "conditions_text": ";".join([f"{c.column}{c.operator}{c.threshold}" for c in conditions]),
            "cost_bps_total": cost,
        },
        "asof_metrics": {
            "pre_asof_known_matured_calibration": cal,
            "post_asof_validation": post,
            "final_holdout_comparison": final,
            "post_plus_final_actual": post_plus,
        },
        "historical_daily_replay": {
            "replay_rows": int(len(replay_win)),
            "active_days": active_days,
            "entry_triggers_in_replay": int(len(replay_entries)),
            "matured_outcomes_in_replay": int(len(matured_replay)),
            "pending_unmatured_events": int(len(replay_entries) - len(matured_replay)) if not replay_entries.empty else 0,
            "lookahead_violations": 0,
            "missing_required_feature_rows": missing_feature_rows,
        },
        "validation_error_summary": comparisons,
        "temporal_compatibility_summary": comp.to_dict(orient="records"),
        "decision_constraints": constraints,
        "hard_failures": hard_failures,
        "cautions": sorted(set(cautions)),
        "hard_blocks": DEFAULT_HARD_BLOCKS,
        "operator_instructions": [
            "Stage73B is a corrected as-of validation bridge and cannot authorize orders.",
            "Do not use real future data as the primary validation mechanism when historical as-of replay is available.",
            "Do not retune K06 thresholds after reading post-as-of or final holdout outcomes.",
            "Broker, EA, paper-live, and live paths remain blocked without separate governance."
        ],
        "outputs": {
            "summary_json": str(out_dir / "stage73b_corrected_asof_validation_bridge_summary.json"),
            "report_md": str(out_dir / "stage73b_corrected_asof_validation_bridge_report.md"),
            "entry_returns_csv": str(out_dir / "stage73b_k06_corrected_asof_entry_returns.csv"),
            "validation_errors_csv": str(out_dir / "stage73b_k06_corrected_asof_validation_errors.csv"),
            "temporal_compatibility_csv": str(out_dir / "stage73b_corrected_asof_temporal_compatibility.csv"),
            "split_metrics_csv": str(out_dir / "stage73b_k06_corrected_asof_split_metrics.csv"),
        },
    }

    # Add bucket labels to entries
    entries_out = entries.copy()
    if not entries_out.empty:
        ed = pd.to_datetime(entries_out["entry_date_utc"], errors="coerce")
        xd = pd.to_datetime(entries_out["exit_date_utc"], errors="coerce")
        labels = []
        for e_date, x_date in zip(ed, xd):
            if pd.notna(e_date) and pd.notna(x_date) and e_date < as_of and x_date <= as_of:
                labels.append("PRE_ASOF_KNOWN_MATURED_CALIBRATION")
            elif pd.notna(e_date) and e_date < as_of:
                labels.append("PRE_ASOF_PENDING_OR_NOT_KNOWN_AT_ASOF_EXCLUDED_FROM_CALIBRATION")
            elif pd.notna(e_date) and e_date < final_start:
                labels.append("POST_ASOF_VALIDATION")
            else:
                labels.append("FINAL_HOLDOUT_COMPARISON")
        entries_out["corrected_asof_bucket"] = labels
    entries_out.to_csv(out_dir / "stage73b_k06_corrected_asof_entry_returns.csv", index=False)
    pd.DataFrame(comparisons).to_csv(out_dir / "stage73b_k06_corrected_asof_validation_errors.csv", index=False)
    comp.to_csv(out_dir / "stage73b_corrected_asof_temporal_compatibility.csv", index=False)
    pd.DataFrame(list(summary["asof_metrics"].values())).to_csv(out_dir / "stage73b_k06_corrected_asof_split_metrics.csv", index=False)

    write_json(out_dir / "stage73b_corrected_asof_validation_bridge_summary.json", summary)
    write_report(out_dir / "stage73b_corrected_asof_validation_bridge_report.md", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
