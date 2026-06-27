#!/usr/bin/env python3
"""
Stage98 COT Portfolio Increment Review

Reviews Stage97 COT hard-audit survivors for incremental contribution versus the
current Stage88/Stage87 unified observer portfolio. This is observer/research
only: no orders, no broker connection, no MT5/EA change.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd


HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE98",
    "NO_THRESHOLD_TUNING_FROM_STAGE98_PORTFOLIO_REVIEW",
    "NO_DIRECT_MT5_OR_EA_CHANGE_FROM_STAGE98",
]

CURRENT_RULE_IDS = [
    "K06_RESILIENT_GOLD_VS_DXY_H120",
    "K03_SAFE_HAVEN_REALYIELD_H120",
    "K07_DXY_TREND_RELIEF_GOLD_TREND_H120",
    "S83_14_REALYIELD_120D_DOWN_GOLD_NOT_TRENDING_H120",
    "S83_13_DXY_120D_DOWN_GOLD_NOT_TRENDING_H120",
]


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
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
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)


def write_csv(path: Path, rows: List[Dict[str, Any]], columns: List[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if columns is None:
        seen = []
        for row in rows:
            for k in row:
                if k not in seen:
                    seen.append(k)
        columns = seen
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def normalize_date_series(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, utc=True, errors="coerce").dt.tz_convert(None)


def load_macro(root: Path, cfg: Dict[str, Any]) -> pd.DataFrame:
    path = root / cfg["paths"]["macro_dataset"]
    if not path.exists():
        raise FileNotFoundError(f"Macro dataset not found: {path}")
    df = pd.read_csv(path)
    date_col = cfg["columns"].get("macro_date_col", "feature_date_utc")
    if date_col not in df.columns:
        raise KeyError(f"Macro date column missing: {date_col}")
    df[date_col] = normalize_date_series(df[date_col])
    df = df.dropna(subset=[date_col]).sort_values(date_col).reset_index(drop=True)
    if "gold_close" not in df.columns and "close" in df.columns:
        df["gold_close"] = pd.to_numeric(df["close"], errors="coerce")
    for col in ["gold_close", "dxy", "real_yield", "vix"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    # Derived features needed by current and COT rules.
    if "gold_ret_20d" not in df.columns and "gold_close" in df.columns:
        df["gold_ret_20d"] = df["gold_close"].pct_change(20)
    if "dxy_ret_20d" not in df.columns and "dxy" in df.columns:
        df["dxy_ret_20d"] = df["dxy"].pct_change(20)
    if "dxy_ret_120d" not in df.columns and "dxy" in df.columns:
        df["dxy_ret_120d"] = df["dxy"].pct_change(120)
    if "real_yield_change_20d" not in df.columns and "real_yield" in df.columns:
        df["real_yield_change_20d"] = df["real_yield"].diff(20)
    if "real_yield_change_120d" not in df.columns and "real_yield" in df.columns:
        df["real_yield_change_120d"] = df["real_yield"].diff(120)
    if "vix_change_20d" not in df.columns and "vix" in df.columns:
        df["vix_change_20d"] = df["vix"].diff(20)
    return df


def safe_numeric_series(s: pd.Series) -> pd.Series:
    """Convert numeric-looking columns without using pandas errors='ignore'.

    pandas 3.14 rejects errors='ignore'. We preserve genuinely textual columns
    by keeping the original series when coercion would produce no numeric values.
    """
    converted = pd.to_numeric(s, errors="coerce")
    non_null_in = int(s.notna().sum())
    non_null_out = int(converted.notna().sum())
    if non_null_in > 0 and non_null_out == 0:
        return s
    return converted


def load_cot(root: Path, cfg: Dict[str, Any]) -> pd.DataFrame:
    path = root / cfg["paths"]["cot_dataset"]
    if not path.exists():
        raise FileNotFoundError(f"COT dataset not found: {path}")
    df = pd.read_csv(path)
    if "available_after_utc" in df.columns:
        df["cot_available_after_utc"] = normalize_date_series(df["available_after_utc"])
    elif "report_date_utc" in df.columns:
        df["cot_available_after_utc"] = normalize_date_series(df["report_date_utc"]) + pd.Timedelta(days=int(cfg.get("cot_default_lag_days", 3)))
    elif "report_date" in df.columns:
        df["cot_available_after_utc"] = normalize_date_series(df["report_date"]) + pd.Timedelta(days=int(cfg.get("cot_default_lag_days", 3)))
    else:
        raise KeyError("COT dataset must contain available_after_utc, report_date_utc, or report_date")

    if "report_date_utc" in df.columns:
        df["report_date_utc"] = normalize_date_series(df["report_date_utc"])
    elif "report_date" in df.columns:
        df["report_date_utc"] = normalize_date_series(df["report_date"])

    for col in df.columns:
        if col not in {"report_date_utc", "cot_available_after_utc", "available_after_utc", "market_and_exchange_names"}:
            df[col] = safe_numeric_series(df[col])

    if "cot_mm_net_z" not in df.columns:
        # Conservative fallback for Stage95 output names.  Stage95 official CFTC
        # builder emits rolling-window suffixes such as
        # managed_money_net_pct_oi_z_156w, while discovery stages use the
        # shorter research alias cot_mm_net_z.
        candidates = [
            "managed_money_net_pct_oi_z",
            "managed_money_net_pct_oi_z_156w",
            "managed_money_net_pct_oi_z_104w",
            "managed_money_net_z",
            "managed_money_net_z_156w",
            "managed_money_net_z_104w",
            "mm_net_pct_oi_z",
        ]
        for c in candidates:
            if c in df.columns:
                df["cot_mm_net_z"] = pd.to_numeric(df[c], errors="coerce")
                break

    if "cot_mm_net_z_change_4w" not in df.columns:
        change_candidates = [
            "managed_money_net_pct_oi_change_4w",
            "managed_money_net_change_4w",
            "mm_net_pct_oi_change_4w",
        ]
        for c in change_candidates:
            if c in df.columns:
                df["cot_mm_net_z_change_4w"] = pd.to_numeric(df[c], errors="coerce")
                break

    if "cot_mm_net_z_change_4w" not in df.columns and "cot_mm_net_z" in df.columns:
        df = df.sort_values("cot_available_after_utc").reset_index(drop=True)
        df["cot_mm_net_z_change_4w"] = pd.to_numeric(df["cot_mm_net_z"], errors="coerce").diff(4)

    df = df.dropna(subset=["cot_available_after_utc"]).sort_values("cot_available_after_utc").reset_index(drop=True)
    return df


def build_joined(root: Path, cfg: Dict[str, Any]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    macro = load_macro(root, cfg)
    cot = load_cot(root, cfg)
    date_col = cfg["columns"].get("macro_date_col", "feature_date_utc")
    macro = macro.rename(columns={date_col: "feature_date_utc"})
    macro["feature_date_utc"] = normalize_date_series(macro["feature_date_utc"])
    cot = cot.sort_values("cot_available_after_utc")
    joined = pd.merge_asof(
        macro.sort_values("feature_date_utc"),
        cot.sort_values("cot_available_after_utc"),
        left_on="feature_date_utc",
        right_on="cot_available_after_utc",
        direction="backward",
        suffixes=("", "_cot"),
    )
    lookahead = int((joined["cot_available_after_utc"].notna() & (joined["cot_available_after_utc"] > joined["feature_date_utc"])).sum())
    meta = {
        "macro_rows": int(len(macro)),
        "macro_min_date": str(macro["feature_date_utc"].min().date()) if len(macro) else None,
        "macro_max_date": str(macro["feature_date_utc"].max().date()) if len(macro) else None,
        "cot_rows": int(len(cot)),
        "cot_min_report_date": str(cot["report_date_utc"].min().date()) if "report_date_utc" in cot.columns and len(cot) else None,
        "cot_max_report_date": str(cot["report_date_utc"].max().date()) if "report_date_utc" in cot.columns and len(cot) else None,
        "joined_rows": int(len(joined)),
        "joined_cot_available_rows": int(joined["cot_available_after_utc"].notna().sum()),
        "lookahead_violations": lookahead,
        "cot_sha256": sha256_file(root / cfg["paths"]["cot_dataset"]),
        "macro_sha256": sha256_file(root / cfg["paths"]["macro_dataset"]),
    }
    return joined, meta


def mask_current_portfolio(df: pd.DataFrame) -> Tuple[pd.Series, Dict[str, int]]:
    idx = df.index
    def col(c):
        return pd.to_numeric(df[c], errors="coerce") if c in df.columns else pd.Series([float("nan")] * len(df), index=idx)

    masks = {
        "K06_RESILIENT_GOLD_VS_DXY_H120": (col("gold_sma20_over_50") > 0) & (col("dxy_ret_20d") > 0) & (col("real_yield_change_20d") < 0),
        "K03_SAFE_HAVEN_REALYIELD_H120": (col("vix_change_20d") > 0) & (col("real_yield_change_20d") < 0),
        "K07_DXY_TREND_RELIEF_GOLD_TREND_H120": (col("gold_sma20_over_50") > 0) & (col("dxy_sma20_over_50") < 0),
        "S83_14_REALYIELD_120D_DOWN_GOLD_NOT_TRENDING_H120": (col("real_yield_change_120d") < 0) & (col("gold_sma20_over_50") < 0),
        "S83_13_DXY_120D_DOWN_GOLD_NOT_TRENDING_H120": (col("dxy_ret_120d") < 0) & (col("gold_sma20_over_50") < 0),
    }
    for k in masks:
        masks[k] = masks[k].fillna(False)
    union = pd.Series(False, index=idx)
    counts = {}
    for k, m in masks.items():
        union = union | m
        counts[k] = int(m.sum())
    counts["current_union_active_days"] = int(union.sum())
    return union, counts


def eval_condition(df: pd.DataFrame, condition_text: str) -> Tuple[pd.Series, List[str], List[str]]:
    idx = df.index
    mask = pd.Series(True, index=idx)
    missing_cols: List[str] = []
    required_cols: List[str] = []
    parts = [p.strip() for p in str(condition_text).split("AND") if p.strip()]
    op_re = re = __import__("re")
    for part in parts:
        m = re.match(r"^([A-Za-z0-9_]+)\s*(<=|>=|<|>|==)\s*(-?\d+(?:\.\d+)?)$", part)
        if not m:
            # Unknown condition is treated as impossible rather than silently true.
            mask &= False
            continue
        c, op, v_s = m.group(1), m.group(2), m.group(3)
        required_cols.append(c)
        if c not in df.columns:
            missing_cols.append(c)
            mask &= False
            continue
        s = pd.to_numeric(df[c], errors="coerce")
        v = float(v_s)
        if op == "<":
            mask &= s < v
        elif op == ">":
            mask &= s > v
        elif op == "<=":
            mask &= s <= v
        elif op == ">=":
            mask &= s >= v
        elif op == "==":
            mask &= s == v
    return mask.fillna(False), sorted(set(missing_cols)), sorted(set(required_cols))


def latest_signal(df: pd.DataFrame, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    latest = df.dropna(subset=["feature_date_utc"]).iloc[-1]
    one = df.loc[[latest.name]]
    out = []
    for r in rows:
        m, missing, _ = eval_condition(one, r.get("condition_text", ""))
        active = bool(m.iloc[0])
        out.append({
            "rule_id": r["rule_id"],
            "label": r.get("label", ""),
            "latest_signal_active": active,
            "latest_failures": "" if active else ("missing:" + "|".join(missing) if missing else "condition_not_met"),
        })
    return out


def nan_to_none(obj: Any) -> Any:
    if isinstance(obj, float) and math.isnan(obj):
        return None
    if isinstance(obj, dict):
        return {k: nan_to_none(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [nan_to_none(v) for v in obj]
    return obj


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    cfg_path = Path(args.config)
    if not cfg_path.is_absolute():
        cfg_path = root / cfg_path
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    cfg = read_json(cfg_path)

    stage97_summary_path = root / cfg["paths"]["stage97_summary"]
    stage97_selected_path = root / cfg["paths"]["stage97_selected_csv"]
    stage97_summary = read_json(stage97_summary_path)
    required_disp = cfg["required_stage97_disposition"]
    if stage97_summary.get("disposition") != required_disp:
        raise RuntimeError(f"Stage97 disposition mismatch: {stage97_summary.get('disposition')} != {required_disp}")
    selected_df = pd.read_csv(stage97_selected_path)
    candidate_rows = selected_df.to_dict(orient="records")

    joined, join_meta = build_joined(root, cfg)
    current_union, current_counts = mask_current_portfolio(joined)
    current_union_days = int(current_union.sum())

    constraints = cfg["constraints"]
    reviews: List[Dict[str, Any]] = []
    selected: List[Dict[str, Any]] = []
    selected_union = current_union.copy()
    selected_masks: Dict[str, pd.Series] = {}

    # Rank by hard-audit score first, then incremental days.
    def sort_key(row):
        return (
            float(row.get("cot_hard_audit_score", row.get("hard_audit_score", 0)) or 0),
            float(row.get("post_asof_mean_net_bps", 0) or 0),
            int(row.get("incremental_union_active_days", 0) or 0),
        )
    candidate_rows = sorted(candidate_rows, key=sort_key, reverse=True)

    for row in candidate_rows:
        mask, missing_cols, required_cols = eval_condition(joined, row.get("condition_text", ""))
        active_days = int(mask.sum())
        overlap_days = int((mask & current_union).sum())
        overlap_pct = round(100.0 * overlap_days / active_days, 4) if active_days else 0.0
        incremental_days = int((mask & ~current_union).sum())
        final_union_after = int((current_union | mask).sum())

        fail = []
        if bool(row.get("pass_cot_hard_audit_candidate")) is not True and str(row.get("pass_cot_hard_audit_candidate")).lower() != "true":
            fail.append("NOT_HARD_AUDIT_PASS")
        if float(row.get("cot_hard_audit_score", 0) or 0) < constraints["min_cot_hard_audit_score"]:
            fail.append("HARD_AUDIT_SCORE_TOO_LOW")
        if float(row.get("final_holdout_mean_net_bps", 0) or 0) < constraints["min_final_holdout_mean_bps"]:
            fail.append("FINAL_HOLDOUT_MEAN_TOO_LOW")
        if float(row.get("post_asof_mean_net_bps", 0) or 0) < constraints["min_post_asof_mean_bps"]:
            fail.append("POST_ASOF_MEAN_TOO_LOW")
        if float(row.get("total_win_rate", 0) or 0) < constraints["min_total_win_rate"]:
            fail.append("WIN_RATE_TOO_LOW")
        if incremental_days < constraints["min_incremental_union_active_days"]:
            fail.append("INCREMENTAL_DAYS_TOO_LOW")
        if overlap_pct > constraints["max_overlap_with_current_pct"]:
            fail.append("OVERLAP_WITH_CURRENT_TOO_HIGH")
        if missing_cols:
            fail.append("MISSING_COLUMNS:" + "|".join(missing_cols))

        # Pairwise anti-duplication against already selected COT additions.
        pairwise_max_pct = 0.0
        pairwise_block = ""
        for sid, smask in selected_masks.items():
            denom = int(mask.sum())
            p = round(100.0 * int((mask & smask).sum()) / denom, 4) if denom else 0.0
            pairwise_max_pct = max(pairwise_max_pct, p)
            if p > constraints["max_pairwise_overlap_with_selected_addition_pct"]:
                pairwise_block = sid
        if pairwise_block:
            fail.append("PAIRWISE_OVERLAP_WITH_SELECTED_TOO_HIGH:" + pairwise_block)

        pass_review = len(fail) == 0
        review = dict(row)
        review.update({
            "computed_active_days": active_days,
            "computed_overlap_with_current_days": overlap_days,
            "computed_overlap_with_current_pct": overlap_pct,
            "computed_incremental_union_active_days": incremental_days,
            "computed_current_union_active_days_after_candidate": final_union_after,
            "computed_pairwise_max_overlap_with_selected_pct": pairwise_max_pct,
            "pass_stage98_portfolio_review": pass_review,
            "stage98_fail_reasons": "|".join(fail),
        })
        reviews.append(review)

        if pass_review and len(selected) < int(constraints["max_additions"]):
            selected.append(review)
            selected_union = selected_union | mask
            selected_masks[row["rule_id"]] = mask

    final_ids = CURRENT_RULE_IDS + [r["rule_id"] for r in selected]
    latest = latest_signal(joined, selected)
    active_latest = [r["rule_id"] for r in latest if r["latest_signal_active"]]

    if selected:
        status = "STAGE98_COMPLETE_NO_PROMOTION"
        decision = "STAGE98_COT_INCREMENT_SELECTED_FOR_UNIFIED_OBSERVER_REVIEW_NO_ORDER"
        classification = "S98_COT_INCREMENT_SELECTED"
        disposition = "COT_INCREMENT_SELECTED_FOR_STAGE99_UNIFIED_OBSERVER_EXPANSION"
    else:
        status = "STAGE98_COMPLETE_NO_PROMOTION"
        decision = "STAGE98_NO_COT_INCREMENT_SELECTED_NO_ORDER"
        classification = "S98_NO_COT_INCREMENT_SELECTED"
        disposition = "KEEP_STAGE88_UNIFIED_OBSERVER_ONLY"

    summary = {
        "stage": "Stage98_COT_PORTFOLIO_INCREMENT_REVIEW",
        "root": str(root),
        "config": str(cfg_path),
        "status": status,
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
        "principle": "Review Stage97 COT hard-audit survivors for incremental contribution before any observer-only expansion. No orders, no broker connection, no MT5/EA change.",
        "stage97_reference": {
            "path": str(stage97_summary_path),
            "exists": stage97_summary_path.exists(),
            "decision": stage97_summary.get("decision"),
            "disposition": stage97_summary.get("disposition"),
        },
        "data_join": join_meta,
        "current_unified_portfolio_rule_ids": CURRENT_RULE_IDS,
        "stage97_candidate_rule_ids": [r["rule_id"] for r in candidate_rows],
        "candidate_count": len(candidate_rows),
        "selected_count": len(selected),
        "selected_rule_ids": [r["rule_id"] for r in selected],
        "selected_for_stage99": nan_to_none(selected),
        "final_review_portfolio_rule_ids": final_ids,
        "current_union_active_days": current_union_days,
        "final_union_active_days_after_selected_additions": int(selected_union.sum()),
        "incremental_union_active_days_selected": int((selected_union & ~current_union).sum()),
        "latest_signal_snapshot": latest,
        "latest_active_rule_ids_selected_cot": active_latest,
        "constraints": constraints,
        "issues": [],
        "hard_blocks": HARD_BLOCKS,
        "outputs": {
            "summary_json": str(out_dir / "stage98_cot_portfolio_increment_review_summary.json"),
            "report_md": str(out_dir / "stage98_cot_portfolio_increment_review_report.md"),
            "review_csv": str(out_dir / "stage98_cot_portfolio_increment_review.csv"),
            "selected_csv": str(out_dir / "stage98_selected_for_stage99.csv"),
        },
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "stage98_cot_portfolio_increment_review_summary.json", nan_to_none(summary))
    write_csv(out_dir / "stage98_cot_portfolio_increment_review.csv", nan_to_none(reviews))
    write_csv(out_dir / "stage98_selected_for_stage99.csv", nan_to_none(selected))

    lines = [
        "# Stage98 COT Portfolio Increment Review",
        "",
        "## Decision",
        f"- status: `{status}`",
        f"- decision: `{decision}`",
        f"- classification: `{classification}`",
        f"- disposition: `{disposition}`",
        "",
        "## Selected for Stage99",
    ]
    if selected:
        for r in selected:
            lines.append(f"- `{r['rule_id']}`: {r.get('label','')} overlap=`{r.get('computed_overlap_with_current_pct')}` incremental_days=`{r.get('computed_incremental_union_active_days')}` latest_active=`{next((x['latest_signal_active'] for x in latest if x['rule_id']==r['rule_id']), False)}`")
    else:
        lines.append("- none")
    lines += [
        "",
        "## Candidate snapshot",
    ]
    for r in reviews:
        lines.append(f"- `{r['rule_id']}` pass=`{r['pass_stage98_portfolio_review']}` overlap=`{r['computed_overlap_with_current_pct']}` incremental_days=`{r['computed_incremental_union_active_days']}` score=`{r.get('cot_hard_audit_score')}` fail=`{r['stage98_fail_reasons']}`")
    lines += [
        "",
        "## Hard blocks",
    ]
    lines += [f"- `{x}`" for x in HARD_BLOCKS]
    (out_dir / "stage98_cot_portfolio_increment_review_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"status": status, "decision": decision, "selected_rule_ids": [r["rule_id"] for r in selected]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
