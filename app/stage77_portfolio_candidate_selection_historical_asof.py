#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

SPLITS = [
    ("TRAIN_DISCOVERY", "2011-01-03", "2014-12-31", "discovery_reference_only"),
    ("VALIDATION_SELECTION", "2015-01-01", "2018-12-31", "selection_reference_only"),
    ("LOCKED_HISTORICAL_FORWARD", "2019-01-01", "2022-12-31", "locked_forward_like_unseen"),
    ("FINAL_STATISTICAL_HOLDOUT", "2023-01-01", None, "final_locked_proof"),
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Stage77 portfolio candidate selection with locked/as-of historical replay.")
    p.add_argument("--root", default=".")
    p.add_argument("--config", required=True)
    p.add_argument("--out", required=True)
    return p.parse_args()


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_date_col(df: pd.DataFrame, candidates: Sequence[str]) -> str:
    for c in candidates:
        if c in df.columns:
            return c
    raise ValueError(f"no date column found among {candidates}")


def op_eval(series: pd.Series, operator: str, threshold: float) -> pd.Series:
    if operator == ">":
        return series > threshold
    if operator == ">=":
        return series >= threshold
    if operator == "<":
        return series < threshold
    if operator == "<=":
        return series <= threshold
    if operator == "==":
        return series == threshold
    raise ValueError(f"unsupported operator {operator}")


def active_mask(df: pd.DataFrame, conditions: Sequence[Dict[str, Any]]) -> Tuple[pd.Series, List[str]]:
    mask = pd.Series(True, index=df.index)
    missing = []
    for cond in conditions:
        col = cond["column"]
        if col not in df.columns:
            missing.append(col)
            mask &= False
            continue
        values = pd.to_numeric(df[col], errors="coerce")
        mask &= values.notna()
        mask &= op_eval(values, cond["operator"], float(cond["threshold"]))
    return mask.fillna(False), missing


def compute_entries(df: pd.DataFrame, mask: pd.Series, horizon: int, price_col: str, cost_bps: float, rule_id: str) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    idxs = list(df.index[mask])
    last_entry_pos = -10**9
    pos_by_index = {idx: pos for pos, idx in enumerate(df.index)}
    for idx in idxs:
        pos = pos_by_index[idx]
        if pos - last_entry_pos < horizon:
            continue
        exit_pos = pos + horizon
        if exit_pos >= len(df):
            continue
        entry_price = float(df.iloc[pos][price_col])
        exit_price = float(df.iloc[exit_pos][price_col])
        if not (math.isfinite(entry_price) and math.isfinite(exit_price) and entry_price > 0):
            continue
        gross = (exit_price / entry_price - 1.0) * 10000.0
        net = gross - cost_bps
        rows.append({
            "rule_id": rule_id,
            "entry_date_utc": df.iloc[pos]["_date"].date().isoformat(),
            "exit_date_utc": df.iloc[exit_pos]["_date"].date().isoformat(),
            "entry_row_pos": pos,
            "exit_row_pos": exit_pos,
            "entry_price": round(entry_price, 6),
            "exit_price": round(exit_price, 6),
            "gross_return_bps": round(gross, 4),
            "net_return_bps": round(net, 4),
            "outcome_label": "WIN" if net > 0 else "LOSS",
        })
        last_entry_pos = pos
    return pd.DataFrame(rows)


def metric_block(entries: pd.DataFrame, label: str, start: Optional[str] = None, end: Optional[str] = None) -> Dict[str, Any]:
    if entries.empty:
        return {"bucket": label, "start": start, "end": end, "entry_count": 0, "matured_count": 0, "mean_net_return_bps": None, "median_net_return_bps": None, "win_rate": None, "min_net_return_bps": None, "max_net_return_bps": None, "total_net_return_bps": 0.0}
    x = pd.to_numeric(entries["net_return_bps"], errors="coerce").dropna()
    return {
        "bucket": label,
        "start": start,
        "end": end,
        "entry_count": int(len(x)),
        "matured_count": int(len(x)),
        "mean_net_return_bps": round(float(x.mean()), 4),
        "median_net_return_bps": round(float(x.median()), 4),
        "win_rate": round(float((x > 0).mean()), 4),
        "min_net_return_bps": round(float(x.min()), 4),
        "max_net_return_bps": round(float(x.max()), 4),
        "total_net_return_bps": round(float(x.sum()), 4),
    }


def entries_between(entries: pd.DataFrame, start: Optional[str], end: Optional[str]) -> pd.DataFrame:
    if entries.empty:
        return entries.copy()
    d = pd.to_datetime(entries["entry_date_utc"], utc=True).dt.tz_localize(None)
    mask = pd.Series(True, index=entries.index)
    if start:
        mask &= d >= pd.Timestamp(start)
    if end:
        mask &= d <= pd.Timestamp(end)
    return entries[mask].copy()


def entries_known_by_asof(entries: pd.DataFrame, as_of: str) -> pd.DataFrame:
    if entries.empty:
        return entries.copy()
    entry_d = pd.to_datetime(entries["entry_date_utc"], utc=True).dt.tz_localize(None)
    exit_d = pd.to_datetime(entries["exit_date_utc"], utc=True).dt.tz_localize(None)
    ts = pd.Timestamp(as_of)
    return entries[(entry_d < ts) & (exit_d <= ts)].copy()


def jaccard(mask_a: pd.Series, mask_b: pd.Series) -> float:
    a = set(mask_a.index[mask_a])
    b = set(mask_b.index[mask_b])
    if not a and not b:
        return 0.0
    return 100.0 * len(a & b) / len(a | b)


def passes_constraints(total: Dict[str, Any], split_map: Dict[str, Dict[str, Any]], asof_post_plus: Dict[str, Any], worst_loss_abs: float, missing_rows: int, constraints: Dict[str, Any]) -> Tuple[bool, List[str]]:
    fails = []
    if total["entry_count"] < constraints["min_total_entries"]:
        fails.append("TOTAL_ENTRIES_LOW")
    if total["mean_net_return_bps"] is None or total["mean_net_return_bps"] < constraints["min_total_mean_net_bps"]:
        fails.append("TOTAL_MEAN_LOW")
    if total["win_rate"] is None or total["win_rate"] < constraints["min_total_win_rate"]:
        fails.append("TOTAL_WIN_RATE_LOW")
    locked = split_map.get("LOCKED_HISTORICAL_FORWARD", {})
    final = split_map.get("FINAL_STATISTICAL_HOLDOUT", {})
    if locked.get("entry_count", 0) < constraints["min_locked_forward_entries"]:
        fails.append("LOCKED_FORWARD_ENTRIES_LOW")
    if locked.get("mean_net_return_bps") is None or locked.get("mean_net_return_bps") < constraints["min_locked_forward_mean_bps"]:
        fails.append("LOCKED_FORWARD_MEAN_LOW")
    if final.get("entry_count", 0) < constraints["min_final_holdout_entries"]:
        fails.append("FINAL_HOLDOUT_ENTRIES_LOW")
    if final.get("mean_net_return_bps") is None or final.get("mean_net_return_bps") < constraints["min_final_holdout_mean_bps"]:
        fails.append("FINAL_HOLDOUT_MEAN_LOW")
    if asof_post_plus.get("entry_count", 0) < constraints["min_post_plus_final_entries"]:
        fails.append("ASOF_POST_PLUS_FINAL_ENTRIES_LOW")
    if asof_post_plus.get("mean_net_return_bps") is None or asof_post_plus.get("mean_net_return_bps") < constraints["min_post_plus_final_mean_bps"]:
        fails.append("ASOF_POST_PLUS_FINAL_MEAN_LOW")
    if worst_loss_abs > constraints["max_abs_worst_loss_bps"]:
        fails.append("WORST_LOSS_TOO_LARGE")
    if missing_rows > constraints["max_missing_required_feature_rows"]:
        fails.append("MISSING_REQUIRED_FEATURE_ROWS")
    return (len(fails) == 0), fails


def write_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
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


def main() -> None:
    args = parse_args()
    root = Path(args.root).resolve()
    config_path = (root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    out_dir = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = read_json(config_path)
    macro_path = (root / cfg["macro_path"]).resolve()
    df = pd.read_csv(macro_path)
    date_col = resolve_date_col(df, cfg.get("date_col_candidates", ["feature_date_utc", "date_utc"]))
    df["_date"] = pd.to_datetime(df[date_col], utc=True, errors="coerce").dt.tz_localize(None)
    df = df.dropna(subset=["_date"]).sort_values("_date").reset_index(drop=True)
    price_col = cfg["price_col"]
    df[price_col] = pd.to_numeric(df[price_col], errors="coerce")
    constraints = cfg["constraints"]
    cost = float(cfg["cost_bps_total"])
    as_of = cfg["as_of_date"]
    final_start = cfg["final_holdout_start"]
    replay_start = cfg["daily_replay_start"]

    candidate_rows: List[Dict[str, Any]] = []
    split_rows: List[Dict[str, Any]] = []
    asof_rows: List[Dict[str, Any]] = []
    overlap_rows: List[Dict[str, Any]] = []
    selected_rows: List[Dict[str, Any]] = []
    all_entry_frames: List[pd.DataFrame] = []
    masks: Dict[str, pd.Series] = {}
    metrics_by_rule: Dict[str, Dict[str, Any]] = {}

    for cand in cfg["candidates"]:
        rule_id = cand["rule_id"]
        horizon = int(cand["horizon_trading_days"])
        mask, missing_cols = active_mask(df, cand["conditions"])
        required_cols = [price_col] + [c["column"] for c in cand["conditions"]]
        missing_required_rows = 0
        if not missing_cols:
            required_df = df[required_cols].apply(pd.to_numeric, errors="coerce")
            missing_required_rows = int(required_df.isna().any(axis=1).sum())
        entries = compute_entries(df, mask, horizon, price_col, cost, rule_id)
        if not entries.empty:
            entries["label"] = cand["label"]
            entries["bucket"] = cand["bucket"]
            entries["horizon_trading_days"] = horizon
            all_entry_frames.append(entries)
        masks[rule_id] = mask
        total = metric_block(entries, "TOTAL")
        split_map: Dict[str, Dict[str, Any]] = {}
        for split_id, start, end, role in SPLITS:
            m = metric_block(entries_between(entries, start, end), split_id, start, end)
            m.update({"rule_id": rule_id, "label": cand["label"], "role": role})
            split_rows.append(m)
            split_map[split_id] = m
        pre_known = metric_block(entries_known_by_asof(entries, as_of), "PRE_ASOF_KNOWN_MATURED_CALIBRATION", None, as_of)
        post = metric_block(entries_between(entries, as_of, "2024-12-31"), "POST_ASOF_VALIDATION", as_of, "2024-12-31")
        final = metric_block(entries_between(entries, final_start, None), "FINAL_HOLDOUT_COMPARISON", final_start, None)
        post_plus = metric_block(entries_between(entries, as_of, None), "POST_PLUS_FINAL_ACTUAL", as_of, None)
        for m in [pre_known, post, final, post_plus]:
            m.update({"rule_id": rule_id, "label": cand["label"]})
            asof_rows.append(m)
        worst_loss_abs = abs(float(total["min_net_return_bps"])) if total["min_net_return_bps"] is not None else 10**9
        passes, fails = passes_constraints(total, split_map, post_plus, worst_loss_abs, missing_required_rows, constraints)
        active_days = int(mask.sum())
        replay_mask = df["_date"] >= pd.Timestamp(replay_start)
        replay_active_days = int((mask & replay_mask).sum())
        row = {
            "rule_id": rule_id,
            "label": cand["label"],
            "bucket": cand["bucket"],
            "horizon_trading_days": horizon,
            "active_days": active_days,
            "replay_active_days": replay_active_days,
            "missing_columns": ";".join(missing_cols),
            "missing_required_feature_rows": missing_required_rows,
            "pass_portfolio_candidate": passes,
            "fail_reasons": ";".join(fails),
            **{f"total_{k}": v for k, v in total.items() if k not in {"bucket", "start", "end"}},
            "locked_forward_entries": split_map["LOCKED_HISTORICAL_FORWARD"]["entry_count"],
            "locked_forward_mean_net_bps": split_map["LOCKED_HISTORICAL_FORWARD"]["mean_net_return_bps"],
            "final_holdout_entries": split_map["FINAL_STATISTICAL_HOLDOUT"]["entry_count"],
            "final_holdout_mean_net_bps": split_map["FINAL_STATISTICAL_HOLDOUT"]["mean_net_return_bps"],
            "post_plus_final_entries": post_plus["entry_count"],
            "post_plus_final_mean_net_bps": post_plus["mean_net_return_bps"],
        }
        candidate_rows.append(row)
        metrics_by_rule[rule_id] = row

    ids = list(masks.keys())
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            overlap_rows.append({
                "rule_a": a,
                "rule_b": b,
                "jaccard_active_day_overlap_pct": round(jaccard(masks[a], masks[b]), 4),
                "a_active_days": int(masks[a].sum()),
                "b_active_days": int(masks[b].sum()),
            })

    anchor_id = "K06_RESILIENT_GOLD_VS_DXY_H120"
    selected = [anchor_id] if metrics_by_rule.get(anchor_id, {}).get("pass_portfolio_candidate") else []
    selected_reason: Dict[str, str] = {anchor_id: "ANCHOR_VALIDATED"} if selected else {}
    pass_candidates = [r for r in candidate_rows if r["pass_portfolio_candidate"] and r["rule_id"] != anchor_id]
    def rank_score(r: Dict[str, Any]) -> float:
        mean = float(r.get("post_plus_final_mean_net_bps") or r.get("total_mean_net_return_bps") or 0.0)
        win = float(r.get("total_win_rate") or 0.0) * 250.0
        entries = min(float(r.get("total_entry_count") or 0.0), 40.0) * 2.0
        return mean + win + entries
    pass_candidates.sort(key=rank_score, reverse=True)
    max_complements = int(cfg["portfolio_max_complements"])
    max_j = float(cfg["max_jaccard_vs_selected_pct"])
    for r in pass_candidates:
        if len(selected) >= 1 + max_complements:
            break
        rid = r["rule_id"]
        ok = True
        max_overlap = 0.0
        for s in selected:
            ov = jaccard(masks[rid], masks[s])
            max_overlap = max(max_overlap, ov)
            if ov > max_j:
                ok = False
                break
        if ok:
            selected.append(rid)
            selected_reason[rid] = f"PASS_COMPLEMENT_MAX_OVERLAP_{max_overlap:.2f}PCT"

    for rank, rid in enumerate(selected, start=1):
        row = dict(metrics_by_rule[rid])
        row.update({"portfolio_rank": rank, "selection_reason": selected_reason.get(rid, "SELECTED")})
        selected_rows.append(row)

    if not selected:
        decision = "NO_PORTFOLIO_EXPANSION_ALLOWED_NO_ORDER"
        classification = "S77_NO_VALID_ANCHOR"
        disposition = "NO_PORTFOLIO_EXPANSION_ALLOWED"
    elif len(selected) == 1:
        decision = "K06_ONLY_REMAINS_BEST_NO_ORDER"
        classification = "S77_K06_ONLY"
        disposition = "K06_ONLY_REMAINS_BEST"
    else:
        decision = "PORTFOLIO_READY_WITH_K06_PLUS_COMPLEMENTS_NO_ORDER"
        classification = "S77_PORTFOLIO_READY"
        disposition = "PORTFOLIO_READY_WITH_K06_PLUS_COMPLEMENTS"

    write_csv(out_dir / "stage77_candidate_metrics.csv", candidate_rows)
    write_csv(out_dir / "stage77_candidate_split_metrics.csv", split_rows)
    write_csv(out_dir / "stage77_candidate_asof_metrics.csv", asof_rows)
    write_csv(out_dir / "stage77_candidate_overlap.csv", overlap_rows)
    write_csv(out_dir / "stage77_selected_portfolio.csv", selected_rows)
    if all_entry_frames:
        pd.concat(all_entry_frames, ignore_index=True).to_csv(out_dir / "stage77_candidate_entry_returns.csv", index=False)
    else:
        pd.DataFrame().to_csv(out_dir / "stage77_candidate_entry_returns.csv", index=False)

    summary = {
        "stage": "Stage77_PORTFOLIO_CANDIDATE_SELECTION_HISTORICAL_ASOF",
        "root": str(root),
        "config": str(config_path),
        "generated_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "STAGE77_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
        "principle": "Use locked historical splits, historical daily replay, and corrected as-of validation to select a small no-order demo-observation candidate portfolio. Do not open a new megascan.",
        "macro_dataset": {
            "path": str(macro_path),
            "rows": int(len(df)),
            "date_col": date_col,
            "price_col": price_col,
            "min_date": df["_date"].min().date().isoformat(),
            "max_date": df["_date"].max().date().isoformat(),
            "sha256": sha256_file(macro_path),
        },
        "candidate_count": len(candidate_rows),
        "pass_candidate_count": int(sum(1 for r in candidate_rows if r["pass_portfolio_candidate"])),
        "selected_count": len(selected_rows),
        "selected_rule_ids": selected,
        "selected_portfolio": selected_rows,
        "constraints": constraints,
        "hard_blocks": cfg["hard_blocks"],
        "outputs": {
            "summary_json": str(out_dir / "stage77_portfolio_candidate_selection_historical_asof_summary.json"),
            "report_md": str(out_dir / "stage77_portfolio_candidate_selection_historical_asof_report.md"),
            "candidate_metrics_csv": str(out_dir / "stage77_candidate_metrics.csv"),
            "candidate_split_metrics_csv": str(out_dir / "stage77_candidate_split_metrics.csv"),
            "candidate_asof_metrics_csv": str(out_dir / "stage77_candidate_asof_metrics.csv"),
            "candidate_overlap_csv": str(out_dir / "stage77_candidate_overlap.csv"),
            "selected_portfolio_csv": str(out_dir / "stage77_selected_portfolio.csv"),
            "candidate_entry_returns_csv": str(out_dir / "stage77_candidate_entry_returns.csv"),
        }
    }
    (out_dir / "stage77_portfolio_candidate_selection_historical_asof_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    lines = [
        "# Stage77 Portfolio Candidate Selection Historical-As-Of",
        "",
        "## Decision",
        f"- status: `{summary['status']}`",
        f"- decision: `{decision}`",
        f"- classification: `{classification}`",
        f"- disposition: `{disposition}`",
        "",
        "## Principle",
        summary["principle"],
        "",
        "## Selected portfolio",
    ]
    if selected_rows:
        for r in selected_rows:
            lines.append(f"- rank `{r['portfolio_rank']}`: `{r['rule_id']}` / `{r['label']}`; mean=`{r.get('total_mean_net_return_bps')}`, win=`{r.get('total_win_rate')}`, reason=`{r['selection_reason']}`")
    else:
        lines.append("- none")
    lines += ["", "## Hard blocks"] + [f"- `{b}`" for b in cfg["hard_blocks"]]
    (out_dir / "stage77_portfolio_candidate_selection_historical_asof_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"decision": decision, "selected_rule_ids": selected}, indent=2))


if __name__ == "__main__":
    main()
