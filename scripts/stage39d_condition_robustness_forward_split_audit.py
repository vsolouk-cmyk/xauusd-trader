#!/usr/bin/env python3
"""
Stage39D_CONDITION_ROBUSTNESS_AND_FORWARD_SPLIT_AUDIT

Research-only audit for Stage39C condition-bucket watch rows.

Inputs:
  - Stage39C condition event rows CSV
  - Stage39C condition bucket summary CSV
  - optional Stage39C cross-condition matrix CSV
  - optional Stage39C summary JSON

Outputs:
  - condition robustness summary CSV
  - forward split CSV
  - audited event rows CSV
  - summary JSON
  - markdown report

This script intentionally does not promote any candidate to EA/paper/live.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


STAGE = "Stage39D_CONDITION_ROBUSTNESS_AND_FORWARD_SPLIT_AUDIT"
SCOPE = "RESEARCH_STAGE_ONLY_NO_PROMOTION"
NO_GO = "NO_GO"

WATCH_CLASS = "CONDITION_BUCKET_WATCH_ONLY_NO_PROMOTION"
STRICT_OUT = "STRICT_CONDITION_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION"
FORWARD_WATCH_OUT = "FORWARD_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION"
WEAK_OUT = "WEAK_FORWARD_ROBUSTNESS_NO_PROMOTION"
FAIL_OUT = "FAIL_CONDITION_ROBUSTNESS_NO_PROMOTION"
INSUFF_OUT = "INSUFFICIENT_CONDITION_EVENTS_NO_PROMOTION"
BAD_PATH_OUT = "ADVERSE_PATH_RISK_TOO_HIGH_NO_PROMOTION"
YEAR_WEAK_OUT = "YEAR_SPLIT_WEAK_NO_PROMOTION"

# Stage39C event rows may use entry_ts/exit_ts, while earlier stages used entry_utc/exit_utc.
# Keep this list schema-tolerant and prefer entry timestamps over generic time columns.
DEFAULT_EVENT_TIME_COLS = [
    "entry_utc",
    "entry_ts",
    "entry_time",
    "timestamp",
    "utc_time",
    "ts_utc",
    "time",
    "datetime",
    "date",
    "bar_time",
    "open_time",
]
DEFAULT_FINAL_COLS = ["final_bps", "mean_final_bps", "return_bps"]
DEFAULT_MAE_COLS = ["mae_bps", "median_mae_bps"]
DEFAULT_MFE_COLS = ["mfe_bps", "median_mfe_bps"]


def parse_float_list(value: str) -> List[float]:
    out: List[float] = []
    for part in str(value).split(","):
        part = part.strip()
        if not part:
            continue
        out.append(float(part))
    return out


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def first_existing_col(columns: Sequence[str], candidates: Sequence[str], required: bool = True) -> Optional[str]:
    lower = {str(c).lower(): c for c in columns}
    for cand in candidates:
        if cand in columns:
            return cand
        if cand.lower() in lower:
            return lower[cand.lower()]
    if required:
        raise ValueError(f"Required column not found; tried={list(candidates)} available={list(columns)}")
    return None


def norm_text(x: Any) -> str:
    if x is None:
        return "NA"
    if isinstance(x, float) and math.isnan(x):
        return "NA"
    s = str(x).strip()
    if not s or s.lower() in {"nan", "none", "null", "<na>"}:
        return "NA"
    return s


def norm_bucket(x: Any) -> str:
    s = norm_text(x)
    # Normalize integer-ish buckets because pandas may read "7" as 7.0 in one CSV and string in another.
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
    except Exception:
        pass
    return s


def to_numeric_series(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def read_csv_required(path: Path, label: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing {label}: {path}")
    df = pd.read_csv(path)
    if df.empty:
        raise ValueError(f"{label} is empty: {path}")
    return df


def read_optional_json(path: Optional[Path]) -> Dict[str, Any]:
    if path is None or not path.exists():
        return {"loaded": False, "path": str(path) if path else None}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    data["_loaded"] = True
    data["_path"] = str(path)
    return data


def assign_year(df: pd.DataFrame, time_col: str) -> pd.Series:
    ts = pd.to_datetime(df[time_col], errors="coerce", utc=True)
    return ts.dt.year


def add_time_order(df: pd.DataFrame, time_col: str) -> pd.DataFrame:
    out = df.copy()
    out["_entry_ts"] = pd.to_datetime(out[time_col], errors="coerce", utc=True)
    out = out.sort_values("_entry_ts").reset_index(drop=True)
    out["_time_order"] = np.arange(len(out), dtype=int)
    out["_chrono_frac"] = (out["_time_order"] + 1) / max(len(out), 1)
    return out


def filter_bucket_events(
    events: pd.DataFrame,
    candidate: str,
    dimension: str,
    bucket: str,
) -> pd.DataFrame:
    if "candidate" not in events.columns:
        raise ValueError("stage39c event rows must contain a 'candidate' column")
    if dimension not in events.columns:
        raise ValueError(f"stage39c event rows do not contain condition dimension '{dimension}'")
    mask = events["candidate"].astype(str).eq(str(candidate))
    event_bucket = events[dimension].map(norm_bucket)
    mask &= event_bucket.eq(norm_bucket(bucket))
    return events.loc[mask].copy()


def detect_cross_cols(df: pd.DataFrame) -> Optional[Tuple[str, str, str, str]]:
    # Prefer common names.
    candidates = [
        ("dimension_a", "bucket_a", "dimension_b", "bucket_b"),
        ("dim_a", "bucket_a", "dim_b", "bucket_b"),
        ("dimension_1", "bucket_1", "dimension_2", "bucket_2"),
        ("left_dimension", "left_bucket", "right_dimension", "right_bucket"),
    ]
    cols = set(df.columns)
    for tup in candidates:
        if all(x in cols for x in tup):
            return tup
    # Infer from ordered columns after candidate/classification if possible.
    dim_like = [c for c in df.columns if "dimension" in c.lower() or c.lower().startswith("dim")]
    bucket_like = [c for c in df.columns if "bucket" in c.lower()]
    if len(dim_like) >= 2 and len(bucket_like) >= 2:
        return (dim_like[0], bucket_like[0], dim_like[1], bucket_like[1])
    return None


def filter_cross_events(
    events: pd.DataFrame,
    candidate: str,
    dim_a: str,
    bucket_a: str,
    dim_b: str,
    bucket_b: str,
) -> pd.DataFrame:
    df = filter_bucket_events(events, candidate, dim_a, bucket_a)
    if dim_b not in df.columns:
        raise ValueError(f"stage39c event rows do not contain cross-condition dimension '{dim_b}'")
    return df.loc[df[dim_b].map(norm_bucket).eq(norm_bucket(bucket_b))].copy()


def pct(cond: pd.Series) -> float:
    if len(cond) == 0:
        return float("nan")
    return float(cond.mean() * 100.0)


def robust_mean(x: pd.Series) -> float:
    x = pd.to_numeric(x, errors="coerce").dropna()
    return float(x.mean()) if len(x) else float("nan")


def robust_median(x: pd.Series) -> float:
    x = pd.to_numeric(x, errors="coerce").dropna()
    return float(x.median()) if len(x) else float("nan")


def leave_one_year_out_min(df: pd.DataFrame, value_col: str, cost_bps: float = 0.0) -> Tuple[float, Dict[str, float]]:
    if "year" not in df.columns:
        return float("nan"), {}
    vals: Dict[str, float] = {}
    years = sorted([int(y) for y in pd.to_numeric(df["year"], errors="coerce").dropna().unique()])
    if len(years) <= 1:
        return float("nan"), vals
    for year in years:
        sub = df.loc[pd.to_numeric(df["year"], errors="coerce") != year]
        if len(sub) == 0:
            continue
        vals[str(year)] = robust_mean(sub[value_col]) - cost_bps
    return (float(min(vals.values())) if vals else float("nan"), vals)


def segment_stats(df: pd.DataFrame, final_col: str, cost_bps: float) -> Dict[str, Any]:
    if len(df) == 0:
        return {}
    out: Dict[str, Any] = {}
    d = df.sort_values("_entry_ts").reset_index(drop=True)
    n = len(d)

    def part(name: str, sub: pd.DataFrame) -> None:
        out[f"{name}_n"] = int(len(sub))
        out[f"{name}_mean_bps"] = robust_mean(sub[final_col])
        out[f"{name}_cost_mean_bps"] = out[f"{name}_mean_bps"] - cost_bps if not math.isnan(out[f"{name}_mean_bps"]) else float("nan")
        out[f"{name}_hit_rate_pct"] = pct(pd.to_numeric(sub[final_col], errors="coerce") > 0) if len(sub) else float("nan")

    half = n // 2
    part("first_half", d.iloc[:half])
    part("second_half", d.iloc[half:])
    q1 = n // 4
    q2 = n // 2
    q3 = (3 * n) // 4
    part("q1", d.iloc[:q1])
    part("q2", d.iloc[q1:q2])
    part("q3", d.iloc[q2:q3])
    part("q4", d.iloc[q3:])
    recent_start = int(max(0, math.floor(n * 0.67)))
    part("recent_third", d.iloc[recent_start:])
    return out


def path_stats(df: pd.DataFrame, final_col: str, mae_col: Optional[str], mfe_col: Optional[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    vals = pd.to_numeric(df[final_col], errors="coerce")
    out["n"] = int(vals.notna().sum())
    out["mean_final_bps"] = robust_mean(vals)
    out["median_final_bps"] = robust_median(vals)
    out["hit_rate_pct"] = pct(vals > 0)
    if mae_col and mae_col in df.columns:
        mae = pd.to_numeric(df[mae_col], errors="coerce")
        out["median_mae_bps"] = robust_median(mae)
        out["mean_mae_bps"] = robust_mean(mae)
        out["touch_stop_50bps_pct"] = pct(mae <= -50.0)
        out["touch_stop_100bps_pct"] = pct(mae <= -100.0)
        out["touch_stop_150bps_pct"] = pct(mae <= -150.0)
    else:
        out["median_mae_bps"] = float("nan")
        out["mean_mae_bps"] = float("nan")
        out["touch_stop_50bps_pct"] = float("nan")
        out["touch_stop_100bps_pct"] = float("nan")
        out["touch_stop_150bps_pct"] = float("nan")
    if mfe_col and mfe_col in df.columns:
        mfe = pd.to_numeric(df[mfe_col], errors="coerce")
        out["median_mfe_bps"] = robust_median(mfe)
        out["mean_mfe_bps"] = robust_mean(mfe)
        out["touch_target_50bps_pct"] = pct(mfe >= 50.0)
        out["touch_target_100bps_pct"] = pct(mfe >= 100.0)
        out["touch_target_150bps_pct"] = pct(mfe >= 150.0)
    else:
        out["median_mfe_bps"] = float("nan")
        out["mean_mfe_bps"] = float("nan")
        out["touch_target_50bps_pct"] = float("nan")
        out["touch_target_100bps_pct"] = float("nan")
        out["touch_target_150bps_pct"] = float("nan")
    return out


def yearly_stats(df: pd.DataFrame, final_col: str, cost_bps: float) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if "year" not in df.columns:
        return {
            "years_count": 0,
            "ex2025_n": 0,
            "ex2025_cost_mean_bps": float("nan"),
            "leave_one_year_out_min_cost_mean_bps": float("nan"),
            "leave_one_year_out_json": "{}",
            "year_cost_mean_json": "{}",
        }
    year_num = pd.to_numeric(df["year"], errors="coerce")
    tmp = df.copy()
    tmp["_year_num"] = year_num
    tmp["_final"] = pd.to_numeric(tmp[final_col], errors="coerce")
    years = sorted([int(y) for y in tmp["_year_num"].dropna().unique()])
    year_means = {}
    for y in years:
        sub = tmp.loc[tmp["_year_num"] == y]
        if len(sub):
            year_means[str(y)] = robust_mean(sub["_final"]) - cost_bps
    ex = tmp.loc[tmp["_year_num"] != 2025]
    out["years_count"] = int(len(years))
    out["ex2025_n"] = int(len(ex))
    out["ex2025_cost_mean_bps"] = robust_mean(ex["_final"]) - cost_bps if len(ex) else float("nan")
    loo_min, loo = leave_one_year_out_min(tmp, "_final", cost_bps)
    out["leave_one_year_out_min_cost_mean_bps"] = loo_min
    out["leave_one_year_out_json"] = json.dumps(loo, sort_keys=True)
    out["year_cost_mean_json"] = json.dumps(year_means, sort_keys=True)
    return out


def classify_row(
    row: Dict[str, Any],
    *,
    min_events: int,
    min_years: int,
    min_ex2025_events: int,
    min_cost_mean_bps: float,
    min_recent_cost_mean_bps: float,
    max_touch_stop_100_pct: float,
    max_median_mae_abs_bps: float,
    max_slippage_bps: float,
) -> str:
    n = row.get("n", 0)
    if n < min_events:
        return INSUFF_OUT

    years_count = row.get("years_count", 0)
    ex2025_n = row.get("ex2025_n", 0)
    if years_count < min_years or ex2025_n < min_ex2025_events:
        return YEAR_WEAK_OUT

    median_mae = row.get("median_mae_bps", float("nan"))
    stop100 = row.get("touch_stop_100bps_pct", float("nan"))
    if not math.isnan(median_mae) and abs(median_mae) > max_median_mae_abs_bps:
        return BAD_PATH_OUT
    if not math.isnan(stop100) and stop100 > max_touch_stop_100_pct:
        return BAD_PATH_OUT

    core = row.get("cost_stressed_mean_bps", float("nan"))
    ex2025 = row.get("ex2025_cost_mean_bps", float("nan"))
    loo = row.get("leave_one_year_out_min_cost_mean_bps", float("nan"))
    second_half = row.get("second_half_cost_mean_bps", float("nan"))
    q4 = row.get("q4_cost_mean_bps", float("nan"))
    recent = row.get("recent_third_cost_mean_bps", float("nan"))
    max_slip_col = f"mean_after_cost_plus_slip_{int(max_slippage_bps)}bps"
    max_slip = row.get(max_slip_col, float("nan"))

    critical_values = [core, ex2025, loo, second_half, recent, max_slip]
    if any(math.isnan(float(x)) for x in critical_values):
        return WEAK_OUT
    if core <= min_cost_mean_bps or ex2025 <= min_cost_mean_bps or loo <= min_cost_mean_bps:
        return FAIL_OUT
    if second_half <= min_recent_cost_mean_bps or recent <= min_recent_cost_mean_bps:
        return WEAK_OUT
    if max_slip <= min_recent_cost_mean_bps:
        return WEAK_OUT

    # A stricter internal watch: the most recent quarter also stays positive and median MAE is controlled.
    if (not math.isnan(q4)) and q4 > min_recent_cost_mean_bps and abs(median_mae) <= 80.0 and stop100 <= 40.0:
        return STRICT_OUT
    return FORWARD_WATCH_OUT


def build_condition_specs(bucket_df: pd.DataFrame, cross_df: Optional[pd.DataFrame]) -> List[Dict[str, Any]]:
    specs: List[Dict[str, Any]] = []

    if "classification" not in bucket_df.columns:
        raise ValueError("stage39c bucket summary must contain 'classification'")
    required = ["candidate", "dimension", "bucket"]
    for col in required:
        if col not in bucket_df.columns:
            raise ValueError(f"stage39c bucket summary missing required column '{col}'")

    single_watch = bucket_df.loc[bucket_df["classification"].astype(str).eq(WATCH_CLASS)].copy()
    for _, r in single_watch.iterrows():
        specs.append({
            "spec_type": "single_condition",
            "candidate": str(r["candidate"]),
            "dimension": str(r["dimension"]),
            "bucket": norm_bucket(r["bucket"]),
            "dimension_a": None,
            "bucket_a": None,
            "dimension_b": None,
            "bucket_b": None,
            "source_n": int(pd.to_numeric(pd.Series([r.get("n", np.nan)]), errors="coerce").iloc[0]) if "n" in r else None,
            "source_cost_stressed_mean_bps": float(pd.to_numeric(pd.Series([r.get("cost_stressed_mean_bps", np.nan)]), errors="coerce").iloc[0]) if "cost_stressed_mean_bps" in r else None,
        })

    if cross_df is not None and not cross_df.empty and "classification" in cross_df.columns:
        cross_cols = detect_cross_cols(cross_df)
        if cross_cols:
            da, ba, db, bb = cross_cols
            cross_watch = cross_df.loc[cross_df["classification"].astype(str).eq(WATCH_CLASS)].copy()
            for _, r in cross_watch.iterrows():
                specs.append({
                    "spec_type": "cross_condition",
                    "candidate": str(r["candidate"]),
                    "dimension": None,
                    "bucket": None,
                    "dimension_a": str(r[da]),
                    "bucket_a": norm_bucket(r[ba]),
                    "dimension_b": str(r[db]),
                    "bucket_b": norm_bucket(r[bb]),
                    "source_n": int(pd.to_numeric(pd.Series([r.get("n", np.nan)]), errors="coerce").iloc[0]) if "n" in r else None,
                    "source_cost_stressed_mean_bps": float(pd.to_numeric(pd.Series([r.get("cost_stressed_mean_bps", np.nan)]), errors="coerce").iloc[0]) if "cost_stressed_mean_bps" in r else None,
                })

    # De-duplicate deterministic specs.
    seen = set()
    deduped = []
    for s in specs:
        key = tuple((k, s.get(k)) for k in ["spec_type", "candidate", "dimension", "bucket", "dimension_a", "bucket_a", "dimension_b", "bucket_b"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(s)
    return deduped


def audit_spec(
    events: pd.DataFrame,
    spec: Dict[str, Any],
    *,
    time_col: str,
    final_col: str,
    mae_col: Optional[str],
    mfe_col: Optional[str],
    cost_bps: float,
    extra_slippage_bps: List[float],
    args: argparse.Namespace,
) -> Tuple[Dict[str, Any], pd.DataFrame, pd.DataFrame]:
    candidate = spec["candidate"]
    if spec["spec_type"] == "single_condition":
        df = filter_bucket_events(events, candidate, spec["dimension"], spec["bucket"])
    else:
        df = filter_cross_events(events, candidate, spec["dimension_a"], spec["bucket_a"], spec["dimension_b"], spec["bucket_b"])

    if time_col not in df.columns:
        raise ValueError(f"event rows missing time column '{time_col}'")
    df = add_time_order(df, time_col)
    if "year" not in df.columns:
        df["year"] = assign_year(df, time_col)

    # Normalize numeric columns.
    df[final_col] = pd.to_numeric(df[final_col], errors="coerce")
    if mae_col:
        df[mae_col] = pd.to_numeric(df[mae_col], errors="coerce")
    if mfe_col:
        df[mfe_col] = pd.to_numeric(df[mfe_col], errors="coerce")

    base: Dict[str, Any] = {
        "stage": STAGE,
        "decision_scope": SCOPE,
        "promotion": NO_GO,
        "spec_type": spec["spec_type"],
        "candidate": candidate,
        "dimension": spec.get("dimension"),
        "bucket": spec.get("bucket"),
        "dimension_a": spec.get("dimension_a"),
        "bucket_a": spec.get("bucket_a"),
        "dimension_b": spec.get("dimension_b"),
        "bucket_b": spec.get("bucket_b"),
        "source_stage39c_n": spec.get("source_n"),
        "source_stage39c_cost_stressed_mean_bps": spec.get("source_cost_stressed_mean_bps"),
    }

    stats = path_stats(df, final_col, mae_col, mfe_col)
    base.update(stats)
    base["cost_bps"] = cost_bps
    base["cost_stressed_mean_bps"] = base["mean_final_bps"] - cost_bps if not math.isnan(base["mean_final_bps"]) else float("nan")

    for slip in extra_slippage_bps:
        label = int(slip) if float(slip).is_integer() else slip
        base[f"mean_after_cost_plus_slip_{label}bps"] = base["mean_final_bps"] - cost_bps - slip if not math.isnan(base["mean_final_bps"]) else float("nan")

    base.update(yearly_stats(df, final_col, cost_bps))
    base.update(segment_stats(df, final_col, cost_bps))

    base["classification"] = classify_row(
        base,
        min_events=args.min_events,
        min_years=args.min_years,
        min_ex2025_events=args.min_ex2025_events,
        min_cost_mean_bps=args.min_cost_mean_bps,
        min_recent_cost_mean_bps=args.min_recent_cost_mean_bps,
        max_touch_stop_100_pct=args.max_touch_stop_100_pct,
        max_median_mae_abs_bps=args.max_median_mae_abs_bps,
        max_slippage_bps=max(extra_slippage_bps) if extra_slippage_bps else 0.0,
    )

    split_rows = []
    for segment_name in ["first_half", "second_half", "q1", "q2", "q3", "q4", "recent_third"]:
        split_rows.append({
            "stage": STAGE,
            "candidate": candidate,
            "spec_type": spec["spec_type"],
            "dimension": spec.get("dimension"),
            "bucket": spec.get("bucket"),
            "dimension_a": spec.get("dimension_a"),
            "bucket_a": spec.get("bucket_a"),
            "dimension_b": spec.get("dimension_b"),
            "bucket_b": spec.get("bucket_b"),
            "segment": segment_name,
            "n": base.get(f"{segment_name}_n"),
            "mean_bps": base.get(f"{segment_name}_mean_bps"),
            "cost_mean_bps": base.get(f"{segment_name}_cost_mean_bps"),
            "hit_rate_pct": base.get(f"{segment_name}_hit_rate_pct"),
        })

    df_out = df.copy()
    for k, v in base.items():
        if k in {"leave_one_year_out_json", "year_cost_mean_json"}:
            continue
        if k not in df_out.columns and isinstance(v, (str, int, float, bool, type(None))):
            df_out[k] = v
    return base, df_out, pd.DataFrame(split_rows)


def markdown_table(df: pd.DataFrame, cols: List[str], max_rows: int = 50) -> str:
    if df.empty:
        return "_No rows._\n"
    d = df.copy()
    d = d[cols].head(max_rows)
    try:
        return d.to_markdown(index=False)
    except Exception:
        return d.to_csv(index=False)


def write_markdown_report(
    path: Path,
    summary: Dict[str, Any],
    condition_df: pd.DataFrame,
    split_df: pd.DataFrame,
) -> None:
    top_cols = [
        "classification", "spec_type", "candidate", "dimension", "bucket",
        "dimension_a", "bucket_a", "dimension_b", "bucket_b", "n",
        "mean_final_bps", "cost_stressed_mean_bps", "hit_rate_pct",
        "median_mae_bps", "median_mfe_bps", "ex2025_cost_mean_bps",
        "leave_one_year_out_min_cost_mean_bps", "second_half_cost_mean_bps",
        "q4_cost_mean_bps", "recent_third_cost_mean_bps",
        "touch_stop_100bps_pct", "touch_target_100bps_pct",
        "mean_after_cost_plus_slip_16bps"
    ]
    split_cols = [
        "candidate", "spec_type", "dimension", "bucket", "dimension_a", "bucket_a",
        "dimension_b", "bucket_b", "segment", "n", "mean_bps", "cost_mean_bps", "hit_rate_pct"
    ]

    ordered = condition_df.sort_values(
        by=["classification", "cost_stressed_mean_bps"],
        ascending=[True, False],
        na_position="last",
    ) if not condition_df.empty else condition_df

    with path.open("w", encoding="utf-8") as f:
        f.write(f"# {STAGE}\n\n")
        f.write("## Decision\n\n")
        f.write("```text\n")
        f.write(f"scope = {SCOPE}\n")
        f.write("promotion = NO_GO\nEA = NO_GO\npaper_live = NO_GO\nlive = NO_GO\n")
        f.write("```\n\n")
        f.write("Stage39D audits Stage39C condition-watch buckets for forward robustness. It is not a promotion gate.\n\n")
        f.write("## Classification counts\n\n")
        f.write("```json\n")
        f.write(json.dumps(summary["classification_counts"], indent=2, ensure_ascii=False))
        f.write("\n```\n\n")
        f.write("## Audited condition rows\n\n")
        f.write(markdown_table(ordered, [c for c in top_cols if c in ordered.columns], max_rows=100))
        f.write("\n\n")
        f.write("## Forward split rows\n\n")
        f.write(markdown_table(split_df, [c for c in split_cols if c in split_df.columns], max_rows=200))
        f.write("\n\n")
        f.write("## Interpretation\n\n")
        f.write("- `STRICT_CONDITION_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION` means the bucket survives this strict research audit only; it is still not tradable.\n")
        f.write("- `FORWARD_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION` means the bucket has some forward robustness but still needs a separate out-of-sample/frozen-rule audit.\n")
        f.write("- `WEAK_FORWARD_ROBUSTNESS_NO_PROMOTION`, `FAIL_CONDITION_ROBUSTNESS_NO_PROMOTION`, `YEAR_SPLIT_WEAK_NO_PROMOTION`, and `ADVERSE_PATH_RISK_TOO_HIGH_NO_PROMOTION` should not be extended with more filters.\n")
        f.write("- All Stage39D rows remain `NO_GO` for EA, paper-live, and live.\n\n")
        f.write("## Next allowed step\n\n")
        f.write("Only if one or more rows are `STRICT_CONDITION_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION` or `FORWARD_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION`, the next step is `Stage39E_FROZEN_RULE_OUT_OF_SAMPLE_AUDIT`.\n\n")
        f.write("If no row survives, archive Stage39A-D and do not continue filtering.\n")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=STAGE)
    p.add_argument("--stage39c-summary", default="reports/stage39c/stage39c_condition_diagnostic_summary.json")
    p.add_argument("--stage39c-events", default="reports/stage39c/stage39c_condition_event_rows.csv")
    p.add_argument("--stage39c-buckets", default="reports/stage39c/stage39c_condition_bucket_summary.csv")
    p.add_argument("--stage39c-cross", default="reports/stage39c/stage39c_condition_cross_matrix.csv")
    p.add_argument("--cost-bps", type=float, default=8.0)
    p.add_argument("--extra-slippage-bps", default="0,4,8,12,16")
    p.add_argument("--min-events", type=int, default=30)
    p.add_argument("--min-years", type=int, default=4)
    p.add_argument("--min-ex2025-events", type=int, default=20)
    p.add_argument("--min-cost-mean-bps", type=float, default=15.0)
    p.add_argument("--min-recent-cost-mean-bps", type=float, default=10.0)
    p.add_argument("--max-touch-stop-100-pct", type=float, default=45.0)
    p.add_argument("--max-median-mae-abs-bps", type=float, default=100.0)
    p.add_argument("--output-dir", default="reports/stage39d")
    return p.parse_args()


def run(args: argparse.Namespace) -> None:
    out_dir = Path(args.output_dir)
    ensure_dir(out_dir)

    summary_json = read_optional_json(Path(args.stage39c_summary))
    events = read_csv_required(Path(args.stage39c_events), "Stage39C event rows")
    bucket_df = read_csv_required(Path(args.stage39c_buckets), "Stage39C bucket summary")
    cross_df = None
    cross_path = Path(args.stage39c_cross)
    if cross_path.exists() and cross_path.stat().st_size > 0:
        try:
            cross_df = pd.read_csv(cross_path)
        except pd.errors.EmptyDataError:
            cross_df = None

    time_col = first_existing_col(events.columns, DEFAULT_EVENT_TIME_COLS, required=True)
    final_col = first_existing_col(events.columns, DEFAULT_FINAL_COLS, required=True)
    mae_col = first_existing_col(events.columns, DEFAULT_MAE_COLS, required=False)
    mfe_col = first_existing_col(events.columns, DEFAULT_MFE_COLS, required=False)

    if "candidate" not in events.columns:
        raise ValueError("Stage39C event rows must include 'candidate'")
    if "year" not in events.columns:
        events["year"] = assign_year(events, time_col)

    extra_slippage = parse_float_list(args.extra_slippage_bps)
    specs = build_condition_specs(bucket_df, cross_df)

    condition_rows: List[Dict[str, Any]] = []
    event_rows_out: List[pd.DataFrame] = []
    split_rows_out: List[pd.DataFrame] = []
    errors: List[Dict[str, Any]] = []

    for spec in specs:
        try:
            row, ev, splits = audit_spec(
                events,
                spec,
                time_col=time_col,
                final_col=final_col,
                mae_col=mae_col,
                mfe_col=mfe_col,
                cost_bps=args.cost_bps,
                extra_slippage_bps=extra_slippage,
                args=args,
            )
            condition_rows.append(row)
            event_rows_out.append(ev)
            split_rows_out.append(splits)
        except Exception as exc:
            err = {"spec": spec, "error": repr(exc)}
            errors.append(err)

    condition_df = pd.DataFrame(condition_rows)
    if not condition_df.empty:
        # deterministic column order
        first_cols = [
            "stage", "decision_scope", "promotion", "classification", "spec_type", "candidate",
            "dimension", "bucket", "dimension_a", "bucket_a", "dimension_b", "bucket_b", "n",
            "mean_final_bps", "median_final_bps", "cost_stressed_mean_bps", "hit_rate_pct",
            "median_mae_bps", "median_mfe_bps", "ex2025_cost_mean_bps",
            "leave_one_year_out_min_cost_mean_bps", "second_half_cost_mean_bps",
            "q4_cost_mean_bps", "recent_third_cost_mean_bps",
            "touch_stop_100bps_pct", "touch_target_100bps_pct",
        ]
        remaining = [c for c in condition_df.columns if c not in first_cols]
        condition_df = condition_df[[c for c in first_cols if c in condition_df.columns] + remaining]
        condition_df = condition_df.sort_values(
            by=["classification", "cost_stressed_mean_bps", "n"],
            ascending=[True, False, False],
            na_position="last",
        ).reset_index(drop=True)

    split_df = pd.concat(split_rows_out, ignore_index=True) if split_rows_out else pd.DataFrame()
    event_df = pd.concat(event_rows_out, ignore_index=True) if event_rows_out else pd.DataFrame()

    classification_counts = condition_df["classification"].value_counts(dropna=False).to_dict() if not condition_df.empty else {}

    final_summary = {
        "stage": STAGE,
        "decision_scope": SCOPE,
        "promotion": NO_GO,
        "ea": NO_GO,
        "paper_live": NO_GO,
        "live": NO_GO,
        "parameters": {
            "cost_bps": args.cost_bps,
            "extra_slippage_bps": extra_slippage,
            "min_events": args.min_events,
            "min_years": args.min_years,
            "min_ex2025_events": args.min_ex2025_events,
            "min_cost_mean_bps": args.min_cost_mean_bps,
            "min_recent_cost_mean_bps": args.min_recent_cost_mean_bps,
            "max_touch_stop_100_pct": args.max_touch_stop_100_pct,
            "max_median_mae_abs_bps": args.max_median_mae_abs_bps,
        },
        "input_files": {
            "stage39c_summary": str(args.stage39c_summary),
            "stage39c_events": str(args.stage39c_events),
            "stage39c_buckets": str(args.stage39c_buckets),
            "stage39c_cross": str(args.stage39c_cross),
        },
        "stage39c_context": {
            "summary_loaded": bool(summary_json.get("_loaded", False)),
            "candidate_watch_count": summary_json.get("condition_candidate_watch_count"),
            "condition_bucket_watch_count": summary_json.get("condition_bucket_watch_count"),
            "bucket_classification_counts": summary_json.get("bucket_classification_counts"),
            "cross_classification_counts": summary_json.get("cross_classification_counts"),
        },
        "detected_columns": {
            "event_time": time_col,
            "final_bps": final_col,
            "mae_bps": mae_col,
            "mfe_bps": mfe_col,
        },
        "watch_specs_total": len(specs),
        "watch_specs_audited": int(len(condition_df)),
        "errors": errors,
        "classification_counts": classification_counts,
        "survivor_watch_count": int(sum(condition_df["classification"].isin([STRICT_OUT, FORWARD_WATCH_OUT]))) if not condition_df.empty else 0,
        "outputs": {
            "condition_robustness_csv": str(out_dir / "stage39d_condition_robustness_summary.csv"),
            "forward_split_csv": str(out_dir / "stage39d_forward_split_audit.csv"),
            "audited_event_rows_csv": str(out_dir / "stage39d_condition_audited_event_rows.csv"),
            "summary_json": str(out_dir / "stage39d_condition_robustness_summary.json"),
            "markdown": str(out_dir / "stage39d_condition_robustness_forward_split.md"),
        },
    }

    condition_csv = out_dir / "stage39d_condition_robustness_summary.csv"
    split_csv = out_dir / "stage39d_forward_split_audit.csv"
    events_csv = out_dir / "stage39d_condition_audited_event_rows.csv"
    summary_path = out_dir / "stage39d_condition_robustness_summary.json"
    md_path = out_dir / "stage39d_condition_robustness_forward_split.md"

    condition_df.to_csv(condition_csv, index=False)
    split_df.to_csv(split_csv, index=False)
    event_df.to_csv(events_csv, index=False)
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(final_summary, f, indent=2, ensure_ascii=False)
    write_markdown_report(md_path, final_summary, condition_df, split_df)

    print(json.dumps({
        "stage": STAGE,
        "promotion": NO_GO,
        "watch_specs_audited": final_summary["watch_specs_audited"],
        "classification_counts": classification_counts,
        "survivor_watch_count": final_summary["survivor_watch_count"],
        "outputs": final_summary["outputs"],
    }, indent=2, ensure_ascii=False))


def main() -> None:
    run(parse_args())


if __name__ == "__main__":
    main()
