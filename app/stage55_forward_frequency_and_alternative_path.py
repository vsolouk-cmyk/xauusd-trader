#!/usr/bin/env python3
"""
Stage55 forward-frequency and alternative-path readiness report.

This script is intentionally non-trading. It reads existing Stage52/53/54 state plus
Stage51 historical candidate metadata and estimates whether forward evidence is
likely to accumulate fast enough. Historical cadence is treated only as a cadence
prior, never as promotion evidence.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

STAGE = "Stage55_FORWARD_FREQUENCY_AND_ALTERNATIVE_PATH_NO_PROMOTION"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        return {"_read_error": str(exc), "_path": str(path)}


def parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).astimezone(timezone.utc)
    except Exception:
        return None


def iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or str(x).strip() == "":
            return default
        return float(x)
    except Exception:
        return default


def safe_int(x: Any, default: int = 0) -> int:
    try:
        if x is None or str(x).strip() == "":
            return default
        return int(float(x))
    except Exception:
        return default


def load_config(path: Path) -> Dict[str, Any]:
    defaults = {
        "stage": STAGE,
        "min_true_forward_signals": 100,
        "min_evaluated_signals": 60,
        "max_wait_days_before_parallel_scan": 21,
        "cadence_prior_overlap_discount_base": 0.35,
        "cadence_prior_overlap_discount_low": 0.20,
        "cadence_prior_overlap_discount_high": 0.60,
        "min_expected_true_forward_signals_per_week_warning": 8,
        "alternative_path_policy": {
            "start_parallel_design_if_forecast_days_gt": 21,
            "start_parallel_megascan_if_after_market_reopen_forward_rate_lt_per_week": 5,
            "do_not_archive_stage51_until_forward_gate_fail_or_timeout": True,
        },
        "alternative_thesis_queue": [
            {
                "id": "ALT_A_PULLBACK_AFTER_SQUEEZE_FAILURE",
                "description": "After volatility squeeze breakout fails to follow through, test controlled mean-reversion/pullback continuation with cost-aware broker data.",
                "why": "If forward frequency is too sparse, failed-breakout reactions may occur more often than clean breakouts.",
                "status": "DESIGN_ONLY_NO_SCAN_YET",
            },
            {
                "id": "ALT_B_INTRADAY_TREND_PULLBACK_TO_M15_VALUE_AREA",
                "description": "Trend-confirmed M15/M30 pullback after active-session directional impulse, avoiding pure breakout chasing.",
                "why": "Could produce higher frequency than squeeze breakout while keeping structural trend context.",
                "status": "DESIGN_ONLY_NO_SCAN_YET",
            },
            {
                "id": "ALT_C_SESSION_RANGE_REVERSION_AFTER_EXHAUSTION",
                "description": "Broker-real intraday exhaustion/reversion only after range extension and spread-safe session filters.",
                "why": "A non-breakout family for diversification if Stage51 forward cadence or edge collapses.",
                "status": "DESIGN_ONLY_NO_SCAN_YET",
            },
        ],
    }
    user = read_json(path) if path.exists() else None
    if isinstance(user, dict):
        def merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
            out = dict(a)
            for k, v in b.items():
                if isinstance(v, dict) and isinstance(out.get(k), dict):
                    out[k] = merge(out[k], v)
                else:
                    out[k] = v
            return out
        return merge(defaults, user)
    return defaults


def broker_m15_span(db_path: Path) -> Dict[str, Any]:
    meta = {"found": db_path.exists(), "schema_ok": False, "rows": 0, "start_utc": None, "end_utc": None, "span_days": 0.0, "error": None}
    if not db_path.exists():
        return meta
    try:
        con = sqlite3.connect(str(db_path))
        cur = con.cursor()
        cur.execute("SELECT COUNT(*), MIN(time_utc), MAX(time_utc) FROM amarkets_bars WHERE timeframe='M15'")
        row = cur.fetchone()
        con.close()
        if row:
            rows, start, end = row
            sdt, edt = parse_dt(start), parse_dt(end)
            span_days = max(0.0, ((edt - sdt).total_seconds() / 86400.0) if sdt and edt else 0.0)
            meta.update({"schema_ok": True, "rows": int(rows or 0), "start_utc": iso(sdt), "end_utc": iso(edt), "span_days": span_days})
    except Exception as exc:
        meta["error"] = str(exc)
    return meta


def read_stage51_candidates(path: Path) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "found": path.exists(),
        "rows": 0,
        "pass_rows": 0,
        "total_pass_trade_count": 0,
        "best_single_candidate_trade_count": 0,
        "candidate_ids": [],
        "sample": [],
        "error": None,
    }
    if not path.exists():
        return out
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for r in reader:
                out["rows"] += 1
                status = str(r.get("status", "") or r.get("decision", "") or "")
                passish = "PASS" in status and "NO_PASS" not in status
                if passish:
                    cid = str(r.get("candidate_id") or r.get("id") or "").strip()
                    tc = safe_int(r.get("trade_count", r.get("trades", 0)))
                    out["pass_rows"] += 1
                    out["total_pass_trade_count"] += tc
                    out["best_single_candidate_trade_count"] = max(out["best_single_candidate_trade_count"], tc)
                    if cid:
                        out["candidate_ids"].append(cid)
                    if len(out["sample"]) < 12:
                        out["sample"].append({
                            "candidate_id": cid,
                            "trade_count": tc,
                            "status": status,
                            "mean_stress_bps": safe_float(r.get("mean_stress_bps", r.get("mean", 0)), 0),
                            "win_rate": safe_float(r.get("win_rate", r.get("wr", 0)), 0),
                        })
    except Exception as exc:
        out["error"] = str(exc)
    return out


def read_shadow_state(db_path: Path) -> Dict[str, Any]:
    meta = {"found": db_path.exists(), "schema_ok": False, "total": 0, "true_forward": 0, "backfill": 0, "pending": 0, "evaluated": 0, "first_entry_utc": None, "last_entry_utc": None, "span_days": 0.0, "watermark_utc": None, "error": None}
    if not db_path.exists():
        return meta
    try:
        con = sqlite3.connect(str(db_path))
        cur = con.cursor()
        cur.execute("SELECT value FROM kv WHERE key='forward_watermark_m15_utc'")
        row = cur.fetchone()
        if row:
            meta["watermark_utc"] = row[0]
        cur.execute("SELECT COUNT(*) FROM signals")
        meta["total"] = int(cur.fetchone()[0] or 0)
        cur.execute("SELECT COUNT(*) FROM signals WHERE COALESCE(is_backfill,0)=0")
        meta["true_forward"] = int(cur.fetchone()[0] or 0)
        cur.execute("SELECT COUNT(*) FROM signals WHERE COALESCE(is_backfill,0)=1")
        meta["backfill"] = int(cur.fetchone()[0] or 0)
        cur.execute("SELECT COUNT(*) FROM signals WHERE status='PENDING'")
        meta["pending"] = int(cur.fetchone()[0] or 0)
        cur.execute("SELECT COUNT(*) FROM signals WHERE status='EVALUATED'")
        meta["evaluated"] = int(cur.fetchone()[0] or 0)
        cur.execute("SELECT MIN(entry_time_utc), MAX(entry_time_utc) FROM signals WHERE COALESCE(is_backfill,0)=0")
        r = cur.fetchone()
        con.close()
        if r:
            first, last = parse_dt(r[0]), parse_dt(r[1])
            meta["first_entry_utc"] = iso(first)
            meta["last_entry_utc"] = iso(last)
            meta["span_days"] = max(0.0, ((last - first).total_seconds() / 86400.0) if first and last else 0.0)
        meta["schema_ok"] = True
    except Exception as exc:
        meta["error"] = str(exc)
    return meta


def forecast_from_prior(candidates: Dict[str, Any], broker_span: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    span_days = float(broker_span.get("span_days") or 0.0)
    total_tc = int(candidates.get("total_pass_trade_count") or 0)
    best_tc = int(candidates.get("best_single_candidate_trade_count") or 0)
    raw_daily = (total_tc / span_days) if span_days > 0 else 0.0
    best_daily = (best_tc / span_days) if span_days > 0 else 0.0
    low = raw_daily * float(cfg.get("cadence_prior_overlap_discount_low", 0.20))
    base = raw_daily * float(cfg.get("cadence_prior_overlap_discount_base", 0.35))
    high = raw_daily * float(cfg.get("cadence_prior_overlap_discount_high", 0.60))
    # Guard against pure summed-candidate overestimation: base should not imply more than 3x the best single candidate unless evidence exists.
    base_capped = min(base, best_daily * 3.0) if best_daily > 0 else base
    high_capped = min(high, best_daily * 5.0) if best_daily > 0 else high
    min_true = int(cfg.get("min_true_forward_signals", 100))
    min_eval = int(cfg.get("min_evaluated_signals", 60))
    def days_needed(rate: float, n: int) -> Optional[float]:
        return (n / rate) if rate > 0 else None
    return {
        "basis": "HISTORICAL_CADENCE_PRIOR_ONLY_NOT_FORWARD_EVIDENCE",
        "broker_span_days": span_days,
        "pass_candidate_count": int(candidates.get("pass_rows") or 0),
        "historical_total_pass_trade_count_sum": total_tc,
        "best_single_candidate_trade_count": best_tc,
        "raw_summed_candidate_signals_per_day": raw_daily,
        "best_single_candidate_signals_per_day": best_daily,
        "overlap_adjusted_signals_per_day_low": low,
        "overlap_adjusted_signals_per_day_base": base_capped,
        "overlap_adjusted_signals_per_day_high": high_capped,
        "overlap_adjusted_signals_per_week_base": base_capped * 7.0,
        "forecast_days_to_min_true_forward_base": days_needed(base_capped, min_true),
        "forecast_days_to_min_evaluated_base": days_needed(base_capped, min_eval),
    }


def decide(stage54: Optional[Dict[str, Any]], shadow: Dict[str, Any], prior: Dict[str, Any], cfg: Dict[str, Any]) -> Tuple[str, str, List[str]]:
    reasons: List[str] = []
    if stage54 and stage54.get("decision") and "OPS_READY" not in str(stage54.get("decision")):
        return "FIX_OPS_READINESS_FIRST_NO_PROMOTION", "FIX_OPS_READINESS_THEN_RECHECK_NO_PROMOTION", ["stage54_not_ops_ready"]
    if int(shadow.get("backfill") or 0) > 0:
        return "RESET_OR_REPAIR_BACKFILL_CONTAMINATED_FORWARD_STATE_NO_PROMOTION", "FIX_STAGE52_STATE_NO_PROMOTION", ["backfill_signals_detected"]
    if int(shadow.get("true_forward") or 0) == 0:
        reasons.append("no_true_forward_signals_yet")
    forecast_days = prior.get("forecast_days_to_min_true_forward_base")
    max_wait = float(cfg.get("max_wait_days_before_parallel_scan", 21))
    if forecast_days is None:
        reasons.append("no_cadence_prior_available")
        return "WAIT_FOR_MARKET_REOPEN_AND_PREPARE_PARALLEL_ALTERNATIVES_NO_PROMOTION", "RUN_STAGE52_STAGE53_AFTER_MARKET_REOPEN_AND_KEEP_ALT_DESIGNS_READY_NO_PROMOTION", reasons
    if forecast_days > max_wait:
        reasons.append("forecast_to_min_evidence_exceeds_wait_threshold")
        return "CONTINUE_STAGE52_BUT_PREPARE_PARALLEL_ALTERNATIVE_SCAN_NO_PROMOTION", "AFTER_MARKET_REOPEN_RUN_STAGE52_STAGE53_AND_OPTIONALLY_START_ALT_MEGASCAN_DESIGN_NO_PROMOTION", reasons
    if int(shadow.get("true_forward") or 0) == 0:
        return "WAIT_FOR_MARKET_REOPEN_WITH_STAGE51_AS_ACTIVE_FORWARD_CANDIDATE_NO_PROMOTION", "UPDATE_AMARKETS_AFTER_MARKET_REOPEN_THEN_RUN_STAGE52_STAGE53_NO_PROMOTION", reasons
    return "CONTINUE_TRUE_FORWARD_SHADOW_NO_PROMOTION", "CONTINUE_STAGE52_STAGE53_UNTIL_GATE_PASS_OR_FAIL_NO_PROMOTION", reasons


def write_outputs(out_dir: Path, summary: Dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "stage55_forward_frequency_and_alternative_path_summary.json"
    report_path = out_dir / "stage55_forward_frequency_and_alternative_path_report.md"
    queue_path = out_dir / "stage55_alternative_thesis_queue.csv"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    cfg = summary.get("config", {})
    alt = cfg.get("alternative_thesis_queue", [])
    with queue_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "description", "why", "status"])
        writer.writeheader()
        for row in alt:
            writer.writerow({k: row.get(k, "") for k in ["id", "description", "why", "status"]})

    p = summary.get("frequency_prior", {})
    sh = summary.get("shadow_state", {})
    lines = []
    lines.append("# Stage55 Forward Frequency and Alternative Path Readiness")
    lines.append("")
    for k in ["status", "decision", "next_allowed_step", "promotion", "EA", "paper_live", "live"]:
        lines.append(f"- {k}: `{summary.get(k)}`")
    lines.append("")
    lines.append("## Forward state")
    lines.append(f"- watermark_utc: `{sh.get('watermark_utc')}`")
    lines.append(f"- true_forward_signals: `{sh.get('true_forward')}`")
    lines.append(f"- pending_signals: `{sh.get('pending')}`")
    lines.append(f"- evaluated_signals: `{sh.get('evaluated')}`")
    lines.append(f"- backfill_signals: `{sh.get('backfill')}`")
    lines.append("")
    lines.append("## Historical cadence prior, not forward evidence")
    lines.append(f"- pass_candidate_count: `{p.get('pass_candidate_count')}`")
    lines.append(f"- broker_span_days: `{p.get('broker_span_days')}`")
    lines.append(f"- historical_total_pass_trade_count_sum: `{p.get('historical_total_pass_trade_count_sum')}`")
    lines.append(f"- raw_summed_candidate_signals_per_day: `{p.get('raw_summed_candidate_signals_per_day')}`")
    lines.append(f"- overlap_adjusted_signals_per_day_base: `{p.get('overlap_adjusted_signals_per_day_base')}`")
    lines.append(f"- overlap_adjusted_signals_per_week_base: `{p.get('overlap_adjusted_signals_per_week_base')}`")
    lines.append(f"- forecast_days_to_min_true_forward_base: `{p.get('forecast_days_to_min_true_forward_base')}`")
    lines.append("")
    lines.append("## Alternative path queue")
    for row in alt:
        lines.append(f"- `{row.get('id')}`: {row.get('description')} Status: `{row.get('status')}`")
    lines.append("")
    lines.append("## Interpretation")
    lines.append("Stage55 does not authorize promotion, EA, paper-live, live trading, or order submission. Historical cadence is used only to estimate how long forward evidence may take to accumulate. If actual true-forward cadence is too low after the market reopens, the alternative queue can be scanned in parallel without rescuing Stage51.")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--db", default="data/broker_normalized/amarkets_multitf.sqlite")
    ap.add_argument("--state-db", default="data/shadow/stage52_forward_shadow.sqlite")
    ap.add_argument("--stage51-candidates", default="reports/stage51_volatility_squeeze/stage51_volatility_squeeze_breakout_candidates.csv")
    ap.add_argument("--stage54-summary", default="reports/stage54_ops_readiness/stage54_ops_readiness_summary.json")
    ap.add_argument("--config", default="configs/stage55_forward_frequency_plan.json")
    ap.add_argument("--out", default="reports/stage55_frequency_and_alternatives")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    cfg = load_config(root / args.config)
    stage54 = read_json(root / args.stage54_summary)
    broker = broker_m15_span(root / args.db)
    candidates = read_stage51_candidates(root / args.stage51_candidates)
    shadow = read_shadow_state(root / args.state_db)
    prior = forecast_from_prior(candidates, broker, cfg)
    decision, next_step, reasons = decide(stage54, shadow, prior, cfg)

    summary = {
        "stage": STAGE,
        "status": "FORWARD_FREQUENCY_AND_ALT_PATH_REPORT_COMPLETE_NO_PROMOTION",
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "decision": decision,
        "next_allowed_step": next_step,
        "root": str(root),
        "inputs": {
            "db": str(root / args.db),
            "state_db": str(root / args.state_db),
            "stage51_candidates": str(root / args.stage51_candidates),
            "stage54_summary": str(root / args.stage54_summary),
            "config": str(root / args.config),
        },
        "decision_reasons": reasons,
        "stage54_decision": stage54.get("decision") if isinstance(stage54, dict) else None,
        "broker_m15_span": broker,
        "stage51_candidates": candidates,
        "shadow_state": shadow,
        "frequency_prior": prior,
        "config": cfg,
        "generated_utc": utc_now(),
    }
    write_outputs(root / args.out, summary)
    print(json.dumps({"stage": STAGE, "status": summary["status"], "decision": decision, "next_allowed_step": next_step, "out": str(root / args.out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
