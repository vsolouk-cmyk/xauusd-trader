#!/usr/bin/env python3
"""Stage64N1 corrected-survivor robustness audit.

No order, no broker connection, no paper/live. This script audits only the
Stage64M corrected survivor that Stage64N authorized for stricter research-only
audit. It does not tune hypotheses, run a new scan, or authorize promotion.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

STAGE = "Stage64N1_CORRECTED_SURVIVOR_ROBUSTNESS_AUDIT_NO_ORDER"
STATUS = "CORRECTED_SURVIVOR_ROBUSTNESS_AUDIT_COMPLETE_NO_PROMOTION"

HARD_BLOCKS = [
    "NO_PAPER_ORDER",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_BROKER_CONNECTION",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE64N1",
    "NO_HISTORICAL_EVENT_FILTER_FROM_FORWARD_ONLY_GOVERNANCE",
    "NO_POST_HOC_EVENT_EXCLUSION",
    "NO_REDUCED_SCOPE_RETEST",
    "NO_RESCUE_FILTERING",
    "NO_NEW_INTRADAY_SCAN",
    "NO_PROMOTION_FROM_SINGLE_STAGE64M_PASS",
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
        for row in rows:
            for key in row.keys():
                if key not in keys:
                    keys.append(key)
        fieldnames = keys
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def parse_iso_date(value: Any) -> Optional[dt.datetime]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        out = dt.datetime.fromisoformat(text)
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
    text = str(value).strip().replace(",", "")
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    try:
        x = float(text)
    except Exception:
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def mean(values: Sequence[float]) -> Optional[float]:
    xs = [x for x in values if x is not None and not math.isnan(x)]
    if not xs:
        return None
    return sum(xs) / len(xs)


def median(values: Sequence[float]) -> Optional[float]:
    xs = sorted([x for x in values if x is not None and not math.isnan(x)])
    n = len(xs)
    if n == 0:
        return None
    mid = n // 2
    if n % 2:
        return xs[mid]
    return (xs[mid - 1] + xs[mid]) / 2.0


def variance(values: Sequence[float]) -> Optional[float]:
    xs = [x for x in values if x is not None and not math.isnan(x)]
    n = len(xs)
    if n < 2:
        return None
    m = sum(xs) / n
    return sum((x - m) ** 2 for x in xs) / (n - 1)


def percentile(values: Sequence[float], q: float) -> Optional[float]:
    xs = sorted([x for x in values if x is not None and not math.isnan(x)])
    if not xs:
        return None
    if q <= 0:
        return xs[0]
    if q >= 1:
        return xs[-1]
    idx = q * (len(xs) - 1)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return xs[lo]
    w = idx - lo
    return xs[lo] * (1 - w) + xs[hi] * w


def one_sided_p_mean_gt_sample_a_vs_b(a: Sequence[float], b: Sequence[float]) -> float:
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


def binomial_tail_ge(k: int, n: int, p: float = 0.5) -> float:
    if n <= 0:
        return 1.0
    # Stable enough for the n used here; the audit is diagnostic, not an execution engine.
    prob = 0.0
    for i in range(k, n + 1):
        prob += math.comb(n, i) * (p ** i) * ((1.0 - p) ** (n - i))
    return min(1.0, max(0.0, prob))


def max_share(counts: Dict[Any, int]) -> float:
    total = sum(counts.values())
    if total <= 0:
        return 0.0
    return max(counts.values()) / total


def safe_eval_rule(expr: str, row: Dict[str, Any]) -> bool:
    if expr == "always_true":
        return True
    env: Dict[str, Any] = {"__builtins__": {}}
    local: Dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(key, str) and key.isidentifier():
            x = to_float(value)
            local[key] = x if x is not None else float("nan")
    try:
        return bool(eval(expr, env, local))  # noqa: S307 - predeclared repo config expressions only
    except Exception:
        return False


def split_id_for_date(d: dt.datetime, splits: Sequence[Dict[str, Any]]) -> Optional[str]:
    s = d.date().isoformat()
    for sp in splits:
        if str(sp.get("start")) <= s <= str(sp.get("end")):
            return str(sp.get("split_id"))
    return None


def pick_price_column(fieldnames: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    lower_to_actual = {c.lower(): c for c in fieldnames}
    for cand in candidates:
        if cand.lower() in lower_to_actual:
            return lower_to_actual[cand.lower()]
    for col in fieldnames:
        lc = col.lower()
        if "close" in lc and ("gold" in lc or lc == "close") and "ret" not in lc and "future" not in lc:
            return col
    return None


def values_for_mask(rows: List[Dict[str, Any]], indices: Sequence[int], mask: Dict[int, bool], ret_key: str) -> List[float]:
    out: List[float] = []
    for idx in indices:
        if mask.get(idx):
            x = to_float(rows[idx].get(ret_key))
            if x is not None:
                out.append(x)
    return out


def summarize_values(values: Sequence[float]) -> Dict[str, Any]:
    xs = [x for x in values if x is not None and not math.isnan(x)]
    return {
        "active_days": len(xs),
        "mean_bps": round(mean(xs), 6) if xs else None,
        "median_bps": round(median(xs), 6) if xs else None,
        "win_rate": round(sum(1 for x in xs if x > 0) / len(xs), 6) if xs else None,
        "total_bps": round(sum(xs), 6) if xs else None,
    }


def bootstrap_mean_excess_probability_le_zero(
    candidate_values: Sequence[float],
    benchmark_values: Sequence[float],
    iterations: int,
    seed: int,
) -> Dict[str, Any]:
    cand = [x for x in candidate_values if x is not None and not math.isnan(x)]
    bench = [x for x in benchmark_values if x is not None and not math.isnan(x)]
    if len(cand) < 2 or len(bench) < 2 or iterations <= 0:
        return {"iterations": 0, "p_boot_excess_le_0": 1.0, "q05_excess_bps": None, "q50_excess_bps": None, "q95_excess_bps": None}
    rng = random.Random(seed)
    diffs: List[float] = []
    for _ in range(iterations):
        cm = sum(rng.choice(cand) for _ in range(len(cand))) / len(cand)
        bm = sum(rng.choice(bench) for _ in range(len(bench))) / len(bench)
        diffs.append(cm - bm)
    p_le_zero = sum(1 for d in diffs if d <= 0) / len(diffs)
    return {
        "iterations": iterations,
        "p_boot_excess_le_0": round(p_le_zero, 6),
        "q05_excess_bps": round(percentile(diffs, 0.05) or 0.0, 6),
        "q50_excess_bps": round(percentile(diffs, 0.50) or 0.0, 6),
        "q95_excess_bps": round(percentile(diffs, 0.95) or 0.0, 6),
    }


def build_rule_map(stage64l_summary: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for item in stage64l_summary.get("benchmarks", []) + stage64l_summary.get("candidates", []):
        hid = str(item.get("hypothesis_id"))
        out[hid] = str(item.get("rule_expression", "always_true"))
    return out


def audit_hypothesis(
    parsed: List[Dict[str, Any]],
    split_coverage: Sequence[Dict[str, Any]],
    candidate_expr: str,
    benchmark_expr: str,
    horizon: int,
    effective_test_count: int,
) -> Dict[str, Any]:
    ret_key = f"fwd_ret_bps_h{horizon}"
    valid_indices = [i for i, r in enumerate(parsed) if to_float(r.get(ret_key)) is not None]
    candidate_mask: Dict[int, bool] = {}
    benchmark_mask: Dict[int, bool] = {}
    for i, row in enumerate(parsed):
        candidate_mask[i] = safe_eval_rule(candidate_expr, row)
        benchmark_mask[i] = safe_eval_rule(benchmark_expr, row)
    cand_vals = values_for_mask(parsed, valid_indices, candidate_mask, ret_key)
    bench_vals = values_for_mask(parsed, valid_indices, benchmark_mask, ret_key)
    mean_c = mean(cand_vals)
    mean_b = mean(bench_vals)
    excess = None if mean_c is None or mean_b is None else mean_c - mean_b
    p_unc = one_sided_p_mean_gt_sample_a_vs_b(cand_vals, bench_vals)
    p_corr = min(1.0, p_unc * effective_test_count)

    split_excess = 0
    split_active_counts: Dict[str, int] = {}
    year_counts: Dict[int, int] = {}
    candidate_indices: List[int] = []
    benchmark_indices: List[int] = []
    for idx in valid_indices:
        if candidate_mask.get(idx):
            candidate_indices.append(idx)
        if benchmark_mask.get(idx):
            benchmark_indices.append(idx)
    for sp in split_coverage:
        sid = str(sp.get("split_id"))
        cv: List[float] = []
        bv: List[float] = []
        for idx in valid_indices:
            if split_id_for_date(parsed[idx]["_dt"], split_coverage) != sid:
                continue
            if candidate_mask.get(idx):
                x = to_float(parsed[idx].get(ret_key))
                if x is not None:
                    cv.append(x)
            if benchmark_mask.get(idx):
                y = to_float(parsed[idx].get(ret_key))
                if y is not None:
                    bv.append(y)
        cm = mean(cv)
        bm = mean(bv)
        if cm is not None and bm is not None and cm - bm > 0:
            split_excess += 1
        split_active_counts[sid] = len(cv)
    for idx in candidate_indices:
        y = parsed[idx]["_dt"].year
        year_counts[y] = year_counts.get(y, 0) + 1

    return {
        "horizon_days": horizon,
        "candidate_values": cand_vals,
        "benchmark_values": bench_vals,
        "candidate_indices": candidate_indices,
        "benchmark_indices": benchmark_indices,
        "candidate_active_days": len(cand_vals),
        "candidate_mean_bps": round(mean_c, 6) if mean_c is not None else None,
        "primary_benchmark_active_days": len(bench_vals),
        "primary_benchmark_mean_bps": round(mean_b, 6) if mean_b is not None else None,
        "mean_excess_vs_primary_benchmark_bps": round(excess, 6) if excess is not None else None,
        "one_sided_p_uncorrected_z_approx": round(p_unc, 8),
        "bonferroni_corrected_p": round(p_corr, 8),
        "positive_excess_splits_vs_primary_benchmark": split_excess,
        "max_split_share_of_active_days": round(max_share(split_active_counts), 6),
        "max_year_share_of_active_days": round(max_share(year_counts), 6),
    }


def close_enough(a: Any, b: Any, tolerance: float) -> bool:
    aa = to_float(a)
    bb = to_float(b)
    if aa is None or bb is None:
        return aa is None and bb is None
    return abs(aa - bb) <= tolerance


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
    n_summary_path = root / config.get("stage64n_summary", "reports/stage64n_full_scope_validation_decision_memo/stage64n_full_scope_validation_decision_memo_summary.json")
    m_summary_path = root / config.get("stage64m_summary", "reports/stage64m_full_scope_walk_forward_validation_run/stage64m_full_scope_walk_forward_validation_run_summary.json")
    l_summary_path = root / config.get("stage64l_summary", "reports/stage64l_full_scope_walk_forward_validation_design/stage64l_full_scope_walk_forward_validation_design_summary.json")
    dataset_path = root / config.get("stage64k_dataset", "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv")

    n_summary = read_json(n_summary_path)
    m_summary = read_json(m_summary_path)
    l_summary = read_json(l_summary_path)
    fieldnames, rows = read_csv_rows(dataset_path)

    target_hypothesis = str(config.get("target_hypothesis_id", "H64L_H1_FULL_MACRO_TAILWIND_LONG"))
    target_horizon = int(config.get("target_horizon_days", 120))
    primary_benchmark_id = str(config.get("primary_benchmark_id", l_summary.get("validation_design", {}).get("primary_benchmark_id", "H64L_B1_GOLD_TREND_ONLY_REFERENCE")))
    effective_test_count = int(config.get("effective_test_count", l_summary.get("validation_design", {}).get("effective_test_count", 12)))

    price_col = pick_price_column(fieldnames, config.get("price_column_candidates", ["gold_close", "gold_reference_close", "close"]))
    date_col = str(config.get("date_column", l_summary.get("dataset_checks", {}).get("date_column", "feature_date_utc")))
    if date_col not in fieldnames:
        raise SystemExit(f"missing date column: {date_col}")
    if price_col is None:
        raise SystemExit("missing usable gold close/price column")

    forbidden_hits = [c for c in fieldnames if any(frag in c.lower() for frag in FORBIDDEN_NAME_FRAGMENTS)]

    parsed: List[Dict[str, Any]] = []
    date_errors = 0
    price_errors = 0
    for row in rows:
        d = parse_iso_date(row.get(date_col))
        p = to_float(row.get(price_col))
        if d is None:
            date_errors += 1
            continue
        if p is None or p <= 0:
            price_errors += 1
            continue
        rr: Dict[str, Any] = dict(row)
        rr["_dt"] = d
        rr["_price"] = p
        parsed.append(rr)
    parsed.sort(key=lambda x: x["_dt"])

    ret_key = f"fwd_ret_bps_h{target_horizon}"
    for i, row in enumerate(parsed):
        j = i + target_horizon
        if j < len(parsed):
            row[ret_key] = (parsed[j]["_price"] / row["_price"] - 1.0) * 10000.0
        else:
            row[ret_key] = None

    rule_map = build_rule_map(l_summary)
    candidate_expr = rule_map.get(target_hypothesis)
    benchmark_expr = rule_map.get(primary_benchmark_id)
    if candidate_expr is None:
        raise SystemExit(f"missing candidate expression for {target_hypothesis}")
    if benchmark_expr is None:
        raise SystemExit(f"missing benchmark expression for {primary_benchmark_id}")
    splits = l_summary.get("split_coverage", [])

    recomputed = audit_hypothesis(parsed, splits, candidate_expr, benchmark_expr, target_horizon, effective_test_count)
    expected_survivor = None
    for survivor in m_summary.get("corrected_survivors", []):
        if str(survivor.get("hypothesis_id")) == target_hypothesis and int(survivor.get("horizon_days", -1)) == target_horizon:
            expected_survivor = survivor
            break
    if expected_survivor is None:
        raise SystemExit("target survivor not found in Stage64M corrected_survivors")

    tolerance_bps = float(config.get("accounting_tolerance_bps", 0.02))
    tolerance_p = float(config.get("accounting_tolerance_p", 0.0002))
    accounting_checks = [
        {"metric": "candidate_active_days", "expected": expected_survivor.get("candidate_active_days"), "recomputed": recomputed.get("candidate_active_days"), "pass": int(expected_survivor.get("candidate_active_days", -999)) == int(recomputed.get("candidate_active_days", -998))},
        {"metric": "primary_benchmark_active_days", "expected": expected_survivor.get("primary_benchmark_active_days"), "recomputed": recomputed.get("primary_benchmark_active_days"), "pass": int(expected_survivor.get("primary_benchmark_active_days", -999)) == int(recomputed.get("primary_benchmark_active_days", -998))},
        {"metric": "candidate_mean_bps", "expected": expected_survivor.get("candidate_mean_bps"), "recomputed": recomputed.get("candidate_mean_bps"), "pass": close_enough(expected_survivor.get("candidate_mean_bps"), recomputed.get("candidate_mean_bps"), tolerance_bps)},
        {"metric": "primary_benchmark_mean_bps", "expected": expected_survivor.get("primary_benchmark_mean_bps"), "recomputed": recomputed.get("primary_benchmark_mean_bps"), "pass": close_enough(expected_survivor.get("primary_benchmark_mean_bps"), recomputed.get("primary_benchmark_mean_bps"), tolerance_bps)},
        {"metric": "mean_excess_vs_primary_benchmark_bps", "expected": expected_survivor.get("mean_excess_vs_primary_benchmark_bps"), "recomputed": recomputed.get("mean_excess_vs_primary_benchmark_bps"), "pass": close_enough(expected_survivor.get("mean_excess_vs_primary_benchmark_bps"), recomputed.get("mean_excess_vs_primary_benchmark_bps"), tolerance_bps)},
        {"metric": "bonferroni_corrected_p", "expected": expected_survivor.get("bonferroni_corrected_p"), "recomputed": recomputed.get("bonferroni_corrected_p"), "pass": close_enough(expected_survivor.get("bonferroni_corrected_p"), recomputed.get("bonferroni_corrected_p"), tolerance_p)},
        {"metric": "positive_excess_splits_vs_primary_benchmark", "expected": expected_survivor.get("positive_excess_splits_vs_primary_benchmark"), "recomputed": recomputed.get("positive_excess_splits_vs_primary_benchmark"), "pass": int(expected_survivor.get("positive_excess_splits_vs_primary_benchmark", -999)) == int(recomputed.get("positive_excess_splits_vs_primary_benchmark", -998))},
        {"metric": "max_split_share_of_active_days", "expected": expected_survivor.get("max_split_share_of_active_days"), "recomputed": recomputed.get("max_split_share_of_active_days"), "pass": close_enough(expected_survivor.get("max_split_share_of_active_days"), recomputed.get("max_split_share_of_active_days"), 0.0005)},
        {"metric": "max_year_share_of_active_days", "expected": expected_survivor.get("max_year_share_of_active_days"), "recomputed": recomputed.get("max_year_share_of_active_days"), "pass": close_enough(expected_survivor.get("max_year_share_of_active_days"), recomputed.get("max_year_share_of_active_days"), 0.0005)},
    ]
    a1_pass = all(bool(x["pass"]) for x in accounting_checks) and len(forbidden_hits) == 0

    candidate_values: List[float] = list(recomputed["candidate_values"])
    benchmark_values: List[float] = list(recomputed["benchmark_values"])
    benchmark_mean = mean(benchmark_values) or 0.0
    positives_vs_benchmark_mean = sum(1 for x in candidate_values if x > benchmark_mean)
    sign_p = binomial_tail_ge(positives_vs_benchmark_mean, len(candidate_values), 0.5) if candidate_values else 1.0
    boot = bootstrap_mean_excess_probability_le_zero(
        candidate_values,
        benchmark_values,
        int(config.get("bootstrap_iterations", 2000)),
        int(config.get("bootstrap_seed", 64001)),
    )
    a2_pass = bool(
        len(candidate_values) >= int(config.get("bootstrap_min_active_days", 120))
        and (boot.get("q05_excess_bps") is not None and float(boot.get("q05_excess_bps") or 0.0) > 0)
        and float(boot.get("p_boot_excess_le_0") or 1.0) <= float(config.get("max_bootstrap_p_excess_le_0", 0.05))
        and sign_p <= float(config.get("max_sign_p_vs_benchmark_mean", 0.10))
    )

    # Lag/staleness sensitivity on candidate-active rows.
    candidate_indices: List[int] = list(recomputed["candidate_indices"])
    etf_lags = [to_float(parsed[i].get("etf_asof_lag_days")) for i in candidate_indices]
    cb_lags = [to_float(parsed[i].get("central_bank_asof_lag_days")) for i in candidate_indices]
    etf_lags_clean = [x for x in etf_lags if x is not None]
    cb_lags_clean = [x for x in cb_lags if x is not None]
    etf_strict_cap = float(config.get("strict_etf_lag_cap_days", 180))
    cb_strict_cap = float(config.get("strict_central_bank_lag_cap_days", 270))
    strict_indices = [
        i for i in candidate_indices
        if (to_float(parsed[i].get("etf_asof_lag_days")) is not None and to_float(parsed[i].get("etf_asof_lag_days")) <= etf_strict_cap)
        and (to_float(parsed[i].get("central_bank_asof_lag_days")) is not None and to_float(parsed[i].get("central_bank_asof_lag_days")) <= cb_strict_cap)
    ]
    strict_values = [to_float(parsed[i].get(ret_key)) for i in strict_indices]
    strict_values = [x for x in strict_values if x is not None]
    strict_mean = mean(strict_values)
    strict_excess = None if strict_mean is None else strict_mean - benchmark_mean
    stale_share = 1.0 - (len(strict_indices) / len(candidate_indices) if candidate_indices else 0.0)
    a3_pass = bool(
        len(strict_values) >= int(config.get("strict_lag_min_active_days", 120))
        and strict_excess is not None
        and strict_excess > 0
        and stale_share <= float(config.get("max_stale_share_after_strict_caps", 0.65))
    )

    # Feature ablation governance. These are not new candidates; they are diagnostics of the survivor's interpretation.
    ablation_rules = config.get("ablation_rules", {})
    default_ablation_rules = {
        "B1_trend_only": benchmark_expr,
        "B2_p0_macro_tailwind": rule_map.get("H64L_B2_P0_MACRO_TAILWIND_REFERENCE", "(gold_sma20_over_50 > 0) and (gold_sma50_over_200 > 0) and (dxy_ret_20d < 0) and (real_yield_change_20d < 0)"),
        "H1_without_etf_filter": "(gold_sma20_over_50 > 0) and (gold_sma50_over_200 > 0) and (dxy_ret_20d < 0) and (real_yield_change_20d < 0) and (central_bank_demand_tonnes_6m > 0)",
        "H1_without_central_bank_filter": "(gold_sma20_over_50 > 0) and (gold_sma50_over_200 > 0) and (dxy_ret_20d < 0) and (real_yield_change_20d < 0) and (etf_flow_tonnes_3m > 0)",
    }
    default_ablation_rules.update({str(k): str(v) for k, v in ablation_rules.items()})
    ablation_rows: List[Dict[str, Any]] = []
    for name, expr in default_ablation_rules.items():
        res = audit_hypothesis(parsed, splits, str(expr), benchmark_expr, target_horizon, effective_test_count)
        ablation_rows.append({
            "ablation_id": name,
            "active_days": res.get("candidate_active_days"),
            "mean_bps": res.get("candidate_mean_bps"),
            "excess_vs_B1_bps": res.get("mean_excess_vs_primary_benchmark_bps"),
            "p_corr_as_diagnostic_not_gate": res.get("bonferroni_corrected_p"),
        })
    full_excess = to_float(recomputed.get("mean_excess_vs_primary_benchmark_bps")) or 0.0
    p0_excess = next((to_float(r.get("excess_vs_B1_bps")) for r in ablation_rows if r.get("ablation_id") == "B2_p0_macro_tailwind"), None)
    without_etf_excess = next((to_float(r.get("excess_vs_B1_bps")) for r in ablation_rows if r.get("ablation_id") == "H1_without_etf_filter"), None)
    without_cb_excess = next((to_float(r.get("excess_vs_B1_bps")) for r in ablation_rows if r.get("ablation_id") == "H1_without_central_bank_filter"), None)
    full_active = int(recomputed.get("candidate_active_days") or 0)
    p0_active = next((int(r.get("active_days") or 0) for r in ablation_rows if r.get("ablation_id") == "B2_p0_macro_tailwind"), 0)
    a4_pass = bool(
        p0_excess is not None
        and full_excess > 0
        and full_active < p0_active
        and (
            (without_etf_excess is not None and full_excess >= without_etf_excess - float(config.get("ablation_tolerance_bps", 25.0)))
            or (without_cb_excess is not None and full_excess >= without_cb_excess - float(config.get("ablation_tolerance_bps", 25.0)))
        )
    )

    a5_pass = True

    audit_rows = [
        {"audit_id": "A1_REPRODUCE_STAGE64M_ACCOUNTING", "pass": a1_pass, "headline": "Stage64M accounting reproduced" if a1_pass else "Stage64M accounting reproduction failed"},
        {"audit_id": "A2_NONPARAMETRIC_SIGN_AND_BOOTSTRAP_CHECK", "pass": a2_pass, "headline": "Bootstrap/sign diagnostics non-fragile" if a2_pass else "Bootstrap/sign diagnostics fragile or insufficient"},
        {"audit_id": "A3_SOURCE_LAG_STALENESS_SENSITIVITY", "pass": a3_pass, "headline": "Strict source-lag subset remains positive" if a3_pass else "Strict source-lag subset fragile or too sparse"},
        {"audit_id": "A4_FEATURE_ABLATION_GOVERNANCE", "pass": a4_pass, "headline": "Ablation supports full-scope interpretation" if a4_pass else "Ablation weakens full-scope interpretation"},
        {"audit_id": "A5_BROKER_SPOT_ALIGNMENT_BLOCKER_LEDGER", "pass": a5_pass, "headline": "Broker/spot commercialization blocker retained"},
    ]

    if all(bool(r["pass"]) for r in audit_rows):
        decision = "CORRECTED_SURVIVOR_ROBUSTNESS_AUDIT_PASS_STAGE64N2_REPLICATION_AND_ALIGNMENT_DECISION_NO_ORDER"
        next_step = "Stage64N2_REPLICATION_AND_BROKER_SPOT_ALIGNMENT_DECISION_NO_ORDER"
        executive = "The Stage64M corrected survivor passed the Stage64N1 robustness audit. This remains research-only and authorizes only the next decision/audit stage, not orders."
    elif a1_pass:
        decision = "CORRECTED_SURVIVOR_ROBUSTNESS_AUDIT_FRAGILE_STAGE64N2_DOWNGRADE_OR_REDESIGN_DECISION_NO_ORDER"
        next_step = "Stage64N2_ROBUSTNESS_DOWNGRADE_OR_REDESIGN_DECISION_NO_ORDER"
        executive = "The Stage64M corrected survivor reproduced but failed at least one stricter robustness audit. The next stage must decide downgrade/redesign/kill; no tuning or order is authorized."
    else:
        decision = "CORRECTED_SURVIVOR_ACCOUNTING_REPRODUCTION_FAIL_INVALIDATE_SURVIVOR_NO_ORDER"
        next_step = "Stage64N2_INVALIDATE_OR_REPRODUCTION_FIX_DECISION_NO_ORDER"
        executive = "The Stage64M corrected survivor did not reproduce within tolerance. It must be invalidated or the accounting bug must be fixed before any further research claim."

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
            "stage64n_summary": str(n_summary_path),
            "stage64m_summary": str(m_summary_path),
            "stage64l_summary": str(l_summary_path),
            "stage64k_dataset": str(dataset_path),
        },
        "target_survivor": {
            "hypothesis_id": target_hypothesis,
            "horizon_days": target_horizon,
            "primary_benchmark_id": primary_benchmark_id,
        },
        "dataset_checks": {
            "rows_loaded": len(rows),
            "rows_usable_after_date_price_parse": len(parsed),
            "date_parse_errors": date_errors,
            "price_parse_errors": price_errors,
            "date_column": date_col,
            "price_column": price_col,
            "forbidden_columns": forbidden_hits,
        },
        "a1_recomputed_accounting": {k: v for k, v in recomputed.items() if k not in {"candidate_values", "benchmark_values", "candidate_indices", "benchmark_indices"}},
        "a1_accounting_checks": accounting_checks,
        "a2_nonparametric": {
            "candidate_active_days": len(candidate_values),
            "benchmark_active_days": len(benchmark_values),
            "benchmark_mean_bps": round(benchmark_mean, 6),
            "candidate_values_gt_benchmark_mean": positives_vs_benchmark_mean,
            "sign_test_one_sided_p_gt_benchmark_mean": round(sign_p, 8),
            **boot,
        },
        "a3_lag_staleness": {
            "strict_etf_lag_cap_days": etf_strict_cap,
            "strict_central_bank_lag_cap_days": cb_strict_cap,
            "candidate_active_days": len(candidate_indices),
            "strict_lag_active_days": len(strict_values),
            "strict_lag_share": round(len(strict_values) / len(candidate_indices), 6) if candidate_indices else 0,
            "stale_share_after_strict_caps": round(stale_share, 6),
            "strict_lag_mean_bps": round(strict_mean, 6) if strict_mean is not None else None,
            "strict_lag_excess_vs_B1_bps": round(strict_excess, 6) if strict_excess is not None else None,
            "etf_lag_median": round(median(etf_lags_clean), 6) if etf_lags_clean else None,
            "etf_lag_p90": round(percentile(etf_lags_clean, 0.90), 6) if etf_lags_clean else None,
            "central_bank_lag_median": round(median(cb_lags_clean), 6) if cb_lags_clean else None,
            "central_bank_lag_p90": round(percentile(cb_lags_clean, 0.90), 6) if cb_lags_clean else None,
        },
        "a4_ablation_rows": ablation_rows,
        "audit_results": audit_rows,
        "event_calendar_policy": n_summary.get("event_calendar_policy", m_summary.get("event_calendar_policy")),
        "broker_alignment_policy": n_summary.get("broker_alignment_policy", m_summary.get("broker_alignment_policy")),
        "executive_conclusion": executive,
        "next_allowed_step": next_step,
        "hard_blocks": HARD_BLOCKS,
        "outputs": {
            "summary_json": str(out_dir / "stage64n1_corrected_survivor_robustness_audit_summary.json"),
            "report_md": str(out_dir / "stage64n1_corrected_survivor_robustness_audit_report.md"),
            "audit_results_csv": str(out_dir / "stage64n1_audit_results.csv"),
            "accounting_checks_csv": str(out_dir / "stage64n1_accounting_checks.csv"),
            "feature_ablation_csv": str(out_dir / "stage64n1_feature_ablation.csv"),
        },
    }

    write_json(out_dir / "stage64n1_corrected_survivor_robustness_audit_summary.json", summary)
    write_csv(out_dir / "stage64n1_audit_results.csv", audit_rows)
    write_csv(out_dir / "stage64n1_accounting_checks.csv", accounting_checks)
    write_csv(out_dir / "stage64n1_feature_ablation.csv", ablation_rows)

    report_lines = [
        "# Stage64N1 - Corrected Survivor Robustness Audit (No Order)",
        "",
        f"Generated UTC: `{summary['generated_utc']}`",
        "",
        "## Status",
        "",
        f"- status: `{STATUS}`",
        f"- decision: `{decision}`",
        "- promotion/paper/live: `NO_GO`",
        "- validation_allowed_for_order_or_promotion: `false`",
        "",
        "## Executive conclusion",
        "",
        executive,
        "",
        "## Target survivor",
        "",
        f"- hypothesis_id: `{target_hypothesis}`",
        f"- horizon_days: `{target_horizon}`",
        f"- primary_benchmark_id: `{primary_benchmark_id}`",
        "",
        "## Audit results",
        "",
        "| audit_id | pass | headline |",
        "|---|---:|---|",
    ]
    for row in audit_rows:
        report_lines.append(f"| `{row['audit_id']}` | {row['pass']} | {row['headline']} |")
    report_lines.extend([
        "",
        "## A1 accounting reproduction",
        "",
        "| metric | expected | recomputed | pass |",
        "|---|---:|---:|---:|",
    ])
    for row in accounting_checks:
        report_lines.append(f"| `{row['metric']}` | `{row['expected']}` | `{row['recomputed']}` | {row['pass']} |")
    report_lines.extend([
        "",
        "## A2 non-parametric diagnostics",
        "",
        f"- candidate_active_days: `{len(candidate_values)}`",
        f"- benchmark_active_days: `{len(benchmark_values)}`",
        f"- sign_test_one_sided_p_gt_benchmark_mean: `{round(sign_p, 8)}`",
        f"- bootstrap_p_excess_le_0: `{boot.get('p_boot_excess_le_0')}`",
        f"- bootstrap_q05_excess_bps: `{boot.get('q05_excess_bps')}`",
        "",
        "## A3 source-lag staleness sensitivity",
        "",
        f"- strict_etf_lag_cap_days: `{etf_strict_cap}`",
        f"- strict_central_bank_lag_cap_days: `{cb_strict_cap}`",
        f"- strict_lag_active_days: `{len(strict_values)}`",
        f"- strict_lag_excess_vs_B1_bps: `{round(strict_excess, 6) if strict_excess is not None else None}`",
        f"- stale_share_after_strict_caps: `{round(stale_share, 6)}`",
        "",
        "## A4 feature ablation diagnostics",
        "",
        "| ablation_id | active_days | mean_bps | excess_vs_B1_bps |",
        "|---|---:|---:|---:|",
    ])
    for row in ablation_rows:
        report_lines.append(f"| `{row['ablation_id']}` | `{row['active_days']}` | `{row['mean_bps']}` | `{row['excess_vs_B1_bps']}` |")
    report_lines.extend([
        "",
        "## Governance",
        "",
        "No historical event-calendar filter or post-hoc exclusion is used. Broker/spot alignment remains required before any commercialization or broker XAUUSD validation claim.",
        "",
        "## Hard blocks",
        "",
    ])
    for block in HARD_BLOCKS:
        report_lines.append(f"- `{block}`")
    report_lines.extend([
        "",
        "## Next allowed step",
        "",
        f"`{next_step}`",
        "",
    ])
    (out_dir / "stage64n1_corrected_survivor_robustness_audit_report.md").write_text("\n".join(report_lines), encoding="utf-8")

    print(json.dumps({"status": STATUS, "decision": decision, "next_allowed_step": next_step}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
