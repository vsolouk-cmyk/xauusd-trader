#!/usr/bin/env python3
"""
Stage 12A v2 — Consolidated Forward-Shadow Report with Input Resilience

v2 fixes:
- Adds input completeness audit.
- Scans fallback report paths instead of relying on one exact directory.
- Reads macro context directly from local SQLite when report files are missing.
- Reads Stage 10E policy from fallback locations; if missing, falls back to Stage 10D validation summary.
- Allows explicit MT5/EA long-signal CSV path with --long-signal-csv or XAUUSD_LONG_SIGNAL_CSV.

Hard rules:
- Report only.
- No EA change.
- No automatic trading.
- No demo/paper/live/order authorization.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd


TOOL_VERSION = "v2_input_resilience"
DEFAULT_OUT_DIR = Path("data/reports/stage12a_consolidated_forward_shadow_report")
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def first_existing(paths: Iterable[Path]) -> Optional[Path]:
    for p in paths:
        if p and p.exists():
            return p
    return None


def glob_first(patterns: Iterable[str]) -> Optional[Path]:
    hits: List[Path] = []
    for pat in patterns:
        hits.extend([p for p in Path(".").glob(pat) if p.is_file()])
    if not hits:
        return None
    return sorted(hits, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def glob_all(patterns: Iterable[str]) -> List[Path]:
    hits: List[Path] = []
    seen = set()
    for pat in patterns:
        for p in Path(".").glob(pat):
            if p.is_file() and str(p) not in seen:
                hits.append(p)
                seen.add(str(p))
    return sorted(hits, key=lambda p: p.stat().st_mtime, reverse=True)


def read_json(path: Optional[Path]) -> Dict[str, Any]:
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"_read_error": str(e), "_path": str(path)}


def read_csv_rows(path: Optional[Path]) -> List[dict]:
    if not path or not path.exists():
        return []
    try:
        return pd.read_csv(path).fillna("").to_dict(orient="records")
    except Exception:
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            return list(csv.DictReader(text.splitlines()))
        except Exception:
            return []


def sqlite_table_exists(conn: sqlite3.Connection, table: str) -> bool:
    r = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return bool(r)


def latest_macro_from_db(db_path: Path) -> Dict[str, Any]:
    if not db_path.exists():
        return {"status": "missing", "source": "db_missing", "db_path": str(db_path)}

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
    except Exception as e:
        return {"status": "missing", "source": "db_open_error", "error": str(e), "db_path": str(db_path)}

    out: Dict[str, Any] = {"status": "available", "source": "sqlite", "db_path": str(db_path)}
    try:
        if sqlite_table_exists(conn, "macro_daily_regime"):
            row = conn.execute("SELECT * FROM macro_daily_regime ORDER BY date_utc DESC LIMIT 1").fetchone()
            if row:
                out["macro_daily_regime_latest"] = dict(row)

        if sqlite_table_exists(conn, "macro_numeric_observations"):
            rows = conn.execute("""
                SELECT series_id, date_utc, value
                FROM macro_numeric_observations
                WHERE (series_id, date_utc) IN (
                    SELECT series_id, MAX(date_utc)
                    FROM macro_numeric_observations
                    GROUP BY series_id
                )
                ORDER BY series_id
            """).fetchall()
            out["macro_numeric_latest"] = [dict(r) for r in rows]
            out["macro_numeric_series_count"] = len(rows)

        if "macro_daily_regime_latest" not in out and "macro_numeric_latest" not in out:
            out["status"] = "missing"
            out["source"] = "sqlite_no_macro_tables"
    except Exception as e:
        out["status"] = "missing"
        out["source"] = "sqlite_query_error"
        out["error"] = str(e)
    finally:
        conn.close()

    return out


def summarize_macro(db_path: Path) -> Dict[str, Any]:
    # Prefer direct DB because reports may be archived.
    db_macro = latest_macro_from_db(db_path)
    if db_macro.get("status") == "available":
        return db_macro

    # Fallback to report JSONs.
    p = glob_first([
        "data/reports/stage9d*/**/*.json",
        "data/reports/stage9c*/**/*.json",
        "archive/**/data/reports/stage9d*/**/*.json",
        "archive/**/data/reports/stage9c*/**/*.json",
    ])
    j = read_json(p)
    if j:
        return {"status": "available", "source": "report_json", "path": str(p), "payload_preview": j}
    return db_macro


def summarize_gdelt() -> Dict[str, Any]:
    events_path = first_existing([
        Path("data/macro/events/stage10b_detected_shock_events.csv"),
        glob_first(["archive/**/data/macro/events/stage10b_detected_shock_events.csv"]),
    ])
    status_path = first_existing([
        Path("data/reports/stage10b_event_pipeline_update/stage10b_gdelt_query_status.csv"),
        glob_first(["archive/**/data/reports/stage10b_event_pipeline_update/stage10b_gdelt_query_status.csv"]),
    ])
    events = read_csv_rows(events_path)
    status_rows = read_csv_rows(status_path)

    classes: Dict[str, int] = {}
    for r in events:
        cls = str(r.get("event_class", "unknown") or "unknown")
        classes[cls] = classes.get(cls, 0) + 1

    status_counts: Dict[str, int] = {}
    for r in status_rows:
        st = str(r.get("Status", r.get("status", "unknown")) or "unknown")
        status_counts[st] = status_counts.get(st, 0) + 1

    preview = []
    for r in events[-10:]:
        preview.append({
            "event_time_utc": r.get("event_time_utc", ""),
            "event_class": r.get("event_class", ""),
            "event_channel": r.get("event_channel", ""),
            "expected_gold_direction": r.get("expected_gold_direction", ""),
            "title": r.get("title", ""),
        })

    return {
        "status": "available" if events else "missing",
        "events_path": str(events_path) if events_path else "",
        "query_status_path": str(status_path) if status_path else "",
        "events_loaded": len(events),
        "classes": classes,
        "query_status_counts": status_counts,
        "recent_preview": preview,
    }


def summarize_event_guard() -> Dict[str, Any]:
    policy_path = first_existing([
        Path("data/reports/stage10e_event_aware_guard_simulation/stage10e_guard_policy_simulation.csv"),
        glob_first(["archive/**/data/reports/stage10e_event_aware_guard_simulation/stage10e_guard_policy_simulation.csv"]),
    ])
    policy_rows = read_csv_rows(policy_path)
    if policy_rows:
        decisions = {str(r.get("policy", "unknown")): str(r.get("decision_hint", "")) for r in policy_rows}
        any_candidate = any(v in {"candidate_guard", "weak_candidate_guard"} for v in decisions.values())
        return {
            "status": "available",
            "source": "stage10e_policy",
            "path": str(policy_path),
            "policy_decisions": decisions,
            "decision": "candidate_guard_found_needs_review" if any_candidate else "no_event_guard_passed",
            "conclusion": "Stage 10E did not justify yield/news guard" if not any_candidate else "Review required; do not enable automatically",
        }

    # Fallback: Stage10D says impact classes, but not guard effect on strategy.
    summary_path = first_existing([
        Path("data/reports/stage10d_event_impact_validation_lab/stage10d_event_class_validation_summary.csv"),
        glob_first(["archive/**/data/reports/stage10d_event_impact_validation_lab/stage10d_event_class_validation_summary.csv"]),
    ])
    rows = read_csv_rows(summary_path)
    verdict_counts: Dict[str, int] = {}
    for r in rows:
        v = str(r.get("Verdict", r.get("verdict", "unknown")) or "unknown")
        verdict_counts[v] = verdict_counts.get(v, 0) + 1

    if rows:
        return {
            "status": "available_partial",
            "source": "stage10d_validation_summary",
            "path": str(summary_path),
            "verdict_counts": verdict_counts,
            "decision": "impact_validation_available_but_no_guard_enabled",
            "conclusion": "Stage 10D validated event impact classes, but no Stage 10E guard policy is active; event/news remains report-only",
        }

    return {
        "status": "missing",
        "decision": "no_event_guard_active",
        "conclusion": "event/news guard not enabled",
    }


def summarize_short_watchlist() -> Dict[str, Any]:
    json_path = first_existing([
        Path("data/reports/stage11d_recent_short_watchlist_report/stage11d_recent_short_watchlist_report.json"),
        glob_first(["archive/**/data/reports/stage11d_recent_short_watchlist_report/stage11d_recent_short_watchlist_report.json"]),
    ])
    csv_path = first_existing([
        Path("data/reports/stage11d_recent_short_watchlist_report/stage11d_recent_short_watchlist_report.csv"),
        glob_first(["archive/**/data/reports/stage11d_recent_short_watchlist_report/stage11d_recent_short_watchlist_report.csv"]),
    ])
    j = read_json(json_path)
    rows = read_csv_rows(csv_path)
    if not j and not rows:
        return {"status": "missing", "decision": "short_watchlist_missing"}

    preview = []
    for r in rows[:8]:
        preview.append({
            "status": r.get("status", ""),
            "verdict": r.get("verdict", ""),
            "latest_active": r.get("latest_active", ""),
            "recent_signal_count": r.get("recent_signal_count", ""),
            "last_signal_utc": r.get("last_signal_utc", ""),
            "variant": r.get("variant", ""),
        })

    return {
        "status": "available",
        "json_path": str(json_path) if json_path else "",
        "csv_path": str(csv_path) if csv_path else "",
        "decision": j.get("decision", ""),
        "latest_closed_h1": j.get("latest_closed_h1", ""),
        "latest_active_count": j.get("latest_active_count", ""),
        "recent_signal_candidate_count": j.get("recent_signal_candidate_count", ""),
        "watchlist_candidates_loaded": j.get("watchlist_candidates_loaded", ""),
        "preview": preview,
    }


def signal_candidate_paths(explicit_paths: List[str]) -> List[Path]:
    paths: List[Path] = []

    for s in explicit_paths:
        if s:
            paths.append(Path(s).expanduser())

    env_p = os.environ.get("XAUUSD_LONG_SIGNAL_CSV", "").strip()
    if env_p:
        paths.append(Path(env_p).expanduser())

    # Repo-local fallback.
    paths.extend(glob_all([
        "data/**/*regime_shadow*signal*.csv",
        "data/**/*forward*signal*.csv",
        "data/**/*stage8d*signal*.csv",
        "data/**/*dryrun*signal*.csv",
        "data/**/*DryRun*signal*.csv",
    ]))

    # Common MT5/Wine-ish fallback candidates. These may or may not exist.
    home = Path.home()
    paths.extend([
        home / "Library/Application Support/MetaQuotes/Terminal/Common/Files/XAUUSD_DryRun_v2_regime_shadow_signals.csv",
        home / "Library/Application Support/MetaQuotes/Terminal/Common/Files/XAUUSD_DryRun_v2_RegimeShadow_signals.csv",
    ])

    uniq = []
    seen = set()
    for p in paths:
        s = str(p)
        if s not in seen:
            uniq.append(p)
            seen.add(s)
    return uniq


def summarize_signal_file(path: Path) -> Dict[str, Any]:
    rows = read_csv_rows(path)
    if not rows:
        return {"path": str(path), "exists": path.exists(), "rows": 0}
    cols = rows[0].keys()
    time_col = ""
    for c in ["signal_utc", "time_utc", "timestamp_utc", "utc_time", "created_utc", "entry_utc"]:
        if c in cols:
            time_col = c
            break
    latest = rows[-1]
    if time_col:
        try:
            latest = sorted(rows, key=lambda r: str(r.get(time_col, "")))[-1]
        except Exception:
            latest = rows[-1]
    return {"path": str(path), "exists": True, "rows": len(rows), "time_col": time_col, "latest": latest}


def summarize_long_signals(explicit_paths: List[str]) -> List[Dict[str, Any]]:
    out = []
    for p in signal_candidate_paths(explicit_paths):
        if p.exists() and p.is_file():
            s = summarize_signal_file(p)
            if s.get("rows", 0) > 0:
                out.append(s)
    return sorted(out, key=lambda x: int(x.get("rows", 0)), reverse=True)[:5]


def authorization_flags() -> Dict[str, bool]:
    return {
        "trade_authorization": False,
        "ea_change_authorization": False,
        "paper_order_authorization": False,
        "live_order_authorization": False,
        "automatic_news_trading": False,
        "automatic_short_trading": False,
        "observe_only": True,
    }


def input_audit(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "long_signal_available": bool(payload.get("long_signal_files")),
        "macro_available": payload.get("macro", {}).get("status") == "available",
        "gdelt_available": payload.get("gdelt", {}).get("status") == "available",
        "event_guard_available": payload.get("event_guard", {}).get("status") in {"available", "available_partial"},
        "short_watchlist_available": payload.get("short_watchlist", {}).get("status") == "available",
    }


def write_report(out_dir: Path, payload: Dict[str, Any]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "stage12a_consolidated_forward_shadow_report.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    macro = payload["macro"]
    gdelt = payload["gdelt"]
    event_guard = payload["event_guard"]
    short_watch = payload["short_watchlist"]
    signal_files = payload["long_signal_files"]
    flags = payload["authorization_flags"]
    audit = payload["input_audit"]

    lines = [
        "# Stage 12A Consolidated Forward-Shadow Report",
        "",
        f"Generated UTC: `{payload['generated_utc']}`",
        f"Tool version: `{payload['tool_version']}`",
        "",
        "> Hard rule: consolidated report only. No EA change, no automatic trading, no paper/live authorization.",
        "",
        "## Input completeness audit",
        "| Input | Available |",
        "|---|---|",
    ]
    for k, v in audit.items():
        lines.append(f"| {k} | `{v}` |")

    lines += [
        "",
        "## Executive decision",
        "| Item | Status |",
        "|---|---|",
        f"| Trade authorization | `{flags['trade_authorization']}` |",
        f"| EA change authorization | `{flags['ea_change_authorization']}` |",
        f"| Paper order authorization | `{flags['paper_order_authorization']}` |",
        f"| Live order authorization | `{flags['live_order_authorization']}` |",
        f"| Automatic news trading | `{flags['automatic_news_trading']}` |",
        f"| Automatic short trading | `{flags['automatic_short_trading']}` |",
        f"| Observe only | `{flags['observe_only']}` |",
        "",
        "## Long v2 forward-shadow state",
    ]

    if signal_files:
        lines += [
            "| Signal file | Rows | Time column | Latest summary |",
            "|---|---:|---|---|",
        ]
        for s in signal_files:
            latest = s.get("latest", {})
            compact = "; ".join([f"{k}={v}" for k, v in list(latest.items())[:8]])
            lines.append(f"| `{s.get('path')}` | {s.get('rows')} | `{s.get('time_col')}` | {compact} |")
    else:
        lines.append("- No local long-signal CSV found. Pass it with `--long-signal-csv /path/to/XAUUSD_DryRun_v2_regime_shadow_signals.csv` if it is in MT5 Common Files.")

    lines += ["", "## Macro context"]
    lines.append(f"- status: `{macro.get('status')}`")
    lines.append(f"- source: `{macro.get('source')}`")
    if macro.get("macro_daily_regime_latest"):
        lines.append(f"- macro_daily_regime_latest: `{macro.get('macro_daily_regime_latest')}`")
    if macro.get("macro_numeric_series_count") is not None:
        lines.append(f"- macro_numeric_series_count: `{macro.get('macro_numeric_series_count')}`")
    if macro.get("macro_numeric_latest"):
        latest_text = "; ".join([f"{r.get('series_id')}={r.get('value')}@{r.get('date_utc')}" for r in macro.get("macro_numeric_latest", [])[:12]])
        lines.append(f"- macro_numeric_latest: `{latest_text}`")
    if macro.get("error"):
        lines.append(f"- error: `{macro.get('error')}`")

    lines += [
        "",
        "## GDELT / news monitoring",
        f"- status: `{gdelt.get('status')}`",
        f"- events_loaded: `{gdelt.get('events_loaded')}`",
        f"- event_classes: `{gdelt.get('classes')}`",
        f"- query_status_counts: `{gdelt.get('query_status_counts')}`",
        "",
        "| Time UTC | Class | Channel | Expected | Title |",
        "|---|---|---|---:|---|",
    ]
    for r in gdelt.get("recent_preview", [])[:10]:
        title = str(r.get("title", "")).replace("|", "/")[:180]
        lines.append(f"| {r.get('event_time_utc')} | {r.get('event_class')} | {r.get('event_channel')} | {r.get('expected_gold_direction')} | {title} |")

    lines += [
        "",
        "## Event/news guard conclusion",
        f"- status: `{event_guard.get('status')}`",
        f"- source: `{event_guard.get('source', '')}`",
        f"- decision: `{event_guard.get('decision')}`",
        f"- conclusion: `{event_guard.get('conclusion')}`",
        "",
        "## Short recent-regime watchlist",
        f"- status: `{short_watch.get('status')}`",
        f"- decision: `{short_watch.get('decision')}`",
        f"- latest_active_count: `{short_watch.get('latest_active_count')}`",
        f"- recent_signal_candidate_count: `{short_watch.get('recent_signal_candidate_count')}`",
        "",
        "| Status | Verdict | Active now | Recent count | Last signal UTC | Variant |",
        "|---|---|---:|---:|---|---|",
    ]
    for r in short_watch.get("preview", [])[:8]:
        lines.append(f"| {r.get('status')} | {r.get('verdict')} | {r.get('latest_active')} | {r.get('recent_signal_count')} | {r.get('last_signal_utc')} | {r.get('variant')} |")

    lines += [
        "",
        "## Operational interpretation",
        "- Long-only validated forward-shadow remains the main active research/monitoring path.",
        "- Macro/news and central-bank-demand events remain monitoring/report-only.",
        "- Stage 10E/10D does not enable a yield/news guard.",
        "- Stage 11 short-side candidates are recent-regime watchlist only, not EA rules.",
        "- No short, news, paper, or live order escalation is authorized by this report.",
        "",
        "## Output files",
        f"- json: `{json_path}`",
        f"- md: `{out_dir / 'stage12a_consolidated_forward_shadow_report.md'}`",
    ]

    md_path = out_dir / "stage12a_consolidated_forward_shadow_report.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path


def run(out_dir: Path, db_path: Path, long_signal_csv: List[str]) -> int:
    payload: Dict[str, Any] = {
        "tool_version": TOOL_VERSION,
        "generated_utc": now_iso(),
        "inputs": {
            "db_path": str(db_path),
            "long_signal_csv": long_signal_csv,
        },
        "long_signal_files": summarize_long_signals(long_signal_csv),
        "macro": summarize_macro(db_path),
        "gdelt": summarize_gdelt(),
        "event_guard": summarize_event_guard(),
        "short_watchlist": summarize_short_watchlist(),
        "authorization_flags": authorization_flags(),
    }
    payload["input_audit"] = input_audit(payload)

    md_path = write_report(out_dir, payload)
    print("Stage 12A consolidated forward-shadow report: DONE")
    print(f"tool_version={TOOL_VERSION}")
    print(f"input_audit={payload['input_audit']}")
    print(f"trade_authorization={payload['authorization_flags']['trade_authorization']} observe_only={payload['authorization_flags']['observe_only']}")
    print(f"Report: {md_path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--long-signal-csv", action="append", default=[], help="Optional explicit MT5/EA signal CSV path. Can be repeated.")
    args = p.parse_args()
    return run(Path(args.out_dir), Path(args.db), args.long_signal_csv)


if __name__ == "__main__":
    raise SystemExit(main())
