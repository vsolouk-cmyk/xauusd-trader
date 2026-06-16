from __future__ import annotations

import argparse
import glob
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import pandas as pd
import yaml


def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def latest_stage4b_summary() -> Path:
    files = sorted(glob.glob("data/reports/stage4b_tpsl_scenario_summary_*.json"), key=lambda p: Path(p).stat().st_mtime)
    if not files:
        raise FileNotFoundError("No Stage 4B summary found in data/reports.")
    return Path(files[-1])


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def scenario_key(side: str, tp: Any, sl: Any) -> str:
    return f"side={side}|tp={tp}|sl={sl}"


def normalize_value_for_key(value: Any) -> Any:
    if value is None:
        return None
    try:
        fv = float(value)
        if fv.is_integer():
            return int(fv)
        return fv
    except Exception:
        return value


def possible_keys(side: str, tp: Any, sl: Any) -> list[str]:
    tp_norm = normalize_value_for_key(tp)
    sl_norm = normalize_value_for_key(sl)
    keys = {
        scenario_key(side, tp, sl),
        scenario_key(side, tp_norm, sl_norm),
        scenario_key(side, None if tp is None else float(tp), None if sl is None else float(sl)),
    }
    return list(keys)


def find_scenario(stage4b: Dict[str, Any], side: str, tp: Any, sl: Any) -> Dict[str, Any]:
    targets = set(possible_keys(side, tp, sl))
    all_rows = list(stage4b.get("top_scenarios", [])) + list(stage4b.get("passed_scenarios", []))
    seen = set()
    for row in all_rows:
        key = row.get("scenario")
        if key in seen:
            continue
        seen.add(key)
        if key in targets:
            return row

    csv_path = stage4b.get("scenarios_csv")
    if csv_path and Path(csv_path).exists():
        df = pd.read_csv(csv_path)
        hit = df[df["scenario"].isin(targets)]
        if not hit.empty:
            r = hit.iloc[0].to_dict()
            pf = r.get("profit_factor")
            return {
                "scenario": str(r.get("scenario")),
                "side_filter": side,
                "tp_usd": tp,
                "sl_usd": sl,
                "passed": str(r.get("passed")).lower() in {"true", "1", "yes"},
                "base": {
                    "trade_count": int(r.get("trade_count", 0)),
                    "total_net_usd": float(r.get("total_net_usd", 0.0)),
                    "avg_net_usd": float(r.get("avg_net_usd", 0.0)),
                    "median_net_usd": float(r.get("median_net_usd", 0.0)),
                    "win_rate": float(r.get("win_rate", 0.0)),
                    "profit_factor": None if pd.isna(pf) else float(pf),
                    "max_drawdown_usd": float(r.get("max_drawdown_usd", 0.0)),
                },
                "folds": {"positive_fold_ratio": float(r.get("positive_fold_ratio", 0.0))},
                "ambiguous_exit_ratio": float(r.get("ambiguous_exit_ratio", 0.0)),
                "ambiguous_exit_count": int(r.get("ambiguous_exit_count", 0)),
                "exit_reasons": {},
            }

    raise KeyError(f"Scenario not found. Tried: {sorted(targets)}")


def approximate_cost_stress(selected: Dict[str, Any], multipliers: list[float], base_cost: float = 0.35) -> list[Dict[str, Any]]:
    b = selected["base"]
    n = int(b.get("trade_count", 0))
    total = float(b.get("total_net_usd", 0.0))
    avg = float(b.get("avg_net_usd", total / max(n, 1)))
    median = float(b.get("median_net_usd", 0.0))
    dd = float(b.get("max_drawdown_usd", 0.0))
    pf = b.get("profit_factor")

    rows = []
    for m in multipliers:
        extra_per_trade = (float(m) - 1.0) * base_cost
        extra_total = extra_per_trade * n
        rows.append(
            {
                "cost_multiplier": float(m),
                "trade_count": n,
                "total_net_usd": float(total - extra_total),
                "avg_net_usd": float(avg - extra_per_trade),
                "median_net_usd": float(median - extra_per_trade),
                "profit_factor": pf if float(m) == 1.0 else None,
                "max_drawdown_usd": float(dd - extra_total * 0.25),
                "note": "Approximate stress from summary rows. Exact stress requires trade-level raw_usd replay.",
            }
        )
    return rows


def decide(selected: Dict[str, Any], reference: Dict[str, Any], cfg: Dict[str, Any], cost_stress: list[Dict[str, Any]]) -> Dict[str, Any]:
    th = cfg.get("thresholds", {}) or {}
    stress_cfg = cfg.get("stress_tests", {}) or {}
    b = selected["base"]
    ref_b = reference["base"]
    pf = b.get("profit_factor")

    checks = {
        "min_trades": int(b.get("trade_count", 0)) >= int(th.get("min_trades", 100)),
        "pf_min": pf is not None and float(pf) >= float(th.get("min_profit_factor", 1.25)),
        "median_nonnegative": float(b.get("median_net_usd", 0.0)) >= float(th.get("min_median_net_usd", 0.0)),
        "positive_fold_ratio": float(selected.get("folds", {}).get("positive_fold_ratio", 0.0)) >= float(th.get("min_positive_fold_ratio", 0.8)),
        "ambiguous_exit_ratio_ok": float(selected.get("ambiguous_exit_ratio", 999.0)) <= float(th.get("max_ambiguous_exit_ratio", 0.05)),
    }

    if bool(th.get("max_drawdown_improvement_required", True)):
        checks["drawdown_better_than_reference"] = abs(float(b.get("max_drawdown_usd", 0.0))) < abs(float(ref_b.get("max_drawdown_usd", 0.0)))

    by_mult = {float(x["cost_multiplier"]): x for x in cost_stress}
    if 2.0 in by_mult:
        checks["cost_x2_positive"] = float(by_mult[2.0].get("total_net_usd", 0.0)) > float(stress_cfg.get("min_cost_x2_total_net_usd", 0.0))
    if 3.0 in by_mult:
        checks["cost_x3_positive"] = float(by_mult[3.0].get("total_net_usd", 0.0)) > float(stress_cfg.get("min_cost_x3_total_net_usd", 0.0))

    passed = all(checks.values())
    return {
        "status": "stage4c_selected_scenario_pass" if passed else "stage4c_selected_scenario_fail",
        "reason": "Selected Stage 4B scenario passed locked validation checks." if passed else "Selected Stage 4B scenario failed locked validation checks.",
        "checks": checks,
    }


def write_markdown(path: Path, payload: Dict[str, Any]) -> None:
    sel = payload["selected"]
    ref = payload["reference"]
    lines = [
        "# XAUUSD Stage 4C Selected Scenario Validation",
        "",
        f"- Generated at UTC: `{payload['generated_at_utc']}`",
        f"- Decision: `{payload['decision']['status']}`",
        f"- Reason: `{payload['decision']['reason']}`",
        "",
        "## Selected scenario",
        "",
        f"- scenario: `{sel['scenario']}`",
        f"- trades: `{sel['base']['trade_count']}`",
        f"- total net: `{sel['base']['total_net_usd']}`",
        f"- PF: `{sel['base']['profit_factor']}`",
        f"- median: `{sel['base']['median_net_usd']}`",
        f"- max DD: `{sel['base']['max_drawdown_usd']}`",
        "",
        "## Reference",
        "",
        f"- scenario: `{ref['scenario']}`",
        f"- total net: `{ref['base']['total_net_usd']}`",
        f"- PF: `{ref['base']['profit_factor']}`",
        f"- max DD: `{ref['base']['max_drawdown_usd']}`",
        "",
        "## Cost stress",
        "",
        "| Cost x | Total net | Median | Max DD |",
        "|---:|---:|---:|---:|",
    ]
    for row in payload.get("cost_stress", []):
        lines.append(f"| {row['cost_multiplier']} | {row['total_net_usd']:.4f} | {row['median_net_usd']:.4f} | {row['max_drawdown_usd']:.4f} |")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate locked Stage 4B selected scenario.")
    parser.add_argument("--config", default="configs/stage4c.yaml")
    parser.add_argument("--summary", default=None, help="Path to Stage 4B summary JSON. Defaults to latest.")
    parser.add_argument("--report-dir", default=None)
    args = parser.parse_args()

    cfg = load_yaml(Path(args.config))
    summary_path = Path(args.summary) if args.summary else latest_stage4b_summary()
    stage4b = json.loads(summary_path.read_text(encoding="utf-8"))

    sel_cfg = cfg.get("selected_scenario", {}) or {}
    ref_cfg = cfg.get("baseline_reference", {}) or {}

    selected = find_scenario(stage4b, sel_cfg.get("side_filter", "long"), sel_cfg.get("take_profit_usd"), sel_cfg.get("stop_loss_usd"))
    reference = find_scenario(stage4b, ref_cfg.get("side_filter", "long"), ref_cfg.get("take_profit_usd"), ref_cfg.get("stop_loss_usd"))

    multipliers = [float(x) for x in (cfg.get("stress_tests", {}) or {}).get("cost_multipliers", [1, 2, 3, 4])]
    cost_stress = approximate_cost_stress(selected, multipliers=multipliers)
    decision = decide(selected, reference, cfg, cost_stress)

    report_dir = Path(args.report_dir or cfg.get("report_dir", "data/reports"))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_json = report_dir / f"stage4c_selected_scenario_summary_{stamp}.json"
    out_md = report_dir / f"stage4c_selected_scenario_summary_{stamp}.md"

    payload = {
        "ok": True,
        "stage": "stage4c_selected_scenario_validation",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_stage4b_summary": str(summary_path),
        "selected": selected,
        "reference": reference,
        "cost_stress": cost_stress,
        "decision": decision,
        "warning": "Diagnostic only. Cost stress is approximate unless trade-level rows are supplied. No paper-order. No live trading.",
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
