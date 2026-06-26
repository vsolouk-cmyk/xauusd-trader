#!/usr/bin/env python3
"""Stage66A H64L concentration / outlier / episode audit.

This is the first fast decision audit after Stage65 was demoted to background telemetry.
No broker connection. No orders. No threshold tuning.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from stage66_common_h64l import (
    apply_h64l_rule,
    build_external_index,
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


def build_events(macro_rows: List[Dict[str, str]], external_series, cfg: Dict[str, Any], rule: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    feature_date_col = cfg.get("feature_date_col", "feature_date_utc")
    horizon = int(cfg.get("horizon_trading_days", rule["rule_lock_payload"].get("horizon_trading_days", 120)))
    rows_sorted = sorted([r for r in macro_rows if parse_date(r.get(feature_date_col)) is not None], key=lambda r: parse_date(r.get(feature_date_col)))
    active_events: List[Dict[str, Any]] = []
    all_rows_eval: List[Dict[str, Any]] = []
    for idx, r in enumerate(rows_sorted):
        fd = parse_date(r.get(feature_date_col))
        active, failures = apply_h64l_rule(r, rule)
        event = {
            "row_index": idx,
            "feature_date": fd.isoformat() if fd else None,
            "active": active,
            "rule_failures": failures,
        }
        if active and fd:
            ret, start_d, end_d = horizon_return_bps(external_series, fd, horizon)
            event.update({
                "return_bps": ret,
                "external_start_date": start_d.isoformat() if start_d else None,
                "external_end_date": end_d.isoformat() if end_d else None,
            })
            if ret is not None:
                active_events.append(event)
        all_rows_eval.append(event)
    return active_events, all_rows_eval


def assign_episodes(active_events: List[Dict[str, Any]], all_rows_eval: List[Dict[str, Any]], merge_gap_lt: int) -> List[Dict[str, Any]]:
    active_by_row = {e["row_index"]: e for e in active_events}
    episodes: List[Dict[str, Any]] = []
    current = None
    inactive_count_since_active = 10**9
    for row in all_rows_eval:
        idx = row["row_index"]
        if idx in active_by_row:
            e = active_by_row[idx]
            if current is None or inactive_count_since_active >= merge_gap_lt:
                current = {"episode_id": len(episodes) + 1, "events": []}
                episodes.append(current)
            e["episode_id"] = current["episode_id"]
            current["events"].append(e)
            inactive_count_since_active = 0
        else:
            if current is not None:
                inactive_count_since_active += 1
    result: List[Dict[str, Any]] = []
    for ep in episodes:
        evs = ep["events"]
        returns = [float(e["return_bps"]) for e in evs if e.get("return_bps") is not None]
        result.append({
            "episode_id": ep["episode_id"],
            "start_feature_date": evs[0]["feature_date"] if evs else None,
            "end_feature_date": evs[-1]["feature_date"] if evs else None,
            "active_days": len(evs),
            "mean_return_bps": mean(returns),
            "sum_return_bps_overlap_not_tradable": sum(returns) if returns else None,
            "positive_mean_return": (mean(returns) or 0) > 0 if returns else False,
        })
    return result


def leave_one_out_means(episodes: List[Dict[str, Any]], active_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_ep: Dict[int, List[float]] = {}
    for e in active_events:
        if e.get("episode_id") is None or e.get("return_bps") is None:
            continue
        by_ep.setdefault(int(e["episode_id"]), []).append(float(e["return_bps"]))
    out = []
    for ep in episodes:
        exclude = int(ep["episode_id"])
        returns = []
        for eid, vals in by_ep.items():
            if eid != exclude:
                returns.extend(vals)
        out.append({"excluded_episode_id": exclude, "remaining_mean_return_bps": mean(returns), "remaining_event_count": len(returns)})
    return out


def decide(summary: Dict[str, Any], cfg: Dict[str, Any]) -> str:
    if summary["reconstruction"]["status"] != "PASS":
        return "KILL_OR_ARCHIVE_RECONSTRUCTION_MISMATCH"
    pos_eps = summary["episode_stats"]["positive_independent_episodes"]
    loo_min = summary["leave_one_out"]["min_remaining_mean_return_bps"]
    max_share = summary["episode_stats"]["max_episode_active_day_share"]
    if (
        pos_eps >= int(cfg["pass_fast_min_positive_independent_episodes"])
        and (loo_min is not None and loo_min > float(cfg["pass_fast_leave_one_out_min_mean_bps"]))
        and (max_share is not None and max_share <= float(cfg["pass_fast_max_episode_active_day_share"]))
    ):
        return "PASS_FAST_PAPER_SIM_BAND_B_ALLOWED_NO_ORDER"
    if pos_eps >= int(cfg["pass_small_size_min_positive_independent_episodes"]) and (loo_min is not None and loo_min > float(cfg["pass_small_leave_one_out_min_mean_bps"])):
        return "PASS_SMALL_SIZE_ONLY_PAPER_SIM_BAND_A_NO_ORDER"
    if summary["active_event_stats"]["active_event_count"] > 0:
        return "PASS_LOW_FREQUENCY_ONLY_CONTINUE_ANALYSIS_NO_ORDER"
    return "FAIL_NO_RECONSTRUCTED_ACTIVE_EVENTS"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    p.add_argument("--config", default="configs/stage66a_h64l_concentration_audit.json")
    p.add_argument("--out", default="reports/stage66a_h64l_concentration_audit")
    p.add_argument("--write-events", action="store_true")
    args = p.parse_args()

    root = Path(args.root).resolve()
    cfg = read_json(root / args.config)
    out_dir = Path(args.out) if Path(args.out).is_absolute() else root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    rule = load_locked_rule(root / cfg["locked_rule_path"])
    macro_rows, macro_fields = read_csv(root / cfg["macro_dataset_path"])
    external_rows, external_fields = read_csv(root / cfg["external_d1_path"])
    external_series = build_external_index(external_rows, cfg.get("external_date_col", "date_utc"), cfg.get("external_close_col", "close"))

    active_events, all_rows_eval = build_events(macro_rows, external_series, cfg, rule)
    episodes = assign_episodes(active_events, all_rows_eval, int(cfg["merge_episode_inactive_trading_days_lt"]))
    loo = leave_one_out_means(episodes, active_events)

    active_count = len(active_events)
    expected = int(cfg["expected_stage64r_candidate_active_days"])
    tol_pct = float(cfg["reconstruction_tolerance_pct"])
    diff_pct = abs(active_count - expected) / expected * 100.0 if expected else None
    reconstruction_status = "PASS" if diff_pct is not None and diff_pct <= tol_pct else "FAIL"

    returns = [float(e["return_bps"]) for e in active_events if e.get("return_bps") is not None]
    max_active_days = max([e["active_days"] for e in episodes], default=0)
    max_share = max_active_days / active_count if active_count else None
    positive_eps = sum(1 for e in episodes if e.get("positive_mean_return"))
    loo_vals = [x["remaining_mean_return_bps"] for x in loo if x.get("remaining_mean_return_bps") is not None]

    summary: Dict[str, Any] = {
        "stage": "Stage66A_H64L_CONCENTRATION_AUDIT",
        "generated_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "root": str(root),
        "hard_blocks": ["NO_PAPER_ORDER", "NO_EA_PROMOTION", "NO_PAPER_LIVE", "NO_LIVE", "NO_BROKER_CONNECTION", "NO_THRESHOLD_TUNING", "NO_RESCUE_FILTERING"],
        "rule_lock": {"rule_id": rule["rule_lock_payload"]["rule_id"], "rule_sha256": rule["rule_sha256"]},
        "config_locked_thresholds": {
            "merge_episode_inactive_trading_days_lt": cfg["merge_episode_inactive_trading_days_lt"],
            "pass_fast_min_positive_independent_episodes": cfg["pass_fast_min_positive_independent_episodes"],
            "pass_small_size_min_positive_independent_episodes": cfg["pass_small_size_min_positive_independent_episodes"],
            "reconstruction_tolerance_pct": cfg["reconstruction_tolerance_pct"],
        },
        "reconstruction": {
            "expected_stage64r_candidate_active_days": expected,
            "reconstructed_active_event_count_with_horizon": active_count,
            "difference_pct": diff_pct,
            "tolerance_pct": tol_pct,
            "status": reconstruction_status,
            "kill_or_archive_if_fail": "RECONSTRUCTION_MISMATCH",
        },
        "active_event_stats": {
            "active_event_count": active_count,
            "mean_return_bps": mean(returns),
            "std_return_bps": stddev(returns),
            "min_return_bps": min(returns) if returns else None,
            "max_return_bps": max(returns) if returns else None,
            "positive_event_share": sum(1 for x in returns if x > 0) / len(returns) if returns else None,
        },
        "episode_stats": {
            "episode_count": len(episodes),
            "positive_independent_episodes": positive_eps,
            "max_episode_active_days": max_active_days,
            "max_episode_active_day_share": max_share,
            "episodes": episodes,
        },
        "leave_one_out": {
            "by_episode": loo,
            "min_remaining_mean_return_bps": min(loo_vals) if loo_vals else None,
        },
    }
    summary["decision"] = decide(summary, cfg)
    summary["status"] = "STAGE66A_COMPLETE_NO_PROMOTION" if not summary["decision"].startswith("KILL") else "STAGE66A_KILL_OR_ARCHIVE_NO_PROMOTION"

    write_json(out_dir / "stage66a_h64l_concentration_audit_summary.json", summary)
    if args.write_events:
        write_json(out_dir / "stage66a_h64l_active_events.json", active_events)
    sections = [
        ("Decision", f"- status: `{summary['status']}`\n- decision: `{summary['decision']}`"),
        ("Reconstruction", json.dumps(summary["reconstruction"], ensure_ascii=False, indent=2)),
        ("Active event stats", json.dumps(summary["active_event_stats"], ensure_ascii=False, indent=2)),
        ("Episode stats", json.dumps({k: v for k, v in summary["episode_stats"].items() if k != "episodes"}, ensure_ascii=False, indent=2)),
        ("Leave-one-out", json.dumps(summary["leave_one_out"], ensure_ascii=False, indent=2)),
        ("Episode table", json.dumps(episodes, ensure_ascii=False, indent=2)),
    ]
    write_report(out_dir / "stage66a_h64l_concentration_audit_report.md", "Stage66A H64L Concentration Audit", sections)
    return 0 if reconstruction_status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
