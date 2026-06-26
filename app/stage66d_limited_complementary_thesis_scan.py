#!/usr/bin/env python3
"""Stage66D limited complementary macro thesis scan.

Purpose:
- Evaluate a small pre-registered set of complementary XAUUSD macro theses.
- Use lag-safe Stage64K features and external D1 spot reference.
- Produce event-level and single-position non-overlap diagnostics.
- Never authorize broker/order/EA/live paths.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE66D",
    "NO_THRESHOLD_TUNING",
    "NO_RESCUE_FILTERING",
    "NO_PROMOTION_FROM_COMPLEMENTARY_SCAN_ONLY",
]


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_date(value: Any) -> Optional[dt.date]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return dt.datetime.fromisoformat(s).date()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip()
    if s == "" or s.lower() in {"nan", "none", "null"}:
        return None
    try:
        x = float(s)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    except ValueError:
        return None


def read_csv_dicts(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def first_existing(row: Dict[str, Any], candidates: Iterable[str]) -> Optional[str]:
    for c in candidates:
        if c in row:
            return c
    return None


def eval_condition(row: Dict[str, Any], condition: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    field = condition["field"]
    operator = condition["operator"]
    threshold = float(condition.get("threshold", 0.0))
    val = to_float(row.get(field))
    ok = False
    if val is not None:
        if operator == ">":
            ok = val > threshold
        elif operator == ">=":
            ok = val >= threshold
        elif operator == "<":
            ok = val < threshold
        elif operator == "<=":
            ok = val <= threshold
        elif operator == "==":
            ok = val == threshold
        else:
            raise ValueError(f"Unsupported operator: {operator}")
    return ok, {"field": field, "operator": operator, "threshold": threshold, "value": val, "ok": ok}


def load_macro(path: Path, date_columns: List[str]) -> Tuple[List[Dict[str, Any]], str]:
    rows = read_csv_dicts(path)
    if not rows:
        raise ValueError(f"Macro dataset empty: {path}")
    date_col = first_existing(rows[0], date_columns)
    if not date_col:
        raise ValueError(f"No macro date column found. Tried: {date_columns}")
    out = []
    for row in rows:
        d = parse_date(row.get(date_col))
        if d is None:
            continue
        rr = dict(row)
        rr["__macro_date"] = d
        out.append(rr)
    out.sort(key=lambda r: r["__macro_date"])
    if not out:
        raise ValueError("No parseable macro rows")
    return out, date_col


def load_external(path: Path, date_columns: List[str]) -> Tuple[List[Dict[str, Any]], str]:
    rows = read_csv_dicts(path)
    if not rows:
        raise ValueError(f"External D1 dataset empty: {path}")
    date_col = first_existing(rows[0], date_columns)
    if not date_col:
        raise ValueError(f"No external date column found. Tried: {date_columns}")
    out = []
    for row in rows:
        d = parse_date(row.get(date_col))
        close = to_float(row.get("close") or row.get("Close"))
        if d is None or close is None:
            continue
        rr = dict(row)
        rr["__external_date"] = d
        rr["__close"] = close
        out.append(rr)
    out.sort(key=lambda r: r["__external_date"])
    if not out:
        raise ValueError("No parseable external D1 rows")
    return out, date_col


def external_index_by_date(external_rows: List[Dict[str, Any]]) -> Dict[dt.date, int]:
    return {r["__external_date"]: i for i, r in enumerate(external_rows)}


def first_external_idx_on_or_after(external_rows: List[Dict[str, Any]], d: dt.date) -> Optional[int]:
    lo, hi = 0, len(external_rows) - 1
    ans = None
    while lo <= hi:
        mid = (lo + hi) // 2
        if external_rows[mid]["__external_date"] >= d:
            ans = mid
            hi = mid - 1
        else:
            lo = mid + 1
    return ans


def signal_active(row: Dict[str, Any], conditions: List[Dict[str, Any]]) -> Tuple[bool, List[Dict[str, Any]]]:
    details = []
    all_ok = True
    for cond in conditions:
        ok, detail = eval_condition(row, cond)
        details.append(detail)
        if not ok:
            all_ok = False
    return all_ok, details


def build_events(
    macro_rows: List[Dict[str, Any]],
    external_rows: List[Dict[str, Any]],
    conditions: List[Dict[str, Any]],
    horizon: int,
    total_penalty_bps: float,
    sample_available_columns: List[str],
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    events: List[Dict[str, Any]] = []
    counts = {
        "active_rows": 0,
        "skipped_missing_sample_available": 0,
        "skipped_missing_entry": 0,
        "skipped_missing_exit_or_unmatured": 0,
        "lookahead_breaches": 0,
    }
    for row in macro_rows:
        active, _ = signal_active(row, conditions)
        if not active:
            continue
        counts["active_rows"] += 1
        sample_col = first_existing(row, sample_available_columns)
        sample_date = parse_date(row.get(sample_col)) if sample_col else None
        if sample_date is None:
            counts["skipped_missing_sample_available"] += 1
            continue
        entry_idx = first_external_idx_on_or_after(external_rows, sample_date)
        if entry_idx is None:
            counts["skipped_missing_entry"] += 1
            continue
        exit_idx = entry_idx + int(horizon)
        if exit_idx >= len(external_rows):
            counts["skipped_missing_exit_or_unmatured"] += 1
            continue
        entry = external_rows[entry_idx]
        exit_ = external_rows[exit_idx]
        if entry["__external_date"] < sample_date:
            counts["lookahead_breaches"] += 1
            continue
        entry_close = entry["__close"]
        exit_close = exit_["__close"]
        gross_bps = (exit_close / entry_close - 1.0) * 10000.0
        net_bps = gross_bps - total_penalty_bps
        events.append(
            {
                "feature_date": row["__macro_date"].isoformat(),
                "sample_available_after_date": sample_date.isoformat(),
                "entry_date": entry["__external_date"].isoformat(),
                "exit_date": exit_["__external_date"].isoformat(),
                "entry_idx": entry_idx,
                "exit_idx": exit_idx,
                "entry_close": entry_close,
                "exit_close": exit_close,
                "gross_return_bps": gross_bps,
                "net_return_bps": net_bps,
            }
        )
    return events, counts


def select_non_overlapping_positions(events: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    selected: List[Dict[str, Any]] = []
    skipped_overlap = 0
    last_exit_idx = -1
    for ev in sorted(events, key=lambda x: (x["entry_idx"], x["exit_idx"])):
        if int(ev["entry_idx"]) <= last_exit_idx:
            skipped_overlap += 1
            continue
        pos = dict(ev)
        pos["position_id"] = len(selected) + 1
        selected.append(pos)
        last_exit_idx = int(ev["exit_idx"])
    return selected, skipped_overlap


def mean(xs: List[float]) -> Optional[float]:
    return sum(xs) / len(xs) if xs else None


def median(xs: List[float]) -> Optional[float]:
    if not xs:
        return None
    ys = sorted(xs)
    n = len(ys)
    mid = n // 2
    if n % 2:
        return ys[mid]
    return (ys[mid - 1] + ys[mid]) / 2.0


def std(xs: List[float]) -> Optional[float]:
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def max_drawdown_pct(returns_bps: List[float], notional_fraction: float) -> float:
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in returns_bps:
        equity *= 1.0 + notional_fraction * (r / 10000.0)
        peak = max(peak, equity)
        dd = (equity / peak - 1.0) * 100.0
        max_dd = min(max_dd, dd)
    return max_dd


def final_equity_multiple(returns_bps: List[float], notional_fraction: float) -> float:
    equity = 1.0
    for r in returns_bps:
        equity *= 1.0 + notional_fraction * (r / 10000.0)
    return equity


def summarize_positions(positions: List[Dict[str, Any]], sizing_bands: List[Dict[str, Any]]) -> Dict[str, Any]:
    rets = [float(p["net_return_bps"]) for p in positions]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    years: Dict[str, int] = {}
    for p in positions:
        y = str(p["entry_date"][:4])
        years[y] = years.get(y, 0) + 1
    max_year_share = max(years.values()) / len(positions) if positions else None
    win_mean = mean(wins)
    loss_mean_abs = abs(mean(losses)) if losses else None
    payoff = (win_mean / loss_mean_abs) if (win_mean is not None and loss_mean_abs not in (None, 0.0)) else None
    band_stats = []
    for band in sizing_bands:
        frac = float(band["notional_fraction"])
        eq = final_equity_multiple(rets, frac)
        band_stats.append(
            {
                "band": band["band"],
                "notional_fraction": frac,
                "final_equity_multiple": eq,
                "total_return_pct": (eq - 1.0) * 100.0,
                "max_drawdown_pct": max_drawdown_pct(rets, frac),
            }
        )
    return {
        "trade_count": len(positions),
        "win_rate": len(wins) / len(rets) if rets else None,
        "mean_net_return_bps": mean(rets),
        "median_net_return_bps": median(rets),
        "std_net_return_bps": std(rets),
        "min_net_return_bps": min(rets) if rets else None,
        "max_net_return_bps": max(rets) if rets else None,
        "payoff_ratio_win_mean_abs_loss_mean": payoff,
        "trade_count_by_entry_year": years,
        "max_year_trade_share": max_year_share,
        "sizing_band_stats": band_stats,
    }


def classify_thesis(summary: Dict[str, Any], thresholds: Dict[str, Any]) -> str:
    ps = summary["position_stats"]
    if ps["trade_count"] < int(thresholds["watch_min_closed_positions"]):
        return "KILL_INSUFFICIENT_POSITIONS"
    mean_net = ps["mean_net_return_bps"] if ps["mean_net_return_bps"] is not None else -10**9
    win_rate = ps["win_rate"] if ps["win_rate"] is not None else 0.0
    max_year_share = ps["max_year_trade_share"] if ps["max_year_trade_share"] is not None else 1.0
    base_band = thresholds["base_band_name"]
    base_stats = next((b for b in ps["sizing_band_stats"] if b["band"] == base_band), None)
    base_dd_abs = abs(base_stats["max_drawdown_pct"]) if base_stats else 999.0
    min_return = ps["min_net_return_bps"] if ps["min_net_return_bps"] is not None else -10**9

    pass_fast = (
        ps["trade_count"] >= int(thresholds["pass_fast_min_closed_positions"])
        and mean_net >= float(thresholds["pass_fast_min_mean_net_bps"])
        and win_rate >= float(thresholds["pass_fast_min_win_rate"])
        and base_dd_abs <= float(thresholds["pass_fast_max_base_band_drawdown_pct"])
        and max_year_share <= float(thresholds["max_year_trade_share"])
        and min_return >= float(thresholds["kill_if_single_trade_loss_bps_lt"])
    )
    if pass_fast:
        return "PASS_FAST_COMPLEMENTARY_CANDIDATE_NO_ORDER"

    watch = (
        ps["trade_count"] >= int(thresholds["watch_min_closed_positions"])
        and mean_net >= float(thresholds["watch_min_mean_net_bps"])
        and win_rate >= float(thresholds["watch_min_win_rate"])
        and min_return >= float(thresholds["kill_if_single_trade_loss_bps_lt"])
    )
    if watch:
        return "WATCH_COMPLEMENTARY_CANDIDATE_NO_ORDER"
    return "KILL_COMPLEMENTARY_CANDIDATE_NO_ORDER"


def gate_stage66h(root: Path, cfg: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    rel = cfg.get("stage66h_summary_path")
    if not rel:
        return False, {"ok": False, "issue": "stage66h_summary_path_missing_in_config"}
    path = root / rel
    if not path.exists():
        return False, {"ok": False, "issue": "stage66h_summary_missing", "path": rel}
    js = read_json(path)
    allowed = set(cfg.get("allowed_stage66h_decisions", []))
    decision = js.get("decision")
    ok = decision in allowed
    return ok, {
        "ok": ok,
        "path": rel,
        "decision": decision,
        "classification": js.get("classification"),
        "allowed_decisions": sorted(allowed),
    }


def run(root: Path, config_path: Path, out_dir: Path, write_positions: bool) -> Dict[str, Any]:
    cfg = read_json(config_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    gate_ok, gate = gate_stage66h(root, cfg)
    macro_path = root / cfg["macro_dataset_path"]
    external_path = root / cfg["external_d1_path"]
    macro_rows, macro_date_col = load_macro(macro_path, cfg["macro_date_columns"])
    external_rows, external_date_col = load_external(external_path, cfg["external_d1_date_columns"])

    total_penalty_bps = float(cfg.get("round_trip_execution_cost_bps", 35.0)) + float(cfg.get("feed_mismatch_penalty_bps", 15.0))
    sizing_bands = cfg["sizing_bands"]
    thresholds = cfg["decision_thresholds"]

    thesis_results: List[Dict[str, Any]] = []
    position_csv_paths: Dict[str, str] = {}

    for thesis in cfg["registered_theses"]:
        for horizon in thesis.get("horizons_trading_days", cfg.get("default_horizons_trading_days", [20, 60])):
            events, counts = build_events(
                macro_rows=macro_rows,
                external_rows=external_rows,
                conditions=thesis["conditions"],
                horizon=int(horizon),
                total_penalty_bps=total_penalty_bps,
                sample_available_columns=cfg["sample_available_columns"],
            )
            positions, skipped_overlap = select_non_overlapping_positions(events)
            ps = summarize_positions(positions, sizing_bands)
            result = {
                "thesis_id": thesis["thesis_id"],
                "hypothesis": thesis.get("hypothesis"),
                "horizon_trading_days": int(horizon),
                "conditions": thesis["conditions"],
                "diagnostics": {**counts, "matured_event_count": len(events), "closed_positions": len(positions), "skipped_overlap": skipped_overlap},
                "position_stats": ps,
            }
            result["classification"] = classify_thesis(result, thresholds) if gate_ok else "NOT_EVALUATED_STAGE66H_GATE_BLOCKED"
            thesis_results.append(result)

            if write_positions:
                safe_id = f"{thesis['thesis_id']}_H{int(horizon)}".replace("/", "_")
                pos_path = out_dir / f"stage66d_positions_{safe_id}.csv"
                with pos_path.open("w", encoding="utf-8", newline="") as f:
                    fieldnames = [
                        "position_id", "feature_date", "sample_available_after_date", "entry_date", "exit_date",
                        "entry_close", "exit_close", "gross_return_bps", "net_return_bps",
                        "entry_idx", "exit_idx",
                    ]
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for p in positions:
                        writer.writerow({k: p.get(k) for k in fieldnames})
                position_csv_paths[safe_id] = str(pos_path.relative_to(root)) if pos_path.is_relative_to(root) else str(pos_path)

    pass_fast = [r for r in thesis_results if r["classification"] == "PASS_FAST_COMPLEMENTARY_CANDIDATE_NO_ORDER"]
    watch = [r for r in thesis_results if r["classification"] == "WATCH_COMPLEMENTARY_CANDIDATE_NO_ORDER"]
    if not gate_ok:
        decision = "STOP_STAGE66D_STAGE66H_GATE_NOT_READY_NO_ORDER"
    elif pass_fast:
        decision = "STAGE66D_PASS_FAST_COMPLEMENTARY_SHORTLIST_NO_ORDER"
    elif watch:
        decision = "STAGE66D_WATCH_COMPLEMENTARY_CANDIDATES_NO_ORDER"
    else:
        decision = "STAGE66D_NO_COMPLEMENTARY_CANDIDATE_CONTINUE_H64L_BACKGROUND_NO_ORDER"

    top_ranked = sorted(
        thesis_results,
        key=lambda r: (
            r["classification"] != "PASS_FAST_COMPLEMENTARY_CANDIDATE_NO_ORDER",
            r["classification"] != "WATCH_COMPLEMENTARY_CANDIDATE_NO_ORDER",
            -(r["position_stats"].get("mean_net_return_bps") or -10**9),
            -(r["position_stats"].get("trade_count") or 0),
        ),
    )[:8]

    summary = {
        "stage": "Stage66D_LIMITED_COMPLEMENTARY_THESIS_SCAN",
        "status": "STAGE66D_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "generated_utc": utc_now(),
        "root": str(root),
        "config": str(config_path),
        "hard_blocks": HARD_BLOCKS,
        "input_gate": gate,
        "input_paths": {
            "macro_dataset_path": cfg["macro_dataset_path"],
            "external_d1_path": cfg["external_d1_path"],
            "stage66h_summary_path": cfg.get("stage66h_summary_path"),
        },
        "input_hashes": {
            "macro_dataset_sha256": sha256_file(macro_path),
            "external_d1_sha256": sha256_file(external_path),
            "config_sha256": sha256_file(config_path),
        },
        "macro_date_column": macro_date_col,
        "external_date_column": external_date_col,
        "macro_rows": len(macro_rows),
        "external_rows": len(external_rows),
        "scan_scope_lock": {
            "registered_thesis_count": len(cfg["registered_theses"]),
            "horizons": sorted(set(h for t in cfg["registered_theses"] for h in t.get("horizons_trading_days", cfg.get("default_horizons_trading_days", [])))),
            "no_unregistered_variants": True,
            "no_threshold_tuning": True,
            "no_historical_event_filtering": True,
        },
        "execution_model": {
            "entry_rule": "first_external_d1_close_on_or_after_sample_available_after_utc",
            "exit_rule": "fixed_horizon_by_registered_thesis",
            "position_mode": "single_position_non_overlapping",
            "round_trip_execution_cost_bps": float(cfg.get("round_trip_execution_cost_bps", 35.0)),
            "feed_mismatch_penalty_bps": float(cfg.get("feed_mismatch_penalty_bps", 15.0)),
            "total_penalty_bps": total_penalty_bps,
        },
        "counts": {
            "pass_fast_count": len(pass_fast),
            "watch_count": len(watch),
            "total_thesis_horizon_results": len(thesis_results),
        },
        "top_ranked_results": top_ranked,
        "all_results": thesis_results,
        "outputs": {
            "summary_json": str((out_dir / "stage66d_limited_complementary_thesis_scan_summary.json").relative_to(root)) if (out_dir / "stage66d_limited_complementary_thesis_scan_summary.json").is_relative_to(root) else str(out_dir / "stage66d_limited_complementary_thesis_scan_summary.json"),
            "report_md": str((out_dir / "stage66d_limited_complementary_thesis_scan_report.md").relative_to(root)) if (out_dir / "stage66d_limited_complementary_thesis_scan_report.md").is_relative_to(root) else str(out_dir / "stage66d_limited_complementary_thesis_scan_report.md"),
            "position_csvs": position_csv_paths,
        },
        "next_step": "If PASS_FAST, build Stage66E/Stage66I paper-simulation readiness for the selected complementary thesis; if WATCH, run stricter source/rolling-origin review; if no candidate, keep H64L daily readiness and revisit thesis registry only by explicit pre-registration.",
    }

    summary_path = out_dir / "stage66d_limited_complementary_thesis_scan_summary.json"
    write_json(summary_path, summary)
    write_report(out_dir / "stage66d_limited_complementary_thesis_scan_report.md", summary)
    return summary


def fmt(x: Any) -> str:
    if x is None:
        return "null"
    if isinstance(x, float):
        return f"{x:.4f}"
    return str(x)


def write_report(path: Path, summary: Dict[str, Any]) -> None:
    lines: List[str] = []
    lines.append("# Stage66D Limited Complementary Thesis Scan")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append(f"- status: `{summary['status']}`")
    lines.append(f"- decision: `{summary['decision']}`")
    lines.append("")
    lines.append("## Input gate")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(summary["input_gate"], indent=2, ensure_ascii=False, sort_keys=True))
    lines.append("```")
    lines.append("")
    lines.append("## Scan scope lock")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(summary["scan_scope_lock"], indent=2, ensure_ascii=False, sort_keys=True))
    lines.append("```")
    lines.append("")
    lines.append("## Top ranked thesis-horizon results")
    lines.append("")
    for r in summary["top_ranked_results"]:
        ps = r["position_stats"]
        diag = r["diagnostics"]
        lines.append(f"### `{r['thesis_id']}` H{r['horizon_trading_days']}")
        lines.append("")
        lines.append(f"- classification: `{r['classification']}`")
        lines.append(f"- active_rows: `{diag['active_rows']}`")
        lines.append(f"- matured_events: `{diag['matured_event_count']}`")
        lines.append(f"- closed_positions: `{diag['closed_positions']}`")
        lines.append(f"- skipped_overlap: `{diag['skipped_overlap']}`")
        lines.append(f"- mean_net_return_bps: `{fmt(ps['mean_net_return_bps'])}`")
        lines.append(f"- win_rate: `{fmt(ps['win_rate'])}`")
        lines.append(f"- min_net_return_bps: `{fmt(ps['min_net_return_bps'])}`")
        lines.append(f"- max_year_trade_share: `{fmt(ps['max_year_trade_share'])}`")
        lines.append("")
    lines.append("## Hard blocks")
    lines.append("")
    for b in summary["hard_blocks"]:
        lines.append(f"- `{b}`")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--write-positions", action="store_true")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    config_path = (root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    out_dir = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    summary = run(root, config_path, out_dir, args.write_positions)
    print(json.dumps({"status": summary["status"], "decision": summary["decision"], "counts": summary["counts"]}, indent=2))


if __name__ == "__main__":
    main()
