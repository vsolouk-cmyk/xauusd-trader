#!/usr/bin/env python3
"""
Stage39E_FROZEN_RULE_OUT_OF_SAMPLE_AUDIT

Research-only frozen-rule audit for Stage39D surviving condition rows.

Important:
- This is NOT a promotion gate.
- It does NOT approve EA, paper-live, or live deployment.
- It freezes condition rows identified by Stage39D and evaluates their chronological
  held-out behavior, year robustness, cost/slippage stress, and adverse-path risk.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


STAGE = "Stage39E_FROZEN_RULE_OUT_OF_SAMPLE_AUDIT"
DECISION_SCOPE = "RESEARCH_STAGE_ONLY_NO_PROMOTION"
PROMOTION = "NO_GO"

SURVIVOR_CLASSIFICATIONS = {
    "STRICT_CONDITION_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION",
    "FORWARD_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION",
}

TIME_COL_CANDIDATES = [
    "entry_ts",
    "entry_utc",
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

REQUIRED_EVENT_COLS = ["candidate", "final_bps"]


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        if pd.isna(obj):
            return None
        return float(obj)
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    if pd.isna(obj):
        return None
    return str(obj)


def as_str_clean(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, float) and math.isnan(x):
        return ""
    s = str(x).strip()
    if s.lower() in {"nan", "none", "null"}:
        return ""
    return s


def is_na_bucket(x: Any) -> bool:
    s = as_str_clean(x)
    return s == "" or s.upper() in {"NA", "N/A", "NONE", "NULL", "NAN"}


def norm_bucket(x: Any) -> str:
    s = as_str_clean(x)
    if is_na_bucket(s):
        return "NA"
    return s


def first_existing_col(columns: Iterable[str], candidates: Sequence[str], required: bool = True) -> Optional[str]:
    lower_map = {str(c).lower(): c for c in columns}
    for cand in candidates:
        if cand in columns:
            return cand
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    if required:
        raise ValueError(f"Required column not found; tried={list(candidates)} available={list(columns)}")
    return None


def read_csv_checked(path: str | Path, name: str) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"{name} not found: {p}")
    if p.stat().st_size == 0:
        raise ValueError(f"{name} is empty: {p}")
    return pd.read_csv(p)


def load_stage39d_survivors(path: str | Path) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    raw = read_csv_checked(path, "Stage39D robustness summary CSV")
    required = ["classification", "spec_type", "candidate"]
    missing = [c for c in required if c not in raw.columns]
    if missing:
        raise ValueError(f"Stage39D summary missing required columns: {missing}; available={list(raw.columns)}")

    survivors = raw[raw["classification"].astype(str).isin(SURVIVOR_CLASSIFICATIONS)].copy()
    survivors = survivors.reset_index(drop=True)
    meta = {
        "path": str(path),
        "loaded_rows": int(len(raw)),
        "survivor_rows": int(len(survivors)),
        "classification_counts": raw["classification"].astype(str).value_counts(dropna=False).to_dict(),
        "survivor_classifications": sorted(SURVIVOR_CLASSIFICATIONS),
    }
    return survivors, meta


def load_events(path: str | Path, cost_bps: float) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    events = read_csv_checked(path, "Stage39C condition event rows CSV")
    missing = [c for c in REQUIRED_EVENT_COLS if c not in events.columns]
    if missing:
        raise ValueError(f"Stage39C event rows missing required columns: {missing}; available={list(events.columns)}")

    time_col = first_existing_col(events.columns, TIME_COL_CANDIDATES, required=True)
    events = events.copy()
    events["_event_time"] = pd.to_datetime(events[time_col], utc=True, errors="coerce")
    bad_time = int(events["_event_time"].isna().sum())
    if bad_time:
        events = events.dropna(subset=["_event_time"]).copy()
    events = events.sort_values("_event_time").reset_index(drop=True)

    for c in ["final_bps", "cost_stressed_final_bps", "mae_bps", "mfe_bps"]:
        if c in events.columns:
            events[c] = pd.to_numeric(events[c], errors="coerce")
    if "cost_stressed_final_bps" not in events.columns:
        events["cost_stressed_final_bps"] = pd.to_numeric(events["final_bps"], errors="coerce") - float(cost_bps)
    if "year" not in events.columns:
        events["year"] = events["_event_time"].dt.year
    else:
        events["year"] = pd.to_numeric(events["year"], errors="coerce").fillna(events["_event_time"].dt.year).astype(int)

    meta = {
        "path": str(path),
        "loaded_rows_before_time_drop": int(len(events) + bad_time),
        "loaded_rows": int(len(events)),
        "bad_time_rows_dropped": bad_time,
        "time_column": time_col,
        "date_min": events["_event_time"].min().isoformat() if len(events) else None,
        "date_max": events["_event_time"].max().isoformat() if len(events) else None,
        "columns": list(events.columns),
    }
    return events, meta


def row_spec_label(row: pd.Series) -> str:
    spec_type = as_str_clean(row.get("spec_type"))
    candidate = as_str_clean(row.get("candidate"))
    if spec_type == "cross_condition":
        return (
            f"{candidate} :: "
            f"{as_str_clean(row.get('dimension_a'))}={norm_bucket(row.get('bucket_a'))}"
            f" & {as_str_clean(row.get('dimension_b'))}={norm_bucket(row.get('bucket_b'))}"
        )
    return f"{candidate} :: {as_str_clean(row.get('dimension'))}={norm_bucket(row.get('bucket'))}"


def match_bucket(series: pd.Series, bucket: Any) -> pd.Series:
    if is_na_bucket(bucket):
        return series.map(lambda x: is_na_bucket(x))
    target = norm_bucket(bucket)
    return series.map(lambda x: norm_bucket(x) == target)


def filter_events_for_spec(events: pd.DataFrame, row: pd.Series) -> pd.DataFrame:
    candidate = as_str_clean(row.get("candidate"))
    if not candidate:
        raise ValueError("Stage39D survivor row has empty candidate.")
    mask = events["candidate"].astype(str) == candidate

    spec_type = as_str_clean(row.get("spec_type"))
    if spec_type == "cross_condition":
        dim_a = as_str_clean(row.get("dimension_a"))
        dim_b = as_str_clean(row.get("dimension_b"))
        if not dim_a or not dim_b:
            raise ValueError(f"Cross condition row missing dimension_a/dimension_b: {row.to_dict()}")
        if dim_a not in events.columns or dim_b not in events.columns:
            raise ValueError(
                f"Stage39C event rows missing cross dimensions {dim_a}/{dim_b}; available={list(events.columns)}"
            )
        mask &= match_bucket(events[dim_a], row.get("bucket_a"))
        mask &= match_bucket(events[dim_b], row.get("bucket_b"))
    else:
        dim = as_str_clean(row.get("dimension"))
        if not dim:
            raise ValueError(f"Single condition row missing dimension: {row.to_dict()}")
        if dim not in events.columns:
            raise ValueError(f"Stage39C event rows missing dimension {dim}; available={list(events.columns)}")
        mask &= match_bucket(events[dim], row.get("bucket"))

    out = events[mask].copy()
    out = out.sort_values("_event_time").reset_index(drop=True)
    return out


def safe_mean(s: pd.Series) -> Optional[float]:
    s = pd.to_numeric(s, errors="coerce").dropna()
    if len(s) == 0:
        return None
    return float(s.mean())


def safe_median(s: pd.Series) -> Optional[float]:
    s = pd.to_numeric(s, errors="coerce").dropna()
    if len(s) == 0:
        return None
    return float(s.median())


def hit_rate_pct(s: pd.Series) -> Optional[float]:
    s = pd.to_numeric(s, errors="coerce").dropna()
    if len(s) == 0:
        return None
    return float((s > 0).mean() * 100.0)


def pct_true(s: pd.Series) -> Optional[float]:
    if s is None or len(s) == 0:
        return None
    vals = pd.to_numeric(s, errors="coerce").dropna()
    if len(vals) == 0:
        vals = s.dropna()
        if len(vals) == 0:
            return None
        return float(vals.astype(bool).mean() * 100.0)
    return float((vals != 0).mean() * 100.0)


def leave_one_year_out_min_cost_mean(df: pd.DataFrame) -> Tuple[Optional[float], Dict[str, Optional[float]]]:
    if len(df) == 0 or "year" not in df.columns:
        return None, {}
    years = sorted([int(y) for y in pd.Series(df["year"]).dropna().unique()])
    out: Dict[str, Optional[float]] = {}
    for y in years:
        subset = df[df["year"] != y]
        out[str(y)] = safe_mean(subset["cost_stressed_final_bps"]) if len(subset) else None
    valid = [v for v in out.values() if v is not None]
    return (float(min(valid)) if valid else None), out


def year_cost_mean_json(df: pd.DataFrame) -> Dict[str, Optional[float]]:
    if len(df) == 0 or "year" not in df.columns:
        return {}
    out = {}
    for y, g in df.groupby("year", dropna=True):
        out[str(int(y))] = safe_mean(g["cost_stressed_final_bps"])
    return out


def slice_chrono(df: pd.DataFrame, name: str, oos_fraction: float = 0.33) -> pd.DataFrame:
    if len(df) == 0:
        return df.copy()
    d = df.sort_values("_event_time").reset_index(drop=True)
    n = len(d)
    if name == "train":
        cutoff = max(1, int(math.floor(n * (1.0 - oos_fraction))))
        return d.iloc[:cutoff].copy()
    if name == "oos":
        cutoff = max(1, int(math.floor(n * (1.0 - oos_fraction))))
        return d.iloc[cutoff:].copy()
    if name == "first_half":
        return d.iloc[: max(1, n // 2)].copy()
    if name == "second_half":
        return d.iloc[max(1, n // 2):].copy()
    if name == "recent_third":
        start = max(0, int(math.floor(n * (2.0 / 3.0))))
        return d.iloc[start:].copy()
    if name.startswith("q"):
        q = int(name[1])
        edges = [0, int(math.floor(n * 0.25)), int(math.floor(n * 0.50)), int(math.floor(n * 0.75)), n]
        return d.iloc[edges[q - 1]:edges[q]].copy()
    raise ValueError(name)


def calc_stats(
    df: pd.DataFrame,
    *,
    prefix: str = "",
    extra_slippage_bps: Sequence[float] = (),
    cost_bps: float = 8.0,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    p = f"{prefix}_" if prefix else ""
    out[p + "n"] = int(len(df))
    if len(df) == 0:
        for k in [
            "mean_final_bps", "median_final_bps", "cost_mean_bps", "hit_rate_pct",
            "median_mae_bps", "median_mfe_bps", "mean_mae_bps", "mean_mfe_bps",
            "touch_stop_100bps_pct", "touch_target_100bps_pct",
        ]:
            out[p + k] = None
        for slip in extra_slippage_bps:
            out[p + f"mean_after_cost_plus_slip_{format_slip(slip)}bps"] = None
        return out

    out[p + "mean_final_bps"] = safe_mean(df["final_bps"])
    out[p + "median_final_bps"] = safe_median(df["final_bps"])
    out[p + "cost_mean_bps"] = safe_mean(df["cost_stressed_final_bps"])
    out[p + "hit_rate_pct"] = hit_rate_pct(df["cost_stressed_final_bps"])
    if "mae_bps" in df.columns:
        out[p + "median_mae_bps"] = safe_median(df["mae_bps"])
        out[p + "mean_mae_bps"] = safe_mean(df["mae_bps"])
    else:
        out[p + "median_mae_bps"] = None
        out[p + "mean_mae_bps"] = None
    if "mfe_bps" in df.columns:
        out[p + "median_mfe_bps"] = safe_median(df["mfe_bps"])
        out[p + "mean_mfe_bps"] = safe_mean(df["mfe_bps"])
    else:
        out[p + "median_mfe_bps"] = None
        out[p + "mean_mfe_bps"] = None
    for c in ["touch_stop_50bps", "touch_stop_100bps", "touch_stop_150bps", "touch_target_50bps", "touch_target_100bps", "touch_target_150bps"]:
        if c in df.columns:
            out[p + f"{c}_pct"] = pct_true(df[c])
    for slip in extra_slippage_bps:
        key = p + f"mean_after_cost_plus_slip_{format_slip(slip)}bps"
        cm = out[p + "cost_mean_bps"]
        out[key] = None if cm is None else float(cm - slip)
    return out


def format_slip(x: float) -> str:
    if float(x).is_integer():
        return str(int(x))
    return str(x).replace(".", "p")


def classify_oos(row: Dict[str, Any], args: argparse.Namespace) -> str:
    full_n = row.get("full_n") or 0
    oos_n = row.get("oos_n") or 0
    oos_cost = row.get("oos_cost_mean_bps")
    oos_hit = row.get("oos_hit_rate_pct")
    train_cost = row.get("train_cost_mean_bps")
    ex2025 = row.get("ex2025_cost_mean_bps")
    loyo_min = row.get("leave_one_year_out_min_cost_mean_bps")
    slip16 = row.get("full_mean_after_cost_plus_slip_16bps")
    median_mae = row.get("full_median_mae_bps")
    stop100 = row.get("full_touch_stop_100bps_pct")
    q4 = row.get("q4_cost_mean_bps")
    recent = row.get("recent_third_cost_mean_bps")

    if full_n < args.min_events:
        return "INSUFFICIENT_EVENTS_NO_PROMOTION"
    if oos_n < args.min_oos_events:
        return "INSUFFICIENT_OOS_EVENTS_NO_PROMOTION"
    checks = {
        "oos_cost": oos_cost is not None and oos_cost >= args.min_oos_cost_mean_bps,
        "oos_hit": oos_hit is not None and oos_hit >= args.min_oos_hit_rate_pct,
        "train_cost": train_cost is not None and train_cost >= args.min_train_cost_mean_bps,
        "ex2025": ex2025 is not None and ex2025 >= args.min_ex2025_cost_mean_bps,
        "loyo": loyo_min is not None and loyo_min >= args.min_loyo_cost_mean_bps,
        "slip16": slip16 is not None and slip16 >= args.min_slip16_cost_mean_bps,
        "mae": median_mae is not None and abs(median_mae) <= args.max_median_mae_abs_bps,
        "stop100": stop100 is not None and stop100 <= args.max_touch_stop_100_pct,
        "q4": q4 is not None and q4 >= args.min_q4_cost_mean_bps,
        "recent": recent is not None and recent >= args.min_recent_cost_mean_bps,
    }

    strict_keys = ["oos_cost", "oos_hit", "train_cost", "ex2025", "loyo", "slip16", "mae", "stop100", "q4", "recent"]
    core_keys = ["oos_cost", "oos_hit", "ex2025", "loyo", "q4", "recent"]
    if all(checks[k] for k in strict_keys):
        return "STRICT_FROZEN_OOS_WATCH_ONLY_NO_PROMOTION"
    if all(checks[k] for k in core_keys):
        return "FROZEN_OOS_WATCH_ONLY_NO_PROMOTION"
    return "FAIL_FROZEN_OOS_NO_PROMOTION"


def make_summary_row(
    spec_row: pd.Series,
    spec_id: int,
    ev: pd.DataFrame,
    args: argparse.Namespace,
    extra_slippage_bps: Sequence[float],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    row: Dict[str, Any] = {
        "stage": STAGE,
        "decision_scope": DECISION_SCOPE,
        "promotion": PROMOTION,
        "ea": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "spec_id": int(spec_id),
        "spec_label": row_spec_label(spec_row),
        "source_stage39d_classification": as_str_clean(spec_row.get("classification")),
        "spec_type": as_str_clean(spec_row.get("spec_type")),
        "candidate": as_str_clean(spec_row.get("candidate")),
        "dimension": as_str_clean(spec_row.get("dimension")),
        "bucket": norm_bucket(spec_row.get("bucket")),
        "dimension_a": as_str_clean(spec_row.get("dimension_a")),
        "bucket_a": norm_bucket(spec_row.get("bucket_a")),
        "dimension_b": as_str_clean(spec_row.get("dimension_b")),
        "bucket_b": norm_bucket(spec_row.get("bucket_b")),
        "source_stage39d_n": _safe_int(spec_row.get("n")),
        "source_stage39d_cost_stressed_mean_bps": _safe_float(spec_row.get("cost_stressed_mean_bps")),
        "source_stage39d_recent_third_cost_mean_bps": _safe_float(spec_row.get("recent_third_cost_mean_bps")),
        "source_stage39d_q4_cost_mean_bps": _safe_float(spec_row.get("q4_cost_mean_bps")),
    }

    full_stats = calc_stats(ev, prefix="full", extra_slippage_bps=extra_slippage_bps, cost_bps=args.cost_bps)
    row.update(full_stats)

    ex2025 = ev[ev["year"] != 2025].copy() if len(ev) else ev.copy()
    y2025 = ev[ev["year"] == 2025].copy() if len(ev) else ev.copy()
    row["ex2025_n"] = int(len(ex2025))
    row["ex2025_cost_mean_bps"] = safe_mean(ex2025["cost_stressed_final_bps"]) if len(ex2025) else None
    row["y2025_n"] = int(len(y2025))
    row["y2025_cost_mean_bps"] = safe_mean(y2025["cost_stressed_final_bps"]) if len(y2025) else None
    loyo_min, loyo_json = leave_one_year_out_min_cost_mean(ev)
    row["leave_one_year_out_min_cost_mean_bps"] = loyo_min
    row["leave_one_year_out_json"] = json.dumps(loyo_json, ensure_ascii=False)
    row["year_cost_mean_json"] = json.dumps(year_cost_mean_json(ev), ensure_ascii=False)

    split_rows: List[Dict[str, Any]] = []
    for segment in ["train", "oos", "first_half", "second_half", "q1", "q2", "q3", "q4", "recent_third"]:
        seg_df = slice_chrono(ev, segment, oos_fraction=args.oos_fraction)
        seg_stats = calc_stats(seg_df, prefix=segment, extra_slippage_bps=extra_slippage_bps, cost_bps=args.cost_bps)
        for k, v in seg_stats.items():
            row[k] = v
        split_rows.append({
            "stage": STAGE,
            "decision_scope": DECISION_SCOPE,
            "promotion": PROMOTION,
            "spec_id": int(spec_id),
            "spec_label": row["spec_label"],
            "source_stage39d_classification": row["source_stage39d_classification"],
            "candidate": row["candidate"],
            "spec_type": row["spec_type"],
            "dimension": row["dimension"],
            "bucket": row["bucket"],
            "dimension_a": row["dimension_a"],
            "bucket_a": row["bucket_a"],
            "dimension_b": row["dimension_b"],
            "bucket_b": row["bucket_b"],
            "segment": segment,
            **{k.replace(segment + "_", ""): v for k, v in seg_stats.items()},
        })

    row["classification"] = classify_oos(row, args)
    return row, split_rows


def _safe_float(x: Any) -> Optional[float]:
    try:
        if pd.isna(x):
            return None
        return float(x)
    except Exception:
        return None


def _safe_int(x: Any) -> Optional[int]:
    try:
        if pd.isna(x):
            return None
        return int(float(x))
    except Exception:
        return None


def write_markdown(
    out_path: Path,
    summary_df: pd.DataFrame,
    split_df: pd.DataFrame,
    summary_json: Dict[str, Any],
) -> None:
    lines: List[str] = []
    lines.append(f"# {STAGE}")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append("```text")
    lines.append(f"scope = {DECISION_SCOPE}")
    lines.append("promotion = NO_GO")
    lines.append("EA = NO_GO")
    lines.append("paper_live = NO_GO")
    lines.append("live = NO_GO")
    lines.append("```")
    lines.append("")
    lines.append("Stage39E freezes the surviving Stage39D condition rows and audits chronological held-out behavior. It is not a promotion gate.")
    lines.append("")
    lines.append("## Input audit")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(summary_json["input_audit"], indent=2, ensure_ascii=False, default=_json_default))
    lines.append("```")
    lines.append("")
    lines.append("## Classification counts")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(summary_json["classification_counts"], indent=2, ensure_ascii=False, default=_json_default))
    lines.append("```")
    lines.append("")
    lines.append("## Frozen-rule OOS summary")
    lines.append("")
    show_cols = [
        "classification", "spec_type", "candidate", "dimension", "bucket",
        "dimension_a", "bucket_a", "dimension_b", "bucket_b",
        "full_n", "full_cost_mean_bps", "oos_n", "oos_cost_mean_bps",
        "oos_hit_rate_pct", "ex2025_cost_mean_bps",
        "leave_one_year_out_min_cost_mean_bps",
        "q4_cost_mean_bps", "recent_third_cost_mean_bps",
        "full_median_mae_bps", "full_touch_stop_100bps_pct",
        "full_mean_after_cost_plus_slip_16bps",
    ]
    existing = [c for c in show_cols if c in summary_df.columns]
    if len(summary_df):
        lines.append(summary_df[existing].to_markdown(index=False))
    else:
        lines.append("_No Stage39D survivor rows were available for Stage39E._")
    lines.append("")
    lines.append("## Split audit rows")
    lines.append("")
    split_cols = [
        "spec_id", "spec_label", "segment", "n", "cost_mean_bps",
        "hit_rate_pct", "median_mae_bps", "touch_stop_100bps_pct",
        "mean_after_cost_plus_slip_16bps",
    ]
    existing_split = [c for c in split_cols if c in split_df.columns]
    if len(split_df):
        lines.append(split_df[existing_split].to_markdown(index=False))
    else:
        lines.append("_No split rows._")
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("- `STRICT_FROZEN_OOS_WATCH_ONLY_NO_PROMOTION` means the frozen row survived this research-only OOS audit, but it is still not tradable.")
    lines.append("- `FROZEN_OOS_WATCH_ONLY_NO_PROMOTION` means it has partial held-out robustness but does not satisfy all strict risk and stress checks.")
    lines.append("- `FAIL_FROZEN_OOS_NO_PROMOTION`, `INSUFFICIENT_EVENTS_NO_PROMOTION`, and `INSUFFICIENT_OOS_EVENTS_NO_PROMOTION` should not be extended with more filters.")
    lines.append("- All rows remain `NO_GO` for EA, paper-live, and live.")
    lines.append("")
    lines.append("## Next allowed step")
    lines.append("")
    lines.append("Only if one or more rows are `STRICT_FROZEN_OOS_WATCH_ONLY_NO_PROMOTION`, the next step is a separate Stage39F rule-freeze package plus new-data observation protocol. That is still research-only and must not create trading alerts.")
    lines.append("")
    lines.append("If no row is strict, archive Stage39A-E and do not continue filtering.")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def run(args: argparse.Namespace) -> None:
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    extra_slippage_bps = parse_float_list(args.extra_slippage_bps)

    survivors, d_meta = load_stage39d_survivors(args.stage39d_summary_csv)
    events, e_meta = load_events(args.stage39c_events, cost_bps=args.cost_bps)

    summary_rows: List[Dict[str, Any]] = []
    split_rows: List[Dict[str, Any]] = []
    audited_events: List[pd.DataFrame] = []

    for i, spec in survivors.iterrows():
        ev = filter_events_for_spec(events, spec)
        spec_id = int(i + 1)
        row, splits = make_summary_row(spec, spec_id, ev, args, extra_slippage_bps)
        summary_rows.append(row)
        split_rows.extend(splits)
        if len(ev):
            ev2 = ev.copy()
            ev2.insert(0, "spec_id", spec_id)
            ev2.insert(1, "spec_label", row["spec_label"])
            ev2.insert(2, "stage39e_classification", row["classification"])
            audited_events.append(ev2)

    summary_df = pd.DataFrame(summary_rows)
    if len(summary_df):
        priority = {
            "STRICT_FROZEN_OOS_WATCH_ONLY_NO_PROMOTION": 0,
            "FROZEN_OOS_WATCH_ONLY_NO_PROMOTION": 1,
            "FAIL_FROZEN_OOS_NO_PROMOTION": 2,
            "INSUFFICIENT_OOS_EVENTS_NO_PROMOTION": 3,
            "INSUFFICIENT_EVENTS_NO_PROMOTION": 4,
        }
        summary_df["_sort_priority"] = summary_df["classification"].map(priority).fillna(9)
        sort_cols = ["_sort_priority", "oos_cost_mean_bps", "full_cost_mean_bps"]
        summary_df = summary_df.sort_values(sort_cols, ascending=[True, False, False]).drop(columns=["_sort_priority"])

    split_df = pd.DataFrame(split_rows)
    audited_events_df = pd.concat(audited_events, ignore_index=True) if audited_events else pd.DataFrame()

    classification_counts = summary_df["classification"].value_counts(dropna=False).to_dict() if len(summary_df) else {}
    strict_count = int((summary_df["classification"] == "STRICT_FROZEN_OOS_WATCH_ONLY_NO_PROMOTION").sum()) if len(summary_df) else 0
    frozen_watch_count = int(summary_df["classification"].astype(str).str.contains("FROZEN_OOS_WATCH", regex=False).sum()) if len(summary_df) else 0

    outputs = {
        "summary_csv": str(out_dir / "stage39e_frozen_rule_oos_summary.csv"),
        "split_csv": str(out_dir / "stage39e_frozen_rule_oos_split_audit.csv"),
        "audited_events_csv": str(out_dir / "stage39e_frozen_rule_oos_audited_events.csv"),
        "summary_json": str(out_dir / "stage39e_frozen_rule_oos_summary.json"),
        "markdown": str(out_dir / "stage39e_frozen_rule_oos_audit.md"),
    }

    summary_df.to_csv(outputs["summary_csv"], index=False)
    split_df.to_csv(outputs["split_csv"], index=False)
    audited_events_df.to_csv(outputs["audited_events_csv"], index=False)

    summary_json = {
        "stage": STAGE,
        "decision_scope": DECISION_SCOPE,
        "promotion": "NO_GO",
        "ea": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "parameters": {
            "cost_bps": float(args.cost_bps),
            "extra_slippage_bps": extra_slippage_bps,
            "oos_fraction": float(args.oos_fraction),
            "min_events": int(args.min_events),
            "min_oos_events": int(args.min_oos_events),
            "min_oos_cost_mean_bps": float(args.min_oos_cost_mean_bps),
            "min_oos_hit_rate_pct": float(args.min_oos_hit_rate_pct),
            "min_ex2025_cost_mean_bps": float(args.min_ex2025_cost_mean_bps),
            "min_loyo_cost_mean_bps": float(args.min_loyo_cost_mean_bps),
            "max_median_mae_abs_bps": float(args.max_median_mae_abs_bps),
            "max_touch_stop_100_pct": float(args.max_touch_stop_100_pct),
        },
        "input_audit": {
            "stage39d_summary": d_meta,
            "stage39c_events": {k: v for k, v in e_meta.items() if k != "columns"},
            "stage39c_event_columns": e_meta.get("columns", []),
        },
        "classification_counts": classification_counts,
        "strict_frozen_oos_watch_count": strict_count,
        "frozen_oos_watch_count": frozen_watch_count,
        "outputs": outputs,
        "top_rows": summary_df.head(20).replace({np.nan: None}).to_dict(orient="records") if len(summary_df) else [],
    }

    Path(outputs["summary_json"]).write_text(json.dumps(summary_json, indent=2, ensure_ascii=False, default=_json_default), encoding="utf-8")
    write_markdown(Path(outputs["markdown"]), summary_df, split_df, summary_json)

    print(json.dumps({
        "stage": STAGE,
        "promotion": "NO_GO",
        "strict_frozen_oos_watch_count": strict_count,
        "frozen_oos_watch_count": frozen_watch_count,
        "classification_counts": classification_counts,
        "outputs": outputs,
    }, indent=2, ensure_ascii=False, default=_json_default))


def parse_float_list(s: str) -> List[float]:
    vals: List[float] = []
    for part in str(s).split(","):
        part = part.strip()
        if not part:
            continue
        vals.append(float(part))
    return vals


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=STAGE)
    p.add_argument("--stage39d-summary-csv", default="reports/stage39d/stage39d_condition_robustness_summary.csv")
    p.add_argument("--stage39c-events", default="reports/stage39c/stage39c_condition_event_rows.csv")
    p.add_argument("--cost-bps", type=float, default=8.0)
    p.add_argument("--extra-slippage-bps", default="0,4,8,12,16")
    p.add_argument("--oos-fraction", type=float, default=0.33)
    p.add_argument("--min-events", type=int, default=30)
    p.add_argument("--min-oos-events", type=int, default=10)
    p.add_argument("--min-train-cost-mean-bps", type=float, default=10.0)
    p.add_argument("--min-oos-cost-mean-bps", type=float, default=15.0)
    p.add_argument("--min-oos-hit-rate-pct", type=float, default=55.0)
    p.add_argument("--min-ex2025-cost-mean-bps", type=float, default=10.0)
    p.add_argument("--min-loyo-cost-mean-bps", type=float, default=10.0)
    p.add_argument("--min-slip16-cost-mean-bps", type=float, default=10.0)
    p.add_argument("--min-q4-cost-mean-bps", type=float, default=10.0)
    p.add_argument("--min-recent-cost-mean-bps", type=float, default=10.0)
    p.add_argument("--max-median-mae-abs-bps", type=float, default=100.0)
    p.add_argument("--max-touch-stop-100-pct", type=float, default=45.0)
    p.add_argument("--output-dir", default="reports/stage39e")
    return p.parse_args(argv)


def main() -> None:
    run(parse_args())


if __name__ == "__main__":
    main()
