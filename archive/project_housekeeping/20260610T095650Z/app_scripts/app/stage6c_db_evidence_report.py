#!/usr/bin/env python3
"""
Stage 6C — DB Evidence Report

Reads the local SQLite evidence store created by Stage 6A/6B and produces a
decision-oriented report.

Hard rules:
- Read-only.
- No CSV import.
- No order sending.
- No demo/paper/live authorization.
- AMarkets/MT5 remains the execution source of truth.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple


TOOL_VERSION = "v1"
STRATEGY_ID = "xauusd_long_tp24_sl15_no_london_v1"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_OUT_DIR = Path("data/reports/stage6c_db_evidence_report")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def safe_float(v, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except Exception:
        return default


def connect_readonly(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite DB not found: {db_path}")
    # Read-only URI prevents accidental mutation.
    uri = f"file:{db_path.resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return row is not None


def count_table(conn: sqlite3.Connection, name: str) -> int:
    if not table_exists(conn, name):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS n FROM {name}").fetchone()["n"])


def bars_by_source_tf(conn: sqlite3.Connection) -> List[dict]:
    if not table_exists(conn, "bars"):
        return []
    rows = conn.execute(
        """
        SELECT source, symbol, timeframe,
               COUNT(*) AS rows,
               MIN(utc_time) AS start_utc,
               MAX(utc_time) AS end_utc
        FROM bars
        GROUP BY source, symbol, timeframe
        ORDER BY source, symbol, timeframe
        """
    ).fetchall()
    return [dict(r) for r in rows]


def latest_bars(conn: sqlite3.Connection, limit_per_tf: int = 3) -> Dict[str, List[dict]]:
    if not table_exists(conn, "bars"):
        return {}
    out: Dict[str, List[dict]] = {}
    groups = conn.execute(
        "SELECT DISTINCT source, symbol, timeframe FROM bars ORDER BY source, symbol, timeframe"
    ).fetchall()
    for g in groups:
        key = f"{g['source']}|{g['symbol']}|{g['timeframe']}"
        rows = conn.execute(
            """
            SELECT utc_time, open, high, low, close, tick_volume, spread
            FROM bars
            WHERE source=? AND symbol=? AND timeframe=?
            ORDER BY utc_time DESC
            LIMIT ?
            """,
            (g["source"], g["symbol"], g["timeframe"], limit_per_tf),
        ).fetchall()
        out[key] = [dict(r) for r in rows]
    return out


def latest_import_runs(conn: sqlite3.Connection, limit: int = 12) -> List[dict]:
    if not table_exists(conn, "import_runs"):
        return []
    rows = conn.execute(
        """
        SELECT id, created_utc, source, dataset, timeframe, rows_seen, rows_inserted,
               rows_bad, start_utc, end_utc, path
        FROM import_runs
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def recent_signals(conn: sqlite3.Connection, limit: int = 20) -> List[dict]:
    if not table_exists(conn, "dryrun_signals"):
        return []
    rows = conn.execute(
        """
        SELECT strategy_id, symbol, signal_closed_h1_utc, session_utc, close_h1,
               sma10, distance_usd, direction, tp_usd, sl_usd, time_exit_h1_bars,
               imported_utc
        FROM dryrun_signals
        ORDER BY signal_closed_h1_utc DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def recent_outcomes(conn: sqlite3.Connection, limit: int = 20) -> List[dict]:
    if not table_exists(conn, "dryrun_outcomes"):
        return []
    rows = conn.execute(
        """
        SELECT strategy_id, symbol, signal_closed_h1_utc, session_utc, status, reason,
               entry_utc, entry_price, exit_utc, exit_price, net_usd_x1,
               m1_bars_checked, imported_utc
        FROM dryrun_outcomes
        ORDER BY signal_closed_h1_utc DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def outcome_summary(conn: sqlite3.Connection) -> dict:
    if not table_exists(conn, "dryrun_outcomes"):
        return {
            "total_outcomes": 0,
            "resolved": 0,
            "open_or_unresolved": 0,
            "total_net_usd": 0.0,
            "avg_net_usd": 0.0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "by_session": [],
            "by_reason": [],
        }

    total = count_table(conn, "dryrun_outcomes")
    rows = conn.execute(
        """
        SELECT status, reason, session_utc, net_usd_x1
        FROM dryrun_outcomes
        """
    ).fetchall()
    resolved_vals = [safe_float(r["net_usd_x1"]) for r in rows if r["status"] == "RESOLVED" and r["net_usd_x1"] is not None]
    wins = sum(1 for v in resolved_vals if v > 0)
    losses = sum(1 for v in resolved_vals if v < 0)
    resolved = len(resolved_vals)
    openish = total - resolved
    total_net = round(sum(resolved_vals), 6)
    avg = round(total_net / resolved, 6) if resolved else 0.0

    by_session_rows = conn.execute(
        """
        SELECT session_utc,
               COUNT(*) AS trades,
               SUM(CASE WHEN status='RESOLVED' THEN 1 ELSE 0 END) AS resolved,
               SUM(CASE WHEN status='RESOLVED' THEN COALESCE(net_usd_x1, 0) ELSE 0 END) AS total_net,
               AVG(CASE WHEN status='RESOLVED' THEN net_usd_x1 ELSE NULL END) AS avg_net
        FROM dryrun_outcomes
        GROUP BY session_utc
        ORDER BY trades DESC, session_utc
        """
    ).fetchall()

    by_reason_rows = conn.execute(
        """
        SELECT reason, COUNT(*) AS trades,
               SUM(CASE WHEN status='RESOLVED' THEN COALESCE(net_usd_x1, 0) ELSE 0 END) AS total_net
        FROM dryrun_outcomes
        GROUP BY reason
        ORDER BY trades DESC, reason
        """
    ).fetchall()

    return {
        "total_outcomes": total,
        "resolved": resolved,
        "open_or_unresolved": openish,
        "total_net_usd": total_net,
        "avg_net_usd": avg,
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / resolved, 6) if resolved else 0.0,
        "by_session": [dict(r) for r in by_session_rows],
        "by_reason": [dict(r) for r in by_reason_rows],
    }


def join_signal_outcome(conn: sqlite3.Connection, limit: int = 20) -> List[dict]:
    if not (table_exists(conn, "dryrun_signals") and table_exists(conn, "dryrun_outcomes")):
        return []
    rows = conn.execute(
        """
        SELECT s.signal_closed_h1_utc, s.symbol, s.session_utc, s.distance_usd,
               s.close_h1, s.sma10, s.direction,
               o.status, o.reason, o.entry_utc, o.entry_price,
               o.exit_utc, o.exit_price, o.net_usd_x1
        FROM dryrun_signals s
        LEFT JOIN dryrun_outcomes o
          ON s.strategy_id=o.strategy_id
         AND s.symbol=o.symbol
         AND s.signal_closed_h1_utc=o.signal_closed_h1_utc
        ORDER BY s.signal_closed_h1_utc DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def no_asia_live_counterfactual(conn: sqlite3.Connection) -> dict:
    """
    Very small live-only counterfactual:
    If a future v2 no_asia guard existed, how many recorded live outcomes would
    have been excluded and what net would have been avoided?
    """
    if not table_exists(conn, "dryrun_outcomes"):
        return {"excluded_trades": 0, "excluded_net_usd": 0.0, "kept_trades": 0, "kept_net_usd": 0.0}
    rows = conn.execute(
        """
        SELECT session_utc, status, COALESCE(net_usd_x1, 0) AS net_usd_x1
        FROM dryrun_outcomes
        WHERE status='RESOLVED'
        """
    ).fetchall()
    excluded = [safe_float(r["net_usd_x1"]) for r in rows if r["session_utc"] == "asia"]
    kept = [safe_float(r["net_usd_x1"]) for r in rows if r["session_utc"] != "asia"]
    return {
        "excluded_trades": len(excluded),
        "excluded_net_usd": round(sum(excluded), 6),
        "kept_trades": len(kept),
        "kept_net_usd": round(sum(kept), 6),
        "note": "Live-only sample. Not statistically sufficient by itself.",
    }


def make_warnings(bars_summary: List[dict], outcome: dict, counter: dict) -> List[str]:
    warnings = []
    if not bars_summary:
        warnings.append("No bars in local DB.")
    for r in bars_summary:
        if r["source"] == "amarkets_mt5" and r["timeframe"] in {"1h", "1m"} and not r.get("end_utc"):
            warnings.append(f"Missing end_utc for {r['source']} {r['timeframe']}.")
    if outcome["total_outcomes"] == 0:
        warnings.append("No dry-run outcomes stored yet.")
    elif outcome["resolved"] < 20:
        warnings.append(f"Only {outcome['resolved']} resolved live dry-run outcome(s); live evidence is still too small for execution decisions.")
    if counter["excluded_trades"] > 0:
        warnings.append(
            f"no_asia counterfactual would have excluded {counter['excluded_trades']} live resolved trade(s), net={counter['excluded_net_usd']}."
        )
    if outcome["open_or_unresolved"] > 0:
        warnings.append(f"{outcome['open_or_unresolved']} outcome(s) are open/unresolved.")
    return warnings


def md_table(headers: List[str], rows: List[List[object]]) -> List[str]:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        out.append("| " + " | ".join("" if x is None else str(x) for x in row) + " |")
    return out


def write_report(out_dir: Path, payload: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "stage6c_db_evidence_report.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    lines: List[str] = [
        "# Stage 6C DB Evidence Report",
        "",
        f"Generated UTC: `{payload['generated_utc']}`",
        f"Tool version: `{payload['tool_version']}`",
        f"DB path: `{payload['db_path']}`",
        "",
        "> Hard rule: read-only evidence report. This does not import data and does not authorize demo, paper, or live orders.",
        "",
        "## DB counts",
    ]
    for k, v in payload["counts"].items():
        lines.append(f"- {k}: `{v}`")

    lines += ["", "## Bars by source/timeframe"]
    lines.extend(md_table(
        ["Source", "Symbol", "TF", "Rows", "Start UTC", "End UTC"],
        [[r.get("source"), r.get("symbol"), r.get("timeframe"), r.get("rows"), r.get("start_utc"), r.get("end_utc")] for r in payload["bars_by_source_tf"]]
    ))

    lines += ["", "## Dry-run outcome summary"]
    osum = payload["outcome_summary"]
    lines += [
        f"- total_outcomes: `{osum['total_outcomes']}`",
        f"- resolved: `{osum['resolved']}`",
        f"- open_or_unresolved: `{osum['open_or_unresolved']}`",
        f"- total_net_usd: `{osum['total_net_usd']}`",
        f"- avg_net_usd: `{osum['avg_net_usd']}`",
        f"- wins: `{osum['wins']}`",
        f"- losses: `{osum['losses']}`",
        f"- win_rate: `{osum['win_rate']}`",
    ]

    lines += ["", "## Outcomes by session"]
    lines.extend(md_table(
        ["Session", "Trades", "Resolved", "Total net", "Avg net"],
        [[r.get("session_utc"), r.get("trades"), r.get("resolved"), round(r.get("total_net") or 0, 6), round(r.get("avg_net") or 0, 6)] for r in osum["by_session"]]
    ))

    lines += ["", "## Outcomes by reason"]
    lines.extend(md_table(
        ["Reason", "Trades", "Total net"],
        [[r.get("reason"), r.get("trades"), round(r.get("total_net") or 0, 6)] for r in osum["by_reason"]]
    ))

    lines += ["", "## no_asia live counterfactual"]
    c = payload["no_asia_counterfactual"]
    lines += [
        f"- excluded_trades: `{c['excluded_trades']}`",
        f"- excluded_net_usd: `{c['excluded_net_usd']}`",
        f"- kept_trades: `{c['kept_trades']}`",
        f"- kept_net_usd: `{c['kept_net_usd']}`",
        f"- note: {c['note']}",
    ]

    lines += ["", "## Recent signal/outcome join"]
    lines.extend(md_table(
        ["Closed H1 UTC", "Session", "Distance", "Status", "Reason", "Entry UTC", "Entry", "Exit UTC", "Exit", "Net"],
        [[r.get("signal_closed_h1_utc"), r.get("session_utc"), r.get("distance_usd"), r.get("status"), r.get("reason"), r.get("entry_utc"), r.get("entry_price"), r.get("exit_utc"), r.get("exit_price"), r.get("net_usd_x1")] for r in payload["recent_signal_outcome"]]
    ))

    lines += ["", "## Latest import runs"]
    lines.extend(md_table(
        ["ID", "Created UTC", "Source", "Dataset", "TF", "Rows seen", "Rows inserted", "Bad", "End UTC"],
        [[r.get("id"), r.get("created_utc"), r.get("source"), r.get("dataset"), r.get("timeframe"), r.get("rows_seen"), r.get("rows_inserted"), r.get("rows_bad"), r.get("end_utc")] for r in payload["latest_import_runs"]]
    ))

    lines += ["", "## Warnings / blockers"]
    if payload["warnings"]:
        for w in payload["warnings"]:
            lines.append(f"- {w}")
    else:
        lines.append("- None.")

    lines += [
        "",
        "## Decision",
        "- Local DB evidence store is readable and decision reports can now be generated from SQLite.",
        "- Live evidence is still too small for any demo/paper/live authorization.",
        "- Current working direction remains: keep v1 dry-run running; evaluate no_asia as v2 candidate in deeper validation.",
    ]

    (out_dir / "stage6c_db_evidence_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    ap.add_argument("--recent-limit", type=int, default=20)
    args = ap.parse_args()

    db_path = Path(args.db)
    conn = connect_readonly(db_path)

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": now_iso(),
        "db_path": str(db_path),
        "counts": {
            "bars": count_table(conn, "bars"),
            "dryrun_signals": count_table(conn, "dryrun_signals"),
            "dryrun_outcomes": count_table(conn, "dryrun_outcomes"),
            "import_runs": count_table(conn, "import_runs"),
        },
        "bars_by_source_tf": bars_by_source_tf(conn),
        "latest_bars": latest_bars(conn),
        "latest_import_runs": latest_import_runs(conn),
        "recent_signals": recent_signals(conn, args.recent_limit),
        "recent_outcomes": recent_outcomes(conn, args.recent_limit),
        "recent_signal_outcome": join_signal_outcome(conn, args.recent_limit),
        "outcome_summary": outcome_summary(conn),
        "no_asia_counterfactual": no_asia_live_counterfactual(conn),
    }
    payload["warnings"] = make_warnings(
        payload["bars_by_source_tf"],
        payload["outcome_summary"],
        payload["no_asia_counterfactual"],
    )

    conn.close()
    write_report(Path(args.out_dir), payload)

    print("Stage 6C DB evidence report: DONE")
    print(f"DB: {db_path}")
    print(f"bars={payload['counts']['bars']} signals={payload['counts']['dryrun_signals']} outcomes={payload['counts']['dryrun_outcomes']}")
    print(f"Report: {Path(args.out_dir) / 'stage6c_db_evidence_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
