#!/usr/bin/env python3
"""Stage96 COT positioning thesis discovery.

Research-only COT frontier discovery after the local unified observer portfolio is operational
and macro-only / intraday-session residual discovery did not produce new shortlist candidates.

No orders, no broker connection, no EA/MT5 change.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

STAGE = "Stage96_COT_POSITIONING_THESIS_DISCOVERY"
PATCH_VERSION = "STAGE96D_COT_RULE_WARMUP_ACCOUNTING_FIX"
HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE96",
    "NO_THRESHOLD_TUNING_FROM_STAGE96_DISCOVERY",
    "NO_DIRECT_MT5_OR_EA_CHANGE_FROM_STAGE96",
]

SPLITS = {
    "train": ("1900-01-01", "2014-12-31"),
    "validation": ("2015-01-01", "2018-12-31"),
    "locked_forward": ("2019-01-01", "2022-12-31"),
    "final_holdout": ("2023-01-01", "2999-12-31"),
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_path(root: Path, value: str) -> Path:
    p = Path(value).expanduser()
    if not p.is_absolute():
        p = root / p
    return p


def safe_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        if isinstance(x, str):
            x = x.replace(",", "").strip()
            if x == "" or x.lower() in {"nan", "none", "null"}:
                return None
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None


def lower_cols(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip().strip("<>").strip().lower().replace(" ", "_") for c in out.columns]
    return out


def read_csv_smart(path: Path) -> pd.DataFrame:
    last_err: Optional[Exception] = None
    for sep in [None, ",", "\t", ";", "|"]:
        try:
            if sep is None:
                df = pd.read_csv(path, engine="python")
            else:
                df = pd.read_csv(path, sep=sep, engine="python")
            if len(df.columns) >= 2:
                return lower_cols(df)
        except Exception as exc:
            last_err = exc
    raise RuntimeError(f"Could not read CSV {path}: {last_err}")


def parse_date_series(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, utc=True, errors="coerce").dt.normalize()


def first_existing(cols: Iterable[str], candidates: Iterable[str]) -> Optional[str]:
    cols_set = set(cols)
    for c in candidates:
        if c in cols_set:
            return c
    return None


def normalize_macro(df: pd.DataFrame, date_col: str, price_col: str) -> pd.DataFrame:
    df = lower_cols(df)
    date_col_norm = date_col.lower()
    price_col_norm = price_col.lower()
    if date_col_norm not in df.columns:
        date_col_norm = first_existing(df.columns, ["feature_date_utc", "date_utc", "datetime", "date", "time", "timestamp"]) or ""
    if not date_col_norm or date_col_norm not in df.columns:
        raise ValueError("Macro dataset has no usable date column")
    if price_col_norm not in df.columns:
        price_col_norm = first_existing(df.columns, ["gold_close", "close", "xauusd_close"]) or ""
    if not price_col_norm or price_col_norm not in df.columns:
        raise ValueError("Macro dataset has no usable gold price column")

    out = df.copy()
    out["feature_date_utc"] = parse_date_series(out[date_col_norm])
    out["gold_close"] = pd.to_numeric(out[price_col_norm], errors="coerce")
    out = out.dropna(subset=["feature_date_utc", "gold_close"]).sort_values("feature_date_utc").drop_duplicates("feature_date_utc")
    for c in out.columns:
        if c != "feature_date_utc" and c != date_col_norm:
            try:
                out[c] = pd.to_numeric(out[c], errors="raise")
            except Exception:
                pass

    out["gold_ret_20d"] = out["gold_close"].pct_change(20)
    out["gold_ret_60d"] = out["gold_close"].pct_change(60)
    if "gold_sma20_over_50" not in out.columns:
        out["gold_sma20_over_50"] = out["gold_close"].rolling(20).mean() / out["gold_close"].rolling(50).mean() - 1.0
    if "dxy_ret_20d" not in out.columns and "dxy" in out.columns:
        out["dxy_ret_20d"] = pd.to_numeric(out["dxy"], errors="coerce").pct_change(20)
    if "dxy_ret_120d" not in out.columns and "dxy" in out.columns:
        out["dxy_ret_120d"] = pd.to_numeric(out["dxy"], errors="coerce").pct_change(120)
    if "dxy_sma20_over_50" not in out.columns and "dxy" in out.columns:
        dxy = pd.to_numeric(out["dxy"], errors="coerce")
        out["dxy_sma20_over_50"] = dxy.rolling(20).mean() / dxy.rolling(50).mean() - 1.0
    if "real_yield_change_20d" not in out.columns and "real_yield" in out.columns:
        out["real_yield_change_20d"] = pd.to_numeric(out["real_yield"], errors="coerce").diff(20)
    if "real_yield_change_120d" not in out.columns and "real_yield" in out.columns:
        out["real_yield_change_120d"] = pd.to_numeric(out["real_yield"], errors="coerce").diff(120)
    if "vix_change_20d" not in out.columns and "vix" in out.columns:
        out["vix_change_20d"] = pd.to_numeric(out["vix"], errors="coerce").diff(20)
    return out


def normalize_cot(df: pd.DataFrame, lag_days: int, z_window: int, z_min: int) -> pd.DataFrame:
    df = lower_cols(df)
    date_col = first_existing(df.columns, [
        "report_date_utc", "report_date", "report_date_as_yyyy_mm_dd", "as_of_date_in_form_yyyy-mm-dd", "date", "date_utc"
    ])
    if not date_col:
        raise ValueError("COT dataset has no report date column")
    out = df.copy()
    out["report_date_utc"] = parse_date_series(out[date_col])
    available_col = first_existing(out.columns, ["available_after_utc", "sample_available_after_utc", "publication_date_utc"])
    if available_col:
        out["available_after_utc"] = parse_date_series(out[available_col])
    else:
        out["available_after_utc"] = out["report_date_utc"] + pd.to_timedelta(lag_days, unit="D")

    # Standardize numeric COT columns.
    col_map = {
        "managed_money_long": ["managed_money_long", "m_money_positions_long_all", "managed_money_positions_long_all", "m_money_long", "money_manager_long"],
        "managed_money_short": ["managed_money_short", "m_money_positions_short_all", "managed_money_positions_short_all", "m_money_short", "money_manager_short"],
        "managed_money_spread": ["managed_money_spread", "m_money_positions_spread_all", "managed_money_positions_spread_all"],
        "open_interest": ["open_interest", "open_interest_all", "open_interest_total", "open_interest_futures"],
        "managed_money_net": ["managed_money_net", "managed_money_net_all", "m_money_net", "mm_net"],
        "managed_money_net_pct_oi": ["managed_money_net_pct_oi", "mm_net_pct_oi", "cot_managed_money_net_pct_oi", "managed_money_net_pct_open_interest"],
        "cot_mm_net_z": ["cot_mm_net_z", "managed_money_net_z", "managed_money_net_pct_oi_z", "cot_managed_money_z", "mm_net_z", "zscore"],
    }
    for std, candidates in col_map.items():
        c = first_existing(out.columns, candidates)
        if c and c != std:
            out[std] = out[c]
    for c in ["managed_money_long", "managed_money_short", "managed_money_spread", "open_interest", "managed_money_net", "managed_money_net_pct_oi", "cot_mm_net_z"]:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")

    if "managed_money_net" not in out.columns or out["managed_money_net"].isna().all():
        if "managed_money_long" in out.columns and "managed_money_short" in out.columns:
            out["managed_money_net"] = out["managed_money_long"] - out["managed_money_short"]
    if "managed_money_net_pct_oi" not in out.columns or out["managed_money_net_pct_oi"].isna().all():
        if "managed_money_net" in out.columns and "open_interest" in out.columns:
            out["managed_money_net_pct_oi"] = out["managed_money_net"] / out["open_interest"].replace(0, pd.NA)
    if "managed_money_net_pct_oi" not in out.columns:
        raise ValueError("COT dataset lacks managed money net pct OI inputs")

    out = out.dropna(subset=["report_date_utc", "available_after_utc", "managed_money_net_pct_oi"]).sort_values("report_date_utc")
    out = out.drop_duplicates("report_date_utc", keep="last")

    if "cot_mm_net_z" not in out.columns or out["cot_mm_net_z"].isna().sum() > len(out) * 0.75:
        mean = out["managed_money_net_pct_oi"].rolling(z_window, min_periods=min(z_min, max(2, len(out)))).mean()
        std = out["managed_money_net_pct_oi"].rolling(z_window, min_periods=min(z_min, max(2, len(out)))).std(ddof=0)
        out["cot_mm_net_z"] = (out["managed_money_net_pct_oi"] - mean) / std.replace(0, pd.NA)
    out["cot_mm_net_z_change_4w"] = out["cot_mm_net_z"].diff(4)
    out["cot_mm_net_pct_oi_change_4w"] = out["managed_money_net_pct_oi"].diff(4)
    return out


def build_joined_dataset(macro: pd.DataFrame, cot: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
    """Lag-aware daily join of COT to macro rows.

    The macro dataset may already contain an ``available_after_utc`` column for its own
    source-availability metadata.  Earlier Stage96 used the same column name from the
    COT side as the merge key, which made pandas suffix/drop the expected COT
    availability field and caused ``KeyError: available_after_utc`` on real Stage64K
    macro data.

    Keep macro availability metadata under ``macro_available_after_utc`` and expose the
    COT publication/availability date as both ``cot_available_after_utc`` and the
    backwards-compatible alias ``available_after_utc`` used in Stage96 reports.
    """
    left = macro.sort_values("feature_date_utc").copy()
    if "available_after_utc" in left.columns:
        left = left.rename(columns={"available_after_utc": "macro_available_after_utc"})

    right = cot.sort_values("available_after_utc").copy()
    right = right[[
        "report_date_utc",
        "available_after_utc",
        "managed_money_net_pct_oi",
        "cot_mm_net_z",
        "cot_mm_net_z_change_4w",
        "cot_mm_net_pct_oi_change_4w",
    ]].copy()
    right = right.rename(columns={"available_after_utc": "cot_available_after_utc"})

    joined = pd.merge_asof(
        left,
        right,
        left_on="feature_date_utc",
        right_on="cot_available_after_utc",
        direction="backward",
        allow_exact_matches=True,
    )
    joined["available_after_utc"] = joined["cot_available_after_utc"]
    lookahead = int((joined["cot_available_after_utc"].notna() & (joined["cot_available_after_utc"] > joined["feature_date_utc"])).sum())
    return joined, lookahead


def eval_condition(df: pd.DataFrame, cond: Dict[str, Any]) -> Tuple[pd.Series, List[str]]:
    col = cond["column"]
    op = cond["operator"]
    threshold = float(cond["threshold"])
    if col not in df.columns:
        return pd.Series(False, index=df.index), [col]
    values = pd.to_numeric(df[col], errors="coerce")
    if op == ">":
        mask = values > threshold
    elif op == "<":
        mask = values < threshold
    elif op == ">=":
        mask = values >= threshold
    elif op == "<=":
        mask = values <= threshold
    elif op == "==":
        mask = values == threshold
    else:
        raise ValueError(f"Unsupported operator {op}")
    return mask.fillna(False), []


def build_unified_portfolio_mask(df: pd.DataFrame) -> pd.Series:
    # The current observer portfolio: K06 / K03 / K07 / S83_14 / S83_13.
    def numeric(col: str) -> pd.Series:
        if col in df.columns:
            return pd.to_numeric(df[col], errors="coerce")
        return pd.Series(pd.NA, index=df.index, dtype="float64")
    g = numeric("gold_sma20_over_50")
    dxy20 = numeric("dxy_ret_20d")
    ry20 = numeric("real_yield_change_20d")
    vix20 = numeric("vix_change_20d")
    dxy_sma = numeric("dxy_sma20_over_50")
    ry120 = numeric("real_yield_change_120d")
    dxy120 = numeric("dxy_ret_120d")
    k06 = (g > 0) & (dxy20 > 0) & (ry20 < 0)
    k03 = (vix20 > 0) & (ry20 < 0)
    k07 = (g > 0) & (dxy_sma < 0)
    s8314 = (ry120 < 0) & (g < 0)
    s8313 = (dxy120 < 0) & (g < 0)
    return (k06 | k03 | k07 | s8314 | s8313).fillna(False)


def pick_entries(df: pd.DataFrame, active_mask: pd.Series, horizon: int, cooldown: int, price_col: str = "gold_close") -> pd.DataFrame:
    rows = []
    next_allowed_idx = -1
    n = len(df)
    active_mask = active_mask.fillna(False).to_numpy()
    prices = pd.to_numeric(df[price_col], errors="coerce").to_numpy()
    dates = df["feature_date_utc"].to_numpy()
    for i in range(n):
        if i < next_allowed_idx:
            continue
        if not active_mask[i]:
            continue
        exit_i = i + horizon
        if exit_i >= n:
            continue
        ep = prices[i]
        xp = prices[exit_i]
        if not (math.isfinite(ep) and math.isfinite(xp) and ep > 0):
            continue
        rows.append({
            "entry_index": i,
            "exit_index": exit_i,
            "entry_date_utc": pd.Timestamp(dates[i]).date().isoformat(),
            "exit_date_utc": pd.Timestamp(dates[exit_i]).date().isoformat(),
            "entry_price": float(ep),
            "exit_price": float(xp),
            "gross_return_bps": float((xp / ep - 1.0) * 10000.0),
        })
        next_allowed_idx = i + max(1, cooldown)
    return pd.DataFrame(rows)


def summarize_returns(entries: pd.DataFrame, prefix: str) -> Dict[str, Any]:
    if entries.empty:
        return {
            f"{prefix}_entry_count": 0,
            f"{prefix}_mean_net_bps": None,
            f"{prefix}_median_net_bps": None,
            f"{prefix}_win_rate": None,
            f"{prefix}_min_net_return_bps": None,
            f"{prefix}_max_net_return_bps": None,
            f"{prefix}_total_net_return_bps": 0.0,
        }
    vals = pd.to_numeric(entries["net_return_bps"], errors="coerce").dropna()
    if vals.empty:
        return summarize_returns(pd.DataFrame(), prefix)
    return {
        f"{prefix}_entry_count": int(len(vals)),
        f"{prefix}_mean_net_bps": round(float(vals.mean()), 4),
        f"{prefix}_median_net_bps": round(float(vals.median()), 4),
        f"{prefix}_win_rate": round(float((vals > 0).mean()), 4),
        f"{prefix}_min_net_return_bps": round(float(vals.min()), 4),
        f"{prefix}_max_net_return_bps": round(float(vals.max()), 4),
        f"{prefix}_total_net_return_bps": round(float(vals.sum()), 4),
    }


def split_entries(entries: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    if entries.empty:
        return entries.copy()
    d = pd.to_datetime(entries["entry_date_utc"], utc=True, errors="coerce")
    return entries[(d >= pd.Timestamp(start, tz="UTC")) & (d <= pd.Timestamp(end, tz="UTC"))].copy()


def evaluate_rule(df: pd.DataFrame, rule: Dict[str, Any], cfg: Dict[str, Any]) -> Tuple[Dict[str, Any], pd.DataFrame]:
    required_cols: List[str] = []
    mask = pd.Series(True, index=df.index)
    missing_cols: List[str] = []
    for cond in rule.get("conditions", []):
        required_cols.append(cond["column"])
        cmask, miss = eval_condition(df, cond)
        mask &= cmask
        missing_cols.extend(miss)
    current_active = build_unified_portfolio_mask(df)
    raw_active_days = int(mask.sum())
    overlap_days = int((mask & current_active).sum())
    if cfg.get("residual_only", True):
        active_mask = mask & (~current_active)
    else:
        active_mask = mask
    residual_active_days = int(active_mask.sum())
    current_union_active_days = int(current_active.sum())
    final_union_days = int((current_active | mask).sum())
    incremental_days = max(0, final_union_days - current_union_active_days)
    overlap_pct = round((overlap_days / raw_active_days * 100.0), 4) if raw_active_days else 0.0

    # Stage96C correction: COT datasets often start after the macro dataset and z-score
    # features have an unavoidable warm-up window.  Treat missing values before the first
    # row where all required columns are simultaneously available as coverage/warm-up
    # rows, not as a thesis failure.  Missing values after that first complete row remain
    # hard data-quality failures.
    missing_required_feature_rows = 0
    warmup_missing_rows_ignored = 0
    if required_cols:
        existing_required = [c for c in required_cols if c in df.columns]
        missing_entire_cols = [c for c in required_cols if c not in df.columns]
        if missing_entire_cols:
            missing_required_feature_rows = len(df)
        else:
            required_frame = pd.DataFrame(index=df.index)
            for col in existing_required:
                required_frame[col] = pd.to_numeric(df[col], errors="coerce")
            complete_required = required_frame.notna().all(axis=1)
            if bool(complete_required.any()):
                # Stage96D: evaluate missingness from the first date where the *rule's*
                # required feature set is simultaneously available.  This handles:
                # - COT coverage beginning after macro coverage;
                # - rolling COT z-score warm-up;
                # - 4-week COT change warm-up;
                # - macro rolling feature warm-up.
                # After this first-complete point, any later missing row is still a
                # hard DQ issue.
                first_complete_pos = int(complete_required.to_numpy().argmax())
                eval_window = required_frame.iloc[first_complete_pos:]
                missing_required_feature_rows = int((~eval_window.notna().all(axis=1)).sum())
                warmup_missing_rows_ignored = int(first_complete_pos)
            else:
                missing_required_feature_rows = len(df)
                warmup_missing_rows_ignored = 0

    entries = pick_entries(
        df,
        active_mask,
        int(rule.get("horizon_trading_days", 120)),
        int(rule.get("cooldown_trading_days", rule.get("horizon_trading_days", 120))),
    )
    cost = float(cfg.get("cost_bps_total_reference", 50.0))
    if not entries.empty:
        entries["net_return_bps"] = entries["gross_return_bps"] - cost
        entries["rule_id"] = rule["rule_id"]
        entries["label"] = rule.get("label", rule["rule_id"])
        entries["horizon_trading_days"] = int(rule.get("horizon_trading_days", 120))
        entries["cost_bps_total_reference"] = cost

    metrics: Dict[str, Any] = {
        "rule_id": rule["rule_id"],
        "label": rule.get("label", rule["rule_id"]),
        "bucket": rule.get("bucket", ""),
        "horizon_trading_days": int(rule.get("horizon_trading_days", 120)),
        "cooldown_trading_days": int(rule.get("cooldown_trading_days", rule.get("horizon_trading_days", 120))),
        "condition_text": " AND ".join([f"{c['column']}{c['operator']}{c['threshold']}" for c in rule.get("conditions", [])]),
        "missing_columns": "|".join(sorted(set(missing_cols))),
        "missing_required_feature_rows": int(missing_required_feature_rows),
        "warmup_missing_rows_ignored": int(warmup_missing_rows_ignored),
        "raw_active_days": raw_active_days,
        "residual_active_days": residual_active_days,
        "current_union_active_days": current_union_active_days,
        "current_union_active_days_after_candidate": final_union_days,
        "incremental_union_active_days": incremental_days,
        "overlap_with_current_union_days": overlap_days,
        "overlap_with_current_union_pct": overlap_pct,
    }
    metrics.update(summarize_returns(entries, "total"))
    for split_name, (start, end) in SPLITS.items():
        metrics.update(summarize_returns(split_entries(entries, start, end), split_name))
    asof = cfg.get("asof_date", "2024-01-01")
    if not entries.empty:
        d = pd.to_datetime(entries["entry_date_utc"], utc=True, errors="coerce")
        post = entries[d >= pd.Timestamp(asof, tz="UTC")].copy()
    else:
        post = entries.copy()
    metrics.update(summarize_returns(post, "post_asof"))

    # Entry-year concentration.
    if entries.empty:
        metrics["max_entry_year"] = None
        metrics["max_year_entry_share"] = None
    else:
        years = pd.to_datetime(entries["entry_date_utc"], utc=True).dt.year
        vc = years.value_counts()
        metrics["max_entry_year"] = int(vc.idxmax())
        metrics["max_year_entry_share"] = round(float(vc.max() / len(entries)), 4)

    return metrics, entries


def passes_constraints(m: Dict[str, Any], constraints: Dict[str, Any], lookahead_violations: int) -> Tuple[bool, List[str]]:
    fails = []
    def val(key: str, default: float = 0.0) -> float:
        x = m.get(key)
        if x is None:
            return default
        try:
            return float(x)
        except Exception:
            return default
    if val("total_entry_count") < constraints.get("min_total_entries", 0):
        fails.append("TOTAL_ENTRIES_TOO_LOW")
    if val("total_mean_net_bps", -1e9) < constraints.get("min_total_mean_net_bps", -1e9):
        fails.append("TOTAL_MEAN_TOO_LOW")
    if val("total_win_rate", -1e9) < constraints.get("min_total_win_rate", -1e9):
        fails.append("WIN_RATE_TOO_LOW")
    worst = val("total_min_net_return_bps", 0.0)
    if abs(min(0.0, worst)) > constraints.get("max_abs_worst_loss_bps", 1e9):
        fails.append("WORST_LOSS_TOO_LARGE")
    if val("validation_entry_count") < constraints.get("min_validation_entries", 0):
        fails.append("VALIDATION_ENTRIES_TOO_LOW")
    if val("locked_forward_entry_count") < constraints.get("min_locked_forward_entries", 0):
        fails.append("LOCKED_FORWARD_ENTRIES_TOO_LOW")
    if val("locked_forward_mean_net_bps", -1e9) < constraints.get("min_locked_forward_mean_bps", -1e9):
        fails.append("LOCKED_FORWARD_MEAN_TOO_LOW")
    if val("final_holdout_entry_count") < constraints.get("min_final_holdout_entries", 0):
        fails.append("FINAL_HOLDOUT_ENTRIES_TOO_LOW")
    if val("final_holdout_mean_net_bps", -1e9) < constraints.get("min_final_holdout_mean_bps", -1e9):
        fails.append("FINAL_HOLDOUT_MEAN_TOO_LOW")
    if val("post_asof_entry_count") < constraints.get("min_post_asof_entries", 0):
        fails.append("POST_ASOF_ENTRIES_TOO_LOW")
    if val("post_asof_mean_net_bps", -1e9) < constraints.get("min_post_asof_mean_bps", -1e9):
        fails.append("POST_ASOF_MEAN_TOO_LOW")
    if val("max_year_entry_share", 0.0) > constraints.get("max_year_entry_share", 1.0):
        fails.append("YEAR_CONCENTRATION_TOO_HIGH")
    if val("missing_required_feature_rows", 0.0) > constraints.get("max_missing_required_feature_rows", 1e9):
        fails.append("MISSING_REQUIRED_FEATURE_ROWS")
    if lookahead_violations > constraints.get("max_lookahead_violations", 0):
        fails.append("LOOKAHEAD_VIOLATIONS")
    return not fails, fails


def score_candidate(m: Dict[str, Any]) -> float:
    def v(key: str, default: float = 0.0) -> float:
        x = m.get(key)
        if x is None:
            return default
        try:
            return float(x)
        except Exception:
            return default
    return round(
        v("total_mean_net_bps")
        + 1.0 * v("final_holdout_mean_net_bps")
        + 0.75 * v("post_asof_mean_net_bps")
        + 0.25 * v("locked_forward_mean_net_bps")
        + 0.2 * v("incremental_union_active_days")
        + 400.0 * (v("total_win_rate") - 0.5),
        4,
    )


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: List[str] = []
    for r in rows:
        for k in r.keys():
            if k not in keys:
                keys.append(k)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    cfg_path = resolve_path(root, args.config)
    out_dir = resolve_path(root, args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    macro_path = resolve_path(root, cfg["macro_dataset"])
    cot_path = resolve_path(root, cfg["cot_dataset"])

    issues: List[str] = []
    if not macro_path.exists():
        raise FileNotFoundError(f"Macro dataset not found: {macro_path}")
    if not cot_path.exists():
        raise FileNotFoundError(f"COT dataset not found: {cot_path}")

    macro_raw = read_csv_smart(macro_path)
    cot_raw = read_csv_smart(cot_path)
    macro = normalize_macro(macro_raw, cfg.get("date_col", "feature_date_utc"), cfg.get("price_col", "gold_close"))
    cot = normalize_cot(
        cot_raw,
        int(cfg.get("cot_available_lag_calendar_days_if_missing", 3)),
        int(cfg.get("rolling_z_window_weeks", 156)),
        int(cfg.get("rolling_z_min_periods", 52)),
    )
    joined, lookahead_violations = build_joined_dataset(macro, cot)

    required_base = ["cot_mm_net_z", "cot_mm_net_z_change_4w", "managed_money_net_pct_oi", "gold_close"]
    joined_available_rows = int(joined[required_base].notna().all(axis=1).sum()) if all(c in joined.columns for c in required_base) else 0

    metrics_rows: List[Dict[str, Any]] = []
    all_entries: List[pd.DataFrame] = []
    constraints = cfg.get("constraints", {})
    for rule in cfg.get("candidate_rules", []):
        metrics, entries = evaluate_rule(joined, rule, cfg)
        ok, fails = passes_constraints(metrics, constraints, lookahead_violations)
        metrics["pass_cot_discovery_candidate"] = bool(ok)
        metrics["fail_reasons"] = "|".join(fails)
        metrics["cot_discovery_score"] = score_candidate(metrics)
        metrics["lookahead_violations"] = int(lookahead_violations)
        metrics_rows.append(metrics)
        if not entries.empty:
            all_entries.append(entries)

    metrics_rows = sorted(metrics_rows, key=lambda r: r.get("cot_discovery_score") or -1e18, reverse=True)
    pass_rows = [r for r in metrics_rows if r.get("pass_cot_discovery_candidate")]
    shortlist = pass_rows[: int(cfg.get("max_shortlist", 5))]

    decision = "STAGE96_COT_THESIS_SHORTLIST_READY_FOR_HARD_AUDIT_NO_ORDER" if shortlist else "NO_COT_POSITIONING_THESIS_SHORTLIST_NO_ORDER"
    classification = "S96_COT_DISCOVERY_SHORTLIST_READY" if shortlist else "S96_NO_COT_SHORTLIST"
    disposition = "COT_THESIS_SHORTLIST_READY_FOR_STAGE97_HARD_AUDIT" if shortlist else "NO_COT_POSITIONING_THESIS_SHORTLIST"

    metrics_csv = out_dir / "stage96_cot_candidate_metrics.csv"
    shortlist_csv = out_dir / "stage96_cot_thesis_shortlist.csv"
    entries_csv = out_dir / "stage96_cot_entry_returns.csv"
    joined_csv = out_dir / "stage96_cot_joined_daily_snapshot.csv"
    write_csv(metrics_csv, metrics_rows)
    write_csv(shortlist_csv, shortlist)
    if all_entries:
        pd.concat(all_entries, ignore_index=True).to_csv(entries_csv, index=False)
    else:
        entries_csv.write_text("", encoding="utf-8")
    snapshot_cols = [c for c in [
        "feature_date_utc", "gold_close", "report_date_utc", "available_after_utc", "managed_money_net_pct_oi",
        "cot_mm_net_z", "cot_mm_net_z_change_4w", "gold_sma20_over_50", "dxy_ret_20d", "real_yield_change_20d"
    ] if c in joined.columns]
    joined[snapshot_cols].tail(2000).to_csv(joined_csv, index=False)

    summary = {
        "stage": STAGE,
        "root": str(root),
        "config": str(cfg_path),
        "generated_utc": utc_now_iso(),
        "patch_version": PATCH_VERSION,
        "status": "STAGE96_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
        "principle": "Discover thesis-first COT positioning candidates using lag-aware COT data joined to daily macro data. No orders, no broker connection, no MT5/EA change.",
        "macro_dataset": {
            "path": str(macro_path),
            "rows": int(len(macro)),
            "min_date": macro["feature_date_utc"].min().date().isoformat() if len(macro) else None,
            "max_date": macro["feature_date_utc"].max().date().isoformat() if len(macro) else None,
            "sha256": sha256_file(macro_path),
        },
        "cot_dataset": {
            "path": str(cot_path),
            "raw_rows": int(len(cot_raw)),
            "normalized_rows": int(len(cot)),
            "min_report_date_utc": cot["report_date_utc"].min().date().isoformat() if len(cot) else None,
            "max_report_date_utc": cot["report_date_utc"].max().date().isoformat() if len(cot) else None,
            "zscore_non_null": int(cot["cot_mm_net_z"].notna().sum()) if "cot_mm_net_z" in cot.columns else 0,
            "sha256": sha256_file(cot_path),
        },
        "joined_daily_rows": int(len(joined)),
        "joined_cot_available_rows": int(joined_available_rows),
        "lookahead_violations": int(lookahead_violations),
        "residual_only": bool(cfg.get("residual_only", True)),
        "candidate_count": int(len(metrics_rows)),
        "pass_candidate_count": int(len(pass_rows)),
        "shortlist_count": int(len(shortlist)),
        "shortlist_rule_ids": [r["rule_id"] for r in shortlist],
        "shortlist": shortlist,
        "candidate_snapshot": metrics_rows[:12],
        "constraints": constraints,
        "issues": issues,
        "hard_blocks": HARD_BLOCKS,
        "outputs": {
            "summary_json": str(out_dir / "stage96_cot_positioning_thesis_discovery_summary.json"),
            "report_md": str(out_dir / "stage96_cot_positioning_thesis_discovery_report.md"),
            "candidate_metrics_csv": str(metrics_csv),
            "shortlist_csv": str(shortlist_csv),
            "entry_returns_csv": str(entries_csv),
            "joined_daily_snapshot_csv": str(joined_csv),
        },
    }
    summary_path = out_dir / "stage96_cot_positioning_thesis_discovery_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    report = [
        "# Stage96 COT Positioning Thesis Discovery",
        "",
        "## Decision",
        f"- status: `{summary['status']}`",
        f"- decision: `{decision}`",
        f"- classification: `{classification}`",
        f"- disposition: `{disposition}`",
        "",
        "## Dataset",
        f"- macro rows: `{len(macro)}`",
        f"- COT normalized rows: `{len(cot)}`",
        f"- joined daily rows: `{len(joined)}`",
        f"- lookahead violations: `{lookahead_violations}`",
        f"- residual_only: `{bool(cfg.get('residual_only', True))}`",
        f"- patch_version: `{PATCH_VERSION}`",
        "",
        "## Shortlist",
    ]
    if shortlist:
        for r in shortlist:
            report.append(f"- `{r['rule_id']}`: {r.get('label')} score=`{r.get('cot_discovery_score')}` mean=`{r.get('total_mean_net_bps')}` win=`{r.get('total_win_rate')}` final=`{r.get('final_holdout_mean_net_bps')}` post_asof=`{r.get('post_asof_mean_net_bps')}` fail=`{r.get('fail_reasons')}`")
    else:
        report.append("- none")
    report.extend([
        "",
        "## Candidate snapshot",
    ])
    for r in metrics_rows:
        report.append(f"- `{r['rule_id']}` pass=`{r.get('pass_cot_discovery_candidate')}` score=`{r.get('cot_discovery_score')}` entries=`{r.get('total_entry_count')}` mean=`{r.get('total_mean_net_bps')}` win=`{r.get('total_win_rate')}` final=`{r.get('final_holdout_mean_net_bps')}` fail=`{r.get('fail_reasons')}`")
    report.extend(["", "## Hard blocks"] + [f"- `{b}`" for b in HARD_BLOCKS])
    (out_dir / "stage96_cot_positioning_thesis_discovery_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    print(json.dumps({"status": summary["status"], "decision": decision, "shortlist_count": len(shortlist)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
