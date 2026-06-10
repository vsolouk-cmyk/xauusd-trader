#!/usr/bin/env python3
"""
Stage 12A — Consolidated Forward-Shadow Report

Purpose:
- Produce one operational, consolidated report across:
  1) Long v2 forward-shadow state
  2) Macro context
  3) GDELT/news monitoring
  4) Event/news guard conclusion
  5) Recent short-regime watchlist
  6) Final operational authorization flags

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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd


TOOL_VERSION = "v1"
DEFAULT_OUT_DIR = Path("data/reports/stage12a_consolidated_forward_shadow_report")


STAGE9D_JSON = Path("data/reports/stage9d_macro_aware_forward_shadow_report/stage9d_macro_aware_forward_shadow_report.json")
STAGE9D_MD = Path("data/reports/stage9d_macro_aware_forward_shadow_report/stage9d_macro_aware_forward_shadow_report.md")

STAGE10B_MD = Path("data/reports/stage10b_event_pipeline_update/stage10b_event_pipeline_update.md")
STAGE10B_GDELT_STATUS = Path("data/reports/stage10b_event_pipeline_update/stage10b_gdelt_query_status.csv")
STAGE10B_EVENTS = Path("data/macro/events/stage10b_detected_shock_events.csv")

STAGE10E_POLICY = Path("data/reports/stage10e_event_aware_guard_simulation/stage10e_guard_policy_simulation.csv")
STAGE10E_MD = Path("data/reports/stage10e_event_aware_guard_simulation/stage10e_event_aware_guard_simulation.md")

STAGE11D_JSON = Path("data/reports/stage11d_recent_short_watchlist_report/stage11d_recent_short_watchlist_report.json")
STAGE11D_CSV = Path("data/reports/stage11d_recent_short_watchlist_report/stage11d_recent_short_watchlist_report.csv")
STAGE11D_MD = Path("data/reports/stage11d_recent_short_watchlist_report/stage11d_recent_short_watchlist_report.md")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"_read_error": str(e)}


def read_md_head(path: Path, max_lines: int = 80) -> str:
    if not path.exists():
        return ""
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[:max_lines])
    except Exception:
        return ""


def read_csv_rows(path: Path) -> List[dict]:
    if not path.exists():
        return []
    try:
        return pd.read_csv(path).fillna("").to_dict(orient="records")
    except Exception:
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            return list(csv.DictReader(text.splitlines()))
        except Exception:
            return []


def find_latest_signal_files() -> List[Path]:
    patterns = [
        "data/**/*regime_shadow*signal*.csv",
        "data/**/*forward*signal*.csv",
        "data/**/*stage8d*signal*.csv",
        "data/**/*dryrun*signal*.csv",
        "data/**/*DryRun*signal*.csv",
    ]
    hits: List[Path] = []
    for pat in patterns:
        hits.extend(Path(".").glob(pat))
    uniq = []
    seen = set()
    for p in hits:
        s = str(p)
        if s not in seen and p.is_file():
            seen.add(s)
            uniq.append(p)
    return sorted(uniq, key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)


def summarize_signal_file(path: Path) -> Dict[str, Any]:
    rows = read_csv_rows(path)
    if not rows:
        return {"path": str(path), "rows": 0}
    cols = rows[0].keys()
    time_col = None
    for c in ["signal_utc", "time_utc", "timestamp_utc", "utc_time", "created_utc", "entry_utc"]:
        if c in cols:
            time_col = c
            break
    latest = rows[-1]
    if time_col:
        try:
            rows_sorted = sorted(rows, key=lambda r: str(r.get(time_col, "")))
            latest = rows_sorted[-1]
        except Exception:
            latest = rows[-1]
    return {
        "path": str(path),
        "rows": len(rows),
        "time_col": time_col or "",
        "latest": latest,
    }


def summarize_macro(stage9d: Dict[str, Any], stage9d_md: str) -> Dict[str, Any]:
    if not stage9d and not stage9d_md:
        return {"status": "missing", "decision": "macro_context_missing"}
    # Try common keys, but keep robust.
    out = {"status": "available"}
    for k in [
        "decision", "macro_status", "latest_macro_regime", "latest_macro_score",
        "signals", "outcomes", "warning", "warnings"
    ]:
        if k in stage9d:
            out[k] = stage9d[k]
    # Search text fallback.
    if "neutral" in stage9d_md.lower():
        out.setdefault("macro_context_inferred", "neutral_or_mixed")
    if "warning" in stage9d_md.lower():
        out.setdefault("macro_warning_inferred", True)
    return out


def summarize_gdelt(events: List[dict], query_status: List[dict]) -> Dict[str, Any]:
    classes: Dict[str, int] = {}
    for r in events:
        cls = str(r.get("event_class", "unknown") or "unknown")
        classes[cls] = classes.get(cls, 0) + 1

    status_counts: Dict[str, int] = {}
    for r in query_status:
        st = str(r.get("Status", r.get("status", "unknown")) or "unknown")
        status_counts[st] = status_counts.get(st, 0) + 1

    recent_preview = []
    for r in events[-10:]:
        recent_preview.append({
            "event_time_utc": r.get("event_time_utc", ""),
            "event_class": r.get("event_class", ""),
            "event_channel": r.get("event_channel", ""),
            "expected_gold_direction": r.get("expected_gold_direction", ""),
            "title": r.get("title", ""),
        })

    return {
        "events_loaded": len(events),
        "classes": classes,
        "query_status_counts": status_counts,
        "recent_preview": recent_preview,
    }


def summarize_stage10e(policy_rows: List[dict]) -> Dict[str, Any]:
    if not policy_rows:
        return {
            "status": "missing",
            "decision": "no_event_guard_active",
            "conclusion": "event/news guard not enabled",
        }
    decisions = {}
    for r in policy_rows:
        key = str(r.get("policy", "unknown"))
        decisions[key] = str(r.get("decision_hint", ""))
    any_candidate = any("candidate_guard" == v or "weak_candidate_guard" == v for v in decisions.values())
    return {
        "status": "available",
        "policy_decisions": decisions,
        "decision": "candidate_guard_found_needs_review" if any_candidate else "no_event_guard_passed",
        "conclusion": "Stage 10E did not justify yield/news guard" if not any_candidate else "Review required; do not enable automatically",
    }


def summarize_short_watchlist(stage11d_json: Dict[str, Any], stage11d_rows: List[dict]) -> Dict[str, Any]:
    if not stage11d_json and not stage11d_rows:
        return {"status": "missing", "decision": "short_watchlist_missing"}
    out = {
        "status": "available",
        "decision": stage11d_json.get("decision", ""),
        "latest_closed_h1": stage11d_json.get("latest_closed_h1", ""),
        "latest_active_count": stage11d_json.get("latest_active_count", ""),
        "recent_signal_candidate_count": stage11d_json.get("recent_signal_candidate_count", ""),
        "watchlist_candidates_loaded": stage11d_json.get("watchlist_candidates_loaded", ""),
    }
    preview = []
    for r in stage11d_rows[:8]:
        preview.append({
            "status": r.get("status", ""),
            "verdict": r.get("verdict", ""),
            "latest_active": r.get("latest_active", ""),
            "recent_signal_count": r.get("recent_signal_count", ""),
            "last_signal_utc": r.get("last_signal_utc", ""),
            "variant": r.get("variant", ""),
        })
    out["preview"] = preview
    return out


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

    lines = [
        "# Stage 12A Consolidated Forward-Shadow Report",
        "",
        f"Generated UTC: `{payload['generated_utc']}`",
        f"Tool version: `{payload['tool_version']}`",
        "",
        "> Hard rule: consolidated report only. No EA change, no automatic trading, no paper/live authorization.",
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
        for s in signal_files[:5]:
            latest = s.get("latest", {})
            compact = "; ".join([f"{k}={v}" for k, v in list(latest.items())[:8]])
            lines.append(f"| `{s.get('path')}` | {s.get('rows')} | `{s.get('time_col')}` | {compact} |")
    else:
        lines.append("- No local long-signal CSV found in repo. This is acceptable if MT5 signal logs are outside the repo/Common Files.")

    lines += [
        "",
        "## Macro context",
        f"- status: `{macro.get('status')}`",
        f"- decision/context: `{macro.get('decision', macro.get('macro_context_inferred', 'n/a'))}`",
    ]
    if macro.get("warnings"):
        lines.append(f"- warnings: `{macro.get('warnings')}`")
    if macro.get("warning"):
        lines.append(f"- warning: `{macro.get('warning')}`")

    lines += [
        "",
        "## GDELT / news monitoring",
        f"- events_loaded: `{gdelt.get('events_loaded')}`",
        f"- event_classes: `{gdelt.get('classes')}`",
        f"- query_status_counts: `{gdelt.get('query_status_counts')}`",
        "",
        "| Time UTC | Class | Channel | Expected | Title |",
        "|---|---|---|---:|---|",
    ]
    for r in gdelt.get("recent_preview", [])[:10]:
        title = str(r.get("title", "")).replace("|", "/")[:180]
        lines.append(
            f"| {r.get('event_time_utc')} | {r.get('event_class')} | {r.get('event_channel')} | "
            f"{r.get('expected_gold_direction')} | {title} |"
        )

    lines += [
        "",
        "## Event/news guard conclusion",
        f"- status: `{event_guard.get('status')}`",
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
        lines.append(
            f"| {r.get('status')} | {r.get('verdict')} | {r.get('latest_active')} | "
            f"{r.get('recent_signal_count')} | {r.get('last_signal_utc')} | {r.get('variant')} |"
        )

    lines += [
        "",
        "## Operational interpretation",
        "- Long-only validated forward-shadow remains the main active research/monitoring path.",
        "- Macro/news and central-bank-demand events remain monitoring/report-only.",
        "- Stage 10E did not justify a yield/news guard.",
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


def run(out_dir: Path) -> int:
    generated = now_iso()

    stage9d = read_json(STAGE9D_JSON)
    stage9d_md = read_md_head(STAGE9D_MD)
    macro = summarize_macro(stage9d, stage9d_md)

    gdelt_events = read_csv_rows(STAGE10B_EVENTS)
    gdelt_status = read_csv_rows(STAGE10B_GDELT_STATUS)
    gdelt = summarize_gdelt(gdelt_events, gdelt_status)

    policy_rows = read_csv_rows(STAGE10E_POLICY)
    event_guard = summarize_stage10e(policy_rows)

    stage11d = read_json(STAGE11D_JSON)
    stage11d_rows = read_csv_rows(STAGE11D_CSV)
    short_watchlist = summarize_short_watchlist(stage11d, stage11d_rows)

    signal_files = [summarize_signal_file(p) for p in find_latest_signal_files()[:5]]

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "inputs": {
            "stage9d_json": str(STAGE9D_JSON),
            "stage10b_events": str(STAGE10B_EVENTS),
            "stage10b_gdelt_status": str(STAGE10B_GDELT_STATUS),
            "stage10e_policy": str(STAGE10E_POLICY),
            "stage11d_json": str(STAGE11D_JSON),
            "stage11d_csv": str(STAGE11D_CSV),
        },
        "long_signal_files": signal_files,
        "macro": macro,
        "gdelt": gdelt,
        "event_guard": event_guard,
        "short_watchlist": short_watchlist,
        "authorization_flags": authorization_flags(),
    }

    md_path = write_report(out_dir, payload)
    print("Stage 12A consolidated forward-shadow report: DONE")
    print(f"trade_authorization={payload['authorization_flags']['trade_authorization']} observe_only={payload['authorization_flags']['observe_only']}")
    print(f"Report: {md_path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = p.parse_args()
    return run(Path(args.out_dir))


if __name__ == "__main__":
    raise SystemExit(main())
