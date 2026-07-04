#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


STAGE = "Stage149_STAGE143_TIMEZONE_AND_BAR_AUDIT"
STATUS = "STAGE149_COMPLETE_TIMEZONE_AND_BAR_AUDIT_READY"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_dt(s: str) -> Optional[datetime]:
    s = str(s or "").strip()
    if not s:
        return None
    for fmt in ("%Y.%m.%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def read_rows(path: Path, limit: int = 0) -> List[Dict[str, str]]:
    if not path.exists() or path.stat().st_size <= 0:
        return []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        delimiter = "\t" if sample.count("\t") > sample.count(",") else ","
        reader = csv.DictReader(f, delimiter=delimiter)
        out = []
        for row in reader:
            out.append({str(k).strip().strip("<>").lower(): str(v).strip() for k, v in row.items() if k is not None})
            if limit and len(out) >= limit:
                break
        return out


def combine_dt(row: Dict[str, str]) -> Optional[datetime]:
    for k in ("utc_time", "time_utc", "datetime", "time"):
        if k in row:
            dt = parse_dt(row[k])
            if dt:
                return dt
    if "date" in row and "time" in row:
        return parse_dt(row["date"] + " " + row["time"])
    return None


def run(root: Path, bars: Path, max_allowed_step_minutes: int = 75, max_future_minutes: int = 180) -> Dict[str, Any]:
    root = root.expanduser()
    bars = bars.expanduser()
    rows = read_rows(bars)
    dts = [combine_dt(r) for r in rows]
    dts = [d for d in dts if d is not None]
    generated = utc_now()
    out_dir = root / "reports/stage149_stage143_timezone_and_bar_audit"
    out_dir.mkdir(parents=True, exist_ok=True)

    issues: List[str] = []
    if not bars.exists():
        issues.append("bars_file_missing")
    if len(dts) < 100:
        issues.append("too_few_parseable_datetimes")

    non_monotonic = 0
    gaps = []
    for a, b in zip(dts, dts[1:]):
        delta_min = (b - a).total_seconds() / 60.0
        if delta_min <= 0:
            non_monotonic += 1
        if delta_min > max_allowed_step_minutes:
            gaps.append({"from": a.isoformat().replace("+00:00", "Z"), "to": b.isoformat().replace("+00:00", "Z"), "delta_minutes": round(delta_min, 2)})

    now = datetime.now(timezone.utc)
    last_dt = dts[-1] if dts else None
    first_dt = dts[0] if dts else None
    future_minutes = ((last_dt - now).total_seconds() / 60.0) if last_dt else None
    if future_minutes is not None and future_minutes > max_future_minutes:
        issues.append("bar_timestamp_too_far_in_future_vs_local_utc")

    if non_monotonic:
        issues.append("non_monotonic_timestamps")
    if len(gaps) > 0:
        issues.append("h1_gaps_detected")

    decision = "STAGE149_TIMEZONE_BAR_AUDIT_PASS"
    if issues:
        decision = "STAGE149_TIMEZONE_BAR_AUDIT_REVIEW_REQUIRED"

    summary = {
        "stage": STAGE,
        "generated_utc": generated,
        "status": STATUS,
        "decision": decision,
        "root": str(root),
        "bars": str(bars),
        "bars_exists": bars.exists(),
        "raw_row_count": len(rows),
        "parseable_datetime_count": len(dts),
        "first_bar_utc_assumed": first_dt.isoformat().replace("+00:00", "Z") if first_dt else "",
        "last_bar_utc_assumed": last_dt.isoformat().replace("+00:00", "Z") if last_dt else "",
        "local_utc_now": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "last_bar_future_minutes_vs_local_utc": round(future_minutes, 2) if future_minutes is not None else None,
        "non_monotonic_count": non_monotonic,
        "gap_count": len(gaps),
        "largest_gaps": sorted(gaps, key=lambda x: x["delta_minutes"], reverse=True)[:10],
        "issues": issues,
        "summary_json": str(out_dir / "stage149_stage143_timezone_and_bar_audit_summary.json"),
        "next": [
            "If decision is PASS, Stage143 timestamps are internally consistent enough for demo execution.",
            "If future timestamp or large gaps are detected, do not use H1 signal freshness for promotion decisions until timestamp mapping is fixed."
        ],
    }
    (out_dir / "stage149_stage143_timezone_and_bar_audit_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--root", default="/Users/vahid/Desktop/xauusd-trader")
    ap.add_argument("--bars", default="/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files/xauusd_stage143_live_h1_bars.csv")
    ap.add_argument("--max-allowed-step-minutes", type=int, default=75)
    ap.add_argument("--max-future-minutes", type=int, default=180)
    args = ap.parse_args()
    run(Path(args.root), Path(args.bars), args.max_allowed_step_minutes, args.max_future_minutes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
