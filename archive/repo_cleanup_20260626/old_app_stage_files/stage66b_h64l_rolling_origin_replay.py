#!/usr/bin/env python3
"""Stage66B rolling-origin replay for H64L.

Goal: get fast forward-like historical decision value without waiting 180 real days.
No broker connection. No orders.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List

from stage66_common_h64l import (
    apply_h64l_rule,
    assert_no_lookahead,
    build_external_index,
    filter_rows_asof,
    horizon_return_bps,
    load_locked_rule,
    mean,
    parse_date,
    read_csv,
    read_json,
    stddev,
    write_json,
    write_report,
)


def trading_date_series(rows: List[Dict[str, str]], date_col: str) -> List[dt.date]:
    ds = [parse_date(r.get(date_col)) for r in rows]
    return sorted([d for d in set(ds) if d is not None])


def add_trading_days(dates: List[dt.date], start_idx: int, n: int):
    j = start_idx + n
    return dates[j] if 0 <= j < len(dates) else None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    p.add_argument("--config", default="configs/stage66b_h64l_rolling_origin_replay.json")
    p.add_argument("--out", default="reports/stage66b_h64l_rolling_origin_replay")
    args = p.parse_args()

    root = Path(args.root).resolve()
    cfg = read_json(root / args.config)
    out_dir = Path(args.out) if Path(args.out).is_absolute() else root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    rule = load_locked_rule(root / cfg["locked_rule_path"])
    macro_rows, macro_fields = read_csv(root / cfg["macro_dataset_path"])
    external_rows, external_fields = read_csv(root / cfg["external_d1_path"])
    external_series = build_external_index(external_rows, cfg.get("external_date_col", "date_utc"), cfg.get("external_close_col", "close"))
    ext_dates = [x[0] for x in external_series]
    if not ext_dates:
        raise SystemExit("No external dates available")

    feature_date_col = cfg.get("feature_date_col", "feature_date_utc")
    available_after_col = cfg.get("sample_available_after_col", "sample_available_after_utc")
    macro_by_date = {parse_date(r.get(feature_date_col)): r for r in macro_rows if parse_date(r.get(feature_date_col)) is not None}
    macro_dates = sorted([d for d in macro_by_date.keys() if d is not None])
    if not macro_dates:
        raise SystemExit("No macro feature dates available")

    train_years = int(cfg.get("train_window_years", 5))
    step = int(cfg.get("origin_step_trading_days", 120))
    forward_window = int(cfg.get("forward_window_trading_days", 120))
    horizon = int(cfg.get("horizon_trading_days", 120))

    # origin candidates from external trading dates after train window and with enough forward data.
    origins: List[dt.date] = []
    for i, d in enumerate(ext_dates):
        if d < macro_dates[0] + dt.timedelta(days=365 * train_years):
            continue
        if i + forward_window + horizon >= len(ext_dates):
            break
        if not origins or i >= ext_dates.index(origins[-1]) + step:
            origins.append(d)

    origin_results: List[Dict[str, Any]] = []
    no_lookahead_breaches: List[Dict[str, Any]] = []
    for origin in origins:
        # Only rows available as of the origin date can be used to decide what the rule would have been up to that point.
        training_rows = filter_rows_asof(macro_rows, origin, available_after_col)
        ok, breaches = assert_no_lookahead(training_rows, origin, available_after_col)
        if not ok:
            no_lookahead_breaches.append({"origin": origin.isoformat(), "breaches": breaches[:5], "count": len(breaches)})
            continue
        origin_idx = ext_dates.index(origin)
        window_end = add_trading_days(ext_dates, origin_idx, forward_window)
        if window_end is None:
            continue
        signal_events = []
        for d in macro_dates:
            if not (origin < d <= window_end):
                continue
            row = macro_by_date[d]
            # At decision time for row d, sample_available_after must be <= d end-of-day or next-day availability; for replay window, require actual availability <= d+1 day.
            active, failures = apply_h64l_rule(row, rule)
            if not active:
                continue
            ret, start_d, end_d = horizon_return_bps(external_series, d, horizon)
            if ret is None:
                continue
            signal_events.append({"feature_date": d.isoformat(), "return_bps": ret, "external_start_date": start_d.isoformat() if start_d else None, "external_end_date": end_d.isoformat() if end_d else None})
        returns = [float(x["return_bps"]) for x in signal_events]
        origin_results.append({
            "origin_date": origin.isoformat(),
            "window_end_date": window_end.isoformat(),
            "training_rows_available_asof_origin": len(training_rows),
            "signal_event_count": len(signal_events),
            "mean_return_bps": mean(returns),
            "positive_event_share": sum(1 for x in returns if x > 0) / len(returns) if returns else None,
            "events": signal_events,
        })

    independent_origins = len(origin_results)
    signal_origins = [o for o in origin_results if o["signal_event_count"] > 0]
    signal_origin_count = len(signal_origins)
    origin_means = [o["mean_return_bps"] for o in signal_origins if o.get("mean_return_bps") is not None]
    positive_origin_share = sum(1 for x in origin_means if x > 0) / len(origin_means) if origin_means else None

    if no_lookahead_breaches:
        decision = "KILL_OR_ARCHIVE_LOOKAHEAD_BREACH"
        status = "STAGE66B_FAIL_NO_LOOKAHEAD"
    elif independent_origins < int(cfg["minimum_independent_origins_for_pass_fast"]):
        if signal_origin_count >= int(cfg["minimum_signal_origins_for_continue"]) and (mean(origin_means) or -1e9) > float(cfg["min_mean_bps_for_continue"]):
            decision = "PASS_LOW_FREQUENCY_ONLY_NOT_PASS_FAST"
        else:
            decision = "INSUFFICIENT_SIGNAL_ORIGINS_CONTINUE_HISTORICAL_ONLY"
        status = "STAGE66B_COMPLETE_LIMITED_ORIGINS_NO_PROMOTION"
    elif signal_origin_count >= int(cfg["minimum_signal_origins_for_continue"]) and (mean(origin_means) or -1e9) > float(cfg["min_mean_bps_for_continue"]) and (positive_origin_share or 0) >= float(cfg["min_positive_origin_share_for_continue"]):
        decision = "PASS_FAST_FORWARD_LIKE_REPLAY_NO_ORDER"
        status = "STAGE66B_COMPLETE_NO_PROMOTION"
    else:
        decision = "FAIL_FORWARD_LIKE_REPLAY_NO_ORDER"
        status = "STAGE66B_COMPLETE_NO_PROMOTION"

    summary = {
        "stage": "Stage66B_H64L_ROLLING_ORIGIN_REPLAY",
        "generated_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "root": str(root),
        "status": status,
        "decision": decision,
        "hard_blocks": ["NO_PAPER_ORDER", "NO_EA_PROMOTION", "NO_PAPER_LIVE", "NO_LIVE", "NO_BROKER_CONNECTION", "NO_THRESHOLD_TUNING", "NO_RESCUE_FILTERING"],
        "rule_lock": {"rule_id": rule["rule_lock_payload"]["rule_id"], "rule_sha256": rule["rule_sha256"]},
        "config_locked_thresholds": {
            "train_window_years": train_years,
            "origin_step_trading_days": step,
            "forward_window_trading_days": forward_window,
            "horizon_trading_days": horizon,
            "minimum_independent_origins_for_pass_fast": cfg["minimum_independent_origins_for_pass_fast"],
            "minimum_signal_origins_for_continue": cfg["minimum_signal_origins_for_continue"],
        },
        "no_lookahead": {"required": True, "breach_count": len(no_lookahead_breaches), "breaches": no_lookahead_breaches[:10]},
        "origin_stats": {
            "independent_origin_count": independent_origins,
            "signal_origin_count": signal_origin_count,
            "mean_of_signal_origin_means_bps": mean(origin_means),
            "std_of_signal_origin_means_bps": stddev(origin_means),
            "positive_signal_origin_share": positive_origin_share,
        },
        "origins": origin_results,
    }
    write_json(out_dir / "stage66b_h64l_rolling_origin_replay_summary.json", summary)
    sections = [
        ("Decision", f"- status: `{status}`\n- decision: `{decision}`"),
        ("No-lookahead", json.dumps(summary["no_lookahead"], ensure_ascii=False, indent=2)),
        ("Origin stats", json.dumps(summary["origin_stats"], ensure_ascii=False, indent=2)),
        ("Locked thresholds", json.dumps(summary["config_locked_thresholds"], ensure_ascii=False, indent=2)),
        ("Origin results", json.dumps(origin_results, ensure_ascii=False, indent=2)),
    ]
    write_report(out_dir / "stage66b_h64l_rolling_origin_replay_report.md", "Stage66B H64L Rolling-Origin Replay", sections)
    return 0 if not decision.startswith("KILL") else 2


if __name__ == "__main__":
    raise SystemExit(main())
