#!/usr/bin/env python3
"""
Stage175B — dual-source parity repair for the exact locked T1 refresh.

This is an integration repair, not a new research stage.

Why it exists
-------------
Stage175 compared the archived Stage38A expected metrics with trades rebuilt
from the latest AMarkets CSV. That CSV is not the exact historical input used
by Stage38A, so a parity failure could reflect source drift rather than an
engine mismatch.

Stage175B therefore:
1. loads the exact archived SQLite H1 bars + macro table for engine parity;
2. optionally compares regenerated parity trades with the archived Stage38A
   trade ledger;
3. aligns the current AMarkets CSV to the archived broker-time contract using
   OHLC fingerprinting over integer-hour shifts;
4. uses the aligned current CSV only for the final locked 20% holdout refresh.

No order, demo, paper, live, ML, broad scan, or threshold optimization path.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

BASE_PATH = Path(__file__).with_name("stage175_h64l_closeout_and_t1_locked_holdout_refresh.py")
_spec = importlib.util.spec_from_file_location("stage175_base_for_175b", BASE_PATH)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"Cannot load Stage175 base module: {BASE_PATH}")
base = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = base
_spec.loader.exec_module(base)

Bar = base.Bar
STAGE = "Stage175B_DUAL_SOURCE_PARITY_REPAIR"


def load_h1_db(path: Path, source: str, symbol: str, timeframe: str) -> List[Bar]:
    """Load the exact archived broker bars used by Stage38A."""
    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        if not base.table_exists(conn, "bars"):
            raise ValueError(f"bars table missing in {path}")
        cols = set(base.table_columns(conn, "bars"))
        required = {"utc_time", "open", "high", "low", "close", "source", "symbol", "timeframe"}
        missing = sorted(required - cols)
        if missing:
            raise ValueError(f"bars missing columns {missing} in {path}")
        rows = conn.execute(
            """
            select utc_time, open, high, low, close
            from bars
            where source=? and symbol=? and timeframe=?
            order by utc_time
            """,
            (source, symbol, timeframe),
        ).fetchall()
    finally:
        conn.close()

    by_time: Dict[datetime, Tuple[float, float, float, float]] = {}
    for row_num, row in enumerate(rows, start=1):
        ts = base.parse_dt(row[0])
        o, h, l, c = map(float, row[1:5])
        if not (l <= min(o, c) <= max(o, c) <= h):
            raise ValueError(f"Archived H1 OHLC invariant failed at result row {row_num}")
        by_time[ts] = (o, h, l, c)
    bars = [
        Bar(idx=i, utc_time=ts, open=v[0], high=v[1], low=v[2], close=v[3])
        for i, (ts, v) in enumerate(sorted(by_time.items()))
    ]
    if not bars:
        raise ValueError(
            f"No archived bars for source={source} symbol={symbol} timeframe={timeframe} in {path}"
        )
    return bars


def clone_shift_bars(bars: Sequence[Bar], shift_hours: int) -> List[Bar]:
    shift = timedelta(hours=int(shift_hours))
    return [
        Bar(
            idx=i,
            utc_time=b.utc_time + shift,
            open=b.open,
            high=b.high,
            low=b.low,
            close=b.close,
        )
        for i, b in enumerate(bars)
    ]


def alignment_scores(
    current_bars: Sequence[Bar],
    archived_bars: Sequence[Bar],
    shifts_hours: Sequence[int],
    price_tolerance: float,
) -> List[Dict[str, Any]]:
    ref = {b.utc_time: b for b in archived_bars}
    rows: List[Dict[str, Any]] = []
    for shift in shifts_hours:
        diffs_close: List[float] = []
        exact = 0
        overlap = 0
        delta = timedelta(hours=int(shift))
        for cur in current_bars:
            old = ref.get(cur.utc_time + delta)
            if old is None:
                continue
            overlap += 1
            diffs = [
                abs(cur.open - old.open),
                abs(cur.high - old.high),
                abs(cur.low - old.low),
                abs(cur.close - old.close),
            ]
            diffs_close.append(diffs[-1])
            if max(diffs) <= price_tolerance:
                exact += 1
        ordered = sorted(diffs_close)
        median = ordered[len(ordered)//2] if ordered else None
        p90 = ordered[min(len(ordered)-1, int(math.floor((len(ordered)-1)*0.90)))] if ordered else None
        rows.append({
            "shift_hours_applied_to_current_csv": int(shift),
            "overlap_rows": overlap,
            "ohlc_match_rows": exact,
            "ohlc_match_share": exact / overlap if overlap else 0.0,
            "median_abs_close_difference": median,
            "p90_abs_close_difference": p90,
        })
    return sorted(
        rows,
        key=lambda r: (
            float(r["ohlc_match_share"]),
            int(r["overlap_rows"]),
            -float(r["median_abs_close_difference"] if r["median_abs_close_difference"] is not None else 1e99),
        ),
        reverse=True,
    )


def resolve_alignment(
    score_rows: Sequence[Dict[str, Any]],
    min_overlap_rows: int,
    min_match_share: float,
    min_lead_share: float,
) -> Dict[str, Any]:
    if not score_rows:
        return {"pass": False, "reason": "NO_ALIGNMENT_SCORES"}
    best = dict(score_rows[0])
    runner = dict(score_rows[1]) if len(score_rows) > 1 else None
    lead = (
        float(best["ohlc_match_share"]) -
        float(runner["ohlc_match_share"] if runner else 0.0)
    )
    checks = {
        "min_overlap_rows": int(best["overlap_rows"]) >= int(min_overlap_rows),
        "min_match_share": float(best["ohlc_match_share"]) >= float(min_match_share),
        "unique_lead": lead >= float(min_lead_share),
    }
    return {
        "pass": all(checks.values()),
        "checks": checks,
        "best": best,
        "runner_up": runner,
        "lead_share": lead,
        "resolved_shift_hours": int(best["shift_hours_applied_to_current_csv"]),
    }


def resolve_optional(root: Path, candidates: Sequence[str], glob_pattern: Optional[str]) -> Optional[Path]:
    for item in candidates:
        p = Path(item).expanduser()
        if not p.is_absolute():
            p = root / p
        if p.exists():
            return p.resolve()
    if glob_pattern:
        hits = sorted(root.glob(glob_pattern))
        if hits:
            return hits[0].resolve()
    return None


def load_archived_locked_ledger(
    path: Path,
    cfg: Dict[str, Any],
    reference_end: datetime,
) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    target = str(cfg["locked_variant_id"])
    selected: List[Dict[str, Any]] = []
    for row in rows:
        if row.get("variant_id") != target:
            continue
        d1_close = base.safe_float(row.get("d1_close"))
        d1_ma = base.safe_float(row.get("d1_ma50"))
        h4_close = base.safe_float(row.get("h4_close"))
        h4_ma = base.safe_float(row.get("h4_ma50"))
        atr = base.safe_float(row.get("atr_h1_14"))
        entry = base.safe_float(row.get("entry_price"))
        if None in (d1_close, d1_ma, h4_close, h4_ma, atr, entry) or d1_ma == 0 or h4_ma == 0 or entry == 0:
            continue
        locked = (
            (d1_close - d1_ma) / d1_ma >= float(cfg["locked_d1_trend_pct_min"]) and
            (h4_close - h4_ma) / h4_ma >= float(cfg["locked_h4_trend_pct_min"]) and
            atr / entry >= float(cfg["locked_atr_pct_price_min"])
        )
        signal = base.parse_dt(row.get("signal_utc") or row.get("entry_utc") or "")
        if locked and signal <= reference_end:
            selected.append({
                "signal_utc": signal.isoformat(),
                "entry_utc": row.get("entry_utc", ""),
                "r_stress_p90": float(row["r_stress_p90"]),
                "trade_id": row.get("trade_id", ""),
            })
    selected.sort(key=lambda r: r["signal_utc"])
    return selected


def trade_identity(row: Dict[str, Any]) -> str:
    return str(row.get("signal_utc") or row.get("entry_utc") or "")


def compare_trade_sets(
    generated: Sequence[Dict[str, Any]],
    archived: Sequence[Dict[str, Any]],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    g = {trade_identity(r): r for r in generated}
    a = {trade_identity(r): r for r in archived}
    union = set(g) | set(a)
    common = set(g) & set(a)
    diff_rows: List[Dict[str, Any]] = []
    for key in sorted(union):
        gr = g.get(key)
        ar = a.get(key)
        diff_rows.append({
            "signal_utc": key,
            "in_generated": gr is not None,
            "in_archived_ledger": ar is not None,
            "generated_r_stress_p90": gr.get("r_stress_p90") if gr else None,
            "archived_r_stress_p90": ar.get("r_stress_p90") if ar else None,
            "abs_r_difference": (
                abs(float(gr["r_stress_p90"]) - float(ar["r_stress_p90"]))
                if gr is not None and ar is not None else None
            ),
        })
    common_r = [r for r in diff_rows if r["in_generated"] and r["in_archived_ledger"]]
    max_r_diff = max([float(r["abs_r_difference"]) for r in common_r] or [0.0])
    metrics = {
        "generated_count": len(g),
        "archived_count": len(a),
        "common_count": len(common),
        "missing_from_generated": len(set(a) - set(g)),
        "extra_in_generated": len(set(g) - set(a)),
        "jaccard": len(common) / len(union) if union else 1.0,
        "max_common_abs_r_difference": max_r_diff,
    }
    return metrics, diff_rows


def ledger_parity_pass(metrics: Dict[str, Any], cfg: Dict[str, Any]) -> bool:
    return (
        float(metrics["jaccard"]) >= float(cfg["min_trade_jaccard"]) and
        int(metrics["missing_from_generated"]) <= int(cfg["max_missing_trades"]) and
        int(metrics["extra_in_generated"]) <= int(cfg["max_extra_trades"]) and
        float(metrics["max_common_abs_r_difference"]) <= float(cfg["max_common_abs_r_difference"])
    )


def reset_derived(bars: Sequence[Bar]) -> None:
    # Defensive helper for repeated tests/runs.
    for b in bars:
        b.atr_h1_14 = None
        b.previous_day_high = None
        b.d1_close = None
        b.d1_ma50 = None
        b.h4_close = None
        b.h4_ma50 = None
        b.macro_regime = None
        b.macro_score_long_gold = None
        b.d_real_yield_20d = None
        b.d_usd_20d_pct = None


def prepare_and_generate(
    bars: List[Bar],
    macro: Sequence[Any],
    cfg: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, int], Dict[str, Any]]:
    reset_derived(bars)
    base.compute_atr(bars, int(cfg["atr_period"]))
    context = base.attach_context(bars, list(macro), cfg)
    trades, skips = base.generate_exact_lead_trades(bars, cfg)
    return trades, skips, context


def decision_markdown(summary: Dict[str, Any]) -> str:
    t1 = summary.get("t1_locked_refresh", {})
    parity = t1.get("parity", {"pass": False})
    align = summary.get("source_alignment", {"pass": False})
    return "\n".join([
        "# Stage175B Decision",
        "",
        f"Generated: {summary['generated_utc']}",
        "",
        "## Hard controls",
        "",
        "- Orders/demo/live/paper-order: forbidden.",
        "- ML, broad scan and threshold reoptimization: forbidden.",
        "",
        "## H64L",
        "",
        "**`KILL_COMMERCIAL_RESCUE_CLOSE_H64L_SIGNAL_PATH`**",
        "",
        "## Dual-source repair",
        "",
        f"Archived engine parity: `{parity['pass']}`",
        "",
        f"Current CSV source alignment: `{align['pass']}`",
        "",
        f"Resolved current CSV shift: `{align.get('resolved_shift_hours')}` hours",
        "",
        "## Exact locked T1 refresh",
        "",
        f"**Decision: `{t1['decision']}`**",
        "",
        f"Holdout cutoff: `{t1.get('holdout_cutoff_utc')}`",
        "",
        f"Locked holdout trades: `{t1.get('locked_holdout_metrics', {}).get('trades')}`",
        "",
        f"Locked holdout PF: `{base.clean(t1.get('locked_holdout_metrics', {}).get('profit_factor'))}`",
        "",
        f"Locked holdout avg R: `{base.clean(t1.get('locked_holdout_metrics', {}).get('avg_R'))}`",
        "",
        "## Program decision",
        "",
        f"**`{summary['program_decision']}`**",
        "",
        "No execution bridge is authorized.",
        "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", required=True)
    parser.add_argument("--h1")
    parser.add_argument("--archive-db")
    parser.add_argument("--out")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    config_path = Path(args.config).expanduser()
    if not config_path.is_absolute():
        config_path = root / config_path
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    out_dir = Path(args.out).expanduser().resolve() if args.out else root / cfg["output_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = base.now_utc_iso()

    outputs = {
        "summary_json": out_dir / "stage175b_summary.json",
        "decision_md": out_dir / "stage175b_decision.md",
        "h64l_closeout_json": out_dir / "stage175b_h64l_closeout.json",
        "locked_trades_csv": out_dir / "stage175b_t1_locked_trades.csv",
        "raw_trades_csv": out_dir / "stage175b_t1_raw_comparator_trades.csv",
        "period_metrics_csv": out_dir / "stage175b_t1_period_metrics.csv",
        "gate_checks_csv": out_dir / "stage175b_t1_gate_checks.csv",
        "alignment_scores_csv": out_dir / "stage175b_source_alignment_scores.csv",
        "parity_diff_csv": out_dir / "stage175b_archived_parity_trade_diff.csv",
        "archived_parity_trades_csv": out_dir / "stage175b_archived_engine_parity_trades.csv",
    }

    hard = {
        "orders_allowed": False,
        "demo_allowed": False,
        "live_allowed": False,
        "paper_order_allowed": False,
        "ml_allowed": False,
        "broad_scan_allowed": False,
        "threshold_reoptimization_allowed": False,
    }
    h64l_closeout = {
        "source_stage": "Stage174",
        "decision": "KILL_COMMERCIAL_RESCUE_CLOSE_H64L_SIGNAL_PATH",
        "ops_policy": (
            "PRESERVE_GENERIC_MACRO_EVENT_DATA_PIPELINE; "
            "H64L_SIGNAL_OUTPUT_IS_INERT_AND_MUST_NOT_OPEN_PROMOTION_OR_EXECUTION_GATES"
        ),
        "orders_allowed": False,
    }
    base.json_dump(outputs["h64l_closeout_json"], h64l_closeout)

    summary: Dict[str, Any]
    exit_code = 0
    try:
        h1_path = base.resolve_existing(root, args.h1, cfg["h1_candidates"])
        archive_db = base.resolve_existing(
            root,
            args.archive_db,
            cfg["archive_db_candidates"],
            cfg.get("archive_db_glob"),
        )
        macro = base.load_macro_db(archive_db)
        archived_bars = load_h1_db(
            archive_db,
            str(cfg["archive_bar_contract"]["source"]),
            str(cfg["archive_bar_contract"]["symbol"]),
            str(cfg["archive_bar_contract"]["timeframe"]),
        )
        current_raw = base.load_h1_csv(h1_path)

        if len(archived_bars) < int(cfg["minimum_archived_h1_rows"]):
            raise ValueError(
                f"Archived H1 rows {len(archived_bars)} < minimum {cfg['minimum_archived_h1_rows']}"
            )
        if len(current_raw) < int(cfg["minimum_current_h1_rows"]):
            raise ValueError(
                f"Current H1 rows {len(current_raw)} < minimum {cfg['minimum_current_h1_rows']}"
            )

        shifts = [int(x) for x in cfg["alignment"]["candidate_shift_hours"]]
        score_rows = alignment_scores(
            current_raw,
            archived_bars,
            shifts,
            float(cfg["alignment"]["price_tolerance"]),
        )
        alignment = resolve_alignment(
            score_rows,
            int(cfg["alignment"]["min_overlap_rows"]),
            float(cfg["alignment"]["min_ohlc_match_share"]),
            float(cfg["alignment"]["min_lead_share"]),
        )
        base.write_csv(outputs["alignment_scores_csv"], score_rows)
        if not alignment["pass"]:
            raise ValueError(f"CURRENT_CSV_ARCHIVED_SOURCE_ALIGNMENT_FAILED:{alignment}")

        current_bars = clone_shift_bars(
            current_raw,
            int(alignment["resolved_shift_hours"]),
        )

        # Exact engine parity is always run on the archived Stage38A input source.
        archived_trades, archived_skips, archived_context = prepare_and_generate(
            archived_bars, macro, cfg
        )
        reference_end = base.parse_dt(cfg["parity"]["reference_end_utc"])
        generated_reference = [
            t for t in archived_trades
            if t["locked_filter_pass"] and base.parse_dt(t["signal_utc"]) <= reference_end
        ]
        parity = base.compare_parity(base.metrics(generated_reference), cfg["parity"])
        base.write_csv(outputs["archived_parity_trades_csv"], generated_reference)

        ledger_path = resolve_optional(
            root,
            cfg["archived_ledger_candidates"],
            cfg.get("archived_ledger_glob"),
        )
        ledger_comparison: Dict[str, Any] = {
            "available": False,
            "pass": None,
            "path": None,
        }
        diff_rows: List[Dict[str, Any]] = []
        if ledger_path is not None:
            archived_ledger = load_archived_locked_ledger(
                ledger_path, cfg, reference_end
            )
            ledger_metrics, diff_rows = compare_trade_sets(
                generated_reference, archived_ledger
            )
            ledger_ok = ledger_parity_pass(
                ledger_metrics, cfg["archived_ledger_parity"]
            )
            ledger_comparison = {
                "available": True,
                "pass": ledger_ok,
                "path": str(ledger_path),
                "sha256": base.sha256_file(ledger_path),
                **ledger_metrics,
            }
            parity["archived_ledger_comparison"] = ledger_comparison
            parity["pass"] = bool(parity["pass"] and ledger_ok)
        else:
            parity["archived_ledger_comparison"] = ledger_comparison
        base.write_csv(outputs["parity_diff_csv"], diff_rows)

        # Current holdout is evaluated only after its timestamps have been
        # reconciled against the archived broker source.
        current_trades, current_skips, current_context = prepare_and_generate(
            current_bars, macro, cfg
        )
        raw_trades = current_trades
        locked_trades = [t for t in current_trades if t["locked_filter_pass"]]

        split_idx = max(
            1,
            min(
                len(current_bars) - 1,
                int(math.floor(
                    len(current_bars) * (1.0 - float(cfg["holdout_fraction"]))
                )),
            ),
        )
        cutoff = current_bars[split_idx].utc_time
        raw_dev = [t for t in raw_trades if base.parse_dt(t["signal_utc"]) < cutoff]
        raw_hold = [t for t in raw_trades if base.parse_dt(t["signal_utc"]) >= cutoff]
        locked_dev = [t for t in locked_trades if base.parse_dt(t["signal_utc"]) < cutoff]
        locked_hold = [t for t in locked_trades if base.parse_dt(t["signal_utc"]) >= cutoff]

        m_raw_dev = base.metrics(raw_dev)
        m_raw_hold = base.metrics(raw_hold)
        m_locked_dev = base.metrics(locked_dev)
        m_locked_hold = base.metrics(locked_hold)
        decision, gates = base.evaluate_decision(
            parity, m_locked_hold, m_raw_hold, cfg["gates"]
        )

        base.write_csv(outputs["locked_trades_csv"], locked_trades)
        base.write_csv(outputs["raw_trades_csv"], raw_trades)
        period_rows = [
            {"population": "RAW", "period": "DEVELOPMENT", **{
                k: v for k, v in m_raw_dev.items() if k not in ("monthly", "yearly")
            }},
            {"population": "RAW", "period": "HOLDOUT", **{
                k: v for k, v in m_raw_hold.items() if k not in ("monthly", "yearly")
            }},
            {"population": "LOCKED", "period": "DEVELOPMENT", **{
                k: v for k, v in m_locked_dev.items() if k not in ("monthly", "yearly")
            }},
            {"population": "LOCKED", "period": "HOLDOUT", **{
                k: v for k, v in m_locked_hold.items() if k not in ("monthly", "yearly")
            }},
        ]
        base.write_csv(outputs["period_metrics_csv"], period_rows)
        base.write_csv(
            outputs["gate_checks_csv"],
            [{"gate": k, "pass": v} for k, v in gates.items()],
        )

        program = (
            "CLOSE_H64L_AND_PROMOTE_T1_TO_SHADOW_LOG_ONLY_NO_ORDER"
            if decision == "SHADOW_CANDIDATE_LOG_ONLY_NO_ORDER"
            else "CLOSE_H64L_AND_KILL_LOCKED_T1_NO_ML_REQUIRE_NEW_CAUSAL_THESIS"
            if decision.startswith("KILL")
            else "CLOSE_H64L_BLOCK_T1_PENDING_DUAL_SOURCE_PARITY_REPAIR_NO_NEW_SCAN"
        )
        summary = {
            "stage": STAGE,
            "generated_utc": generated,
            "root": str(root),
            "hard_controls": hard,
            "inputs": {
                "current_h1": str(h1_path),
                "current_h1_sha256": base.sha256_file(h1_path),
                "current_h1_rows_raw": len(current_raw),
                "current_h1_rows_aligned": len(current_bars),
                "current_h1_min_utc_aligned": current_bars[0].utc_time.isoformat(),
                "current_h1_max_utc_aligned": current_bars[-1].utc_time.isoformat(),
                "archive_db": str(archive_db),
                "archive_db_sha256": base.sha256_file(archive_db),
                "archived_h1_rows": len(archived_bars),
                "archived_h1_min_utc": archived_bars[0].utc_time.isoformat(),
                "archived_h1_max_utc": archived_bars[-1].utc_time.isoformat(),
                "macro_rows": len(macro),
            },
            "source_alignment": alignment,
            "h64l_closeout": h64l_closeout,
            "t1_locked_contract": {
                "variant_id": cfg["locked_variant_id"],
                "target_R": cfg["target_r"],
                "time_stop_h1_bars": cfg["time_stop_h1_bars"],
                "locked_d1_trend_pct_min": cfg["locked_d1_trend_pct_min"],
                "locked_h4_trend_pct_min": cfg["locked_h4_trend_pct_min"],
                "locked_atr_pct_price_min": cfg["locked_atr_pct_price_min"],
                "stress_spread_points": cfg["stress_spread_points"],
                "point_size": cfg["point_size"],
            },
            "t1_locked_refresh": {
                "status": "COMPLETE",
                "decision": decision,
                "holdout_fraction": cfg["holdout_fraction"],
                "holdout_cutoff_utc": cutoff.isoformat(),
                "archived_context": archived_context,
                "current_context": current_context,
                "archived_skip_counts": archived_skips,
                "current_skip_counts": current_skips,
                "raw_development_metrics": m_raw_dev,
                "raw_holdout_metrics": m_raw_hold,
                "locked_development_metrics": m_locked_dev,
                "locked_holdout_metrics": m_locked_hold,
                "parity": parity,
                "gates": gates,
            },
            "outputs": {k: str(v) for k, v in outputs.items()},
            "program_decision": program,
        }
    except Exception as exc:
        exit_code = 2
        summary = {
            "stage": STAGE,
            "generated_utc": generated,
            "root": str(root),
            "hard_controls": hard,
            "h64l_closeout": h64l_closeout,
            "source_alignment": locals().get(
                "alignment",
                {"pass": False, "reason": "NOT_COMPLETED"},
            ),
            "t1_locked_refresh": {
                "status": "BLOCKED",
                "decision": "INCONCLUSIVE_BLOCKED_DUAL_SOURCE_PARITY_REPAIR_FAILED",
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
            "outputs": {k: str(v) for k, v in outputs.items()},
            "program_decision": (
                "CLOSE_H64L_BLOCK_T1_PENDING_DUAL_SOURCE_PARITY_REPAIR_NO_NEW_SCAN"
            ),
        }

    base.json_dump(outputs["summary_json"], summary)
    outputs["decision_md"].write_text(
        decision_markdown(summary),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
