#!/usr/bin/env python3
"""Stage70B Champion Hard Audit.

No-order, no-broker hard audit for one locked champion thesis:
K06_RESILIENT_GOLD_VS_DXY / H120.

The script deliberately does not scan for new candidates or tune thresholds.
It returns one of:
- PROMOTE_TO_NO_ORDER_SHADOW_CANDIDATE
- KILL_CHAMPION_CLOSE_STAGE70
- AMBIGUOUS_ONE_DIAGNOSTIC_ONLY
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


PROMOTE = "PROMOTE_TO_NO_ORDER_SHADOW_CANDIDATE"
KILL = "KILL_CHAMPION_CLOSE_STAGE70"
AMBIGUOUS = "AMBIGUOUS_ONE_DIAGNOSTIC_ONLY"


@dataclass(frozen=True)
class RuleSpec:
    rule_key: str
    label: str
    horizon: int
    conditions: List[Dict[str, Any]]
    cost_bps_total: float


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def pick_date_col(df: pd.DataFrame, candidates: Iterable[str]) -> str:
    for c in candidates:
        if c in df.columns:
            return c
    raise ValueError(f"No date column found from candidates: {list(candidates)}")


def normalize_macro(df: pd.DataFrame, date_col: str, price_col: str) -> pd.DataFrame:
    out = df.copy()
    out[date_col] = pd.to_datetime(out[date_col], errors="coerce", utc=True).dt.tz_convert(None)
    out = out[out[date_col].notna()].copy()
    out = out.sort_values(date_col).drop_duplicates(date_col, keep="last").reset_index(drop=True)
    if price_col not in out.columns:
        raise ValueError(f"Missing price column: {price_col}")
    out[price_col] = pd.to_numeric(out[price_col], errors="coerce")
    out = out[out[price_col].notna()].copy().reset_index(drop=True)
    return out


def compare_series(s: pd.Series, op: str, threshold: float) -> pd.Series:
    vals = pd.to_numeric(s, errors="coerce")
    if op == ">":
        return vals > threshold
    if op == ">=":
        return vals >= threshold
    if op == "<":
        return vals < threshold
    if op == "<=":
        return vals <= threshold
    if op == "==":
        return vals == threshold
    raise ValueError(f"Unsupported operator: {op}")


def rule_mask(df: pd.DataFrame, conditions: List[Dict[str, Any]]) -> Tuple[pd.Series, List[str]]:
    mask = pd.Series(True, index=df.index)
    missing: List[str] = []
    for cond in conditions:
        col = cond["column"]
        if col not in df.columns:
            missing.append(col)
            mask &= False
            continue
        mask &= compare_series(df[col], cond["operator"], float(cond["threshold"]))
    return mask.fillna(False), missing


def latest_rule_snapshot(df: pd.DataFrame, conditions: List[Dict[str, Any]], date_col: str) -> Dict[str, Any]:
    if df.empty:
        return {"signal_active": False, "condition_results": [], "rule_failures": ["EMPTY_DATASET"]}
    row = df.iloc[-1]
    results: List[Dict[str, Any]] = []
    failures: List[str] = []
    active = True
    for cond in conditions:
        col = cond["column"]
        op = cond["operator"]
        threshold = float(cond["threshold"])
        if col not in df.columns:
            active = False
            failures.append(f"MISSING:{col}")
            results.append({"column": col, "operator": op, "threshold": threshold, "value": None, "passed": False})
            continue
        value = pd.to_numeric(pd.Series([row[col]]), errors="coerce").iloc[0]
        if pd.isna(value):
            active = False
            failures.append(f"NA:{col}")
            passed = False
        else:
            passed = bool(compare_series(pd.Series([value]), op, threshold).iloc[0])
            if not passed:
                active = False
                failures.append(f"{col}:{value}{op}{threshold}")
        results.append({"column": col, "operator": op, "threshold": threshold, "value": None if pd.isna(value) else float(value), "passed": passed})
    return {
        "latest_feature_date_utc": str(pd.Timestamp(row[date_col]).date()),
        "signal_active": bool(active),
        "condition_results": results,
        "rule_failures": failures,
    }


def build_entries(
    df: pd.DataFrame,
    date_col: str,
    price_col: str,
    rule_key: str,
    label: str,
    conditions: List[Dict[str, Any]],
    horizon: int,
    cost_bps_total: float,
    cooldown: Optional[int] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    mask, missing = rule_mask(df, conditions)
    active_idx = [int(i) for i in df.index[mask].tolist()]
    cooldown = horizon if cooldown is None else cooldown
    rows: List[Dict[str, Any]] = []
    i = 0
    while i < len(active_idx):
        idx = active_idx[i]
        exit_idx = idx + horizon
        if exit_idx >= len(df):
            break
        entry_px = float(df.at[idx, price_col])
        exit_px = float(df.at[exit_idx, price_col])
        if not (math.isfinite(entry_px) and math.isfinite(exit_px) and entry_px > 0):
            i += 1
            continue
        gross = (exit_px / entry_px - 1.0) * 10000.0
        net = gross - cost_bps_total
        entry_date = pd.Timestamp(df.at[idx, date_col])
        exit_date = pd.Timestamp(df.at[exit_idx, date_col])
        rows.append(
            {
                "rule_key": rule_key,
                "label": label,
                "entry_idx": idx,
                "exit_idx": exit_idx,
                "entry_date": str(entry_date.date()),
                "exit_date": str(exit_date.date()),
                "horizon_trading_days": horizon,
                "entry_price": entry_px,
                "exit_price": exit_px,
                "gross_return_bps": round(gross, 6),
                "net_return_bps": round(net, 6),
                "year": int(entry_date.year),
                "month": int(entry_date.month),
            }
        )
        next_allowed = idx + cooldown
        while i < len(active_idx) and active_idx[i] < next_allowed:
            i += 1
    entries = pd.DataFrame(rows)
    meta = {
        "missing_columns": missing,
        "active_days": int(mask.sum()) if not missing else 0,
        "active_pct_of_evaluable": round(float(mask.sum()) / max(len(df), 1) * 100.0, 4) if not missing else 0.0,
        "entry_count": int(len(entries)),
    }
    return entries, meta


def safe_mean(vals: pd.Series) -> Optional[float]:
    vals = pd.to_numeric(vals, errors="coerce").dropna()
    if vals.empty:
        return None
    return round(float(vals.mean()), 4)


def safe_median(vals: pd.Series) -> Optional[float]:
    vals = pd.to_numeric(vals, errors="coerce").dropna()
    if vals.empty:
        return None
    return round(float(vals.median()), 4)


def max_drawdown_from_bps(entries: pd.DataFrame, exposure_fraction: float = 1.0) -> Optional[float]:
    if entries.empty:
        return None
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in pd.to_numeric(entries["net_return_bps"], errors="coerce").dropna():
        equity *= 1.0 + exposure_fraction * float(r) / 10000.0
        peak = max(peak, equity)
        dd = (equity / peak - 1.0) * 100.0
        max_dd = min(max_dd, dd)
    return round(float(max_dd), 4)


def metrics_for_entries(entries: pd.DataFrame) -> Dict[str, Any]:
    if entries.empty:
        return {
            "entry_count": 0,
            "mean_net_return_bps": None,
            "median_net_return_bps": None,
            "win_rate": None,
            "min_net_return_bps": None,
            "max_net_return_bps": None,
            "total_net_return_bps": 0.0,
            "worst_3_entry_sum_bps": None,
            "max_drawdown_full_notional_pct": None,
        }
    net = pd.to_numeric(entries["net_return_bps"], errors="coerce").dropna()
    worst3 = net.sort_values().head(min(3, len(net))).sum() if not net.empty else None
    return {
        "entry_count": int(len(net)),
        "mean_net_return_bps": safe_mean(net),
        "median_net_return_bps": safe_median(net),
        "win_rate": round(float((net > 0).mean()), 4) if len(net) else None,
        "min_net_return_bps": round(float(net.min()), 4) if len(net) else None,
        "max_net_return_bps": round(float(net.max()), 4) if len(net) else None,
        "total_net_return_bps": round(float(net.sum()), 4) if len(net) else 0.0,
        "worst_3_entry_sum_bps": round(float(worst3), 4) if worst3 is not None else None,
        "max_drawdown_full_notional_pct": max_drawdown_from_bps(entries),
    }


def period_metrics(entries: pd.DataFrame, periods: List[Dict[str, Any]]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    if entries.empty:
        return pd.DataFrame(rows)
    e = entries.copy()
    e["entry_dt"] = pd.to_datetime(e["entry_date"], errors="coerce")
    for p in periods:
        start = pd.Timestamp(p["start"])
        end = pd.Timestamp(p["end"])
        sub = e[(e["entry_dt"] >= start) & (e["entry_dt"] <= end)]
        m = metrics_for_entries(sub)
        rows.append({"period_id": p["period_id"], "start": p["start"], "end": p["end"], **m})
    return pd.DataFrame(rows)


def yearly_metrics(entries: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    if entries.empty:
        return pd.DataFrame(rows)
    for year, sub in entries.groupby("year"):
        rows.append({"year": int(year), **metrics_for_entries(sub)})
    return pd.DataFrame(rows).sort_values("year")


def positive_share(metric_df: pd.DataFrame, count_col: str = "entry_count") -> Optional[float]:
    if metric_df.empty or "total_net_return_bps" not in metric_df.columns:
        return None
    sub = metric_df[pd.to_numeric(metric_df[count_col], errors="coerce").fillna(0) > 0]
    if sub.empty:
        return None
    return round(float((pd.to_numeric(sub["total_net_return_bps"], errors="coerce") > 0).mean()), 4)


def max_year_share(entries: pd.DataFrame) -> Optional[float]:
    if entries.empty:
        return None
    vc = entries["year"].value_counts()
    return round(float(vc.max() / vc.sum()), 4) if vc.sum() else None


def recent_period_share(period_df: pd.DataFrame) -> Optional[float]:
    if period_df.empty:
        return None
    totals = pd.to_numeric(period_df["total_net_return_bps"], errors="coerce").fillna(0.0)
    total = totals.sum()
    if total <= 0:
        return None
    return round(float(totals.iloc[-1] / total), 4)


def leave_one_period_out(entries: pd.DataFrame, periods: List[Dict[str, Any]]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    if entries.empty:
        return pd.DataFrame(rows)
    e = entries.copy()
    e["entry_dt"] = pd.to_datetime(e["entry_date"], errors="coerce")
    for p in periods:
        start = pd.Timestamp(p["start"])
        end = pd.Timestamp(p["end"])
        keep = ~((e["entry_dt"] >= start) & (e["entry_dt"] <= end))
        sub = e[keep]
        rows.append({"left_out_period_id": p["period_id"], **metrics_for_entries(sub)})
    return pd.DataFrame(rows)


def stress_cost_table(entries: pd.DataFrame, base_cost: float, stress_costs: List[float]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    if entries.empty:
        return pd.DataFrame(rows)
    gross = pd.to_numeric(entries["gross_return_bps"], errors="coerce")
    for c in stress_costs:
        tmp = entries.copy()
        tmp["net_return_bps"] = gross - float(c)
        m = metrics_for_entries(tmp)
        rows.append({"cost_bps_total": float(c), **m})
    return pd.DataFrame(rows)


def outlier_sensitivity(entries: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    if entries.empty:
        return pd.DataFrame(rows)
    net = pd.to_numeric(entries["net_return_bps"], errors="coerce")
    cases = {"base": entries}
    if len(entries) >= 3:
        cases["drop_best_1"] = entries.drop(index=net.idxmax())
        cases["drop_worst_1"] = entries.drop(index=net.idxmin())
        cases["drop_best_and_worst_1"] = entries.drop(index=[net.idxmax(), net.idxmin()])
    for name, sub in cases.items():
        rows.append({"case_id": name, **metrics_for_entries(sub)})
    return pd.DataFrame(rows)


def active_day_set(df: pd.DataFrame, conditions: List[Dict[str, Any]], date_col: str) -> set:
    mask, missing = rule_mask(df, conditions)
    if missing:
        return set()
    return set(str(pd.Timestamp(x).date()) for x in df.loc[mask, date_col].tolist())


def jaccard(a: set, b: set) -> Optional[float]:
    if not a and not b:
        return None
    union = len(a | b)
    if union == 0:
        return None
    return round(float(len(a & b) / union * 100.0), 4)


def build_rule(rule_key: str, label: str, horizon: int, conditions: List[Dict[str, Any]], cost: float) -> RuleSpec:
    return RuleSpec(rule_key=rule_key, label=label, horizon=horizon, conditions=conditions, cost_bps_total=cost)


def evaluate_decision(
    champion_metrics: Dict[str, Any],
    period_df: pd.DataFrame,
    yearly_df: pd.DataFrame,
    leave_df: pd.DataFrame,
    stress_df: pd.DataFrame,
    benchmark_overlap_df: pd.DataFrame,
    constraints: Dict[str, Any],
) -> Tuple[str, str, List[str], List[str]]:
    hard_fails: List[str] = []
    cautions: List[str] = []

    def val(name: str) -> Optional[float]:
        v = champion_metrics.get(name)
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return None
        return float(v)

    entry_count = val("entry_count") or 0
    mean_net = val("mean_net_return_bps")
    median_net = val("median_net_return_bps")
    win_rate = val("win_rate")
    min_net = val("min_net_return_bps")

    if entry_count < float(constraints["min_entry_count"]):
        hard_fails.append(f"ENTRY_COUNT_BELOW_MIN:{entry_count}<{constraints['min_entry_count']}")
    if mean_net is None or mean_net < float(constraints["min_mean_net_return_bps"]):
        hard_fails.append(f"MEAN_NET_BELOW_MIN:{mean_net}<{constraints['min_mean_net_return_bps']}")
    if median_net is None or median_net < float(constraints["min_median_net_return_bps"]):
        hard_fails.append(f"MEDIAN_NET_BELOW_MIN:{median_net}<{constraints['min_median_net_return_bps']}")
    if win_rate is None or win_rate < float(constraints["min_win_rate"]):
        hard_fails.append(f"WIN_RATE_BELOW_MIN:{win_rate}<{constraints['min_win_rate']}")
    if min_net is None or abs(min_net) > float(constraints["max_abs_min_net_return_bps"]):
        cautions.append(f"MIN_LOSS_ABS_ABOVE_LIMIT:{min_net}>{constraints['max_abs_min_net_return_bps']}")

    pos_period = positive_share(period_df)
    if pos_period is None or pos_period < float(constraints["min_positive_period_share"]):
        hard_fails.append(f"POSITIVE_PERIOD_SHARE_BELOW_MIN:{pos_period}<{constraints['min_positive_period_share']}")

    pos_year = positive_share(yearly_df)
    if pos_year is None or pos_year < float(constraints["min_positive_year_share"]):
        hard_fails.append(f"POSITIVE_YEAR_SHARE_BELOW_MIN:{pos_year}<{constraints['min_positive_year_share']}")

    mys = max_year_share_from_yearly(yearly_df)
    if mys is None or mys > float(constraints["max_year_entry_share"]):
        hard_fails.append(f"MAX_YEAR_ENTRY_SHARE_ABOVE_LIMIT:{mys}>{constraints['max_year_entry_share']}")

    recent_share = recent_period_share(period_df)
    if recent_share is not None and recent_share > float(constraints["max_recent_period_share_of_total_return"]):
        hard_fails.append(f"RECENT_PERIOD_SHARE_ABOVE_LIMIT:{recent_share}>{constraints['max_recent_period_share_of_total_return']}")

    min_leave_mean = None
    if not leave_df.empty and "mean_net_return_bps" in leave_df.columns:
        s = pd.to_numeric(leave_df["mean_net_return_bps"], errors="coerce").dropna()
        if not s.empty:
            min_leave_mean = round(float(s.min()), 4)
    if min_leave_mean is None or min_leave_mean < float(constraints["min_leave_one_period_out_mean_bps"]):
        hard_fails.append(f"LEAVE_ONE_PERIOD_OUT_MEAN_BELOW_MIN:{min_leave_mean}<{constraints['min_leave_one_period_out_mean_bps']}")

    mean_150 = None
    if not stress_df.empty:
        row = stress_df[pd.to_numeric(stress_df["cost_bps_total"], errors="coerce") == 150.0]
        if not row.empty:
            mean_150 = float(row.iloc[0].get("mean_net_return_bps"))
    if mean_150 is None or mean_150 < float(constraints["min_mean_net_bps_at_150_cost"]):
        hard_fails.append(f"STRESS_150_COST_MEAN_BELOW_MIN:{mean_150}<{constraints['min_mean_net_bps_at_150_cost']}")

    if not benchmark_overlap_df.empty and "jaccard_active_day_overlap_pct" in benchmark_overlap_df.columns:
        max_overlap = pd.to_numeric(benchmark_overlap_df["jaccard_active_day_overlap_pct"], errors="coerce").dropna()
        if not max_overlap.empty and max_overlap.max() > float(constraints["max_benchmark_overlap_jaccard_pct"]):
            cautions.append(f"HIGH_BENCHMARK_OVERLAP:{round(float(max_overlap.max()),4)}>{constraints['max_benchmark_overlap_jaccard_pct']}")

    # Decision: hard failures kill only if structural; otherwise ambiguous if limited fails/cautions.
    if not hard_fails and not cautions:
        return PROMOTE, "S70B_PROMOTE_TO_NO_ORDER_SHADOW_CANDIDATE", hard_fails, cautions
    if len(hard_fails) >= 3 or any(x.startswith("MEAN_NET_BELOW") or x.startswith("ENTRY_COUNT_BELOW") for x in hard_fails):
        return KILL, "S70B_KILL_CHAMPION_CLOSE_STAGE70", hard_fails, cautions
    return AMBIGUOUS, "S70B_AMBIGUOUS_ONE_DIAGNOSTIC_ONLY", hard_fails, cautions


def max_year_share_from_yearly(yearly_df: pd.DataFrame) -> Optional[float]:
    if yearly_df.empty or "entry_count" not in yearly_df.columns:
        return None
    counts = pd.to_numeric(yearly_df["entry_count"], errors="coerce").fillna(0.0)
    total = counts.sum()
    if total <= 0:
        return None
    return round(float(counts.max() / total), 4)


def write_df(df: pd.DataFrame, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return str(path)


def markdown_report(summary: Dict[str, Any]) -> str:
    champ = summary["champion"]
    m = summary["champion_metrics"]
    constraints = summary["decision_constraints"]
    lines = [
        "# Stage70B Champion Hard Audit",
        "",
        "## Decision",
        f"- status: `{summary['status']}`",
        f"- decision: `{summary['decision']}`",
        f"- classification: `{summary['classification']}`",
        f"- disposition: `{summary['disposition']}`",
        "",
        "## Champion",
        f"- thesis_id: `{champ['thesis_id']}`",
        f"- family: `{champ['family']}`",
        f"- horizon_trading_days: `{champ['horizon_trading_days']}`",
        f"- conditions: `{champ['conditions_text']}`",
        "",
        "## Champion metrics",
        f"- entry_count: `{m['entry_count']}`",
        f"- mean_net_return_bps: `{m['mean_net_return_bps']}`",
        f"- median_net_return_bps: `{m['median_net_return_bps']}`",
        f"- win_rate: `{m['win_rate']}`",
        f"- min_net_return_bps: `{m['min_net_return_bps']}`",
        f"- max_net_return_bps: `{m['max_net_return_bps']}`",
        f"- total_net_return_bps: `{m['total_net_return_bps']}`",
        f"- max_drawdown_full_notional_pct: `{m['max_drawdown_full_notional_pct']}`",
        "",
        "## Robustness summary",
        f"- positive_period_share: `{summary['robustness_metrics']['positive_period_share']}`",
        f"- positive_year_share: `{summary['robustness_metrics']['positive_year_share']}`",
        f"- max_year_entry_share: `{summary['robustness_metrics']['max_year_entry_share']}`",
        f"- recent_period_share_of_total_return: `{summary['robustness_metrics']['recent_period_share_of_total_return']}`",
        f"- min_leave_one_period_out_mean_bps: `{summary['robustness_metrics']['min_leave_one_period_out_mean_bps']}`",
        f"- mean_net_bps_at_150_cost: `{summary['robustness_metrics']['mean_net_bps_at_150_cost']}`",
        "",
        "## Latest signal snapshot",
        f"- latest_feature_date_utc: `{summary['latest_signal_snapshot'].get('latest_feature_date_utc')}`",
        f"- signal_active: `{summary['latest_signal_snapshot'].get('signal_active')}`",
        f"- rule_failures: `{'; '.join(summary['latest_signal_snapshot'].get('rule_failures', []))}`",
        "",
        "## Issues",
    ]
    if summary["hard_failures"]:
        lines.extend([f"- `{x}`" for x in summary["hard_failures"]])
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Cautions")
    if summary["cautions"]:
        lines.extend([f"- `{x}`" for x in summary["cautions"]])
    else:
        lines.append("- none")
    lines.extend([
        "",
        "## Backlog policy",
        "- Backlog items are registered but cannot interrupt the champion audit path.",
        "- No new megascan is allowed until this champion is promoted, killed, or parked with a reason.",
        "",
        "## Decision constraints",
    ])
    for k, v in constraints.items():
        lines.append(f"- `{k}`: `{v}`")
    lines.extend(["", "## Hard blocks"])
    lines.extend([f"- `{x}`" for x in summary["hard_blocks"]])
    return "\n".join(lines) + "\n"


def run(root: Path, config_path: Path, out_dir: Path) -> Dict[str, Any]:
    config = load_json(config_path)
    root = root.resolve()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    champion_cfg = config["champion"]
    macro_path = root / config["macro_dataset_path"]
    if not macro_path.exists():
        raise FileNotFoundError(f"Macro dataset not found: {macro_path}")

    raw = pd.read_csv(macro_path)
    date_col = pick_date_col(raw, champion_cfg["date_column_candidates"])
    price_col = champion_cfg["entry_price_column"]
    df = normalize_macro(raw, date_col, price_col)

    champ_rule = build_rule(
        "K06_RESILIENT_GOLD_VS_DXY",
        "K06 Resilient Gold vs DXY",
        int(champion_cfg["horizon_trading_days"]),
        champion_cfg["conditions"],
        float(champion_cfg["cost_bps_total"]),
    )
    entries, activity_meta = build_entries(
        df=df,
        date_col=date_col,
        price_col=price_col,
        rule_key=champ_rule.rule_key,
        label=champ_rule.label,
        conditions=champ_rule.conditions,
        horizon=champ_rule.horizon,
        cost_bps_total=champ_rule.cost_bps_total,
        cooldown=int(champion_cfg.get("entry_cooldown_trading_days", champ_rule.horizon)),
    )

    champion_metrics = metrics_for_entries(entries)
    period_df = period_metrics(entries, config["periods"])
    yearly_df = yearly_metrics(entries)
    leave_df = leave_one_period_out(entries, config["periods"])
    stress_df = stress_cost_table(entries, champ_rule.cost_bps_total, config["stress_cost_bps"])
    outlier_df = outlier_sensitivity(entries)

    champion_active_set = active_day_set(df, champ_rule.conditions, date_col)
    benchmark_rows: List[Dict[str, Any]] = []
    for b in config.get("benchmark_rules", []):
        b_entries, b_meta = build_entries(
            df=df,
            date_col=date_col,
            price_col=price_col,
            rule_key=b["rule_key"],
            label=b["label"],
            conditions=b["conditions"],
            horizon=int(b["horizon_trading_days"]),
            cost_bps_total=champ_rule.cost_bps_total,
            cooldown=int(b["horizon_trading_days"]),
        )
        b_set = active_day_set(df, b["conditions"], date_col)
        b_metrics = metrics_for_entries(b_entries)
        benchmark_rows.append(
            {
                "benchmark_rule_key": b["rule_key"],
                "benchmark_label": b["label"],
                "benchmark_horizon_trading_days": int(b["horizon_trading_days"]),
                "benchmark_active_days": len(b_set),
                "champion_active_days": len(champion_active_set),
                "intersection_active_days": len(champion_active_set & b_set),
                "jaccard_active_day_overlap_pct": jaccard(champion_active_set, b_set),
                **{f"benchmark_{k}": v for k, v in b_metrics.items()},
            }
        )
    benchmark_df = pd.DataFrame(benchmark_rows)

    latest_snapshot = latest_rule_snapshot(df, champ_rule.conditions, date_col)

    decision, classification, hard_fails, cautions = evaluate_decision(
        champion_metrics=champion_metrics,
        period_df=period_df,
        yearly_df=yearly_df,
        leave_df=leave_df,
        stress_df=stress_df,
        benchmark_overlap_df=benchmark_df,
        constraints=config["decision_constraints"],
    )

    pos_period = positive_share(period_df)
    pos_year = positive_share(yearly_df)
    mys = max_year_share_from_yearly(yearly_df)
    recent_share = recent_period_share(period_df)
    min_leave = None
    if not leave_df.empty:
        s = pd.to_numeric(leave_df["mean_net_return_bps"], errors="coerce").dropna()
        if not s.empty:
            min_leave = round(float(s.min()), 4)
    mean_150 = None
    row150 = stress_df[pd.to_numeric(stress_df.get("cost_bps_total", pd.Series(dtype=float)), errors="coerce") == 150.0] if not stress_df.empty else pd.DataFrame()
    if not row150.empty:
        mean_150 = round(float(row150.iloc[0]["mean_net_return_bps"]), 4)

    backlog_df = pd.DataFrame(config.get("backlog_register", []))

    paths = {
        "summary_json": str(out_dir / "stage70b_champion_hard_audit_summary.json"),
        "report_md": str(out_dir / "stage70b_champion_hard_audit_report.md"),
        "entry_returns_csv": write_df(entries, out_dir / "stage70b_champion_entry_returns.csv"),
        "period_metrics_csv": write_df(period_df, out_dir / "stage70b_champion_period_metrics.csv"),
        "yearly_metrics_csv": write_df(yearly_df, out_dir / "stage70b_champion_yearly_metrics.csv"),
        "leave_one_period_out_csv": write_df(leave_df, out_dir / "stage70b_champion_leave_one_period_out.csv"),
        "stress_cost_csv": write_df(stress_df, out_dir / "stage70b_champion_stress_cost.csv"),
        "outlier_sensitivity_csv": write_df(outlier_df, out_dir / "stage70b_champion_outlier_sensitivity.csv"),
        "benchmark_overlap_csv": write_df(benchmark_df, out_dir / "stage70b_champion_benchmark_overlap.csv"),
        "backlog_register_csv": write_df(backlog_df, out_dir / "stage70b_backlog_register.csv"),
    }

    summary: Dict[str, Any] = {
        "stage": "Stage70B_CHAMPION_HARD_AUDIT",
        "root": str(root),
        "config": str(config_path.resolve()),
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "STAGE70B_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "disposition": decision,
        "macro_dataset": {
            "path": str(macro_path),
            "rows_raw": int(len(raw)),
            "rows_used": int(len(df)),
            "date_col": date_col,
            "price_col": price_col,
            "min_date": str(pd.Timestamp(df[date_col].min()).date()) if not df.empty else None,
            "max_date": str(pd.Timestamp(df[date_col].max()).date()) if not df.empty else None,
            "sha256": sha256_file(macro_path),
        },
        "champion": {
            "thesis_id": champion_cfg["thesis_id"],
            "family": champion_cfg["family"],
            "direction": champion_cfg["direction"],
            "horizon_trading_days": int(champion_cfg["horizon_trading_days"]),
            "conditions_text": ";".join(f"{c['column']}{c['operator']}{c['threshold']}" for c in champion_cfg["conditions"]),
            "cost_bps_total": float(champion_cfg["cost_bps_total"]),
            "entry_cooldown_trading_days": int(champion_cfg.get("entry_cooldown_trading_days", champion_cfg["horizon_trading_days"])),
        },
        "activity_meta": activity_meta,
        "champion_metrics": champion_metrics,
        "robustness_metrics": {
            "positive_period_share": pos_period,
            "positive_year_share": pos_year,
            "max_year_entry_share": mys,
            "recent_period_share_of_total_return": recent_share,
            "min_leave_one_period_out_mean_bps": min_leave,
            "mean_net_bps_at_150_cost": mean_150,
        },
        "latest_signal_snapshot": latest_snapshot,
        "decision_constraints": config["decision_constraints"],
        "hard_failures": hard_fails,
        "cautions": cautions,
        "backlog_policy": {
            "mode": "CONTROLLED_BACKLOG_NON_INTERRUPTIVE",
            "registered_backlog_count": int(len(backlog_df)),
            "rule": "Backlog can be updated but cannot interrupt K06 until K06 is promoted, killed, or parked with reason.",
        },
        "hard_blocks": config["hard_blocks"],
        "operator_instructions": [
            "Stage70B is a no-order hard audit and cannot authorize orders.",
            "Do not tune thresholds from Stage70B.",
            "Do not open another megascan until this champion is closed, killed, or promoted to no-order shadow candidate.",
            "If decision is AMBIGUOUS_ONE_DIAGNOSTIC_ONLY, only one diagnostic package is allowed before final disposition.",
            "Broker, EA, paper-live, and live paths remain blocked.",
        ],
        "outputs": paths,
    }

    write_json(Path(paths["summary_json"]), summary)
    Path(paths["report_md"]).write_text(markdown_report(summary), encoding="utf-8")
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Stage70B Champion Hard Audit")
    ap.add_argument("--root", default=".", help="Repository root")
    ap.add_argument("--config", default="configs/stage70b_champion_hard_audit.json")
    ap.add_argument("--out", default="reports/stage70b_champion_hard_audit")
    args = ap.parse_args()
    summary = run(Path(args.root), Path(args.config), Path(args.out))
    print(json.dumps({
        "stage": summary["stage"],
        "status": summary["status"],
        "decision": summary["decision"],
        "classification": summary["classification"],
        "champion": summary["champion"]["thesis_id"],
        "summary_json": summary["outputs"]["summary_json"],
        "report_md": summary["outputs"]["report_md"],
    }, indent=2))


if __name__ == "__main__":
    main()
