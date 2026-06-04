from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import pandas as pd
import yaml

from app.xauusd_candidate_eval import evaluate_fixed_candidate, read_interval_from_db


def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def window_info(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {"rows": 0, "start_utc": None, "end_utc": None}
    return {
        "rows": int(len(df)),
        "start_utc": df["time_utc"].min().isoformat(),
        "end_utc": df["time_utc"].max().isoformat(),
    }


def apply_shift(df: pd.DataFrame, hours: int) -> pd.DataFrame:
    out = df.copy()
    out["time_utc"] = out["time_utc"] + pd.Timedelta(hours=int(hours))
    out = out.sort_values("time_utc").drop_duplicates(subset=["time_utc"], keep="last").reset_index(drop=True)
    out["date_utc"] = out["time_utc"].dt.date.astype(str)
    out["month_utc"] = out["time_utc"].dt.to_period("M").astype(str)
    out["hour_utc"] = out["time_utc"].dt.hour
    return out


def common_slice(primary: pd.DataFrame, secondary: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    start = max(primary["time_utc"].min(), secondary["time_utc"].min())
    end = min(primary["time_utc"].max(), secondary["time_utc"].max())

    p = primary[(primary["time_utc"] >= start) & (primary["time_utc"] <= end)].copy().reset_index(drop=True)
    s = secondary[(secondary["time_utc"] >= start) & (secondary["time_utc"] <= end)].copy().reset_index(drop=True)

    days = float((end - start).total_seconds() / 86400.0) if end > start else 0.0
    return p, s, {"start_utc": start.isoformat(), "end_utc": end.isoformat(), "overlap_days": days}


def cost_x(analysis: Dict[str, Any], multiplier: float) -> Dict[str, Any]:
    return next((x for x in analysis.get("cost_stress", []) if float(x.get("cost_multiplier", 0)) == float(multiplier)), {})


def source_summary(analysis: Dict[str, Any]) -> Dict[str, Any]:
    base = analysis.get("base", {})
    x4 = cost_x(analysis, 4.0)
    direction = analysis.get("direction", {})
    return {
        "trades": base.get("trade_count", 0),
        "total_net_usd": base.get("total_net_usd", 0.0),
        "profit_factor": base.get("profit_factor"),
        "win_rate": base.get("win_rate", 0.0),
        "max_drawdown_usd": base.get("max_drawdown_usd", 0.0),
        "cost_x4_total_net_usd": x4.get("total_net_usd", 0.0),
        "positive_fold_ratio": analysis.get("folds", {}).get("positive_fold_ratio", 0.0),
        "positive_month_ratio": analysis.get("monthly", {}).get("positive_month_ratio", 0.0),
        "long_total_net_usd": direction.get("long", {}).get("total_net_usd", 0.0),
        "short_total_net_usd": direction.get("short", {}).get("total_net_usd", 0.0),
    }


def decide_pair(primary_analysis: Dict[str, Any], secondary_analysis: Dict[str, Any], overlap: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    decision_cfg = cfg.get("decision", {}) or {}

    p = source_summary(primary_analysis)
    s = source_summary(secondary_analysis)

    p_total = float(p.get("total_net_usd", 0.0))
    s_total = float(s.get("total_net_usd", 0.0))
    s_pf = s.get("profit_factor")

    checks = {
        "min_overlap_days": float(overlap.get("overlap_days", 0.0)) >= float(decision_cfg.get("min_overlap_days", 365)),
        "secondary_min_trades": int(s.get("trades", 0)) >= int(decision_cfg.get("min_secondary_trades", 100)),
        "secondary_total_positive": s_total > 0 if bool(decision_cfg.get("require_secondary_total_positive", True)) else True,
        "secondary_pf_min": s_pf is not None and float(s_pf) >= float(decision_cfg.get("min_secondary_profit_factor", 1.05)),
        "secondary_cost_x4_positive": float(s.get("cost_x4_total_net_usd", 0.0)) > 0 if bool(decision_cfg.get("require_secondary_cost_x4_positive", True)) else True,
        "degradation_ok": s_total >= float(decision_cfg.get("max_total_net_degradation_ratio", 0.65)) * p_total if p_total > 0 else False,
    }

    status = "overlap_second_source_pass" if all(checks.values()) else "overlap_second_source_fail"
    reason = "Fixed candidate passed overlap-aligned second-source checks." if all(checks.values()) else "Fixed candidate failed overlap-aligned diagnostics."

    return {
        "status": status,
        "reason": reason,
        "checks": checks,
        "primary_total_net_usd": p_total,
        "secondary_total_net_usd": s_total,
        "secondary_to_primary_total_ratio": (s_total / p_total) if p_total else None,
    }


def write_markdown(path: Path, payload: Dict[str, Any]) -> None:
    lines = []
    lines.append("# XAUUSD Stage 3C Overlap-Aligned Feed Diagnostics")
    lines.append("")
    lines.append(f"- Generated at UTC: `{payload['generated_at_utc']}`")
    lines.append(f"- Decision: `{payload['decision']['status']}`")
    lines.append(f"- Reason: `{payload['decision']['reason']}`")
    lines.append("")
    lines.append("## Data windows")
    lines.append("")
    lines.append(f"- Primary full: `{payload['windows']['primary_full']}`")
    lines.append(f"- Secondary full: `{payload['windows']['secondary_full']}`")
    lines.append(f"- Common overlap: `{payload['windows']['common_overlap']}`")
    lines.append("")
    lines.append("## Exact timestamp comparison")
    lines.append("")
    exact = payload["exact_overlap"]
    lines.append("| Source | Trades | Total net | PF | Cost x4 | Fold+ ratio | Month+ ratio |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for source_name in ["primary", "secondary"]:
        s = exact[source_name]["summary"]
        pf = s.get("profit_factor")
        lines.append(
            "| {name} | {trades} | {total:.4f} | {pf} | {x4:.4f} | {fold:.3f} | {month:.3f} |".format(
                name=source_name,
                trades=s.get("trades", 0),
                total=float(s.get("total_net_usd", 0.0)),
                pf="n/a" if pf is None else f"{float(pf):.3f}",
                x4=float(s.get("cost_x4_total_net_usd", 0.0)),
                fold=float(s.get("positive_fold_ratio", 0.0)),
                month=float(s.get("positive_month_ratio", 0.0)),
            )
        )
    lines.append("")
    lines.append("## Secondary time-shift diagnostics")
    lines.append("")
    lines.append("| Shift hours | Status | Secondary total | Ratio vs primary | Secondary PF |")
    lines.append("|---:|---|---:|---:|---:|")
    for item in payload["shift_diagnostics"]:
        sec = item["secondary"]["summary"]
        pf = sec.get("profit_factor")
        lines.append(
            "| {shift} | {status} | {total:.4f} | {ratio} | {pf} |".format(
                shift=item["secondary_shift_hours"],
                status=item["decision"]["status"],
                total=float(sec.get("total_net_usd", 0.0)),
                ratio="n/a" if item["decision"].get("secondary_to_primary_total_ratio") is None else f"{float(item['decision']['secondary_to_primary_total_ratio']):.3f}",
                pf="n/a" if pf is None else f"{float(pf):.3f}",
            )
        )
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 3C overlap-aligned primary/secondary feed diagnostics.")
    parser.add_argument("--config", default="configs/stage3c.yaml")
    parser.add_argument("--primary-db", default=None)
    parser.add_argument("--secondary-db", default=None)
    parser.add_argument("--report-dir", default=None)
    args = parser.parse_args()

    cfg = load_yaml(Path(args.config))
    candidate = cfg.get("candidate", {}) or {}
    sources = cfg.get("sources", {}) or {}
    cost_cfg = cfg.get("cost_model", {}) or {}
    cost_usd = float(cost_cfg.get("total_roundtrip_cost_usd", 0.35))

    primary_db = args.primary_db or sources.get("primary", {}).get("db_path", "data/store/xauusd.sqlite")
    secondary_db = args.secondary_db or sources.get("secondary", {}).get("db_path", "data/second_source/second_source.sqlite")
    interval = str(candidate.get("interval", "1h"))

    primary_df = read_interval_from_db(primary_db, interval)
    secondary_df_base = read_interval_from_db(secondary_db, interval)

    p_exact, s_exact, overlap_exact = common_slice(primary_df, secondary_df_base)
    primary_analysis_exact = evaluate_fixed_candidate(p_exact, candidate, cost_usd=cost_usd)
    secondary_analysis_exact = evaluate_fixed_candidate(s_exact, candidate, cost_usd=cost_usd)
    exact_decision = decide_pair(primary_analysis_exact, secondary_analysis_exact, overlap_exact, cfg)

    shifts = [int(x) for x in (cfg.get("diagnostics", {}) or {}).get("secondary_time_shift_hours", [0])]
    shift_rows = []
    for shift in shifts:
        secondary_shifted = apply_shift(secondary_df_base, shift)
        p_slice, s_slice, overlap = common_slice(primary_df, secondary_shifted)
        p_analysis = evaluate_fixed_candidate(p_slice, candidate, cost_usd=cost_usd)
        s_analysis = evaluate_fixed_candidate(s_slice, candidate, cost_usd=cost_usd)
        decision = decide_pair(p_analysis, s_analysis, overlap, cfg)
        shift_rows.append(
            {
                "secondary_shift_hours": shift,
                "overlap": overlap,
                "primary": {"summary": source_summary(p_analysis)},
                "secondary": {"summary": source_summary(s_analysis)},
                "decision": decision,
            }
        )

    # Use exact import as official decision. Shift rows are diagnostics only.
    payload = {
        "ok": True,
        "stage": "stage3c_overlap_aligned_feed_diagnostics",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "candidate": {
            "family": candidate.get("family"),
            "variant": candidate.get("variant"),
            "interval": interval,
        },
        "windows": {
            "primary_full": window_info(primary_df),
            "secondary_full": window_info(secondary_df_base),
            "common_overlap": overlap_exact,
        },
        "exact_overlap": {
            "primary": {"summary": source_summary(primary_analysis_exact)},
            "secondary": {"summary": source_summary(secondary_analysis_exact)},
            "decision": exact_decision,
        },
        "shift_diagnostics": shift_rows,
        "decision": exact_decision,
    }

    report_dir = Path(args.report_dir or cfg.get("report_dir", "data/reports"))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    summary_json = report_dir / f"stage3c_overlap_diagnostics_summary_{stamp}.json"
    summary_md = report_dir / f"stage3c_overlap_diagnostics_summary_{stamp}.md"

    write_json(summary_json, payload)
    write_markdown(summary_md, payload)

    print(
        json.dumps(
            {
                "ok": True,
                "decision": payload["decision"],
                "summary_json": str(summary_json),
                "summary_md": str(summary_md),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
