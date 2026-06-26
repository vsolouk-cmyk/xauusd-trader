#!/usr/bin/env python3
"""Stage66C H64L v2 paper-execution simulator.

No broker connection. No orders. No EA promotion. This is a historical,
file-based, position-level simulator for the reconciled H64L v2 rule-lock.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from stage66_common_h64l import (
    apply_h64l_rule,
    load_locked_rule,
    parse_date,
    parse_datetime,
    parse_float,
    read_csv,
    read_json,
    write_json,
    write_report,
)

HARD_BLOCKS = [
    "NO_PAPER_ORDER",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_BROKER_CONNECTION",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE66C",
    "NO_THRESHOLD_TUNING",
    "NO_PROMOTION_FROM_SIMULATOR_ONLY",
]


def mean(xs: List[float]) -> Optional[float]:
    clean = [x for x in xs if x is not None and not math.isnan(x)]
    return sum(clean) / len(clean) if clean else None


def stddev(xs: List[float]) -> Optional[float]:
    clean = [x for x in xs if x is not None and not math.isnan(x)]
    if len(clean) < 2:
        return None
    m = sum(clean) / len(clean)
    return math.sqrt(sum((x - m) ** 2 for x in clean) / (len(clean) - 1))


def pct(x: float) -> float:
    return x * 100.0


def max_drawdown_pct(equity_curve: List[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak > 0:
            dd = (value / peak - 1.0) * 100.0
            max_dd = min(max_dd, dd)
    return max_dd


def first_index_on_or_after(daily: List[Dict[str, Any]], target: dt.date) -> Optional[int]:
    lo, hi = 0, len(daily)
    while lo < hi:
        mid = (lo + hi) // 2
        if daily[mid]["date"] < target:
            lo = mid + 1
        else:
            hi = mid
    return lo if lo < len(daily) else None


def load_external_d1(path: Path, date_col: str) -> List[Dict[str, Any]]:
    rows, fields = read_csv(path)
    daily: List[Dict[str, Any]] = []
    for row in rows:
        d = parse_date(row.get(date_col))
        close = parse_float(row.get("close"))
        if d is None or close is None or close <= 0:
            continue
        open_ = parse_float(row.get("open")) or close
        high = parse_float(row.get("high")) or max(open_, close)
        low = parse_float(row.get("low")) or min(open_, close)
        volume = parse_float(row.get("volume"))
        daily.append({"date": d, "open": open_, "high": high, "low": low, "close": close, "volume": volume, "raw": row})
    daily.sort(key=lambda r: r["date"])
    return daily


def available_entry_date(row: Dict[str, Any], feature_date_col: str, available_after_col: str) -> Optional[dt.date]:
    feature_date = parse_date(row.get(feature_date_col))
    available_after = parse_datetime(row.get(available_after_col))
    if feature_date is None:
        return None
    if available_after is None:
        return feature_date
    # Use the later of feature date and availability date. If sample is available at 00:00 UTC,
    # same-day close is allowed in this no-order simulator; intraday execution is not assumed.
    return max(feature_date, available_after.date())


def build_paper_positions(
    macro_rows: List[Dict[str, str]],
    daily: List[Dict[str, Any]],
    locked_rule: Dict[str, Any],
    feature_date_col: str,
    available_after_col: str,
    holding_period_trading_days: int,
    entry_delay_trading_days: int,
    base_round_trip_cost_bps: float,
    feed_mismatch_penalty_bps: float,
    non_overlap: bool = True,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    active_candidates: List[Dict[str, Any]] = []
    for row in macro_rows:
        is_active, failures = apply_h64l_rule(row, locked_rule)
        if not is_active:
            continue
        fd = parse_date(row.get(feature_date_col))
        available_date = available_entry_date(row, feature_date_col, available_after_col)
        if fd is None or available_date is None:
            continue
        active_candidates.append({"feature_date": fd, "available_date": available_date, "row": row})
    active_candidates.sort(key=lambda x: (x["available_date"], x["feature_date"]))

    positions: List[Dict[str, Any]] = []
    skipped_overlap = 0
    skipped_missing_entry = 0
    skipped_missing_exit = 0
    next_entry_allowed_idx = -1
    total_cost_bps = float(base_round_trip_cost_bps) + float(feed_mismatch_penalty_bps)

    for idx, candidate in enumerate(active_candidates):
        entry_idx = first_index_on_or_after(daily, candidate["available_date"])
        if entry_idx is None:
            skipped_missing_entry += 1
            continue
        entry_idx += int(entry_delay_trading_days)
        if entry_idx >= len(daily):
            skipped_missing_entry += 1
            continue
        if non_overlap and entry_idx <= next_entry_allowed_idx:
            skipped_overlap += 1
            continue
        exit_idx = entry_idx + int(holding_period_trading_days)
        if exit_idx >= len(daily):
            skipped_missing_exit += 1
            continue

        entry = daily[entry_idx]
        exit_ = daily[exit_idx]
        entry_price = entry["close"]
        exit_price = exit_["close"]
        gross_bps = (exit_price / entry_price - 1.0) * 10000.0
        net_bps = gross_bps - total_cost_bps
        window = daily[entry_idx : exit_idx + 1]
        min_low = min(x["low"] for x in window)
        max_high = max(x["high"] for x in window)
        mae_bps = (min_low / entry_price - 1.0) * 10000.0
        mfe_bps = (max_high / entry_price - 1.0) * 10000.0
        holding_calendar_days = (exit_["date"] - entry["date"]).days
        positions.append(
            {
                "trade_id": len(positions) + 1,
                "signal_feature_date": candidate["feature_date"].isoformat(),
                "signal_available_date": candidate["available_date"].isoformat(),
                "entry_date": entry["date"].isoformat(),
                "exit_date": exit_["date"].isoformat(),
                "entry_close": entry_price,
                "exit_close": exit_price,
                "holding_trading_days": int(holding_period_trading_days),
                "holding_calendar_days": holding_calendar_days,
                "gross_return_bps": gross_bps,
                "cost_and_feed_penalty_bps": total_cost_bps,
                "net_return_bps": net_bps,
                "mae_bps": mae_bps,
                "mfe_bps": mfe_bps,
                "entry_year": entry["date"].year,
                "exit_year": exit_["date"].year,
            }
        )
        if non_overlap:
            next_entry_allowed_idx = exit_idx

    diagnostics = {
        "active_candidate_rows": len(active_candidates),
        "closed_positions": len(positions),
        "skipped_overlap": skipped_overlap,
        "skipped_missing_entry": skipped_missing_entry,
        "skipped_missing_exit_or_unmatured": skipped_missing_exit,
        "total_cost_and_feed_penalty_bps": total_cost_bps,
    }
    return positions, diagnostics


def summarize_positions(positions: List[Dict[str, Any]], sizing_bands: List[Dict[str, Any]], stress_costs_bps: List[float], base_cost_bps: float) -> Dict[str, Any]:
    rets = [float(p["net_return_bps"]) for p in positions]
    gross = [float(p["gross_return_bps"]) for p in positions]
    wins = [x for x in rets if x > 0]
    losses = [x for x in rets if x <= 0]
    trade_count = len(rets)
    years: Dict[str, int] = {}
    for p in positions:
        y = str(p["entry_year"])
        years[y] = years.get(y, 0) + 1
    win_rate = len(wins) / trade_count if trade_count else None
    payoff_ratio = (mean(wins) / abs(mean(losses))) if wins and losses and mean(losses) not in (None, 0) else None

    base_stats = {
        "trade_count": trade_count,
        "win_rate": win_rate,
        "mean_gross_return_bps": mean(gross),
        "mean_net_return_bps": mean(rets),
        "median_net_return_bps": sorted(rets)[trade_count // 2] if trade_count else None,
        "std_net_return_bps": stddev(rets),
        "min_net_return_bps": min(rets) if rets else None,
        "max_net_return_bps": max(rets) if rets else None,
        "mean_mae_bps": mean([float(p["mae_bps"]) for p in positions]),
        "worst_mae_bps": min([float(p["mae_bps"]) for p in positions]) if positions else None,
        "mean_mfe_bps": mean([float(p["mfe_bps"]) for p in positions]),
        "best_mfe_bps": max([float(p["mfe_bps"]) for p in positions]) if positions else None,
        "payoff_ratio_win_mean_abs_loss_mean": payoff_ratio,
        "trade_count_by_entry_year": years,
        "max_year_trade_share": max(years.values()) / trade_count if trade_count and years else None,
    }

    band_stats: List[Dict[str, Any]] = []
    for band in sizing_bands:
        frac = float(band["notional_fraction"])
        equity = 1.0
        curve = [equity]
        for r in rets:
            equity *= 1.0 + frac * (r / 10000.0)
            curve.append(equity)
        band_stats.append(
            {
                "band": band["band"],
                "notional_fraction": frac,
                "final_equity_multiple": equity,
                "total_return_pct": (equity - 1.0) * 100.0,
                "max_drawdown_pct": max_drawdown_pct(curve),
            }
        )

    stress_stats: List[Dict[str, Any]] = []
    gross_from_positions = [float(p["gross_return_bps"]) for p in positions]
    for stress_cost in stress_costs_bps:
        stressed = [g - float(stress_cost) for g in gross_from_positions]
        stress_stats.append(
            {
                "round_trip_total_penalty_bps": float(stress_cost),
                "mean_net_return_bps": mean(stressed),
                "win_rate": len([x for x in stressed if x > 0]) / len(stressed) if stressed else None,
                "min_net_return_bps": min(stressed) if stressed else None,
            }
        )

    return {"position_stats": base_stats, "sizing_band_stats": band_stats, "stress_cost_stats": stress_stats}


def decide(summary: Dict[str, Any], thresholds: Dict[str, Any]) -> str:
    stats = summary["position_stats"]
    trade_count = stats.get("trade_count") or 0
    mean_net = stats.get("mean_net_return_bps")
    win_rate = stats.get("win_rate")
    min_net = stats.get("min_net_return_bps")
    base_band = next((b for b in summary["sizing_band_stats"] if b["band"] == thresholds.get("base_band_name", "B_base")), None)
    base_dd = abs(base_band["max_drawdown_pct"]) if base_band else 999.0
    stress_100 = next((s for s in summary["stress_cost_stats"] if abs(s["round_trip_total_penalty_bps"] - float(thresholds["stress_gate_penalty_bps"])) < 1e-9), None)
    stress_mean = stress_100.get("mean_net_return_bps") if stress_100 else None

    if trade_count < int(thresholds["min_closed_positions"]):
        return "INSUFFICIENT_CLOSED_POSITIONS_NO_ORDER"
    if mean_net is None or mean_net <= 0 or win_rate is None:
        return "FAIL_PAPER_EXECUTION_SIM_NO_ORDER"
    if min_net is not None and min_net < float(thresholds["kill_if_single_trade_loss_bps_lt"]):
        return "FAIL_SINGLE_TRADE_LOSS_TOO_LARGE_NO_ORDER"
    if win_rate >= float(thresholds["pass_fast_min_win_rate"]) and mean_net >= float(thresholds["pass_fast_min_mean_net_bps"]) and base_dd <= float(thresholds["pass_fast_max_base_band_drawdown_pct"]) and stress_mean is not None and stress_mean >= float(thresholds["pass_fast_min_stress_mean_net_bps"]):
        return "PASS_FAST_PAPER_EXECUTION_SIM_BAND_B_NO_ORDER"
    if mean_net >= float(thresholds["small_size_min_mean_net_bps"]) and win_rate >= float(thresholds["small_size_min_win_rate"]):
        return "PASS_SMALL_SIZE_ONLY_PAPER_EXECUTION_SIM_NO_ORDER"
    return "FAIL_PAPER_EXECUTION_SIM_NO_ORDER"


def write_positions_csv(path: Path, positions: List[Dict[str, Any]]) -> None:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "trade_id",
        "signal_feature_date",
        "signal_available_date",
        "entry_date",
        "exit_date",
        "entry_close",
        "exit_close",
        "holding_trading_days",
        "holding_calendar_days",
        "gross_return_bps",
        "cost_and_feed_penalty_bps",
        "net_return_bps",
        "mae_bps",
        "mfe_bps",
        "entry_year",
        "exit_year",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for p in positions:
            writer.writerow({k: p.get(k) for k in fields})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", default="configs/stage66c_h64l_paper_execution_simulator.json")
    parser.add_argument("--out", default="reports/stage66c_h64l_paper_execution_simulator")
    parser.add_argument("--write-positions", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    cfg = read_json(root / args.config)
    out_dir = Path(args.out) if Path(args.out).is_absolute() else root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    issues: List[Dict[str, Any]] = []
    f2_path = root / cfg["stage66f2_summary_path"]
    if not f2_path.exists():
        issues.append({"scope": "stage66f2", "issue": "missing", "path": str(f2_path)})
        f2 = {}
    else:
        f2 = read_json(f2_path)
    required_gate = cfg["required_stage66f2_decision"]
    if f2.get("decision") != required_gate:
        issues.append({"scope": "stage66f2", "issue": "gate_not_open", "expected": required_gate, "actual": f2.get("decision")})

    macro_path = root / cfg["macro_dataset_path"]
    external_path = root / cfg["external_d1_path"]
    rule_path = root / cfg["locked_rule_path"]
    for label, path in [("macro_dataset", macro_path), ("external_d1", external_path), ("locked_rule", rule_path)]:
        if not path.exists():
            issues.append({"scope": label, "issue": "missing", "path": str(path)})

    if issues:
        summary = {
            "stage": "Stage66C_H64L_PAPER_EXECUTION_SIMULATOR",
            "generated_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "root": str(root),
            "status": "STAGE66C_INPUT_FAIL_NO_ORDER",
            "decision": "STOP_FIX_STAGE66C_INPUTS_OR_GATE_NO_ORDER",
            "hard_blocks": HARD_BLOCKS,
            "issues": issues,
        }
        write_json(out_dir / "stage66c_h64l_paper_execution_simulator_summary.json", summary)
        write_report(out_dir / "stage66c_h64l_paper_execution_simulator_report.md", "Stage66C H64L Paper-Execution Simulator", [("Decision", f"- status: `{summary['status']}`\n- decision: `{summary['decision']}`"), ("Issues", json.dumps(issues, ensure_ascii=False, indent=2))])
        return 2

    macro_rows, macro_fields = read_csv(macro_path)
    daily = load_external_d1(external_path, cfg["external_date_col"])
    locked_rule = load_locked_rule(rule_path)

    positions, diagnostics = build_paper_positions(
        macro_rows=macro_rows,
        daily=daily,
        locked_rule=locked_rule,
        feature_date_col=cfg["feature_date_col"],
        available_after_col=cfg["available_after_col"],
        holding_period_trading_days=int(cfg["holding_period_trading_days"]),
        entry_delay_trading_days=int(cfg["entry_delay_trading_days"]),
        base_round_trip_cost_bps=float(cfg["round_trip_execution_cost_bps"]),
        feed_mismatch_penalty_bps=float(cfg["feed_mismatch_penalty_bps"]),
        non_overlap=bool(cfg["single_position_non_overlapping"]),
    )
    metrics = summarize_positions(
        positions=positions,
        sizing_bands=cfg["sizing_bands"],
        stress_costs_bps=cfg["stress_total_penalty_bps"],
        base_cost_bps=float(cfg["round_trip_execution_cost_bps"]) + float(cfg["feed_mismatch_penalty_bps"]),
    )
    decision = decide(metrics, cfg["decision_thresholds"])
    status = "STAGE66C_COMPLETE_NO_PROMOTION"
    if decision.startswith("FAIL"):
        status = "STAGE66C_FAIL_NO_ORDER"
    elif decision.startswith("INSUFFICIENT"):
        status = "STAGE66C_INSUFFICIENT_NO_ORDER"

    summary = {
        "stage": "Stage66C_H64L_PAPER_EXECUTION_SIMULATOR",
        "generated_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "root": str(root),
        "status": status,
        "decision": decision,
        "hard_blocks": HARD_BLOCKS,
        "input_gate": {
            "stage66f2_summary_path": cfg["stage66f2_summary_path"],
            "required_stage66f2_decision": required_gate,
            "actual_stage66f2_decision": f2.get("decision"),
            "stage66f2_gate_ok": f2.get("decision") == required_gate,
        },
        "rule_lock": {"rule_id": locked_rule["rule_lock_payload"].get("rule_id"), "rule_sha256": locked_rule.get("rule_sha256"), "rule_path": cfg["locked_rule_path"]},
        "execution_model": {
            "entry_rule": cfg["entry_rule"],
            "entry_delay_trading_days": cfg["entry_delay_trading_days"],
            "exit_rule": f"fixed_{cfg['holding_period_trading_days']}_trading_day_horizon",
            "position_mode": "single_position_non_overlapping" if cfg["single_position_non_overlapping"] else "stacking_allowed",
            "round_trip_execution_cost_bps": cfg["round_trip_execution_cost_bps"],
            "feed_mismatch_penalty_bps": cfg["feed_mismatch_penalty_bps"],
            "total_default_penalty_bps": diagnostics["total_cost_and_feed_penalty_bps"],
        },
        "diagnostics": diagnostics,
        "metrics": metrics,
        "decision_thresholds": cfg["decision_thresholds"],
        "outputs": {
            "summary_json": str(out_dir / "stage66c_h64l_paper_execution_simulator_summary.json"),
            "report_md": str(out_dir / "stage66c_h64l_paper_execution_simulator_report.md"),
            "positions_csv": str(out_dir / "stage66c_h64l_paper_positions.csv") if args.write_positions else None,
        },
        "next_step": "If PASS_FAST, build Stage66G controlled paper-order design package; if PASS_SMALL_SIZE_ONLY, reduce sizing and run stress review; if FAIL/INSUFFICIENT, start Stage66D complementary thesis path. No broker/order path is authorized by Stage66C alone.",
    }
    write_json(out_dir / "stage66c_h64l_paper_execution_simulator_summary.json", summary)
    if args.write_positions:
        write_positions_csv(out_dir / "stage66c_h64l_paper_positions.csv", positions)
    sections = [
        ("Decision", f"- status: `{status}`\n- decision: `{decision}`"),
        ("Input gate", json.dumps(summary["input_gate"], ensure_ascii=False, indent=2)),
        ("Execution model", json.dumps(summary["execution_model"], ensure_ascii=False, indent=2)),
        ("Diagnostics", json.dumps(diagnostics, ensure_ascii=False, indent=2)),
        ("Position stats", json.dumps(metrics["position_stats"], ensure_ascii=False, indent=2)),
        ("Sizing band stats", json.dumps(metrics["sizing_band_stats"], ensure_ascii=False, indent=2)),
        ("Stress cost stats", json.dumps(metrics["stress_cost_stats"], ensure_ascii=False, indent=2)),
        ("Hard blocks", "\n".join(f"- `{b}`" for b in HARD_BLOCKS)),
    ]
    write_report(out_dir / "stage66c_h64l_paper_execution_simulator_report.md", "Stage66C H64L Paper-Execution Simulator", sections)
    return 0 if not decision.startswith("FAIL") else 2


if __name__ == "__main__":
    raise SystemExit(main())
