#!/usr/bin/env python3
"""
Stage61 Demo Execution Sandbox signal exporter.

Reads Stage58B true-forward shadow state and exports only non-backfill pending
signals to a small CSV file that the MT5 demo-only EA can poll.

This script does NOT connect to a broker and does NOT submit orders.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


STAGE = "Stage61_DEMO_EXECUTION_SANDBOX_EXPORT_NO_PROMOTION"
NO_GO = "NO_GO"


@dataclass
class SignalRow:
    signal_id: str
    candidate_id: str
    base_candidate_id: str
    context_tag: str
    signal_time_utc: str
    entry_time_utc: str
    symbol: str
    side: str
    lot: float
    sl_points: int
    tp_points: int
    max_spread_points: int
    max_hold_minutes: int
    expiry_utc: str
    magic: int
    comment: str


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def connect_readonly(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"state db not found: {db_path}")
    uri = f"file:{db_path}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "select name from sqlite_master where type='table' and name=?", (table,)
    ).fetchone()
    return row is not None


def get_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    return [r[1] for r in conn.execute(f"pragma table_info({table})").fetchall()]


def fetch_pending_signals(conn: sqlite3.Connection, limit: int) -> List[Dict[str, Any]]:
    if not table_exists(conn, "signals"):
        return []
    cols = set(get_columns(conn, "signals"))
    required = {
        "signal_id", "candidate_id", "base_candidate_id", "context_tag", "signal_time_utc",
        "entry_time_utc", "direction", "status", "is_backfill", "horizon_m5_bars",
        "stress_cost_bps", "spread_cost_bps"
    }
    missing = sorted(required - cols)
    if missing:
        raise RuntimeError(f"signals table missing required columns: {missing}")
    rows = conn.execute(
        """
        select signal_id, candidate_id, base_candidate_id, context_tag,
               signal_time_utc, entry_time_utc, direction, horizon_m5_bars,
               stress_cost_bps, spread_cost_bps, params_json, context_json
        from signals
        where coalesce(is_backfill,0)=0
          and status in ('PENDING','pending','OPEN','open','NEW','new')
        order by entry_time_utc asc, signal_id asc
        limit ?
        """,
        (int(limit),),
    ).fetchall()
    names = [
        "signal_id", "candidate_id", "base_candidate_id", "context_tag", "signal_time_utc",
        "entry_time_utc", "direction", "horizon_m5_bars", "stress_cost_bps",
        "spread_cost_bps", "params_json", "context_json"
    ]
    return [dict(zip(names, row)) for row in rows]


def fetch_state_metrics(conn: sqlite3.Connection) -> Dict[str, Any]:
    metrics = {
        "state_db_found": True,
        "schema_ok": table_exists(conn, "signals"),
        "total_signals": 0,
        "backfill_signals": 0,
        "true_forward_signals": 0,
        "pending_signals": 0,
        "evaluated_signals": 0,
    }
    if not table_exists(conn, "signals"):
        metrics["schema_ok"] = False
        return metrics
    try:
        metrics["total_signals"] = int(conn.execute("select count(*) from signals").fetchone()[0] or 0)
        metrics["backfill_signals"] = int(conn.execute("select count(*) from signals where coalesce(is_backfill,0)=1").fetchone()[0] or 0)
        metrics["true_forward_signals"] = int(conn.execute("select count(*) from signals where coalesce(is_backfill,0)=0").fetchone()[0] or 0)
        metrics["pending_signals"] = int(conn.execute("select count(*) from signals where coalesce(is_backfill,0)=0 and status in ('PENDING','pending','OPEN','open','NEW','new')").fetchone()[0] or 0)
        metrics["evaluated_signals"] = int(conn.execute("select count(*) from signals where coalesce(is_backfill,0)=0 and status in ('EVALUATED','evaluated','CLOSED','closed')").fetchone()[0] or 0)
    except sqlite3.Error as exc:
        metrics["schema_ok"] = False
        metrics["error"] = str(exc)
    return metrics


def safe_int(value: Any, default: int) -> int:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return default
        return int(float(value))
    except Exception:
        return default


def safe_float(value: Any, default: float) -> float:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return default
        return float(value)
    except Exception:
        return default


def side_from_direction(direction: Any) -> str:
    s = str(direction or "").strip().lower()
    if s in {"long", "buy", "1", "+1"}:
        return "BUY"
    if s in {"short", "sell", "-1"}:
        return "SELL"
    return "UNKNOWN"


def build_export_rows(raw_rows: List[Dict[str, Any]], cfg: Dict[str, Any]) -> List[SignalRow]:
    symbol = str(cfg.get("symbol", "XAUUSD"))
    lot = safe_float(cfg.get("fixed_lot", 0.01), 0.01)
    sl_points = safe_int(cfg.get("stop_loss_points", 500), 500)
    tp_points = safe_int(cfg.get("take_profit_points", 500), 500)
    max_spread = safe_int(cfg.get("max_spread_points", 60), 60)
    max_hold_minutes = safe_int(cfg.get("max_hold_minutes", 180), 180)
    magic = safe_int(cfg.get("magic_number", 610058), 610058)
    expiry_utc = str(cfg.get("expiry_utc", "")) or utc_now()
    out: List[SignalRow] = []
    for r in raw_rows:
        side = side_from_direction(r.get("direction"))
        if side == "UNKNOWN":
            continue
        sig_id = str(r.get("signal_id", "")).strip()
        if not sig_id:
            continue
        comment = f"S61|{sig_id[:20]}"
        out.append(
            SignalRow(
                signal_id=sig_id,
                candidate_id=str(r.get("candidate_id", "")),
                base_candidate_id=str(r.get("base_candidate_id", "")),
                context_tag=str(r.get("context_tag", "")),
                signal_time_utc=str(r.get("signal_time_utc", "")),
                entry_time_utc=str(r.get("entry_time_utc", "")),
                symbol=symbol,
                side=side,
                lot=lot,
                sl_points=sl_points,
                tp_points=tp_points,
                max_spread_points=max_spread,
                max_hold_minutes=max_hold_minutes,
                expiry_utc=expiry_utc,
                magic=magic,
                comment=comment,
            )
        )
    return out


def write_csv(path: Path, rows: List[SignalRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(SignalRow.__dataclass_fields__.keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow(asdict(row))


def write_report(path: Path, summary: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Stage61 Demo Execution Sandbox Export", "",
        f"- status: `{summary['status']}`",
        f"- decision: `{summary['decision']}`",
        f"- next_allowed_step: `{summary['next_allowed_step']}`",
        f"- promotion: `{summary['promotion']}`",
        f"- EA: `{summary['EA']}`",
        f"- paper_live: `{summary['paper_live']}`",
        f"- live: `{summary['live']}`", "",
        "## Export", "",
        f"- pending_true_forward_signals_seen: `{summary['pending_true_forward_signals_seen']}`",
        f"- exported_demo_signals: `{summary['exported_demo_signals']}`",
        f"- broker_connection: `{summary['broker_connection']}`",
        f"- live_block: `{summary['live_block']}`", "",
        "## Files", "",
        f"- export_csv: `{summary['outputs']['export_csv']}`",
        f"- mt5_copy_csv: `{summary['outputs']['mt5_copy_csv']}`", "",
        "## Interpretation", "",
        "Stage61 exports tiny-risk demo sandbox signals only. It does not validate statistical edge and does not authorize paper-live, live trading, or broker connection outside a demo-only harness.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--state-db", default="data/shadow/stage58b_context_forward_shadow.sqlite")
    ap.add_argument("--config", default="configs/stage61_demo_execution_sandbox.json")
    ap.add_argument("--out", default="reports/stage61_demo_execution_sandbox")
    ap.add_argument("--max-signals", type=int, default=None)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    state_db = (root / args.state_db).resolve()
    cfg_path = (root / args.config).resolve()
    out_dir = (root / args.out).resolve()
    cfg = load_json(cfg_path, {}) or {}
    max_signals = int(args.max_signals if args.max_signals is not None else cfg.get("max_export_signals", 3))

    checks: List[Dict[str, Any]] = []
    pending: List[Dict[str, Any]] = []
    metrics: Dict[str, Any] = {"state_db_found": state_db.exists(), "schema_ok": False}
    error: Optional[str] = None

    try:
        with connect_readonly(state_db) as conn:
            metrics = fetch_state_metrics(conn)
            pending = fetch_pending_signals(conn, max_signals)
            checks.append({"check": "state_db_readable", "passed": True, "observed": str(state_db)})
            checks.append({"check": "signals_schema_ok", "passed": bool(metrics.get("schema_ok")), "observed": metrics})
    except Exception as exc:
        error = str(exc)
        checks.append({"check": "state_db_readable", "passed": False, "observed": error})

    export_rows = build_export_rows(pending, cfg) if error is None else []
    export_csv = out_dir / "stage61_demo_signal_export.csv"
    mt5_copy_csv = out_dir / "stage61_mt5_files_stage61_demo_signals.csv"
    write_csv(export_csv, export_rows)
    write_csv(mt5_copy_csv, export_rows)

    status = "DEMO_SIGNAL_EXPORT_READY_NO_PROMOTION" if export_rows else "DEMO_SIGNAL_EXPORT_EMPTY_WAIT_FOR_FORWARD_SIGNALS_NO_PROMOTION"
    decision = "DEMO_SANDBOX_EXPORT_READY_NO_EDGE_PROMOTION" if export_rows else "WAIT_FOR_STAGE58B_TRUE_FORWARD_SIGNALS_NO_PROMOTION"
    summary: Dict[str, Any] = {
        "stage": STAGE,
        "status": status,
        "promotion": NO_GO,
        "EA": "DEMO_HARNESS_ONLY_NO_LIVE",
        "paper_live": NO_GO,
        "live": NO_GO,
        "decision": decision,
        "next_allowed_step": "COPY_EXPORT_TO_MT5_FILES_AND_RUN_DEMO_EA_ONLY" if export_rows else "CONTINUE_STAGE58B_FORWARD_SHADOW_NO_DEMO_ORDERS_YET",
        "root": str(root),
        "state_db": str(state_db),
        "config": str(cfg_path),
        "metrics": metrics,
        "pending_true_forward_signals_seen": len(pending),
        "exported_demo_signals": len(export_rows),
        "broker_connection": "DISABLED_IN_PYTHON_EXPORTER_DEMO_EA_ONLY",
        "live_block": True,
        "error": error,
        "checks": checks,
        "outputs": {
            "export_csv": str(export_csv),
            "mt5_copy_csv": str(mt5_copy_csv),
            "report": str(out_dir / "stage61_demo_signal_export_report.md"),
        },
        "generated_utc": utc_now(),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "stage61_demo_signal_export_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report(out_dir / "stage61_demo_signal_export_report.md", summary)


if __name__ == "__main__":
    main()
