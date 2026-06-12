#!/usr/bin/env python3
"""
Stage 9B — Macro Event Calendar Update

Purpose:
- Maintain scheduled/manual macro/geopolitical events.
- Run locally or in GitHub Actions.
- Produce event calendar artifacts even when no internet is available.
- Feed Stage 9A/9B macro context.

Inputs:
- data/config/stage9a_macro_events.csv
- data/config/stage9b_scheduled_events_seed.csv

Outputs:
- data/macro/events/macro_event_calendar.csv
- data/reports/stage9b_macro_event_calendar_update/*

Hard rules:
- Data/calendar only.
- No trading signal.
- No EA/order/demo/paper/live authorization.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional


TOOL_VERSION = "v1"
DEFAULT_MANUAL_EVENTS = Path("data/config/stage9a_macro_events.csv")
DEFAULT_SCHEDULED_SEED = Path("data/config/stage9b_scheduled_events_seed.csv")
DEFAULT_OUT_DIR = Path("data/macro/events")
DEFAULT_REPORT_DIR = Path("data/reports/stage9b_macro_event_calendar_update")


HEADER = [
    "event_id", "event_time_utc", "event_end_utc", "label", "category", "impact",
    "guard_before_min", "guard_after_min", "mode",
    "event_gold_bias", "safe_haven_score", "real_yield_pressure", "usd_pressure",
    "oil_inflation_pressure", "growth_fear_score", "central_bank_demand_score",
    "confidence", "source_note"
]


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def parse_time(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def read_csv(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if not text.strip():
        return []
    rows = list(csv.DictReader(text.splitlines()))
    out = []
    for r in rows:
        label = (r.get("label") or "").strip()
        if not label or label.upper().startswith("EXAMPLE"):
            continue
        t = parse_time(r.get("event_time_utc", ""))
        if t is None:
            continue
        row = {h: (r.get(h, "") or "").strip() for h in HEADER}
        if not row["event_id"]:
            row["event_id"] = f"{row['category']}_{t.strftime('%Y%m%d%H%M')}_{label.lower().replace(' ', '_')[:30]}"
        if not row["event_end_utc"]:
            row["event_end_utc"] = row["event_time_utc"]
        out.append(row)
    return out


def write_csv(path: Path, rows: List[Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        for r in rows:
            w.writerow({h: r.get(h, "") for h in HEADER})


def merge_events(manual: List[Dict], scheduled: List[Dict]) -> List[Dict]:
    merged: Dict[str, Dict] = {}
    for r in scheduled + manual:
        eid = r.get("event_id", "")
        if not eid:
            continue
        merged[eid] = r  # manual overrides scheduled if same event_id
    return sorted(merged.values(), key=lambda x: x.get("event_time_utc", ""))


def upcoming(rows: List[Dict], days_back: int, days_forward: int) -> List[Dict]:
    now = now_utc()
    lo = now - timedelta(days=days_back)
    hi = now + timedelta(days=days_forward)
    out = []
    for r in rows:
        t = parse_time(r.get("event_time_utc", ""))
        if t is not None and lo <= t <= hi:
            out.append(r)
    return out


def run_update(manual_path: Path, scheduled_path: Path, out_dir: Path, report_dir: Path, days_back: int, days_forward: int) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    generated = now_utc().isoformat()

    manual = read_csv(manual_path)
    scheduled = read_csv(scheduled_path)
    merged = merge_events(manual, scheduled)
    near = upcoming(merged, days_back, days_forward)

    write_csv(out_dir / "macro_event_calendar.csv", merged)
    write_csv(out_dir / "macro_event_calendar_upcoming.csv", near)
    write_csv(report_dir / "macro_event_calendar.csv", merged)
    write_csv(report_dir / "macro_event_calendar_upcoming.csv", near)

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "manual_path": str(manual_path),
        "scheduled_seed_path": str(scheduled_path),
        "manual_events": len(manual),
        "scheduled_events": len(scheduled),
        "merged_events": len(merged),
        "upcoming_events": len(near),
        "window_days_back": days_back,
        "window_days_forward": days_forward,
    }
    (report_dir / "macro_event_calendar_update.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Stage 9B Macro Event Calendar Update",
        "",
        f"Generated UTC: `{generated}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "## Status",
        f"- manual_events: `{len(manual)}`",
        f"- scheduled_events: `{len(scheduled)}`",
        f"- merged_events: `{len(merged)}`",
        f"- upcoming_events: `{len(near)}`",
        f"- window: `{days_back}` days back / `{days_forward}` days forward",
        "",
        "## Upcoming / recent events",
        "| Time UTC | Label | Category | Impact | Mode | Source note |",
        "|---|---|---|---|---|---|",
    ]
    for r in near[:80]:
        lines.append(f"| {r.get('event_time_utc','')} | {r.get('label','')} | {r.get('category','')} | {r.get('impact','')} | {r.get('mode','')} | {r.get('source_note','')} |")
    if not near:
        lines.append("| none | none | none | none | none | none |")
    lines += [
        "",
        "## Decision",
        "- This is calendar/data maintenance only.",
        "- Manual geopolitical events remain curated by the user/operator.",
        "- No EA/order workflow changes are authorized.",
    ]
    (report_dir / "macro_event_calendar_update.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 9B macro event calendar update: DONE")
    print(f"merged_events={len(merged)} upcoming={len(near)} report={report_dir / 'macro_event_calendar_update.md'}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--manual-events", default=str(DEFAULT_MANUAL_EVENTS))
    p.add_argument("--scheduled-seed", default=str(DEFAULT_SCHEDULED_SEED))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    p.add_argument("--days-back", type=int, default=7)
    p.add_argument("--days-forward", type=int, default=45)
    args = p.parse_args()
    return run_update(
        Path(args.manual_events),
        Path(args.scheduled_seed),
        Path(args.out_dir),
        Path(args.report_dir),
        args.days_back,
        args.days_forward,
    )


if __name__ == "__main__":
    raise SystemExit(main())
