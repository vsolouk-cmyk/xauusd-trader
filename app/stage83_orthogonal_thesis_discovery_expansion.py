#!/usr/bin/env python3
"""
Stage83 Orthogonal Thesis Discovery Expansion

Purpose:
  Continue thesis-first discovery only after Stage82 kept the Stage77B portfolio unchanged
  because Stage81B survivors overlapped too much with the existing portfolio.

This stage searches for lower-overlap macro-regime thesis candidates. It does not authorize
orders, broker connections, EA changes, paper trading, or threshold tuning.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd


def now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def safe_float(x: Any) -> Optional[float]:
    try:
        if pd.isna(x):
            return None
        return float(x)
    except Exception:
        return None


OPS = {
    ">": lambda s, t: s > t,
    "<": lambda s, t: s < t,
    ">=": lambda s, t: s >= t,
    "<=": lambda s, t: s <= t,
    "==": lambda s, t: s == t,
    "!=": lambda s, t: s != t,
}


def load_macro(path: Path, date_col: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"macro dataset not found: {path}")
    df = pd.read_csv(path)
    if date_col not in df.columns:
        raise ValueError(f"date column {date_col!r} not found in macro dataset")
    df[date_col] = pd.to_datetime(df[date_col], utc=True, errors="coerce")
    if df[date_col].isna().any():
        bad = int(df[date_col].isna().sum())
        raise ValueError(f"macro dataset has {bad} invalid dates in {date_col}")
    df = df.sort_values(date_col).reset_index(drop=True)

    # Convert likely numeric columns safely. Metadata/date-like string columns that cannot
    # convert remain as all-NaN only if overwritten, so avoid rewriting all-NaN conversions.
    for col in df.columns:
        if col == date_col:
            continue
        if df[col].dtype == object:
            converted = pd.to_numeric(df[col], errors="coerce")
            if converted.notna().sum() > 0:
                df[col] = converted
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def first_existing(df: pd.DataFrame, names: Iterable[str]) -> Optional[str]:
    for n in names:
        if n in df.columns:
            return n
    return None


def add_derived_features(df: pd.DataFrame, price_col: str) -> List[str]:
    added: List[str] = []

    def add_col(name: str, values: pd.Series) -> None:
        nonlocal added
        if name not in df.columns:
            df[name] = values
            added.append(name)

    if price_col in df.columns:
        p = pd.to_numeric(df[price_col], errors="coerce")
        for n in [20, 60, 120]:
            add_col(f"gold_ret_{n}d", p.pct_change(n))
        sma20 = p.rolling(20, min_periods=20).mean()
        sma50 = p.rolling(50, min_periods=50).mean()
        add_col("gold_sma20_over_50", (sma20 / sma50) - 1.0)
        ret = p.pct_change()
        add_col("gold_realized_vol_20d", ret.rolling(20, min_periods=20).std())

    dxy_col = first_existing(df, ["dxy", "dxy_close", "DXY", "dxy_index"])
    if dxy_col:
        d = pd.to_numeric(df[dxy_col], errors="coerce")
        for n in [20, 60, 120]:
            add_col(f"dxy_ret_{n}d", d.pct_change(n))
        sma20 = d.rolling(20, min_periods=20).mean()
        sma50 = d.rolling(50, min_periods=50).mean()
        add_col("dxy_sma20_over_50", (sma20 / sma50) - 1.0)

    ry_col = first_existing(df, ["real_yield", "real_yield_close", "us10y_real_yield"])
    if ry_col:
        r = pd.to_numeric(df[ry_col], errors="coerce")
        for n in [20, 60, 120]:
            add_col(f"real_yield_change_{n}d", r - r.shift(n))

    vix_col = first_existing(df, ["vix", "vix_close", "VIX"])
    if vix_col:
        v = pd.to_numeric(df[vix_col], errors="coerce")
        for n in [20, 60]:
            add_col(f"vix_change_{n}d", v - v.shift(n))
        add_col("vix_ret_20d", v.pct_change(20))

    if "etf_flow_tonnes_3m" in df.columns:
        e = pd.to_numeric(df["etf_flow_tonnes_3m"], errors="coerce")
        add_col("etf_flow_change_20d", e - e.shift(20))
        add_col("etf_flow_positive", (e > 0).astype(float))

    if "central_bank_demand_tonnes_3m" in df.columns:
        c = pd.to_numeric(df["central_bank_demand_tonnes_3m"], errors="coerce")
        add_col("central_bank_demand_change_20d", c - c.shift(20))
        add_col("central_bank_demand_positive", (c > 0).astype(float))

    return added


def condition_text(conditions: List[Dict[str, Any]]) -> str:
    return " AND ".join(f"{c['column']}{c['operator']}{c['threshold']}" for c in conditions)


def evaluate_conditions(df: pd.DataFrame, conditions: List[Dict[str, Any]]) -> Tuple[pd.Series, List[str], int, int, List[Dict[str, Any]]]:
    missing_cols = [c["column"] for c in conditions if c["column"] not in df.columns]
    if missing_cols:
        return pd.Series(False, index=df.index), missing_cols, len(df), -1, []

    required_cols = [c["column"] for c in conditions]
    required_complete = df[required_cols].notna().all(axis=1)
    complete_indices = list(required_complete[required_complete].index)
    if not complete_indices:
        return pd.Series(False, index=df.index), [], len(df), -1, []
    first_complete_idx = int(complete_indices[0])
    missing_after_warmup = int((~required_complete.loc[first_complete_idx:]).sum())

    mask = pd.Series(True, index=df.index)
    latest_condition_results: List[Dict[str, Any]] = []
    for c in conditions:
        col = c["column"]
        op = c["operator"]
        threshold = float(c["threshold"])
        if op not in OPS:
            raise ValueError(f"unsupported operator {op!r}")
        s = pd.to_numeric(df[col], errors="coerce")
        cond = OPS[op](s, threshold).fillna(False)
        mask &= cond

        latest_value = safe_float(s.iloc[-1])
        latest_pass = bool(cond.iloc[-1]) if len(cond) else False
        latest_condition_results.append({
            "column": col,
            "operator": op,
            "threshold": threshold,
            "value": latest_value,
            "passed": latest_pass,
            "reason": "ok" if latest_pass else f"{latest_value}{op}{threshold}",
        })

    mask &= required_complete
    warmup_ignored = first_complete_idx
    return mask, [], missing_after_warmup, warmup_ignored, latest_condition_results


def current_portfolio_union_mask(df: pd.DataFrame) -> pd.Series:
    rules = [
        [
            {"column": "gold_sma20_over_50", "operator": ">", "threshold": 0.0},
            {"column": "dxy_ret_20d", "operator": ">", "threshold": 0.0},
            {"column": "real_yield_change_20d", "operator": "<", "threshold": 0.0},
        ],
        [
            {"column": "vix_change_20d", "operator": ">", "threshold": 0.0},
            {"column": "real_yield_change_20d", "operator": "<", "threshold": 0.0},
        ],
        [
            {"column": "gold_sma20_over_50", "operator": ">", "threshold": 0.0},
            {"column": "dxy_sma20_over_50", "operator": "<", "threshold": 0.0},
        ],
    ]
    union = pd.Series(False, index=df.index)
    for conds in rules:
        mask, missing, *_ = evaluate_conditions(df, conds)
        if not missing:
            union |= mask
    return union.fillna(False)


def split_name(dt: pd.Timestamp) -> str:
    d = dt.date()
    if d < pd.Timestamp("2015-01-01").date():
        return "TRAIN_DISCOVERY"
    if d < pd.Timestamp("2019-01-01").date():
        return "VALIDATION_SELECTION"
    if d < pd.Timestamp("2023-01-01").date():
        return "LOCKED_HISTORICAL_FORWARD"
    return "FINAL_STATISTICAL_HOLDOUT"


def build_entries(
    df: pd.DataFrame,
    mask: pd.Series,
    date_col: str,
    price_col: str,
    horizon: int,
    cooldown: int,
    cost_bps: float,
    rule_id: str,
    label: str,
) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    prices = pd.to_numeric(df[price_col], errors="coerce")
    next_allowed = 0
    n = len(df)
    for idx, active in enumerate(mask.fillna(False).tolist()):
        if not active or idx < next_allowed:
            continue
        exit_idx = idx + horizon
        next_allowed = idx + cooldown
        if exit_idx >= n:
            continue
        entry_price = safe_float(prices.iloc[idx])
        exit_price = safe_float(prices.iloc[exit_idx])
        if entry_price is None or exit_price is None or entry_price <= 0:
            continue
        gross_bps = (exit_price / entry_price - 1.0) * 10000.0
        net_bps = gross_bps - cost_bps
        entry_date = df[date_col].iloc[idx]
        exit_date = df[date_col].iloc[exit_idx]
        entries.append({
            "rule_id": rule_id,
            "label": label,
            "entry_index": idx,
            "exit_index": exit_idx,
            "entry_date_utc": entry_date.date().isoformat(),
            "exit_date_utc": exit_date.date().isoformat(),
            "entry_price": round(entry_price, 8),
            "exit_price": round(exit_price, 8),
            "gross_return_bps": round(gross_bps, 4),
            "net_return_bps": round(net_bps, 4),
            "split": split_name(entry_date),
        })
    return entries


def metrics_from_returns(vals: List[float], prefix: str) -> Dict[str, Any]:
    if not vals:
        return {
            f"{prefix}_entries": 0,
            f"{prefix}_mean_net_bps": None,
            f"{prefix}_median_net_bps": None,
            f"{prefix}_win_rate": None,
        }
    s = pd.Series(vals, dtype="float64")
    return {
        f"{prefix}_entries": int(len(s)),
        f"{prefix}_mean_net_bps": round(float(s.mean()), 4),
        f"{prefix}_median_net_bps": round(float(s.median()), 4),
        f"{prefix}_win_rate": round(float((s > 0).mean()), 4),
    }


def evaluate_rule(
    df: pd.DataFrame,
    rule: Dict[str, Any],
    date_col: str,
    price_col: str,
    current_union: pd.Series,
    constraints: Dict[str, Any],
    cost_bps: float,
    asof_date: str,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    rule_id = rule["rule_id"]
    label = rule.get("label", rule_id)
    horizon = int(rule.get("horizon_trading_days", 120))
    cooldown = int(rule.get("cooldown_trading_days", horizon))
    conditions = rule["conditions"]

    mask, missing_columns, missing_after_warmup, warmup_ignored, latest_condition_results = evaluate_conditions(df, conditions)
    active_days = int(mask.sum())
    current_union_active = int(current_union.sum())
    union_after = int((current_union | mask).sum())
    incremental_days = union_after - current_union_active
    intersection = int((current_union & mask).sum())
    max_overlap_pct = round(100.0 * intersection / active_days, 4) if active_days else 100.0
    jaccard_den = int((current_union | mask).sum())
    jaccard_pct = round(100.0 * intersection / jaccard_den, 4) if jaccard_den else 0.0

    entries = build_entries(df, mask, date_col, price_col, horizon, cooldown, cost_bps, rule_id, label)
    vals = [float(e["net_return_bps"]) for e in entries]

    total = metrics_from_returns(vals, "total")
    if vals:
        total.update({
            "total_min_net_return_bps": round(float(min(vals)), 4),
            "total_max_net_return_bps": round(float(max(vals)), 4),
            "total_total_net_return_bps": round(float(sum(vals)), 4),
        })
    else:
        total.update({
            "total_min_net_return_bps": None,
            "total_max_net_return_bps": None,
            "total_total_net_return_bps": 0.0,
        })

    by_split: Dict[str, List[float]] = {"TRAIN_DISCOVERY": [], "VALIDATION_SELECTION": [], "LOCKED_HISTORICAL_FORWARD": [], "FINAL_STATISTICAL_HOLDOUT": []}
    for e in entries:
        by_split[e["split"]].append(float(e["net_return_bps"]))

    split_metrics: Dict[str, Any] = {}
    split_metrics.update(metrics_from_returns(by_split["TRAIN_DISCOVERY"], "train"))
    split_metrics.update(metrics_from_returns(by_split["VALIDATION_SELECTION"], "validation"))
    split_metrics.update(metrics_from_returns(by_split["LOCKED_HISTORICAL_FORWARD"], "locked_forward"))
    split_metrics.update(metrics_from_returns(by_split["FINAL_STATISTICAL_HOLDOUT"], "final_holdout"))

    asof_ts = pd.Timestamp(asof_date, tz="UTC")
    post_vals: List[float] = []
    pre_vals: List[float] = []
    for e in entries:
        entry_dt = pd.Timestamp(e["entry_date_utc"], tz="UTC")
        if entry_dt >= asof_ts:
            post_vals.append(float(e["net_return_bps"]))
        else:
            pre_vals.append(float(e["net_return_bps"]))
    asof_metrics: Dict[str, Any] = {}
    asof_metrics.update(metrics_from_returns(pre_vals, "pre_asof"))
    asof_metrics.update(metrics_from_returns(post_vals, "post_asof"))
    # To keep the output comparable with previous stages, post_plus_final is the post-as-of window
    # when available; otherwise it remains empty.
    asof_metrics.update(metrics_from_returns(post_vals, "post_plus_final"))

    years: Dict[int, int] = {}
    for e in entries:
        y = int(str(e["entry_date_utc"])[:4])
        years[y] = years.get(y, 0) + 1
    max_year_entry_share = round(max(years.values()) / len(entries), 4) if entries else 1.0
    max_entry_year = max(years, key=years.get) if years else None

    latest_active = bool(mask.iloc[-1]) if len(mask) else False
    latest_failures: List[str] = []
    if latest_condition_results:
        for r in latest_condition_results:
            if not r["passed"]:
                latest_failures.append(f"{r['column']}:{r['reason']}")

    fail_reasons: List[str] = []
    c = constraints
    if missing_columns:
        fail_reasons.append("MISSING_COLUMNS")
    if missing_after_warmup > int(c["max_missing_required_feature_rows"]):
        fail_reasons.append("MISSING_REQUIRED_FEATURE_ROWS")
    if total["total_entries"] < int(c["min_total_entries"]):
        fail_reasons.append("TOO_FEW_TOTAL_ENTRIES")
    if (total["total_mean_net_bps"] is None) or total["total_mean_net_bps"] < float(c["min_total_mean_net_bps"]):
        fail_reasons.append("TOTAL_MEAN_TOO_LOW")
    if (total["total_win_rate"] is None) or total["total_win_rate"] < float(c["min_total_win_rate"]):
        fail_reasons.append("WIN_RATE_TOO_LOW")
    if total["total_min_net_return_bps"] is None or abs(float(total["total_min_net_return_bps"])) > float(c["max_abs_worst_loss_bps"]):
        fail_reasons.append("WORST_LOSS_TOO_LARGE")
    if split_metrics["locked_forward_entries"] < int(c["min_locked_forward_entries"]):
        fail_reasons.append("TOO_FEW_LOCKED_FORWARD_ENTRIES")
    if (split_metrics["locked_forward_mean_net_bps"] is None) or split_metrics["locked_forward_mean_net_bps"] < float(c["min_locked_forward_mean_bps"]):
        fail_reasons.append("LOCKED_FORWARD_MEAN_TOO_LOW")
    if split_metrics["final_holdout_entries"] < int(c["min_final_holdout_entries"]):
        fail_reasons.append("TOO_FEW_FINAL_HOLDOUT_ENTRIES")
    if (split_metrics["final_holdout_mean_net_bps"] is None) or split_metrics["final_holdout_mean_net_bps"] < float(c["min_final_holdout_mean_bps"]):
        fail_reasons.append("FINAL_HOLDOUT_MEAN_TOO_LOW")
    if asof_metrics["post_plus_final_entries"] < int(c["min_post_plus_final_entries"]):
        fail_reasons.append("TOO_FEW_POST_ASOF_ENTRIES")
    if (asof_metrics["post_plus_final_mean_net_bps"] is None) or asof_metrics["post_plus_final_mean_net_bps"] < float(c["min_post_plus_final_mean_bps"]):
        fail_reasons.append("POST_ASOF_MEAN_TOO_LOW")
    if max_year_entry_share > float(c["max_year_entry_share"]):
        fail_reasons.append("YEAR_CONCENTRATION_TOO_HIGH")
    if max_overlap_pct > float(c["max_overlap_with_current_portfolio_pct"]):
        fail_reasons.append("OVERLAP_WITH_CURRENT_PORTFOLIO_TOO_HIGH")
    if incremental_days < int(c["min_incremental_union_active_days"]):
        fail_reasons.append("INCREMENTAL_ACTIVE_DAYS_TOO_LOW")

    score_parts = [
        total.get("total_mean_net_bps") or 0.0,
        split_metrics.get("locked_forward_mean_net_bps") or 0.0,
        split_metrics.get("final_holdout_mean_net_bps") or 0.0,
        asof_metrics.get("post_plus_final_mean_net_bps") or 0.0,
        0.5 * incremental_days,
        -8.0 * max_overlap_pct,
    ]
    score = round(float(sum(score_parts)), 4)

    row: Dict[str, Any] = {
        "rule_id": rule_id,
        "label": label,
        "bucket": rule.get("bucket", ""),
        "horizon_trading_days": horizon,
        "cooldown_trading_days": cooldown,
        "condition_text": condition_text(conditions),
        "missing_columns": "|".join(missing_columns),
        "missing_required_feature_rows": missing_after_warmup,
        "warmup_missing_rows_ignored": warmup_ignored if warmup_ignored >= 0 else None,
        "active_days": active_days,
        "current_union_active_days_before": current_union_active,
        "current_union_active_days_after_candidate": union_after,
        "incremental_union_active_days": incremental_days,
        "max_overlap_with_current_portfolio_pct": max_overlap_pct,
        "max_jaccard_with_current_portfolio_pct": jaccard_pct,
        "latest_signal_active": latest_active,
        "latest_failures": "|".join(latest_failures),
        "max_entry_year": max_entry_year,
        "max_year_entry_share": max_year_entry_share,
        "pass_orthogonal_discovery_candidate": len(fail_reasons) == 0,
        "fail_reasons": "|".join(fail_reasons),
        "orthogonal_discovery_score": score,
    }
    row.update(total)
    row.update(split_metrics)
    row.update(asof_metrics)
    return row, entries


def rows_to_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    # Stable union of keys.
    keys: List[str] = []
    seen = set()
    for r in rows:
        for k in r.keys():
            if k not in seen:
                seen.add(k)
                keys.append(k)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def make_report(summary: Dict[str, Any], shortlist: List[Dict[str, Any]], path: Path) -> None:
    lines = [
        "# Stage83 Orthogonal Thesis Discovery Expansion",
        "",
        "## Decision",
        f"- status: `{summary['status']}`",
        f"- decision: `{summary['decision']}`",
        f"- classification: `{summary['classification']}`",
        f"- disposition: `{summary['disposition']}`",
        "",
        "## Principle",
        summary["principle"],
        "",
        "## Current portfolio reference",
    ]
    for rid in summary["current_stage77b_rule_ids"]:
        lines.append(f"- `{rid}`")
    lines += ["", "## Shortlist for Stage84"]
    if shortlist:
        for r in shortlist:
            lines.append(
                f"- `{r['rule_id']}`: {r['label']} score=`{r['orthogonal_discovery_score']}` "
                f"mean=`{r['total_mean_net_bps']}` overlap=`{r['max_overlap_with_current_portfolio_pct']}` "
                f"incremental_days=`{r['incremental_union_active_days']}`"
            )
    else:
        lines.append("- none")
    lines += ["", "## Candidate snapshot"]
    for r in summary["candidate_snapshot"]:
        lines.append(
            f"- `{r['rule_id']}` pass=`{r['pass_orthogonal_discovery_candidate']}` "
            f"score=`{r['orthogonal_discovery_score']}` mean=`{r['total_mean_net_bps']}` "
            f"overlap=`{r['max_overlap_with_current_portfolio_pct']}` "
            f"incremental=`{r['incremental_union_active_days']}` fail=`{r['fail_reasons']}`"
        )
    lines += ["", "## Hard blocks"]
    for b in summary["hard_blocks"]:
        lines.append(f"- `{b}`")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = root / config_path
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir

    cfg = read_json(config_path)
    macro_path = Path(cfg["macro_dataset_path"])
    if not macro_path.is_absolute():
        macro_path = root / macro_path
    date_col = cfg.get("date_col", "feature_date_utc")
    price_col = cfg.get("price_col", "gold_close")

    df = load_macro(macro_path, date_col)
    derived_added = add_derived_features(df, price_col)

    if price_col not in df.columns:
        raise ValueError(f"price column {price_col!r} not found")

    current_union = current_portfolio_union_mask(df)
    cost_bps = float(cfg.get("cost_bps_total_reference", 50.0))
    asof_date = cfg.get("asof_date", "2024-01-01")
    constraints = cfg["constraints"]

    rows: List[Dict[str, Any]] = []
    all_entries: List[Dict[str, Any]] = []
    missing_data_rows: List[Dict[str, Any]] = []
    for rule in cfg["candidate_rules"]:
        row, entries = evaluate_rule(df, rule, date_col, price_col, current_union, constraints, cost_bps, asof_date)
        rows.append(row)
        all_entries.extend(entries)
        if row["missing_columns"] or int(row["missing_required_feature_rows"] or 0) > 0:
            missing_data_rows.append({
                "rule_id": row["rule_id"],
                "missing_columns": row["missing_columns"],
                "missing_required_feature_rows": row["missing_required_feature_rows"],
            })

    rows_sorted = sorted(rows, key=lambda r: r["orthogonal_discovery_score"], reverse=True)
    passing = [r for r in rows_sorted if r["pass_orthogonal_discovery_candidate"]]
    shortlist = passing[: int(cfg.get("max_shortlist", 8))]

    if shortlist:
        decision = "STAGE83_ORTHOGONAL_DISCOVERY_SHORTLIST_READY_FOR_HARD_AUDIT_NO_ORDER"
        classification = "S83_ORTHOGONAL_DISCOVERY_SHORTLIST_READY"
        disposition = "ORTHOGONAL_THESIS_SHORTLIST_READY_FOR_STAGE84_HARD_AUDIT"
    else:
        decision = "STAGE83_NO_ORTHOGONAL_DISCOVERY_PASS_NO_ORDER"
        classification = "S83_NO_ORTHOGONAL_DISCOVERY_PASS"
        disposition = "NO_ORTHOGONAL_THESIS_READY_FOR_HARD_AUDIT"

    out_dir.mkdir(parents=True, exist_ok=True)
    metrics_csv = out_dir / "stage83_orthogonal_discovery_candidate_metrics.csv"
    shortlist_csv = out_dir / "stage83_orthogonal_discovery_shortlist.csv"
    entries_csv = out_dir / "stage83_orthogonal_discovery_entry_returns.csv"
    missing_csv = out_dir / "stage83_orthogonal_missing_data_requirements.csv"
    rows_to_csv(metrics_csv, rows_sorted)
    rows_to_csv(shortlist_csv, shortlist)
    rows_to_csv(entries_csv, all_entries)
    rows_to_csv(missing_csv, missing_data_rows)

    summary = {
        "stage": "Stage83_ORTHOGONAL_THESIS_DISCOVERY_EXPANSION",
        "root": str(root),
        "config": str(config_path),
        "generated_utc": now_utc(),
        "status": "STAGE83_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
        "principle": "Search for lower-overlap thesis-first macro candidates after Stage82 kept the Stage77B portfolio unchanged. Do not loosen overlap gates and do not change MT5/EA/order state.",
        "macro_dataset": {
            "path": str(macro_path),
            "rows": int(len(df)),
            "date_col": date_col,
            "price_col": price_col,
            "min_date": df[date_col].min().date().isoformat(),
            "max_date": df[date_col].max().date().isoformat(),
            "sha256": sha256_file(macro_path),
            "derived_features_added": derived_added,
        },
        "current_stage77b_rule_ids": [
            "K06_RESILIENT_GOLD_VS_DXY_H120",
            "K03_SAFE_HAVEN_REALYIELD_H120",
            "K07_DXY_TREND_RELIEF_GOLD_TREND_H120",
        ],
        "candidate_count": len(rows_sorted),
        "pass_candidate_count": len(passing),
        "shortlist_count": len(shortlist),
        "shortlist_rule_ids": [r["rule_id"] for r in shortlist],
        "shortlist": shortlist,
        "candidate_snapshot": [
            {
                "rule_id": r["rule_id"],
                "label": r["label"],
                "pass_orthogonal_discovery_candidate": r["pass_orthogonal_discovery_candidate"],
                "orthogonal_discovery_score": r["orthogonal_discovery_score"],
                "total_mean_net_bps": r["total_mean_net_bps"],
                "total_win_rate": r["total_win_rate"],
                "final_holdout_mean_net_bps": r["final_holdout_mean_net_bps"],
                "post_plus_final_mean_net_bps": r["post_plus_final_mean_net_bps"],
                "max_overlap_with_current_portfolio_pct": r["max_overlap_with_current_portfolio_pct"],
                "incremental_union_active_days": r["incremental_union_active_days"],
                "fail_reasons": r["fail_reasons"],
            }
            for r in rows_sorted[:20]
        ],
        "latest_feature_date_utc": df[date_col].max().date().isoformat(),
        "current_union_active_days": int(current_union.sum()),
        "constraints": constraints,
        "hard_blocks": [
            "NO_AUTOMATED_ORDER",
            "NO_PAPER_ORDER",
            "NO_BROKER_CONNECTION",
            "NO_EA_PROMOTION",
            "NO_PAPER_LIVE",
            "NO_LIVE",
            "NO_ORDER_AUTHORIZATION_FROM_STAGE83",
            "NO_THRESHOLD_TUNING_FROM_STAGE83_DISCOVERY",
            "NO_DIRECT_MT5_OR_EA_CHANGE_FROM_STAGE83",
        ],
        "outputs": {
            "summary_json": str(out_dir / "stage83_orthogonal_thesis_discovery_expansion_summary.json"),
            "report_md": str(out_dir / "stage83_orthogonal_thesis_discovery_expansion_report.md"),
            "candidate_metrics_csv": str(metrics_csv),
            "shortlist_csv": str(shortlist_csv),
            "entry_returns_csv": str(entries_csv),
            "missing_data_requirements_csv": str(missing_csv),
        },
    }

    summary_json = out_dir / "stage83_orthogonal_thesis_discovery_expansion_summary.json"
    report_md = out_dir / "stage83_orthogonal_thesis_discovery_expansion_report.md"
    write_json(summary_json, summary)
    make_report(summary, shortlist, report_md)

    print(json.dumps({
        "stage": summary["stage"],
        "status": summary["status"],
        "decision": summary["decision"],
        "classification": summary["classification"],
        "shortlist_count": summary["shortlist_count"],
        "summary_json": str(summary_json),
        "report_md": str(report_md),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
