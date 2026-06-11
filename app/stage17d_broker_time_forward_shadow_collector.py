#!/usr/bin/env python3
"""
Stage 17D — Broker-Time Forward Shadow Collector for PDH Breakout Continuation

Candidate:
- pdh_breakout_continuation_long_h32_cool4
- LONG
- previous-day high breakout continuation
- signal: completed M15 bar in London/New York breaks above previous-day high
          and closes above PDH + 0.8
- entry: next completed M15 bar open (theoretical)
- exit: 32 M15 bars after entry = 8 hours
- cooldown/non-overlap handled during candidate detection
- source clock: AMarkets/MT5 broker bar timestamp, NOT wall-clock UTC

Why broker-time:
- Stage17C found AMarkets bar timestamps ahead of wall-clock UTC.
- Therefore true-forward boundaries must be based on broker bar time in the CSV,
  not the machine's current UTC time.

Forward validity rule:
- On first run, collector_start_bar_time is set to the latest completed M15 broker-time bar.
- Only signals with signal_dt > collector_start_bar_time are eligible.
- If a new signal is discovered after its exit target is already available in M1 data,
  it is marked not_forward_late_detected.
- A valid signal must be logged before its exit outcome is known.

Hard rules:
- Research shadow collection only.
- No EA change.
- No automatic trading.
- No paper/live/order authorization.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd


TOOL_VERSION = "v1"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_OUT_DIR = Path("data/reports/stage17d_broker_time_forward_shadow_collector")


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
    # With right-labeled bars, latest completed M15 label is floor(latest_m1 to 15min).
    # This drops the partial current bar, e.g. latest M1 09:26 -> drop 09:30 bar.
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
        })
    return pd.DataFrame(rows)


def add_context(m15: pd.DataFrame) -> pd.DataFrame:
    x = m15.copy()
    x["date"] = x.index.strftime("%Y-%m-%d")
    x["hour"] = x.index.hour
    x["minute"] = x.index.minute
    x["session"] = "other"
    # Broker-time session buckets. Do not treat these as wall-clock UTC sessions.
    x.loc[(x["hour"] >= 0) & (x["hour"] < 7), "session"] = "asia"
    x.loc[(x["hour"] >= 7) & (x["hour"] < 12), "session"] = "london"
    x.loc[(x["hour"] >= 12) & (x["hour"] < 17), "session"] = "new_york"
    x.loc[(x["hour"] >= 17) & (x["hour"] < 22), "session"] = "late_us"

    prev = previous_day_levels(m15)
    x = x.reset_index()
    if "utc_time" in x.columns:
        x = x.rename(columns={"utc_time": "dt"})
    else:
        x = x.rename(columns={x.columns[0]: "dt"})
    x = x.merge(prev, on="date", how="left")
    return x.sort_values("dt").reset_index(drop=True)


def apply_spacing(indices: Sequence[int], horizon_bars: int, cooldown_bars: int) -> List[int]:
    chosen = []
    next_allowed = -1
    for i in indices:
        if i < next_allowed:
            continue
        chosen.append(int(i))
        next_allowed = int(i) + int(horizon_bars) + int(cooldown_bars)
    return chosen


def detect_candidates(
    m15: pd.DataFrame,
    buffer_usd: float,
    close_above_pdh: float,
    horizon_bars: int,
    cooldown_bars: int,
    scan_bars: int,
) -> pd.DataFrame:
    ctx = add_context(m15)
    if scan_bars > 0 and len(ctx) > scan_bars:
        # Need enough history for prev-day levels, already computed; restrict only after context.
        ctx = ctx.tail(scan_bars).reset_index(drop=True)

    cond = (
        ctx["pdh"].notna()
        & ctx["session"].isin(["london", "new_york"])
        & (ctx["high"] > ctx["pdh"] + buffer_usd)
        & (ctx["close"] > ctx["pdh"] + close_above_pdh)
    )
    idxs = apply_spacing(ctx.index[cond].tolist(), horizon_bars=horizon_bars, cooldown_bars=cooldown_bars)

    rows = []
    for i in idxs:
        entry_i = i + 1
        exit_i = entry_i + horizon_bars
        if entry_i >= len(ctx):
            continue
        signal_dt = pd.to_datetime(ctx.iloc[i]["dt"], utc=True)
        entry_dt = pd.to_datetime(ctx.iloc[entry_i]["dt"], utc=True)
        # Exit may be beyond currently completed M15. Compute target by bar duration instead of requiring row exists.
        exit_target_dt = entry_dt + pd.Timedelta(minutes=15 * horizon_bars)
        sid = signal_dt.strftime("%Y%m%dT%H%M%S") + "_pdh_breakout_long_h32_cool4"
        rows.append({
            "signal_id": sid,
            "signal_dt": signal_dt,
            "entry_dt": entry_dt,
            "exit_target_dt": exit_target_dt,
            "variant": "pdh_breakout_continuation_long_h32_cool4",
            "side": "LONG",
            "session": str(ctx.iloc[i]["session"]),
            "hour": int(ctx.iloc[i]["hour"]),
            "signal_open": float(ctx.iloc[i]["open"]),
            "signal_high": float(ctx.iloc[i]["high"]),
            "signal_low": float(ctx.iloc[i]["low"]),
            "signal_close": float(ctx.iloc[i]["close"]),
            "pdh": float(ctx.iloc[i]["pdh"]),
            "pdl": float(ctx.iloc[i]["pdl"]),
            "prev_range": float(ctx.iloc[i]["prev_range"]),
            "break_above_pdh": round(float(ctx.iloc[i]["high"] - ctx.iloc[i]["pdh"]), 6),
            "close_above_pdh": round(float(ctx.iloc[i]["close"] - ctx.iloc[i]["pdh"]), 6),
        })

    out = pd.DataFrame(rows)
    if not out.empty:
        for c in ["signal_dt", "entry_dt", "exit_target_dt"]:
            out[c] = pd.to_datetime(out[c], utc=True, errors="coerce")
        out = out.sort_values("signal_dt").reset_index(drop=True)
    return out


def load_or_create_state(state_path: Path, latest_completed_m15: pd.Timestamp, force_reset: bool = False) -> Dict:
    if state_path.exists() and not force_reset:
        return json.loads(state_path.read_text(encoding="utf-8"))

    state = {
        "created_wall_utc": now_iso(),
        "collector_clock_mode": "BROKER_BAR_TIME",
        "collector_start_bar_time": latest_completed_m15.isoformat(),
        "candidate": "pdh_breakout_continuation_long_h32_cool4",
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
    for c in ["detected_wall_utc", "signal_dt", "entry_dt", "exit_target_dt", "resolved_wall_utc"]:
        if c in x.columns:
            x[c] = pd.to_datetime(x[c], utc=True, errors="coerce")
    return x


def get_entry_price(m15: pd.DataFrame, entry_dt: pd.Timestamp) -> Tuple[float, str]:
    if entry_dt in m15.index:
        return float(m15.loc[entry_dt]["open"]), "m15_exact_open"
    pos = m15.index.searchsorted(entry_dt)
    if pos < len(m15):
        return float(m15.iloc[pos]["open"]), "m15_next_open"
    return float("nan"), "entry_after_available_data"


def resolve_one(row: pd.Series, m1: pd.DataFrame, m15: pd.DataFrame, cost_usd: float, resolved_wall_utc: pd.Timestamp) -> Dict:
    status = str(row.get("status", ""))
    if status in {"closed_time_exit", "not_forward_late_detected", "not_forward_exit_already_available"}:
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
    else:
        src = str(row.get("entry_price_source", ""))

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
        out["resolved_wall_utc"] = resolved_wall_utc.isoformat()
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


def append_new_candidates(
    journal: pd.DataFrame,
    candidates: pd.DataFrame,
    collector_start_bar_time: pd.Timestamp,
    latest_m1_time: pd.Timestamp,
    detected_wall_utc: pd.Timestamp,
) -> Tuple[pd.DataFrame, int, int, int]:
    existing_ids = set(journal["signal_id"].astype(str)) if not journal.empty and "signal_id" in journal.columns else set()
    new_rows = []
    skipped_before_start = 0
    late_detected = 0

    if candidates.empty:
        return journal, 0, 0, 0

    for _, r in candidates.iterrows():
        signal_dt = pd.to_datetime(r["signal_dt"], utc=True)
        entry_dt = pd.to_datetime(r["entry_dt"], utc=True)
        exit_dt = pd.to_datetime(r["exit_target_dt"], utc=True)
        sid = str(r["signal_id"])

        if signal_dt <= collector_start_bar_time:
            skipped_before_start += 1
            continue
        if sid in existing_ids:
            continue

        if latest_m1_time >= exit_dt:
            forward_valid = False
            status = "not_forward_late_detected"
            late_detected += 1
        else:
            forward_valid = True
            status = "pending_entry" if latest_m1_time < entry_dt else "open_shadow"

        new_rows.append({
            "signal_id": sid,
            "detected_wall_utc": detected_wall_utc.isoformat(),
            "signal_dt": signal_dt,
            "entry_dt": entry_dt,
            "exit_target_dt": exit_dt,
            "variant": str(r["variant"]),
            "side": "LONG",
            "session": str(r["session"]),
            "hour": int(r["hour"]),
            "forward_valid": bool(forward_valid),
            "status": status,
            "signal_open": float(r["signal_open"]),
            "signal_high": float(r["signal_high"]),
            "signal_low": float(r["signal_low"]),
            "signal_close": float(r["signal_close"]),
            "pdh": float(r["pdh"]),
            "pdl": float(r["pdl"]),
            "prev_range": float(r["prev_range"]),
            "break_above_pdh": float(r["break_above_pdh"]),
            "close_above_pdh": float(r["close_above_pdh"]),
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
            "authorization": "RESEARCH_BROKER_TIME_FORWARD_SHADOW_ONLY_NO_ORDER",
        })

    if new_rows:
        add = pd.DataFrame(new_rows)
        journal = pd.concat([journal, add], ignore_index=True) if not journal.empty else add
        for c in ["detected_wall_utc", "signal_dt", "entry_dt", "exit_target_dt", "resolved_wall_utc"]:
            if c in journal.columns:
                journal[c] = pd.to_datetime(journal[c], utc=True, errors="coerce")

    return journal, len(new_rows), skipped_before_start, late_detected


def resolve_journal(journal: pd.DataFrame, m1: pd.DataFrame, m15: pd.DataFrame, cost_usd: float, resolved_wall_utc: pd.Timestamp) -> Tuple[pd.DataFrame, int]:
    if journal.empty:
        return journal, 0

    rows = []
    closed_before = int(journal["status"].eq("closed_time_exit").sum()) if "status" in journal.columns else 0
    for _, row in journal.iterrows():
        rows.append(resolve_one(row, m1, m15, cost_usd, resolved_wall_utc))
    out = pd.DataFrame(rows)
    for c in ["detected_wall_utc", "signal_dt", "entry_dt", "exit_target_dt", "resolved_wall_utc"]:
        if c in out.columns:
            out[c] = pd.to_datetime(out[c], utc=True, errors="coerce")
    closed_after = int(out["status"].eq("closed_time_exit").sum()) if "status" in out.columns else 0
    return out.sort_values(["signal_dt", "signal_id"]).reset_index(drop=True), max(0, closed_after - closed_before)


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


def decide(journal: pd.DataFrame, data_advanced: bool, new_logged: int, late_detected: int) -> Tuple[str, List[str]]:
    reasons: List[str] = []
    if not data_advanced:
        return "BROKER_FORWARD_WAITING_FOR_NEW_BAR_DATA", ["No new completed broker-time M15 data after collector start/boundary."]

    if journal.empty:
        return "BROKER_FORWARD_ACTIVE_NO_SIGNAL_YET", ["Broker-time forward collection is active; no eligible signal after start yet."]

    valid = journal[journal["forward_valid"].astype(str).str.lower().isin(["true", "1"])].copy()
    closed = valid[valid["status"].eq("closed_time_exit")].copy()
    open_ = valid[valid["status"].isin(["pending_entry", "open_shadow", "open_no_path_yet"])].copy()

    if new_logged > 0 and len(open_) > 0:
        return "BROKER_FORWARD_SIGNAL_OPEN", ["A valid broker-time forward shadow signal is open/pending resolution."]

    if len(closed) > 0:
        if len(closed) < 10:
            return "BROKER_FORWARD_OUTCOMES_AVAILABLE_INSUFFICIENT_SAMPLE", [f"Closed valid broker-time forward outcomes={len(closed)}; continue collecting."]
        m = metrics(closed, "net_x1")
        if m["total"] > 0 and m["pf"] >= 1.15 and m["median"] > 0:
            return "BROKER_FORWARD_SHADOW_POSITIVE_EARLY", ["Closed forward outcomes are positive but still research-only."]
        return "BROKER_FORWARD_SHADOW_WEAK_OR_NEGATIVE", ["Closed forward outcomes are weak/negative; do not escalate."]

    if late_detected > 0 and len(valid) == 0:
        return "BROKER_FORWARD_ONLY_LATE_DETECTED_SIGNALS", ["Signals were found but detected after their exit target; increase refresh cadence."]

    return "BROKER_FORWARD_ACTIVE_NO_SIGNAL_YET", ["Collection is active; no valid open/closed forward signal yet."]


def run(
    db: Path,
    out_dir: Path,
    cost_usd: float,
    buffer_usd: float,
    close_above_pdh: float,
    horizon_bars: int,
    cooldown_bars: int,
    scan_bars: int,
    force_reset: bool,
) -> int:
    generated_wall = now_utc()
    generated = generated_wall.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)

    state_path = out_dir / "stage17d_collector_state.json"
    journal_path = out_dir / "stage17d_broker_time_forward_shadow_journal.csv"
    candidates_csv = out_dir / "stage17d_scan_candidates.csv"
    json_path = out_dir / "stage17d_broker_time_forward_shadow_collector.json"
    md_path = out_dir / "stage17d_broker_time_forward_shadow_collector.md"

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

    candidates = detect_candidates(
        m15=m15,
        buffer_usd=buffer_usd,
        close_above_pdh=close_above_pdh,
        horizon_bars=horizon_bars,
        cooldown_bars=cooldown_bars,
        scan_bars=scan_bars,
    )
    candidates.to_csv(candidates_csv, index=False)

    journal = load_journal(journal_path)
    journal, new_logged, skipped_before_start, late_detected = append_new_candidates(
        journal=journal,
        candidates=candidates,
        collector_start_bar_time=collector_start,
        latest_m1_time=latest_m1,
        detected_wall_utc=generated_wall,
    )
    journal, resolved_count = resolve_journal(journal, m1, m15, cost_usd, generated_wall)
    journal.to_csv(journal_path, index=False)

    valid = journal[journal["forward_valid"].astype(str).str.lower().isin(["true", "1"])].copy() if not journal.empty else pd.DataFrame()
    closed = valid[valid["status"].eq("closed_time_exit")].copy() if not valid.empty else pd.DataFrame()
    open_ = valid[valid["status"].isin(["pending_entry", "open_shadow", "open_no_path_yet"])].copy() if not valid.empty else pd.DataFrame()
    late_invalid = journal[journal["status"].eq("not_forward_late_detected")].copy() if not journal.empty else pd.DataFrame()

    data_advanced = latest_completed_m15 > collector_start
    final_decision, reasons = decide(journal, data_advanced, new_logged, late_detected)
    closed_m = metrics(closed, "net_x1")
    status_counts = journal["status"].value_counts().to_dict() if not journal.empty else {}

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_wall_utc": generated,
        "candidate": {
            "variant": "pdh_breakout_continuation_long_h32_cool4",
            "side": "LONG",
            "clock_mode": "BROKER_BAR_TIME",
            "horizon_bars": int(horizon_bars),
            "horizon_minutes": int(horizon_bars * 15),
            "cooldown_bars": int(cooldown_bars),
            "buffer_usd": float(buffer_usd),
            "close_above_pdh": float(close_above_pdh),
            "cost_usd": float(cost_usd),
        },
        "bar_state": {
            "m1_first_broker_time": m1.index.min().isoformat(),
            "m1_last_broker_time": latest_m1.isoformat(),
            "latest_completed_m15_broker_time": latest_completed_m15.isoformat(),
            "collector_start_bar_time": collector_start.isoformat(),
            "data_after_collector_start": bool(data_advanced),
        },
        "counts": {
            "scan_candidates": int(len(candidates)),
            "new_logged_this_run": int(new_logged),
            "skipped_before_start": int(skipped_before_start),
            "late_detected_this_run": int(late_detected),
            "resolved_this_run": int(resolved_count),
            "journal_rows": int(len(journal)),
            "valid_forward_rows": int(len(valid)),
            "open_valid_rows": int(len(open_)),
            "closed_valid_rows": int(len(closed)),
            "late_invalid_rows": int(len(late_invalid)),
            "status_counts": status_counts,
        },
        "closed_valid_metrics": closed_m,
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
        "# Stage 17D Broker-Time Forward Shadow Collector",
        "",
        f"Generated wall UTC: `{generated}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: broker-time research shadow collection only. No EA change, no automatic trading, no paper/live authorization.",
        "",
        "## Candidate",
        "- variant: `pdh_breakout_continuation_long_h32_cool4`",
        "- side: `LONG`",
        "- clock_mode: `BROKER_BAR_TIME`",
        f"- horizon_bars: `{horizon_bars}`",
        f"- horizon_minutes: `{horizon_bars * 15}`",
        f"- cooldown_bars: `{cooldown_bars}`",
        f"- close_above_pdh: `{close_above_pdh}`",
        f"- cost_usd: `{cost_usd}`",
        "",
        "## Bar-time state",
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
        f"- scan_candidates: `{len(candidates)}`",
        f"- new_logged_this_run: `{new_logged}`",
        f"- skipped_before_start: `{skipped_before_start}`",
        f"- late_detected_this_run: `{late_detected}`",
        f"- resolved_this_run: `{resolved_count}`",
        f"- journal_rows: `{len(journal)}`",
        f"- valid_forward_rows: `{len(valid)}`",
        f"- open_valid_rows: `{len(open_)}`",
        f"- closed_valid_rows: `{len(closed)}`",
        f"- late_invalid_rows: `{len(late_invalid)}`",
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
        "## Closed valid forward outcomes",
        "| Events | Total | Avg | Median | WR | PF | DD |",
        "|---:|---:|---:|---:|---:|---:|---:|",
        f"| {closed_m['events']} | {closed_m['total']} | {closed_m['avg']} | {closed_m['median']} | {closed_m['wr']} | {closed_m['pf']} | {closed_m['dd']} |",
        "",
        "## Evidence rule",
        "- This collector uses broker bar time, not wall-clock UTC, for forward boundaries.",
        "- Signals with `signal_dt <= collector_start_bar_time` are not forward evidence.",
        "- Signals first detected after `exit_target_dt` are marked `not_forward_late_detected`.",
        "- Because the horizon is 8 hours, a 24-hour refresh cadence will often create late-detected invalid records.",
        "- No paper/live/order escalation is authorized.",
        "",
        "## Output files",
        f"- state_json: `{state_path}`",
        f"- journal_csv: `{journal_path}`",
        f"- candidates_csv: `{candidates_csv}`",
        f"- json: `{json_path}`",
        f"- md: `{md_path}`",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 17D broker-time forward shadow collector: DONE")
    print(f"final_decision={final_decision}")
    print(f"collector_start_bar_time={collector_start.isoformat()}")
    print(f"latest_completed_m15_broker_time={latest_completed_m15.isoformat()}")
    print(f"new_logged={new_logged} late_detected={late_detected} open_valid={len(open_)} closed_valid={len(closed)}")
    print(f"Report: {md_path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--cost-usd", type=float, default=0.35)
    p.add_argument("--buffer-usd", type=float, default=0.2)
    p.add_argument("--close-above-pdh", type=float, default=0.8)
    p.add_argument("--horizon-bars", type=int, default=32)
    p.add_argument("--cooldown-bars", type=int, default=4)
    p.add_argument("--scan-bars", type=int, default=5000)
    p.add_argument("--force-reset", action="store_true", help="Reset collector start to current latest completed M15 broker-time bar.")
    args = p.parse_args()

    return run(
        db=Path(args.db),
        out_dir=Path(args.out_dir),
        cost_usd=float(args.cost_usd),
        buffer_usd=float(args.buffer_usd),
        close_above_pdh=float(args.close_above_pdh),
        horizon_bars=int(args.horizon_bars),
        cooldown_bars=int(args.cooldown_bars),
        scan_bars=int(args.scan_bars),
        force_reset=bool(args.force_reset),
    )


if __name__ == "__main__":
    raise SystemExit(main())
