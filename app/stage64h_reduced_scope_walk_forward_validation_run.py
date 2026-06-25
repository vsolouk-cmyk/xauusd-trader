#!/usr/bin/env python3
"""Stage64H - Reduced-scope walk-forward validation run, no order path.

This stage consumes the Stage64F feature-only dataset and the Stage64G
predeclared validation design. It computes predeclared benchmark/candidate
outcomes over fixed horizons and fixed historical splits. It does not create
orders, EA signals, paper-live instructions, or any broker connection.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import statistics
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

STAGE = "Stage64H_REDUCED_SCOPE_WALK_FORWARD_VALIDATION_RUN_NO_ORDER"
STATUS = "REDUCED_SCOPE_WALK_FORWARD_VALIDATION_COMPLETE_NO_PROMOTION"


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_date_utc(value: str) -> dt.date:
    s = (value or "").strip()
    if not s:
        raise ValueError("empty date")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    if "T" in s:
        return dt.datetime.fromisoformat(s).date()
    return dt.date.fromisoformat(s[:10])


def parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip()
    if s == "" or s.lower() in {"nan", "none", "null"}:
        return None
    try:
        x = float(s)
    except ValueError:
        return None
    if not math.isfinite(x):
        return None
    return x


def read_json(path: Path, default: Optional[dict] = None) -> dict:
    if not path.exists():
        return {} if default is None else default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def write_csv(path: Path, rows: List[dict], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def read_csv_rows(path: Path) -> List[dict]:
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def locate_first(columns: Iterable[str], candidates: Iterable[str]) -> Optional[str]:
    cols = list(columns)
    lower_to_orig = {c.lower(): c for c in cols}
    for c in candidates:
        if c.lower() in lower_to_orig:
            return lower_to_orig[c.lower()]
    return None


def binom_sf_at_least(k: int, n: int, p: float = 0.5) -> float:
    """Exact P[X >= k] for X~Bin(n,p), stable enough for n in thousands."""
    if n <= 0:
        return 1.0
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    # Recurrence around probability of 0 to avoid scipy dependency.
    # For p=0.5 and n not too huge this is fine. If it underflows, fall back to normal.
    if n > 5000:
        mu = n * p
        var = n * p * (1.0 - p)
        z = ((k - 0.5) - mu) / math.sqrt(var)
        return 0.5 * math.erfc(z / math.sqrt(2.0))
    q = 1.0 - p
    prob = q ** n
    tail = 0.0
    for i in range(0, n + 1):
        if i >= k:
            tail += prob
        if i < n:
            if q == 0:
                prob = 0.0
            else:
                prob *= (n - i) / (i + 1) * (p / q)
    return max(0.0, min(1.0, tail))


def median(xs: List[float]) -> Optional[float]:
    return statistics.median(xs) if xs else None


def mean(xs: List[float]) -> Optional[float]:
    return statistics.fmean(xs) if xs else None


def max_drawdown(seq: List[float]) -> float:
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for x in seq:
        cum += x
        if cum > peak:
            peak = cum
        dd = cum - peak
        if dd < max_dd:
            max_dd = dd
    return max_dd


def split_for_date(d: dt.date, splits: List[dict]) -> Optional[str]:
    for sp in splits:
        start = dt.date.fromisoformat(sp["start"])
        end = dt.date.fromisoformat(sp["end"])
        if start <= d <= end:
            return sp["split_id"]
    return None


def load_dataset(path: Path, required_features: List[str], close_column_candidates: List[str], date_column_candidates: List[str]) -> Tuple[List[dict], str, str, List[str]]:
    rows_raw = read_csv_rows(path)
    if not rows_raw:
        raise RuntimeError(f"feature dataset is empty: {path}")
    cols = list(rows_raw[0].keys())
    date_col = locate_first(cols, date_column_candidates)
    close_col = locate_first(cols, close_column_candidates)
    if not date_col:
        raise RuntimeError(f"no date column found. candidates={date_column_candidates} columns={cols}")
    if not close_col:
        raise RuntimeError(f"no gold close column found. candidates={close_column_candidates} columns={cols}")
    missing = [c for c in required_features if c not in cols]
    if missing:
        raise RuntimeError(f"missing required feature columns: {missing}")

    rows: List[dict] = []
    for r in rows_raw:
        try:
            d = parse_date_utc(r[date_col])
        except Exception:
            continue
        close = parse_float(r.get(close_col))
        if close is None or close <= 0:
            continue
        rr = dict(r)
        rr["__date"] = d
        rr["__gold_close"] = close
        ok = True
        for c in required_features:
            x = parse_float(rr.get(c))
            if x is None:
                ok = False
                break
            rr[c] = x
        if ok:
            rows.append(rr)
    rows.sort(key=lambda x: x["__date"])
    return rows, date_col, close_col, missing


def sig_b0(row: dict) -> bool:
    return True


def sig_b1(row: dict) -> bool:
    return row["gold_sma20_over_50"] > 0 and row["gold_sma50_over_200"] > 0


def sig_h1(row: dict) -> bool:
    return sig_b1(row) and row["dxy_ret_20d"] < 0 and row["real_yield_change_20d"] < 0


def sig_h2(row: dict) -> bool:
    return sig_b1(row) and not (row["dxy_ret_20d"] > 0 and row["real_yield_change_20d"] > 0)


def sig_h3(row: dict) -> bool:
    return sig_h1(row) and row["vix_change_20d"] <= 0 and row["vix_sma20_over_50"] <= 0


SIGNAL_FUNCTIONS: Dict[str, Callable[[dict], bool]] = {
    "H64G_B0_ALWAYS_LONG_REFERENCE": sig_b0,
    "H64G_B1_GOLD_TREND_ONLY_REFERENCE": sig_b1,
    "H64G_H1_MACRO_TAILWIND_TREND_LONG": sig_h1,
    "H64G_H2_HEADWIND_AVOID_LONG_FILTER": sig_h2,
    "H64G_H3_VOL_SHOCK_SUPPRESSED_MACRO_LONG": sig_h3,
}


def evaluate_hypothesis(rows: List[dict], hypothesis_id: str, horizon: int, splits: List[dict]) -> Tuple[List[dict], List[dict]]:
    fn = SIGNAL_FUNCTIONS[hypothesis_id]
    detail: List[dict] = []
    n = len(rows)
    for i in range(0, n - horizon):
        r = rows[i]
        future = rows[i + horizon]
        split_id = split_for_date(r["__date"], splits)
        if not split_id:
            continue
        fwd_ret_bps = (future["__gold_close"] / r["__gold_close"] - 1.0) * 10000.0
        active = bool(fn(r))
        detail.append({
            "date_utc": r["__date"].isoformat() + "T00:00:00Z",
            "split_id": split_id,
            "hypothesis_id": hypothesis_id,
            "horizon_days": horizon,
            "active": active,
            "fwd_ret_bps": fwd_ret_bps,
            "strategy_ret_bps": fwd_ret_bps if active else 0.0,
        })
    split_rows: List[dict] = []
    for sp in splits:
        sid = sp["split_id"]
        part = [x for x in detail if x["split_id"] == sid]
        active_part = [x["fwd_ret_bps"] for x in part if x["active"]]
        strat = [x["strategy_ret_bps"] for x in part]
        wins = sum(1 for x in active_part if x > 0)
        active_n = len(active_part)
        total_n = len(part)
        p_sign = binom_sf_at_least(wins, active_n, 0.5) if active_n else 1.0
        split_rows.append({
            "split_id": sid,
            "hypothesis_id": hypothesis_id,
            "horizon_days": horizon,
            "eligible_days": total_n,
            "active_days": active_n,
            "exposure_share": active_n / total_n if total_n else 0.0,
            "mean_active_fwd_bps": mean(active_part),
            "median_active_fwd_bps": median(active_part),
            "win_rate_active": wins / active_n if active_n else None,
            "wins_active": wins,
            "losses_or_zero_active": active_n - wins,
            "mean_strategy_bps_per_eligible_day": mean(strat),
            "total_strategy_bps": sum(strat),
            "max_drawdown_strategy_bps": max_drawdown(strat),
            "sign_test_p_uncorrected": p_sign,
        })
    return detail, split_rows


def summarize_overall(detail: List[dict], hypothesis_id: str, horizon: int, effective_test_count: int, benchmark_detail: Optional[List[dict]], gates: dict) -> dict:
    active_rets = [x["fwd_ret_bps"] for x in detail if x["active"]]
    strat = [x["strategy_ret_bps"] for x in detail]
    wins = sum(1 for x in active_rets if x > 0)
    active_n = len(active_rets)
    total_n = len(detail)
    p_sign = binom_sf_at_least(wins, active_n, 0.5) if active_n else 1.0
    p_corr = min(1.0, p_sign * effective_test_count)
    row = {
        "hypothesis_id": hypothesis_id,
        "horizon_days": horizon,
        "eligible_days": total_n,
        "active_days": active_n,
        "exposure_share": active_n / total_n if total_n else 0.0,
        "mean_active_fwd_bps": mean(active_rets),
        "median_active_fwd_bps": median(active_rets),
        "win_rate_active": wins / active_n if active_n else None,
        "wins_active": wins,
        "losses_or_zero_active": active_n - wins,
        "mean_strategy_bps_per_eligible_day": mean(strat),
        "total_strategy_bps": sum(strat),
        "max_drawdown_strategy_bps": max_drawdown(strat),
        "sign_test_p_uncorrected": p_sign,
        "bonferroni_sign_test_p": p_corr,
        "effective_test_count": effective_test_count,
    }
    if benchmark_detail is not None:
        by_key = {(x["date_utc"], x["split_id"]): x for x in benchmark_detail}
        diffs = []
        for x in detail:
            b = by_key.get((x["date_utc"], x["split_id"]))
            if b is not None:
                diffs.append(x["strategy_ret_bps"] - b["strategy_ret_bps"])
        row["mean_excess_vs_b1_bps_per_eligible_day"] = mean(diffs) if diffs else None
        row["total_excess_vs_b1_bps"] = sum(diffs) if diffs else 0.0
        row["excess_positive_day_share_vs_b1"] = sum(1 for d in diffs if d > 0) / len(diffs) if diffs else None
    else:
        row["mean_excess_vs_b1_bps_per_eligible_day"] = None
        row["total_excess_vs_b1_bps"] = None
        row["excess_positive_day_share_vs_b1"] = None

    if hypothesis_id.startswith("H64G_H"):
        corrected_pass = (
            active_n >= gates["min_active_days_overall"]
            and (row["mean_active_fwd_bps"] is not None and row["mean_active_fwd_bps"] >= gates["min_mean_active_bps"])
            and (row["win_rate_active"] is not None and row["win_rate_active"] >= gates["min_win_rate_active"])
            and (row["mean_excess_vs_b1_bps_per_eligible_day"] is not None and row["mean_excess_vs_b1_bps_per_eligible_day"] >= gates["min_excess_vs_b1_bps_per_eligible_day"])
            and p_corr <= gates["bonferroni_alpha"]
        )
        uncorrected_watch = (
            active_n >= gates["min_active_days_overall"]
            and (row["mean_active_fwd_bps"] is not None and row["mean_active_fwd_bps"] >= gates["min_mean_active_bps"])
            and (row["win_rate_active"] is not None and row["win_rate_active"] >= gates["min_win_rate_active"])
            and (row["mean_excess_vs_b1_bps_per_eligible_day"] is not None and row["mean_excess_vs_b1_bps_per_eligible_day"] >= gates["min_excess_vs_b1_bps_per_eligible_day"])
            and p_sign <= gates["uncorrected_watch_alpha"]
        )
        row["candidate_corrected_pass"] = corrected_pass
        row["candidate_uncorrected_watch"] = (not corrected_pass) and uncorrected_watch
    else:
        row["candidate_corrected_pass"] = False
        row["candidate_uncorrected_watch"] = False
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    config_path = (root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    out_dir = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    config = read_json(config_path)
    dataset_path = root / config["feature_dataset"]
    stage64g_summary_path = root / config.get("stage64g_summary", "reports/stage64g_walk_forward_validation_design/stage64g_walk_forward_validation_design_summary.json")
    stage64g = read_json(stage64g_summary_path, default={})

    hypotheses = config["hypotheses"]
    horizons = config["horizons"]
    splits = config["splits"]
    required_features = config["required_features"]
    gates = config["gates"]

    rows, date_col, close_col, _ = load_dataset(
        dataset_path,
        required_features=required_features,
        close_column_candidates=config["gold_close_column_candidates"],
        date_column_candidates=config["date_column_candidates"],
    )

    stage64f_ok = bool(stage64g.get("dataset_design_checks", {}).get("dataset_ok_for_stage64h_design", True))
    if not stage64f_ok:
        raise RuntimeError("Stage64G did not mark dataset as ok for Stage64H design")

    effective_test_count = int(stage64g.get("hypothesis_design", {}).get("effective_test_count") or config.get("effective_test_count", 9))

    all_detail_by_key: Dict[Tuple[str, int], List[dict]] = {}
    split_result_rows: List[dict] = []
    overall_rows: List[dict] = []

    # Evaluate every hypothesis first so candidate excess can reference benchmark B1.
    for h in horizons:
        for hyp in hypotheses:
            detail, split_rows = evaluate_hypothesis(rows, hyp["hypothesis_id"], h, splits)
            all_detail_by_key[(hyp["hypothesis_id"], h)] = detail
            for sr in split_rows:
                sr["role"] = hyp["role"]
                split_result_rows.append(sr)

    b1_id = config.get("primary_benchmark_id", "H64G_B1_GOLD_TREND_ONLY_REFERENCE")
    for h in horizons:
        b1_detail = all_detail_by_key.get((b1_id, h))
        for hyp in hypotheses:
            hid = hyp["hypothesis_id"]
            detail = all_detail_by_key[(hid, h)]
            bench = None if hid == b1_id else b1_detail
            row = summarize_overall(detail, hid, h, effective_test_count, bench, gates)
            row["role"] = hyp["role"]
            row["side"] = hyp.get("side", "")
            overall_rows.append(row)

    # Split-level excess vs B1 and pass diagnostics for candidates.
    split_by_key = {(r["hypothesis_id"], int(r["horizon_days"]), r["split_id"]): r for r in split_result_rows}
    for r in split_result_rows:
        if not str(r["hypothesis_id"]).startswith("H64G_H"):
            r["mean_excess_vs_b1_bps_per_eligible_day"] = None
            r["split_positive_mean_pass"] = False
            r["split_excess_vs_b1_pass"] = False
            continue
        b = split_by_key.get((b1_id, int(r["horizon_days"]), r["split_id"]))
        if b is None:
            r["mean_excess_vs_b1_bps_per_eligible_day"] = None
        else:
            r["mean_excess_vs_b1_bps_per_eligible_day"] = (r.get("mean_strategy_bps_per_eligible_day") or 0.0) - (b.get("mean_strategy_bps_per_eligible_day") or 0.0)
        r["split_positive_mean_pass"] = (r.get("active_days") or 0) >= gates["min_active_days_per_split"] and (r.get("mean_active_fwd_bps") is not None and r.get("mean_active_fwd_bps") >= gates["min_mean_active_bps"])
        r["split_excess_vs_b1_pass"] = (r.get("active_days") or 0) >= gates["min_active_days_per_split"] and (r.get("mean_excess_vs_b1_bps_per_eligible_day") is not None and r.get("mean_excess_vs_b1_bps_per_eligible_day") >= gates["min_excess_vs_b1_bps_per_eligible_day"])

    # Aggregate candidate decisions with split robustness.
    candidate_decisions: List[dict] = []
    for row in overall_rows:
        hid = row["hypothesis_id"]
        if not hid.startswith("H64G_H"):
            continue
        h = int(row["horizon_days"])
        candidate_splits = [x for x in split_result_rows if x["hypothesis_id"] == hid and int(x["horizon_days"]) == h]
        positive_splits = sum(1 for x in candidate_splits if x.get("split_positive_mean_pass"))
        excess_splits = sum(1 for x in candidate_splits if x.get("split_excess_vs_b1_pass"))
        split_robust = positive_splits >= gates["min_positive_splits"] and excess_splits >= gates["min_excess_splits_vs_b1"]
        corrected_pass = bool(row["candidate_corrected_pass"] and split_robust)
        uncorrected_watch = bool(row["candidate_uncorrected_watch"] and split_robust)
        if corrected_pass:
            decision = "CORRECTED_FEASIBILITY_SURVIVOR_FOR_INDEPENDENT_CONFIRMATION_NO_ORDER"
        elif uncorrected_watch:
            decision = "UNCORRECTED_POSITIVE_WATCH_ONLY_NO_ORDER"
        else:
            decision = "FAIL_REDUCED_SCOPE_FEASIBILITY_NO_ORDER"
        candidate_decisions.append({
            "hypothesis_id": hid,
            "horizon_days": h,
            "decision": decision,
            "corrected_pass": corrected_pass,
            "uncorrected_watch": uncorrected_watch,
            "split_robust": split_robust,
            "positive_splits": positive_splits,
            "excess_splits_vs_b1": excess_splits,
            **row,
        })

    any_corrected = any(x["corrected_pass"] for x in candidate_decisions)
    any_watch = any(x["uncorrected_watch"] for x in candidate_decisions)
    if any_corrected:
        decision = "REDUCED_SCOPE_VALIDATION_HAS_CORRECTED_FEASIBILITY_SURVIVOR_NO_ORDER"
        next_allowed = "Stage64I_INDEPENDENT_CONFIRMATION_OR_BROKER_SPOT_PROXY_ALIGNMENT_NO_ORDER"
    elif any_watch:
        decision = "REDUCED_SCOPE_VALIDATION_UNCORRECTED_WATCH_ONLY_NO_ORDER"
        next_allowed = "Stage64I_INDEPENDENT_CONFIRMATION_OR_KILL_DECISION_NO_ORDER"
    else:
        decision = "REDUCED_SCOPE_VALIDATION_NO_CORRECTED_EDGE_KILL_OR_REDESIGN_NO_ORDER"
        next_allowed = "Stage64I_DECISION_MEMO_KILL_OR_DATA_COMPLETION_NO_ORDER"

    # sample details, capped to keep reports light.
    signal_sample = []
    for (hid, h), detail in all_detail_by_key.items():
        if not hid.startswith("H64G_H"):
            continue
        for x in detail:
            if x["active"]:
                signal_sample.append(x)
            if len(signal_sample) >= 500:
                break
        if len(signal_sample) >= 500:
            break

    result_fields = [
        "hypothesis_id", "role", "side", "horizon_days", "eligible_days", "active_days", "exposure_share",
        "mean_active_fwd_bps", "median_active_fwd_bps", "win_rate_active", "wins_active", "losses_or_zero_active",
        "mean_strategy_bps_per_eligible_day", "total_strategy_bps", "max_drawdown_strategy_bps",
        "mean_excess_vs_b1_bps_per_eligible_day", "total_excess_vs_b1_bps", "excess_positive_day_share_vs_b1",
        "sign_test_p_uncorrected", "bonferroni_sign_test_p", "effective_test_count", "candidate_corrected_pass", "candidate_uncorrected_watch",
    ]
    split_fields = [
        "split_id", "hypothesis_id", "role", "horizon_days", "eligible_days", "active_days", "exposure_share",
        "mean_active_fwd_bps", "median_active_fwd_bps", "win_rate_active", "wins_active", "losses_or_zero_active",
        "mean_strategy_bps_per_eligible_day", "mean_excess_vs_b1_bps_per_eligible_day", "total_strategy_bps", "max_drawdown_strategy_bps",
        "sign_test_p_uncorrected", "split_positive_mean_pass", "split_excess_vs_b1_pass",
    ]
    decision_fields = [
        "hypothesis_id", "horizon_days", "decision", "corrected_pass", "uncorrected_watch", "split_robust", "positive_splits", "excess_splits_vs_b1",
        "active_days", "mean_active_fwd_bps", "win_rate_active", "mean_excess_vs_b1_bps_per_eligible_day", "sign_test_p_uncorrected", "bonferroni_sign_test_p",
    ]
    sample_fields = ["date_utc", "split_id", "hypothesis_id", "horizon_days", "active", "fwd_ret_bps", "strategy_ret_bps"]

    outputs = {
        "overall_results_csv": str(out_dir / "stage64h_validation_results.csv"),
        "split_results_csv": str(out_dir / "stage64h_split_results.csv"),
        "candidate_decisions_csv": str(out_dir / "stage64h_candidate_decisions.csv"),
        "signal_sample_csv": str(out_dir / "stage64h_signal_sample.csv"),
        "summary_json": str(out_dir / "stage64h_reduced_scope_walk_forward_validation_summary.json"),
        "report_md": str(out_dir / "stage64h_reduced_scope_walk_forward_validation_report.md"),
    }

    write_csv(Path(outputs["overall_results_csv"]), overall_rows, result_fields)
    write_csv(Path(outputs["split_results_csv"]), split_result_rows, split_fields)
    write_csv(Path(outputs["candidate_decisions_csv"]), candidate_decisions, decision_fields)
    write_csv(Path(outputs["signal_sample_csv"]), signal_sample, sample_fields)

    best_candidates = sorted(
        candidate_decisions,
        key=lambda x: (
            bool(x["corrected_pass"]),
            bool(x["uncorrected_watch"]),
            x.get("mean_excess_vs_b1_bps_per_eligible_day") or -1e9,
            x.get("mean_active_fwd_bps") or -1e9,
        ),
        reverse=True,
    )[:5]

    summary = {
        "stage": STAGE,
        "status": STATUS,
        "decision": decision,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_order": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "validation_allowed_for_order_or_promotion": False,
        "generated_utc": utc_now(),
        "root": str(root),
        "inputs": {
            "config": str(config_path),
            "feature_dataset": str(dataset_path),
            "stage64g_summary": str(stage64g_summary_path),
        },
        "dataset": {
            "rows_used": len(rows),
            "date_column": date_col,
            "gold_close_column": close_col,
            "first_date_utc": rows[0]["__date"].isoformat() + "T00:00:00Z" if rows else None,
            "last_date_utc": rows[-1]["__date"].isoformat() + "T00:00:00Z" if rows else None,
        },
        "design": {
            "hypotheses": len(hypotheses),
            "candidate_hypotheses": sum(1 for h in hypotheses if h["hypothesis_id"].startswith("H64G_H")),
            "benchmark_hypotheses": sum(1 for h in hypotheses if h["hypothesis_id"].startswith("H64G_B")),
            "horizons": horizons,
            "effective_test_count": effective_test_count,
            "primary_benchmark_id": b1_id,
        },
        "counts": {
            "overall_rows": len(overall_rows),
            "split_result_rows": len(split_result_rows),
            "candidate_decision_rows": len(candidate_decisions),
            "corrected_survivors": sum(1 for x in candidate_decisions if x["corrected_pass"]),
            "uncorrected_watch_only": sum(1 for x in candidate_decisions if x["uncorrected_watch"]),
        },
        "best_candidates": best_candidates,
        "source_warnings": config.get("source_warnings", [
            "Gold D1 source is COMEX continuous futures reference if source contains GC_F; results are reduced-scope proxy feasibility only."
        ]),
        "hard_blocks": [
            "NO_PAPER_ORDER",
            "NO_EA_PROMOTION",
            "NO_PAPER_LIVE",
            "NO_LIVE",
            "NO_BROKER_CONNECTION",
            "NO_FULL_SCOPE_VALIDATION_CLAIM",
            "NO_ORDER_OR_PROMOTION_FROM_STAGE64H",
        ],
        "next_allowed_step": next_allowed,
        "outputs": outputs,
    }
    write_json(Path(outputs["summary_json"]), summary)

    # Markdown report
    report_path = Path(outputs["report_md"])
    with report_path.open("w", encoding="utf-8") as f:
        f.write("# Stage64H - Reduced-Scope Walk-Forward Validation Run (No Order)\n\n")
        f.write(f"Generated UTC: `{summary['generated_utc']}`\n\n")
        f.write("## Status\n\n")
        f.write(f"- status: `{STATUS}`\n")
        f.write(f"- decision: `{decision}`\n")
        f.write("- promotion/paper/live: `NO_GO`\n")
        f.write("- validation_allowed_for_order_or_promotion: `false`\n\n")
        f.write("## Executive conclusion\n\n")
        if any_corrected:
            f.write("At least one reduced-scope candidate/horizon survived the conservative corrected feasibility gates. This does not authorize orders or promotion; it only permits independent confirmation/proxy alignment work.\n\n")
        elif any_watch:
            f.write("Some candidate evidence may be positive before correction, but no corrected feasibility survivor is established. The result is watch-only and requires independent confirmation or kill decision.\n\n")
        else:
            f.write("No reduced-scope candidate/horizon passed corrected feasibility gates. The reduced-scope macro proxy path should not be promoted and should move to kill/redesign/data-completion decision.\n\n")
        f.write("## Dataset\n\n")
        f.write(f"- rows_used: `{len(rows)}`\n")
        f.write(f"- first_date: `{summary['dataset']['first_date_utc']}`\n")
        f.write(f"- last_date: `{summary['dataset']['last_date_utc']}`\n")
        f.write(f"- gold_close_column: `{close_col}`\n\n")
        f.write("## Design\n\n")
        f.write(f"- hypotheses: `{len(hypotheses)}`\n")
        f.write(f"- horizons: `{horizons}`\n")
        f.write(f"- effective_test_count: `{effective_test_count}`\n")
        f.write(f"- primary benchmark: `{b1_id}`\n\n")
        f.write("## Candidate decisions\n\n")
        f.write("| hypothesis_id | horizon | decision | active_days | mean_active_bps | win_rate | excess_vs_b1_bps/day | corrected_p |\n")
        f.write("|---|---:|---|---:|---:|---:|---:|---:|\n")
        for r in candidate_decisions:
            f.write(
                f"| `{r['hypothesis_id']}` | {r['horizon_days']} | `{r['decision']}` | {r.get('active_days')} | "
                f"{(r.get('mean_active_fwd_bps') if r.get('mean_active_fwd_bps') is not None else float('nan')):.4f} | "
                f"{(r.get('win_rate_active') if r.get('win_rate_active') is not None else float('nan')):.4f} | "
                f"{(r.get('mean_excess_vs_b1_bps_per_eligible_day') if r.get('mean_excess_vs_b1_bps_per_eligible_day') is not None else float('nan')):.4f} | "
                f"{(r.get('bonferroni_sign_test_p') if r.get('bonferroni_sign_test_p') is not None else float('nan')):.4f} |\n"
            )
        f.write("\n## Source warning\n\n")
        for w in summary["source_warnings"]:
            f.write(f"- {w}\n")
        f.write("\n## Operational decision\n\n")
        f.write("No paper-order, paper-live, live, EA promotion, broker connection, or full-scope validation claim is authorized by Stage64H.\n\n")
        f.write("## Next allowed step\n\n")
        f.write(f"`{next_allowed}`\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
