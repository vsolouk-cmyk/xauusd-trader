#!/usr/bin/env python3
"""
Stage 9B — Macro Numeric Artifact Importer v2

Fix:
- Handles existing SQLite databases where macro_numeric_observations was created
  before the ssl_mode column existed.
- Adds missing columns safely via PRAGMA table_info + ALTER TABLE.

Purpose:
- Import macro numeric CSV artifacts produced by GitHub Actions into local SQLite.
- GitHub fetches data; local imports artifact.

Expected input:
- data/macro/macro_numeric_observations.csv
or a custom CSV path.

Writes:
- data/local/xauusd_local_store.sqlite
  table: macro_numeric_observations
  table: macro_update_runs

Hard rules:
- Data import only.
- No trading signal.
- No EA change.
- No order/demo/paper/live authorization.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


TOOL_VERSION = "v2_schema_fix"
DEFAULT_CSV = Path("data/macro/macro_numeric_observations.csv")
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_REPORT_DIR = Path("data/reports/stage9b_macro_artifact_import")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def safe_float(v) -> Optional[float]:
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.lower() == "none":
        return None
    try:
        return float(s)
    except Exception:
        return None


def read_rows(path: Path) -> List[Dict]:
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if not text.strip():
        return []
    return list(csv.DictReader(text.splitlines()))


def table_columns(conn: sqlite3.Connection, table: str) -> set:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def ensure_tables(conn: sqlite3.Connection) -> List[str]:
    migrations: List[str] = []

    conn.execute("""
        CREATE TABLE IF NOT EXISTS macro_numeric_observations (
            source TEXT NOT NULL,
            series_id TEXT NOT NULL,
            obs_date TEXT NOT NULL,
            value REAL,
            realtime_start TEXT,
            realtime_end TEXT,
            label TEXT,
            category TEXT,
            gold_driver TEXT,
            update_frequency TEXT,
            units_hint TEXT,
            fetched_utc TEXT,
            ssl_mode TEXT,
            PRIMARY KEY (source, series_id, obs_date, realtime_start, realtime_end)
        )
    """)

    cols = table_columns(conn, "macro_numeric_observations")
    if "ssl_mode" not in cols:
        conn.execute("ALTER TABLE macro_numeric_observations ADD COLUMN ssl_mode TEXT")
        migrations.append("Added macro_numeric_observations.ssl_mode")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS macro_update_runs (
            run_id TEXT PRIMARY KEY,
            tool_version TEXT,
            source TEXT,
            status TEXT,
            series_requested INTEGER,
            series_ok INTEGER,
            observations_written INTEGER,
            generated_utc TEXT,
            message TEXT
        )
    """)
    conn.commit()
    return migrations


def import_rows(conn: sqlite3.Connection, rows: List[Dict]) -> int:
    n = 0
    for r in rows:
        source = (r.get("source") or "FRED").strip()
        series_id = (r.get("series_id") or "").strip()
        obs_date = (r.get("date") or r.get("obs_date") or "").strip()
        if not series_id or not obs_date:
            continue

        conn.execute("""
            INSERT OR REPLACE INTO macro_numeric_observations (
                source, series_id, obs_date, value, realtime_start, realtime_end,
                label, category, gold_driver, update_frequency, units_hint, fetched_utc, ssl_mode
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            source,
            series_id,
            obs_date,
            safe_float(r.get("value")),
            (r.get("realtime_start") or "").strip(),
            (r.get("realtime_end") or "").strip(),
            (r.get("label") or "").strip(),
            (r.get("category") or "").strip(),
            (r.get("gold_driver") or "").strip(),
            (r.get("update_frequency") or "").strip(),
            (r.get("units_hint") or "").strip(),
            (r.get("fetched_utc") or "").strip(),
            (r.get("ssl_mode") or "github_artifact").strip(),
        ))
        n += 1
    conn.commit()
    return n


def summarize(conn: sqlite3.Connection) -> List[Dict]:
    rows = conn.execute("""
        SELECT
            source,
            series_id,
            COUNT(*) AS observations,
            MIN(obs_date) AS first_date,
            MAX(obs_date) AS latest_date
        FROM macro_numeric_observations
        GROUP BY source, series_id
        ORDER BY source, series_id
    """).fetchall()

    out = []
    for r in rows:
        latest_val = conn.execute("""
            SELECT value FROM macro_numeric_observations
            WHERE source=? AND series_id=? AND obs_date=?
            ORDER BY realtime_end DESC
            LIMIT 1
        """, (r["source"], r["series_id"], r["latest_date"])).fetchone()
        out.append({
            "source": r["source"],
            "series_id": r["series_id"],
            "observations": r["observations"],
            "first_date": r["first_date"],
            "latest_date": r["latest_date"],
            "latest_value": latest_val["value"] if latest_val else None,
        })
    return out


def write_csv(path: Path, rows: List[Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = list(rows[0].keys()) if rows else ["empty"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def run(csv_path: Path, db_path: Path, report_dir: Path) -> int:
    report_dir.mkdir(parents=True, exist_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    generated = now_iso()
    rows = read_rows(csv_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    migrations = ensure_tables(conn)
    written = import_rows(conn, rows)
    series_summary = summarize(conn)

    run_id = f"stage9b_artifact_import_{generated}"
    conn.execute("""
        INSERT OR REPLACE INTO macro_update_runs (
            run_id, tool_version, source, status, series_requested, series_ok,
            observations_written, generated_utc, message
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_id,
        TOOL_VERSION,
        "github_artifact_csv",
        "ok",
        len(set((r.get("series_id") or "").strip() for r in rows if (r.get("series_id") or "").strip())),
        len(series_summary),
        written,
        generated,
        f"Imported from {csv_path}; migrations={'; '.join(migrations) if migrations else 'none'}",
    ))
    conn.commit()
    conn.close()

    write_csv(report_dir / "macro_artifact_import_series_summary.csv", series_summary)

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "status": "ok",
        "csv_path": str(csv_path),
        "db_path": str(db_path),
        "rows_read": len(rows),
        "rows_written": written,
        "series_count": len(series_summary),
        "migrations": migrations,
        "series_summary": series_summary,
    }
    (report_dir / "macro_artifact_import.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Stage 9B Macro Numeric Artifact Import",
        "",
        f"Generated UTC: `{generated}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "## Status",
        f"- status: `ok`",
        f"- csv_path: `{csv_path}`",
        f"- db_path: `{db_path}`",
        f"- rows_read: `{len(rows)}`",
        f"- rows_written: `{written}`",
        f"- series_count: `{len(series_summary)}`",
        f"- migrations: `{'; '.join(migrations) if migrations else 'none'}`",
        "",
        "## Series summary",
        "| Source | Series | Observations | First date | Latest date | Latest value |",
        "|---|---|---:|---|---|---:|",
    ]
    for r in series_summary:
        lines.append(f"| {r['source']} | {r['series_id']} | {r['observations']} | {r['first_date']} | {r['latest_date']} | {r['latest_value']} |")
    lines += [
        "",
        "## Decision",
        "- Data imported into local SQLite.",
        "- No EA/order workflow changes are authorized.",
    ]
    (report_dir / "macro_artifact_import.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 9B macro numeric artifact import: DONE")
    print(f"rows_read={len(rows)} rows_written={written} series={len(series_summary)}")
    print(f"migrations={'; '.join(migrations) if migrations else 'none'}")
    print(f"Report: {report_dir / 'macro_artifact_import.md'}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default=str(DEFAULT_CSV))
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    args = p.parse_args()
    return run(Path(args.csv), Path(args.db), Path(args.report_dir))


if __name__ == "__main__":
    raise SystemExit(main())
