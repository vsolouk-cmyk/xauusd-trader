from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

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


def write_markdown(path: Path, payload: Dict[str, Any]) -> None:
    lines = []
    lines.append("# XAUUSD Stage 3A Second-Source Validation")
    lines.append("")
    lines.append(f"- Generated at UTC: `{payload['generated_at_utc']}`")
    lines.append(f"- Decision: `{payload['decision']['status']}`")
    lines.append(f"- Reason: `{payload['decision']['reason']}`")
    lines.append("")
    lines.append("## Candidate")
    lines.append("")
    candidate = payload.get("candidate", {})
    lines.append(f"- family: `{candidate.get('family')}`")
    lines.append(f"- variant: `{candidate.get('variant')}`")
    lines.append("")
    lines.append("## Source comparison")
    lines.append("")
    lines.append("| Source | Available | Trades | Total net | PF | Win rate | Cost x4 total | Positive fold ratio | Positive month ratio |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")

    for source_name, result in payload.get("sources", {}).items():
        if not result.get("available"):
            lines.append(f"| {source_name} | False | 0 | 0 | n/a | 0 | 0 | 0 | 0 |")
            continue

        analysis = result["analysis"]
        base = analysis["base"]
        x4 = next((x for x in analysis.get("cost_stress", []) if float(x.get("cost_multiplier", 0)) == 4.0), {})
        pf = base.get("profit_factor")
        lines.append(
            "| {name} | True | {trades} | {total:.4f} | {pf} | {wr:.3f} | {x4:.4f} | {fold:.3f} | {month:.3f} |".format(
                name=source_name,
                trades=base.get("trade_count", 0),
                total=float(base.get("total_net_usd", 0.0)),
                pf="n/a" if pf is None else f"{float(pf):.3f}",
                wr=float(base.get("win_rate", 0.0)),
                x4=float(x4.get("total_net_usd", 0.0)),
                fold=float(analysis.get("folds", {}).get("positive_fold_ratio", 0.0)),
                month=float(analysis.get("monthly", {}).get("positive_month_ratio", 0.0)),
            )
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def source_result(source_cfg: Dict[str, Any], candidate_cfg: Dict[str, Any], cost_usd: float) -> Dict[str, Any]:
    db_path = Path(source_cfg["db_path"])
    if not db_path.exists():
        return {
            "available": False,
            "db_path": str(db_path),
            "reason": "db_missing",
        }

    try:
        df = read_interval_from_db(str(db_path), str(candidate_cfg.get("interval", "1h")))
        analysis = evaluate_fixed_candidate(df, candidate_cfg, cost_usd=cost_usd)
        return {
            "available": True,
            "db_path": str(db_path),
            "rows": int(len(df)),
            "start_utc": df["time_utc"].min().isoformat() if not df.empty else None,
            "end_utc": df["time_utc"].max().isoformat() if not df.empty else None,
            "analysis": analysis,
        }
    except Exception as exc:
        return {
            "available": False,
            "db_path": str(db_path),
            "reason": f"analysis_error:{exc}",
        }


def decide(payload: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    decision_cfg = cfg.get("decision", {}) or {}
    sources = payload.get("sources", {})
    primary = sources.get("primary", {})
    secondary = sources.get("secondary", {})

    if not primary.get("available"):
        return {"status": "failed_primary_missing", "reason": "Primary SQLite source is missing or unreadable."}

    if not secondary.get("available"):
        return {
            "status": "pending_second_source",
            "reason": "Primary candidate was evaluated, but secondary source is not available yet.",
        }

    p_base = primary["analysis"]["base"]
    s_base = secondary["analysis"]["base"]
    s_x4 = next((x for x in secondary["analysis"].get("cost_stress", []) if float(x.get("cost_multiplier", 0)) == 4.0), {})

    p_total = float(p_base.get("total_net_usd", 0.0))
    s_total = float(s_base.get("total_net_usd", 0.0))
    s_pf = s_base.get("profit_factor")

    checks = {
        "secondary_min_trades": int(s_base.get("trade_count", 0)) >= int(decision_cfg.get("min_secondary_trades", 100)),
        "secondary_total_positive": s_total > 0 if bool(decision_cfg.get("require_secondary_total_positive", True)) else True,
        "secondary_pf_min": s_pf is not None and float(s_pf) >= float(decision_cfg.get("min_secondary_profit_factor", 1.05)),
        "secondary_cost_x4_positive": float(s_x4.get("total_net_usd", 0.0)) > 0 if bool(decision_cfg.get("require_secondary_cost_x4_positive", True)) else True,
        "degradation_ok": s_total >= float(decision_cfg.get("max_total_net_degradation_ratio", 0.65)) * p_total if p_total > 0 else False,
    }

    if bool(decision_cfg.get("require_long_short_not_both_negative", True)):
        direction = secondary["analysis"].get("direction", {})
        long_total = float(direction.get("long", {}).get("total_net_usd", 0.0))
        short_total = float(direction.get("short", {}).get("total_net_usd", 0.0))
        checks["long_short_not_both_negative"] = not (long_total <= 0 and short_total <= 0)

    if all(checks.values()):
        return {
            "status": "stage3a_second_source_pass",
            "reason": "Fixed candidate passed primary/secondary comparison checks.",
            "checks": checks,
        }

    return {
        "status": "stage3a_second_source_fail",
        "reason": "Fixed candidate failed second-source validation checks.",
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 3A fixed-candidate validation on primary and second-source SQLite stores.")
    parser.add_argument("--config", default="configs/second_source.yaml")
    parser.add_argument("--primary-db", default=None)
    parser.add_argument("--secondary-db", default=None)
    parser.add_argument("--report-dir", default=None)
    args = parser.parse_args()

    cfg = load_yaml(Path(args.config))
    candidate_cfg = cfg.get("candidate", {}) or {}
    cost_cfg = cfg.get("cost_model", {}) or {}
    cost_usd = float(cost_cfg.get("total_roundtrip_cost_usd", 0.35))

    sources_cfg = cfg.get("sources", {}) or {}
    if args.primary_db:
        sources_cfg.setdefault("primary", {})["db_path"] = args.primary_db
    if args.secondary_db:
        sources_cfg.setdefault("secondary", {})["db_path"] = args.secondary_db

    results = {}
    for key in ["primary", "secondary"]:
        if key in sources_cfg:
            results[key] = source_result(sources_cfg[key], candidate_cfg, cost_usd)

    payload = {
        "ok": True,
        "stage": "stage3a_second_source_validation",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "candidate": {
            "family": candidate_cfg.get("family"),
            "variant": candidate_cfg.get("variant"),
            "interval": candidate_cfg.get("interval"),
        },
        "sources": results,
    }
    payload["decision"] = decide(payload, cfg)

    report_dir = Path(args.report_dir or cfg.get("report_dir", "data/reports"))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    summary_json = report_dir / f"stage3a_second_source_summary_{stamp}.json"
    summary_md = report_dir / f"stage3a_second_source_summary_{stamp}.md"

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
