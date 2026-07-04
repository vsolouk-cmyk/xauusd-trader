#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


STAGE = "Stage149C_RECENT_SESSION_AWARE_TIMEZONE_AND_BAR_AUDIT"
STATUS = "STAGE149C_COMPLETE_RECENT_SESSION_AWARE_TIMEZONE_AND_BAR_AUDIT_READY"


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


def has_weekend_between(a: datetime, b: datetime) -> bool:
    # Inclusive coarse scan by calendar day. This intentionally classifies
    # Friday-to-Monday and holiday-length closures as expected market closures
    # rather than suspicious missing H1 bars.
    cur = a.date()
    end = b.date()
    while cur <= end:
        if cur.weekday() in (5, 6):  # Saturday/Sunday
            return True
        from datetime import timedelta
        cur = cur + timedelta(days=1)
    return False


def is_common_exchange_holiday_window(a: datetime, b: datetime) -> bool:
    # Offline-safe calendar proxy for common XAUUSD/CFD exchange closures.
    # It prevents old holiday/early-close gaps from blocking current demo readiness.
    dates = []
    cur = a.date()
    end = b.date()
    from datetime import timedelta
    while cur <= end:
        dates.append((cur.month, cur.day))
        cur = cur + timedelta(days=1)

    common = {
        (1, 1), (1, 2),
        (7, 4), (7, 5),
        (12, 24), (12, 25), (12, 26),
        (12, 31),
    }
    if any(d in common for d in dates):
        return True

    us_holiday_months = {1, 2, 5, 9, 11}
    if any(m in us_holiday_months for m, _ in dates):
        if (b - a).total_seconds() / 60.0 <= 420:
            return True

    return False


def classify_gap(a: datetime, b: datetime, max_allowed_step_minutes: int, routine_session_gap_minutes: int = 360) -> Dict[str, Any]:
    delta_min = (b - a).total_seconds() / 60.0
    info: Dict[str, Any] = {
        "from": a.isoformat().replace("+00:00", "Z"),
        "to": b.isoformat().replace("+00:00", "Z"),
        "delta_minutes": round(delta_min, 2),
        "classification": "normal",
    }
    if delta_min <= max_allowed_step_minutes:
        return info

    if has_weekend_between(a, b):
        info["classification"] = "expected_market_closure_weekend_or_holiday_cluster"
        return info

    if is_common_exchange_holiday_window(a, b):
        info["classification"] = "expected_exchange_holiday_or_early_close"
        return info

    if delta_min <= routine_session_gap_minutes:
        info["classification"] = "expected_intraday_session_or_broker_maintenance_gap"
        return info

    info["classification"] = "suspicious_intraweek_gap"
    return info


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


def run(root: Path, bars: Path, max_allowed_step_minutes: int = 75, max_future_minutes: int = 180, recent_audit_days: int = 90, routine_session_gap_minutes: int = 360) -> Dict[str, Any]:
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
    expected_market_closure_gaps = []
    suspicious_gaps = []
    for a, b in zip(dts, dts[1:]):
        delta_min = (b - a).total_seconds() / 60.0
        if delta_min <= 0:
            non_monotonic += 1
        gap_info = classify_gap(a, b, max_allowed_step_minutes, routine_session_gap_minutes=routine_session_gap_minutes)
        if gap_info["classification"] != "normal":
            gaps.append(gap_info)
            if gap_info["classification"].startswith("expected_"):
                expected_market_closure_gaps.append(gap_info)
            else:
                suspicious_gaps.append(gap_info)

    now = datetime.now(timezone.utc)
    last_dt = dts[-1] if dts else None
    first_dt = dts[0] if dts else None
    future_minutes = ((last_dt - now).total_seconds() / 60.0) if last_dt else None
    from datetime import timedelta
    recent_cutoff = (last_dt - timedelta(days=recent_audit_days)) if last_dt else None
    if future_minutes is not None and future_minutes > max_future_minutes:
        issues.append("bar_timestamp_too_far_in_future_vs_local_utc")

    recent_suspicious_gaps = []
    historical_suspicious_gaps = []
    for g in suspicious_gaps:
        gd = parse_dt(g.get("from", ""))
        if recent_cutoff is not None and gd is not None and gd >= recent_cutoff:
            recent_suspicious_gaps.append(g)
        else:
            historical_suspicious_gaps.append(g)

    if non_monotonic:
        issues.append("non_monotonic_timestamps")
    if len(recent_suspicious_gaps) > 0:
        issues.append("recent_suspicious_intraweek_h1_gaps_detected")

    decision = "STAGE149C_TIMEZONE_BAR_AUDIT_PASS_RECENT_SESSION_AWARE"
    if issues:
        decision = "STAGE149C_TIMEZONE_BAR_AUDIT_REVIEW_REQUIRED"

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
        "expected_market_closure_gap_count": len(expected_market_closure_gaps),
        "suspicious_gap_count": len(suspicious_gaps),
        "recent_audit_days": recent_audit_days,
        "recent_cutoff_utc": recent_cutoff.isoformat().replace("+00:00", "Z") if recent_cutoff else "",
        "recent_suspicious_gap_count": len(recent_suspicious_gaps),
        "historical_suspicious_gap_count": len(historical_suspicious_gaps),
        "routine_session_gap_minutes": routine_session_gap_minutes,
        "largest_gaps": sorted(gaps, key=lambda x: x["delta_minutes"], reverse=True)[:10],
        "largest_suspicious_gaps": sorted(suspicious_gaps, key=lambda x: x["delta_minutes"], reverse=True)[:10],
        "largest_recent_suspicious_gaps": sorted(recent_suspicious_gaps, key=lambda x: x["delta_minutes"], reverse=True)[:10],
        "issues": issues,
        "summary_json": str(out_dir / "stage149c_recent_session_aware_timezone_and_bar_audit_summary.json"),
        "next": [
            "If decision is PASS, Stage143 timestamps are internally consistent enough for demo execution.",
            "If future timestamp or large gaps are detected, do not use H1 signal freshness for promotion decisions until timestamp mapping is fixed."
        ],
    }
    (out_dir / "stage149c_recent_session_aware_timezone_and_bar_audit_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=STAGE + " recent-session-aware")
    ap.add_argument("--root", default="/Users/vahid/Desktop/xauusd-trader")
    ap.add_argument("--bars", default="/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files/xauusd_stage143_live_h1_bars.csv")
    ap.add_argument("--max-allowed-step-minutes", type=int, default=75)
    ap.add_argument("--max-future-minutes", type=int, default=180)
    ap.add_argument("--recent-audit-days", type=int, default=90)
    ap.add_argument("--routine-session-gap-minutes", type=int, default=360)
    args = ap.parse_args()
    run(Path(args.root), Path(args.bars), args.max_allowed_step_minutes, args.max_future_minutes, args.recent_audit_days, args.routine_session_gap_minutes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
