#!/usr/bin/env python3
"""
Stage28D — DB-first forward-shadow tracker for the Stage28C validated meta-gate.

Research/shadow-only module. It does NOT modify Stage18A, Stage23D, Stage25D,
Stage27D, EA, paper/live mode, or orders.

Purpose
-------
Stage28C validated strict forward-safe meta-gates around the canonical Stage23/25
lineage. Stage28D tracks the selected gate forward with event-by-event expanding
thresholds:

    london_range >= prior-event q60(london_range)
    prior_day_range >= prior-event q25(prior_day_range)

Thresholds are computed only from earlier canonical candidate events, never from
future events. London range is the completed 07:00-13:00 UTC session range known
at the 13:00 UTC entry time; prior-day range is fully known before the current day.

Run:
    cd ~/Desktop/xauusd-trader
    python3 -m app.stage28d_forward_safe_meta_gate_tracker
    cat data/reports/stage28d_forward_safe_meta_gate_tracker/stage28d_forward_safe_meta_gate_tracker.md
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    from app.stage23b_continuation_no_trade_discovery import (
        Candidate,
        ROUNDTRIP_COST_USD,
        events_london_oneway_continuation,
        merge_atr,
        profit_factor,
    )
except Exception as exc:  # pragma: no cover
    raise RuntimeError(
        "Stage28D depends on app.stage23b_continuation_no_trade_discovery. "
        "Restore/apply Stage23B compatibility dependency before Stage28D. Original import error: " + str(exc)
    )

try:
    from app.stage25c_deduped_filter_validation import load_bars_from_db
except Exception as exc:  # pragma: no cover
    raise RuntimeError(
        "Stage28D depends on app.stage25c_deduped_filter_validation for DB-first candle loading. "
        "Apply/run Stage25C before Stage28D. Original import error: " + str(exc)
    )


STAGE_NAME = "stage28d_forward_safe_meta_gate_tracker"
REPORT_DIR = Path("data/reports") / STAGE_NAME
LEDGER_PATH = REPORT_DIR / "stage28d_meta_gate_forward_shadow_ledger.csv"
REPORT_MD = REPORT_DIR / "stage28d_forward_safe_meta_gate_tracker.md"
REPORT_JSON = REPORT_DIR / "stage28d_forward_safe_meta_gate_tracker.json"
RECENT_EVENTS_CSV = REPORT_DIR / "stage28d_recent_meta_gate_events.csv"
GATE_DIAG_CSV = REPORT_DIR / "stage28d_meta_gate_diagnostics.csv"
SCHEMA_DIAG_CSV = REPORT_DIR / "stage28d_db_schema_diagnostic.csv"

DB_PATH = Path(os.getenv("STAGE28D_DB_PATH", "data/local/xauusd_local_store.sqlite")).expanduser()
LOOKBACK_HOURS = int(os.getenv("STAGE28D_LOOKBACK_HOURS", "336"))
MAX_RECENT_ROWS_REPORT = int(os.getenv("STAGE28D_MAX_RECENT_ROWS_REPORT", "25"))
MIN_CALIB_EVENTS = int(os.getenv("STAGE28D_MIN_CALIB_EVENTS", "25"))
LONDON_Q = float(os.getenv("STAGE28D_LONDON_RANGE_Q", "0.60"))
PRIOR_Q = float(os.getenv("STAGE28D_PRIOR_DAY_RANGE_Q", "0.25"))
GATE_NAME = os.getenv("STAGE28D_GATE_NAME", "stage28c_london_q60_prior_q25_expanding").strip()

# Canonical candidate from Stage25C / Stage23B-C lineage:
# S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65
PRIMARY_CANDIDATE = Candidate(
    "london_oneway_continuation",
    "S28D_META_FILTERED_S23B_B_eff0.60_pb0.1_h180_tp0.6_sl0.65_london_q60_prior_q25",
    {
        "london_move_atr_min": 0.9,
        "eff_min": 0.60,
        "pullback_atr_max": 0.10,
        "ny_confirm_atr_min": 0.15,
        "entry_hour": 13,
        "horizon_min": 180,
        "tp_atr": 0.60,
        "sl_atr": 0.65,
    },
)


class Stage28DError(RuntimeError):
    pass


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _finite_for_json(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _finite_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_finite_for_json(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        val = float(obj)
        if math.isinf(val):
            return "inf"
        if math.isnan(val):
            return None
        return val
    if isinstance(obj, pd.Timestamp):
        return str(obj)
    return obj


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        out = float(v)
        return out if np.isfinite(out) else default
    except Exception:
        return default


def _time_column(df: pd.DataFrame) -> str:
    if "time" in df.columns:
        return "time"
    if "timestamp" in df.columns:
        return "timestamp"
    raise Stage28DError("OHLC bars have no time/timestamp column.")


def _to_time_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    tcol = _time_column(out)
    if tcol != "time":
        out = out.rename(columns={tcol: "time"})
    out["time"] = pd.to_datetime(out["time"], utc=True, errors="coerce")
    for c in ["open", "high", "low", "close"]:
        if c not in out.columns:
            raise Stage28DError(f"OHLC bars missing {c} column.")
        out[c] = pd.to_numeric(out[c], errors="coerce")
    if "volume" not in out.columns:
        out["volume"] = 0.0
    return out.dropna(subset=["time", "open", "high", "low", "close"]).sort_values("time").reset_index(drop=True)


def _resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    x = df.copy().set_index("time").sort_index()
    out = (
        x[["open", "high", "low", "close", "volume"]]
        .resample(rule, label="left", closed="left")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna(subset=["open", "high", "low", "close"])
        .reset_index()
    )
    return out


def load_market_data_db_first() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, Any], pd.DataFrame]:
    m1_raw, h1_raw, db_meta, schema_diag = load_bars_from_db(DB_PATH)
    m1 = _to_time_df(m1_raw)
    if m1.empty:
        raise Stage28DError("No M1 OHLC candles found from SQLite DB. CSV fallback is intentionally disabled.")
    h1 = _to_time_df(h1_raw) if h1_raw is not None and not h1_raw.empty else pd.DataFrame()
    if h1.empty:
        h1 = _resample_ohlcv(m1, "1h")
        db_meta["h1_mode_stage28d"] = "derived_from_m1_resample"
    m15 = _resample_ohlcv(m1, "15min")
    db_meta.update(
        {
            "db_first": True,
            "csv_fallback_enabled": False,
            "m1_rows_stage28d": int(len(m1)),
            "h1_rows_stage28d": int(len(h1)),
            "m15_rows_stage28d": int(len(m15)),
        }
    )
    return m1, h1, m15, db_meta, schema_diag


def _session_stats_for_day(g: pd.DataFrame, start_hour: int, end_hour: int, prefix: str) -> Dict[str, float]:
    t = pd.to_datetime(g["time"], utc=True, errors="coerce")
    s = g[(t.dt.hour >= start_hour) & (t.dt.hour < end_hour)].sort_values("time")
    if s.empty:
        return {f"{prefix}_range": np.nan, f"{prefix}_eff": np.nan}
    hi = float(s["high"].max())
    lo = float(s["low"].min())
    op = float(s.iloc[0]["open"])
    cl = float(s.iloc[-1]["close"])
    rng = hi - lo
    eff = abs(cl - op) / rng if rng > 0 else np.nan
    return {f"{prefix}_range": rng, f"{prefix}_eff": eff}


def build_forward_safe_day_features(m15: pd.DataFrame) -> pd.DataFrame:
    x = m15.copy().sort_values("time").reset_index(drop=True)
    x["time"] = pd.to_datetime(x["time"], utc=True, errors="coerce")
    x = x.dropna(subset=["time"])
    x["event_day"] = x["time"].dt.date
    daily = (
        x.groupby("event_day")
        .agg(day_high=("high", "max"), day_low=("low", "min"), day_close=("close", "last"))
        .sort_index()
    )
    daily["day_range"] = daily["day_high"] - daily["day_low"]
    daily["prior_day_range"] = daily["day_range"].shift(1)

    rows: List[Dict[str, Any]] = []
    for day, g in x.groupby("event_day"):
        rec: Dict[str, Any] = {"event_day": day}
        if day in daily.index:
            rec["prior_day_range"] = float(daily.loc[day, "prior_day_range"]) if pd.notna(daily.loc[day, "prior_day_range"]) else np.nan
        rec.update(_session_stats_for_day(g, 0, 7, "asia"))
        rec.update(_session_stats_for_day(g, 7, 13, "london"))
        rows.append(rec)
    return pd.DataFrame(rows)


def enrich_events_with_forward_safe_features(events: pd.DataFrame, m15: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return events.copy()
    ev = events.copy()
    ev["signal_time_dt"] = pd.to_datetime(ev["signal_time"], utc=True, errors="coerce")
    ev = ev.dropna(subset=["signal_time_dt"]).sort_values("signal_time_dt").reset_index(drop=True)
    ev["event_day"] = ev["signal_time_dt"].dt.date
    feats = build_forward_safe_day_features(m15)
    out = ev.merge(feats, on="event_day", how="left")
    return out.sort_values("signal_time_dt").reset_index(drop=True)


def apply_expanding_meta_gate(all_events: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Compute prior-event thresholds and pass/fail for every canonical event."""
    if all_events.empty:
        return all_events.copy(), {
            "gate_name": GATE_NAME,
            "events_before_gate": 0,
            "gate_kept_total": 0,
            "gate_dropped_total": 0,
        }
    out = all_events.copy().sort_values("signal_time_dt").reset_index(drop=True)
    out["stage28d_gate_name"] = GATE_NAME
    out["stage28d_london_q"] = LONDON_Q
    out["stage28d_prior_day_q"] = PRIOR_Q
    out["stage28d_gate_pass"] = False
    out["stage28d_reason"] = "not_evaluated"
    out["london_range_threshold"] = np.nan
    out["prior_day_range_threshold"] = np.nan
    out["calib_events_used"] = 0

    london_vals = pd.to_numeric(out.get("london_range"), errors="coerce")
    prior_vals = pd.to_numeric(out.get("prior_day_range"), errors="coerce")
    for i in range(len(out)):
        hist = out.iloc[:i]
        hist_london = pd.to_numeric(hist.get("london_range"), errors="coerce").dropna()
        hist_prior = pd.to_numeric(hist.get("prior_day_range"), errors="coerce").dropna()
        calib = int(min(len(hist_london), len(hist_prior)))
        out.at[i, "calib_events_used"] = calib
        if calib < MIN_CALIB_EVENTS:
            out.at[i, "stage28d_reason"] = "insufficient_prior_event_calibration"
            continue
        if not np.isfinite(london_vals.iloc[i]) or not np.isfinite(prior_vals.iloc[i]):
            out.at[i, "stage28d_reason"] = "missing_forward_safe_feature"
            continue
        london_thr = float(hist_london.quantile(LONDON_Q))
        prior_thr = float(hist_prior.quantile(PRIOR_Q))
        out.at[i, "london_range_threshold"] = london_thr
        out.at[i, "prior_day_range_threshold"] = prior_thr
        passed = bool(london_vals.iloc[i] >= london_thr and prior_vals.iloc[i] >= prior_thr)
        out.at[i, "stage28d_gate_pass"] = passed
        out.at[i, "stage28d_reason"] = "passed" if passed else "failed_threshold"

    pass_mask = out["stage28d_gate_pass"].fillna(False).astype(bool)
    info = {
        "gate_name": GATE_NAME,
        "gate_basis": "event_by_event_expanding_prior_candidate_events",
        "london_range_quantile": LONDON_Q,
        "prior_day_range_quantile": PRIOR_Q,
        "min_calib_events": MIN_CALIB_EVENTS,
        "events_before_gate_total": int(len(out)),
        "gate_kept_total": int(pass_mask.sum()),
        "gate_dropped_total": int((~pass_mask).sum()),
        "gate_retained_ratio_total": float(pass_mask.mean()) if len(pass_mask) else 0.0,
        "missing_london_range": int(london_vals.isna().sum()),
        "missing_prior_day_range": int(prior_vals.isna().sum()),
        "insufficient_calibration_count": int((out["stage28d_reason"] == "insufficient_prior_event_calibration").sum()),
    }
    return out, info


def _signal_id(candidate: Candidate, signal_time: Any, direction: str) -> str:
    ts = str(pd.Timestamp(signal_time))
    return f"{candidate.name}|{GATE_NAME}|{ts}|{str(direction).lower()}"


def _read_ledger() -> pd.DataFrame:
    if not LEDGER_PATH.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(LEDGER_PATH)
        if "signal_id" not in df.columns:
            return pd.DataFrame()
        return df
    except Exception:
        return pd.DataFrame()


def _write_ledger(df: pd.DataFrame) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    if df.empty:
        df.to_csv(LEDGER_PATH, index=False)
        return
    sort_cols = [c for c in ["signal_time", "candidate", "direction"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols)
    df.to_csv(LEDGER_PATH, index=False)


def _ns_array(times: pd.Series) -> np.ndarray:
    return pd.to_datetime(times, utc=True, errors="coerce").astype("int64").to_numpy(dtype=np.int64)


def _ts_ns(ts: Any) -> int:
    t = pd.Timestamp(ts)
    return int(t.tz_convert("UTC").value if t.tzinfo else t.tz_localize("UTC").value)


def _resolve_event_forward(candles: pd.DataFrame, event: pd.Series, candidate: Candidate, data_latest: pd.Timestamp) -> Dict[str, Any]:
    c = candles.sort_values("time").reset_index(drop=True).copy()
    times_ns = _ns_array(c["time"])
    opens = c["open"].to_numpy(dtype=float)
    highs = c["high"].to_numpy(dtype=float)
    lows = c["low"].to_numpy(dtype=float)
    closes = c["close"].to_numpy(dtype=float)

    params = candidate.params
    signal_time = pd.Timestamp(event["signal_time"])
    if signal_time.tzinfo is None:
        signal_time = signal_time.tz_localize("UTC")
    else:
        signal_time = signal_time.tz_convert("UTC")
    direction = str(event["direction"]).lower()
    atr = _safe_float(event.get("atr", np.nan), default=np.nan)
    sid = _signal_id(candidate, signal_time, direction)

    base: Dict[str, Any] = {
        "signal_id": sid,
        "candidate": candidate.name,
        "family": candidate.family,
        "stage28d_gate_name": GATE_NAME,
        "signal_time": str(signal_time),
        "direction": direction,
        "atr": round(float(atr), 6) if np.isfinite(atr) else None,
        "london_range": round(_safe_float(event.get("london_range", np.nan), np.nan), 6) if pd.notna(event.get("london_range", np.nan)) else None,
        "prior_day_range": round(_safe_float(event.get("prior_day_range", np.nan), np.nan), 6) if pd.notna(event.get("prior_day_range", np.nan)) else None,
        "london_range_threshold": round(_safe_float(event.get("london_range_threshold", np.nan), np.nan), 6) if pd.notna(event.get("london_range_threshold", np.nan)) else None,
        "prior_day_range_threshold": round(_safe_float(event.get("prior_day_range_threshold", np.nan), np.nan), 6) if pd.notna(event.get("prior_day_range_threshold", np.nan)) else None,
        "calib_events_used": int(event.get("calib_events_used", 0)) if pd.notna(event.get("calib_events_used", np.nan)) else 0,
        "gate_reason": str(event.get("stage28d_reason", "")),
        "status": "UNRESOLVED_NO_ENTRY",
        "entry_time": None,
        "entry": None,
        "tp": None,
        "sl": None,
        "exit_time": None,
        "exit": None,
        "exit_reason": None,
        "gross": None,
        "net_x1": None,
        "net_x4": None,
        "floating_gross": None,
        "floating_net_x1": None,
        "horizon_deadline": None,
        "is_open": False,
        "is_resolved": False,
    }

    if not np.isfinite(atr) or atr <= 0 or direction not in {"long", "short"}:
        base["status"] = "INVALID_EVENT"
        return base

    signal_ns = _ts_ns(signal_time)
    entry_idx = int(np.searchsorted(times_ns, signal_ns, side="right"))
    if entry_idx >= len(times_ns):
        base["status"] = "UNRESOLVED_WAITING_FOR_NEXT_M1_BAR"
        base["is_open"] = True
        return base

    entry_ns = int(times_ns[entry_idx])
    entry = float(opens[entry_idx])
    cutoff_ns = entry_ns + int(params["horizon_min"]) * 60 * 1_000_000_000
    tp_atr = float(params["tp_atr"])
    sl_atr = float(params["sl_atr"])

    if direction == "long":
        tp = entry + tp_atr * atr
        sl = entry - sl_atr * atr
    else:
        tp = entry - tp_atr * atr
        sl = entry + sl_atr * atr

    base.update({
        "entry_time": str(pd.Timestamp(entry_ns, tz="UTC")),
        "entry": round(entry, 5),
        "tp": round(tp, 5),
        "sl": round(sl, 5),
        "horizon_deadline": str(pd.Timestamp(cutoff_ns, tz="UTC")),
    })

    full_end_idx = int(np.searchsorted(times_ns, cutoff_ns, side="right"))
    available_end_idx = min(full_end_idx, len(times_ns))
    if available_end_idx <= entry_idx:
        base["status"] = "UNRESOLVED_NO_AVAILABLE_M1_AFTER_ENTRY"
        base["is_open"] = True
        return base

    exit_idx: Optional[int] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None

    for j in range(entry_idx, available_end_idx):
        hi = float(highs[j])
        lo = float(lows[j])
        if direction == "long":
            if lo <= sl:
                exit_idx, exit_price, exit_reason = j, sl, "sl_conservative"
                break
            if hi >= tp:
                exit_idx, exit_price, exit_reason = j, tp, "tp"
                break
        else:
            if hi >= sl:
                exit_idx, exit_price, exit_reason = j, sl, "sl_conservative"
                break
            if lo <= tp:
                exit_idx, exit_price, exit_reason = j, tp, "tp"
                break

    if exit_idx is not None and exit_price is not None:
        gross = (exit_price - entry) if direction == "long" else (entry - exit_price)
        base.update({
            "status": "RESOLVED_TP_SL",
            "exit_time": str(pd.Timestamp(int(times_ns[exit_idx]), tz="UTC")),
            "exit": round(float(exit_price), 5),
            "exit_reason": exit_reason,
            "gross": round(float(gross), 5),
            "net_x1": round(float(gross - ROUNDTRIP_COST_USD), 5),
            "net_x4": round(float(gross - 4.0 * ROUNDTRIP_COST_USD), 5),
            "is_open": False,
            "is_resolved": True,
        })
        return base

    data_latest_ns = _ts_ns(data_latest)
    if full_end_idx <= len(times_ns) and data_latest_ns >= cutoff_ns:
        hidx = max(entry_idx, full_end_idx - 1)
        exit_price = float(closes[hidx])
        gross = (exit_price - entry) if direction == "long" else (entry - exit_price)
        base.update({
            "status": "RESOLVED_HORIZON_CLOSE",
            "exit_time": str(pd.Timestamp(int(times_ns[hidx]), tz="UTC")),
            "exit": round(float(exit_price), 5),
            "exit_reason": "horizon_close",
            "gross": round(float(gross), 5),
            "net_x1": round(float(gross - ROUNDTRIP_COST_USD), 5),
            "net_x4": round(float(gross - 4.0 * ROUNDTRIP_COST_USD), 5),
            "is_open": False,
            "is_resolved": True,
        })
        return base

    current_idx = max(entry_idx, available_end_idx - 1)
    current_close = float(closes[current_idx])
    floating = (current_close - entry) if direction == "long" else (entry - current_close)
    base.update({
        "status": "OPEN_FORWARD_UNRESOLVED",
        "exit_reason": "open_unresolved",
        "floating_gross": round(float(floating), 5),
        "floating_net_x1": round(float(floating - ROUNDTRIP_COST_USD), 5),
        "is_open": True,
        "is_resolved": False,
    })
    return base


def _merge_with_ledger(new_records: List[Dict[str, Any]], ledger: pd.DataFrame, data_latest: pd.Timestamp) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    now_utc = _utc_now_iso()
    old_by_id: Dict[str, Dict[str, Any]] = {}
    if not ledger.empty:
        for _, row in ledger.iterrows():
            old_by_id[str(row["signal_id"])] = row.to_dict()

    merged_updates: List[Dict[str, Any]] = []
    counters = {"new_signal_count": 0, "new_forward_open_count": 0, "new_late_backfill_count": 0, "newly_resolved_forward_count": 0}

    for rec in new_records:
        sid = str(rec["signal_id"])
        old = old_by_id.get(sid)
        is_new = old is None
        if is_new:
            rec["first_seen_utc"] = now_utc
            rec["first_seen_data_time"] = str(data_latest)
            if bool(rec.get("is_open")):
                rec["first_seen_class"] = "FORWARD_OPEN_FIRST_SEEN_BEFORE_OUTCOME"
                counters["new_forward_open_count"] += 1
            elif bool(rec.get("is_resolved")):
                rec["first_seen_class"] = "LATE_DETECTED_ALREADY_RESOLVED"
                counters["new_late_backfill_count"] += 1
            else:
                rec["first_seen_class"] = "UNRESOLVED_FIRST_SEEN"
            rec["previous_status"] = None
            counters["new_signal_count"] += 1
        else:
            rec["first_seen_utc"] = old.get("first_seen_utc")
            rec["first_seen_data_time"] = old.get("first_seen_data_time")
            rec["first_seen_class"] = old.get("first_seen_class")
            rec["previous_status"] = old.get("status")
            prior_open = str(old.get("status", "")).startswith("OPEN") or str(old.get("is_open", "")).lower() in {"true", "1"}
            if prior_open and bool(rec.get("is_resolved")):
                counters["newly_resolved_forward_count"] += 1

        rec["forward_valid_outcome"] = False
        if bool(rec.get("is_open")):
            rec["forward_valid_outcome"] = True
        elif bool(rec.get("is_resolved")) and rec.get("exit_time") and rec.get("first_seen_data_time"):
            try:
                rec["forward_valid_outcome"] = pd.Timestamp(rec["first_seen_data_time"]) <= pd.Timestamp(rec["exit_time"])
            except Exception:
                rec["forward_valid_outcome"] = False

        rec["last_seen_utc"] = now_utc
        rec["last_seen_data_time"] = str(data_latest)
        merged_updates.append(rec)

    update_df = pd.DataFrame(merged_updates)
    if ledger.empty:
        final = update_df
    else:
        untouched = ledger[~ledger["signal_id"].astype(str).isin(set(update_df["signal_id"].astype(str)))] if not update_df.empty else ledger
        final = pd.concat([untouched, update_df], ignore_index=True, sort=False)
    return final, counters


def _metric_summary(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {"events": 0, "pf_x1": 0.0, "pf_x4": 0.0, "total_x1": 0.0, "win_rate_x1": 0.0}
    is_resolved = df.get("is_resolved", pd.Series(dtype=object)).astype(str).str.lower().isin(["true", "1"])
    r = df.loc[is_resolved].copy()
    if r.empty or "net_x1" not in r.columns:
        return {"events": 0, "pf_x1": 0.0, "pf_x4": 0.0, "total_x1": 0.0, "win_rate_x1": 0.0}
    n1 = pd.to_numeric(r["net_x1"], errors="coerce").dropna()
    n4 = pd.to_numeric(r["net_x4"], errors="coerce").dropna() if "net_x4" in r.columns else pd.Series(dtype=float)
    return {
        "events": int(len(n1)),
        "pf_x1": round(float(profit_factor(n1)), 4) if len(n1) else 0.0,
        "pf_x4": round(float(profit_factor(n4)), 4) if len(n4) else 0.0,
        "total_x1": round(float(n1.sum()), 4) if len(n1) else 0.0,
        "win_rate_x1": round(float((n1 > 0).mean()), 4) if len(n1) else 0.0,
    }


def _status_decision(counters: Dict[str, Any], open_count: int) -> str:
    if open_count > 0:
        return "STAGE28D_META_GATE_FORWARD_SIGNAL_OPEN_RESEARCH_ONLY"
    if counters.get("newly_resolved_forward_count", 0) > 0:
        return "STAGE28D_META_GATE_FORWARD_OUTCOME_AVAILABLE_RESEARCH_ONLY"
    if counters.get("new_late_backfill_count", 0) > 0:
        return "STAGE28D_META_GATE_LATE_DETECTED_REVIEW_CADENCE_RESEARCH_ONLY"
    return "STAGE28D_NO_ACTIVE_META_GATE_FORWARD_SIGNAL_RESEARCH_ONLY"


def _markdown_table(df: pd.DataFrame, cols: List[str], limit: int) -> str:
    if df.empty:
        return "No rows."
    show = df.copy()
    for c in cols:
        if c not in show.columns:
            show[c] = None
    show = show[cols].head(limit)

    def fmt(v: Any) -> str:
        if isinstance(v, (list, tuple, set)):
            return ", ".join(str(x) for x in v)
        if isinstance(v, dict):
            return json.dumps(v, ensure_ascii=False, sort_keys=True)
        if v is None:
            return ""
        try:
            if pd.isna(v):
                return ""
        except Exception:
            pass
        if isinstance(v, (float, np.floating)):
            if math.isinf(float(v)):
                return "inf"
            return f"{float(v):.4f}".rstrip("0").rstrip(".")
        return str(v).replace("|", "/")

    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    rows = ["| " + " | ".join(fmt(row[c]) for c in cols) + " |" for _, row in show.iterrows()]
    return "\n".join([header, sep] + rows)


def render_markdown(report: Dict[str, Any], recent_df: pd.DataFrame, ledger_df: pd.DataFrame, gate_diag: pd.DataFrame) -> str:
    lines: List[str] = []
    lines.append("# Stage28D Forward-Safe Meta-Gate Forward-Shadow Tracker")
    lines.append("")
    lines.append(f"Generated UTC: {report['generated_utc']}")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append("```text")
    lines.append(str(report["decision"]))
    lines.append("```")
    lines.append("")
    lines.append("## Scope guardrails")
    lines.append("")
    lines.append("- Research/shadow only.")
    lines.append("- Stage18A, Stage23D, Stage25D, and Stage27D remain unchanged.")
    lines.append("- No EA change, no automatic trading, no paper/live/order authorization.")
    lines.append("- Candles are DB-first from SQLite; AMarkets CSV fallback is disabled.")
    lines.append("- The meta-gate uses only forward-safe features known at entry time.")
    lines.append("- Quantile thresholds are expanding/event-by-event and use only prior canonical candidate events.")
    lines.append("")
    lines.append("## Tracked candidate and meta-gate")
    lines.append("")
    lines.append(f"- Candidate: `{PRIMARY_CANDIDATE.name}`")
    lines.append("- Family: `london_oneway_continuation`")
    lines.append(f"- Gate: `{GATE_NAME}`")
    lines.append(f"- Gate rule: `london_range >= prior-event q{int(round(LONDON_Q*100))}` AND `prior_day_range >= prior-event q{int(round(PRIOR_Q*100))}`")
    lines.append(f"- Minimum prior calibration events: `{MIN_CALIB_EVENTS}`")
    lines.append("- Parameters:")
    lines.append("```json")
    lines.append(json.dumps(PRIMARY_CANDIDATE.params, indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")
    lines.append("## DB source of truth")
    lines.append("")
    for key, val in report["data"].get("db_meta", {}).items():
        lines.append(f"- {key}: `{val}`")
    lines.append(f"- M1 rows used: `{report['data']['m1_rows']}` | span: `{report['data']['m1_start']} → {report['data']['m1_end']}`")
    lines.append(f"- H1 rows used: `{report['data']['h1_rows']}` | span: `{report['data']['h1_start']} → {report['data']['h1_end']}`")
    lines.append(f"- M15 rows derived: `{report['data']['m15_rows']}` | span: `{report['data']['m15_start']} → {report['data']['m15_end']}`")
    lines.append("")
    lines.append("## Gate diagnostics")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(_finite_for_json(report["gate"]), indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")
    lines.append("## Run counters")
    lines.append("")
    for key, val in report["counters"].items():
        lines.append(f"- {key}: {val}")
    lines.append(f"- open_signal_count_now: {report['open_signal_count_now']}")
    lines.append(f"- resolved_signal_count_in_ledger: {report['resolved_signal_count_in_ledger']}")
    lines.append(f"- forward_valid_resolved_count: {report['forward_valid_resolved_count']}")
    lines.append("")
    lines.append("## Forward-valid resolved metric snapshot")
    lines.append("")
    lines.append("These metrics include only outcomes whose first recorded observation happened before or at exit time.")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(report["forward_valid_metrics"], indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")
    lines.append("## Recent meta-gate tracked events")
    lines.append("")
    recent_cols = [
        "status", "first_seen_class", "forward_valid_outcome", "signal_time", "direction",
        "london_range", "london_range_threshold", "prior_day_range", "prior_day_range_threshold", "calib_events_used",
        "entry_time", "exit_time", "exit_reason", "net_x1", "floating_net_x1",
    ]
    if not recent_df.empty:
        recent_sorted = recent_df.copy()
        recent_sorted["_signal_dt"] = pd.to_datetime(recent_sorted["signal_time"], errors="coerce")
        recent_sorted = recent_sorted.sort_values("_signal_dt", ascending=False).drop(columns=["_signal_dt"])
    else:
        recent_sorted = recent_df
    lines.append(_markdown_table(recent_sorted, recent_cols, MAX_RECENT_ROWS_REPORT))
    lines.append("")
    lines.append("## Meta-gate diagnostics in current lookback")
    lines.append("")
    diag_cols = [
        "signal_time", "direction", "stage28d_gate_pass", "stage28d_reason", "calib_events_used",
        "london_range", "london_range_threshold", "prior_day_range", "prior_day_range_threshold",
    ]
    lines.append(_markdown_table(gate_diag.sort_values("signal_time", ascending=False) if not gate_diag.empty else gate_diag, diag_cols, MAX_RECENT_ROWS_REPORT))
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("- This tracker is research-shadow only; an open signal is not an order instruction.")
    lines.append("- `LATE_DETECTED_ALREADY_RESOLVED` means the signal was first seen after the outcome was already knowable; it is not forward proof.")
    lines.append("- Stage28D tracks the Stage28C validated meta-gate, but forward evidence still has to be collected separately.")
    lines.append("- The active operational suite remains unchanged until this tracker accumulates forward-valid outcomes.")
    lines.append("")
    lines.append("## Operational reminder")
    lines.append("")
    lines.append("```bash")
    lines.append("cd ~/Desktop/xauusd-trader")
    lines.append("python3 -m app.run_active_shadow_suite")
    lines.append("python3 -m app.stage28d_forward_safe_meta_gate_tracker")
    lines.append("```")
    lines.append("")
    lines.append("## Output files")
    lines.append("")
    lines.append(f"- `{REPORT_JSON}`")
    lines.append(f"- `{REPORT_MD}`")
    lines.append(f"- `{LEDGER_PATH}`")
    lines.append(f"- `{RECENT_EVENTS_CSV}`")
    lines.append(f"- `{GATE_DIAG_CSV}`")
    lines.append(f"- `{SCHEMA_DIAG_CSV}`")
    lines.append("")
    return "\n".join(lines)


def write_error_report(error: Exception) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"decision": "STAGE28D_ERROR_DIAGNOSTIC_ONLY", "error": f"{type(error).__name__}: {error}"}
    REPORT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    REPORT_MD.write_text(
        "\n".join([
            "# Stage28D Forward-Safe Meta-Gate Forward-Shadow Tracker",
            "",
            "## Decision",
            "",
            "```text",
            "STAGE28D_ERROR_DIAGNOSTIC_ONLY",
            "```",
            "",
            "## Error",
            "",
            "```text",
            f"{type(error).__name__}: {error}",
            "```",
            "",
            "## Interpretation",
            "",
            "- This is diagnostic only and does not change active trackers, EA, paper/live, or orders.",
            "- AMarkets CSV fallback remains disabled; fix DB/schema/gate logic rather than falling back to CSV.",
        ]),
        encoding="utf-8",
    )


def main() -> None:
    try:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        generated_utc = _utc_now_iso()

        m1, h1, m15, db_meta, schema_diag = load_market_data_db_first()
        data_latest = pd.Timestamp(m1["time"].max())
        lookback_start = data_latest - pd.Timedelta(hours=LOOKBACK_HOURS)

        m15_atr = merge_atr(m15, h1)
        raw_events = events_london_oneway_continuation(m15_atr, PRIMARY_CANDIDATE.params)
        if raw_events.empty:
            enriched = raw_events.copy()
            gated_all = raw_events.copy()
            recent_diag = pd.DataFrame()
            recent_gated = raw_events.copy()
            gate_info = {
                "gate_name": GATE_NAME,
                "events_before_gate_total": 0,
                "gate_kept_total": 0,
                "gate_dropped_total": 0,
                "events_before_gate_recent": 0,
                "gate_kept_recent": 0,
                "gate_dropped_recent": 0,
            }
        else:
            enriched_features = enrich_events_with_forward_safe_features(raw_events, m15)
            enriched, gate_info = apply_expanding_meta_gate(enriched_features)
            recent_diag = enriched.loc[enriched["signal_time_dt"] >= lookback_start].copy()
            recent_gated = recent_diag.loc[recent_diag["stage28d_gate_pass"].fillna(False).astype(bool)].copy()
            gate_info.update(
                {
                    "events_before_gate_recent": int(len(recent_diag)),
                    "gate_kept_recent": int(len(recent_gated)),
                    "gate_dropped_recent": int(len(recent_diag) - len(recent_gated)),
                    "gate_retained_ratio_recent": float(len(recent_gated) / len(recent_diag)) if len(recent_diag) else 0.0,
                    "lookback_hours": LOOKBACK_HOURS,
                }
            )
            gated_all = enriched.loc[enriched["stage28d_gate_pass"].fillna(False).astype(bool)].copy()

        new_records: List[Dict[str, Any]] = []
        iterator = recent_gated.sort_values("signal_time").iterrows() if not recent_gated.empty else []
        for _, ev in iterator:
            new_records.append(_resolve_event_forward(m1, ev, PRIMARY_CANDIDATE, data_latest))

        ledger = _read_ledger()
        final_ledger, counters = _merge_with_ledger(new_records, ledger, data_latest)
        _write_ledger(final_ledger)

        recent_df = pd.DataFrame(new_records)
        recent_df.to_csv(RECENT_EVENTS_CSV, index=False)
        if recent_diag is not None and not recent_diag.empty:
            keep_cols = [
                "signal_time", "direction", "stage28d_gate_pass", "stage28d_reason", "calib_events_used",
                "london_range", "london_range_threshold", "prior_day_range", "prior_day_range_threshold",
                "asia_range", "london_eff", "asia_eff",
            ]
            for col in keep_cols:
                if col not in recent_diag.columns:
                    recent_diag[col] = np.nan
            recent_diag[keep_cols].to_csv(GATE_DIAG_CSV, index=False)
            gate_diag_for_md = recent_diag[keep_cols].copy()
        else:
            pd.DataFrame().to_csv(GATE_DIAG_CSV, index=False)
            gate_diag_for_md = pd.DataFrame()

        if not final_ledger.empty:
            is_open = final_ledger.get("is_open", pd.Series(dtype=object)).astype(str).str.lower().isin(["true", "1"])
            is_resolved = final_ledger.get("is_resolved", pd.Series(dtype=object)).astype(str).str.lower().isin(["true", "1"])
            forward_valid = final_ledger.get("forward_valid_outcome", pd.Series(dtype=object)).astype(str).str.lower().isin(["true", "1"])
            open_count = int(is_open.sum())
            resolved_count = int(is_resolved.sum())
            forward_valid_resolved = final_ledger[is_resolved & forward_valid].copy()
        else:
            open_count = 0
            resolved_count = 0
            forward_valid_resolved = pd.DataFrame()

        decision = _status_decision(counters, open_count)
        report: Dict[str, Any] = {
            "generated_utc": generated_utc,
            "decision": decision,
            "scope": {
                "research_shadow_only": True,
                "active_suite_unchanged": True,
                "stage18a_unchanged": True,
                "stage23d_unchanged": True,
                "stage25d_unchanged": True,
                "stage27d_unchanged": True,
                "no_ea_change": True,
                "no_automatic_trading": True,
                "no_paper_live_order_authorization": True,
                "db_first": True,
                "csv_fallback_enabled": False,
                "forward_safe_features_only": True,
                "expanding_thresholds_only": True,
            },
            "candidate": {"name": PRIMARY_CANDIDATE.name, "family": PRIMARY_CANDIDATE.family, "params": PRIMARY_CANDIDATE.params},
            "gate": gate_info,
            "data": {
                "db_meta": db_meta,
                "m1_rows": int(len(m1)),
                "m1_start": str(pd.Timestamp(m1["time"].min())),
                "m1_end": str(pd.Timestamp(m1["time"].max())),
                "h1_rows": int(len(h1)),
                "h1_start": str(pd.Timestamp(h1["time"].min())),
                "h1_end": str(pd.Timestamp(h1["time"].max())),
                "m15_rows": int(len(m15)),
                "m15_start": str(pd.Timestamp(m15["time"].min())),
                "m15_end": str(pd.Timestamp(m15["time"].max())),
            },
            "settings": {
                "lookback_hours": LOOKBACK_HOURS,
                "gate_name": GATE_NAME,
                "london_range_quantile": LONDON_Q,
                "prior_day_range_quantile": PRIOR_Q,
                "min_calib_events": MIN_CALIB_EVENTS,
                "max_recent_rows_report": MAX_RECENT_ROWS_REPORT,
            },
            "counters": {
                **counters,
                "recent_events_before_gate": int(gate_info.get("events_before_gate_recent", 0)),
                "recent_events_after_gate": int(gate_info.get("gate_kept_recent", 0)),
                "ledger_total_rows": int(len(final_ledger)),
            },
            "open_signal_count_now": open_count,
            "resolved_signal_count_in_ledger": resolved_count,
            "forward_valid_resolved_count": int(len(forward_valid_resolved)),
            "forward_valid_metrics": _metric_summary(forward_valid_resolved),
            "historical_gate_total_events": int(len(gated_all)) if gated_all is not None else 0,
            "output_files": {
                "report_json": str(REPORT_JSON),
                "report_md": str(REPORT_MD),
                "ledger_csv": str(LEDGER_PATH),
                "recent_events_csv": str(RECENT_EVENTS_CSV),
                "gate_diag_csv": str(GATE_DIAG_CSV),
                "schema_diag_csv": str(SCHEMA_DIAG_CSV),
            },
        }

        REPORT_JSON.write_text(json.dumps(_finite_for_json(report), indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        REPORT_MD.write_text(render_markdown(report, recent_df, final_ledger, gate_diag_for_md), encoding="utf-8")
        if schema_diag is not None and not schema_diag.empty:
            schema_diag.to_csv(SCHEMA_DIAG_CSV, index=False)
        print(json.dumps({"stage": STAGE_NAME, "decision": decision, "report_md": str(REPORT_MD)}, ensure_ascii=False))
    except Exception as exc:
        write_error_report(exc)
        print(json.dumps({"stage": STAGE_NAME, "decision": "STAGE28D_ERROR_DIAGNOSTIC_ONLY", "error": str(exc), "report_md": str(REPORT_MD)}, ensure_ascii=False))
        raise


if __name__ == "__main__":
    main()
