#!/usr/bin/env python3
"""
Stage 10D — Event Impact Validation Lab

Purpose:
- Validate Stage 10A event/news impact results against matched non-event controls.
- De-cluster repeated numeric shocks so one prolonged regime does not become 50 pseudo-events.
- Decide whether each event class is:
  1) useful as directional signal candidate
  2) useful as risk/volatility warning only
  3) too noisy / reject

Inputs:
- data/reports/stage10a_event_impact_lab/stage10a_events_annotated.csv
- data/local/xauusd_local_store.sqlite
  bars table with AMarkets MT5 XAUUSD H1 data

Outputs:
- data/reports/stage10d_event_impact_validation_lab/stage10d_event_impact_validation_lab.md
- data/reports/stage10d_event_impact_validation_lab/stage10d_event_class_validation_summary.csv
- data/reports/stage10d_event_impact_validation_lab/stage10d_event_controls.csv
- data/reports/stage10d_event_impact_validation_lab/stage10d_events_declustered.csv
- data/reports/stage10d_event_impact_validation_lab/stage10d_event_impact_validation_lab.json
- SQLite:
  event_impact_validation_summary

Hard rules:
- Research/validation only.
- No trading signal.
- No EA change.
- No demo/paper/live/order authorization.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from statistics import median, mean
from typing import Dict, List, Optional, Sequence, Tuple


TOOL_VERSION = "v1"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_ANNOTATED = Path("data/reports/stage10a_event_impact_lab/stage10a_events_annotated.csv")
DEFAULT_OUT_DIR = Path("data/reports/stage10d_event_impact_validation_lab")


@dataclass
class Bar:
    utc_time: datetime
    open: float
    high: float
    low: float
    close: float


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_time(v: str) -> Optional[datetime]:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return None


def safe_float(v, default=0.0) -> float:
    try:
        if v is None or str(v).strip() == "":
            return default
        return float(str(v).strip())
    except Exception:
        return default


def safe_int(v, default=0) -> int:
    try:
        if v is None or str(v).strip() == "":
            return default
        return int(float(str(v).strip()))
    except Exception:
        return default


def sign(v: Optional[float], flat_threshold: float = 0.15) -> int:
    if v is None:
        return 0
    if v > flat_threshold:
        return 1
    if v < -flat_threshold:
        return -1
    return 0


def direction_match(expected: int, realized: int) -> Optional[int]:
    if expected == 0 or realized == 0:
        return None
    return 1 if expected == realized else 0


def read_csv(path: Path) -> List[dict]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if not text.strip():
        return []
    return list(csv.DictReader(text.splitlines()))


def write_csv(path: Path, rows: Sequence[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = list(rows[0].keys()) if rows else ["empty"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def connect_db(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(f"DB not found: {path}")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def load_h1_bars(conn: sqlite3.Connection) -> List[Bar]:
    rows = conn.execute("""
        SELECT utc_time, open, high, low, close
        FROM bars
        WHERE source='amarkets_mt5' AND symbol='XAUUSD' AND timeframe='1h'
        ORDER BY utc_time ASC
    """).fetchall()
    out = []
    for r in rows:
        t = parse_time(r["utc_time"])
        if t is None:
            continue
        out.append(Bar(t, float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])))
    return out


def first_bar_at_or_after(bars: Sequence[Bar], t: datetime) -> Optional[int]:
    lo, hi = 0, len(bars) - 1
    ans = None
    while lo <= hi:
        mid = (lo + hi) // 2
        if bars[mid].utc_time >= t:
            ans = mid
            hi = mid - 1
        else:
            lo = mid + 1
    return ans


def rolling_baseline_abs_move(bars: Sequence[Bar], idx: int, lookback: int = 120) -> float:
    lo = max(1, idx - lookback)
    vals = [abs(bars[i].close - bars[i - 1].close) for i in range(lo, idx)]
    vals = [v for v in vals if v > 0]
    if not vals:
        return 1.0
    return max(0.25, median(vals))


def reaction_at(bars: Sequence[Bar], t: datetime, horizon_h: int = 12) -> Optional[dict]:
    idx = first_bar_at_or_after(bars, t)
    if idx is None:
        return None
    target = bars[idx].utc_time + timedelta(hours=horizon_h)
    j = first_bar_at_or_after(bars, target)
    if j is None or j >= len(bars):
        return None

    anchor = bars[idx]
    ret = bars[j].close - anchor.open
    window = bars[idx:j + 1]
    mfe = max(b.high for b in window) - anchor.open
    mae = min(b.low for b in window) - anchor.open
    base = rolling_baseline_abs_move(bars, idx)
    norm = abs(ret) / base if base else 0.0
    return {
        "anchor_bar_utc": anchor.utc_time.isoformat(),
        "anchor_price": round(anchor.open, 6),
        "ret_12h": round(ret, 6),
        "mfe_12h": round(mfe, 6),
        "mae_12h": round(mae, 6),
        "abs_impact_12h": round(abs(ret), 6),
        "normalized_impact_12h": round(norm, 6),
        "realized_direction_12h": sign(ret),
    }


def decluster_events(rows: Sequence[dict], min_gap_hours: int) -> List[dict]:
    """
    De-cluster by (event_class, event_channel). Keep earliest event, then skip same class/channel
    events until min_gap_hours has passed.
    """
    parsed = []
    for r in rows:
        t = parse_time(r.get("event_time_utc", ""))
        if t is None:
            continue
        rr = dict(r)
        rr["_event_dt"] = t
        parsed.append(rr)

    parsed.sort(key=lambda r: (r["_event_dt"], r.get("event_class", ""), r.get("event_id", "")))

    last_by_key: Dict[Tuple[str, str], datetime] = {}
    out = []
    for r in parsed:
        key = (r.get("event_class", "unknown"), r.get("event_channel", "unknown"))
        t = r["_event_dt"]
        last = last_by_key.get(key)
        if last is not None and (t - last).total_seconds() < min_gap_hours * 3600:
            continue
        last_by_key[key] = t
        r.pop("_event_dt", None)
        out.append(r)
    return out


def event_date_set(rows: Sequence[dict], pad_days: int = 1) -> set:
    dates = set()
    for r in rows:
        t = parse_time(r.get("event_time_utc", ""))
        if t is None:
            continue
        for k in range(-pad_days, pad_days + 1):
            dates.add((t.date() + timedelta(days=k)).isoformat())
    return dates


def matched_controls_for_event(row: dict, bars: Sequence[Bar], event_dates: set, controls_per_event: int = 4, max_weeks: int = 32) -> List[dict]:
    """
    Controls: same UTC hour and weekday, +-N weeks, excluding event +/- pad days.
    """
    t = parse_time(row.get("event_time_utc", ""))
    if t is None:
        return []

    expected = safe_int(row.get("expected_gold_direction"), 0)
    controls = []
    offsets = []
    for w in range(1, max_weeks + 1):
        offsets.append(-7 * w)
        offsets.append(7 * w)

    for days in offsets:
        if len(controls) >= controls_per_event:
            break
        ct = t + timedelta(days=days)
        if ct.date().isoformat() in event_dates:
            continue
        react = reaction_at(bars, ct, horizon_h=12)
        if react is None:
            continue
        realized = react["realized_direction_12h"]
        dm = direction_match(expected, realized)
        controls.append({
            "event_id": row.get("event_id", ""),
            "control_time_utc": ct.isoformat(),
            "event_class": row.get("event_class", "unknown"),
            "event_channel": row.get("event_channel", "unknown"),
            "expected_gold_direction": expected,
            **react,
            "direction_match_12h": "" if dm is None else dm,
        })

    return controls


def rate(vals: Sequence[float], pred) -> float:
    if not vals:
        return 0.0
    return sum(1 for v in vals if pred(v)) / len(vals)


def avg(vals: Sequence[float]) -> float:
    return mean(vals) if vals else 0.0


def med(vals: Sequence[float]) -> float:
    return median(vals) if vals else 0.0


def summarize(events: Sequence[dict], controls: Sequence[dict]) -> List[dict]:
    event_groups: Dict[Tuple[str, str], List[dict]] = {}
    control_groups: Dict[Tuple[str, str], List[dict]] = {}

    for r in events:
        key = (r.get("event_class", "unknown"), r.get("event_channel", "unknown"))
        event_groups.setdefault(key, []).append(r)

    for r in controls:
        key = (r.get("event_class", "unknown"), r.get("event_channel", "unknown"))
        control_groups.setdefault(key, []).append(r)

    rows = []
    keys = sorted(set(event_groups.keys()) | set(control_groups.keys()))
    for cls, channel in keys:
        es = event_groups.get((cls, channel), [])
        cs = control_groups.get((cls, channel), [])

        e_norm = [safe_float(r.get("normalized_impact_12h")) for r in es if str(r.get("normalized_impact_12h", "")).strip() != ""]
        c_norm = [safe_float(r.get("normalized_impact_12h")) for r in cs if str(r.get("normalized_impact_12h", "")).strip() != ""]

        e_highmed = rate(e_norm, lambda x: x >= 2.0)
        c_highmed = rate(c_norm, lambda x: x >= 2.0)

        e_noise = rate(e_norm, lambda x: x < 0.75)
        c_noise = rate(c_norm, lambda x: x < 0.75)

        e_dir = [safe_int(r.get("direction_match_12h")) for r in es if str(r.get("direction_match_12h", "")).strip() in {"0", "1"}]
        c_dir = [safe_int(r.get("direction_match_12h")) for r in cs if str(r.get("direction_match_12h", "")).strip() in {"0", "1"}]

        avg_e = avg(e_norm)
        avg_c = avg(c_norm)
        med_e = med(e_norm)
        med_c = med(c_norm)
        lift_avg = avg_e / avg_c if avg_c > 0 else 0.0
        lift_med = med_e / med_c if med_c > 0 else 0.0
        lift_rate = e_highmed / c_highmed if c_highmed > 0 else 0.0

        dir_acc_e = avg(e_dir) if e_dir else None
        dir_acc_c = avg(c_dir) if c_dir else None

        # Conservative decision rules.
        if len(es) >= 20 and lift_avg >= 1.25 and e_highmed >= c_highmed + 0.10 and (dir_acc_e is None or dir_acc_e >= 0.55):
            if dir_acc_e is None:
                verdict = "risk_volatility_warning_candidate"
            else:
                verdict = "directional_or_guard_candidate"
        elif len(es) >= 20 and lift_avg >= 1.15 and e_highmed > c_highmed:
            verdict = "weak_monitor_candidate"
        elif len(es) < 10:
            verdict = "insufficient_sample"
        else:
            verdict = "reject_or_noise"

        rows.append({
            "event_class": cls,
            "event_channel": channel,
            "events_declustered": len(es),
            "controls": len(cs),
            "avg_event_norm12": round(avg_e, 6),
            "avg_control_norm12": round(avg_c, 6),
            "avg_impact_lift": round(lift_avg, 6),
            "median_event_norm12": round(med_e, 6),
            "median_control_norm12": round(med_c, 6),
            "median_impact_lift": round(lift_med, 6),
            "event_high_medium_rate": round(e_highmed, 6),
            "control_high_medium_rate": round(c_highmed, 6),
            "impact_rate_lift": round(lift_rate, 6),
            "event_noise_rate": round(e_noise, 6),
            "control_noise_rate": round(c_noise, 6),
            "event_direction_accuracy": "" if dir_acc_e is None else round(dir_acc_e, 6),
            "control_direction_accuracy": "" if dir_acc_c is None else round(dir_acc_c, 6),
            "validation_verdict": verdict,
        })

    rows.sort(key=lambda r: (r["validation_verdict"], r["avg_impact_lift"], r["events_declustered"]), reverse=True)
    return rows


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS event_impact_validation_summary (
            event_class TEXT,
            event_channel TEXT,
            events_declustered INTEGER,
            controls INTEGER,
            avg_event_norm12 REAL,
            avg_control_norm12 REAL,
            avg_impact_lift REAL,
            median_event_norm12 REAL,
            median_control_norm12 REAL,
            median_impact_lift REAL,
            event_high_medium_rate REAL,
            control_high_medium_rate REAL,
            impact_rate_lift REAL,
            event_noise_rate REAL,
            control_noise_rate REAL,
            event_direction_accuracy REAL,
            control_direction_accuracy REAL,
            validation_verdict TEXT,
            generated_utc TEXT,
            PRIMARY KEY (event_class, event_channel)
        )
    """)
    conn.commit()


def upsert_summary(conn: sqlite3.Connection, rows: Sequence[dict]) -> None:
    ensure_table(conn)
    gen = now_iso()
    for r in rows:
        def nullable_float(x):
            if x == "" or x is None:
                return None
            return float(x)
        conn.execute("""
            INSERT OR REPLACE INTO event_impact_validation_summary (
                event_class, event_channel, events_declustered, controls,
                avg_event_norm12, avg_control_norm12, avg_impact_lift,
                median_event_norm12, median_control_norm12, median_impact_lift,
                event_high_medium_rate, control_high_medium_rate, impact_rate_lift,
                event_noise_rate, control_noise_rate, event_direction_accuracy,
                control_direction_accuracy, validation_verdict, generated_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            r["event_class"], r["event_channel"], r["events_declustered"], r["controls"],
            r["avg_event_norm12"], r["avg_control_norm12"], r["avg_impact_lift"],
            r["median_event_norm12"], r["median_control_norm12"], r["median_impact_lift"],
            r["event_high_medium_rate"], r["control_high_medium_rate"], r["impact_rate_lift"],
            r["event_noise_rate"], r["control_noise_rate"], nullable_float(r["event_direction_accuracy"]),
            nullable_float(r["control_direction_accuracy"]), r["validation_verdict"], gen
        ))
    conn.commit()


def write_report(out_dir: Path, payload: dict, summary: Sequence[dict]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "stage10d_event_impact_validation_lab.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    verdict_counts: Dict[str, int] = {}
    for r in summary:
        verdict_counts[r["validation_verdict"]] = verdict_counts.get(r["validation_verdict"], 0) + 1

    lines = [
        "# Stage 10D Event Impact Validation Lab",
        "",
        f"Generated UTC: `{payload['generated_utc']}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: validation only. This does not authorize demo, paper, or live orders.",
        "",
        "## Inputs",
        f"- db: `{payload['db_path']}`",
        f"- annotated_events_csv: `{payload['annotated_events_csv']}`",
        f"- raw_events_loaded: `{payload['raw_events_loaded']}`",
        f"- declustered_events: `{payload['declustered_events']}`",
        f"- controls_generated: `{payload['controls_generated']}`",
        f"- min_gap_hours: `{payload['min_gap_hours']}`",
        f"- controls_per_event: `{payload['controls_per_event']}`",
        "",
        "## Verdict counts",
        "| Verdict | Classes |",
        "|---|---:|",
    ]
    for k, v in sorted(verdict_counts.items()):
        lines.append(f"| {k} | {v} |")
    if not verdict_counts:
        lines.append("| none | 0 |")

    lines += [
        "",
        "## Event class validation summary",
        "| Event class | Channel | Events | Controls | Avg lift | Median lift | Event high/med | Control high/med | Dir acc | Verdict |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    if summary:
        for r in summary:
            lines.append(
                f"| {r['event_class']} | {r['event_channel']} | {r['events_declustered']} | {r['controls']} | "
                f"{r['avg_impact_lift']} | {r['median_impact_lift']} | {r['event_high_medium_rate']} | "
                f"{r['control_high_medium_rate']} | {r['event_direction_accuracy']} | {r['validation_verdict']} |"
            )
    else:
        lines.append("| none | none | 0 | 0 | 0 | 0 | 0 | 0 |  | none |")

    lines += [
        "",
        "## Interpretation",
        "- Stage 10A measured impact, but Stage 10D asks whether that impact is larger than matched non-event windows.",
        "- De-clustering reduces repeated regime days being counted as independent events.",
        "- `directional_or_guard_candidate` can be tested later as a report/guard layer.",
        "- `risk_volatility_warning_candidate` is not directional; it can support no-trade/event-risk warnings.",
        "- `reject_or_noise` should not be used for trading decisions.",
        "",
        "## Decision",
        "- No EA change.",
        "- No automatic news trading.",
        "- If a class passes validation, next step is Stage 10E: event-aware report/guard simulation, not live execution.",
    ]
    (out_dir / "stage10d_event_impact_validation_lab.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(db_path: Path, annotated_path: Path, out_dir: Path, min_gap_hours: int, controls_per_event: int) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = now_iso()

    raw = read_csv(annotated_path)
    # Only resolved rows with Stage 10A metrics.
    resolved = [r for r in raw if str(r.get("normalized_impact_12h", "")).strip() != ""]
    declustered = decluster_events(resolved, min_gap_hours=min_gap_hours)

    conn = connect_db(db_path)
    bars = load_h1_bars(conn)
    event_dates = event_date_set(declustered, pad_days=1)

    controls: List[dict] = []
    for r in declustered:
        controls.extend(matched_controls_for_event(r, bars, event_dates, controls_per_event=controls_per_event))

    summary = summarize(declustered, controls)
    upsert_summary(conn, summary)
    conn.close()

    write_csv(out_dir / "stage10d_events_declustered.csv", declustered)
    write_csv(out_dir / "stage10d_event_controls.csv", controls)
    write_csv(out_dir / "stage10d_event_class_validation_summary.csv", summary)

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "db_path": str(db_path),
        "annotated_events_csv": str(annotated_path),
        "raw_events_loaded": len(raw),
        "resolved_events_loaded": len(resolved),
        "declustered_events": len(declustered),
        "controls_generated": len(controls),
        "min_gap_hours": min_gap_hours,
        "controls_per_event": controls_per_event,
        "summary_rows": len(summary),
        "summary": summary,
    }
    write_report(out_dir, payload, summary)

    print("Stage 10D event impact validation lab: DONE")
    print(f"raw={len(raw)} resolved={len(resolved)} declustered={len(declustered)} controls={len(controls)} summary_rows={len(summary)}")
    print(f"Report: {out_dir / 'stage10d_event_impact_validation_lab.md'}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--annotated-events", default=str(DEFAULT_ANNOTATED))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--min-gap-hours", type=int, default=48)
    p.add_argument("--controls-per-event", type=int, default=4)
    args = p.parse_args()
    return run(
        Path(args.db),
        Path(args.annotated_events),
        Path(args.out_dir),
        args.min_gap_hours,
        args.controls_per_event,
    )


if __name__ == "__main__":
    raise SystemExit(main())
