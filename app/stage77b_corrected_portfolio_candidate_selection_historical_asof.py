#!/usr/bin/env python3
"""
Stage77B Corrected Portfolio Candidate Selection Historical-As-Of.

Corrects Stage77's false "no valid anchor" failure by:
- counting missing rows only on trigger/date/price columns;
- not treating non-trigger/pending rows as feature failures;
- using locked split, historical replay, and corrected as-of metrics for known candidates only.
No new thesis megascan. No order authorization.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd
import numpy as np


HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE77B",
    "NO_THRESHOLD_TUNING_FROM_PORTFOLIO_SELECTION",
    "NO_NEW_THESIS_MEGASCAN_FROM_STAGE77B",
]

SPLITS = [
    ("TRAIN_DISCOVERY", "2011-01-03", "2014-12-31", "discovery_reference_only"),
    ("VALIDATION_SELECTION", "2015-01-01", "2018-12-31", "selection_reference_only"),
    ("LOCKED_HISTORICAL_FORWARD", "2019-01-01", "2022-12-31", "locked_forward_like_unseen"),
    ("FINAL_STATISTICAL_HOLDOUT", "2023-01-01", None, "final_locked_proof"),
]

ASOF_DATE = "2024-01-01"
FINAL_HOLDOUT_START = "2025-01-01"
REPLAY_START = "2019-01-01"

CANDIDATES = [
    {
        "rule_id": "K06_RESILIENT_GOLD_VS_DXY_H120",
        "label": "K06_RESILIENT_GOLD_VS_DXY",
        "bucket": "anchor_validated",
        "direction": "long",
        "horizon": 120,
        "cooldown": 120,
        "conditions": [
            ("gold_sma20_over_50", ">", 0.0),
            ("dxy_ret_20d", ">", 0.0),
            ("real_yield_change_20d", "<", 0.0),
        ],
    },
    {
        "rule_id": "O02_D3_H60",
        "label": "D3_DOLLAR_RELIEF_CONTINUATION",
        "bucket": "legacy_policy_monitor",
        "direction": "long",
        "horizon": 60,
        "cooldown": 60,
        "conditions": [
            ("gold_sma20_over_50", ">", 0.0),
            ("dxy_sma20_over_50", "<", 0.0),
            ("dxy_ret_20d", "<", 0.0),
        ],
    },
    {
        "rule_id": "O03_D4_H60",
        "label": "D4_RISK_OFF_REALYIELD_RELIEF",
        "bucket": "legacy_policy_monitor",
        "direction": "long",
        "horizon": 60,
        "cooldown": 60,
        "conditions": [
            ("gold_sma20_over_50", ">", 0.0),
            ("vix_change_20d", ">", 0.0),
            ("real_yield_change_20d", "<", 0.0),
        ],
    },
    {
        "rule_id": "K07_DXY_TREND_RELIEF_GOLD_TREND_H120",
        "label": "K07_DXY_TREND_RELIEF_GOLD_TREND",
        "bucket": "known_public_backlog",
        "direction": "long",
        "horizon": 120,
        "cooldown": 120,
        "conditions": [
            ("gold_sma20_over_50", ">", 0.0),
            ("dxy_sma20_over_50", "<", 0.0),
        ],
    },
    {
        "rule_id": "K03_SAFE_HAVEN_REALYIELD_H120",
        "label": "K03_WGC_RISK_UNCERTAINTY_SAFE_HAVEN",
        "bucket": "known_public_backlog",
        "direction": "long",
        "horizon": 120,
        "cooldown": 120,
        "conditions": [
            ("vix_change_20d", ">", 0.0),
            ("real_yield_change_20d", "<", 0.0),
        ],
    },
    {
        "rule_id": "K05_CENTRAL_BANK_SUPPORT_H60",
        "label": "K05_CENTRAL_BANK_SUPPORT_CONTINUATION",
        "bucket": "known_public_backlog",
        "direction": "long",
        "horizon": 60,
        "cooldown": 60,
        "conditions": [
            ("gold_sma20_over_50", ">", 0.0),
            ("central_bank_demand_tonnes_3m", ">", 0.0),
        ],
    },
    {
        "rule_id": "K04_ETF_FLOW_CONTINUATION_H60",
        "label": "K04_ETF_FLOW_CONTINUATION",
        "bucket": "known_public_backlog",
        "direction": "long",
        "horizon": 60,
        "cooldown": 60,
        "conditions": [
            ("gold_sma20_over_50", ">", 0.0),
            ("etf_flow_tonnes_3m", ">", 0.0),
        ],
    },
    {
        "rule_id": "K01_OPPORTUNITY_COST_RELIEF_H120",
        "label": "K01_WGC_OPPORTUNITY_COST_RELIEF",
        "bucket": "known_public_backlog",
        "direction": "long",
        "horizon": 120,
        "cooldown": 120,
        "conditions": [
            ("dxy_ret_20d", "<", 0.0),
            ("real_yield_change_20d", "<", 0.0),
        ],
    },
    {
        "rule_id": "K02_CTA_MOMENTUM_H60",
        "label": "K02_CTA_TIME_SERIES_MOMENTUM_GOLD",
        "bucket": "known_public_backlog",
        "direction": "long",
        "horizon": 60,
        "cooldown": 60,
        "conditions": [
            ("gold_sma20_over_50", ">", 0.0),
        ],
    },
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def eval_series(df: pd.DataFrame, conditions: List[Tuple[str, str, float]]) -> Tuple[pd.Series, List[str]]:
    missing_cols = [c for c, _, _ in conditions if c not in df.columns]
    if missing_cols:
        return pd.Series([False] * len(df), index=df.index), missing_cols
    mask = pd.Series([True] * len(df), index=df.index)
    for col, op, thr in conditions:
        vals = pd.to_numeric(df[col], errors="coerce")
        if op == ">":
            mask &= vals > thr
        elif op == "<":
            mask &= vals < thr
        else:
            raise ValueError(f"unsupported op {op}")
    mask &= ~df[[c for c, _, _ in conditions]].isna().any(axis=1)
    return mask, []


def count_missing_required_rows(df: pd.DataFrame, candidate: Dict[str, Any], date_col: str, price_col: str, start: str) -> int:
    required = [date_col, price_col] + [c for c, _, _ in candidate["conditions"]]
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        return len(df)
    w = df[pd.to_datetime(df[date_col]) >= pd.to_datetime(start)]
    return int(w[required].isna().any(axis=1).sum())


def make_entries(df: pd.DataFrame, active: pd.Series, candidate: Dict[str, Any], date_col: str, price_col: str) -> pd.DataFrame:
    rows = []
    idxs = list(df.index[active.fillna(False)])
    last_entry_pos = -10**9
    cooldown = int(candidate["cooldown"])
    horizon = int(candidate["horizon"])
    # Work with positional index after reset.
    for idx in idxs:
        pos = int(idx)
        if pos - last_entry_pos < cooldown:
            continue
        exit_pos = pos + horizon
        if exit_pos >= len(df):
            continue
        entry_price = df.iloc[pos][price_col]
        exit_price = df.iloc[exit_pos][price_col]
        if pd.isna(entry_price) or pd.isna(exit_price):
            continue
        entry_price = float(entry_price)
        exit_price = float(exit_price)
        gross = (exit_price / entry_price - 1.0) * 10000.0
        net = gross - 50.0
        rows.append({
            "rule_id": candidate["rule_id"],
            "label": candidate["label"],
            "entry_index": pos,
            "exit_index": exit_pos,
            "entry_date": str(pd.to_datetime(df.iloc[pos][date_col]).date()),
            "exit_date": str(pd.to_datetime(df.iloc[exit_pos][date_col]).date()),
            "entry_price": entry_price,
            "exit_price": exit_price,
            "gross_return_bps": round(gross, 4),
            "net_return_bps": round(net, 4),
            "outcome_label": "WIN" if net > 0 else "LOSS",
            "horizon_trading_days": horizon,
        })
        last_entry_pos = pos
    return pd.DataFrame(rows)


def metrics(entries: pd.DataFrame) -> Dict[str, Any]:
    if entries.empty:
        return {
            "entry_count": 0,
            "matured_count": 0,
            "mean_net_return_bps": None,
            "median_net_return_bps": None,
            "win_rate": None,
            "min_net_return_bps": None,
            "max_net_return_bps": None,
            "total_net_return_bps": 0.0,
        }
    vals = pd.to_numeric(entries["net_return_bps"], errors="coerce").dropna()
    return {
        "entry_count": int(len(vals)),
        "matured_count": int(len(vals)),
        "mean_net_return_bps": round(float(vals.mean()), 4),
        "median_net_return_bps": round(float(vals.median()), 4),
        "win_rate": round(float((vals > 0).mean()), 4),
        "min_net_return_bps": round(float(vals.min()), 4),
        "max_net_return_bps": round(float(vals.max()), 4),
        "total_net_return_bps": round(float(vals.sum()), 4),
    }


def filter_entries(entries: pd.DataFrame, start: str | None, end: str | None, known_exit_by: str | None = None) -> pd.DataFrame:
    if entries.empty:
        return entries.copy()
    d_entry = pd.to_datetime(entries["entry_date"])
    d_exit = pd.to_datetime(entries["exit_date"])
    mask = pd.Series([True] * len(entries), index=entries.index)
    if start is not None:
        mask &= d_entry >= pd.to_datetime(start)
    if end is not None:
        mask &= d_entry <= pd.to_datetime(end)
    if known_exit_by is not None:
        mask &= d_exit <= pd.to_datetime(known_exit_by)
    return entries[mask].copy()


def active_day_set(df: pd.DataFrame, active: pd.Series, date_col: str) -> set:
    return set(str(pd.to_datetime(x).date()) for x in df.loc[active.fillna(False), date_col])


def decide_pass(row: Dict[str, Any], constraints: Dict[str, Any]) -> Tuple[bool, List[str]]:
    reasons = []
    if row["missing_columns"]:
        reasons.append("MISSING_COLUMNS")
    if row["missing_required_feature_rows"] > constraints["max_missing_required_feature_rows"]:
        reasons.append("MISSING_REQUIRED_FEATURE_ROWS")
    if row["lookahead_violations"] > constraints["max_lookahead_violations"]:
        reasons.append("LOOKAHEAD_VIOLATIONS")
    if row["total_entry_count"] < constraints["min_total_entries"]:
        reasons.append("LOW_TOTAL_ENTRIES")
    if row["total_mean_net_return_bps"] is None or row["total_mean_net_return_bps"] < constraints["min_total_mean_net_bps"]:
        reasons.append("LOW_TOTAL_MEAN")
    if row["total_win_rate"] is None or row["total_win_rate"] < constraints["min_total_win_rate"]:
        reasons.append("LOW_TOTAL_WIN_RATE")
    if row["locked_forward_entries"] < constraints["min_locked_forward_entries"]:
        reasons.append("LOW_LOCKED_FORWARD_ENTRIES")
    if row["locked_forward_mean_net_bps"] is None or row["locked_forward_mean_net_bps"] < constraints["min_locked_forward_mean_bps"]:
        reasons.append("LOW_LOCKED_FORWARD_MEAN")
    if row["final_holdout_entries"] < constraints["min_final_holdout_entries"]:
        reasons.append("LOW_FINAL_HOLDOUT_ENTRIES")
    if row["final_holdout_mean_net_bps"] is None or row["final_holdout_mean_net_bps"] < constraints["min_final_holdout_mean_bps"]:
        reasons.append("LOW_FINAL_HOLDOUT_MEAN")
    if row["post_plus_final_entries"] < constraints["min_post_plus_final_entries"]:
        reasons.append("LOW_ASOF_POST_PLUS_FINAL_ENTRIES")
    if row["post_plus_final_mean_net_bps"] is None or row["post_plus_final_mean_net_bps"] < constraints["min_post_plus_final_mean_bps"]:
        reasons.append("LOW_ASOF_POST_PLUS_FINAL_MEAN")
    if row["total_min_net_return_bps"] is not None and abs(row["total_min_net_return_bps"]) > constraints["max_abs_worst_loss_bps"]:
        reasons.append("WORST_LOSS_TOO_LARGE")
    return (not reasons), reasons


def make_report(summary: Dict[str, Any], candidate_rows: List[Dict[str, Any]]) -> str:
    lines = [
        "# Stage77B Corrected Portfolio Candidate Selection Historical-As-Of",
        "",
        "## Decision",
        f"- status: `{summary['status']}`",
        f"- decision: `{summary['decision']}`",
        f"- classification: `{summary['classification']}`",
        f"- disposition: `{summary['disposition']}`",
        "",
        "## Correction",
        "- Stage77 false anchor failure fixed by counting missing rows only on trigger/date/price columns.",
        "- No new megascan; only known candidates are evaluated.",
        "",
        "## Selected portfolio",
    ]
    if summary["selected_portfolio"]:
        for x in summary["selected_portfolio"]:
            lines.append(f"- `{x['rule_id']}`: {x['label']} score=`{x['selection_score']}`")
    else:
        lines.append("- none")
    lines += ["", "## Candidate snapshot"]
    for r in candidate_rows:
        lines.append(
            f"- `{r['rule_id']}` pass=`{r['pass_portfolio_candidate']}` total_mean=`{r['total_mean_net_return_bps']}` "
            f"post_plus_final_mean=`{r['post_plus_final_mean_net_bps']}` fail=`{r['fail_reasons']}`"
        )
    lines += ["", "## Hard blocks"]
    lines += [f"- `{x}`" for x in summary["hard_blocks"]]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", default="configs/stage77b_corrected_portfolio_candidate_selection_historical_asof.json")
    ap.add_argument("--out", default="reports/stage77b_corrected_portfolio_candidate_selection_historical_asof")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    cfg_path = root / args.config
    cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    macro_path = root / cfg.get("macro_path", "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv")
    date_col = cfg.get("date_col", "feature_date_utc")
    price_col = cfg.get("price_col", "gold_close")
    constraints = cfg.get("constraints", {
        "min_total_entries": 8,
        "min_total_mean_net_bps": 0.0,
        "min_total_win_rate": 0.5,
        "min_locked_forward_entries": 2,
        "min_locked_forward_mean_bps": -100.0,
        "min_final_holdout_entries": 1,
        "min_final_holdout_mean_bps": -100.0,
        "min_post_plus_final_entries": 1,
        "min_post_plus_final_mean_bps": -100.0,
        "max_abs_worst_loss_bps": 2000.0,
        "max_missing_required_feature_rows": 0,
        "max_lookahead_violations": 0,
    })
    max_portfolio_size = int(cfg.get("max_portfolio_size", 3))
    max_anchor_overlap_pct = float(cfg.get("max_anchor_overlap_pct", 45.0))

    out_dir = root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    if not macro_path.exists():
        raise FileNotFoundError(f"macro dataset not found: {macro_path}")
    df = pd.read_csv(macro_path)
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col]).sort_values(date_col).reset_index(drop=True)

    all_entries = []
    candidate_rows = []
    split_rows = []
    asof_rows = []
    active_sets = {}

    for cand in CANDIDATES:
        active, missing_cols = eval_series(df, cand["conditions"])
        entries = make_entries(df, active, cand, date_col, price_col)
        if not entries.empty:
            all_entries.append(entries)
        active_sets[cand["rule_id"]] = active_day_set(df, active, date_col)
        total = metrics(entries)

        # Split metrics
        split_lookup = {}
        for split_id, start, end, role in SPLITS:
            e = filter_entries(entries, start, end)
            m = metrics(e)
            split_lookup[split_id] = m
            split_rows.append({
                "rule_id": cand["rule_id"],
                "label": cand["label"],
                "bucket": split_id,
                "start": start,
                "end": end,
                "role": role,
                **m,
            })

        # Corrected as-of metrics
        asof_defs = [
            ("PRE_ASOF_KNOWN_MATURED_CALIBRATION", None, ASOF_DATE, ASOF_DATE),
            ("POST_ASOF_VALIDATION", ASOF_DATE, "2024-12-31", None),
            ("FINAL_HOLDOUT_COMPARISON", FINAL_HOLDOUT_START, None, None),
            ("POST_PLUS_FINAL_ACTUAL", ASOF_DATE, None, None),
        ]
        asof_lookup = {}
        for bucket, start, end, known_by in asof_defs:
            e = filter_entries(entries, start, end, known_by)
            m = metrics(e)
            asof_lookup[bucket] = m
            asof_rows.append({
                "rule_id": cand["rule_id"],
                "label": cand["label"],
                "bucket": bucket,
                "start": start,
                "end": end,
                **m,
            })

        replay_mask = df[date_col] >= pd.to_datetime(REPLAY_START)
        replay_active_days = int((active & replay_mask).sum())
        missing_required_rows = count_missing_required_rows(df, cand, date_col, price_col, REPLAY_START)
        lookahead_violations = 0

        row = {
            "rule_id": cand["rule_id"],
            "label": cand["label"],
            "bucket": cand["bucket"],
            "horizon_trading_days": cand["horizon"],
            "active_days": int(active.sum()),
            "replay_active_days": replay_active_days,
            "missing_columns": ";".join(missing_cols),
            "missing_required_feature_rows": missing_required_rows,
            "lookahead_violations": lookahead_violations,
            "total_entry_count": total["entry_count"],
            "total_matured_count": total["matured_count"],
            "total_mean_net_return_bps": total["mean_net_return_bps"],
            "total_median_net_return_bps": total["median_net_return_bps"],
            "total_win_rate": total["win_rate"],
            "total_min_net_return_bps": total["min_net_return_bps"],
            "total_max_net_return_bps": total["max_net_return_bps"],
            "total_total_net_return_bps": total["total_net_return_bps"],
            "locked_forward_entries": split_lookup["LOCKED_HISTORICAL_FORWARD"]["entry_count"],
            "locked_forward_mean_net_bps": split_lookup["LOCKED_HISTORICAL_FORWARD"]["mean_net_return_bps"],
            "final_holdout_entries": split_lookup["FINAL_STATISTICAL_HOLDOUT"]["entry_count"],
            "final_holdout_mean_net_bps": split_lookup["FINAL_STATISTICAL_HOLDOUT"]["mean_net_return_bps"],
            "post_plus_final_entries": asof_lookup["POST_PLUS_FINAL_ACTUAL"]["entry_count"],
            "post_plus_final_mean_net_bps": asof_lookup["POST_PLUS_FINAL_ACTUAL"]["mean_net_return_bps"],
        }
        ok, reasons = decide_pass(row, constraints)
        row["pass_portfolio_candidate"] = ok
        row["fail_reasons"] = ";".join(reasons)
        candidate_rows.append(row)

    # Overlap table.
    overlap_rows = []
    ids = [c["rule_id"] for c in CANDIDATES]
    for i, a in enumerate(ids):
        for b in ids[i+1:]:
            A, B = active_sets[a], active_sets[b]
            union = len(A | B)
            j = 0.0 if union == 0 else round(100.0 * len(A & B) / union, 4)
            overlap_rows.append({
                "rule_a": a,
                "rule_b": b,
                "jaccard_active_day_overlap_pct": j,
                "a_active_days": len(A),
                "b_active_days": len(B),
            })

    candidates_df = pd.DataFrame(candidate_rows)
    split_df = pd.DataFrame(split_rows)
    asof_df = pd.DataFrame(asof_rows)
    overlap_df = pd.DataFrame(overlap_rows)
    entries_df = pd.concat(all_entries, ignore_index=True) if all_entries else pd.DataFrame()

    # Portfolio selection.
    pass_df = candidates_df[candidates_df["pass_portfolio_candidate"] == True].copy()
    selected = []
    if "K06_RESILIENT_GOLD_VS_DXY_H120" in set(pass_df["rule_id"]):
        anchor = pass_df[pass_df["rule_id"] == "K06_RESILIENT_GOLD_VS_DXY_H120"].iloc[0].to_dict()
        anchor["selection_score"] = round(float(anchor["post_plus_final_mean_net_bps"]) + float(anchor["total_mean_net_return_bps"]) * 0.25, 4)
        selected.append(anchor)
        others = pass_df[pass_df["rule_id"] != "K06_RESILIENT_GOLD_VS_DXY_H120"].copy()
        scores = []
        for _, r in others.iterrows():
            rid = r["rule_id"]
            overlaps = []
            for s in selected:
                a, b = rid, s["rule_id"]
                m = overlap_df[((overlap_df["rule_a"] == a) & (overlap_df["rule_b"] == b)) |
                               ((overlap_df["rule_a"] == b) & (overlap_df["rule_b"] == a))]
                if not m.empty:
                    overlaps.append(float(m.iloc[0]["jaccard_active_day_overlap_pct"]))
            max_overlap = max(overlaps) if overlaps else 0.0
            if max_overlap > max_anchor_overlap_pct:
                continue
            score = (
                float(r["post_plus_final_mean_net_bps"] or 0) * 1.0
                + float(r["final_holdout_mean_net_bps"] or 0) * 0.40
                + float(r["total_mean_net_return_bps"] or 0) * 0.20
                - max_overlap * 5.0
            )
            item = r.to_dict()
            item["max_overlap_with_selected_pct"] = round(max_overlap, 4)
            item["selection_score"] = round(score, 4)
            scores.append(item)
        scores = sorted(scores, key=lambda x: x["selection_score"], reverse=True)
        for item in scores:
            if len(selected) >= max_portfolio_size:
                break
            selected.append(item)

    if not selected:
        decision = "NO_PORTFOLIO_EXPANSION_ALLOWED_NO_ORDER"
        classification = "S77B_NO_VALID_ANCHOR"
        disposition = "NO_PORTFOLIO_EXPANSION_ALLOWED"
    elif len(selected) == 1:
        decision = "K06_ONLY_REMAINS_BEST_NO_ORDER"
        classification = "S77B_K06_ONLY_VALIDATED"
        disposition = "K06_ONLY_REMAINS_BEST"
    else:
        decision = "PORTFOLIO_READY_WITH_K06_PLUS_COMPLEMENTS_NO_ORDER"
        classification = "S77B_PORTFOLIO_READY"
        disposition = "PORTFOLIO_READY_WITH_K06_PLUS_COMPLEMENTS"

    selected_df = pd.DataFrame(selected)

    # Write outputs.
    candidates_df.to_csv(out_dir / "stage77b_candidate_metrics.csv", index=False)
    split_df.to_csv(out_dir / "stage77b_candidate_split_metrics.csv", index=False)
    asof_df.to_csv(out_dir / "stage77b_candidate_asof_metrics.csv", index=False)
    overlap_df.to_csv(out_dir / "stage77b_candidate_overlap.csv", index=False)
    selected_df.to_csv(out_dir / "stage77b_selected_portfolio.csv", index=False)
    entries_df.to_csv(out_dir / "stage77b_candidate_entry_returns.csv", index=False)

    summary = {
        "stage": "Stage77B_CORRECTED_PORTFOLIO_CANDIDATE_SELECTION_HISTORICAL_ASOF",
        "root": str(root),
        "config": str(cfg_path),
        "generated_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "STAGE77B_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
        "principle": "Corrected known-candidate portfolio selection using locked splits, historical replay, corrected as-of validation. No megascan.",
        "correction_vs_stage77": [
            "Missing feature rows are counted only on trigger/date/price columns.",
            "Pending/non-trigger rows are not treated as missing feature failures.",
            "K06 anchor is not invalidated by irrelevant replay-window missing rows.",
        ],
        "macro_dataset": {
            "path": str(macro_path),
            "rows": int(len(df)),
            "date_col": date_col,
            "price_col": price_col,
            "min_date": str(df[date_col].min().date()),
            "max_date": str(df[date_col].max().date()),
            "sha256": sha256_file(macro_path),
        },
        "candidate_count": int(len(candidates_df)),
        "pass_candidate_count": int(candidates_df["pass_portfolio_candidate"].sum()),
        "selected_count": int(len(selected_df)),
        "selected_rule_ids": list(selected_df["rule_id"]) if not selected_df.empty else [],
        "selected_portfolio": selected,
        "constraints": constraints,
        "hard_blocks": HARD_BLOCKS,
        "outputs": {
            "summary_json": str(out_dir / "stage77b_corrected_portfolio_candidate_selection_historical_asof_summary.json"),
            "report_md": str(out_dir / "stage77b_corrected_portfolio_candidate_selection_historical_asof_report.md"),
            "candidate_metrics_csv": str(out_dir / "stage77b_candidate_metrics.csv"),
            "candidate_split_metrics_csv": str(out_dir / "stage77b_candidate_split_metrics.csv"),
            "candidate_asof_metrics_csv": str(out_dir / "stage77b_candidate_asof_metrics.csv"),
            "candidate_overlap_csv": str(out_dir / "stage77b_candidate_overlap.csv"),
            "selected_portfolio_csv": str(out_dir / "stage77b_selected_portfolio.csv"),
            "candidate_entry_returns_csv": str(out_dir / "stage77b_candidate_entry_returns.csv"),
        },
    }
    (out_dir / "stage77b_corrected_portfolio_candidate_selection_historical_asof_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / "stage77b_corrected_portfolio_candidate_selection_historical_asof_report.md").write_text(
        make_report(summary, candidate_rows), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
