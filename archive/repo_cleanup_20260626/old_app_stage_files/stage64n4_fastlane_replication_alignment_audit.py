#!/usr/bin/env python3
"""Stage64N4 fastlane replication/alignment audit (no order).

This script intentionally performs no tuning, no scan, no broker connection, and no order action.
It independently recomputes the predeclared Stage64M corrected survivor from the Stage64K dataset,
then emits an immutable reproduction manifest and a broker/spot alignment contract ledger.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


def now_utc() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path, default: Any = None) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    s = str(x).strip()
    if s == "" or s.lower() in {"nan", "none", "null"}:
        return None
    try:
        v = float(s)
        if math.isfinite(v):
            return v
    except Exception:
        return None
    return None


def parse_date(s: str) -> Optional[dt.date]:
    if not s:
        return None
    t = str(s).strip()
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        return dt.datetime.fromisoformat(t).date()
    except Exception:
        pass
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def compare_op(v: Optional[float], op: str, threshold: float) -> bool:
    if v is None:
        return False
    if op == ">":
        return v > threshold
    if op == ">=":
        return v >= threshold
    if op == "<":
        return v < threshold
    if op == "<=":
        return v <= threshold
    if op == "==":
        return v == threshold
    if op == "!=":
        return v != threshold
    raise ValueError(f"unsupported operator: {op}")


def rule_pass(row: Dict[str, Any], rule: Dict[str, Dict[str, Any]]) -> bool:
    for col, spec in rule.items():
        if not compare_op(parse_float(row.get(col)), spec["op"], float(spec["value"])):
            return False
    return True


def mean(xs: List[float]) -> Optional[float]:
    return sum(xs) / len(xs) if xs else None


def sample_std(xs: List[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def norm_sf(z: float) -> float:
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def one_sided_z_p(candidate: List[float], benchmark: List[float]) -> float:
    if len(candidate) < 2 or len(benchmark) < 2:
        return 1.0
    cm = mean(candidate) or 0.0
    bm = mean(benchmark) or 0.0
    cs = sample_std(candidate) or 0.0
    bs = sample_std(benchmark) or 0.0
    se = math.sqrt((cs * cs / len(candidate)) + (bs * bs / len(benchmark)))
    if se <= 0:
        return 1.0 if cm <= bm else 0.0
    return max(0.0, min(1.0, norm_sf((cm - bm) / se)))


def load_dataset(path: Path, date_col: str, price_col: str) -> Tuple[List[Dict[str, Any]], List[str], Dict[str, int]]:
    diagnostics = {"rows_loaded": 0, "rows_usable": 0, "date_parse_errors": 0, "price_parse_errors": 0}
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        for raw in reader:
            diagnostics["rows_loaded"] += 1
            d = parse_date(str(raw.get(date_col, "")))
            price = parse_float(raw.get(price_col))
            if d is None:
                diagnostics["date_parse_errors"] += 1
                continue
            if price is None or price <= 0:
                diagnostics["price_parse_errors"] += 1
                continue
            rr = dict(raw)
            rr["__date"] = d
            rr["__price"] = price
            rows.append(rr)
    rows.sort(key=lambda r: r["__date"])
    diagnostics["rows_usable"] = len(rows)
    return rows, fieldnames, diagnostics


def split_id_for_date(d: dt.date, splits: List[Dict[str, str]]) -> str:
    for s in splits:
        start = dt.date.fromisoformat(s["start"])
        end = dt.date.fromisoformat(s["end"])
        if start <= d <= end:
            return s["split_id"]
    return "OUT_OF_SPLIT"


def concentration(rows: List[Tuple[dt.date, float]], splits: List[Dict[str, str]]) -> Tuple[float, float, Dict[str, int], Dict[str, int]]:
    if not rows:
        return 1.0, 1.0, {}, {}
    split_counts: Dict[str, int] = {}
    year_counts: Dict[str, int] = {}
    for d, _v in rows:
        sid = split_id_for_date(d, splits)
        split_counts[sid] = split_counts.get(sid, 0) + 1
        y = str(d.year)
        year_counts[y] = year_counts.get(y, 0) + 1
    total = len(rows)
    return max(split_counts.values()) / total, max(year_counts.values()) / total, split_counts, year_counts


def evaluate(rows: List[Dict[str, Any]], cfg: Dict[str, Any]) -> Dict[str, Any]:
    h = int(cfg["target_survivor"]["horizon_days"])
    candidate_rule = cfg["candidate_rule"]
    benchmark_rule = cfg["benchmark_rule"]
    splits = cfg["splits"]

    candidate_returns: List[Tuple[dt.date, float]] = []
    benchmark_returns: List[Tuple[dt.date, float]] = []

    for i in range(0, len(rows) - h):
        r = rows[i]
        future = rows[i + h]
        ret_bps = (float(future["__price"]) / float(r["__price"]) - 1.0) * 10000.0
        d = r["__date"]
        if rule_pass(r, candidate_rule):
            candidate_returns.append((d, ret_bps))
        if rule_pass(r, benchmark_rule):
            benchmark_returns.append((d, ret_bps))

    c_vals = [v for _d, v in candidate_returns]
    b_vals = [v for _d, v in benchmark_returns]
    c_mean = mean(c_vals) or 0.0
    b_mean = mean(b_vals) or 0.0
    excess = c_mean - b_mean
    p_unc = one_sided_z_p(c_vals, b_vals)
    p_corr = min(1.0, p_unc * 12.0)
    max_split_share, max_year_share, split_counts, year_counts = concentration(candidate_returns, splits)

    pos_splits = 0
    split_excess: List[Dict[str, Any]] = []
    for s in splits:
        sid = s["split_id"]
        c_split = [v for d, v in candidate_returns if split_id_for_date(d, splits) == sid]
        b_split = [v for d, v in benchmark_returns if split_id_for_date(d, splits) == sid]
        cm = mean(c_split)
        bm = mean(b_split)
        ex = None if cm is None or bm is None else cm - bm
        if ex is not None and ex > 0:
            pos_splits += 1
        split_excess.append({
            "split_id": sid,
            "candidate_active_days": len(c_split),
            "benchmark_active_days": len(b_split),
            "candidate_mean_bps": cm,
            "benchmark_mean_bps": bm,
            "excess_vs_B1_bps": ex,
            "positive_excess": bool(ex is not None and ex > 0),
        })

    return {
        "horizon_days": h,
        "candidate_active_days": len(c_vals),
        "candidate_mean_bps": round(c_mean, 6),
        "primary_benchmark_active_days": len(b_vals),
        "primary_benchmark_mean_bps": round(b_mean, 6),
        "mean_excess_vs_primary_benchmark_bps": round(excess, 6),
        "one_sided_p_uncorrected_z_approx_independent": round(p_unc, 12),
        "bonferroni_corrected_p_independent": round(p_corr, 12),
        "positive_excess_splits_vs_primary_benchmark": pos_splits,
        "max_split_share_of_active_days": round(max_split_share, 6),
        "max_year_share_of_active_days": round(max_year_share, 6),
        "split_counts": split_counts,
        "year_counts_top10": dict(sorted(year_counts.items(), key=lambda kv: kv[1], reverse=True)[:10]),
        "split_excess": split_excess,
    }


def pass_compare(metric: str, actual: Any, expected: Any, tol: float) -> bool:
    if isinstance(expected, int):
        return int(actual) == int(expected)
    try:
        return abs(float(actual) - float(expected)) <= tol
    except Exception:
        return actual == expected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    cfg_path = (root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    cfg = read_json(cfg_path)
    out = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    dataset_path = root / cfg["dataset_path"]
    stage64m_summary_path = root / cfg["stage64m_summary_path"]
    stage64n3_summary_path = root / cfg["stage64n3_summary_path"]
    stage64m_summary = read_json(stage64m_summary_path, {})
    stage64n3_summary = read_json(stage64n3_summary_path, {})

    rows, fieldnames, ds_diag = load_dataset(dataset_path, cfg["columns"]["date"], cfg["columns"]["price"])
    independent = evaluate(rows, cfg)

    expected = cfg["expected_stage64m_headline"]
    tols = cfg["tolerances"]
    comparison_rows: List[Dict[str, Any]] = []
    all_match = True
    metric_tolerances = {
        "candidate_active_days": tols["active_days"],
        "candidate_mean_bps": tols["mean_bps"],
        "primary_benchmark_active_days": tols["active_days"],
        "primary_benchmark_mean_bps": tols["mean_bps"],
        "mean_excess_vs_primary_benchmark_bps": tols["excess_bps"],
        "positive_excess_splits_vs_primary_benchmark": tols["active_days"],
        "max_split_share_of_active_days": tols["share"],
        "max_year_share_of_active_days": tols["share"],
    }
    for metric, tol in metric_tolerances.items():
        actual = independent.get(metric)
        exp = expected.get(metric)
        ok = pass_compare(metric, actual, exp, tol)
        all_match = all_match and ok
        comparison_rows.append({"metric": metric, "expected": exp, "independent_recomputed": actual, "tolerance": tol, "pass": ok})

    forbidden_cols = [c for c in fieldnames if c.lower().startswith(("target", "signal", "validation")) or "event_filter" in c.lower() or "post_hoc" in c.lower()]
    n3_ok = stage64n3_summary.get("decision") == "SURVIVOR_HELD_FOR_REPLICATION_AND_ALIGNMENT_AUDIT_DESIGN_NO_ORDER"
    no_order_flags_ok = all(stage64n3_summary.get(k) == "NO_GO" for k in ["promotion", "EA", "paper_order", "paper_live", "live"])

    replication_pass = all_match and not forbidden_cols and n3_ok and no_order_flags_ok
    decision = (
        "FASTLANE_REPLICATION_PASSED_ALIGNMENT_CONTRACT_DECLARED_STAGE64O_ALLOWED_NO_ORDER"
        if replication_pass else
        "FASTLANE_REPLICATION_FAIL_FIX_PROVENANCE_OR_DOWNGRADE_NO_ORDER"
    )

    immutable_manifest = {
        "stage": cfg["stage"],
        "generated_utc": now_utc(),
        "dataset_path": str(dataset_path),
        "dataset_sha256": sha256_file(dataset_path),
        "config_path": str(cfg_path),
        "config_sha256": sha256_file(cfg_path),
        "stage64m_summary_path": str(stage64m_summary_path),
        "stage64m_summary_sha256": sha256_file(stage64m_summary_path),
        "stage64n3_summary_path": str(stage64n3_summary_path),
        "stage64n3_summary_sha256": sha256_file(stage64n3_summary_path),
        "target_survivor": cfg["target_survivor"],
        "candidate_rule": cfg["candidate_rule"],
        "benchmark_rule": cfg["benchmark_rule"],
        "splits": cfg["splits"],
        "source_of_truth_note": "Independent replication recomputes from Stage64K dataset and config rules; reports are used only as expected-stat comparison inputs.",
    }
    alignment_contract = {
        "stage": cfg["stage"],
        "generated_utc": now_utc(),
        "broker_spot_alignment_contract": cfg["broker_spot_alignment_contract"],
        "event_calendar_policy": "Historical event-calendar features remain excluded; forward-only governance ledger only after later validation.",
        "order_governance": "No order, paper-order, paper-live, live, EA promotion, or broker connection is authorized by Stage64N4.",
    }

    summary = {
        "stage": cfg["stage"],
        "status": "FASTLANE_REPLICATION_ALIGNMENT_AUDIT_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_order": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "validation_allowed_for_order_or_promotion": False,
        "validation_run_performed": False,
        "generated_utc": now_utc(),
        "root": str(root),
        "input_checks": {
            "stage64n3_decision_ok": n3_ok,
            "stage64n3_no_order_flags_ok": no_order_flags_ok,
            "dataset_found": dataset_path.exists(),
            "forbidden_columns": forbidden_cols,
        },
        "dataset_checks": ds_diag,
        "target_survivor": cfg["target_survivor"],
        "independent_replication": independent,
        "expected_stage64m_headline": expected,
        "replication_comparison_all_match": all_match,
        "replication_pass": replication_pass,
        "broker_spot_alignment_contract_declared": True,
        "event_calendar_forward_only_ledger_retained": True,
        "next_allowed_step": "Stage64O_EXTERNAL_REPLICATION_OR_BROKER_SPOT_ALIGNMENT_DATA_DECISION_NO_ORDER" if replication_pass else "Stage64N4_FAIL_FIX_PROVENANCE_OR_DOWNGRADE_NO_ORDER",
        "hard_blocks": [
            "NO_PAPER_ORDER",
            "NO_EA_PROMOTION",
            "NO_PAPER_LIVE",
            "NO_LIVE",
            "NO_BROKER_CONNECTION",
            "NO_ORDER_AUTHORIZATION_FROM_STAGE64N4",
            "NO_HISTORICAL_EVENT_FILTER_FROM_FORWARD_ONLY_GOVERNANCE",
            "NO_POST_HOC_EVENT_EXCLUSION",
            "NO_REDUCED_SCOPE_RETEST",
            "NO_RESCUE_FILTERING",
            "NO_NEW_INTRADAY_SCAN",
            "NO_COMMERCIALIZATION_WITHOUT_BROKER_SPOT_ALIGNMENT"
        ],
        "outputs": {
            "summary_json": str(out / "stage64n4_fastlane_replication_alignment_audit_summary.json"),
            "report_md": str(out / "stage64n4_fastlane_replication_alignment_audit_report.md"),
            "replication_comparison_csv": str(out / "stage64n4_replication_comparison.csv"),
            "immutable_reproduction_manifest_json": str(out / "stage64n4_immutable_reproduction_manifest.json"),
            "broker_spot_alignment_contract_json": str(out / "stage64n4_broker_spot_alignment_contract.json"),
        },
    }

    write_json(out / "stage64n4_fastlane_replication_alignment_audit_summary.json", summary)
    write_json(out / "stage64n4_immutable_reproduction_manifest.json", immutable_manifest)
    write_json(out / "stage64n4_broker_spot_alignment_contract.json", alignment_contract)

    with (out / "stage64n4_replication_comparison.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["metric", "expected", "independent_recomputed", "tolerance", "pass"])
        writer.writeheader()
        writer.writerows(comparison_rows)

    report_lines = [
        "# Stage64N4 - Fastlane Replication and Alignment Audit (No Order)",
        "",
        f"Generated UTC: `{summary['generated_utc']}`",
        "",
        "## Status",
        "",
        f"- status: `{summary['status']}`",
        f"- decision: `{summary['decision']}`",
        "- promotion/paper/live: `NO_GO`",
        "- validation_allowed_for_order_or_promotion: `false`",
        "",
        "## Executive conclusion",
        "",
        ("Independent replication passed and the broker/spot alignment contract was declared. "
         "The survivor remains research-only; no order, broker connection, paper-live, live, EA promotion, or commercialization claim is authorized." if replication_pass else
         "Independent replication failed or governance inputs were inconsistent. Fix provenance/accounting or downgrade; no tuning or order is authorized."),
        "",
        "## Target survivor",
        "",
        f"- hypothesis_id: `{cfg['target_survivor']['hypothesis_id']}`",
        f"- horizon_days: `{cfg['target_survivor']['horizon_days']}`",
        f"- primary_benchmark_id: `{cfg['target_survivor']['primary_benchmark_id']}`",
        "",
        "## Independent replication headline",
        "",
        "| metric | value |",
        "|---|---:|",
    ]
    for key in ["candidate_active_days", "candidate_mean_bps", "primary_benchmark_active_days", "primary_benchmark_mean_bps", "mean_excess_vs_primary_benchmark_bps", "positive_excess_splits_vs_primary_benchmark", "max_split_share_of_active_days", "max_year_share_of_active_days"]:
        report_lines.append(f"| `{key}` | `{independent.get(key)}` |")
    report_lines.extend([
        "",
        "## Replication comparison",
        "",
        "| metric | expected | independent | pass |",
        "|---|---:|---:|---:|",
    ])
    for r in comparison_rows:
        report_lines.append(f"| `{r['metric']}` | `{r['expected']}` | `{r['independent_recomputed']}` | `{r['pass']}` |")
    report_lines.extend([
        "",
        "## Broker/spot alignment contract",
        "",
        "Broker/spot D1 alignment is declared as a hard prerequisite before broker XAUUSD validation or commercialization claims. This stage does not connect to any broker.",
        "",
        "## Event-calendar governance",
        "",
        "Historical event-calendar features remain excluded. Forward-only governance may be retained only for future blackout/risk control after later validation.",
        "",
        "## Hard blocks",
        "",
    ])
    for b in summary["hard_blocks"]:
        report_lines.append(f"- `{b}`")
    report_lines.extend(["", "## Next allowed step", "", f"`{summary['next_allowed_step']}`", ""])
    (out / "stage64n4_fastlane_replication_alignment_audit_report.md").write_text("\n".join(report_lines), encoding="utf-8")

    print(json.dumps({"decision": decision, "replication_pass": replication_pass}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
