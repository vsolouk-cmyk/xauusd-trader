#!/usr/bin/env python3
"""Stage89 residual-regime thesis discovery.

Searches for thesis-first macro rules that add exposure mostly when the current
Stage86 unified observer portfolio is inactive. Observer/research only. No
orders, no MT5 change, no broker connection.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: List[str] = []
    for row in rows:
        for k in row.keys():
            if k not in keys:
                keys.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


@dataclass(frozen=True)
class Cond:
    column: str
    op: str
    threshold: float

    def text(self) -> str:
        return f"{self.column}{self.op}{self.threshold}"


@dataclass(frozen=True)
class Rule:
    rule_id: str
    label: str
    bucket: str
    horizon: int
    cooldown: int
    conditions: Tuple[Cond, ...]

    def condition_text(self) -> str:
        return " AND ".join(c.text() for c in self.conditions)


def load_macro(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"macro dataset not found: {path}")
    df = pd.read_csv(path)
    if "feature_date_utc" not in df.columns:
        raise ValueError("macro dataset missing feature_date_utc")
    if "gold_close" not in df.columns:
        raise ValueError("macro dataset missing gold_close")
    df["feature_date_utc"] = pd.to_datetime(df["feature_date_utc"], errors="coerce", utc=True).dt.date.astype(str)
    for c in df.columns:
        if c == "feature_date_utc":
            continue
        converted = pd.to_numeric(df[c], errors="coerce")
        # Preserve pure metadata columns that cannot be converted at all.
        if converted.notna().sum() > 0:
            df[c] = converted
    df = df.dropna(subset=["feature_date_utc", "gold_close"]).reset_index(drop=True)
    return df


def add_derived_features(df: pd.DataFrame) -> List[str]:
    added: List[str] = []

    def add(name: str, series: pd.Series) -> None:
        if name not in df.columns:
            df[name] = series
            added.append(name)

    if "gold_close" in df.columns:
        gold = pd.to_numeric(df["gold_close"], errors="coerce")
        for w in (20, 60, 120):
            add(f"gold_ret_{w}d", gold / gold.shift(w) - 1.0)
        add("gold_realized_vol_20d", gold.pct_change().rolling(20).std())
        add("gold_sma20_over_50", gold.rolling(20).mean() / gold.rolling(50).mean() - 1.0)
    if "dxy" in df.columns:
        dxy = pd.to_numeric(df["dxy"], errors="coerce")
        for w in (20, 60, 120):
            add(f"dxy_ret_{w}d", dxy / dxy.shift(w) - 1.0)
        add("dxy_sma20_over_50", dxy.rolling(20).mean() / dxy.rolling(50).mean() - 1.0)
    if "real_yield" in df.columns:
        ry = pd.to_numeric(df["real_yield"], errors="coerce")
        for w in (20, 60, 120):
            add(f"real_yield_change_{w}d", ry - ry.shift(w))
    if "vix" in df.columns:
        vix = pd.to_numeric(df["vix"], errors="coerce")
        for w in (20, 60):
            add(f"vix_change_{w}d", vix - vix.shift(w))
            add(f"vix_ret_{w}d", vix / vix.shift(w) - 1.0)
    if "etf_flow_tonnes_3m" in df.columns:
        etf = pd.to_numeric(df["etf_flow_tonnes_3m"], errors="coerce")
        add("etf_flow_change_20d", etf - etf.shift(20))
        add("etf_flow_positive", (etf > 0).astype(float))
    if "central_bank_demand_tonnes_3m" in df.columns:
        cb = pd.to_numeric(df["central_bank_demand_tonnes_3m"], errors="coerce")
        add("central_bank_demand_change_20d", cb - cb.shift(20))
        add("central_bank_demand_positive", (cb > 0).astype(float))
    return added


def eval_condition(series: pd.Series, op: str, threshold: float) -> pd.Series:
    if op == ">":
        return series > threshold
    if op == "<":
        return series < threshold
    if op == ">=":
        return series >= threshold
    if op == "<=":
        return series <= threshold
    if op == "==":
        return series == threshold
    raise ValueError(f"unsupported operator: {op}")


def rule_mask(df: pd.DataFrame, rule: Rule) -> Tuple[pd.Series, List[str], int, int]:
    missing_cols = [c.column for c in rule.conditions if c.column not in df.columns]
    if missing_cols:
        return pd.Series(False, index=df.index), missing_cols, 0, 0
    req = df[[c.column for c in rule.conditions]].copy()
    complete = req.notna().all(axis=1)
    first_complete_idx = int(complete.idxmax()) if complete.any() else len(df)
    warmup_missing = int((~complete.iloc[:first_complete_idx]).sum()) if first_complete_idx < len(df) else len(df)
    mask = complete.copy()
    for cond in rule.conditions:
        vals = pd.to_numeric(df[cond.column], errors="coerce")
        mask = mask & eval_condition(vals, cond.op, cond.threshold).fillna(False)
    return mask.astype(bool), [], warmup_missing, first_complete_idx


def current_portfolio_rules() -> List[Rule]:
    return [
        Rule("K06_RESILIENT_GOLD_VS_DXY_H120", "K06_RESILIENT_GOLD_VS_DXY", "current_anchor", 120, 120, (
            Cond("gold_sma20_over_50", ">", 0.0), Cond("dxy_ret_20d", ">", 0.0), Cond("real_yield_change_20d", "<", 0.0))),
        Rule("K03_SAFE_HAVEN_REALYIELD_H120", "K03_WGC_RISK_UNCERTAINTY_SAFE_HAVEN", "current_stage77b", 120, 120, (
            Cond("vix_change_20d", ">", 0.0), Cond("real_yield_change_20d", "<", 0.0))),
        Rule("K07_DXY_TREND_RELIEF_GOLD_TREND_H120", "K07_DXY_TREND_RELIEF_GOLD_TREND", "current_stage77b", 120, 120, (
            Cond("gold_sma20_over_50", ">", 0.0), Cond("dxy_sma20_over_50", "<", 0.0))),
        Rule("S83_14_REALYIELD_120D_DOWN_GOLD_NOT_TRENDING_H120", "REALYIELD_120D_DOWN_GOLD_NOT_TRENDING", "current_stage86", 120, 120, (
            Cond("real_yield_change_120d", "<", 0.0), Cond("gold_sma20_over_50", "<", 0.0))),
        Rule("S83_13_DXY_120D_DOWN_GOLD_NOT_TRENDING_H120", "DXY_120D_DOWN_GOLD_NOT_TRENDING", "current_stage86", 120, 120, (
            Cond("dxy_ret_120d", "<", 0.0), Cond("gold_sma20_over_50", "<", 0.0))),
    ]


def residual_candidate_rules() -> List[Rule]:
    # Built as thesis-first families intended to be residual to the current five-rule observer.
    rules: List[Rule] = []
    def R(i: int, label: str, bucket: str, horizon: int, conds: List[Tuple[str, str, float]]):
        rules.append(Rule(f"S89_{i:02d}_{label}_H{horizon}", label, bucket, horizon, horizon, tuple(Cond(*x) for x in conds)))

    R(1, "DXY_STRONG_ETF_ACCUMULATION_GOLD_PULLBACK", "residual_flow_headwind", 60, [("dxy_ret_60d", ">", 0), ("etf_flow_change_20d", ">", 0), ("gold_ret_20d", "<", 0)])
    R(2, "DXY_STRONG_CB_ACCUMULATION_GOLD_PULLBACK", "residual_cb_headwind", 60, [("dxy_ret_60d", ">", 0), ("central_bank_demand_change_20d", ">", 0), ("gold_ret_20d", "<", 0)])
    R(3, "REALYIELD_UP_ETF_ACCUMULATION_GOLD_PULLBACK", "residual_flow_headwind", 60, [("real_yield_change_60d", ">", 0), ("etf_flow_change_20d", ">", 0), ("gold_ret_20d", "<", 0)])
    R(4, "REALYIELD_UP_CB_ACCUMULATION_GOLD_PULLBACK", "residual_cb_headwind", 60, [("real_yield_change_60d", ">", 0), ("central_bank_demand_change_20d", ">", 0), ("gold_ret_20d", "<", 0)])
    R(5, "VIX_UP_DXY_STRONG_GOLD_PULLBACK", "residual_stress_pullback", 60, [("vix_change_20d", ">", 0), ("dxy_ret_20d", ">", 0), ("gold_ret_20d", "<", 0)])
    R(6, "VIX_UP_REALYIELD_UP_GOLD_PULLBACK", "residual_stress_pullback", 60, [("vix_change_20d", ">", 0), ("real_yield_change_20d", ">", 0), ("gold_ret_20d", "<", 0)])
    R(7, "ETF_POSITIVE_GOLD_120D_PULLBACK", "residual_deep_pullback_flow", 120, [("gold_ret_120d", "<", 0), ("etf_flow_tonnes_3m", ">", 0)])
    R(8, "CB_POSITIVE_GOLD_120D_PULLBACK", "residual_deep_pullback_cb", 120, [("gold_ret_120d", "<", 0), ("central_bank_demand_tonnes_3m", ">", 0)])
    R(9, "LOW_VOL_GOLD_PULLBACK_ETF_SUPPORT", "residual_benign_pullback", 60, [("gold_realized_vol_20d", "<", 0.012), ("gold_ret_20d", "<", 0), ("etf_flow_tonnes_3m", ">", 0)])
    R(10, "LOW_VOL_GOLD_PULLBACK_CB_SUPPORT", "residual_benign_pullback", 60, [("gold_realized_vol_20d", "<", 0.012), ("gold_ret_20d", "<", 0), ("central_bank_demand_tonnes_3m", ">", 0)])
    R(11, "GOLD_NOT_TRENDING_ETF_ACCELERATION", "residual_not_trending_flow", 60, [("gold_sma20_over_50", "<", 0), ("etf_flow_change_20d", ">", 0)])
    R(12, "GOLD_NOT_TRENDING_CB_ACCELERATION", "residual_not_trending_cb", 60, [("gold_sma20_over_50", "<", 0), ("central_bank_demand_change_20d", ">", 0)])
    R(13, "DXY_120D_UP_ETF_SUPPORT_GOLD_NOT_TRENDING", "residual_headwind_absorption", 120, [("dxy_ret_120d", ">", 0), ("etf_flow_tonnes_3m", ">", 0), ("gold_sma20_over_50", "<", 0)])
    R(14, "DXY_120D_UP_CB_SUPPORT_GOLD_NOT_TRENDING", "residual_headwind_absorption", 120, [("dxy_ret_120d", ">", 0), ("central_bank_demand_tonnes_3m", ">", 0), ("gold_sma20_over_50", "<", 0)])
    R(15, "REALYIELD_120D_UP_ETF_SUPPORT_GOLD_NOT_TRENDING", "residual_headwind_absorption", 120, [("real_yield_change_120d", ">", 0), ("etf_flow_tonnes_3m", ">", 0), ("gold_sma20_over_50", "<", 0)])
    R(16, "REALYIELD_120D_UP_CB_SUPPORT_GOLD_NOT_TRENDING", "residual_headwind_absorption", 120, [("real_yield_change_120d", ">", 0), ("central_bank_demand_tonnes_3m", ">", 0), ("gold_sma20_over_50", "<", 0)])
    R(17, "ETF_ACCELERATION_AFTER_GOLD_60D_PULLBACK", "residual_flow_turn", 60, [("gold_ret_60d", "<", 0), ("etf_flow_change_20d", ">", 0)])
    R(18, "CB_ACCELERATION_AFTER_GOLD_60D_PULLBACK", "residual_cb_turn", 60, [("gold_ret_60d", "<", 0), ("central_bank_demand_change_20d", ">", 0)])
    R(19, "VIX_60D_UP_GOLD_NOT_TRENDING", "residual_slow_stress", 120, [("vix_change_60d", ">", 0), ("gold_sma20_over_50", "<", 0)])
    R(20, "VIX_60D_UP_GOLD_60D_PULLBACK", "residual_slow_stress", 120, [("vix_change_60d", ">", 0), ("gold_ret_60d", "<", 0)])
    return rules


def entry_indices(mask: pd.Series, cooldown: int) -> List[int]:
    entries: List[int] = []
    last = -10**9
    for i, active in enumerate(mask.fillna(False).astype(bool).to_list()):
        if active and i - last >= cooldown:
            entries.append(i)
            last = i
    return entries


def calc_entry_returns(df: pd.DataFrame, rule: Rule, mask: pd.Series, cost_bps: float) -> List[Dict[str, Any]]:
    prices = pd.to_numeric(df["gold_close"], errors="coerce")
    rows: List[Dict[str, Any]] = []
    for i in entry_indices(mask, rule.cooldown):
        j = i + rule.horizon
        if j >= len(df):
            continue
        entry = prices.iloc[i]
        exitp = prices.iloc[j]
        if not (pd.notna(entry) and pd.notna(exitp) and entry != 0):
            continue
        gross = float((exitp / entry - 1.0) * 10000.0)
        net = gross - cost_bps
        rows.append({
            "rule_id": rule.rule_id,
            "label": rule.label,
            "bucket": rule.bucket,
            "entry_date": df["feature_date_utc"].iloc[i],
            "exit_date": df["feature_date_utc"].iloc[j],
            "horizon_trading_days": rule.horizon,
            "entry_price": float(entry),
            "exit_price": float(exitp),
            "gross_return_bps": round(gross, 4),
            "net_return_bps": round(net, 4),
            "win": bool(net > 0),
            "entry_year": int(str(df["feature_date_utc"].iloc[i])[:4]),
        })
    return rows


def metrics_for(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not entries:
        return {"entries": 0, "mean": None, "median": None, "win_rate": None, "min": None, "max": None, "total": 0.0}
    vals = pd.Series([float(e["net_return_bps"]) for e in entries])
    return {
        "entries": int(len(vals)),
        "mean": round(float(vals.mean()), 4),
        "median": round(float(vals.median()), 4),
        "win_rate": round(float((vals > 0).mean()), 4),
        "min": round(float(vals.min()), 4),
        "max": round(float(vals.max()), 4),
        "total": round(float(vals.sum()), 4),
    }


def split_entries(entries: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    out = {"train": [], "validation": [], "locked_forward": [], "final_holdout": [], "post_asof": []}
    for e in entries:
        d = str(e["entry_date"])
        if d <= "2014-12-31":
            out["train"].append(e)
        elif d <= "2018-12-31":
            out["validation"].append(e)
        elif d <= "2022-12-31":
            out["locked_forward"].append(e)
        else:
            out["final_holdout"].append(e)
        if d >= "2024-01-01":
            out["post_asof"].append(e)
    return out


def max_year_share(entries: List[Dict[str, Any]]) -> Tuple[Optional[int], float]:
    if not entries:
        return None, 0.0
    s = pd.Series([int(e["entry_year"]) for e in entries])
    vc = s.value_counts()
    return int(vc.index[0]), round(float(vc.iloc[0] / len(entries)), 4)


def latest_status(df: pd.DataFrame, rule: Rule, mask: pd.Series) -> Tuple[bool, str]:
    if len(df) == 0:
        return False, "no_rows"
    latest = df.iloc[-1]
    failures: List[str] = []
    for cond in rule.conditions:
        if cond.column not in df.columns:
            failures.append(f"missing:{cond.column}")
            continue
        val = latest[cond.column]
        try:
            v = float(val)
        except Exception:
            failures.append(f"{cond.column}:nan")
            continue
        passed = bool(eval_condition(pd.Series([v]), cond.op, cond.threshold).iloc[0])
        if not passed:
            failures.append(f"{cond.column}:{v}{cond.op}{cond.threshold}")
    return bool(mask.iloc[-1]) if len(mask) else False, "|".join(failures)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = root / config_path
    cfg = read_json(config_path)
    out = Path(args.out)
    if not out.is_absolute():
        out = root / out
    out.mkdir(parents=True, exist_ok=True)

    macro_path = Path(cfg.get("macro_dataset", "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv"))
    if not macro_path.is_absolute():
        macro_path = root / macro_path
    cost_bps = float(cfg.get("cost_bps_total_reference", 50.0))
    constraints = cfg.get("constraints", {})

    df = load_macro(macro_path)
    derived = add_derived_features(df)

    current_masks: Dict[str, pd.Series] = {}
    current_union = pd.Series(False, index=df.index)
    for r in current_portfolio_rules():
        m, _, _, _ = rule_mask(df, r)
        current_masks[r.rule_id] = m
        current_union = current_union | m

    candidate_rows: List[Dict[str, Any]] = []
    selected_rows: List[Dict[str, Any]] = []
    entry_rows_all: List[Dict[str, Any]] = []
    missing_rows: List[Dict[str, Any]] = []

    for rule in residual_candidate_rules():
        mask, missing_cols, warmup_missing, first_complete_idx = rule_mask(df, rule)
        active_days = int(mask.sum())
        overlap_days = int((mask & current_union).sum())
        incremental_days = int((mask & ~current_union).sum())
        overlap_pct = round(float(overlap_days / active_days * 100.0), 4) if active_days else 0.0
        residual_active_share = round(float(incremental_days / active_days), 4) if active_days else 0.0
        entries = calc_entry_returns(df, rule, mask, cost_bps)
        entry_rows_all.extend(entries)
        total = metrics_for(entries)
        splits = split_entries(entries)
        sm = {k: metrics_for(v) for k, v in splits.items()}
        max_year, year_share = max_year_share(entries)
        latest_active, latest_failures = latest_status(df, rule, mask)

        fail: List[str] = []
        if missing_cols:
            fail.append("MISSING_COLUMNS")
            for c in missing_cols:
                missing_rows.append({"rule_id": rule.rule_id, "missing_column": c})
        if total["entries"] < int(constraints.get("min_total_entries", 8)):
            fail.append("TOTAL_ENTRIES_TOO_LOW")
        if (total["mean"] is None) or total["mean"] < float(constraints.get("min_total_mean_bps", 150)):
            fail.append("TOTAL_MEAN_TOO_LOW")
        if (total["win_rate"] is None) or total["win_rate"] < float(constraints.get("min_total_win_rate", 0.55)):
            fail.append("WIN_RATE_TOO_LOW")
        if total["min"] is not None and abs(float(total["min"])) > float(constraints.get("max_abs_worst_loss_bps", 2200)):
            fail.append("WORST_LOSS_TOO_LARGE")
        if sm["locked_forward"]["entries"] < int(constraints.get("min_locked_forward_entries", 2)):
            fail.append("LOCKED_FORWARD_ENTRIES_TOO_LOW")
        if (sm["locked_forward"]["mean"] is None) or sm["locked_forward"]["mean"] < float(constraints.get("min_locked_forward_mean_bps", 0)):
            fail.append("LOCKED_FORWARD_MEAN_TOO_LOW")
        if sm["final_holdout"]["entries"] < int(constraints.get("min_final_holdout_entries", 2)):
            fail.append("FINAL_HOLDOUT_ENTRIES_TOO_LOW")
        if (sm["final_holdout"]["mean"] is None) or sm["final_holdout"]["mean"] < float(constraints.get("min_final_holdout_mean_bps", 500)):
            fail.append("FINAL_HOLDOUT_MEAN_TOO_LOW")
        if sm["post_asof"]["entries"] < int(constraints.get("min_post_asof_entries", 1)):
            fail.append("POST_ASOF_ENTRIES_TOO_LOW")
        if (sm["post_asof"]["mean"] is None) or sm["post_asof"]["mean"] < float(constraints.get("min_post_asof_mean_bps", 500)):
            fail.append("POST_ASOF_MEAN_TOO_LOW")
        if overlap_pct > float(constraints.get("max_overlap_with_current_union_pct", 35.0)):
            fail.append("OVERLAP_WITH_CURRENT_TOO_HIGH")
        if incremental_days < int(constraints.get("min_incremental_union_active_days", 100)):
            fail.append("INCREMENTAL_DAYS_TOO_LOW")
        if year_share > float(constraints.get("max_year_entry_share", 0.35)):
            fail.append("YEAR_CONCENTRATION_TOO_HIGH")

        score = 0.0
        if total["mean"] is not None:
            score += float(total["mean"])
        if sm["final_holdout"]["mean"] is not None:
            score += 1.2 * float(sm["final_holdout"]["mean"])
        if sm["post_asof"]["mean"] is not None:
            score += 1.2 * float(sm["post_asof"]["mean"])
        score += incremental_days * 1.0
        score -= overlap_pct * 20.0
        if total["min"] is not None:
            score += max(float(total["min"]), -2500.0) * 0.25

        row = {
            "rule_id": rule.rule_id,
            "label": rule.label,
            "bucket": rule.bucket,
            "horizon_trading_days": rule.horizon,
            "cooldown_trading_days": rule.cooldown,
            "condition_text": rule.condition_text(),
            "missing_columns": "|".join(missing_cols),
            "warmup_missing_rows_ignored": warmup_missing,
            "first_complete_required_row_index": first_complete_idx,
            "active_days": active_days,
            "current_union_active_days": int(current_union.sum()),
            "overlap_days_with_current_union": overlap_days,
            "incremental_union_active_days": incremental_days,
            "overlap_with_current_union_pct": overlap_pct,
            "residual_active_share": residual_active_share,
            "latest_signal_active": latest_active,
            "latest_failures": latest_failures,
            "total_entry_count": total["entries"],
            "total_mean_net_bps": total["mean"],
            "total_median_net_bps": total["median"],
            "total_win_rate": total["win_rate"],
            "total_min_net_return_bps": total["min"],
            "total_max_net_return_bps": total["max"],
            "total_total_net_return_bps": total["total"],
            "train_entries": sm["train"]["entries"],
            "train_mean_net_bps": sm["train"]["mean"],
            "validation_entries": sm["validation"]["entries"],
            "validation_mean_net_bps": sm["validation"]["mean"],
            "locked_forward_entries": sm["locked_forward"]["entries"],
            "locked_forward_mean_net_bps": sm["locked_forward"]["mean"],
            "final_holdout_entries": sm["final_holdout"]["entries"],
            "final_holdout_mean_net_bps": sm["final_holdout"]["mean"],
            "post_asof_entries": sm["post_asof"]["entries"],
            "post_asof_mean_net_bps": sm["post_asof"]["mean"],
            "max_entry_year": max_year,
            "max_year_entry_share": year_share,
            "pass_residual_discovery_candidate": len(fail) == 0,
            "fail_reasons": "|".join(fail),
            "residual_discovery_score": round(score, 4),
        }
        candidate_rows.append(row)

    pass_rows = [r for r in candidate_rows if r["pass_residual_discovery_candidate"]]
    pass_rows.sort(key=lambda r: float(r["residual_discovery_score"]), reverse=True)
    shortlist = pass_rows[: int(cfg.get("shortlist_limit", 8))]

    decision = "NO_RESIDUAL_THESIS_SHORTLIST_NO_ORDER"
    classification = "S89_NO_RESIDUAL_SHORTLIST"
    disposition = "NO_RESIDUAL_THESIS_SHORTLIST"
    if shortlist:
        decision = "RESIDUAL_THESIS_SHORTLIST_READY_FOR_HARD_AUDIT_NO_ORDER"
        classification = "S89_RESIDUAL_THESIS_SHORTLIST_READY"
        disposition = "RESIDUAL_THESIS_SHORTLIST_READY_FOR_STAGE90_HARD_AUDIT"

    candidate_rows.sort(key=lambda r: float(r["residual_discovery_score"]), reverse=True)
    candidate_csv = out / "stage89_residual_candidate_metrics.csv"
    shortlist_csv = out / "stage89_residual_discovery_shortlist.csv"
    entry_csv = out / "stage89_residual_entry_returns.csv"
    missing_csv = out / "stage89_residual_missing_data_requirements.csv"
    write_csv(candidate_csv, candidate_rows)
    write_csv(shortlist_csv, shortlist)
    write_csv(entry_csv, entry_rows_all)
    write_csv(missing_csv, missing_rows)

    summary = {
        "stage": "Stage89_RESIDUAL_REGIME_THESIS_DISCOVERY",
        "root": str(root),
        "config": str(config_path),
        "generated_utc": utc_now(),
        "status": "STAGE89_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
        "principle": "Search thesis-first candidates that add residual exposure when the Stage86 unified observer portfolio is inactive. No orders and no MT5/EA change.",
        "macro_dataset": {
            "path": str(macro_path),
            "rows": int(len(df)),
            "date_col": "feature_date_utc",
            "price_col": "gold_close",
            "min_date": str(df["feature_date_utc"].min()),
            "max_date": str(df["feature_date_utc"].max()),
            "sha256": sha256_file(macro_path),
            "derived_features_added": derived,
        },
        "current_unified_portfolio_rule_ids": [r.rule_id for r in current_portfolio_rules()],
        "current_union_active_days": int(current_union.sum()),
        "candidate_count": len(candidate_rows),
        "pass_candidate_count": len(pass_rows),
        "shortlist_count": len(shortlist),
        "shortlist_rule_ids": [r["rule_id"] for r in shortlist],
        "shortlist": shortlist,
        "latest_feature_date_utc": str(df["feature_date_utc"].iloc[-1]) if len(df) else None,
        "constraints": constraints,
        "hard_blocks": [
            "NO_AUTOMATED_ORDER",
            "NO_PAPER_ORDER",
            "NO_BROKER_CONNECTION",
            "NO_EA_PROMOTION",
            "NO_PAPER_LIVE",
            "NO_LIVE",
            "NO_ORDER_AUTHORIZATION_FROM_STAGE89",
            "NO_THRESHOLD_TUNING_FROM_STAGE89_DISCOVERY",
            "NO_DIRECT_MT5_OR_EA_CHANGE_FROM_STAGE89",
        ],
        "outputs": {
            "summary_json": str(out / "stage89_residual_regime_thesis_discovery_summary.json"),
            "report_md": str(out / "stage89_residual_regime_thesis_discovery_report.md"),
            "candidate_metrics_csv": str(candidate_csv),
            "shortlist_csv": str(shortlist_csv),
            "entry_returns_csv": str(entry_csv),
            "missing_data_requirements_csv": str(missing_csv),
        },
    }

    write_json(out / "stage89_residual_regime_thesis_discovery_summary.json", summary)
    report_lines = [
        "# Stage89 Residual Regime Thesis Discovery",
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
        "## Current unified observer portfolio",
    ]
    for rid in summary["current_unified_portfolio_rule_ids"]:
        report_lines.append(f"- `{rid}`")
    report_lines += ["", "## Shortlist"]
    if shortlist:
        for r in shortlist:
            report_lines.append(
                f"- `{r['rule_id']}`: {r['label']} score=`{r['residual_discovery_score']}` "
                f"mean=`{r['total_mean_net_bps']}` final=`{r['final_holdout_mean_net_bps']}` "
                f"post_asof=`{r['post_asof_mean_net_bps']}` overlap=`{r['overlap_with_current_union_pct']}` "
                f"incremental_days=`{r['incremental_union_active_days']}` latest_active=`{r['latest_signal_active']}`"
            )
    else:
        report_lines.append("- none")
    report_lines += ["", "## Candidate snapshot"]
    for r in candidate_rows[:12]:
        report_lines.append(
            f"- `{r['rule_id']}` pass=`{r['pass_residual_discovery_candidate']}` score=`{r['residual_discovery_score']}` "
            f"mean=`{r['total_mean_net_bps']}` win=`{r['total_win_rate']}` worst=`{r['total_min_net_return_bps']}` "
            f"overlap=`{r['overlap_with_current_union_pct']}` incremental_days=`{r['incremental_union_active_days']}` fail=`{r['fail_reasons']}`"
        )
    report_lines += ["", "## Hard blocks"]
    for hb in summary["hard_blocks"]:
        report_lines.append(f"- `{hb}`")
    (out / "stage89_residual_regime_thesis_discovery_report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print(json.dumps({
        "stage": summary["stage"],
        "status": summary["status"],
        "decision": decision,
        "classification": classification,
        "shortlist_count": len(shortlist),
        "summary_json": summary["outputs"]["summary_json"],
        "report_md": summary["outputs"]["report_md"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
