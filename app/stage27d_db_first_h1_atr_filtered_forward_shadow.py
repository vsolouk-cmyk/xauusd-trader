#!/usr/bin/env python3
"""
Stage27D — DB-first H1 ATR gated forward-shadow tracker for the canonical Stage23/25 lineage.

Research/shadow-only module. It does NOT modify Stage18A, Stage23D, Stage25D, EA,
paper/live mode, or orders.

Purpose
-------
Stage27C validated the `h1_atr_drop_low30_strict_completed` no-trade gate around the
canonical Stage23B/C lineage. Stage27D tracks that same canonical candidate forward,
using only a fully completed H1 candle at/ before the candidate signal time.

Anti-leakage rule
-----------------
For left-labeled H1 bars, the H1 feature used for a signal at `signal_time` must satisfy:

    h1_bar_start + 1 hour <= signal_time

No current/incomplete H1 candle is used.

Run:
    cd ~/Desktop/xauusd-trader
    python3 -m app.stage27d_db_first_h1_atr_filtered_forward_shadow
    cat data/reports/stage27d_db_first_h1_atr_filtered_forward_shadow/stage27d_db_first_h1_atr_filtered_forward_shadow.md
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

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
        "Stage27D depends on app.stage23b_continuation_no_trade_discovery. "
        "Apply/run Stage23B before Stage27D. Original import error: " + str(exc)
    )

try:
    from app.stage25c_deduped_filter_validation import load_bars_from_db
except Exception as exc:  # pragma: no cover
    raise RuntimeError(
        "Stage27D depends on app.stage25c_deduped_filter_validation for DB-first candle loading. "
        "Apply/run Stage25C before Stage27D. Original import error: " + str(exc)
    )


STAGE_NAME = "stage27d_db_first_h1_atr_filtered_forward_shadow"
REPORT_DIR = Path("data/reports") / STAGE_NAME
LEDGER_PATH = REPORT_DIR / "stage27d_h1_atr_filtered_forward_shadow_ledger.csv"
REPORT_MD = REPORT_DIR / "stage27d_db_first_h1_atr_filtered_forward_shadow.md"
REPORT_JSON = REPORT_DIR / "stage27d_db_first_h1_atr_filtered_forward_shadow.json"
RECENT_EVENTS_CSV = REPORT_DIR / "stage27d_recent_h1_atr_filtered_events.csv"
GATE_DIAG_CSV = REPORT_DIR / "stage27d_h1_atr_gate_diagnostics.csv"
SCHEMA_DIAG_CSV = REPORT_DIR / "stage27d_db_schema_diagnostic.csv"

DB_PATH = Path(os.getenv("STAGE27D_DB_PATH", "data/local/xauusd_local_store.sqlite")).expanduser()
LOOKBACK_HOURS = int(os.getenv("STAGE27D_LOOKBACK_HOURS", "336"))
MAX_RECENT_ROWS_REPORT = int(os.getenv("STAGE27D_MAX_RECENT_ROWS_REPORT", "25"))
MIN_CALIBRATION_DAYS = int(os.getenv("STAGE27D_MIN_CALIBRATION_DAYS", "250"))
ATR_PERIOD = int(os.getenv("STAGE27D_H1_ATR_PERIOD", "20"))
GATE_QUANTILE = float(os.getenv("STAGE27D_H1_ATR_GATE_QUANTILE", "0.30"))
GATE_NAME = os.getenv("STAGE27D_GATE_NAME", "h1_atr_drop_low30_strict_completed").strip()

# Canonical candidate from Stage25C:
# S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65
PRIMARY_CANDIDATE = Candidate(
    "london_oneway_continuation",
    "S27D_H1_ATR_FILTERED_S23B_B_eff0.60_pb0.1_h180_tp0.6_sl0.65_h1atr_drop_low30",
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


class Stage27DError(RuntimeError):
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
    raise Stage27DError("OHLC bars have no time/timestamp column.")


def _to_time_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    tcol = _time_column(out)
    if tcol != "time":
        out = out.rename(columns={tcol: "time"})
    out["time"] = pd.to_datetime(out["time"], utc=True, errors="coerce")
    for c in ["open", "high", "low", "close"]:
        if c not in out.columns:
            raise Stage27DError(f"OHLC bars missing {c} column.")
        out[c] = pd.to_numeric(out[c], errors="coerce")
    if "volume" not in out.columns:
        out["volume"] = 0.0
    out = out.dropna(subset=["time", "open", "high", "low", "close"]).sort_values("time").reset_index(drop=True)
    return out


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
        raise Stage27DError("No M1 OHLC candles found from SQLite DB. CSV fallback is intentionally disabled.")
    h1 = _to_time_df(h1_raw) if h1_raw is not None and not h1_raw.empty else pd.DataFrame()
    if h1.empty:
        h1 = _resample_ohlcv(m1, "1h")
        db_meta["h1_mode_stage27d"] = "derived_from_m1_resample"
    m15 = _resample_ohlcv(m1, "15min")
    db_meta.update(
        {
            "db_first": True,
            "csv_fallback_enabled": False,
            "m1_rows_stage27d": int(len(m1)),
            "h1_rows_stage27d": int(len(h1)),
            "m15_rows_stage27d": int(len(m15)),
        }
    )
    return m1, h1, m15, db_meta, schema_diag


def build_h1_atr_features(h1: pd.DataFrame) -> pd.DataFrame:
    out = h1.copy().sort_values("time").reset_index(drop=True)
    out["time"] = pd.to_datetime(out["time"], utc=True, errors="coerce")
    for c in ["open", "high", "low", "close"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(subset=["time", "open", "high", "low", "close"]).reset_index(drop=True)
    if out.empty:
        raise Stage27DError("No H1 OHLC candles available for H1 ATR gate.")

    prev_close = out["close"].shift(1)
    tr = pd.concat(
        [
            (out["high"] - out["low"]).abs(),
            (out["high"] - prev_close).abs(),
            (out["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr_min_periods = min(max(5, ATR_PERIOD // 2), ATR_PERIOD)
    out["h1_atr"] = tr.rolling(ATR_PERIOD, min_periods=atr_min_periods).mean()

    calibration_window = MIN_CALIBRATION_DAYS * 24
    q = GATE_QUANTILE
    q_col = f"h1_atr_q{int(round(q * 100))}"
    # Shift(1): threshold uses only H1 bars before the current H1 bar.
    out[q_col] = out["h1_atr"].rolling(calibration_window, min_periods=MIN_CALIBRATION_DAYS).quantile(q).shift(1)
    out["h1_bar_start"] = out["time"]
    out["h1_bar_end"] = out["time"] + pd.Timedelta(hours=1)
    return out[["h1_bar_start", "h1_bar_end", "h1_atr", q_col]].copy()


def apply_h1_atr_gate(events: pd.DataFrame, h1: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    q_col = f"h1_atr_q{int(round(GATE_QUANTILE * 100))}"
    if events.empty:
        return events.copy(), pd.DataFrame(), {"gate_name": GATE_NAME, "events_before_gate": 0, "gate_kept": 0, "gate_dropped": 0}
    features = build_h1_atr_features(h1).sort_values("h1_bar_end").reset_index(drop=True)
    ev = events.copy()
    ev["signal_time_dt"] = pd.to_datetime(ev["signal_time"], utc=True, errors="coerce")
    ev = ev.dropna(subset=["signal_time_dt"]).sort_values("signal_time_dt").reset_index(drop=True)
    if ev.empty:
        return ev, pd.DataFrame(), {"gate_name": GATE_NAME, "events_before_gate": 0, "gate_kept": 0, "gate_dropped": 0}

    merged = pd.merge_asof(
        ev,
        features,
        left_on="signal_time_dt",
        right_on="h1_bar_end",
        direction="backward",
        allow_exact_matches=True,
    )
    # Strict anti-leakage: completed H1 bar must end before or at the signal timestamp.
    merged["strict_completed_h1_ok"] = merged["h1_bar_end"].notna() & (merged["h1_bar_end"] <= merged["signal_time_dt"])
    merged["completed_h1_age_minutes"] = (merged["signal_time_dt"] - merged["h1_bar_end"]).dt.total_seconds() / 60.0
    gate_mask = (
        merged["strict_completed_h1_ok"].fillna(False).astype(bool)
        & pd.to_numeric(merged["h1_atr"], errors="coerce").notna()
        & pd.to_numeric(merged[q_col], errors="coerce").notna()
        & (pd.to_numeric(merged["h1_atr"], errors="coerce") > pd.to_numeric(merged[q_col], errors="coerce"))
    )
    merged["stage27d_gate_pass"] = gate_mask
    merged["stage27d_gate_name"] = GATE_NAME
    passed = merged.loc[gate_mask].copy()

    diag = merged[[
        "signal_time", "direction", "stage27d_gate_pass", "h1_bar_start", "h1_bar_end", "completed_h1_age_minutes", "h1_atr", q_col
    ]].copy()
    info = {
        "gate_name": GATE_NAME,
        "gate_quantile": GATE_QUANTILE,
        "h1_atr_period": ATR_PERIOD,
        "min_calibration_days": MIN_CALIBRATION_DAYS,
        "events_before_gate": int(len(merged)),
        "gate_kept": int(gate_mask.sum()),
        "gate_dropped": int((~gate_mask).sum()),
        "gate_retained_ratio": float(gate_mask.mean()) if len(gate_mask) else 0.0,
        "strict_completed_h1_missing": int(merged["h1_bar_end"].isna().sum()),
        "strict_completed_h1_not_complete_count": int((~merged["strict_completed_h1_ok"].fillna(False).astype(bool)).sum()),
        "min_completed_h1_age_minutes": float(merged.loc[merged["strict_completed_h1_ok"], "completed_h1_age_minutes"].min()) if merged["strict_completed_h1_ok"].any() else None,
        "median_completed_h1_age_minutes": float(merged.loc[merged["strict_completed_h1_ok"], "completed_h1_age_minutes"].median()) if merged["strict_completed_h1_ok"].any() else None,
        "max_completed_h1_age_minutes": float(merged.loc[merged["strict_completed_h1_ok"], "completed_h1_age_minutes"].max()) if merged["strict_completed_h1_ok"].any() else None,
    }
    return passed, diag, info


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
    return int(pd.Timestamp(ts).tz_convert("UTC").value if pd.Timestamp(ts).tzinfo else pd.Timestamp(ts).tz_localize("UTC").value)


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

    q_col = f"h1_atr_q{int(round(GATE_QUANTILE * 100))}"
    base: Dict[str, Any] = {
        "signal_id": sid,
        "candidate": candidate.name,
        "family": candidate.family,
        "stage27d_gate_name": GATE_NAME,
        "signal_time": str(signal_time),
        "direction": direction,
        "atr": round(float(atr), 6) if np.isfinite(atr) else None,
        "h1_bar_start": str(event.get("h1_bar_start")) if pd.notna(event.get("h1_bar_start", pd.NaT)) else None,
        "h1_bar_end": str(event.get("h1_bar_end")) if pd.notna(event.get("h1_bar_end", pd.NaT)) else None,
        "completed_h1_age_minutes": round(_safe_float(event.get("completed_h1_age_minutes", np.nan), np.nan), 4) if pd.notna(event.get("completed_h1_age_minutes", np.nan)) else None,
        "h1_atr": round(_safe_float(event.get("h1_atr", np.nan), np.nan), 6) if pd.notna(event.get("h1_atr", np.nan)) else None,
        q_col: round(_safe_float(event.get(q_col, np.nan), np.nan), 6) if pd.notna(event.get(q_col, np.nan)) else None,
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
        return "STAGE27D_H1_ATR_FILTERED_FORWARD_SIGNAL_OPEN_RESEARCH_ONLY"
    if counters.get("newly_resolved_forward_count", 0) > 0:
        return "STAGE27D_H1_ATR_FILTERED_FORWARD_OUTCOME_AVAILABLE_RESEARCH_ONLY"
    if counters.get("new_late_backfill_count", 0) > 0:
        return "STAGE27D_H1_ATR_FILTERED_LATE_DETECTED_REVIEW_CADENCE_RESEARCH_ONLY"
    return "STAGE27D_NO_ACTIVE_H1_ATR_FILTERED_FORWARD_SIGNAL_RESEARCH_ONLY"


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
    lines.append("# Stage27D DB-First H1 ATR Filtered Forward-Shadow Tracker")
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
    lines.append("- Stage18A v2 remains unchanged and remains the active operational forward-shadow runner.")
    lines.append("- Stage23D and Stage25D remain separate; this module does not modify either one.")
    lines.append("- No EA change, no automatic trading, no paper/live/order authorization.")
    lines.append("- Candles are DB-first from SQLite; AMarkets CSV fallback is disabled.")
    lines.append("- H1 ATR gate uses only a completed H1 bar with `h1_bar_end <= signal_time`.")
    lines.append("")
    lines.append("## Tracked candidate and gate")
    lines.append("")
    lines.append(f"- Candidate: `{PRIMARY_CANDIDATE.name}`")
    lines.append("- Family: `london_oneway_continuation`")
    lines.append(f"- Gate: `{GATE_NAME}`")
    lines.append(f"- H1 ATR quantile: `{GATE_QUANTILE}`")
    lines.append(f"- H1 ATR period: `{ATR_PERIOD}`")
    lines.append(f"- Minimum calibration days: `{MIN_CALIBRATION_DAYS}`")
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
    lines.append("## Gate diagnostics in current lookback")
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
    lines.append("## Recent H1 ATR filtered tracked events")
    lines.append("")
    recent_cols = [
        "status", "first_seen_class", "forward_valid_outcome", "signal_time", "direction",
        "h1_bar_end", "completed_h1_age_minutes", "h1_atr", f"h1_atr_q{int(round(GATE_QUANTILE*100))}",
        "entry_time", "exit_time", "exit_reason", "net_x1", "floating_net_x1"
    ]
    if not recent_df.empty:
        recent_sorted = recent_df.copy()
        recent_sorted["_signal_dt"] = pd.to_datetime(recent_sorted["signal_time"], errors="coerce")
        recent_sorted = recent_sorted.sort_values("_signal_dt", ascending=False).drop(columns=["_signal_dt"])
    else:
        recent_sorted = recent_df
    lines.append(_markdown_table(recent_sorted, recent_cols, MAX_RECENT_ROWS_REPORT))
    lines.append("")
    lines.append("## H1 ATR gate diagnostics in current lookback")
    lines.append("")
    lines.append(_markdown_table(gate_diag.sort_values("signal_time", ascending=False) if not gate_diag.empty else gate_diag, [
        "signal_time", "direction", "stage27d_gate_pass", "h1_bar_end", "completed_h1_age_minutes", "h1_atr", f"h1_atr_q{int(round(GATE_QUANTILE*100))}"
    ], MAX_RECENT_ROWS_REPORT))
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("- This tracker is research-shadow only; an open signal is not an order instruction.")
    lines.append("- `LATE_DETECTED_ALREADY_RESOLVED` means the signal was first seen after the outcome was already knowable; it is not forward proof.")
    lines.append("- This module tracks the Stage27C validated H1 ATR no-trade gate around the canonical Stage23/25 lineage.")
    lines.append("- The gate is anti-leakage constrained: only completed H1 bars at or before signal time are used.")
    lines.append("- Keep Stage18A v2, Stage23D, and Stage25D running separately after each AMarkets CSV refresh/import cycle.")
    lines.append("")
    lines.append("## Operational reminder")
    lines.append("")
    lines.append("```bash")
    lines.append("cd ~/Desktop/xauusd-trader")
    lines.append("python3 -m app.stage18a_unified_shadow_ops_cycle")
    lines.append("python3 -m app.stage23d_forward_shadow_candidate")
    lines.append("python3 -m app.stage25d_db_first_filtered_forward_shadow")
    lines.append("python3 -m app.stage27d_db_first_h1_atr_filtered_forward_shadow")
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
    payload = {"decision": "STAGE27D_ERROR_DIAGNOSTIC_ONLY", "error": f"{type(error).__name__}: {error}"}
    REPORT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    REPORT_MD.write_text(
        "\n".join([
            "# Stage27D DB-First H1 ATR Filtered Forward-Shadow Tracker",
            "",
            "## Decision",
            "",
            "```text",
            "STAGE27D_ERROR_DIAGNOSTIC_ONLY",
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
            "- This is diagnostic only and does not change Stage18A, Stage23D, Stage25D, EA, paper/live, or orders.",
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
        all_events = events_london_oneway_continuation(m15_atr, PRIMARY_CANDIDATE.params)
        if all_events.empty:
            recent_events = all_events.copy()
            gated_events = all_events.copy()
            gate_diag = pd.DataFrame()
            gate_info = {"events_before_gate": 0, "gate_kept": 0, "gate_dropped": 0, "gate_retained_ratio": 0.0}
        else:
            all_events["signal_time_dt"] = pd.to_datetime(all_events["signal_time"], utc=True, errors="coerce")
            recent_events = all_events.loc[all_events["signal_time_dt"] >= lookback_start].copy()
            gated_events, gate_diag, gate_info = apply_h1_atr_gate(recent_events, h1)

        new_records: List[Dict[str, Any]] = []
        iterator = gated_events.sort_values("signal_time").iterrows() if not gated_events.empty else []
        for _, ev in iterator:
            new_records.append(_resolve_event_forward(m1, ev, PRIMARY_CANDIDATE, data_latest))

        ledger = _read_ledger()
        final_ledger, counters = _merge_with_ledger(new_records, ledger, data_latest)
        _write_ledger(final_ledger)

        recent_df = pd.DataFrame(new_records)
        recent_df.to_csv(RECENT_EVENTS_CSV, index=False)
        gate_diag.to_csv(GATE_DIAG_CSV, index=False)

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
                "stage18a_unchanged": True,
                "stage23d_unchanged": True,
                "stage25d_unchanged": True,
                "no_ea_change": True,
                "no_automatic_trading": True,
                "no_paper_live_order_authorization": True,
                "db_first": True,
                "csv_fallback_enabled": False,
                "strict_completed_h1": True,
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
                "gate_quantile": GATE_QUANTILE,
                "h1_atr_period": ATR_PERIOD,
                "min_calibration_days": MIN_CALIBRATION_DAYS,
                "max_recent_rows_report": MAX_RECENT_ROWS_REPORT,
            },
            "counters": {
                **counters,
                "recent_events_before_gate": int(len(recent_events)) if recent_events is not None else 0,
                "recent_events_after_gate": int(len(gated_events)) if gated_events is not None else 0,
                "ledger_total_rows": int(len(final_ledger)),
            },
            "open_signal_count_now": open_count,
            "resolved_signal_count_in_ledger": resolved_count,
            "forward_valid_resolved_count": int(len(forward_valid_resolved)),
            "forward_valid_metrics": _metric_summary(forward_valid_resolved),
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
        REPORT_MD.write_text(render_markdown(report, recent_df, final_ledger, gate_diag), encoding="utf-8")
        if schema_diag is not None and not schema_diag.empty:
            schema_diag.to_csv(SCHEMA_DIAG_CSV, index=False)
        print(json.dumps({"stage": STAGE_NAME, "decision": decision, "report_md": str(REPORT_MD)}, ensure_ascii=False))
    except Exception as exc:
        write_error_report(exc)
        print(json.dumps({"stage": STAGE_NAME, "decision": "STAGE27D_ERROR_DIAGNOSTIC_ONLY", "error": str(exc), "report_md": str(REPORT_MD)}, ensure_ascii=False))
        raise


if __name__ == "__main__":
    main()
