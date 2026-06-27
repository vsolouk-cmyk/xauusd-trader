#!/usr/bin/env python3
"""
Stage106 Second-Order COT/Macro Hard Audit

Hard-audits Stage105 second-order COT/macro shortlist before any portfolio or
observer expansion. This stage does not trade, does not change MT5/EA, and does
not authorize orders.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

STAGE = "Stage106_SECOND_ORDER_COT_MACRO_HARD_AUDIT"

CURRENT_UNIFIED_RULES = [
    {
        "rule_id": "K06_RESILIENT_GOLD_VS_DXY_H120",
        "short_id": "K06",
        "condition_text": "gold_sma20_over_50>0.0 AND dxy_ret_20d>0.0 AND real_yield_change_20d<0.0",
    },
    {
        "rule_id": "K03_SAFE_HAVEN_REALYIELD_H120",
        "short_id": "K03",
        "condition_text": "vix_change_20d>0.0 AND real_yield_change_20d<0.0",
    },
    {
        "rule_id": "K07_DXY_TREND_RELIEF_GOLD_TREND_H120",
        "short_id": "K07",
        "condition_text": "gold_sma20_over_50>0.0 AND dxy_sma20_over_50<0.0",
    },
    {
        "rule_id": "S83_14_REALYIELD_120D_DOWN_GOLD_NOT_TRENDING_H120",
        "short_id": "S83_14",
        "condition_text": "real_yield_change_120d<0.0 AND gold_sma20_over_50<0.0",
    },
    {
        "rule_id": "S83_13_DXY_120D_DOWN_GOLD_NOT_TRENDING_H120",
        "short_id": "S83_13",
        "condition_text": "dxy_ret_120d<0.0 AND gold_sma20_over_50<0.0",
    },
    {
        "rule_id": "C96_07_CB_SUPPORT_NOT_CROWDED_H120",
        "short_id": "C96_07",
        "condition_text": "cot_mm_net_z<1.0 AND central_bank_demand_tonnes_3m>0.0 AND gold_ret_20d<0.0",
    },
]

COT_ALIAS_MAP = {
    "managed_money_net_pct_oi_z_156w": "cot_mm_net_z",
    "managed_money_net_z_156w": "cot_mm_net_z",
    "mm_net_pct_oi_z_156w": "cot_mm_net_z",
    "cot_mm_net_z": "cot_mm_net_z",
    "managed_money_net_pct_oi_change_4w": "cot_mm_net_z_change_4w",
    "managed_money_net_change_4w": "cot_mm_net_z_change_4w",
    "mm_net_pct_oi_change_4w": "cot_mm_net_z_change_4w",
    "cot_mm_net_z_change_4w": "cot_mm_net_z_change_4w",
}

DATE_COLS = [
    "date", "date_utc", "utc_date", "asof_date_utc", "as_of_date",
    "trading_date", "timestamp", "utc_time", "time", "datetime",
]
COT_DATE_COLS = [
    "report_date_utc", "report_date", "date", "date_utc", "timestamp", "time"
]
COT_AVAILABLE_COLS = [
    "available_after_utc", "cot_available_after_utc", "available_after",
    "release_date_utc", "publication_date_utc",
]


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_config(root: Path, config_path: Path) -> Dict[str, Any]:
    cfg = read_json(config_path)
    cfg.setdefault("paths", {})
    cfg.setdefault("constraints", {})
    cfg.setdefault("post_asof_date", "2024-01-01")
    return cfg


def first_existing_col(df: pd.DataFrame, candidates: List[str]) -> str | None:
    lower_to_actual = {str(c).lower(): c for c in df.columns}
    for c in candidates:
        if c in df.columns:
            return c
        if c.lower() in lower_to_actual:
            return lower_to_actual[c.lower()]
    return None


def safe_to_numeric(s: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(s):
        return s
    cleaned = s.astype(str).str.replace(",", "", regex=False).str.replace("%", "", regex=False).str.strip()
    out = pd.to_numeric(cleaned, errors="coerce")
    if out.notna().sum() == 0 and s.notna().sum() > 0:
        return s
    return out


def load_macro(root: Path, cfg: Dict[str, Any]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    rel = cfg["paths"].get("macro_dataset", "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv")
    p = root / rel
    if not p.exists():
        raise FileNotFoundError(f"Macro dataset not found: {p}")
    df = pd.read_csv(p)
    date_col = first_existing_col(df, DATE_COLS)
    if date_col is None:
        raise ValueError(f"No macro date column found. Columns sample={list(df.columns)[:40]}")
    df["_date"] = pd.to_datetime(df[date_col], errors="coerce", utc=True).dt.tz_convert(None).dt.normalize()
    df = df.dropna(subset=["_date"]).sort_values("_date").drop_duplicates("_date", keep="last")
    for c in df.columns:
        if c == "_date":
            continue
        df[c] = safe_to_numeric(df[c])
    meta = {
        "path": str(p),
        "rows": int(len(df)),
        "date_col": str(date_col),
        "min_date": df["_date"].min().date().isoformat() if len(df) else None,
        "max_date": df["_date"].max().date().isoformat() if len(df) else None,
        "sha256": sha256_file(p),
    }
    return df, meta


def load_cot(root: Path, cfg: Dict[str, Any]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    rel = cfg["paths"].get("cot_dataset", "data/external_frontiers/cot_positioning_normalized.csv")
    p = root / rel
    if not p.exists():
        raise FileNotFoundError(f"COT dataset not found: {p}")
    df = pd.read_csv(p)
    report_col = first_existing_col(df, COT_DATE_COLS)
    if report_col is None:
        raise ValueError(f"No COT report date column found. Columns sample={list(df.columns)[:40]}")
    available_col = first_existing_col(df, COT_AVAILABLE_COLS)
    if available_col is not None:
        df["_cot_available_date"] = pd.to_datetime(df[available_col], errors="coerce", utc=True).dt.tz_convert(None).dt.normalize()
    else:
        # COT is normally released after report date. Use a conservative Friday + 1 calendar day proxy
        # when the normalized dataset lacks a dedicated availability column.
        report_dt = pd.to_datetime(df[report_col], errors="coerce", utc=True).dt.tz_convert(None).dt.normalize()
        df["_cot_available_date"] = report_dt + pd.Timedelta(days=4)
    df["_cot_report_date"] = pd.to_datetime(df[report_col], errors="coerce", utc=True).dt.tz_convert(None).dt.normalize()
    for old, new in COT_ALIAS_MAP.items():
        if old in df.columns and new not in df.columns:
            df[new] = df[old]
    for c in df.columns:
        if c.startswith("_"):
            continue
        df[c] = safe_to_numeric(df[c])
    df = df.dropna(subset=["_cot_available_date"]).sort_values("_cot_available_date").drop_duplicates("_cot_available_date", keep="last")
    meta = {
        "path": str(p),
        "rows": int(len(df)),
        "report_date_col": str(report_col),
        "available_col": str(available_col) if available_col else None,
        "min_report_date_utc": df["_cot_report_date"].min().date().isoformat() if len(df) else None,
        "max_report_date_utc": df["_cot_report_date"].max().date().isoformat() if len(df) else None,
        "zscore_non_null": int(df.get("cot_mm_net_z", pd.Series(dtype=float)).notna().sum()) if "cot_mm_net_z" in df else 0,
        "change_non_null": int(df.get("cot_mm_net_z_change_4w", pd.Series(dtype=float)).notna().sum()) if "cot_mm_net_z_change_4w" in df else 0,
        "sha256": sha256_file(p),
    }
    return df, meta


def build_joined(root: Path, cfg: Dict[str, Any]) -> Tuple[pd.DataFrame, Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    macro, macro_meta = load_macro(root, cfg)
    cot, cot_meta = load_cot(root, cfg)
    joined = pd.merge_asof(
        macro.sort_values("_date"),
        cot.sort_values("_cot_available_date"),
        left_on="_date",
        right_on="_cot_available_date",
        direction="backward",
        suffixes=("", "_cot"),
    )
    lookahead = int((joined["_cot_available_date"].notna() & (joined["_cot_available_date"] > joined["_date"])).sum())
    join_meta = {
        "joined_rows": int(len(joined)),
        "joined_cot_available_rows": int(joined["_cot_available_date"].notna().sum()),
        "lookahead_violations": lookahead,
    }
    return joined, macro_meta, cot_meta, join_meta


COND_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*(<=|>=|<|>|==)\s*(-?\d+(?:\.\d+)?)\s*$")


def evaluate_condition_text(df: pd.DataFrame, condition_text: str) -> Tuple[pd.Series, List[str]]:
    if not condition_text or not isinstance(condition_text, str):
        return pd.Series(False, index=df.index), ["EMPTY_CONDITION_TEXT"]
    parts = [p.strip() for p in condition_text.split("AND") if p.strip()]
    active = pd.Series(True, index=df.index)
    missing: List[str] = []
    for part in parts:
        m = COND_RE.match(part)
        if not m:
            active &= False
            missing.append(f"UNPARSED:{part}")
            continue
        col, op, thr_s = m.group(1), m.group(2), m.group(3)
        thr = float(thr_s)
        if col not in df.columns:
            active &= False
            missing.append(col)
            continue
        s = pd.to_numeric(df[col], errors="coerce")
        if op == "<":
            cond = s < thr
        elif op == ">":
            cond = s > thr
        elif op == "<=":
            cond = s <= thr
        elif op == ">=":
            cond = s >= thr
        elif op == "==":
            cond = s == thr
        else:
            cond = pd.Series(False, index=df.index)
        active &= cond.fillna(False)
    return active.fillna(False), sorted(set(missing))


def read_csv_if_exists(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def boolish(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if pd.isna(v):
        return False
    return str(v).strip().lower() in {"true", "1", "yes", "y"}


def fnum(row: pd.Series, col: str, default: float = math.nan) -> float:
    try:
        v = row.get(col, default)
        if pd.isna(v):
            return default
        return float(v)
    except Exception:
        return default


def inum(row: pd.Series, col: str, default: int = 0) -> int:
    try:
        v = row.get(col, default)
        if pd.isna(v):
            return default
        return int(float(v))
    except Exception:
        return default


def audit_candidate(row: pd.Series, recomputed: Dict[str, Any], constraints: Dict[str, Any]) -> Tuple[bool, List[str], float]:
    fails: List[str] = []

    total_entries = inum(row, "total_entry_count")
    total_mean = fnum(row, "total_mean_net_bps")
    total_win = fnum(row, "total_win_rate")
    worst = fnum(row, "total_min_net_return_bps")
    locked_entries = inum(row, "locked_forward_entry_count")
    locked_mean = fnum(row, "locked_forward_mean_net_bps")
    final_entries = inum(row, "final_holdout_entry_count")
    final_mean = fnum(row, "final_holdout_mean_net_bps")
    post_entries = inum(row, "post_asof_entry_count")
    post_mean = fnum(row, "post_asof_mean_net_bps")
    max_year_share = fnum(row, "max_year_entry_share")
    missing_req = inum(row, "missing_required_feature_rows")
    lookahead = inum(row, "lookahead_violations")
    discovery_pass = boolish(row.get("pass_second_order_discovery_candidate", True))
    recomputed_incremental = int(recomputed.get("incremental_union_active_days", 0))
    recomputed_overlap = float(recomputed.get("overlap_with_current_union_pct", 100.0))
    active_days = int(recomputed.get("candidate_active_days", 0))

    if not discovery_pass:
        fails.append("DISCOVERY_PASS_FALSE")
    if total_entries < constraints["min_total_entries"]:
        fails.append("TOTAL_ENTRIES_TOO_LOW")
    if total_mean < constraints["min_total_mean_net_bps"]:
        fails.append("TOTAL_MEAN_TOO_LOW")
    if total_win < constraints["min_total_win_rate"]:
        fails.append("WIN_RATE_TOO_LOW")
    if abs(worst) > constraints["max_abs_worst_loss_bps"]:
        fails.append("WORST_LOSS_TOO_LARGE")
    if locked_entries < constraints["min_locked_forward_entries"]:
        fails.append("LOCKED_FORWARD_ENTRIES_TOO_LOW")
    if locked_mean < constraints["min_locked_forward_mean_bps"]:
        fails.append("LOCKED_FORWARD_MEAN_TOO_LOW")
    if final_entries < constraints["min_final_holdout_entries"]:
        fails.append("FINAL_HOLDOUT_ENTRIES_TOO_LOW")
    if final_mean < constraints["min_final_holdout_mean_bps"]:
        fails.append("FINAL_HOLDOUT_MEAN_TOO_LOW")
    if post_entries < constraints["min_post_asof_entries"]:
        fails.append("POST_ASOF_ENTRIES_TOO_LOW")
    if post_mean < constraints["min_post_asof_mean_bps"]:
        fails.append("POST_ASOF_MEAN_TOO_LOW")
    if max_year_share > constraints["max_year_entry_share"]:
        fails.append("YEAR_CONCENTRATION_TOO_HIGH")
    if missing_req > constraints["max_missing_required_feature_rows"]:
        fails.append("MISSING_REQUIRED_FEATURE_ROWS")
    if lookahead > constraints["max_lookahead_violations"]:
        fails.append("LOOKAHEAD_VIOLATIONS")
    if active_days < constraints["min_candidate_active_days"]:
        fails.append("ACTIVE_DAYS_TOO_LOW")
    if recomputed_incremental < constraints["min_incremental_union_active_days_recomputed"]:
        fails.append("RECOMPUTED_INCREMENTAL_DAYS_TOO_LOW")
    if recomputed_overlap > constraints["max_overlap_with_current_pct_recomputed"]:
        fails.append("RECOMPUTED_OVERLAP_TOO_HIGH")

    score = (
        max(total_mean, -1000) * 1.0
        + max(final_mean, -1000) * 1.5
        + max(post_mean, -1000) * 1.5
        + max(locked_mean, -1000) * 0.7
        + recomputed_incremental * 1.2
        - max(0.0, recomputed_overlap - 50.0) * 10.0
        - max(0.0, abs(worst) - 1000.0) * 0.4
    )
    return len(fails) == 0, fails, round(float(score), 4)


def recompute_portfolio_contribution(joined: pd.DataFrame, candidate_condition_text: str) -> Dict[str, Any]:
    current_active = pd.Series(False, index=joined.index)
    current_rule_stats = []
    for r in CURRENT_UNIFIED_RULES:
        active, missing = evaluate_condition_text(joined, r["condition_text"])
        current_active |= active
        current_rule_stats.append({
            "rule_id": r["rule_id"],
            "short_id": r["short_id"],
            "active_days": int(active.sum()),
            "missing_columns": "|".join(missing),
        })
    candidate_active, candidate_missing = evaluate_condition_text(joined, candidate_condition_text)
    overlap_days = int((candidate_active & current_active).sum())
    candidate_days = int(candidate_active.sum())
    current_days = int(current_active.sum())
    after_days = int((current_active | candidate_active).sum())
    incremental = after_days - current_days
    overlap_pct = round(100.0 * overlap_days / candidate_days, 4) if candidate_days else 100.0
    return {
        "candidate_active_days": candidate_days,
        "current_union_active_days_recomputed": current_days,
        "current_union_active_days_after_candidate_recomputed": after_days,
        "incremental_union_active_days": incremental,
        "overlap_with_current_union_days_recomputed": overlap_days,
        "overlap_with_current_union_pct": overlap_pct,
        "candidate_missing_columns_recomputed": "|".join(candidate_missing),
        "current_rule_stats": current_rule_stats,
    }


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", default="configs/stage106_second_order_cot_macro_hard_audit.json")
    ap.add_argument("--out", default="reports/stage106_second_order_cot_macro_hard_audit")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    cfg = load_config(root, Path(args.config))
    out = Path(args.out)
    if not out.is_absolute():
        out = root / out
    out.mkdir(parents=True, exist_ok=True)

    stage105_summary_path = root / cfg["paths"].get(
        "stage105_summary",
        "reports/stage105_second_order_cot_macro_thesis_discovery/stage105_second_order_cot_macro_thesis_discovery_summary.json",
    )
    stage105_metrics_path = root / cfg["paths"].get(
        "stage105_candidate_metrics",
        "reports/stage105_second_order_cot_macro_thesis_discovery/stage105_second_order_cot_macro_candidate_metrics.csv",
    )
    stage105_shortlist_path = root / cfg["paths"].get(
        "stage105_shortlist",
        "reports/stage105_second_order_cot_macro_thesis_discovery/stage105_second_order_cot_macro_shortlist.csv",
    )

    if not stage105_summary_path.exists():
        raise FileNotFoundError(f"Stage105 summary not found: {stage105_summary_path}")
    stage105_summary = read_json(stage105_summary_path)
    metrics = read_csv_if_exists(stage105_metrics_path)
    shortlist = read_csv_if_exists(stage105_shortlist_path)

    joined, macro_meta, cot_meta, join_meta = build_joined(root, cfg)
    constraints = {
        "min_total_entries": 10,
        "min_total_mean_net_bps": 250.0,
        "min_total_win_rate": 0.55,
        "max_abs_worst_loss_bps": 2200.0,
        "min_locked_forward_entries": 2,
        "min_locked_forward_mean_bps": 300.0,
        "min_final_holdout_entries": 2,
        "min_final_holdout_mean_bps": 1200.0,
        "min_post_asof_entries": 2,
        "min_post_asof_mean_bps": 1200.0,
        "max_year_entry_share": 0.30,
        "max_missing_required_feature_rows": 0,
        "max_lookahead_violations": 0,
        "min_candidate_active_days": 150,
        "min_incremental_union_active_days_recomputed": 150,
        "max_overlap_with_current_pct_recomputed": 80.0,
    }
    constraints.update(cfg.get("constraints", {}))

    if shortlist.empty:
        selected = pd.DataFrame()
        audit_rows: List[Dict[str, Any]] = []
    else:
        audit_rows = []
        for _, row in shortlist.iterrows():
            recomputed = recompute_portfolio_contribution(joined, str(row.get("condition_text", "")))
            passed, fails, score = audit_candidate(row, recomputed, constraints)
            d = row.to_dict()
            d.update({
                "candidate_active_days_recomputed": recomputed["candidate_active_days"],
                "current_union_active_days_recomputed": recomputed["current_union_active_days_recomputed"],
                "current_union_active_days_after_candidate_recomputed": recomputed["current_union_active_days_after_candidate_recomputed"],
                "incremental_union_active_days_recomputed": recomputed["incremental_union_active_days"],
                "overlap_with_current_union_days_recomputed": recomputed["overlap_with_current_union_days_recomputed"],
                "overlap_with_current_union_pct_recomputed": recomputed["overlap_with_current_union_pct"],
                "candidate_missing_columns_recomputed": recomputed["candidate_missing_columns_recomputed"],
                "pass_second_order_hard_audit_candidate": bool(passed),
                "hard_fail_reasons": "|".join(fails),
                "second_order_hard_audit_score": score,
            })
            audit_rows.append(d)
        audit_rows = sorted(audit_rows, key=lambda x: x.get("second_order_hard_audit_score", -1e9), reverse=True)
        max_selected = int(cfg.get("max_selected", 2))
        selected_rows = [r for r in audit_rows if r["pass_second_order_hard_audit_candidate"]][:max_selected]
        selected = pd.DataFrame(selected_rows)

    audit_df = pd.DataFrame(audit_rows)
    audit_csv = out / "stage106_second_order_cot_macro_hard_audit_metrics.csv"
    selected_csv = out / "stage106_selected_for_stage107.csv"
    audit_df.to_csv(audit_csv, index=False)
    selected.to_csv(selected_csv, index=False)

    selected_rule_ids = selected["rule_id"].tolist() if not selected.empty and "rule_id" in selected.columns else []
    pass_count = int(audit_df.get("pass_second_order_hard_audit_candidate", pd.Series(dtype=bool)).fillna(False).sum()) if not audit_df.empty else 0
    if selected_rule_ids:
        decision = "STAGE106_SECOND_ORDER_HARD_AUDIT_READY_FOR_PORTFOLIO_REVIEW_NO_ORDER"
        classification = "S106_SECOND_ORDER_HARD_AUDIT_SHORTLIST_READY"
        disposition = "SECOND_ORDER_COT_MACRO_READY_FOR_STAGE107_PORTFOLIO_REVIEW"
    else:
        decision = "STAGE106_NO_SECOND_ORDER_SURVIVOR_NO_ORDER"
        classification = "S106_NO_SECOND_ORDER_SURVIVOR"
        disposition = "KEEP_STAGE100_UNIFIED_OBSERVER_ONLY"

    issues = []
    if join_meta["lookahead_violations"] > 0:
        issues.append(f"LOOKAHEAD_VIOLATIONS:{join_meta['lookahead_violations']}")
    if stage105_summary.get("current_union_active_days") and not audit_df.empty:
        old_union = int(stage105_summary.get("current_union_active_days") or 0)
        new_union = int(audit_df.iloc[0].get("current_union_active_days_recomputed", 0))
        if old_union and new_union and old_union != new_union:
            issues.append(f"STAGE105_UNION_RECOMPUTED_DIFFERENCE:{old_union}->{new_union}")

    summary = {
        "stage": STAGE,
        "root": str(root),
        "config": str(Path(args.config).resolve() if Path(args.config).exists() else args.config),
        "status": "STAGE106_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
        "principle": "Hard-audit Stage105 second-order COT/macro shortlist with stricter gates and recomputed 6-rule unified portfolio overlap. No order, broker, MT5, EA, paper-live, or live change.",
        "stage105_reference": {
            "path": str(stage105_summary_path),
            "exists": stage105_summary_path.exists(),
            "decision": stage105_summary.get("decision"),
            "shortlist_rule_ids": stage105_summary.get("shortlist_rule_ids", []),
            "reported_current_union_active_days": stage105_summary.get("current_union_active_days"),
        },
        "macro_dataset": macro_meta,
        "cot_dataset": cot_meta,
        "data_join": join_meta,
        "current_unified_portfolio_rule_ids": [r["rule_id"] for r in CURRENT_UNIFIED_RULES],
        "stage105_shortlist_count": int(len(shortlist)),
        "candidate_count": int(len(audit_df)),
        "pass_hard_audit_count": pass_count,
        "selected_count": int(len(selected_rule_ids)),
        "selected_rule_ids": selected_rule_ids,
        "selected_for_stage107": selected.to_dict(orient="records") if not selected.empty else [],
        "constraints": constraints,
        "issues": issues,
        "hard_blocks": [
            "NO_AUTOMATED_ORDER",
            "NO_PAPER_ORDER",
            "NO_BROKER_CONNECTION",
            "NO_EA_PROMOTION",
            "NO_MT5_OR_EA_CHANGE",
            "NO_PAPER_LIVE",
            "NO_LIVE",
            "NO_ORDER_AUTHORIZATION_FROM_STAGE106",
            "NO_THRESHOLD_TUNING_FROM_STAGE106_HARD_AUDIT",
        ],
        "outputs": {
            "summary_json": str(out / "stage106_second_order_cot_macro_hard_audit_summary.json"),
            "report_md": str(out / "stage106_second_order_cot_macro_hard_audit_report.md"),
            "audit_metrics_csv": str(audit_csv),
            "selected_csv": str(selected_csv),
        },
    }
    write_json(out / "stage106_second_order_cot_macro_hard_audit_summary.json", summary)

    lines = [
        "# Stage106 Second-Order COT/Macro Hard Audit",
        "",
        "## Decision",
        f"- status: `{summary['status']}`",
        f"- decision: `{decision}`",
        f"- classification: `{classification}`",
        f"- disposition: `{disposition}`",
        "",
        "## Selected for Stage107",
        f"- selected_rule_ids: `{', '.join(selected_rule_ids)}`" if selected_rule_ids else "- selected_rule_ids: ``",
        "",
        "## Recomputed unified portfolio",
        f"- current rules: `{len(CURRENT_UNIFIED_RULES)}`",
        f"- join lookahead violations: `{join_meta['lookahead_violations']}`",
        "",
        "## Issues",
    ]
    if issues:
        for issue in issues:
            lines.append(f"- `{issue}`")
    else:
        lines.append("- none")
    lines += [
        "",
        "## Hard blocks",
    ] + [f"- `{b}`" for b in summary["hard_blocks"]]
    (out / "stage106_second_order_cot_macro_hard_audit_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({
        "status": summary["status"],
        "decision": decision,
        "selected_rule_ids": selected_rule_ids,
        "issues": issues,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
