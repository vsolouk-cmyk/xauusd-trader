#!/usr/bin/env python3
"""
Stage39F_RECENCY_BIAS_AND_RULE_STABILITY_AUDIT

Research-stage only. No promotion, no EA, no paper-live, no live.

This script audits Stage39E frozen-rule OOS survivors for:
- train vs OOS asymmetry,
- q1/q2/q3/q4 stability,
- recency dominance,
- ex-2025 and leave-one-year-out sanity,
- slippage-16 survival,
- adverse path risk,
- optional event-row reconstruction from Stage39C events.

It intentionally remains a diagnostic gate. It does not output trade alerts.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd


STAGE = "Stage39F_RECENCY_BIAS_AND_RULE_STABILITY_AUDIT"
DECISION_SCOPE = "RESEARCH_STAGE_ONLY_NO_PROMOTION"
NO_GO = "NO_GO"

SURVIVOR_CLASSES = {
    "STRICT_FROZEN_OOS_WATCH_ONLY_NO_PROMOTION",
    "FROZEN_OOS_WATCH_ONLY_NO_PROMOTION",
}

TIME_COL_CANDIDATES = [
    "entry_ts", "entry_utc", "entry_time", "_event_time",
    "timestamp", "utc_time", "ts_utc", "time", "datetime", "date",
]


def finite_float(v: Any, default: float = float("nan")) -> float:
    try:
        if v is None:
            return default
        if isinstance(v, str) and not v.strip():
            return default
        x = float(v)
        if math.isfinite(x):
            return x
        return default
    except Exception:
        return default


def finite_int(v: Any, default: int = 0) -> int:
    try:
        if v is None:
            return default
        if isinstance(v, str) and not v.strip():
            return default
        x = int(float(v))
        return x
    except Exception:
        return default


def value_eq(a: Any, b: Any) -> bool:
    """Tolerant comparison for CSV bucket values."""
    if pd.isna(a):
        a_s = "NA"
    else:
        a_s = str(a).strip()
    if pd.isna(b):
        b_s = "NA"
    else:
        b_s = str(b).strip()
    if a_s == "":
        a_s = "NA"
    if b_s == "":
        b_s = "NA"
    return a_s.upper() == b_s.upper()


def first_existing_col(columns: Iterable[str], candidates: Iterable[str]) -> Optional[str]:
    cols = list(columns)
    lower_map = {str(c).lower(): c for c in cols}
    for cand in candidates:
        if cand in cols:
            return cand
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    return None


def load_stage39e_summary(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if data.get("stage") != "Stage39E_FROZEN_RULE_OUT_OF_SAMPLE_AUDIT":
        raise ValueError(f"Unexpected stage in {path}: {data.get('stage')}")
    rows = data.get("top_rows", [])
    if not isinstance(rows, list):
        raise ValueError("stage39e summary JSON does not contain a list top_rows")
    return data


def load_events(path: Optional[Path]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    if path is None or not path.exists():
        return pd.DataFrame(), {"loaded": False, "reason": "missing_or_not_provided"}
    df = pd.read_csv(path)
    audit: Dict[str, Any] = {
        "path": str(path),
        "loaded": True,
        "rows_before_time_drop": int(len(df)),
        "columns": list(df.columns),
    }
    time_col = first_existing_col(df.columns, TIME_COL_CANDIDATES)
    audit["time_column"] = time_col
    if time_col is not None:
        df["_event_time"] = pd.to_datetime(df[time_col], utc=True, errors="coerce")
        bad = int(df["_event_time"].isna().sum())
        df = df.loc[df["_event_time"].notna()].copy()
        df = df.sort_values("_event_time").reset_index(drop=True)
        audit["bad_time_rows_dropped"] = bad
        audit["rows_after_time_drop"] = int(len(df))
        if len(df):
            audit["date_min"] = df["_event_time"].min().isoformat()
            audit["date_max"] = df["_event_time"].max().isoformat()
    return df, audit


def row_spec_label(row: Dict[str, Any]) -> str:
    return str(row.get("spec_label") or "")


def matches_spec(ev: pd.DataFrame, row: Dict[str, Any]) -> pd.Series:
    if ev.empty:
        return pd.Series([], dtype=bool)

    mask = pd.Series([True] * len(ev), index=ev.index)

    cand = str(row.get("candidate", "")).strip()
    if cand and "candidate" in ev.columns:
        mask &= ev["candidate"].astype(str).str.strip().eq(cand)

    spec_type = str(row.get("spec_type", "single_condition")).strip()
    if spec_type == "cross_condition":
        da, ba = str(row.get("dimension_a", "")).strip(), row.get("bucket_a", "NA")
        db, bb = str(row.get("dimension_b", "")).strip(), row.get("bucket_b", "NA")
        if da and da in ev.columns:
            mask &= ev[da].apply(lambda x: value_eq(x, ba))
        if db and db in ev.columns:
            mask &= ev[db].apply(lambda x: value_eq(x, bb))
    else:
        dim, bucket = str(row.get("dimension", "")).strip(), row.get("bucket", "NA")
        if dim and dim in ev.columns:
            mask &= ev[dim].apply(lambda x: value_eq(x, bucket))
    return mask


def metrics_from_series(x: pd.Series) -> Dict[str, float]:
    s = pd.to_numeric(x, errors="coerce").dropna()
    if len(s) == 0:
        return {"n": 0, "mean": float("nan"), "median": float("nan")}
    return {"n": int(len(s)), "mean": float(s.mean()), "median": float(s.median())}


def compute_basic_event_recheck(ev_sub: pd.DataFrame, cost_bps: float, slip16: float = 16.0) -> Dict[str, Any]:
    if ev_sub.empty:
        return {
            "event_recheck_n": 0,
            "event_recheck_cost_mean_bps": float("nan"),
            "event_recheck_median_mae_bps": float("nan"),
            "event_recheck_touch_stop_100bps_pct": float("nan"),
        }

    # Prefer already-cost-stressed final bps if present; otherwise subtract configured cost.
    if "cost_stressed_final_bps" in ev_sub.columns:
        cost_final = pd.to_numeric(ev_sub["cost_stressed_final_bps"], errors="coerce")
    else:
        cost_final = pd.to_numeric(ev_sub.get("final_bps", pd.Series(dtype=float)), errors="coerce") - cost_bps

    out: Dict[str, Any] = {
        "event_recheck_n": int(cost_final.notna().sum()),
        "event_recheck_cost_mean_bps": float(cost_final.mean()) if cost_final.notna().any() else float("nan"),
        "event_recheck_cost_median_bps": float(cost_final.median()) if cost_final.notna().any() else float("nan"),
        "event_recheck_after_slip16_mean_bps": float((cost_final - slip16).mean()) if cost_final.notna().any() else float("nan"),
    }
    if "mae_bps" in ev_sub.columns:
        mae = pd.to_numeric(ev_sub["mae_bps"], errors="coerce")
        out["event_recheck_median_mae_bps"] = float(mae.median()) if mae.notna().any() else float("nan")
    if "touch_stop_100bps" in ev_sub.columns:
        st = ev_sub["touch_stop_100bps"]
        if st.dtype == object:
            st = st.astype(str).str.lower().isin(["1", "true", "yes", "y"])
        out["event_recheck_touch_stop_100bps_pct"] = float(pd.to_numeric(st, errors="coerce").mean() * 100.0)
    return out


def audit_row(row: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    # Core metrics from Stage39E.
    fields = {
        "full_n": finite_int(row.get("full_n")),
        "train_n": finite_int(row.get("train_n")),
        "oos_n": finite_int(row.get("oos_n")),
        "full_cost_mean_bps": finite_float(row.get("full_cost_mean_bps")),
        "train_cost_mean_bps": finite_float(row.get("train_cost_mean_bps")),
        "oos_cost_mean_bps": finite_float(row.get("oos_cost_mean_bps")),
        "full_mean_after_cost_plus_slip_16bps": finite_float(row.get("full_mean_after_cost_plus_slip_16bps")),
        "train_mean_after_cost_plus_slip_16bps": finite_float(row.get("train_mean_after_cost_plus_slip_16bps")),
        "oos_mean_after_cost_plus_slip_16bps": finite_float(row.get("oos_mean_after_cost_plus_slip_16bps")),
        "ex2025_cost_mean_bps": finite_float(row.get("ex2025_cost_mean_bps")),
        "leave_one_year_out_min_cost_mean_bps": finite_float(row.get("leave_one_year_out_min_cost_mean_bps")),
        "full_median_mae_bps": finite_float(row.get("full_median_mae_bps")),
        "oos_median_mae_bps": finite_float(row.get("oos_median_mae_bps")),
        "full_touch_stop_100bps_pct": finite_float(row.get("full_touch_stop_100bps_pct")),
        "oos_touch_stop_100bps_pct": finite_float(row.get("oos_touch_stop_100bps_pct")),
        "full_hit_rate_pct": finite_float(row.get("full_hit_rate_pct")),
        "oos_hit_rate_pct": finite_float(row.get("oos_hit_rate_pct")),
    }

    quarter_costs = [
        finite_float(row.get("q1_cost_mean_bps")),
        finite_float(row.get("q2_cost_mean_bps")),
        finite_float(row.get("q3_cost_mean_bps")),
        finite_float(row.get("q4_cost_mean_bps")),
    ]
    quarter_slip16 = [
        finite_float(row.get("q1_mean_after_cost_plus_slip_16bps")),
        finite_float(row.get("q2_mean_after_cost_plus_slip_16bps")),
        finite_float(row.get("q3_mean_after_cost_plus_slip_16bps")),
        finite_float(row.get("q4_mean_after_cost_plus_slip_16bps")),
    ]
    quarter_ns = [
        finite_int(row.get("q1_n")),
        finite_int(row.get("q2_n")),
        finite_int(row.get("q3_n")),
        finite_int(row.get("q4_n")),
    ]

    finite_quarter_costs = [x for x in quarter_costs if math.isfinite(x)]
    finite_quarter_slip16 = [x for x in quarter_slip16 if math.isfinite(x)]
    worst_quarter_cost = min(finite_quarter_costs) if finite_quarter_costs else float("nan")
    worst_quarter_slip16 = min(finite_quarter_slip16) if finite_quarter_slip16 else float("nan")

    train_cost = fields["train_cost_mean_bps"]
    oos_cost = fields["oos_cost_mean_bps"]
    full_cost = fields["full_cost_mean_bps"]
    oos_train_gap = oos_cost - train_cost if math.isfinite(oos_cost) and math.isfinite(train_cost) else float("nan")
    # Ratio is not used alone for pass/fail because low train mean can explode ratios.
    oos_train_ratio = (
        oos_cost / max(abs(train_cost), args.ratio_floor_bps)
        if math.isfinite(oos_cost) and math.isfinite(train_cost)
        else float("nan")
    )
    q4_to_full_ratio = (
        finite_float(row.get("q4_cost_mean_bps")) / max(abs(full_cost), args.ratio_floor_bps)
        if math.isfinite(full_cost)
        else float("nan")
    )

    hard_checks = {
        "min_full_events": fields["full_n"] >= args.min_events,
        "min_train_events": fields["train_n"] >= args.min_train_events,
        "min_oos_events": fields["oos_n"] >= args.min_oos_events,
        "full_cost_floor": fields["full_cost_mean_bps"] >= args.min_full_cost_mean_bps,
        "train_cost_floor": fields["train_cost_mean_bps"] >= args.min_train_cost_mean_bps,
        "oos_cost_floor": fields["oos_cost_mean_bps"] >= args.min_oos_cost_mean_bps,
        "full_slip16_floor": fields["full_mean_after_cost_plus_slip_16bps"] >= args.min_full_slip16_mean_bps,
        "train_slip16_floor": fields["train_mean_after_cost_plus_slip_16bps"] >= args.min_train_slip16_mean_bps,
        "oos_slip16_floor": fields["oos_mean_after_cost_plus_slip_16bps"] >= args.min_oos_slip16_mean_bps,
        "ex2025_floor": fields["ex2025_cost_mean_bps"] >= args.min_ex2025_cost_mean_bps,
        "loyo_floor": fields["leave_one_year_out_min_cost_mean_bps"] >= args.min_loyo_cost_mean_bps,
        "worst_quarter_cost_floor": worst_quarter_cost >= args.min_worst_quarter_cost_bps,
        "worst_quarter_slip16_floor": worst_quarter_slip16 >= args.min_worst_quarter_slip16_bps,
        "full_median_mae_cap": abs(fields["full_median_mae_bps"]) <= args.max_full_median_mae_abs_bps,
        "oos_median_mae_cap": abs(fields["oos_median_mae_bps"]) <= args.max_oos_median_mae_abs_bps,
        "full_stop100_cap": fields["full_touch_stop_100bps_pct"] <= args.max_full_touch_stop_100_pct,
        "oos_stop100_cap": fields["oos_touch_stop_100bps_pct"] <= args.max_oos_touch_stop_100_pct,
    }

    recency_flags = {
        "oos_train_gap_high": math.isfinite(oos_train_gap) and oos_train_gap > args.max_oos_train_gap_bps,
        "oos_train_ratio_high": math.isfinite(oos_train_ratio) and oos_train_ratio > args.max_oos_train_ratio,
        "q4_to_full_ratio_high": math.isfinite(q4_to_full_ratio) and q4_to_full_ratio > args.max_q4_full_ratio,
        "early_quarter_negative": any(math.isfinite(x) and x < 0 for x in quarter_costs[:2]),
        "early_quarter_slip16_negative": any(math.isfinite(x) and x < 0 for x in quarter_slip16[:2]),
    }

    strict_pass = all(hard_checks.values()) and not any(recency_flags.values())
    partial_watch = (
        hard_checks["min_full_events"]
        and hard_checks["min_oos_events"]
        and hard_checks["full_cost_floor"]
        and hard_checks["oos_cost_floor"]
        and hard_checks["ex2025_floor"]
        and hard_checks["loyo_floor"]
    )

    if strict_pass:
        classification = "STRICT_STABLE_FROZEN_RULE_WATCH_ONLY_NO_PROMOTION"
    elif partial_watch:
        classification = "RECENCY_BIASED_FROZEN_RULE_WATCH_ONLY_NO_PROMOTION"
    else:
        classification = "FAIL_RECENCY_STABILITY_NO_PROMOTION"

    failed_checks = [k for k, ok in hard_checks.items() if not ok]
    active_recency_flags = [k for k, ok in recency_flags.items() if ok]

    out = {
        "stage": STAGE,
        "decision_scope": DECISION_SCOPE,
        "promotion": NO_GO,
        "ea": NO_GO,
        "paper_live": NO_GO,
        "live": NO_GO,
        "source_stage39e_classification": row.get("classification"),
        "spec_id": row.get("spec_id"),
        "spec_label": row_spec_label(row),
        "spec_type": row.get("spec_type"),
        "candidate": row.get("candidate"),
        "dimension": row.get("dimension", ""),
        "bucket": row.get("bucket", ""),
        "dimension_a": row.get("dimension_a", ""),
        "bucket_a": row.get("bucket_a", ""),
        "dimension_b": row.get("dimension_b", ""),
        "bucket_b": row.get("bucket_b", ""),
        **fields,
        "q1_cost_mean_bps": quarter_costs[0],
        "q2_cost_mean_bps": quarter_costs[1],
        "q3_cost_mean_bps": quarter_costs[2],
        "q4_cost_mean_bps": quarter_costs[3],
        "q1_mean_after_cost_plus_slip_16bps": quarter_slip16[0],
        "q2_mean_after_cost_plus_slip_16bps": quarter_slip16[1],
        "q3_mean_after_cost_plus_slip_16bps": quarter_slip16[2],
        "q4_mean_after_cost_plus_slip_16bps": quarter_slip16[3],
        "q1_n": quarter_ns[0],
        "q2_n": quarter_ns[1],
        "q3_n": quarter_ns[2],
        "q4_n": quarter_ns[3],
        "worst_quarter_cost_mean_bps": worst_quarter_cost,
        "worst_quarter_slip16_mean_bps": worst_quarter_slip16,
        "oos_train_gap_bps": oos_train_gap,
        "oos_train_ratio": oos_train_ratio,
        "q4_to_full_cost_ratio": q4_to_full_ratio,
        "failed_hard_checks": ";".join(failed_checks),
        "recency_flags": ";".join(active_recency_flags),
        "classification": classification,
    }
    return out


def make_markdown(summary: Dict[str, Any], rows_df: pd.DataFrame, split_df: pd.DataFrame) -> str:
    counts = summary["classification_counts"]
    top_cols = [
        "classification", "spec_label", "full_n", "train_n", "oos_n",
        "full_cost_mean_bps", "train_cost_mean_bps", "oos_cost_mean_bps",
        "worst_quarter_cost_mean_bps", "worst_quarter_slip16_mean_bps",
        "ex2025_cost_mean_bps", "leave_one_year_out_min_cost_mean_bps",
        "full_median_mae_bps", "oos_median_mae_bps",
        "full_touch_stop_100bps_pct", "oos_touch_stop_100bps_pct",
        "recency_flags", "failed_hard_checks",
    ]
    present_top = [c for c in top_cols if c in rows_df.columns]
    table_md = rows_df[present_top].to_markdown(index=False) if len(rows_df) else "_No audited rows._"

    split_cols = ["spec_id", "spec_label", "segment", "n", "cost_mean_bps", "hit_rate_pct", "median_mae_bps", "touch_stop_100bps_pct", "mean_after_cost_plus_slip_16bps"]
    split_md = split_df[[c for c in split_cols if c in split_df.columns]].to_markdown(index=False) if len(split_df) else "_No split rows._"

    next_step = (
        "Only if one or more rows are `STRICT_STABLE_FROZEN_RULE_WATCH_ONLY_NO_PROMOTION`, "
        "the next allowed step is `Stage39G_FIXED_RULE_RISK_BOX_OFFLINE_REPLAY`. "
        "If only recency-biased rows remain, do not promote; either archive Stage39A-F or run a separate decay/2026-forward extension when more data exists."
    )
    if summary.get("strict_stable_frozen_watch_count", 0) == 0:
        next_step = (
            "No strict stable frozen rule survived this audit. The default decision is to archive Stage39A-F and not continue filter stacking. "
            "A future revisit is allowed only after materially more forward data exists."
        )

    return f"""# {STAGE}

## Decision

```text
scope = {DECISION_SCOPE}
promotion = {NO_GO}
EA = {NO_GO}
paper_live = {NO_GO}
live = {NO_GO}
```

Stage39F audits Stage39E frozen-rule survivors for recency bias, train/OOS asymmetry, quarter stability, slippage-16 survival, and adverse path risk. It is not a promotion gate.

## Input audit

```json
{json.dumps(summary["input_audit"], indent=2, ensure_ascii=False)}
```

## Classification counts

```json
{json.dumps(counts, indent=2, ensure_ascii=False)}
```

## Frozen rule recency/stability summary

{table_md}

## Split rows

{split_md}

## Interpretation

- `STRICT_STABLE_FROZEN_RULE_WATCH_ONLY_NO_PROMOTION` means the rule survived this stability audit, but it is still research-only.
- `RECENCY_BIASED_FROZEN_RULE_WATCH_ONLY_NO_PROMOTION` means the rule remains interesting but is dominated by recent/OOS behavior, weak early quarters, or weak train/slippage survival.
- `FAIL_RECENCY_STABILITY_NO_PROMOTION` means do not extend this row with more filters.
- All Stage39F rows remain `NO_GO` for EA, paper-live, and live.

## Next allowed step

{next_step}
"""


def build_split_rows(audited_rows: List[Dict[str, Any]]) -> pd.DataFrame:
    records: List[Dict[str, Any]] = []
    segments = ["train", "oos", "first_half", "second_half", "q1", "q2", "q3", "q4", "recent_third"]
    fields = [
        "n", "cost_mean_bps", "hit_rate_pct", "median_mae_bps",
        "touch_stop_100bps_pct", "mean_after_cost_plus_slip_16bps",
    ]
    for row in audited_rows:
        for seg in segments:
            rec = {
                "spec_id": row.get("spec_id"),
                "spec_label": row.get("spec_label"),
                "segment": seg,
            }
            any_present = False
            for field in fields:
                key = f"{seg}_{field}"
                # Only source JSON rows have these keys; preserve if we copied them.
                if key in row:
                    rec[field] = row.get(key)
                    any_present = True
            # Our compact audited rows do not carry all segment keys. Fill known ones.
            for field in fields:
                if field not in rec:
                    compact_key = f"{seg}_{field}"
                    if compact_key in row:
                        rec[field] = row.get(compact_key)
                        any_present = True
            if any_present:
                records.append(rec)
    return pd.DataFrame(records)


def run(args: argparse.Namespace) -> None:
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stage39e = load_stage39e_summary(Path(args.stage39e_summary_json))
    events, events_audit = load_events(Path(args.stage39c_events) if args.stage39c_events else None)

    source_rows = [
        r for r in stage39e.get("top_rows", [])
        if str(r.get("classification")) in SURVIVOR_CLASSES
    ]

    audited: List[Dict[str, Any]] = []
    audited_events_frames: List[pd.DataFrame] = []

    for r in source_rows:
        row = audit_row(r, args)

        # Preserve split metrics from Stage39E top_rows in the row and split CSV.
        for k, v in r.items():
            if any(k.startswith(prefix) for prefix in [
                "train_", "oos_", "first_half_", "second_half_", "q1_", "q2_", "q3_", "q4_", "recent_third_"
            ]):
                row.setdefault(k, v)

        if not events.empty:
            mask = matches_spec(events, r)
            ev_sub = events.loc[mask].copy()
            recheck = compute_basic_event_recheck(ev_sub, args.cost_bps)
            row.update(recheck)
            if not ev_sub.empty:
                ev_sub.insert(0, "stage39f_spec_id", row.get("spec_id"))
                ev_sub.insert(1, "stage39f_spec_label", row.get("spec_label"))
                ev_sub.insert(2, "stage39f_classification", row.get("classification"))
                audited_events_frames.append(ev_sub)

        audited.append(row)

    rows_df = pd.DataFrame(audited)
    if len(rows_df):
        sort_cols = [c for c in ["classification", "oos_cost_mean_bps", "full_cost_mean_bps"] if c in rows_df.columns]
        rows_df = rows_df.sort_values(sort_cols, ascending=[True, False, False][:len(sort_cols)]).reset_index(drop=True)

    split_records = []
    for r in source_rows:
        spec_id = r.get("spec_id")
        spec_label = row_spec_label(r)
        for seg in ["train", "oos", "first_half", "second_half", "q1", "q2", "q3", "q4", "recent_third"]:
            rec = {
                "spec_id": spec_id,
                "spec_label": spec_label,
                "segment": seg,
                "n": finite_int(r.get(f"{seg}_n")),
                "cost_mean_bps": finite_float(r.get(f"{seg}_cost_mean_bps")),
                "hit_rate_pct": finite_float(r.get(f"{seg}_hit_rate_pct")),
                "median_mae_bps": finite_float(r.get(f"{seg}_median_mae_bps")),
                "touch_stop_100bps_pct": finite_float(r.get(f"{seg}_touch_stop_100bps_pct")),
                "mean_after_cost_plus_slip_16bps": finite_float(r.get(f"{seg}_mean_after_cost_plus_slip_16bps")),
            }
            if rec["n"] > 0:
                split_records.append(rec)
    split_df = pd.DataFrame(split_records)

    events_out = pd.concat(audited_events_frames, ignore_index=True) if audited_events_frames else pd.DataFrame()

    classification_counts = rows_df["classification"].value_counts(dropna=False).to_dict() if len(rows_df) else {}
    strict_count = int((rows_df.get("classification", pd.Series(dtype=str)) == "STRICT_STABLE_FROZEN_RULE_WATCH_ONLY_NO_PROMOTION").sum()) if len(rows_df) else 0
    recency_count = int((rows_df.get("classification", pd.Series(dtype=str)) == "RECENCY_BIASED_FROZEN_RULE_WATCH_ONLY_NO_PROMOTION").sum()) if len(rows_df) else 0

    summary = {
        "stage": STAGE,
        "decision_scope": DECISION_SCOPE,
        "promotion": NO_GO,
        "ea": NO_GO,
        "paper_live": NO_GO,
        "live": NO_GO,
        "parameters": vars(args),
        "input_audit": {
            "stage39e_summary_json": {
                "path": args.stage39e_summary_json,
                "loaded_rows": len(stage39e.get("top_rows", [])),
                "survivor_rows": len(source_rows),
                "source_classification_counts": stage39e.get("classification_counts", {}),
            },
            "stage39c_events": events_audit,
        },
        "classification_counts": classification_counts,
        "strict_stable_frozen_watch_count": strict_count,
        "recency_biased_watch_count": recency_count,
        "outputs": {
            "summary_csv": str(out_dir / "stage39f_frozen_rule_recency_bias_summary.csv"),
            "split_csv": str(out_dir / "stage39f_split_stability_audit.csv"),
            "audited_events_csv": str(out_dir / "stage39f_audited_events.csv"),
            "summary_json": str(out_dir / "stage39f_frozen_rule_recency_bias_summary.json"),
            "markdown": str(out_dir / "stage39f_frozen_rule_recency_bias_audit.md"),
        },
        "top_rows": rows_df.to_dict(orient="records") if len(rows_df) else [],
    }

    rows_df.to_csv(out_dir / "stage39f_frozen_rule_recency_bias_summary.csv", index=False)
    split_df.to_csv(out_dir / "stage39f_split_stability_audit.csv", index=False)
    events_out.to_csv(out_dir / "stage39f_audited_events.csv", index=False)
    with (out_dir / "stage39f_frozen_rule_recency_bias_summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    (out_dir / "stage39f_frozen_rule_recency_bias_audit.md").write_text(
        make_markdown(summary, rows_df, split_df),
        encoding="utf-8",
    )

    print(json.dumps({
        "stage": STAGE,
        "promotion": NO_GO,
        "rows": int(len(rows_df)),
        "classification_counts": classification_counts,
        "strict_stable_frozen_watch_count": strict_count,
        "recency_biased_watch_count": recency_count,
        "outputs": summary["outputs"],
    }, indent=2, ensure_ascii=False))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=STAGE)
    p.add_argument("--stage39e-summary-json", required=True)
    p.add_argument("--stage39c-events", default="")
    p.add_argument("--cost-bps", type=float, default=8.0)
    p.add_argument("--output-dir", default="reports/stage39f")

    p.add_argument("--min-events", type=int, default=30)
    p.add_argument("--min-train-events", type=int, default=20)
    p.add_argument("--min-oos-events", type=int, default=10)

    p.add_argument("--min-full-cost-mean-bps", type=float, default=15.0)
    p.add_argument("--min-train-cost-mean-bps", type=float, default=15.0)
    p.add_argument("--min-oos-cost-mean-bps", type=float, default=15.0)

    p.add_argument("--min-full-slip16-mean-bps", type=float, default=10.0)
    p.add_argument("--min-train-slip16-mean-bps", type=float, default=10.0)
    p.add_argument("--min-oos-slip16-mean-bps", type=float, default=10.0)

    p.add_argument("--min-ex2025-cost-mean-bps", type=float, default=10.0)
    p.add_argument("--min-loyo-cost-mean-bps", type=float, default=10.0)
    p.add_argument("--min-worst-quarter-cost-bps", type=float, default=0.0)
    p.add_argument("--min-worst-quarter-slip16-bps", type=float, default=0.0)

    p.add_argument("--max-full-median-mae-abs-bps", type=float, default=100.0)
    p.add_argument("--max-oos-median-mae-abs-bps", type=float, default=120.0)
    p.add_argument("--max-full-touch-stop-100-pct", type=float, default=45.0)
    p.add_argument("--max-oos-touch-stop-100-pct", type=float, default=55.0)

    p.add_argument("--max-oos-train-gap-bps", type=float, default=60.0)
    p.add_argument("--max-oos-train-ratio", type=float, default=3.0)
    p.add_argument("--max-q4-full-ratio", type=float, default=3.0)
    p.add_argument("--ratio-floor-bps", type=float, default=10.0)
    return p.parse_args()


def main() -> None:
    run(parse_args())


if __name__ == "__main__":
    main()
