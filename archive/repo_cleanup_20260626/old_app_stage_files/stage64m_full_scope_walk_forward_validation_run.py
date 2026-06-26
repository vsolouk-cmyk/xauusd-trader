#!/usr/bin/env python3
"""Stage64M full-scope walk-forward validation run.

No order, no broker connection, no paper/live. This script evaluates only the
predeclared Stage64L hypotheses on the Stage64K lag-safe feature dataset.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

STAGE = "Stage64M_FULL_SCOPE_WALK_FORWARD_VALIDATION_RUN_NO_ORDER"
STATUS = "FULL_SCOPE_WALK_FORWARD_VALIDATION_RUN_COMPLETE_NO_PROMOTION"
HARD_BLOCKS = [
    "NO_PAPER_ORDER",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_BROKER_CONNECTION",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE64M",
    "NO_HISTORICAL_EVENT_FILTER_FROM_FORWARD_ONLY_GOVERNANCE",
    "NO_POST_HOC_EVENT_EXCLUSION",
    "NO_REDUCED_SCOPE_RETEST",
    "NO_RESCUE_FILTERING",
    "NO_NEW_INTRADAY_SCAN",
]

FORBIDDEN_NAME_FRAGMENTS = [
    "target",
    "signal",
    "validation",
    "future_return",
    "fwd_return",
    "fwd_ret",
    "event_filter",
    "event_blackout_historical",
]


def utc_now_iso() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso_date(value: Any) -> Optional[dt.datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        out = dt.datetime.fromisoformat(s)
    except Exception:
        try:
            out = dt.datetime.strptime(str(value).strip()[:10], "%Y-%m-%d").replace(tzinfo=dt.UTC)
        except Exception:
            return None
    if out.tzinfo is None:
        out = out.replace(tzinfo=dt.UTC)
    return out.astimezone(dt.UTC)


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if not s or s.lower() in {"nan", "none", "null"}:
        return None
    try:
        x = float(s)
    except Exception:
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")


def read_csv_rows(path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = [dict(r) for r in reader]
    return fieldnames, rows


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
    if fieldnames is None:
        keys: List[str] = []
        for r in rows:
            for k in r.keys():
                if k not in keys:
                    keys.append(k)
        fieldnames = keys
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in fieldnames})


def mean(xs: Sequence[float]) -> Optional[float]:
    vals = [x for x in xs if x is not None and not math.isnan(x)]
    if not vals:
        return None
    return sum(vals) / len(vals)


def median(xs: Sequence[float]) -> Optional[float]:
    vals = sorted([x for x in xs if x is not None and not math.isnan(x)])
    n = len(vals)
    if n == 0:
        return None
    mid = n // 2
    if n % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2.0


def variance(xs: Sequence[float]) -> Optional[float]:
    vals = [x for x in xs if x is not None and not math.isnan(x)]
    n = len(vals)
    if n < 2:
        return None
    m = sum(vals) / n
    return sum((x - m) ** 2 for x in vals) / (n - 1)


def one_sided_p_mean_gt_sample_a_vs_b(a: Sequence[float], b: Sequence[float]) -> float:
    """Approximate one-sided p-value for mean(a) > mean(b), Welch z approximation.

    Uses only the standard library. This is a conservative operational diagnostic
    for this research stage; corrected p-value gate remains hard.
    """
    aa = [x for x in a if x is not None and not math.isnan(x)]
    bb = [x for x in b if x is not None and not math.isnan(x)]
    if len(aa) < 2 or len(bb) < 2:
        return 1.0
    ma = mean(aa) or 0.0
    mb = mean(bb) or 0.0
    va = variance(aa) or 0.0
    vb = variance(bb) or 0.0
    se2 = va / len(aa) + vb / len(bb)
    if se2 <= 0:
        return 0.0 if ma > mb else 1.0
    z = (ma - mb) / math.sqrt(se2)
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def safe_eval_rule(expr: str, row: Dict[str, Any]) -> bool:
    if expr == "always_true":
        return True
    env: Dict[str, Any] = {"__builtins__": {}}
    local: Dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(k, str) and k.isidentifier():
            x = to_float(v)
            local[k] = x if x is not None else float("nan")
    try:
        return bool(eval(expr, env, local))  # noqa: S307 - expressions are predeclared config artifacts in repo
    except Exception:
        return False


def pick_price_column(fieldnames: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    lower_to_actual = {c.lower(): c for c in fieldnames}
    for c in candidates:
        if c.lower() in lower_to_actual:
            return lower_to_actual[c.lower()]
    # conservative fallback: any obvious gold close column, not feature/return columns
    for c in fieldnames:
        lc = c.lower()
        if "close" in lc and ("gold" in lc or lc == "close") and "ret" not in lc and "future" not in lc:
            return c
    return None


def split_id_for_date(d: dt.datetime, splits: Sequence[Dict[str, Any]]) -> Optional[str]:
    date_str = d.date().isoformat()
    for s in splits:
        if str(s.get("start")) <= date_str <= str(s.get("end")):
            return str(s.get("split_id"))
    return None


def year_for_date(d: dt.datetime) -> int:
    return d.year


def values_for_hypothesis(valid_rows: List[Dict[str, Any]], active_map: Dict[int, bool], ret_key: str) -> List[float]:
    out: List[float] = []
    for i, r in enumerate(valid_rows):
        if active_map.get(i):
            x = to_float(r.get(ret_key))
            if x is not None:
                out.append(x)
    return out


def summarize_values(values: Sequence[float]) -> Dict[str, Any]:
    vals = [x for x in values if x is not None and not math.isnan(x)]
    return {
        "active_days": len(vals),
        "mean_bps": round(mean(vals), 6) if vals else None,
        "median_bps": round(median(vals), 6) if vals else None,
        "win_rate": round(sum(1 for x in vals if x > 0) / len(vals), 6) if vals else None,
        "total_bps": round(sum(vals), 6) if vals else None,
    }


def max_share(counts: Dict[Any, int]) -> float:
    total = sum(counts.values())
    if total <= 0:
        return 0.0
    return max(counts.values()) / total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    config_path = (root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    out_dir = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    ensure_dir(out_dir)

    config = read_json(config_path)
    stage64l_summary_path = root / config.get(
        "stage64l_summary",
        "reports/stage64l_full_scope_walk_forward_validation_design/stage64l_full_scope_walk_forward_validation_design_summary.json",
    )
    l_summary = read_json(stage64l_summary_path)

    dataset_path = root / config.get(
        "stage64k_dataset",
        "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv",
    )
    fieldnames, rows = read_csv_rows(dataset_path)

    price_candidates = config.get("price_column_candidates", [
        "gold_close",
        "gold_d1_close",
        "gold_close_d1",
        "close_gold",
        "xauusd_close",
        "close",
        "gold_reference_close",
    ])
    price_col = pick_price_column(fieldnames, price_candidates)

    date_col = str(l_summary.get("dataset_checks", {}).get("date_column") or config.get("date_column", "feature_date_utc"))
    if date_col not in fieldnames:
        raise SystemExit(f"missing date column: {date_col}")
    if price_col is None:
        raise SystemExit("missing price column; configure price_column_candidates in Stage64M config")

    forbidden_hits = [c for c in fieldnames if any(frag in c.lower() for frag in FORBIDDEN_NAME_FRAGMENTS)]

    parsed: List[Dict[str, Any]] = []
    parse_errors = 0
    price_errors = 0
    for r in rows:
        d = parse_iso_date(r.get(date_col))
        p = to_float(r.get(price_col))
        if d is None:
            parse_errors += 1
            continue
        if p is None or p <= 0:
            price_errors += 1
            continue
        rr: Dict[str, Any] = dict(r)
        rr["_dt"] = d
        rr["_price"] = p
        parsed.append(rr)
    parsed.sort(key=lambda x: x["_dt"])

    design = l_summary.get("validation_design", {})
    horizons = [int(x) for x in design.get("horizons_trading_days", config.get("horizons_trading_days", [20, 60, 120]))]
    effective_test_count = int(design.get("effective_test_count", 12))
    primary_benchmark_id = str(design.get("primary_benchmark_id", "H64L_B1_GOLD_TREND_ONLY_REFERENCE"))
    split_coverage = l_summary.get("split_coverage", [])
    pass_gates = design.get("pass_gates", [])

    hypotheses = []
    for b in l_summary.get("benchmarks", []):
        hypotheses.append(dict(b))
    for c in l_summary.get("candidates", []):
        hypotheses.append(dict(c))
    candidate_ids = [str(c.get("hypothesis_id")) for c in l_summary.get("candidates", [])]

    # Compute forward returns per horizon.
    for h in horizons:
        ret_key = f"fwd_ret_bps_h{h}"
        for i, r in enumerate(parsed):
            j = i + h
            if j < len(parsed):
                fp = parsed[j]["_price"]
                r[ret_key] = (fp / r["_price"] - 1.0) * 10000.0
            else:
                r[ret_key] = None

    active_maps: Dict[str, Dict[int, bool]] = {}
    rule_eval_counts: Dict[str, int] = {}
    for hyp in hypotheses:
        hid = str(hyp.get("hypothesis_id"))
        expr = str(hyp.get("rule_expression", "always_true"))
        amap: Dict[int, bool] = {}
        ntrue = 0
        for i, r in enumerate(parsed):
            ok = safe_eval_rule(expr, r)
            amap[i] = ok
            ntrue += int(ok)
        active_maps[hid] = amap
        rule_eval_counts[hid] = ntrue

    overall_rows: List[Dict[str, Any]] = []
    split_rows: List[Dict[str, Any]] = []
    candidate_rows: List[Dict[str, Any]] = []

    corrected_survivors: List[Dict[str, Any]] = []
    uncorrected_watch_only: List[Dict[str, Any]] = []

    primary_map = active_maps.get(primary_benchmark_id, {})

    min_active_by_horizon = config.get("minimum_active_days_by_horizon", {"20": 250, "60": 180, "120": 120})
    max_split_share_limit = float(config.get("max_split_share_of_active_days_lte", 0.45))
    max_year_share_limit = float(config.get("max_year_share_of_active_days_lte", 0.40))
    min_positive_splits = int(config.get("min_positive_excess_splits", 3))

    for h in horizons:
        ret_key = f"fwd_ret_bps_h{h}"
        horizon_valid = [r for r in parsed if to_float(r.get(ret_key)) is not None]
        # Create index mapping original parsed index -> horizon-valid local row.
        valid_original_indices = [i for i, r in enumerate(parsed) if to_float(r.get(ret_key)) is not None]
        benchmark_vals = [to_float(parsed[i].get(ret_key)) for i in valid_original_indices if primary_map.get(i)]
        benchmark_vals = [x for x in benchmark_vals if x is not None]
        benchmark_summary = summarize_values(benchmark_vals)

        for hyp in hypotheses:
            hid = str(hyp.get("hypothesis_id"))
            role = str(hyp.get("role", ""))
            amap = active_maps.get(hid, {})
            vals = [to_float(parsed[i].get(ret_key)) for i in valid_original_indices if amap.get(i)]
            vals = [x for x in vals if x is not None]
            summ = summarize_values(vals)
            overall_rows.append({
                "hypothesis_id": hid,
                "role": role,
                "horizon_days": h,
                **summ,
            })

            for sp in split_coverage:
                sid = str(sp.get("split_id"))
                svals: List[float] = []
                for i in valid_original_indices:
                    d = parsed[i]["_dt"]
                    if split_id_for_date(d, split_coverage) == sid and amap.get(i):
                        x = to_float(parsed[i].get(ret_key))
                        if x is not None:
                            svals.append(x)
                ss = summarize_values(svals)
                split_rows.append({
                    "hypothesis_id": hid,
                    "role": role,
                    "split_id": sid,
                    "horizon_days": h,
                    **ss,
                })

            if hid in candidate_ids:
                cand_vals = vals
                bvals = benchmark_vals
                mean_c = mean(cand_vals)
                mean_b = mean(bvals)
                excess = None if mean_c is None or mean_b is None else mean_c - mean_b
                p_unc = one_sided_p_mean_gt_sample_a_vs_b(cand_vals, bvals)
                p_corr = min(1.0, p_unc * effective_test_count)

                split_excess_count = 0
                split_active_counts: Dict[str, int] = {}
                year_counts: Dict[int, int] = {}
                for sp in split_coverage:
                    sid = str(sp.get("split_id"))
                    cv: List[float] = []
                    bv: List[float] = []
                    for i in valid_original_indices:
                        d = parsed[i]["_dt"]
                        if split_id_for_date(d, split_coverage) != sid:
                            continue
                        if amap.get(i):
                            x = to_float(parsed[i].get(ret_key))
                            if x is not None:
                                cv.append(x)
                        if primary_map.get(i):
                            y = to_float(parsed[i].get(ret_key))
                            if y is not None:
                                bv.append(y)
                    cm = mean(cv)
                    bm = mean(bv)
                    if cm is not None and bm is not None and (cm - bm) > 0:
                        split_excess_count += 1
                    split_active_counts[sid] = len(cv)

                for i in valid_original_indices:
                    if amap.get(i):
                        x = to_float(parsed[i].get(ret_key))
                        if x is not None:
                            year_counts[year_for_date(parsed[i]["_dt"])] = year_counts.get(year_for_date(parsed[i]["_dt"]), 0) + 1

                active_days = len(cand_vals)
                min_active = int(min_active_by_horizon.get(str(h), 0))
                max_split_share = max_share(split_active_counts)
                max_year_share = max_share(year_counts)
                gate_mean_excess = (excess is not None and excess > 0)
                gate_p = p_corr < 0.05
                gate_splits = split_excess_count >= min_positive_splits
                gate_active = active_days >= min_active
                gate_split_share = max_split_share <= max_split_share_limit
                gate_year_share = max_year_share <= max_year_share_limit
                gate_no_forbidden = len(forbidden_hits) == 0
                all_gates = all([gate_mean_excess, gate_p, gate_splits, gate_active, gate_split_share, gate_year_share, gate_no_forbidden])
                uncorrected_watch = bool(gate_mean_excess and p_unc < 0.05 and gate_splits and gate_active and gate_split_share and gate_year_share and gate_no_forbidden and not gate_p)

                decision = "PASS_CORRECTED_RESEARCH_ONLY_NO_ORDER" if all_gates else (
                    "WATCH_UNCORRECTED_RESEARCH_ONLY_NO_ORDER" if uncorrected_watch else "FAIL_FULL_SCOPE_VALIDATION_NO_ORDER"
                )
                row = {
                    "hypothesis_id": hid,
                    "horizon_days": h,
                    "candidate_active_days": active_days,
                    "candidate_mean_bps": round(mean_c, 6) if mean_c is not None else None,
                    "primary_benchmark_active_days": len(bvals),
                    "primary_benchmark_mean_bps": round(mean_b, 6) if mean_b is not None else None,
                    "mean_excess_vs_primary_benchmark_bps": round(excess, 6) if excess is not None else None,
                    "one_sided_p_uncorrected_z_approx": round(p_unc, 8),
                    "bonferroni_corrected_p": round(p_corr, 8),
                    "positive_excess_splits_vs_primary_benchmark": split_excess_count,
                    "max_split_share_of_active_days": round(max_split_share, 6),
                    "max_year_share_of_active_days": round(max_year_share, 6),
                    "gate_mean_excess_gt_0": gate_mean_excess,
                    "gate_corrected_p_lt_0_05": gate_p,
                    "gate_positive_excess_splits": gate_splits,
                    "gate_minimum_active_days": gate_active,
                    "gate_max_split_share": gate_split_share,
                    "gate_max_year_share": gate_year_share,
                    "gate_no_forbidden_columns": gate_no_forbidden,
                    "decision": decision,
                }
                candidate_rows.append(row)
                if all_gates:
                    corrected_survivors.append(row)
                elif uncorrected_watch:
                    uncorrected_watch_only.append(row)

    if corrected_survivors:
        decision = "FULL_SCOPE_VALIDATION_CORRECTED_SURVIVOR_STAGE64N_DECISION_MEMO_NO_ORDER"
        executive = "At least one full-scope candidate/horizon passed the predeclared corrected statistical gates. This is research-only and does not authorize orders; Stage64N must decide whether to continue toward stricter audits."
    elif uncorrected_watch_only:
        decision = "FULL_SCOPE_VALIDATION_UNCORRECTED_WATCH_ONLY_STAGE64N_DECISION_MEMO_NO_ORDER"
        executive = "No candidate passed corrected gates, but at least one row is uncorrected-watch only. This does not authorize promotion; Stage64N must decide whether the program is killed, redesigned, or passively watched."
    else:
        decision = "FULL_SCOPE_VALIDATION_NO_CORRECTED_EDGE_STAGE64N_KILL_OR_REDESIGN_NO_ORDER"
        executive = "No full-scope candidate passed corrected gates. The full-scope macro-regime path has no validated edge in this run and must go to Stage64N kill/redesign decision, not order/paper/live."

    summary: Dict[str, Any] = {
        "stage": STAGE,
        "status": STATUS,
        "decision": decision,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_order": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "validation_allowed_for_order_or_promotion": False,
        "generated_utc": utc_now_iso(),
        "root": str(root),
        "inputs": {
            "config": str(config_path),
            "stage64l_summary": str(stage64l_summary_path),
            "dataset": str(dataset_path),
        },
        "dataset_checks": {
            "rows_loaded": len(rows),
            "rows_usable_after_date_price_parse": len(parsed),
            "date_parse_errors": parse_errors,
            "price_parse_errors": price_errors,
            "date_column": date_col,
            "price_column": price_col,
            "forbidden_columns": forbidden_hits,
            "first_feature_date_utc": parsed[0]["_dt"].isoformat().replace("+00:00", "Z") if parsed else None,
            "last_feature_date_utc": parsed[-1]["_dt"].isoformat().replace("+00:00", "Z") if parsed else None,
        },
        "validation_design_reference": {
            "horizons_trading_days": horizons,
            "candidate_count": len(candidate_ids),
            "benchmark_count": len(l_summary.get("benchmarks", [])),
            "primary_benchmark_id": primary_benchmark_id,
            "effective_test_count": effective_test_count,
            "multiple_testing_rule": design.get("multiple_testing_rule"),
            "pass_gates": pass_gates,
        },
        "counts": {
            "overall_result_rows": len(overall_rows),
            "split_result_rows": len(split_rows),
            "candidate_decision_rows": len(candidate_rows),
            "corrected_survivors": len(corrected_survivors),
            "uncorrected_watch_only": len(uncorrected_watch_only),
        },
        "corrected_survivors": corrected_survivors,
        "uncorrected_watch_only": uncorrected_watch_only,
        "event_calendar_policy": design.get("event_calendar_policy"),
        "broker_alignment_policy": design.get("broker_alignment_policy"),
        "executive_conclusion": executive,
        "next_allowed_step": "Stage64N_FULL_SCOPE_VALIDATION_DECISION_MEMO_NO_ORDER",
        "hard_blocks": HARD_BLOCKS,
        "outputs": {
            "summary_json": str(out_dir / "stage64m_full_scope_walk_forward_validation_run_summary.json"),
            "report_md": str(out_dir / "stage64m_full_scope_walk_forward_validation_run_report.md"),
            "overall_results_csv": str(out_dir / "stage64m_overall_results.csv"),
            "split_results_csv": str(out_dir / "stage64m_split_results.csv"),
            "candidate_decisions_csv": str(out_dir / "stage64m_candidate_decisions.csv"),
        },
    }

    write_csv(out_dir / "stage64m_overall_results.csv", overall_rows)
    write_csv(out_dir / "stage64m_split_results.csv", split_rows)
    write_csv(out_dir / "stage64m_candidate_decisions.csv", candidate_rows)
    write_json(out_dir / "stage64m_full_scope_walk_forward_validation_run_summary.json", summary)

    # Markdown report
    lines: List[str] = []
    lines.append("# Stage64M - Full-Scope Walk-Forward Validation Run (No Order)\n")
    lines.append(f"Generated UTC: `{summary['generated_utc']}`\n")
    lines.append("## Status\n")
    lines.append(f"- status: `{STATUS}`")
    lines.append(f"- decision: `{decision}`")
    lines.append("- promotion/paper/live: `NO_GO`")
    lines.append("- validation_allowed_for_order_or_promotion: `false`\n")
    lines.append("## Executive conclusion\n")
    lines.append(executive + "\n")
    lines.append("## Dataset checks\n")
    dc = summary["dataset_checks"]
    for k in ["rows_loaded", "rows_usable_after_date_price_parse", "date_parse_errors", "price_parse_errors", "date_column", "price_column", "first_feature_date_utc", "last_feature_date_utc"]:
        lines.append(f"- {k}: `{dc.get(k)}`")
    lines.append(f"- forbidden_columns: `{dc.get('forbidden_columns')}`\n")
    lines.append("## Candidate decisions\n")
    lines.append("| hypothesis_id | horizon | active_days | mean_bps | benchmark_mean_bps | excess_bps | p_unc | p_corr | pos_splits | max_split_share | max_year_share | decision |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for r in candidate_rows:
        lines.append(
            f"| `{r['hypothesis_id']}` | {r['horizon_days']} | {r['candidate_active_days']} | {r['candidate_mean_bps']} | {r['primary_benchmark_mean_bps']} | {r['mean_excess_vs_primary_benchmark_bps']} | {r['one_sided_p_uncorrected_z_approx']} | {r['bonferroni_corrected_p']} | {r['positive_excess_splits_vs_primary_benchmark']} | {r['max_split_share_of_active_days']} | {r['max_year_share_of_active_days']} | `{r['decision']}` |"
        )
    lines.append("\n## Counts\n")
    for k, v in summary["counts"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("\n## Event-calendar governance\n")
    lines.append(str(summary.get("event_calendar_policy") or "Historical event-calendar features are not used."))
    lines.append("\n## Broker/spot alignment\n")
    lines.append(str(summary.get("broker_alignment_policy") or "Broker/spot alignment remains required before commercialization."))
    lines.append("\n## Hard blocks\n")
    for b in HARD_BLOCKS:
        lines.append(f"- `{b}`")
    lines.append("\n## Next allowed step\n")
    lines.append("`Stage64N_FULL_SCOPE_VALIDATION_DECISION_MEMO_NO_ORDER`\n")
    (out_dir / "stage64m_full_scope_walk_forward_validation_run_report.md").write_text("\n".join(lines), encoding="utf-8")

    print(decision)
    print(f"summary={out_dir / 'stage64m_full_scope_walk_forward_validation_run_summary.json'}")
    print(f"report={out_dir / 'stage64m_full_scope_walk_forward_validation_run_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
