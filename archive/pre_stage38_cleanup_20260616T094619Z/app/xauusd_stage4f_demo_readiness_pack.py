from __future__ import annotations

import argparse
import glob
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import yaml


def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def latest_stage4e_summary() -> Path:
    files = sorted(glob.glob("data/reports/stage4e_session_filter_summary_*.json"), key=lambda p: Path(p).stat().st_mtime)
    if not files:
        raise FileNotFoundError("No Stage 4E summary found in data/reports.")
    return Path(files[-1])


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def find_set(stage4e: Dict[str, Any], name: str) -> Dict[str, Any]:
    for row in stage4e.get("ranked_session_sets", []):
        if row.get("name") == name:
            return row
    raise KeyError(f"Session set not found in Stage 4E summary: {name}")


def gate_decision(selected: Dict[str, Any], baseline: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    gates = cfg.get("minimum_gates", {}) or {}
    comp = cfg.get("baseline_comparison_required", {}) or {}

    b = selected["base"]
    bb = baseline["base"]
    pf = b.get("profit_factor")
    baseline_pf = bb.get("profit_factor")

    checks = {
        "stage4e_selected_passed": bool(selected.get("passed")),
        "min_trades": int(b.get("trade_count", 0)) >= int(gates.get("min_trades", 250)),
        "min_profit_factor": pf is not None and float(pf) >= float(gates.get("min_profit_factor", 1.45)),
        "min_median_net_usd": float(b.get("median_net_usd", 0.0)) >= float(gates.get("min_median_net_usd", 1.0)),
        "max_drawdown_abs": abs(float(b.get("max_drawdown_usd", 0.0))) <= float(gates.get("max_drawdown_usd_abs", 100.0)),
        "positive_fold_ratio": float(selected.get("folds", {}).get("positive_fold_ratio", 0.0)) >= float(gates.get("min_positive_fold_ratio", 1.0)),
        "positive_year_ratio": float(selected.get("positive_year_ratio", 0.0)) >= float(gates.get("min_positive_year_ratio", 0.75)),
    }

    if bool(comp.get("total_net_better_than_baseline_all", True)):
        checks["total_net_better_than_baseline_all"] = float(b.get("total_net_usd", 0.0)) > float(bb.get("total_net_usd", 0.0))
    if bool(comp.get("pf_better_than_baseline_all", True)):
        checks["pf_better_than_baseline_all"] = pf is not None and baseline_pf is not None and float(pf) > float(baseline_pf)
    if bool(comp.get("median_better_than_baseline_all", True)):
        checks["median_better_than_baseline_all"] = float(b.get("median_net_usd", 0.0)) > float(bb.get("median_net_usd", 0.0))
    if bool(comp.get("drawdown_better_than_baseline_all", True)):
        checks["drawdown_better_than_baseline_all"] = abs(float(b.get("max_drawdown_usd", 0.0))) < abs(float(bb.get("max_drawdown_usd", 0.0)))

    passed = all(checks.values())

    # Strict interpretation: this permits demo-design, not demo execution.
    return {
        "status": "stage4f_demo_design_ready" if passed else "stage4f_demo_design_not_ready",
        "reason": "Locked candidate is ready for demo EA/dry-run design, but not yet authorized for demo execution." if passed else "Locked candidate failed demo-design readiness gates.",
        "checks": checks,
        "authorization": {
            "demo_design": bool(passed),
            "demo_execution": False,
            "paper_order": False,
            "live_trading": False,
        },
    }


def write_markdown(path: Path, payload: Dict[str, Any]) -> None:
    selected = payload["selected_session_set"]
    b = selected["base"]
    lines = [
        "# XAUUSD Stage 4F Demo-Readiness Pack",
        "",
        f"- Generated at UTC: `{payload['generated_at_utc']}`",
        f"- Decision: `{payload['decision']['status']}`",
        f"- Reason: `{payload['decision']['reason']}`",
        "",
        "## Locked candidate",
        "",
        "- Direction: `long-only`",
        "- TP: `24 USD`",
        "- SL: `15 USD`",
        "- Blocked session: `London 07:00-13:00 UTC`",
        "- Allowed sessions: `Asia`, `London-NY overlap`, `New York`, `Other`",
        "",
        "## Selected session set metrics",
        "",
        f"- name: `{selected['name']}`",
        f"- trades: `{b['trade_count']}`",
        f"- total net: `{b['total_net_usd']}`",
        f"- PF: `{b['profit_factor']}`",
        f"- median: `{b['median_net_usd']}`",
        f"- max DD: `{b['max_drawdown_usd']}`",
        f"- fold+: `{selected['folds']['positive_fold_ratio']}`",
        f"- year+: `{selected['positive_year_ratio']}`",
        "",
        "## Authorization",
        "",
        f"- demo design: `{payload['decision']['authorization']['demo_design']}`",
        f"- demo execution: `{payload['decision']['authorization']['demo_execution']}`",
        f"- paper-order: `{payload['decision']['authorization']['paper_order']}`",
        f"- live trading: `{payload['decision']['authorization']['live_trading']}`",
        "",
        "## Next required step",
        "",
        "Build Stage 5A MT5 demo EA specification and a dry-run logging design. Do not send orders yet.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Stage 4F demo-readiness pack from latest Stage 4E summary.")
    parser.add_argument("--config", default="configs/stage4f.yaml")
    parser.add_argument("--summary", default=None)
    parser.add_argument("--report-dir", default=None)
    args = parser.parse_args()

    cfg = load_yaml(Path(args.config))
    summary_path = Path(args.summary) if args.summary else latest_stage4e_summary()
    stage4e = json.loads(summary_path.read_text(encoding="utf-8"))

    selected_name = str(cfg.get("selected_session_set", "no_london"))
    selected = find_set(stage4e, selected_name)
    baseline = find_set(stage4e, "baseline_all")

    decision = gate_decision(selected, baseline, cfg)

    report_dir = Path(args.report_dir or cfg.get("report_dir", "data/reports"))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_json = report_dir / f"stage4f_demo_readiness_pack_{stamp}.json"
    out_md = report_dir / f"stage4f_demo_readiness_pack_{stamp}.md"

    payload = {
        "ok": True,
        "stage": "stage4f_demo_readiness_pack",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_stage4e_summary": str(summary_path),
        "locked_strategy_path": cfg.get("locked_strategy_path", "configs/locked_strategy_v1.yaml"),
        "selected_session_set": selected,
        "baseline_all": baseline,
        "decision": decision,
        "warning": "Demo-design ready does not mean demo execution, paper-order, or live trading authorization.",
    }

    write_json(out_json, payload)
    write_markdown(out_md, payload)

    print(json.dumps({
        "ok": True,
        "decision": decision,
        "summary_json": str(out_json),
        "summary_md": str(out_md),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
