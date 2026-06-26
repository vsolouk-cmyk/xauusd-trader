#!/usr/bin/env python3
"""Stage71 locked historical forward test for K06 and references.

Local-only, no-order, no-broker. It treats later historical periods as locked
pseudo-forward segments and explicitly separates final statistical holdout from
train/validation windows.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd


@dataclass(frozen=True)
class Rule:
    thesis_id: str
    family: str
    direction: str
    horizon: int
    cooldown: int
    cost_bps: float
    conditions: List[Dict[str, Any]]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def find_col(columns: Iterable[str], candidates: List[str]) -> Optional[str]:
    cols = list(columns)
    lower = {c.lower(): c for c in cols}
    for cand in candidates:
        if cand in cols:
            return cand
        if cand.lower() in lower:
            return lower[cand.lower()]
    return None


def coerce_date_series(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce", utc=True).dt.tz_convert(None).dt.normalize()


def coerce_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def load_macro(root: Path, cfg: Dict[str, Any]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    path = root / cfg["macro_dataset_path"]
    if not path.exists():
        raise FileNotFoundError(f"macro dataset not found: {path}")
    df = pd.read_csv(path)
    date_col = find_col(df.columns, cfg.get("date_col_candidates", []))
    price_col = find_col(df.columns, cfg.get("price_col_candidates", []))
    if not date_col:
        raise ValueError(f"no date column found; columns={list(df.columns)}")
    if not price_col:
        raise ValueError(f"no gold price column found; columns={list(df.columns)}")
    df["_date"] = coerce_date_series(df[date_col])
    df["_price"] = coerce_num(df[price_col])
    df = df.dropna(subset=["_date", "_price"]).sort_values("_date").reset_index(drop=True)
    meta = {
        "path": str(path),
        "rows_raw": int(pd.read_csv(path, usecols=[date_col]).shape[0]),
        "rows_used": int(len(df)),
        "date_col": date_col,
        "price_col": price_col,
        "min_date": df["_date"].min().strftime("%Y-%m-%d") if len(df) else None,
        "max_date": df["_date"].max().strftime("%Y-%m-%d") if len(df) else None,
        "sha256": sha256_file(path),
    }
    return df, meta


def condition_pass(series: pd.Series, op: str, threshold: float) -> pd.Series:
    x = coerce_num(series)
    if op == ">":
        return x > threshold
    if op == ">=":
        return x >= threshold
    if op == "<":
        return x < threshold
    if op == "<=":
        return x <= threshold
    if op == "==":
        return x == threshold
    raise ValueError(f"unsupported operator: {op}")


def make_rule(d: Dict[str, Any]) -> Rule:
    return Rule(
        thesis_id=d["thesis_id"],
        family=d.get("family", ""),
        direction=d.get("direction", "long"),
        horizon=int(d["horizon_trading_days"]),
        cooldown=int(d.get("entry_cooldown_trading_days", d["horizon_trading_days"])),
        cost_bps=float(d.get("cost_bps_total", 0.0)),
        conditions=list(d["conditions"]),
    )


def active_mask(df: pd.DataFrame, rule: Rule) -> Tuple[pd.Series, List[str]]:
    mask = pd.Series(True, index=df.index)
    missing = []
    for cond in rule.conditions:
        col = cond["column"]
        if col not in df.columns:
            missing.append(col)
            mask &= False
            continue
        mask &= condition_pass(df[col], cond["operator"], float(cond["threshold"]))
    return mask.fillna(False), missing


def simulate_entries(df: pd.DataFrame, rule: Rule) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    mask, missing = active_mask(df, rule)
    entries: List[Dict[str, Any]] = []
    next_allowed = 0
    n = len(df)
    for i, is_active in enumerate(mask.tolist()):
        if not is_active or i < next_allowed:
            continue
        exit_i = i + rule.horizon
        if exit_i >= n:
            # Keep strict no-lookahead: no entry whose fixed horizon has not matured.
            continue
        entry_price = float(df.loc[i, "_price"])
        exit_price = float(df.loc[exit_i, "_price"])
        gross_bps = (exit_price / entry_price - 1.0) * 10000.0
        if rule.direction.lower() == "short":
            gross_bps = -gross_bps
        net_bps = gross_bps - rule.cost_bps
        entries.append({
            "thesis_id": rule.thesis_id,
            "family": rule.family,
            "direction": rule.direction,
            "horizon_trading_days": rule.horizon,
            "entry_date": df.loc[i, "_date"].strftime("%Y-%m-%d"),
            "exit_date": df.loc[exit_i, "_date"].strftime("%Y-%m-%d"),
            "entry_index": int(i),
            "exit_index": int(exit_i),
            "entry_price": entry_price,
            "exit_price": exit_price,
            "gross_return_bps": round(gross_bps, 4),
            "net_return_bps": round(net_bps, 4),
            "cost_bps_total": rule.cost_bps,
        })
        next_allowed = i + rule.cooldown
    meta = {
        "missing_columns": missing,
        "active_days": int(mask.sum()),
        "active_pct_of_evaluable": round(float(mask.sum()) / max(1, len(df)) * 100.0, 4),
        "entry_count": int(len(entries)),
    }
    return pd.DataFrame(entries), meta


def metrics_for_returns(values: List[float]) -> Dict[str, Any]:
    vals = [float(v) for v in values if pd.notna(v)]
    if not vals:
        return {
            "entry_count": 0,
            "mean_net_return_bps": None,
            "median_net_return_bps": None,
            "win_rate": None,
            "min_net_return_bps": None,
            "max_net_return_bps": None,
            "total_net_return_bps": 0.0,
        }
    s = pd.Series(vals)
    return {
        "entry_count": int(len(vals)),
        "mean_net_return_bps": round(float(s.mean()), 4),
        "median_net_return_bps": round(float(s.median()), 4),
        "win_rate": round(float((s > 0).mean()), 4),
        "min_net_return_bps": round(float(s.min()), 4),
        "max_net_return_bps": round(float(s.max()), 4),
        "total_net_return_bps": round(float(s.sum()), 4),
    }


def assign_split(date_str: str, splits: List[Dict[str, Any]]) -> Optional[str]:
    d = pd.Timestamp(date_str)
    for sp in splits:
        start = pd.Timestamp(sp["start"])
        end = pd.Timestamp(sp["end"]) if sp.get("end") else pd.Timestamp.max
        if start <= d <= end:
            return sp["split_id"]
    return None


def split_metrics(entries: pd.DataFrame, splits: List[Dict[str, Any]], thesis_id: str) -> pd.DataFrame:
    rows = []
    if entries.empty:
        for sp in splits:
            rows.append({"thesis_id": thesis_id, "split_id": sp["split_id"], "role": sp.get("role", ""), **metrics_for_returns([])})
        return pd.DataFrame(rows)
    e = entries.copy()
    e["split_id"] = e["entry_date"].apply(lambda x: assign_split(x, splits))
    for sp in splits:
        sub = e[e["split_id"] == sp["split_id"]]
        rows.append({
            "thesis_id": thesis_id,
            "split_id": sp["split_id"],
            "role": sp.get("role", ""),
            "start": sp["start"],
            "end": sp.get("end"),
            **metrics_for_returns(sub["net_return_bps"].tolist()),
        })
    return pd.DataFrame(rows)


def compatibility_audit(df: pd.DataFrame, cfg: Dict[str, Any]) -> pd.DataFrame:
    rows = []
    target_start = pd.Timestamp(cfg.get("compatibility_target_start", "2011-01-03"))
    min_cov = float(cfg.get("compatibility_min_coverage_pct", 95.0))
    total_rows = int((df["_date"] >= target_start).sum())
    for col in cfg.get("compatibility_required_columns", []):
        if col not in df.columns:
            rows.append({
                "column": col,
                "exists": False,
                "rows_since_target_start": total_rows,
                "non_null_rows": 0,
                "coverage_pct": 0.0,
                "first_non_null_date": None,
                "last_non_null_date": None,
                "status": "MISSING_COLUMN_MANUAL_OR_PIPELINE_BACKFILL_REQUIRED",
            })
            continue
        sub = df[df["_date"] >= target_start][["_date", col]].copy()
        non_null = sub[pd.notna(pd.to_numeric(sub[col], errors="coerce"))]
        coverage = round(float(len(non_null)) / max(1, total_rows) * 100.0, 4)
        rows.append({
            "column": col,
            "exists": True,
            "rows_since_target_start": total_rows,
            "non_null_rows": int(len(non_null)),
            "coverage_pct": coverage,
            "first_non_null_date": non_null["_date"].min().strftime("%Y-%m-%d") if len(non_null) else None,
            "last_non_null_date": non_null["_date"].max().strftime("%Y-%m-%d") if len(non_null) else None,
            "status": "PASS_TEMPORAL_COMPATIBILITY" if coverage >= min_cov else "LOW_COVERAGE_BACKFILL_OR_ALIGNMENT_REVIEW_REQUIRED",
        })
    return pd.DataFrame(rows)


def latest_signal(df: pd.DataFrame, rule: Rule) -> Dict[str, Any]:
    latest = df.iloc[-1]
    condition_results = []
    failures = []
    missing_columns = []
    for cond in rule.conditions:
        col = cond["column"]
        op = cond["operator"]
        thr = float(cond["threshold"])
        if col not in df.columns:
            missing_columns.append(col)
            condition_results.append({"column": col, "operator": op, "threshold": thr, "value": None, "passed": False})
            failures.append(f"{col}:MISSING")
            continue
        val = pd.to_numeric(pd.Series([latest[col]]), errors="coerce").iloc[0]
        passed = bool(condition_pass(pd.Series([val]), op, thr).iloc[0]) if pd.notna(val) else False
        condition_results.append({"column": col, "operator": op, "threshold": thr, "value": None if pd.isna(val) else float(val), "passed": passed})
        if not passed:
            failures.append(f"{col}:{val}{op}{thr}")
    return {
        "latest_feature_date_utc": latest["_date"].strftime("%Y-%m-%d"),
        "signal_active": bool(all(x["passed"] for x in condition_results)),
        "condition_results": condition_results,
        "rule_failures": failures,
        "missing_columns": missing_columns,
    }


def decide(overall: Dict[str, Any], split_df: pd.DataFrame, compat_df: pd.DataFrame, cfg: Dict[str, Any]) -> Tuple[str, str, List[str], List[str]]:
    c = cfg["decision_constraints"]
    hard_failures: List[str] = []
    cautions: List[str] = []
    def val(name: str, default: float = 0.0) -> float:
        x = overall.get(name)
        return default if x is None else float(x)
    if val("entry_count") < c["min_total_entry_count"]:
        hard_failures.append("TOTAL_ENTRY_COUNT_BELOW_MIN")
    if val("mean_net_return_bps") < c["min_total_mean_net_return_bps"]:
        hard_failures.append("TOTAL_MEAN_NET_BELOW_MIN")
    if val("median_net_return_bps") < c["min_total_median_net_return_bps"]:
        hard_failures.append("TOTAL_MEDIAN_NET_BELOW_MIN")
    if val("win_rate") < c["min_total_win_rate"]:
        hard_failures.append("TOTAL_WIN_RATE_BELOW_MIN")
    if abs(val("min_net_return_bps")) > c["max_abs_worst_loss_bps"]:
        hard_failures.append("WORST_LOSS_EXCEEDS_LIMIT")

    split_index = {r["split_id"]: r for _, r in split_df.iterrows()}
    locked_entries = int(split_index.get("LOCKED_HISTORICAL_FORWARD", {}).get("entry_count", 0) or 0)
    locked_mean = split_index.get("LOCKED_HISTORICAL_FORWARD", {}).get("mean_net_return_bps", None)
    final_entries = int(split_index.get("FINAL_STATISTICAL_HOLDOUT", {}).get("entry_count", 0) or 0)
    final_mean = split_index.get("FINAL_STATISTICAL_HOLDOUT", {}).get("mean_net_return_bps", None)

    positive_locked = 0
    for sid in ["LOCKED_HISTORICAL_FORWARD", "FINAL_STATISTICAL_HOLDOUT"]:
        x = split_index.get(sid, {}).get("mean_net_return_bps", None)
        if x is not None and float(x) > 0:
            positive_locked += 1
    if locked_entries < c["min_locked_forward_entry_count"]:
        cautions.append("LOCKED_FORWARD_ENTRY_COUNT_LOW")
    if locked_mean is None or float(locked_mean) < c["min_locked_forward_mean_net_bps"]:
        hard_failures.append("LOCKED_FORWARD_MEAN_BELOW_MIN")
    if final_entries < c["min_final_holdout_entry_count"]:
        cautions.append("FINAL_HOLDOUT_ENTRY_COUNT_LOW")
    if final_mean is None or float(final_mean) < c["min_final_holdout_mean_net_bps"]:
        hard_failures.append("FINAL_HOLDOUT_MEAN_BELOW_MIN")
    if positive_locked < c["min_positive_locked_splits"]:
        hard_failures.append("NOT_ENOUGH_POSITIVE_LOCKED_SPLITS")

    bad_compat = compat_df[compat_df["coverage_pct"].astype(float) < float(c["min_compatibility_coverage_pct"])]
    if len(bad_compat):
        cautions.append("TEMPORAL_COMPATIBILITY_COVERAGE_REVIEW_REQUIRED")

    if hard_failures:
        return "K06_FAILS_LOCKED_HISTORICAL_FORWARD_NO_ORDER", "S71_K06_FAIL_LOCKED_TEST", hard_failures, cautions
    if cautions:
        return "K06_PASSES_LOCKED_HISTORICAL_FORWARD_WITH_CAUTION_NO_ORDER", "S71_K06_PASS_LOCKED_TEST_WITH_CAUTION", hard_failures, cautions
    return "K06_PASSES_LOCKED_HISTORICAL_FORWARD_NO_ORDER", "S71_K06_PASS_LOCKED_TEST", hard_failures, cautions


def write_report(path: Path, summary: Dict[str, Any], split_df: pd.DataFrame, compat_df: pd.DataFrame) -> None:
    lines = []
    lines.append("# Stage71 Locked Historical Forward Test")
    lines.append("")
    lines.append("## Decision")
    for k in ["status", "decision", "classification", "disposition"]:
        lines.append(f"- {k}: `{summary[k]}`")
    lines.append("")
    ch = summary["champion"]
    lines.append("## Champion")
    lines.append(f"- thesis_id: `{ch['thesis_id']}`")
    lines.append(f"- family: `{ch['family']}`")
    lines.append(f"- horizon_trading_days: `{ch['horizon_trading_days']}`")
    lines.append(f"- conditions: `{ch['conditions_text']}`")
    lines.append("")
    lines.append("## Overall metrics")
    for k, v in summary["overall_metrics"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")
    lines.append("## Locked splits")
    for _, r in split_df.iterrows():
        lines.append(f"### `{r['split_id']}`")
        lines.append(f"- role: `{r.get('role', '')}`")
        lines.append(f"- entry_count: `{r['entry_count']}`")
        lines.append(f"- mean_net_return_bps: `{r['mean_net_return_bps']}`")
        lines.append(f"- median_net_return_bps: `{r['median_net_return_bps']}`")
        lines.append(f"- win_rate: `{r['win_rate']}`")
        lines.append("")
    lines.append("## Latest signal snapshot")
    latest = summary["latest_signal_snapshot"]
    lines.append(f"- latest_feature_date_utc: `{latest['latest_feature_date_utc']}`")
    lines.append(f"- signal_active: `{latest['signal_active']}`")
    lines.append(f"- rule_failures: `{'; '.join(latest['rule_failures'])}`")
    lines.append("")
    lines.append("## Temporal compatibility")
    for _, r in compat_df.iterrows():
        lines.append(f"- `{r['column']}`: status=`{r['status']}`, coverage_pct=`{r['coverage_pct']}`, first=`{r['first_non_null_date']}`, last=`{r['last_non_null_date']}`")
    lines.append("")
    lines.append("## Hard failures")
    if summary["hard_failures"]:
        for x in summary["hard_failures"]:
            lines.append(f"- `{x}`")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Cautions")
    if summary["cautions"]:
        for x in summary["cautions"]:
            lines.append(f"- `{x}`")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Hard blocks")
    for x in summary["hard_blocks"]:
        lines.append(f"- `{x}`")
    path.write_text("\n".join(lines) + "\n")


def run(root: Path, config: Path, out: Path) -> Dict[str, Any]:
    cfg = load_json(config)
    out.mkdir(parents=True, exist_ok=True)
    df, meta = load_macro(root, cfg)
    champion = make_rule(cfg["champion"])
    entries, activity = simulate_entries(df, champion)
    overall = metrics_for_returns(entries["net_return_bps"].tolist() if not entries.empty else [])
    splits = cfg["locked_splits"]
    split_df = split_metrics(entries, splits, champion.thesis_id)
    compat_df = compatibility_audit(df, cfg)
    latest = latest_signal(df, champion)

    # Benchmark split metrics, for context only.
    benchmark_rows = []
    benchmark_entries_all = []
    for b in cfg.get("benchmarks", []):
        br = make_rule(b)
        be, bm = simulate_entries(df, br)
        if not be.empty:
            benchmark_entries_all.append(be)
        bs = split_metrics(be, splits, br.thesis_id)
        for _, row in bs.iterrows():
            rowd = row.to_dict()
            rowd["benchmark_family"] = br.family
            benchmark_rows.append(rowd)
    benchmark_df = pd.DataFrame(benchmark_rows)

    decision, classification, hard_failures, cautions = decide(overall, split_df, compat_df, cfg)
    disposition = decision.replace("_NO_ORDER", "")

    outputs = {
        "summary_json": str(out / "stage71_locked_historical_forward_test_summary.json"),
        "report_md": str(out / "stage71_locked_historical_forward_test_report.md"),
        "entry_returns_csv": str(out / "stage71_k06_entry_returns.csv"),
        "split_metrics_csv": str(out / "stage71_k06_split_metrics.csv"),
        "benchmark_split_metrics_csv": str(out / "stage71_benchmark_split_metrics.csv"),
        "temporal_compatibility_csv": str(out / "stage71_temporal_compatibility.csv"),
    }
    if not entries.empty:
        entries.to_csv(outputs["entry_returns_csv"], index=False)
    else:
        pd.DataFrame().to_csv(outputs["entry_returns_csv"], index=False)
    split_df.to_csv(outputs["split_metrics_csv"], index=False)
    benchmark_df.to_csv(outputs["benchmark_split_metrics_csv"], index=False)
    compat_df.to_csv(outputs["temporal_compatibility_csv"], index=False)

    summary: Dict[str, Any] = {
        "stage": cfg["stage"],
        "root": str(root),
        "config": str(config),
        "status": "STAGE71_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
        "macro_dataset": meta,
        "split_policy": {
            "principle": "Historical data is separated into discovery, validation, locked historical forward, and final statistical holdout. No parameters are tuned on locked/final splits.",
            "splits": splits,
            "real_forward_role": "Pipeline/latency/sanity only; not the primary statistical proof mechanism.",
        },
        "champion": {
            "thesis_id": champion.thesis_id,
            "family": champion.family,
            "direction": champion.direction,
            "horizon_trading_days": champion.horizon,
            "entry_cooldown_trading_days": champion.cooldown,
            "conditions_text": ";".join([f"{c['column']}{c['operator']}{c['threshold']}" for c in champion.conditions]),
            "cost_bps_total": champion.cost_bps,
        },
        "activity_meta": activity,
        "overall_metrics": overall,
        "latest_signal_snapshot": latest,
        "decision_constraints": cfg["decision_constraints"],
        "hard_failures": hard_failures,
        "cautions": cautions,
        "temporal_compatibility_summary": compat_df.to_dict(orient="records"),
        "hard_blocks": cfg.get("hard_blocks", []),
        "operator_instructions": [
            "Stage71 is a locked historical forward test and cannot authorize orders.",
            "Do not retune thresholds on locked historical forward or final statistical holdout.",
            "If temporal compatibility coverage fails, backfill or align source data before relying on the affected feature.",
            "Real forward is kept for pipeline/latency sanity, not as the only statistical proof.",
            "Broker, EA, paper-live, and live paths remain blocked.",
        ],
        "outputs": outputs,
    }
    Path(outputs["summary_json"]).write_text(json.dumps(summary, indent=2))
    write_report(Path(outputs["report_md"]), summary, split_df, compat_df)
    print(json.dumps({
        "stage": summary["stage"],
        "status": summary["status"],
        "decision": summary["decision"],
        "classification": summary["classification"],
        "summary_json": outputs["summary_json"],
        "report_md": outputs["report_md"],
    }, indent=2))
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", default="configs/stage71_locked_historical_forward_test.json")
    ap.add_argument("--out", default="reports/stage71_locked_historical_forward_test")
    args = ap.parse_args()
    run(Path(args.root).resolve(), Path(args.config).resolve(), Path(args.out).resolve())


if __name__ == "__main__":
    main()
