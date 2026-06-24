#!/usr/bin/env python3
"""
Stage64B - Stage58B Corrected Statistical Audit

Report-only audit for Stage58B. It does not mutate state, does not place orders,
and does not authorize promotion. The purpose is to apply a conservative
multiple-testing-aware interpretation to the current Stage58B forward telemetry.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import sqlite3
import statistics
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, sort_keys=False)
        f.write("\n")


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        delimiter = ","
        if "\t" in sample and sample.count("\t") > sample.count(","):
            delimiter = "\t"
        return list(csv.DictReader(f, delimiter=delimiter))


def as_float(x: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if x is None:
            return default
        return float(x)
    except (TypeError, ValueError):
        return default


def as_int(x: Any, default: int = 0) -> int:
    try:
        if x is None:
            return default
        return int(float(x))
    except (TypeError, ValueError):
        return default


def normal_sf(z: float) -> float:
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def exact_binomial_one_sided_p(n: int, wins: int, p0: float = 0.5) -> Optional[float]:
    if n <= 0 or wins < 0:
        return None
    if wins / n <= p0:
        return 1.0
    # n is small in this stage. For larger n, this still works for typical forward counts.
    p = 0.0
    for k in range(wins, n + 1):
        p += math.comb(n, k) * (p0 ** k) * ((1 - p0) ** (n - k))
    return min(1.0, max(0.0, p))


def bonferroni(p: Optional[float], m: int) -> Optional[float]:
    if p is None:
        return None
    return min(1.0, max(0.0, p * max(1, m)))


def median(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return float(statistics.median(values))


def mean(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return float(sum(values) / len(values))


def sample_stdev(values: List[float]) -> Optional[float]:
    if len(values) < 2:
        return None
    return float(statistics.stdev(values))


def one_sided_mean_p_normal_approx(values: List[float]) -> Optional[float]:
    if len(values) < 2:
        return None
    mu = mean(values)
    sd = sample_stdev(values)
    if mu is None or sd is None or sd <= 0:
        return None
    z = mu / (sd / math.sqrt(len(values)))
    return normal_sf(z)


def find_first_existing(root: Path, candidates: Iterable[str]) -> Optional[Path]:
    for c in candidates:
        p = root / c
        if p.exists():
            return p
    return None


def extract_metrics_from_stage59(stage59: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not stage59:
        return {}
    metrics = stage59.get("metrics") or {}
    return dict(metrics)


def load_stage58a_candidate_rows(root: Path, stage59: Optional[Dict[str, Any]], config: Dict[str, Any]) -> Tuple[List[Dict[str, str]], Optional[Path], Dict[str, Any]]:
    paths = []
    if config.get("stage58a_candidates"):
        paths.append(str(config["stage58a_candidates"]))
    meta_path = (((stage59 or {}).get("stage58a_candidates_meta") or {}).get("path"))
    if meta_path:
        # If absolute path is from user repo, remap to current root by suffix when possible.
        meta = Path(meta_path)
        if meta.is_absolute():
            try:
                idx = meta.parts.index("reports")
                paths.append(str(Path(*meta.parts[idx:])))
            except ValueError:
                paths.append(str(meta))
        else:
            paths.append(str(meta))
    paths.append("reports/stage58_context_aware_stage51/stage58a_context_aware_stage51_regime_audit_candidates.csv")

    for rel in paths:
        p = Path(rel)
        if not p.is_absolute():
            p = root / p
        rows = read_csv_rows(p)
        if rows:
            meta = {
                "found": True,
                "path": str(p),
                "rows": len(rows),
                "unique_candidate_ids": len({r.get("candidate_id") or r.get("candidate") or r.get("id") for r in rows if (r.get("candidate_id") or r.get("candidate") or r.get("id"))}),
            }
            pass_like = []
            for r in rows:
                decision_text = " ".join(str(v) for v in r.values()).upper()
                if "PASS" in decision_text or "WATCH" in decision_text or "TRUE" in decision_text:
                    pass_like.append(r)
            meta["pass_like_rows_conservative"] = len(pass_like) if pass_like else len(rows)
            return rows, p, meta

    meta = ((stage59 or {}).get("stage58a_candidates_meta") or {})
    fallback = {
        "found": False,
        "path": None,
        "rows": as_int(meta.get("rows"), 0),
        "pass_like_rows_conservative": as_int(meta.get("pass_rows"), 0),
        "unique_candidate_ids": len(meta.get("candidate_ids") or []),
        "source": "stage59_meta_fallback",
    }
    return [], None, fallback


def load_signal_rows_from_sqlite(root: Path, config: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    db_rel = config.get("stage58b_state_db", "data/shadow/stage58b_context_forward_shadow.sqlite")
    db_path = Path(db_rel)
    if not db_path.is_absolute():
        db_path = root / db_path
    meta = {"path": str(db_path), "found": db_path.exists(), "schema_ok": False, "rows_read": 0, "error": None}
    if not db_path.exists():
        return [], meta
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(signals)")
        cols = [r[1] for r in cur.fetchall()]
        meta["columns"] = cols
        if "signals" and "stress_bps" in cols:
            meta["schema_ok"] = True
        else:
            meta["error"] = "signals table missing stress_bps"
            conn.close()
            return [], meta
        cur.execute("SELECT * FROM signals")
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        meta["rows_read"] = len(rows)
        return rows, meta
    except Exception as exc:  # report-only, do not crash entire audit if sqlite is unavailable
        meta["error"] = f"{type(exc).__name__}: {exc}"
        return [], meta


def compute_metrics_from_signal_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    evaluated = []
    pending = []
    true_forward = []
    backfill = []
    for r in rows:
        is_backfill = as_int(r.get("is_backfill"), 0) != 0
        if is_backfill:
            backfill.append(r)
        else:
            true_forward.append(r)
        stress = as_float(r.get("stress_bps"))
        status = str(r.get("status") or "").upper()
        if stress is None or status in {"PENDING", "OPEN", "NEW"}:
            pending.append(r)
        else:
            evaluated.append(r)
    stress_values = [float(r["stress_bps"]) for r in evaluated if as_float(r.get("stress_bps")) is not None]
    wins = sum(1 for x in stress_values if x > 0)
    candidates = {}
    for r in true_forward:
        cid = str(r.get("candidate_id") or "UNKNOWN")
        candidates.setdefault(cid, []).append(r)
    candidate_means = {}
    for cid, crs in candidates.items():
        vals = [as_float(r.get("stress_bps")) for r in crs if as_float(r.get("stress_bps")) is not None]
        if vals:
            candidate_means[cid] = sum(vals) / len(vals)
    return {
        "total_state_rows": len(rows),
        "backfill_signals": len(backfill),
        "true_forward_signals": len(true_forward),
        "pending_signals": len(pending),
        "evaluated_signals": len(evaluated),
        "evaluated_mean_stress_bps": mean(stress_values),
        "evaluated_median_stress_bps": median(stress_values),
        "evaluated_win_rate": (wins / len(stress_values)) if stress_values else None,
        "evaluated_wins": wins,
        "evaluated_losses_or_zero": len(stress_values) - wins,
        "distinct_candidate_ids": len(candidates),
        "candidate_mean_stress_bps": candidate_means,
        "negative_candidate_mean_count": sum(1 for v in candidate_means.values() if v < 0),
        "stress_values_available": bool(stress_values),
    }


def merge_metrics(primary: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(fallback or {})
    for k, v in (primary or {}).items():
        if v is not None:
            out[k] = v
    if "evaluated_wins" not in out:
        n = as_int(out.get("evaluated_signals"), 0)
        wr = as_float(out.get("evaluated_win_rate"), None)
        if n and wr is not None:
            out["evaluated_wins"] = int(round(n * wr))
            out["evaluated_losses_or_zero"] = n - out["evaluated_wins"]
    return out


def classify_role(metrics: Dict[str, Any], corrected: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    n_true = as_int(metrics.get("true_forward_signals"), 0)
    n_eval = as_int(metrics.get("evaluated_signals"), 0)
    mean_bps = as_float(metrics.get("evaluated_mean_stress_bps"), None)
    median_bps = as_float(metrics.get("evaluated_median_stress_bps"), None)
    wr = as_float(metrics.get("evaluated_win_rate"), None)
    neg_count = as_int(metrics.get("negative_candidate_mean_count"), 999999)
    backfill = as_int(metrics.get("backfill_signals"), 999999)
    fspan = as_float(metrics.get("forward_span_days"), 0.0) or 0.0
    espan = as_float(metrics.get("evaluated_span_days"), 0.0) or 0.0
    max_day = as_float(metrics.get("max_day_share"), 1.0) or 1.0

    gates = {
        "true_forward_signals": {"observed": n_true, "threshold": config.get("min_true_forward_signals", 100), "passed": n_true >= as_int(config.get("min_true_forward_signals", 100))},
        "evaluated_signals": {"observed": n_eval, "threshold": config.get("min_evaluated_signals", 60), "passed": n_eval >= as_int(config.get("min_evaluated_signals", 60))},
        "forward_span_days": {"observed": fspan, "threshold": config.get("min_forward_span_days", 10.0), "passed": fspan >= float(config.get("min_forward_span_days", 10.0))},
        "evaluated_span_days": {"observed": espan, "threshold": config.get("min_evaluated_span_days", 5.0), "passed": espan >= float(config.get("min_evaluated_span_days", 5.0))},
        "max_day_share": {"observed": max_day, "threshold": config.get("max_day_share", 0.35), "passed": max_day <= float(config.get("max_day_share", 0.35))},
        "mean_stress_bps": {"observed": mean_bps, "threshold": config.get("min_mean_stress_bps", 2.0), "passed": mean_bps is not None and mean_bps >= float(config.get("min_mean_stress_bps", 2.0))},
        "median_stress_bps": {"observed": median_bps, "threshold": config.get("min_median_stress_bps", 0.0), "passed": median_bps is not None and median_bps >= float(config.get("min_median_stress_bps", 0.0))},
        "win_rate": {"observed": wr, "threshold": config.get("min_win_rate", 0.53), "passed": wr is not None and wr >= float(config.get("min_win_rate", 0.53))},
        "negative_candidate_mean_count": {"observed": neg_count, "threshold": config.get("max_negative_candidate_mean_count", 1), "passed": neg_count <= as_int(config.get("max_negative_candidate_mean_count", 1))},
        "backfill_signals": {"observed": backfill, "threshold": 0, "passed": backfill <= 0},
    }
    failed = [k for k, v in gates.items() if not v["passed"]]
    uncorrected_quality = all(gates[k]["passed"] for k in ["mean_stress_bps", "median_stress_bps", "win_rate", "negative_candidate_mean_count", "backfill_signals"])
    scale_ok = all(gates[k]["passed"] for k in ["true_forward_signals", "evaluated_signals", "forward_span_days", "evaluated_span_days", "max_day_share"])

    alpha = float(config.get("alpha", 0.05))
    p_sign_corr = corrected.get("bonferroni_sign_test_p")
    p_mean_corr = corrected.get("bonferroni_mean_positive_p_normal_approx")
    sign_ok = p_sign_corr is not None and p_sign_corr <= alpha
    mean_stat_ok = p_mean_corr is None or p_mean_corr <= alpha
    mtc_ok = sign_ok and mean_stat_ok

    if not uncorrected_quality:
        role = "ARCHIVE_OR_PASSIVE_TELEMETRY_ONLY_NO_PROMOTION"
        reason = "Uncorrected quality gates are not stable enough."
    elif uncorrected_quality and not scale_ok:
        role = "PASSIVE_TELEMETRY_SECONDARY_RESEARCH_ONLY_NO_PROMOTION"
        reason = "Quality is currently positive, but sample/span/concentration gates are insufficient."
    elif uncorrected_quality and scale_ok and not mtc_ok:
        role = "SECONDARY_RESEARCH_ONLY_MTC_NOT_SIGNIFICANT_NO_PROMOTION"
        reason = "Operational gates may be adequate, but multiple-testing-corrected evidence is not significant."
    else:
        role = "SECONDARY_RESEARCH_CANDIDATE_ONLY_NO_PROMOTION_UNDER_STAGE64_POLICY"
        reason = "Corrected statistical evidence is acceptable, but Stage64 policy still blocks direct promotion and routes main work to macro-regime thesis."

    return {
        "role": role,
        "reason": reason,
        "uncorrected_quality_ok": uncorrected_quality,
        "scale_and_concentration_ok": scale_ok,
        "multiple_testing_corrected_statistical_ok": mtc_ok,
        "gates": gates,
        "failed_gates": failed,
    }


def markdown_table(rows: List[Tuple[str, Any]]) -> str:
    lines = ["| metric | value |", "|---|---:|"]
    for k, v in rows:
        if isinstance(v, float):
            s = f"{v:.10g}"
        else:
            s = str(v)
        lines.append(f"| {k} | {s} |")
    return "\n".join(lines)


def write_report(path: Path, summary: Dict[str, Any]) -> None:
    m = summary["stage58b_corrected_audit"]["metrics"]
    corr = summary["stage58b_corrected_audit"]["corrected_statistics"]
    role = summary["stage58b_corrected_audit"]["role_decision"]
    mt = summary["multiple_testing"]
    lines = []
    lines.append("# Stage64B - Stage58B Corrected Statistical Audit")
    lines.append("")
    lines.append(f"- status: `{summary['status']}`")
    lines.append(f"- decision: `{summary['decision']}`")
    lines.append(f"- promotion: `{summary['promotion']}`")
    lines.append(f"- paper_order: `{summary['paper_order']}`")
    lines.append(f"- live: `{summary['live']}`")
    lines.append("")
    lines.append("## Executive conclusion")
    lines.append("")
    lines.append("Stage58B remains a passive telemetry / secondary research path only. It is not a promotion path under Stage64. The current evidence is interpreted after applying a conservative multiple-testing penalty from the available Stage58A candidate/variant universe.")
    lines.append("")
    lines.append(f"Final role: `{role['role']}`")
    lines.append("")
    lines.append(role["reason"])
    lines.append("")
    lines.append("## Stage58B forward metrics")
    lines.append("")
    lines.append(markdown_table([
        ("true_forward_signals", m.get("true_forward_signals")),
        ("evaluated_signals", m.get("evaluated_signals")),
        ("pending_signals", m.get("pending_signals")),
        ("backfill_signals", m.get("backfill_signals")),
        ("evaluated_mean_stress_bps", m.get("evaluated_mean_stress_bps")),
        ("evaluated_median_stress_bps", m.get("evaluated_median_stress_bps")),
        ("evaluated_win_rate", m.get("evaluated_win_rate")),
        ("evaluated_wins", m.get("evaluated_wins")),
        ("negative_candidate_mean_count", m.get("negative_candidate_mean_count")),
        ("forward_span_days", m.get("forward_span_days")),
        ("evaluated_span_days", m.get("evaluated_span_days")),
        ("max_day_share", m.get("max_day_share")),
        ("max_candidate_share", m.get("max_candidate_share")),
        ("distinct_candidate_ids", m.get("distinct_candidate_ids")),
    ]))
    lines.append("")
    lines.append("## Multiple-testing model")
    lines.append("")
    lines.append(markdown_table([
        ("stage58a_candidate_rows", mt.get("stage58a_candidate_rows")),
        ("stage58a_pass_like_rows", mt.get("stage58a_pass_like_rows")),
        ("active_stage58b_candidate_count", mt.get("active_stage58b_candidate_count")),
        ("effective_test_count", mt.get("effective_test_count")),
        ("effective_test_count_rule", mt.get("effective_test_count_rule")),
    ]))
    lines.append("")
    lines.append("## Corrected statistics")
    lines.append("")
    lines.append(markdown_table([
        ("sign_test_one_sided_p_uncorrected", corr.get("sign_test_one_sided_p_uncorrected")),
        ("bonferroni_sign_test_p", corr.get("bonferroni_sign_test_p")),
        ("mean_positive_p_normal_approx_uncorrected", corr.get("mean_positive_p_normal_approx_uncorrected")),
        ("bonferroni_mean_positive_p_normal_approx", corr.get("bonferroni_mean_positive_p_normal_approx")),
        ("alpha", corr.get("alpha")),
    ]))
    lines.append("")
    lines.append("## Gate interpretation")
    lines.append("")
    lines.append("Failed gates:")
    for g in role.get("failed_gates", []):
        lines.append(f"- `{g}`")
    lines.append("")
    lines.append("## Candidate-level means")
    lines.append("")
    cmeans = m.get("candidate_mean_stress_bps") or {}
    if cmeans:
        lines.append("| candidate_id | mean_stress_bps |")
        lines.append("|---|---:|")
        for cid, val in sorted(cmeans.items()):
            lines.append(f"| `{cid}` | {float(val):.10g} |")
    else:
        lines.append("Candidate-level means were not available from the current input artifacts.")
    lines.append("")
    lines.append("## Operational decision")
    lines.append("")
    lines.append("No paper-order, paper-live, live, or EA promotion is authorized. Stage58B may continue only as passive independent telemetry and as a corrected statistical reference stream while the Stage64 macro-regime thesis becomes the main program.")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", default="configs/stage64b_stage58b_corrected_statistical_audit.json")
    ap.add_argument("--out", default="reports/stage64b_stage58b_corrected_statistical_audit")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    cfg_path = Path(args.config)
    if not cfg_path.is_absolute():
        cfg_path = root / cfg_path
    config = read_json(cfg_path) or {}
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    stage59_path = find_first_existing(root, [
        config.get("stage59_summary", ""),
        "reports/stage59_context_forward_gates/stage59_context_forward_gate_summary.json",
    ])
    stage58b_path = find_first_existing(root, [
        config.get("stage58b_summary", ""),
        "reports/stage58_context_forward_shadow/stage58b_context_forward_shadow_summary.json",
    ])
    stage64a_ledger_path = find_first_existing(root, [
        config.get("stage64a_ledger", ""),
        "reports/stage64a_research_freeze_cleanup/stage64a_experiment_ledger_skeleton.csv",
    ])

    stage59 = read_json(stage59_path) if stage59_path else None
    stage58b = read_json(stage58b_path) if stage58b_path else None
    stage58a_rows, stage58a_path, stage58a_meta = load_stage58a_candidate_rows(root, stage59, config)
    sqlite_rows, sqlite_meta = load_signal_rows_from_sqlite(root, config)

    fallback_metrics = extract_metrics_from_stage59(stage59)
    sqlite_metrics = compute_metrics_from_signal_rows(sqlite_rows) if sqlite_rows else {}
    metrics = merge_metrics(sqlite_metrics, fallback_metrics)

    n_eval = as_int(metrics.get("evaluated_signals"), 0)
    wins = as_int(metrics.get("evaluated_wins"), 0)
    sign_p = exact_binomial_one_sided_p(n_eval, wins, 0.5)
    stress_values = []
    if sqlite_rows:
        for r in sqlite_rows:
            stress = as_float(r.get("stress_bps"))
            if stress is not None and str(r.get("status") or "").upper() not in {"PENDING", "OPEN", "NEW"}:
                stress_values.append(stress)
    mean_p = one_sided_mean_p_normal_approx(stress_values)

    active_candidate_count = as_int(metrics.get("distinct_candidate_ids"), 0)
    stage58a_rows_count = as_int(stage58a_meta.get("rows"), 0)
    stage58a_pass_count = as_int(stage58a_meta.get("pass_like_rows_conservative"), 0)
    floor = as_int(config.get("effective_test_count_floor", 100), 100)
    effective_test_count = max(1, active_candidate_count, stage58a_rows_count, stage58a_pass_count, floor)

    corrected = {
        "alpha": float(config.get("alpha", 0.05)),
        "evaluated_signals": n_eval,
        "evaluated_wins": wins,
        "sign_test_one_sided_p_uncorrected": sign_p,
        "bonferroni_sign_test_p": bonferroni(sign_p, effective_test_count),
        "mean_positive_p_normal_approx_uncorrected": mean_p,
        "bonferroni_mean_positive_p_normal_approx": bonferroni(mean_p, effective_test_count),
        "note": "Sign-test is exact under p0=0.5. Mean p-value is a normal approximation and is only reported when per-signal stress values are available from SQLite.",
    }

    multiple_testing = {
        "stage58a_candidate_rows": stage58a_rows_count,
        "stage58a_pass_like_rows": stage58a_pass_count,
        "active_stage58b_candidate_count": active_candidate_count,
        "effective_test_count_floor": floor,
        "effective_test_count": effective_test_count,
        "effective_test_count_rule": "max(stage58a_rows, stage58a_pass_like_rows, active_stage58b_candidate_count, configured_floor)",
        "stage58a_candidates_path": str(stage58a_path) if stage58a_path else stage58a_meta.get("path"),
        "ledger_path": str(stage64a_ledger_path) if stage64a_ledger_path else None,
    }

    role = classify_role(metrics, corrected, config)

    summary = {
        "stage": "Stage64B_STAGE58B_CORRECTED_STATISTICAL_AUDIT_NO_PROMOTION",
        "status": "CORRECTED_STATISTICAL_AUDIT_COMPLETE_NO_PROMOTION",
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_order": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "decision": role["role"],
        "next_allowed_step": "CONTINUE_STAGE58B_PASSIVE_TELEMETRY_AND_START_STAGE64C_MACRO_REGIME_THESIS_SPEC",
        "generated_utc": utc_now(),
        "root": str(root),
        "inputs": {
            "config": str(cfg_path),
            "stage59_summary": str(stage59_path) if stage59_path else None,
            "stage58b_summary": str(stage58b_path) if stage58b_path else None,
            "stage58a_candidates": str(stage58a_path) if stage58a_path else None,
            "stage58b_state_db": sqlite_meta,
        },
        "multiple_testing": multiple_testing,
        "stage58b_corrected_audit": {
            "metrics": metrics,
            "corrected_statistics": corrected,
            "role_decision": role,
        },
        "hard_blocks": [
            "NO_PAPER_ORDER",
            "NO_EA_PROMOTION",
            "NO_PAPER_LIVE",
            "NO_LIVE",
            "NO_BROKER_CONNECTION",
            "NO_STAGE58B_PROMOTION_UNDER_STAGE64_POLICY",
        ],
    }

    write_json(out_dir / "stage64b_stage58b_corrected_statistical_audit_summary.json", summary)
    write_report(out_dir / "stage64b_stage58b_corrected_statistical_audit_report.md", summary)
    print(json.dumps({
        "stage": summary["stage"],
        "status": summary["status"],
        "decision": summary["decision"],
        "effective_test_count": effective_test_count,
        "sign_p_corrected": corrected["bonferroni_sign_test_p"],
        "out": str(out_dir),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
