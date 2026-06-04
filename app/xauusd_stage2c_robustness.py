from __future__ import annotations

import argparse
import glob
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import yaml


def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def latest_file(pattern: str) -> Optional[Path]:
    files = sorted(glob.glob(pattern), key=lambda p: Path(p).stat().st_mtime, reverse=True)
    return Path(files[0]) if files else None


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def max_drawdown(values: List[float]) -> float:
    if not values:
        return 0.0
    equity = pd.Series(values).cumsum()
    peak = equity.cummax()
    return float((equity - peak).min())


def profit_factor(values: List[float]) -> Optional[float]:
    wins = [x for x in values if x > 0]
    losses = [x for x in values if x <= 0]
    loss_abs = abs(sum(losses))
    if loss_abs == 0:
        return None
    return float(sum(wins) / loss_abs)


def base_metrics(values: List[float]) -> Dict[str, Any]:
    if not values:
        return {
            "trade_count": 0,
            "total_net_usd": 0.0,
            "avg_net_usd": 0.0,
            "median_net_usd": 0.0,
            "win_rate": 0.0,
            "max_drawdown_usd": 0.0,
            "profit_factor": None,
        }

    s = pd.Series(values, dtype="float64")
    return {
        "trade_count": int(len(s)),
        "total_net_usd": float(s.sum()),
        "avg_net_usd": float(s.mean()),
        "median_net_usd": float(s.median()),
        "win_rate": float((s > 0).mean()),
        "best_net_usd": float(s.max()),
        "worst_net_usd": float(s.min()),
        "max_drawdown_usd": max_drawdown(s.tolist()),
        "profit_factor": profit_factor(s.tolist()),
    }


def remove_top_k(values: List[float], k: int) -> List[float]:
    if not values:
        return []
    ordered = sorted(values, reverse=True)
    cutoff = set()
    # Remove by index after sorting to handle duplicate values conservatively.
    remove_values = ordered[: min(k, len(ordered))]
    remaining = values.copy()
    for v in remove_values:
        for i, x in enumerate(remaining):
            if x == v:
                remaining.pop(i)
                break
    return remaining


def split_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {}

    work = df.sort_values("entry_time_utc").reset_index(drop=True)
    mid = len(work) // 2
    first = work.iloc[:mid]
    second = work.iloc[mid:]

    return {
        "first_half": base_metrics(first["net_usd"].tolist()),
        "second_half": base_metrics(second["net_usd"].tolist()),
    }


def monthly_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {}

    work = df.copy()
    work["entry_dt"] = pd.to_datetime(work["entry_time_utc"], utc=True)
    work["month"] = work["entry_dt"].dt.to_period("M").astype(str)

    rows = []
    for month, g in work.groupby("month", sort=True):
        m = base_metrics(g["net_usd"].tolist())
        m["month"] = month
        rows.append(m)

    if not rows:
        return {"months": [], "without_best_month": base_metrics([])}

    best_month = max(rows, key=lambda x: float(x["total_net_usd"]))
    without_best = work[work["month"] != best_month["month"]]

    return {
        "months": rows,
        "best_month": best_month,
        "without_best_month": base_metrics(without_best["net_usd"].tolist()),
        "positive_month_count": int(sum(1 for r in rows if float(r["total_net_usd"]) > 0)),
        "month_count": int(len(rows)),
    }


def cost_stress_metrics(df: pd.DataFrame, multipliers: List[float]) -> List[Dict[str, Any]]:
    if df.empty:
        return []

    out = []
    raw = pd.to_numeric(df["raw_usd"], errors="coerce").fillna(0.0)
    cost = pd.to_numeric(df["cost_usd"], errors="coerce").fillna(0.0)

    for mult in multipliers:
        stressed = raw - cost * float(mult)
        m = base_metrics(stressed.tolist())
        m["cost_multiplier"] = float(mult)
        out.append(m)

    return out


def direction_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {}

    out = {}
    for direction, g in df.groupby("direction_label", sort=True):
        out[str(direction)] = base_metrics(g["net_usd"].tolist())
    return out


def analyze_baseline(
    baseline: str,
    df: pd.DataFrame,
    cfg: Dict[str, Any],
    cost_multipliers: List[float],
) -> Dict[str, Any]:
    values = df["net_usd"].astype(float).tolist()

    metrics = {
        "baseline": baseline,
        "base": base_metrics(values),
        "remove_top_1": base_metrics(remove_top_k(values, 1)),
        "remove_top_5": base_metrics(remove_top_k(values, 5)),
        "split": split_metrics(df),
        "monthly": monthly_metrics(df),
        "cost_stress": cost_stress_metrics(df, cost_multipliers),
        "direction": direction_metrics(df),
    }

    decision_cfg = cfg.get("decision", {}) or {}
    pf_min = float(decision_cfg.get("require_profit_factor_min", 1.05))
    min_trades = int(decision_cfg.get("min_trades", 50))

    base = metrics["base"]
    remove1 = metrics["remove_top_1"]
    remove5 = metrics["remove_top_5"]
    second = metrics["split"].get("second_half", {})
    without_best = metrics["monthly"].get("without_best_month", {})
    stress = metrics["cost_stress"]
    stress_x2 = next((x for x in stress if float(x.get("cost_multiplier", 0)) == 2.0), None)

    checks = {
        "min_trades": int(base.get("trade_count", 0)) >= min_trades,
        "base_positive_total": float(base.get("total_net_usd", 0.0)) > 0,
        "base_positive_avg": float(base.get("avg_net_usd", 0.0)) > 0,
        "base_profit_factor_min": (base.get("profit_factor") is not None and float(base.get("profit_factor")) >= pf_min),
        "remove_top_1_positive": float(remove1.get("total_net_usd", 0.0)) > 0,
        "remove_top_5_positive": float(remove5.get("total_net_usd", 0.0)) > 0,
        "second_half_positive": float(second.get("total_net_usd", 0.0)) > 0,
        "without_best_month_positive": float(without_best.get("total_net_usd", 0.0)) > 0,
        "cost_x2_positive": bool(stress_x2 and float(stress_x2.get("total_net_usd", 0.0)) > 0),
    }

    robust = all(checks.values())

    if robust:
        reason = "robust_after_outlier_split_month_cost_stress"
    else:
        failed = [k for k, v in checks.items() if not v]
        reason = "failed_checks:" + ",".join(failed)

    metrics["decision"] = {
        "robust_after_stage2c": bool(robust),
        "reason": reason,
        "checks": checks,
    }
    return metrics


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
    tmp.replace(path)


def write_markdown(path: Path, payload: Dict[str, Any]) -> None:
    lines: List[str] = []
    lines.append("# XAUUSD Stage 2C Robustness Diagnostics")
    lines.append("")
    lines.append(f"- Generated at UTC: `{payload['generated_at_utc']}`")
    lines.append(f"- Decision: `{payload['decision']['status']}`")
    lines.append(f"- Reason: `{payload['decision']['reason']}`")
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("Stage 2C checks whether a Stage 2B candidate depends on outliers, one half of the sample, one best month, or weak cost assumptions.")
    lines.append("This is still not ML, not paper-order, and not live approval.")
    lines.append("")
    lines.append("## Baselines")
    lines.append("")
    lines.append("| Baseline | Trades | Base total | PF | Remove top 1 total | Remove top 5 total | Second half total | Without best month total | Cost x2 total | Stage2C robust |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for item in payload["analyses"]:
        base = item["base"]
        remove1 = item["remove_top_1"]
        remove5 = item["remove_top_5"]
        second = item["split"].get("second_half", {})
        without_best = item["monthly"].get("without_best_month", {})
        stress_x2 = next((x for x in item["cost_stress"] if float(x.get("cost_multiplier", 0)) == 2.0), {})
        lines.append(
            "| {baseline} | {trades} | {base_total:.4f} | {pf} | {r1:.4f} | {r5:.4f} | {second:.4f} | {wb:.4f} | {cx2:.4f} | {robust} |".format(
                baseline=item["baseline"],
                trades=int(base.get("trade_count", 0)),
                base_total=float(base.get("total_net_usd", 0.0)),
                pf="n/a" if base.get("profit_factor") is None else f"{float(base.get('profit_factor')):.3f}",
                r1=float(remove1.get("total_net_usd", 0.0)),
                r5=float(remove5.get("total_net_usd", 0.0)),
                second=float(second.get("total_net_usd", 0.0)),
                wb=float(without_best.get("total_net_usd", 0.0)),
                cx2=float(stress_x2.get("total_net_usd", 0.0)),
                robust=item["decision"]["robust_after_stage2c"],
            )
        )
    lines.append("")
    lines.append("## Next rule")
    lines.append("")
    lines.append("If no baseline is robust after Stage 2C, do not proceed to ML. Improve data/backfill or baseline definitions first.")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 2C robustness diagnostics for Stage 2B baseline candidates.")
    parser.add_argument("--config", default="configs/stage2c.yaml")
    parser.add_argument("--trades", default=None)
    parser.add_argument("--stage2b-summary", default=None)
    parser.add_argument("--report-dir", default=None)
    args = parser.parse_args()

    cfg = load_yaml(Path(args.config))
    report_dir = Path(args.report_dir or cfg.get("report_dir", "data/reports"))
    report_dir.mkdir(parents=True, exist_ok=True)

    trades_path = Path(args.trades) if args.trades else latest_file(str(cfg.get("trades_glob", "data/reports/stage2b_trades/stage2b_nonoverlap_trades_*.csv")))
    if not trades_path or not trades_path.exists():
        raise SystemExit("No Stage 2B trades CSV found.")

    summary_path = Path(args.stage2b_summary) if args.stage2b_summary else latest_file(str(cfg.get("stage2b_summary_glob", "data/reports/stage2b_validation_summary_*.json")))
    stage2b_summary = load_json(summary_path) if summary_path and summary_path.exists() else {}

    df = pd.read_csv(trades_path)
    if df.empty:
        raise SystemExit(f"Trades CSV is empty: {trades_path}")

    df["entry_time_utc"] = pd.to_datetime(df["entry_time_utc"], utc=True)
    df["exit_time_utc"] = pd.to_datetime(df["exit_time_utc"], utc=True)
    for col in ["raw_usd", "cost_usd", "net_usd"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["entry_time_utc", "exit_time_utc", "raw_usd", "cost_usd", "net_usd"])

    multipliers = [float(x) for x in (cfg.get("cost_stress", {}) or {}).get("multipliers", [1.0, 1.5, 2.0, 3.0])]

    # Analyze all baselines, but final decision focuses on Stage 2B robust candidates if available.
    stage2b_robust = set()
    for item in stage2b_summary.get("summaries", []) or []:
        if item.get("robust_candidate"):
            stage2b_robust.add(str(item.get("baseline")))

    analyses = []
    for baseline, g in df.groupby("baseline", sort=True):
        analyses.append(analyze_baseline(str(baseline), g.sort_values("entry_time_utc"), cfg, multipliers))

    if stage2b_robust:
        focus = [a for a in analyses if a["baseline"] in stage2b_robust]
    else:
        focus = analyses

    robust_after = [a for a in focus if a["decision"]["robust_after_stage2c"]]

    if robust_after:
        status = "stage2c_robust_candidate_found"
        reason = "At least one Stage 2B candidate survived outlier, split, month, and cost-stress diagnostics."
    else:
        status = "no_stage2c_robust_candidate"
        reason = "No Stage 2B candidate survived Stage 2C robustness diagnostics."

    payload = {
        "ok": True,
        "stage": "stage2c_robustness_diagnostics",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "trades_csv": str(trades_path),
        "stage2b_summary": str(summary_path) if summary_path else None,
        "stage2b_robust_candidates": sorted(stage2b_robust),
        "decision": {
            "status": status,
            "reason": reason,
            "robust_after_stage2c_count": int(len(robust_after)),
        },
        "analyses": analyses,
    }

    stamp = utc_stamp()
    summary_json = report_dir / f"stage2c_robustness_summary_{stamp}.json"
    summary_md = report_dir / f"stage2c_robustness_summary_{stamp}.md"

    write_json(summary_json, payload)
    write_markdown(summary_md, payload)

    print(
        json.dumps(
            {
                "ok": True,
                "decision": payload["decision"],
                "summary_json": str(summary_json),
                "summary_md": str(summary_md),
                "analysis_count": len(analyses),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
