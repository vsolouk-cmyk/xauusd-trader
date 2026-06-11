#!/usr/bin/env python3
"""
Stage 18E — Shortlist Broker-Time Forward Shadow Collector

Purpose:
- Add only Stage18D selected shortlist candidates to research-only forward shadow.
- Do not add all 13 Stage18C promotions.
- Use broker bar time for boundaries, because AMarkets/MT5 timestamps are broker-time-like.

Shortlist candidates:
C1) pdl_sweep_reclaim_long_sweep2.5_reclaim2_london_new_york_h6_cool4
    - side: LONG
    - signal: previous-day low sweep + reclaim
    - low < PDL - 0.2
    - sweep_depth >= 2.5
    - 0 <= close - PDL <= 2.0
    - session: London or New York, broker-time buckets
    - entry: next M15 open
    - exit: 6 M15 bars = 90 minutes
    - cooldown: 4 M15 bars

C2) asia_high_breakout_long_close2_range4-35_new_york_only_h48_cool0
    - side: LONG
    - signal: Asia high breakout continuation
    - Asia range between 4 and 35
    - high > Asia high + 0.2
    - close > Asia high + 2.0
    - session: New York only, broker-time buckets
    - entry: next M15 open
    - exit: 48 M15 bars = 12 hours
    - cooldown: 0

Hard rules:
- Research shadow only.
- No EA change.
- No automatic trading.
- No paper/live/order authorization.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import pandas as pd


TOOL_VERSION = "v1"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_OUT_DIR = Path("data/reports/stage18e_shortlist_forward_shadow_collector")


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    variant: str
    family: str
    side: str
    horizon_bars: int
    cooldown_bars: int
    params: Dict


CANDIDATES = [
    Candidate(
        candidate_id="C1_PDL_RECLAIM_H6",
        variant="pdl_sweep_reclaim_long_sweep2.5_reclaim2_london_new_york_h6_cool4",
        family="pdl_sweep_reclaim_refined",
        side="LONG",
        horizon_bars=6,
        cooldown_bars=4,
        params={
            "sweep_min": 2.5,
            "reclaim_min": 0.0,
            "reclaim_max": 2.0,
            "session_set": "london_new_york",
            "buffer_usd": 0.2,
        },
    ),
    Candidate(
        candidate_id="C2_ASIA_HIGH_NY_H48",
        variant="asia_high_breakout_long_close2_range4-35_new_york_only_h48_cool0",
        family="asia_high_breakout_refined",
        side="LONG",
        horizon_bars=48,
        cooldown_bars=0,
        params={
            "close_above": 2.0,
            "asia_range_min": 4.0,
            "asia_range_max": 35.0,
            "session_set": "new_york_only",
            "buffer_usd": 0.2,
        },
    ),
]


def now_utc() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(timezone.utc)).replace(microsecond=0)


def now_iso() -> str:
    return now_utc().isoformat()


def connect(db: Path) -> sqlite3.Connection:
    if not db.exists():
        raise FileNotFoundError(f"DB not found: {db}")
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    return conn


def load_m1(conn: sqlite3.Connection) -> pd.DataFrame:
    rows = conn.execute(
        """
        SELECT utc_time, open, high, low, close
        FROM bars
        WHERE source='amarkets_mt5' AND symbol='XAUUSD' AND timeframe='1m'
        ORDER BY utc_time
        """
    ).fetchall()
    if not rows:
        raise RuntimeError("No AMarkets MT5 M1 bars found.")
    df = pd.DataFrame([dict(r) for r in rows])
    df["utc_time"] = pd.to_datetime(df["utc_time"], utc=True, errors="coerce")
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return (
        df.dropna(subset=["utc_time", "open", "high", "low", "close"])
        .sort_values("utc_time")
        .drop_duplicates("utc_time")
        .set_index("utc_time")
    )


def resample_m15_completed(m1: pd.DataFrame) -> pd.DataFrame:
    raw = m1.resample("15min", label="right", closed="right").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna()
    if raw.empty:
        return raw
    latest_m1 = m1.index.max()
    latest_completed_label = latest_m1.floor("15min")
    return raw[raw.index <= latest_completed_label].copy()


def previous_day_levels(m15: pd.DataFrame) -> pd.DataFrame:
    daily = m15.resample("1D", label="right", closed="right").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna()
    rows = []
    days = list(daily.index.strftime("%Y-%m-%d"))
    for i, day in enumerate(days):
        if i == 0:
            continue
        prev = daily.iloc[i - 1]
        rows.append({
            "date": day,
            "pdh": float(prev["high"]),
            "pdl": float(prev["low"]),
            "prev_range": float(prev["high"] - prev["low"]),
            "prev_mid": float((prev["high"] + prev["low"]) / 2.0),
        })
    return pd.DataFrame(rows)


def session_mask(x: pd.DataFrame, session_set: str) -> pd.Series:
    if session_set == "london_new_york":
        return x["session"].isin(["london", "new_york"])
    if session_set == "new_york_only":
        return x["session"].eq("new_york")
    if session_set == "london_only":
        return x["session"].eq("london")
    return pd.Series(False, index=x.index)


def add_context(m15: pd.DataFrame) -> pd.DataFrame:
    x = m15.copy()
    x["date"] = x.index.strftime("%Y-%m-%d")
    x["hour"] = x.index.hour
    x["minute"] = x.index.minute
    x["session"] = "other"
    # Broker-time buckets, consistent with Stage17D/18C.
    x.loc[(x["hour"] >= 0) & (x["hour"] < 7), "session"] = "asia"
    x.loc[(x["hour"] >= 7) & (x["hour"] < 12), "session"] = "london"
    x.loc[(x["hour"] >= 12) & (x["hour"] < 17), "session"] = "new_york"
    x.loc[(x["hour"] >= 17) & (x["hour"] < 22), "session"] = "late_us"

    prev = previous_day_levels(m15)
    base = x.reset_index()
    if "utc_time" in base.columns:
        base = base.rename(columns={"utc_time": "dt"})
    else:
        base = base.rename(columns={base.columns[0]: "dt"})
    base = base.merge(prev, on="date", how="left")

    asia = base[(base["hour"] >= 0) & (base["hour"] < 7)].groupby("date").agg(
        asia_high=("high", "max"),
        asia_low=("low", "min"),
        asia_open=("open", "first"),
        asia_close=("close", "last"),
    )
    asia["asia_range"] = asia["asia_high"] - asia["asia_low"]
    base = base.merge(asia.reset_index(), on="date", how="left")
    return base.sort_values("dt").reset_index(drop=True)


def apply_spacing(indices: Sequence[int], horizon_bars: int, cooldown_bars: int) -> List[int]:
    chosen = []
    next_allowed = -1
    for i in indices:
        if i < next_allowed:
            continue
        chosen.append(int(i))
        next_allowed = int(i) + int(horizon_bars) + int(cooldown_bars)
    return chosen


def candidate_mask(x: pd.DataFrame, c: Candidate) -> pd.Series:
    p = c.params
    sess = session_mask(x, str(p.get("session_set")))

    if c.family == "pdl_sweep_reclaim_refined":
        sweep_depth = x["pdl"] - x["low"]
        reclaim = x["close"] - x["pdl"]
        return (
            x["pdl"].notna()
            & sess
            & (x["low"] < x["pdl"] - float(p["buffer_usd"]))
            & (x["close"] > x["pdl"])
            & (sweep_depth >= float(p["sweep_min"]))
            & (reclaim >= float(p["reclaim_min"]))
            & (reclaim <= float(p["reclaim_max"]))
        ).fillna(False)

    if c.family == "asia_high_breakout_refined":
        return (
            x["asia_high"].notna()
            & sess
            & (x["asia_range"].between(float(p["asia_range_min"]), float(p["asia_range_max"])))
            & (x["high"] > x["asia_high"] + float(p["buffer_usd"]))
            & (x["close"] > x["asia_high"] + float(p["close_above"]))
        ).fillna(False)

    return pd.Series(False, index=x.index)


def detect_candidates(m15: pd.DataFrame, scan_bars: int) -> pd.DataFrame:
    ctx = add_context(m15)
    if scan_bars > 0 and len(ctx) > scan_bars:
        ctx = ctx.tail(scan_bars).reset_index(drop=True)

    rows = []
    for c in CANDIDATES:
        mask = candidate_mask(ctx, c)
        idxs = apply_spacing(ctx.index[mask].tolist(), c.horizon_bars, c.cooldown_bars)
        for i in idxs:
            entry_i = i + 1
            if entry_i >= len(ctx):
                continue

            signal_dt = pd.to_datetime(ctx.iloc[i]["dt"], utc=True)
            entry_dt = pd.to_datetime(ctx.iloc[entry_i]["dt"], utc=True)
            exit_target_dt = entry_dt + pd.Timedelta(minutes=15 * c.horizon_bars)
            signal_id = f"{c.candidate_id}_{signal_dt.strftime('%Y%m%dT%H%M%S')}"
            rows.append({
                "signal_id": signal_id,
                "candidate_id": c.candidate_id,
                "variant": c.variant,
                "family": c.family,
                "side": c.side,
                "horizon_bars": c.horizon_bars,
                "horizon_minutes": c.horizon_bars * 15,
                "cooldown_bars": c.cooldown_bars,
                "params_json": json.dumps(c.params, sort_keys=True),
                "signal_dt": signal_dt,
                "entry_dt": entry_dt,
                "exit_target_dt": exit_target_dt,
                "session": str(ctx.iloc[i].get("session", "")),
                "hour": int(ctx.iloc[i].get("hour", -1)),
                "signal_open": float(ctx.iloc[i]["open"]),
                "signal_high": float(ctx.iloc[i]["high"]),
                "signal_low": float(ctx.iloc[i]["low"]),
                "signal_close": float(ctx.iloc[i]["close"]),
                "pdh": float(ctx.iloc[i].get("pdh")) if pd.notna(ctx.iloc[i].get("pdh")) else float("nan"),
                "pdl": float(ctx.iloc[i].get("pdl")) if pd.notna(ctx.iloc[i].get("pdl")) else float("nan"),
                "asia_high": float(ctx.iloc[i].get("asia_high")) if pd.notna(ctx.iloc[i].get("asia_high")) else float("nan"),
                "asia_low": float(ctx.iloc[i].get("asia_low")) if pd.notna(ctx.iloc[i].get("asia_low")) else float("nan"),
                "asia_range": float(ctx.iloc[i].get("asia_range")) if pd.notna(ctx.iloc[i].get("asia_range")) else float("nan"),
            })

    out = pd.DataFrame(rows)
    if not out.empty:
        for col in ["signal_dt", "entry_dt", "exit_target_dt"]:
            out[col] = pd.to_datetime(out[col], utc=True, errors="coerce")
        out = out.sort_values(["candidate_id", "signal_dt"]).reset_index(drop=True)
    return out


def load_or_create_state(state_path: Path, latest_completed_m15: pd.Timestamp, force_reset: bool = False) -> Dict:
    if state_path.exists() and not force_reset:
        return json.loads(state_path.read_text(encoding="utf-8"))

    state = {
        "created_wall_utc": now_iso(),
        "collector_clock_mode": "BROKER_BAR_TIME",
        "collector_start_bar_time": latest_completed_m15.isoformat(),
        "candidates": [c.candidate_id for c in CANDIDATES],
        "note": "Only signals with signal_dt > collector_start_bar_time are eligible.",
        "tool_version": TOOL_VERSION,
    }
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    return state


def load_journal(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        x = pd.read_csv(path)
    except Exception:
        return pd.DataFrame()
    for col in ["detected_wall_utc", "signal_dt", "entry_dt", "exit_target_dt", "resolved_wall_utc"]:
        if col in x.columns:
            x[col] = pd.to_datetime(x[col], utc=True, errors="coerce")
    return x


def get_entry_price(m15: pd.DataFrame, entry_dt: pd.Timestamp) -> Tuple[float, str]:
    if entry_dt in m15.index:
        return float(m15.loc[entry_dt]["open"]), "m15_exact_open"
    pos = m15.index.searchsorted(entry_dt)
    if pos < len(m15):
        return float(m15.iloc[pos]["open"]), "m15_next_open"
    return float("nan"), "entry_after_available_data"


def append_new_candidates(journal: pd.DataFrame, candidates: pd.DataFrame, collector_start: pd.Timestamp, latest_m1: pd.Timestamp, detected_wall: pd.Timestamp) -> Tuple[pd.DataFrame, int, int, int]:
    existing = set(journal["signal_id"].astype(str)) if not journal.empty and "signal_id" in journal.columns else set()
    new_rows = []
    skipped = 0
    late = 0

    if candidates.empty:
        return journal, 0, 0, 0

    for _, r in candidates.iterrows():
        signal_dt = pd.to_datetime(r["signal_dt"], utc=True)
        entry_dt = pd.to_datetime(r["entry_dt"], utc=True)
        exit_dt = pd.to_datetime(r["exit_target_dt"], utc=True)
        signal_id = str(r["signal_id"])

        if signal_dt <= collector_start:
            skipped += 1
            continue
        if signal_id in existing:
            continue

        if latest_m1 >= exit_dt:
            forward_valid = False
            status = "not_forward_late_detected"
            late += 1
        else:
            forward_valid = True
            status = "pending_entry" if latest_m1 < entry_dt else "open_shadow"

        d = r.to_dict()
        d.update({
            "detected_wall_utc": detected_wall.isoformat(),
            "forward_valid": bool(forward_valid),
            "status": status,
            "entry_price": float("nan"),
            "entry_price_source": "",
            "exit_price": float("nan"),
            "gross_ret": float("nan"),
            "net_x1": float("nan"),
            "net_x2": float("nan"),
            "net_x4": float("nan"),
            "mfe": float("nan"),
            "mae": float("nan"),
            "resolved_wall_utc": "",
            "authorization": "RESEARCH_SHORTLIST_FORWARD_SHADOW_ONLY_NO_ORDER",
        })
        new_rows.append(d)

    if new_rows:
        add = pd.DataFrame(new_rows)
        journal = pd.concat([journal, add], ignore_index=True) if not journal.empty else add
        for col in ["detected_wall_utc", "signal_dt", "entry_dt", "exit_target_dt", "resolved_wall_utc"]:
            if col in journal.columns:
                journal[col] = pd.to_datetime(journal[col], utc=True, errors="coerce")
    return journal, len(new_rows), skipped, late


def resolve_one(row: pd.Series, m1: pd.DataFrame, m15: pd.DataFrame, cost_usd: float, resolved_wall: pd.Timestamp) -> Dict:
    status = str(row.get("status", ""))
    if status in {"closed_time_exit", "not_forward_late_detected"}:
        return row.to_dict()

    entry_dt = pd.to_datetime(row["entry_dt"], utc=True)
    exit_dt = pd.to_datetime(row["exit_target_dt"], utc=True)
    latest_m1 = m1.index.max()
    out = row.to_dict()

    if latest_m1 < entry_dt:
        out["status"] = "pending_entry"
        return out

    entry_price = pd.to_numeric(row.get("entry_price"), errors="coerce")
    if pd.isna(entry_price):
        entry_price, src = get_entry_price(m15, entry_dt)
        out["entry_price"] = round(float(entry_price), 6) if pd.notna(entry_price) else float("nan")
        out["entry_price_source"] = src

    if pd.isna(entry_price):
        out["status"] = "entry_price_unavailable"
        return out

    if latest_m1 < exit_dt:
        path = m1[(m1.index > entry_dt) & (m1.index <= latest_m1)]
        if path.empty:
            out["status"] = "open_no_path_yet"
            return out
        out["status"] = "open_shadow"
        exit_price = float(path.iloc[-1]["close"])
    else:
        path = m1[(m1.index > entry_dt) & (m1.index <= exit_dt)]
        if path.empty:
            out["status"] = "missing_m1_path"
            return out
        out["status"] = "closed_time_exit"
        out["resolved_wall_utc"] = resolved_wall.isoformat()
        exit_price = float(path.iloc[-1]["close"])

    gross = exit_price - float(entry_price)
    mfe = float(path["high"].max()) - float(entry_price)
    mae = float(entry_price) - float(path["low"].min())
    out["exit_price"] = round(exit_price, 6)
    out["gross_ret"] = round(gross, 6)
    out["net_x1"] = round(gross - cost_usd, 6)
    out["net_x2"] = round(gross - 2 * cost_usd, 6)
    out["net_x4"] = round(gross - 4 * cost_usd, 6)
    out["mfe"] = round(mfe, 6)
    out["mae"] = round(mae, 6)
    return out


def resolve_journal(journal: pd.DataFrame, m1: pd.DataFrame, m15: pd.DataFrame, cost_usd: float, resolved_wall: pd.Timestamp) -> Tuple[pd.DataFrame, int]:
    if journal.empty:
        return journal, 0
    before = int(journal["status"].eq("closed_time_exit").sum()) if "status" in journal.columns else 0
    rows = [resolve_one(row, m1, m15, cost_usd, resolved_wall) for _, row in journal.iterrows()]
    out = pd.DataFrame(rows)
    for col in ["detected_wall_utc", "signal_dt", "entry_dt", "exit_target_dt", "resolved_wall_utc"]:
        if col in out.columns:
            out[col] = pd.to_datetime(out[col], utc=True, errors="coerce")
    after = int(out["status"].eq("closed_time_exit").sum()) if "status" in out.columns else 0
    return out.sort_values(["candidate_id", "signal_dt", "signal_id"]).reset_index(drop=True), max(0, after - before)


def profit_factor(vals: Sequence[float]) -> float:
    vals = [float(v) for v in vals]
    wins = sum(v for v in vals if v > 0)
    losses = abs(sum(v for v in vals if v < 0))
    if losses == 0:
        return 999.0 if wins > 0 else 0.0
    return round(wins / losses, 6)


def max_dd(vals: Sequence[float]) -> float:
    eq = peak = 0.0
    dd = 0.0
    for v in vals:
        eq += float(v)
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return round(dd, 6)


def metrics(df: pd.DataFrame, col: str = "net_x1") -> Dict:
    if df.empty or col not in df.columns:
        return {"events": 0, "total": 0.0, "avg": 0.0, "median": 0.0, "wr": 0.0, "pf": 0.0, "dd": 0.0}
    vals = pd.to_numeric(df[col], errors="coerce").dropna().astype(float).tolist()
    if not vals:
        return {"events": 0, "total": 0.0, "avg": 0.0, "median": 0.0, "wr": 0.0, "pf": 0.0, "dd": 0.0}
    s = pd.Series(vals)
    return {
        "events": int(len(vals)),
        "total": round(float(s.sum()), 6),
        "avg": round(float(s.mean()), 6),
        "median": round(float(s.median()), 6),
        "wr": round(float((s > 0).mean()), 6),
        "pf": profit_factor(vals),
        "dd": max_dd(vals),
    }


def candidate_summary(journal: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for c in CANDIDATES:
        if journal.empty or "candidate_id" not in journal.columns:
            g = pd.DataFrame()
        else:
            g = journal[journal["candidate_id"].eq(c.candidate_id)].copy()
        valid = g[g["forward_valid"].astype(str).str.lower().isin(["true", "1"])] if not g.empty and "forward_valid" in g.columns else pd.DataFrame()
        open_ = valid[valid["status"].isin(["pending_entry", "open_shadow", "open_no_path_yet"])] if not valid.empty else pd.DataFrame()
        closed = valid[valid["status"].eq("closed_time_exit")] if not valid.empty else pd.DataFrame()
        late = g[g["status"].eq("not_forward_late_detected")] if not g.empty and "status" in g.columns else pd.DataFrame()
        m = metrics(closed, "net_x1")
        rows.append({
            "candidate_id": c.candidate_id,
            "variant": c.variant,
            "family": c.family,
            "horizon_minutes": c.horizon_bars * 15,
            "journal_rows": int(len(g)),
            "valid_forward_rows": int(len(valid)),
            "open_valid_rows": int(len(open_)),
            "closed_valid_rows": int(len(closed)),
            "late_invalid_rows": int(len(late)),
            "closed_total": m["total"],
            "closed_median": m["median"],
            "closed_pf": m["pf"],
            "closed_dd": m["dd"],
        })
    return pd.DataFrame(rows)


def decide(journal: pd.DataFrame, data_advanced: bool, new_logged: int, late_detected: int) -> Tuple[str, List[str]]:
    if not data_advanced:
        return "SHORTLIST_WAITING_FOR_NEW_BROKER_BARS", ["No completed broker-time M15 bar after collector boundary."]
    if journal.empty:
        return "SHORTLIST_ACTIVE_NO_SIGNAL_YET", ["Collector is active; no eligible shortlist signal after boundary yet."]

    valid = journal[journal["forward_valid"].astype(str).str.lower().isin(["true", "1"])].copy()
    open_ = valid[valid["status"].isin(["pending_entry", "open_shadow", "open_no_path_yet"])] if not valid.empty else pd.DataFrame()
    closed = valid[valid["status"].eq("closed_time_exit")] if not valid.empty else pd.DataFrame()

    if len(open_) > 0:
        return "SHORTLIST_FORWARD_SIGNAL_OPEN", ["At least one shortlist candidate has an open valid forward-shadow signal."]
    if len(closed) > 0:
        if len(closed) < 10:
            return "SHORTLIST_FORWARD_OUTCOMES_AVAILABLE_INSUFFICIENT_SAMPLE", [f"Closed valid shortlist outcomes={len(closed)}; continue collecting."]
        m = metrics(closed, "net_x1")
        if m["total"] > 0 and m["pf"] >= 1.15 and m["median"] > 0:
            return "SHORTLIST_FORWARD_SHADOW_POSITIVE_EARLY", ["Closed valid shortlist outcomes are positive but still research-only."]
        return "SHORTLIST_FORWARD_SHADOW_WEAK_OR_NEGATIVE", ["Closed valid shortlist outcomes are weak/negative; do not escalate."]
    if late_detected > 0:
        return "SHORTLIST_ONLY_LATE_DETECTED_SIGNALS", ["Signals found after exit target; refresh cadence is too slow for at least one candidate."]
    return "SHORTLIST_ACTIVE_NO_SIGNAL_YET", ["Fresh broker-time data exists; no valid shortlist signal yet."]


def run(db: Path, out_dir: Path, cost_usd: float, scan_bars: int, force_reset: bool) -> int:
    generated_wall = now_utc()
    generated = generated_wall.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)

    state_path = out_dir / "stage18e_collector_state.json"
    journal_path = out_dir / "stage18e_shortlist_forward_shadow_journal.csv"
    candidates_path = out_dir / "stage18e_scan_candidates.csv"
    candidate_summary_path = out_dir / "stage18e_candidate_summary.csv"
    json_path = out_dir / "stage18e_shortlist_forward_shadow_collector.json"
    md_path = out_dir / "stage18e_shortlist_forward_shadow_collector.md"

    conn = connect(db)
    try:
        m1 = load_m1(conn)
    finally:
        conn.close()

    m15 = resample_m15_completed(m1)
    latest_m1 = m1.index.max()
    latest_completed_m15 = m15.index.max()
    state = load_or_create_state(state_path, latest_completed_m15, force_reset=force_reset)
    collector_start = pd.to_datetime(state["collector_start_bar_time"], utc=True)

    scan = detect_candidates(m15, scan_bars=scan_bars)
    scan.to_csv(candidates_path, index=False)

    journal = load_journal(journal_path)
    journal, new_logged, skipped_before_start, late_detected = append_new_candidates(
        journal=journal,
        candidates=scan,
        collector_start=collector_start,
        latest_m1=latest_m1,
        detected_wall=generated_wall,
    )
    journal, resolved_count = resolve_journal(journal, m1, m15, cost_usd, generated_wall)
    journal.to_csv(journal_path, index=False)

    data_advanced = latest_completed_m15 > collector_start
    final_decision, reasons = decide(journal, data_advanced, new_logged, late_detected)
    csum = candidate_summary(journal)
    csum.to_csv(candidate_summary_path, index=False)

    status_counts = journal["status"].value_counts().to_dict() if not journal.empty and "status" in journal.columns else {}

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_wall_utc": generated,
        "clock_mode": "BROKER_BAR_TIME",
        "bar_state": {
            "m1_first_broker_time": m1.index.min().isoformat(),
            "m1_last_broker_time": latest_m1.isoformat(),
            "latest_completed_m15_broker_time": latest_completed_m15.isoformat(),
            "collector_start_bar_time": collector_start.isoformat(),
            "data_after_collector_start": bool(data_advanced),
        },
        "counts": {
            "scan_candidates": int(len(scan)),
            "new_logged_this_run": int(new_logged),
            "skipped_before_start": int(skipped_before_start),
            "late_detected_this_run": int(late_detected),
            "resolved_this_run": int(resolved_count),
            "journal_rows": int(len(journal)),
            "status_counts": status_counts,
        },
        "candidate_summary": csum.to_dict(orient="records"),
        "final_decision": final_decision,
        "reasons": reasons,
        "authorization_flags": {
            "trade_authorization": False,
            "ea_change_authorization": False,
            "paper_order_authorization": False,
            "live_order_authorization": False,
            "automatic_trading": False,
        },
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    lines = [
        "# Stage 18E Shortlist Broker-Time Forward Shadow Collector",
        "",
        f"Generated wall UTC: `{generated}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: shortlist research shadow only. No EA change, no automatic trading, no paper/live authorization.",
        "",
        "## Clock and bar-time state",
        "- clock_mode: `BROKER_BAR_TIME`",
        f"- m1_last_broker_time: `{latest_m1.isoformat()}`",
        f"- latest_completed_m15_broker_time: `{latest_completed_m15.isoformat()}`",
        f"- collector_start_bar_time: `{collector_start.isoformat()}`",
        f"- data_after_collector_start: `{data_advanced}`",
        "",
        "## Final decision",
        f"- final_decision: `{final_decision}`",
        "",
        "## Reasons",
    ]
    for r in reasons:
        lines.append(f"- {r}")

    lines += [
        "",
        "## Counts",
        f"- scan_candidates: `{len(scan)}`",
        f"- new_logged_this_run: `{new_logged}`",
        f"- skipped_before_start: `{skipped_before_start}`",
        f"- late_detected_this_run: `{late_detected}`",
        f"- resolved_this_run: `{resolved_count}`",
        f"- journal_rows: `{len(journal)}`",
        "",
        "## Candidate summary",
        "| Candidate | Variant | Family | Horizon min | Journal | Valid | Open | Closed | Late | Closed total | Closed median | Closed PF |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in csum.to_dict(orient="records"):
        lines.append(
            f"| `{r['candidate_id']}` | `{r['variant']}` | `{r['family']}` | {r['horizon_minutes']} | {r['journal_rows']} | {r['valid_forward_rows']} | {r['open_valid_rows']} | {r['closed_valid_rows']} | {r['late_invalid_rows']} | {r['closed_total']} | {r['closed_median']} | {r['closed_pf']} |"
        )

    lines += [
        "",
        "## Status counts",
    ]
    if status_counts:
        for k, v in status_counts.items():
            lines.append(f"- {k}: `{v}`")
    else:
        lines.append("- none")

    lines += [
        "",
        "## Evidence rule",
        "- Signals with `signal_dt <= collector_start_bar_time` are not forward evidence.",
        "- Signals first detected after `exit_target_dt` are marked `not_forward_late_detected`.",
        "- C1 has 90-minute horizon, so manual daily refresh is usually too slow for valid forward proof.",
        "- C2 has 12-hour horizon, still preferably needs sub-12-hour refresh.",
        "- No paper/live/order escalation is authorized.",
        "",
        "## Output files",
        f"- state_json: `{state_path}`",
        f"- journal_csv: `{journal_path}`",
        f"- candidates_csv: `{candidates_path}`",
        f"- candidate_summary_csv: `{candidate_summary_path}`",
        f"- json: `{json_path}`",
        f"- md: `{md_path}`",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 18E shortlist forward shadow collector: DONE")
    print(f"final_decision={final_decision}")
    print(f"collector_start_bar_time={collector_start.isoformat()}")
    print(f"latest_completed_m15_broker_time={latest_completed_m15.isoformat()}")
    print(f"new_logged={new_logged} late_detected={late_detected} resolved={resolved_count}")
    print(f"Report: {md_path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--cost-usd", type=float, default=0.35)
    p.add_argument("--scan-bars", type=int, default=5000)
    p.add_argument("--force-reset", action="store_true")
    args = p.parse_args()

    return run(
        db=Path(args.db),
        out_dir=Path(args.out_dir),
        cost_usd=float(args.cost_usd),
        scan_bars=int(args.scan_bars),
        force_reset=bool(args.force_reset),
    )


if __name__ == "__main__":
    raise SystemExit(main())
