#!/usr/bin/env python3
"""Stage26A DB-first structured behavior discovery for XAUUSD.

Research/shadow only. No EA/paper/live/order authorization.
Reads candles from SQLite as the source of truth; CSV fallback is intentionally disabled.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    from app.stage25c_deduped_filter_validation import load_bars_from_db
except Exception:  # pragma: no cover - handled in run() with a clear diagnostic
    load_bars_from_db = None

STAGE = "stage26a_db_first_structured_behavior_discovery"
REPORT_DIR = Path("data/reports") / STAGE
DB_PATH = Path(os.environ.get("STAGE26A_DB_PATH", "data/local/xauusd_local_store.sqlite"))
MAX_RUNTIME_SECONDS = int(os.environ.get("STAGE26A_MAX_RUNTIME_SECONDS", "210"))
EXACT_RESERVED_SECONDS = int(os.environ.get("STAGE26A_EXACT_RESERVED_SECONDS", "60"))
MAX_CANDIDATES_TOTAL = int(os.environ.get("STAGE26A_MAX_CANDIDATES_TOTAL", "72"))
MAX_EXACT_TOTAL = int(os.environ.get("STAGE26A_MAX_EXACT", "12"))
MAX_EXACT_PER_FAMILY = int(os.environ.get("STAGE26A_MAX_EXACT_PER_FAMILY", "4"))
ROUNDTRIP_COST_X1 = float(os.environ.get("STAGE26A_ROUNDTRIP_COST_X1", "0.35"))
MIN_EVENTS = int(os.environ.get("STAGE26A_MIN_EVENTS", "45"))
BOOT_N = int(os.environ.get("STAGE26A_BOOT_N", "180"))
SEED = int(os.environ.get("STAGE26A_SEED", "2601"))


@dataclass(frozen=True)
class Candidate:
    family: str
    name: str
    params: Dict[str, Any]


class DBFirstLoaderError(RuntimeError):
    pass


def norm_col(c: str) -> str:
    return str(c).strip().lower().replace("<", "").replace(">", "").replace(" ", "_")


def quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def table_info(con: sqlite3.Connection, table: str) -> pd.DataFrame:
    return pd.read_sql_query(f"PRAGMA table_info({quote_ident(table)})", con)


def list_tables(con: sqlite3.Connection) -> List[str]:
    rows = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return [r[0] for r in rows]


def find_col(cols: Iterable[str], options: Iterable[str]) -> Optional[str]:
    by_norm = {norm_col(c): c for c in cols}
    for opt in options:
        if norm_col(opt) in by_norm:
            return by_norm[norm_col(opt)]
    # fuzzy fallback
    opts = [norm_col(o) for o in options]
    for nc, orig in by_norm.items():
        if any(o in nc for o in opts):
            return orig
    return None


def discover_candle_source(con: sqlite3.Connection) -> Dict[str, Any]:
    diagnostics: List[Dict[str, Any]] = []
    for table in list_tables(con):
        try:
            info = table_info(con, table)
        except Exception as exc:
            diagnostics.append({"table": table, "error": str(exc)})
            continue
        cols = info["name"].astype(str).tolist()
        tcol = find_col(cols, ["timestamp", "time", "datetime", "bar_time", "broker_time", "open_time", "date_time"])
        ocol = find_col(cols, ["open", "o"])
        hcol = find_col(cols, ["high", "h"])
        lcol = find_col(cols, ["low", "l"])
        ccol = find_col(cols, ["close", "c"])
        tfcol = find_col(cols, ["timeframe", "tf", "period", "interval"])
        symbol_col = find_col(cols, ["symbol", "ticker", "instrument"])
        count = None
        try:
            count = con.execute(f"SELECT COUNT(*) FROM {quote_ident(table)}").fetchone()[0]
        except Exception:
            pass
        row = {
            "table": table,
            "row_count": count,
            "timestamp_col": tcol,
            "open_col": ocol,
            "high_col": hcol,
            "low_col": lcol,
            "close_col": ccol,
            "timeframe_col": tfcol,
            "symbol_col": symbol_col,
            "usable": bool(tcol and ocol and hcol and lcol and ccol),
        }
        diagnostics.append(row)
        if row["usable"]:
            return row | {"diagnostics": diagnostics}
    raise DBFirstLoaderError("No OHLC candle table found in SQLite DB. CSV fallback is intentionally disabled.")


def normalize_time(s: pd.Series) -> pd.Series:
    if np.issubdtype(s.dtype, np.number):
        mx = float(pd.to_numeric(s, errors="coerce").dropna().max())
        unit = "ms" if mx > 10_000_000_000 else "s"
        return pd.to_datetime(s, unit=unit, utc=True, errors="coerce")
    return pd.to_datetime(s, utc=True, errors="coerce")


def read_candles(con: sqlite3.Connection, source: Dict[str, Any], timeframe: Optional[str]) -> pd.DataFrame:
    table = source["table"]
    tcol, ocol, hcol, lcol, ccol = source["timestamp_col"], source["open_col"], source["high_col"], source["low_col"], source["close_col"]
    tfcol, symbol_col = source.get("timeframe_col"), source.get("symbol_col")
    select_cols = [tcol, ocol, hcol, lcol, ccol]
    aliases = ["timestamp", "open", "high", "low", "close"]
    if tfcol:
        select_cols.append(tfcol); aliases.append("timeframe")
    if symbol_col:
        select_cols.append(symbol_col); aliases.append("symbol")
    select_sql = ", ".join(f"{quote_ident(c)} AS {quote_ident(a)}" for c, a in zip(select_cols, aliases))
    base = f"SELECT {select_sql} FROM {quote_ident(table)}"
    params: List[Any] = []
    where: List[str] = []
    if tfcol and timeframe:
        tf = timeframe.lower()
        tf_values = {
            "m1": ["M1", "1m", "1min", "1", 1, "60", 60],
            "h1": ["H1", "1h", "60m", "60min", "60", 60, "3600", 3600],
        }.get(tf, [timeframe])
        where.append(f"{quote_ident(tfcol)} IN ({','.join(['?']*len(tf_values))})")
        params.extend(tf_values)
    if where:
        base += " WHERE " + " AND ".join(where)
    df = pd.read_sql_query(base, con, params=params)
    if df.empty and tfcol and timeframe:
        # Try no timeframe filter; we will infer below.
        df = pd.read_sql_query(f"SELECT {select_sql} FROM {quote_ident(table)}", con)
    if df.empty:
        return df
    if "symbol" in df.columns:
        # Prefer XAU-like symbol if available, otherwise the largest symbol group.
        sym = df["symbol"].astype(str)
        mask = sym.str.upper().str.contains("XAU|GOLD", regex=True, na=False)
        if mask.any():
            df = df[mask].copy()
        else:
            top = sym.value_counts().index[0]
            df = df[sym == top].copy()
    df["timestamp"] = normalize_time(df["timestamp"])
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["timestamp", "open", "high", "low", "close"]).sort_values("timestamp")
    df = df.drop_duplicates("timestamp", keep="last")
    df = df.set_index("timestamp")[["open", "high", "low", "close"]]
    if timeframe and (not tfcol or "timeframe" not in df.columns):
        # If all bars are mixed in one table without timeframe, infer by interval and filter.
        if len(df) > 2:
            diffs = df.index.to_series().diff().dt.total_seconds()
            target = 60 if timeframe.lower() == "m1" else 3600
            med = diffs.median()
            # If table is already at target granularity, keep it; otherwise caller may resample.
            if target == 60 and med and med > 180:
                return pd.DataFrame(columns=["open", "high", "low", "close"])
    return df


def resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    out = df.resample(rule, label="left", closed="left").agg({"open": "first", "high": "max", "low": "min", "close": "last"})
    return out.dropna()


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        (df["high"] - df["low"]).abs(),
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=max(3, n // 2)).mean()


def add_features(m15: pd.DataFrame, h1: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    m15 = m15.copy()
    h1 = h1.copy()
    m15["atr14"] = atr(m15, 14)
    h1["atr14"] = atr(h1, 14)
    h1["sma20"] = h1["close"].rolling(20, min_periods=10).mean()
    h1["sma50"] = h1["close"].rolling(50, min_periods=25).mean()
    daily = m15.resample("1D", label="left", closed="left").agg({"open": "first", "high": "max", "low": "min", "close": "last", "atr14": "median"}).dropna()
    daily["range"] = daily["high"] - daily["low"]
    daily["direction"] = np.sign(daily["close"] - daily["open"])
    daily["range_med20"] = daily["range"].rolling(20, min_periods=10).median()
    return m15, h1, daily


def get_session(m15: pd.DataFrame, day: pd.Timestamp, start_hour: int, end_hour: int) -> pd.DataFrame:
    start = pd.Timestamp(day).tz_convert("UTC") if pd.Timestamp(day).tzinfo else pd.Timestamp(day, tz="UTC")
    start = start.normalize() + pd.Timedelta(hours=start_hour)
    end = start.normalize() + pd.Timedelta(hours=end_hour)
    return m15[(m15.index >= start) & (m15.index < end)]


def get_entry_bar(m15: pd.DataFrame, day: pd.Timestamp, entry_hour: int) -> Optional[pd.Series]:
    start = (pd.Timestamp(day).tz_convert("UTC") if pd.Timestamp(day).tzinfo else pd.Timestamp(day, tz="UTC")).normalize() + pd.Timedelta(hours=entry_hour)
    end = start + pd.Timedelta(minutes=15)
    sub = m15[(m15.index >= start) & (m15.index < end)]
    if sub.empty:
        return None
    return sub.iloc[0]


def htf_bias_at(h1: pd.DataFrame, ts: pd.Timestamp) -> int:
    hist = h1[h1.index < ts]
    if hist.empty:
        return 0
    r = hist.iloc[-1]
    if pd.isna(r.get("sma20")) or pd.isna(r.get("sma50")):
        return 0
    if r["close"] > r["sma20"] > r["sma50"]:
        return 1
    if r["close"] < r["sma20"] < r["sma50"]:
        return -1
    return 0


def generate_candidates() -> List[Candidate]:
    cands: List[Candidate] = []
    tps = [(0.6, 0.65), (0.8, 0.8)]
    for lm in [0.6, 0.9]:
        for eff in [0.55, 0.7]:
            for pb in [0.15, 0.3]:
                for eh in [13, 14]:
                    for hz in [90, 180]:
                        for tp, sl in tps:
                            name = f"htf_bias_pullback_cont_lm{lm}_eff{eff}_pb{pb}_h{hz}_e{eh}_tp{tp}_sl{sl}"
                            cands.append(Candidate("htf_bias_pullback_continuation", name, {"london_move_atr_min": lm, "eff_min": eff, "pullback_atr_max": pb, "entry_hour": eh, "horizon_min": hz, "tp_atr": tp, "sl_atr": sl}))
    for armax in [0.8, 1.2]:
        for conf in [0.05, 0.15]:
            for hold in [0.0, 0.1]:
                for eh in [13, 14]:
                    for hz in [90, 180]:
                        for tp, sl in tps:
                            name = f"break_pullback_cont_ar{armax}_cf{conf}_hold{hold}_h{hz}_e{eh}_tp{tp}_sl{sl}"
                            cands.append(Candidate("breakout_pullback_continuation", name, {"asia_range_atr_max": armax, "confirm_atr_min": conf, "hold_atr_min": hold, "entry_hour": eh, "horizon_min": hz, "tp_atr": tp, "sl_atr": sl}))
    for lm in [0.6, 0.9]:
        for nyc in [0.05, 0.15]:
            for lmax in [1.4, 2.2]:
                for eh in [14, 15]:
                    for hz in [90, 180]:
                        for tp, sl in tps:
                            name = f"session_transition_imb_lm{lm}_nyc{nyc}_lmax{lmax}_h{hz}_e{eh}_tp{tp}_sl{sl}"
                            cands.append(Candidate("session_transition_imbalance", name, {"london_move_atr_min": lm, "ny_confirm_atr_min": nyc, "london_range_atr_max": lmax, "entry_hour": eh, "horizon_min": hz, "tp_atr": tp, "sl_atr": sl}))
    return cands[:MAX_CANDIDATES_TOTAL]


def events_for_candidate(c: Candidate, m15: pd.DataFrame, h1: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    if m15.empty:
        return pd.DataFrame()
    days = pd.Series(m15.index.normalize().unique()).sort_values().tolist()
    p = c.params
    for day in days[60:]:
        day = pd.Timestamp(day)
        entry = get_entry_bar(m15, day, int(p["entry_hour"]))
        if entry is None or pd.isna(entry.get("atr14")) or entry["atr14"] <= 0:
            continue
        entry_ts = entry.name
        entry_price = float(entry["close"])
        atrv = float(entry["atr14"])
        asia = get_session(m15, day, 0, 7)
        london = get_session(m15, day, 7, 13)
        if asia.empty or london.empty:
            continue
        london_open = float(london.iloc[0]["open"]); london_close = float(london.iloc[-1]["close"])
        london_high = float(london["high"].max()); london_low = float(london["low"].min())
        london_range = london_high - london_low
        london_move = london_close - london_open
        london_dir = int(np.sign(london_move))
        london_eff = abs(london_move) / max(london_range, 1e-9)
        asia_high = float(asia["high"].max()); asia_low = float(asia["low"].min()); asia_range = asia_high - asia_low
        direction = 0
        reason = ""
        if c.family == "htf_bias_pullback_continuation":
            bias = htf_bias_at(h1, entry_ts)
            if bias == 0 or london_dir != bias:
                continue
            if abs(london_move) < p["london_move_atr_min"] * atrv or london_eff < p["eff_min"]:
                continue
            if bias > 0:
                # Pullback cannot be too far below London midpoint; entry must not be late-extension beyond London high.
                if entry_price < (london_low + london_range * 0.45):
                    continue
                if entry_price > london_high + p["pullback_atr_max"] * atrv:
                    continue
            else:
                if entry_price > (london_high - london_range * 0.45):
                    continue
                if entry_price < london_low - p["pullback_atr_max"] * atrv:
                    continue
            direction = bias
            reason = f"bias={bias};london_eff={london_eff:.2f}"
        elif c.family == "breakout_pullback_continuation":
            if asia_range > p["asia_range_atr_max"] * atrv:
                continue
            if london_close > asia_high + p["confirm_atr_min"] * atrv:
                if entry_price < asia_high + p["hold_atr_min"] * atrv:
                    continue
                direction = 1
            elif london_close < asia_low - p["confirm_atr_min"] * atrv:
                if entry_price > asia_low - p["hold_atr_min"] * atrv:
                    continue
                direction = -1
            else:
                continue
            reason = f"asia_range_atr={asia_range/max(atrv,1e-9):.2f}"
        elif c.family == "session_transition_imbalance":
            if london_dir == 0:
                continue
            if abs(london_move) < p["london_move_atr_min"] * atrv:
                continue
            if london_range > p["london_range_atr_max"] * atrv:
                continue
            ny_so_far = get_session(m15, day, 13, int(p["entry_hour"]))
            if ny_so_far.empty and int(p["entry_hour"]) <= 13:
                continue
            if int(p["entry_hour"]) > 13 and not ny_so_far.empty:
                ny_move = float(ny_so_far.iloc[-1]["close"] - ny_so_far.iloc[0]["open"])
                if np.sign(ny_move) != london_dir or abs(ny_move) < p["ny_confirm_atr_min"] * atrv:
                    continue
            direction = london_dir
            reason = f"london_range_atr={london_range/max(atrv,1e-9):.2f}"
        if direction == 0:
            continue
        rows.append({
            "candidate": c.name, "family": c.family, "entry_time": entry_ts, "direction": "long" if direction > 0 else "short",
            "dir_mult": direction, "entry_price": entry_price, "atr": atrv, "horizon_min": int(p["horizon_min"]),
            "tp_atr": float(p["tp_atr"]), "sl_atr": float(p["sl_atr"]), "reason": reason,
        })
    return pd.DataFrame(rows)


def outcome_for_events(events: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return events.copy()
    idx = bars.index
    close = bars["close"].to_numpy(float)
    high = bars["high"].to_numpy(float)
    low = bars["low"].to_numpy(float)
    out_rows: List[Dict[str, Any]] = []
    for _, ev in events.iterrows():
        ts = pd.Timestamp(ev["entry_time"])
        start = idx.searchsorted(ts, side="right")
        end_ts = ts + pd.Timedelta(minutes=int(ev["horizon_min"]))
        end = idx.searchsorted(end_ts, side="right")
        if start >= len(idx) or end <= start:
            continue
        dir_mult = int(ev["dir_mult"]); ep = float(ev["entry_price"]); atrv = float(ev["atr"])
        tp = ep + dir_mult * float(ev["tp_atr"]) * atrv
        sl = ep - dir_mult * float(ev["sl_atr"]) * atrv
        exit_price = float(close[min(end - 1, len(close)-1)]); exit_time = idx[min(end - 1, len(idx)-1)]; exit_reason = "horizon_close"
        for j in range(start, min(end, len(idx))):
            if dir_mult > 0:
                hit_tp = high[j] >= tp; hit_sl = low[j] <= sl
            else:
                hit_tp = low[j] <= tp; hit_sl = high[j] >= sl
            if hit_tp and hit_sl:
                exit_price = sl; exit_time = idx[j]; exit_reason = "sl_conservative"; break
            if hit_sl:
                exit_price = sl; exit_time = idx[j]; exit_reason = "sl"; break
            if hit_tp:
                exit_price = tp; exit_time = idx[j]; exit_reason = "tp"; break
        gross = dir_mult * (exit_price - ep)
        row = ev.to_dict()
        row.update({"exit_time": exit_time, "exit_price": exit_price, "exit_reason": exit_reason, "gross": gross,
                    "net_x1": gross - ROUNDTRIP_COST_X1, "net_x4": gross - 4 * ROUNDTRIP_COST_X1, "net_x6": gross - 6 * ROUNDTRIP_COST_X1})
        out_rows.append(row)
    return pd.DataFrame(out_rows)


def profit_factor(vals: pd.Series) -> float:
    vals = pd.to_numeric(vals, errors="coerce").dropna()
    if vals.empty:
        return 0.0
    gains = vals[vals > 0].sum(); losses = -vals[vals < 0].sum()
    if losses == 0 and gains > 0:
        return float("inf")
    if losses == 0:
        return 0.0
    return float(gains / losses)


def boot_pf_p05(vals: pd.Series, n: int = BOOT_N) -> float:
    vals = pd.to_numeric(vals, errors="coerce").dropna().to_numpy(float)
    if len(vals) < 10:
        return 0.0
    rng = np.random.default_rng(SEED)
    pfs = []
    for _ in range(n):
        sample = rng.choice(vals, size=len(vals), replace=True)
        pfs.append(profit_factor(pd.Series(sample)))
    finite = np.array([x for x in pfs if np.isfinite(x)], dtype=float)
    if len(finite) == 0:
        return float("inf")
    return float(np.percentile(finite, 5))


def summarize_trades(trades: pd.DataFrame, c: Candidate, proxy: bool = False) -> Dict[str, Any]:
    if trades.empty:
        return {"family": c.family, "name": c.name, "events": 0, "pf_x1": 0.0, "pf_x4": 0.0, "pf_x6": 0.0, "boot_pf_p05_x4": 0.0, "median_x4": 0.0, "total_x4": 0.0, "win_rate_x4": 0.0, "rank_score": 0.0}
    vals = trades["net_x4"]
    pf1 = profit_factor(trades["net_x1"]); pf4 = profit_factor(trades["net_x4"]); pf6 = profit_factor(trades["net_x6"])
    boot = boot_pf_p05(trades["net_x4"], n=max(60, BOOT_N // (2 if proxy else 1)))
    med = float(vals.median()); total = float(vals.sum()); wr = float((vals > 0).mean())
    events = int(len(trades))
    # Penalize high-frequency generic results; prefer cost-robust, non-tiny event counts.
    freq_penalty = max(0.0, (events - 350) / 250.0)
    rank = (min(pf4, 8.0) * 2.2) + (min(pf6, 6.0) * 1.2) + (min(boot, 5.0) * 1.4) + (0.6 if med > 0 else -0.5) - freq_penalty
    decision = "STAGE26A_REJECT"
    if events >= MIN_EVENTS and pf4 >= 1.35 and pf6 >= 1.05 and boot >= 0.95 and total > 0:
        decision = "STAGE26A_PROMOTION_REVIEW_RESEARCH_ONLY"
    elif events >= MIN_EVENTS and pf4 >= 1.1 and pf6 >= 0.9 and total > 0:
        decision = "STAGE26A_WATCHLIST_ONLY"
    return {"decision": decision, "family": c.family, "name": c.name, "events": events, "pf_x1": pf1, "pf_x4": pf4, "pf_x6": pf6, "boot_pf_p05_x4": boot, "median_x4": med, "total_x4": total, "win_rate_x4": wr, "rank_score": rank}


def to_indexed_ohlc(df: pd.DataFrame, *, label: str) -> pd.DataFrame:
    """Convert Stage25C DB-loaded candles to indexed OHLC format used by Stage26A.

    Stage25C's loader is the proven DB schema introspection path used by Stage23D/25D.
    It returns timestamp/open/high/low/close columns. This adapter keeps Stage26A
    DB-first while avoiding duplicated, fragile SQLite schema discovery logic.
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close"])
    out = df.copy()
    if "timestamp" not in out.columns:
        if "time" in out.columns:
            out = out.rename(columns={"time": "timestamp"})
        elif "datetime" in out.columns:
            out = out.rename(columns={"datetime": "timestamp"})
    missing = [c for c in ["timestamp", "open", "high", "low", "close"] if c not in out.columns]
    if missing:
        raise DBFirstLoaderError(f"DB-first {label} candles missing columns: {missing}. CSV fallback is intentionally disabled.")
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    for c in ["open", "high", "low", "close"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(subset=["timestamp", "open", "high", "low", "close"]).sort_values("timestamp")
    out = out.drop_duplicates("timestamp", keep="last")
    out = out.set_index("timestamp")[["open", "high", "low", "close"]]
    return out


def run() -> Dict[str, Any]:
    started = time.time()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    if not DB_PATH.exists():
        raise DBFirstLoaderError(f"SQLite DB not found: {DB_PATH}. CSV fallback is intentionally disabled.")
    if load_bars_from_db is None:
        raise DBFirstLoaderError("Stage26A DB-first loader could not import load_bars_from_db from app.stage25c_deduped_filter_validation. Apply Stage25C before Stage26A.")

    # Use the proven Stage25C DB schema introspection path, already validated by Stage23D/25D.
    m1_raw, h1_raw, db_meta, schema_diag = load_bars_from_db(DB_PATH)
    pd.DataFrame(schema_diag).to_csv(REPORT_DIR / "stage26a_db_schema_diagnostic.csv", index=False)
    m1 = to_indexed_ohlc(m1_raw, label="M1")
    h1 = to_indexed_ohlc(h1_raw, label="H1") if h1_raw is not None and not h1_raw.empty else pd.DataFrame()
    if m1.empty:
        raise DBFirstLoaderError("No M1 OHLC candles found in SQLite DB via Stage25C schema introspection. CSV fallback is intentionally disabled.")
    if h1.empty or len(h1) < 1000:
        h1 = resample_ohlc(m1, "1h")
        h1_mode = "resampled_from_m1"
    else:
        h1_mode = str(db_meta.get("h1_mode", "db_schema_introspection"))
    m15 = resample_ohlc(m1, "15min")
    m15, h1, daily = add_features(m15, h1)
    cands = generate_candidates()
    proxy_deadline = started + max(30, MAX_RUNTIME_SECONDS - EXACT_RESERVED_SECONDS)
    proxy_rows: List[Dict[str, Any]] = []
    event_cache: Dict[str, pd.DataFrame] = {}
    proxy_timed_out = False
    for c in cands:
        if time.time() > proxy_deadline:
            proxy_timed_out = True
            break
        ev = events_for_candidate(c, m15, h1, daily)
        event_cache[c.name] = ev
        if len(ev) < MIN_EVENTS:
            continue
        trades = outcome_for_events(ev, m15)
        if len(trades) < MIN_EVENTS:
            continue
        proxy_rows.append(summarize_trades(trades, c, proxy=True))
    proxy_df = pd.DataFrame(proxy_rows).sort_values(["rank_score", "pf_x4", "events"], ascending=[False, False, False]) if proxy_rows else pd.DataFrame()
    proxy_df.to_csv(REPORT_DIR / "stage26a_proxy_candidates.csv", index=False)
    # Family-balanced exact selection.
    exact_cands: List[Candidate] = []
    if not proxy_df.empty:
        for family, sub in proxy_df.groupby("family", sort=False):
            for name in sub.head(MAX_EXACT_PER_FAMILY)["name"].tolist():
                exact_cands.append(next(c for c in cands if c.name == name))
        exact_cands = exact_cands[:MAX_EXACT_TOTAL]
    exact_rows: List[Dict[str, Any]] = []
    exact_trades_all: List[pd.DataFrame] = []
    exact_timed_out = False
    for c in exact_cands:
        if time.time() > started + MAX_RUNTIME_SECONDS:
            exact_timed_out = True
            break
        ev = event_cache.get(c.name)
        if ev is None:
            ev = events_for_candidate(c, m15, h1, daily)
        trades = outcome_for_events(ev, m1)
        if len(trades) == 0:
            continue
        summary = summarize_trades(trades, c, proxy=False)
        exact_rows.append(summary)
        trades["candidate"] = c.name
        trades["family"] = c.family
        exact_trades_all.append(trades)
    exact_df = pd.DataFrame(exact_rows).sort_values(["rank_score", "pf_x4", "events"], ascending=[False, False, False]) if exact_rows else pd.DataFrame()
    exact_df.to_csv(REPORT_DIR / "stage26a_exact_candidates.csv", index=False)
    if exact_trades_all:
        pd.concat(exact_trades_all, ignore_index=True).to_csv(REPORT_DIR / "stage26a_exact_trades.csv", index=False)
    else:
        pd.DataFrame().to_csv(REPORT_DIR / "stage26a_exact_trades.csv", index=False)
    promo_count = int((exact_df.get("decision", pd.Series(dtype=str)) == "STAGE26A_PROMOTION_REVIEW_RESEARCH_ONLY").sum()) if not exact_df.empty else 0
    watch_count = int((exact_df.get("decision", pd.Series(dtype=str)) == "STAGE26A_WATCHLIST_ONLY").sum()) if not exact_df.empty else 0
    decision = "STAGE26A_NO_PROMOTION_KEEP_DISCOVERY_OPEN"
    if promo_count > 0:
        decision = "STAGE26A_HAS_PROMOTION_REVIEW_CANDIDATE_RESEARCH_ONLY"
    elif watch_count > 0:
        decision = "STAGE26A_HAS_WATCHLIST_CANDIDATE_RESEARCH_ONLY"
    report = {
        "stage": STAGE,
        "generated_utc": pd.Timestamp.utcnow().isoformat(),
        "decision": decision,
        "db_path": str(DB_PATH),
        "candle_table": db_meta.get("candle_table", ""),
        "db_first": True,
        "csv_fallback_enabled": False,
        "m1_rows": int(len(m1)), "m1_span": f"{m1.index.min()} → {m1.index.max()}",
        "h1_rows": int(len(h1)), "h1_span": f"{h1.index.min()} → {h1.index.max()}", "h1_mode": h1_mode,
        "m15_rows": int(len(m15)), "m15_span": f"{m15.index.min()} → {m15.index.max()}",
        "proxy_candidates_tested": int(min(len(cands), len(event_cache))),
        "proxy_candidates_passing_min_events": int(len(proxy_df)),
        "exact_replayed": int(len(exact_df)),
        "promotion_review_candidates": promo_count,
        "watchlist_only_candidates": watch_count,
        "proxy_timed_out": bool(proxy_timed_out), "exact_timed_out": bool(exact_timed_out),
        "runtime_seconds": round(time.time() - started, 2),
        "roundtrip_cost_x1": ROUNDTRIP_COST_X1,
    }
    return {"report": report, "proxy_df": proxy_df, "exact_df": exact_df}


def fmt(v: Any) -> str:
    if isinstance(v, float):
        if math.isinf(v): return "inf"
        if math.isnan(v): return ""
        return f"{v:.4f}".rstrip("0").rstrip(".")
    return str(v)


def md_table(df: pd.DataFrame, cols: List[str], limit: int = 20) -> List[str]:
    if df is None or df.empty:
        return ["No rows."]
    show = df.head(limit).copy()
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"]*len(cols)) + " |"]
    for _, r in show.iterrows():
        lines.append("| " + " | ".join(fmt(r.get(c, "")) for c in cols) + " |")
    return lines


def write_outputs(result: Dict[str, Any]) -> None:
    report, proxy_df, exact_df = result["report"], result["proxy_df"], result["exact_df"]
    (REPORT_DIR / f"{STAGE}.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    lines: List[str] = []
    lines.append("# Stage26A DB-First Structured Behavior Discovery")
    lines.append("")
    lines.append(f"Generated UTC: `{report['generated_utc']}`")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append("```text")
    lines.append(report["decision"])
    lines.append("```")
    lines.append("")
    lines.append("## Scope guardrails")
    lines += ["", "- Research/shadow discovery only.", "- Stage18A v2 remains the active operational forward-shadow runner.", "- Stage23D and Stage25D remain separate DB-first trackers.", "- No EA change, no automatic trading, no paper/live/order authorization.", "- Candles are DB-first from SQLite; AMarkets CSV fallback is disabled."]
    lines.append("")
    lines.append("## DB source of truth")
    for k in ["db_path", "candle_table", "db_first", "csv_fallback_enabled", "m1_rows", "m1_span", "h1_rows", "h1_span", "h1_mode", "m15_rows", "m15_span"]:
        lines.append(f"- {k}: `{report[k]}`")
    lines.append("")
    lines.append("## Discovery families")
    lines += ["", "1. `htf_bias_pullback_continuation` — H1 trend bias plus London directional move and controlled pullback.", "2. `breakout_pullback_continuation` — Asia range breakout, pullback/hold, then continuation.", "3. `session_transition_imbalance` — London imbalance carried into early NY/session transition."]
    lines.append("")
    lines.append("## Counts")
    for k in ["proxy_candidates_tested", "proxy_candidates_passing_min_events", "exact_replayed", "promotion_review_candidates", "watchlist_only_candidates", "proxy_timed_out", "exact_timed_out", "runtime_seconds"]:
        lines.append(f"- {k}: `{report[k]}`")
    lines.append("")
    lines.append("## Top exact M1 results")
    cols = ["decision", "family", "name", "events", "pf_x1", "pf_x4", "pf_x6", "boot_pf_p05_x4", "median_x4", "total_x4", "win_rate_x4"]
    lines += md_table(exact_df, cols, 20)
    lines.append("")
    lines.append("## Top M15 proxy results")
    cols2 = ["decision", "family", "name", "events", "pf_x1", "pf_x4", "pf_x6", "boot_pf_p05_x4", "median_x4", "rank_score"]
    lines += md_table(proxy_df, cols2, 20)
    lines.append("")
    lines.append("## Interpretation")
    lines += ["", "- Stage26A is a new DB-first discovery branch, not a modification of Stage18A/23D/25D.", "- Exact replay is family-balanced so one high-frequency family cannot consume all exact slots.", "- Generic high-frequency candidates are penalized in ranking to reduce the Stage24 failure mode.", "- A promotion-review result here remains research-only and requires separate validation and forward-shadow tracking."]
    lines.append("")
    lines.append("## Operational reminder")
    lines.append("")
    lines.append("```bash")
    lines.append("cd ~/Desktop/xauusd-trader")
    lines.append("python3 -m app.stage18a_unified_shadow_ops_cycle")
    lines.append("python3 -m app.stage23d_forward_shadow_candidate")
    lines.append("python3 -m app.stage25d_db_first_filtered_forward_shadow")
    lines.append("```")
    lines.append("")
    lines.append("## Output files")
    for name in [f"{STAGE}.json", f"{STAGE}.md", "stage26a_proxy_candidates.csv", "stage26a_exact_candidates.csv", "stage26a_exact_trades.csv", "stage26a_db_schema_diagnostic.csv"]:
        lines.append(f"- `data/reports/{STAGE}/{name}`")
    (REPORT_DIR / f"{STAGE}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    try:
        result = run()
        write_outputs(result)
    except Exception as exc:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        report = {"decision": "STAGE26A_ERROR_DIAGNOSTIC_ONLY", "error": f"{type(exc).__name__}: {exc}", "db_path": str(DB_PATH), "db_first": True, "csv_fallback_enabled": False}
        (REPORT_DIR / f"{STAGE}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        (REPORT_DIR / f"{STAGE}.md").write_text("# Stage26A DB-First Structured Behavior Discovery\n\n## Decision\n\n```text\nSTAGE26A_ERROR_DIAGNOSTIC_ONLY\n```\n\n## Error\n\n```text\n" + report["error"] + "\n```\n\n- DB-first is enabled.\n- CSV fallback is intentionally disabled.\n- Stage18A, Stage23D, and Stage25D remain unchanged.\n", encoding="utf-8")
        raise


if __name__ == "__main__":
    main()
