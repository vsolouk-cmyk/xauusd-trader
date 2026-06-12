"""
Stage 23B — controlled continuation/no-trade-regime discovery for XAUUSD.

Research-only module. It does NOT modify Stage18A, does NOT authorize paper/live,
and does NOT create orders.

Design:
- Load AMarkets/local M1 and H1 OHLCV data from the local SQLite store when possible.
- Fall back to ~/Downloads/amarkets_xauusd_1m.csv and ~/Downloads/amarkets_xauusd_1h.csv.
- Build a lite M15 proxy grid over continuation/mirror families after Stage23B fade rejection.
- Run exact M1 diagnostic replay for the best proxy candidates, while reserving runtime for exact.
- Write JSON/CSV/MD reports under data/reports/stage23b_continuation_no_trade_discovery/.

Run:
    cd ~/Desktop/xauusd-trader
    python3 -m app.stage23b_continuation_no_trade_discovery
    cat data/reports/stage23b_continuation_no_trade_discovery/stage23b_continuation_no_trade_discovery.md
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


STAGE_NAME = "stage23b_continuation_no_trade_discovery"
REPORT_DIR = Path("data/reports") / STAGE_NAME
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_M1_CSV = Path(os.path.expanduser("~/Downloads/amarkets_xauusd_1m.csv"))
DEFAULT_H1_CSV = Path(os.path.expanduser("~/Downloads/amarkets_xauusd_1h.csv"))
ROUNDTRIP_COST_USD = 0.35
RANDOM_SEED = 2301

# Keep discovery controlled. Exact replay must remain small.
# v3 hotfix: reserve time for exact replay and cache repeated signal events.
# These caps keep discovery in the intended lite/proxy-then-exact mode.
MAX_PROXY_ROWS_IN_REPORT = 80
MAX_EXACT_REPLAY_TOTAL = int(os.getenv("STAGE23B_MAX_EXACT", "12"))
MAX_EXACT_REPLAY_PER_FAMILY = int(os.getenv("STAGE23B_MAX_EXACT_PER_FAMILY", "4"))
MIN_PROXY_EVENTS = int(os.getenv("STAGE23B_MIN_PROXY_EVENTS", "25"))
MIN_EXACT_EVENTS = int(os.getenv("STAGE23B_MIN_EXACT_EVENTS", "35"))
MAX_RUNTIME_SECONDS = int(os.getenv("STAGE23B_MAX_RUNTIME_SECONDS", "180"))
EXACT_RESERVED_SECONDS = int(os.getenv("STAGE23B_EXACT_RESERVED_SECONDS", "45"))
MAX_CANDIDATES_TOTAL = int(os.getenv("STAGE23B_MAX_CANDIDATES_TOTAL", "72"))
PROXY_BOOTSTRAP_ITERS = int(os.getenv("STAGE23B_PROXY_BOOTSTRAP_ITERS", "20"))
EXACT_BOOTSTRAP_ITERS = int(os.getenv("STAGE23B_EXACT_BOOTSTRAP_ITERS", "80"))
# CSV-first avoids expensive SQLite table discovery on large local stores.
DATA_LOAD_MODE = os.getenv("STAGE23B_DATA_LOAD_MODE", "csv_first").strip().lower()


@dataclass(frozen=True)
class Candidate:
    family: str
    name: str
    params: Dict[str, Any]


@dataclass
class Trade:
    signal_time: str
    entry_time: str
    exit_time: str
    direction: str
    entry: float
    exit: float
    tp: float
    sl: float
    gross: float
    net_x1: float
    net_x4: float
    exit_reason: str
    family: str
    candidate: str


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def _clean_col_name(col: Any) -> str:
    return str(col).strip().lower().replace("<", "").replace(">", "").replace(" ", "_")


def _find_first(cols: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    colset = set(cols)
    for c in candidates:
        if c in colset:
            return c
    return None


def _normalize_ohlcv(raw: pd.DataFrame, source_name: str) -> pd.DataFrame:
    if raw is None or raw.empty:
        raise ValueError(f"empty OHLCV source: {source_name}")

    df = raw.copy()
    df.columns = [_clean_col_name(c) for c in df.columns]
    cols = list(df.columns)

    # MT5 exports often have DATE and TIME as separate columns.
    date_col = _find_first(cols, ["date", "date_", "day"])
    clock_col = _find_first(cols, ["time", "clock", "time_"])
    datetime_col = _find_first(
        cols,
        [
            "datetime",
            "timestamp",
            "time_utc",
            "utc_time",
            "open_time",
            "bar_time",
            "dt",
        ],
    )

    if date_col and clock_col and date_col != clock_col:
        parsed_time = pd.to_datetime(
            df[date_col].astype(str).str.strip() + " " + df[clock_col].astype(str).str.strip(),
            errors="coerce",
            utc=False,
        )
    elif datetime_col:
        parsed_time = pd.to_datetime(df[datetime_col], errors="coerce", utc=False)
    elif clock_col:
        parsed_time = pd.to_datetime(df[clock_col], errors="coerce", utc=False)
    else:
        raise ValueError(f"cannot detect time column in {source_name}; columns={cols}")

    open_col = _find_first(cols, ["open", "o", "bid_open"])
    high_col = _find_first(cols, ["high", "h", "bid_high"])
    low_col = _find_first(cols, ["low", "l", "bid_low"])
    close_col = _find_first(cols, ["close", "c", "last", "bid_close"])
    if not all([open_col, high_col, low_col, close_col]):
        raise ValueError(f"cannot detect OHLC columns in {source_name}; columns={cols}")

    out = pd.DataFrame(
        {
            "time": parsed_time,
            "open": pd.to_numeric(df[open_col], errors="coerce"),
            "high": pd.to_numeric(df[high_col], errors="coerce"),
            "low": pd.to_numeric(df[low_col], errors="coerce"),
            "close": pd.to_numeric(df[close_col], errors="coerce"),
        }
    )

    vol_col = _find_first(cols, ["volume", "vol", "tickvol", "tick_volume", "real_volume"])
    if vol_col:
        out["volume"] = pd.to_numeric(df[vol_col], errors="coerce").fillna(0.0)
    else:
        out["volume"] = 0.0

    out = out.dropna(subset=["time", "open", "high", "low", "close"])
    out = out.sort_values("time").drop_duplicates("time", keep="last").reset_index(drop=True)
    if out.empty:
        raise ValueError(f"no valid OHLCV rows after normalization: {source_name}")

    # Use timezone-naive timestamps to remain compatible with the existing local stages.
    if getattr(out["time"].dt, "tz", None) is not None:
        out["time"] = out["time"].dt.tz_convert(None)

    return out


def _read_csv_ohlcv(path: Path, label: str) -> Optional[pd.DataFrame]:
    if not path.exists():
        return None
    try:
        raw = pd.read_csv(path, sep=None, engine="python")
        return _normalize_ohlcv(raw, f"{label}:{path}")
    except Exception as exc:
        print(f"[WARN] CSV load failed for {path}: {exc}")
        return None


def _table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    return [_clean_col_name(r[1]) for r in rows]


def _read_sql_table(conn: sqlite3.Connection, table: str, where_sql: str = "") -> Optional[pd.DataFrame]:
    try:
        query = f'SELECT * FROM "{table}" {where_sql}'
        raw = pd.read_sql_query(query, conn)
        return _normalize_ohlcv(raw, f"sqlite:{table}{where_sql}")
    except Exception:
        return None


def _load_from_sqlite(db_path: Path) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Dict[str, Any]]:
    meta: Dict[str, Any] = {"db_path": str(db_path), "sqlite_used": False, "m1_table": None, "h1_table": None}
    if not db_path.exists():
        return None, None, meta

    m1_candidates: List[Tuple[int, str, pd.DataFrame]] = []
    h1_candidates: List[Tuple[int, str, pd.DataFrame]] = []

    try:
        with sqlite3.connect(db_path) as conn:
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            for table in tables:
                table_l = table.lower()
                cols = _table_columns(conn, table)
                has_ohlc = {"open", "high", "low", "close"}.issubset(set(cols))
                if not has_ohlc:
                    continue

                timeframe_col = None
                for c in ["timeframe", "tf", "interval", "granularity"]:
                    if c in cols:
                        timeframe_col = c
                        break

                if timeframe_col:
                    m1_where = f"WHERE lower(cast({timeframe_col} as text)) IN ('m1','1m','1min','1','minute','1 minute')"
                    h1_where = f"WHERE lower(cast({timeframe_col} as text)) IN ('h1','1h','60m','60min','hour','1 hour')"
                    m1_df = _read_sql_table(conn, table, m1_where)
                    h1_df = _read_sql_table(conn, table, h1_where)
                    if m1_df is not None and len(m1_df) > 100:
                        m1_candidates.append((len(m1_df), f"{table}:{timeframe_col}=M1", m1_df))
                    if h1_df is not None and len(h1_df) > 50:
                        h1_candidates.append((len(h1_df), f"{table}:{timeframe_col}=H1", h1_df))

                # Table-name fallback.
                df = _read_sql_table(conn, table)
                if df is None or len(df) < 50:
                    continue
                if any(tok in table_l for tok in ["m1", "1m", "minute"]):
                    m1_candidates.append((len(df), table, df))
                if any(tok in table_l for tok in ["h1", "1h", "hour"]):
                    h1_candidates.append((len(df), table, df))

        m1 = max(m1_candidates, key=lambda x: x[0]) if m1_candidates else None
        h1 = max(h1_candidates, key=lambda x: x[0]) if h1_candidates else None
        meta["sqlite_used"] = bool(m1 or h1)
        if m1:
            meta["m1_table"] = m1[1]
        if h1:
            meta["h1_table"] = h1[1]
        return (m1[2] if m1 else None), (h1[2] if h1 else None), meta
    except Exception as exc:
        meta["sqlite_error"] = str(exc)
        return None, None, meta


def _resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    x = df.copy().set_index("time").sort_index()
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    out = x.resample(rule).agg(agg).dropna(subset=["open", "high", "low", "close"]).reset_index()
    return out


def load_market_data() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    meta: Dict[str, Any] = {"data_load_mode": DATA_LOAD_MODE}

    m1: Optional[pd.DataFrame] = None
    h1: Optional[pd.DataFrame] = None

    # v2 hotfix: use AMarkets CSV first by default. The previous SQLite-first
    # path can become very slow when the local store contains multiple large OHLC tables.
    if DATA_LOAD_MODE != "sqlite_first":
        m1 = _read_csv_ohlcv(DEFAULT_M1_CSV, "M1 csv_first")
        h1 = _read_csv_ohlcv(DEFAULT_H1_CSV, "H1 csv_first")
        if m1 is not None:
            meta["m1_csv"] = str(DEFAULT_M1_CSV)
        if h1 is not None:
            meta["h1_csv"] = str(DEFAULT_H1_CSV)

    if m1 is None or h1 is None:
        sql_m1, sql_h1, sql_meta = _load_from_sqlite(DEFAULT_DB)
        meta.update(sql_meta)
        if m1 is None:
            m1 = sql_m1
        if h1 is None:
            h1 = sql_h1

    if m1 is None:
        m1 = _read_csv_ohlcv(DEFAULT_M1_CSV, "M1 fallback")
        if m1 is not None:
            meta["m1_fallback_csv"] = str(DEFAULT_M1_CSV)
    if h1 is None:
        h1 = _read_csv_ohlcv(DEFAULT_H1_CSV, "H1 fallback")
        if h1 is not None:
            meta["h1_fallback_csv"] = str(DEFAULT_H1_CSV)

    if m1 is None or m1.empty:
        raise RuntimeError(
            "M1 data not found. Expected ~/Downloads/amarkets_xauusd_1m.csv or local SQLite data."
        )
    if h1 is None or h1.empty:
        h1 = _resample_ohlcv(m1, "1H")
        meta["h1_resampled_from_m1"] = True

    m15 = _resample_ohlcv(m1, "15min")
    return m1, h1, m15, meta


# ---------------------------------------------------------------------------
# Metrics and replay
# ---------------------------------------------------------------------------


def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    x = df.copy().sort_values("time")
    prev_close = x["close"].shift(1)
    tr = pd.concat(
        [
            (x["high"] - x["low"]).abs(),
            (x["high"] - prev_close).abs(),
            (x["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    x["atr"] = tr.rolling(period, min_periods=max(3, period // 2)).mean()
    return x


def merge_atr(base: pd.DataFrame, h1: pd.DataFrame) -> pd.DataFrame:
    h1_atr = add_atr(h1)[["time", "atr"]].dropna().sort_values("time")
    out = pd.merge_asof(base.sort_values("time"), h1_atr, on="time", direction="backward")
    out["atr"] = out["atr"].ffill().bfill()
    return out


def profit_factor(values: Sequence[float]) -> float:
    vals = np.asarray(list(values), dtype=float)
    if vals.size == 0:
        return 0.0
    pos = vals[vals > 0].sum()
    neg = vals[vals < 0].sum()
    if neg == 0:
        return float("inf") if pos > 0 else 0.0
    return float(pos / abs(neg))


def bootstrap_pf_p05(values: Sequence[float], n_iter: int = 100) -> float:
    vals = np.asarray(list(values), dtype=float)
    if vals.size < 10:
        return 0.0
    if n_iter <= 0:
        return profit_factor(vals)
    rng = np.random.default_rng(RANDOM_SEED)
    pfs = []
    for _ in range(n_iter):
        sample = rng.choice(vals, size=vals.size, replace=True)
        pfs.append(profit_factor(sample))
    finite = np.asarray([x for x in pfs if np.isfinite(x)], dtype=float)
    if finite.size == 0:
        return float("inf")
    return float(np.percentile(finite, 5))


def summarize_trades(trades: List[Trade], stage: str) -> Dict[str, Any]:
    if not trades:
        return {
            "stage": stage,
            "events": 0,
            "pf_x1": 0.0,
            "pf_x4": 0.0,
            "total_x1": 0.0,
            "median_x1": 0.0,
            "win_rate_x1": 0.0,
            "test20_pf_x1": 0.0,
            "pf_2026_x1": None,
            "boot_pf_p05_x1": 0.0,
        }
    df = pd.DataFrame([asdict(t) for t in trades])
    df["entry_time_dt"] = pd.to_datetime(df["entry_time"], errors="coerce")
    df = df.sort_values("entry_time_dt")
    n = len(df)
    split = max(1, int(math.floor(n * 0.8)))
    test = df.iloc[split:] if split < n else df.iloc[-max(1, n // 5) :]
    y2026 = df[df["entry_time_dt"].dt.year == 2026]
    return {
        "stage": stage,
        "events": int(n),
        "pf_x1": round(profit_factor(df["net_x1"]), 4),
        "pf_x4": round(profit_factor(df["net_x4"]), 4),
        "total_x1": round(float(df["net_x1"].sum()), 4),
        "total_x4": round(float(df["net_x4"].sum()), 4),
        "median_x1": round(float(df["net_x1"].median()), 4),
        "win_rate_x1": round(float((df["net_x1"] > 0).mean()), 4),
        "test20_pf_x1": round(profit_factor(test["net_x1"]), 4),
        "pf_2026_x1": None if y2026.empty else round(profit_factor(y2026["net_x1"]), 4),
        "boot_pf_p05_x1": round(bootstrap_pf_p05(df["net_x1"], PROXY_BOOTSTRAP_ITERS if stage.startswith("proxy") else EXACT_BOOTSTRAP_ITERS), 4),
        "first_entry": str(df["entry_time_dt"].min()),
        "last_entry": str(df["entry_time_dt"].max()),
    }


def decide_exact(summary: Dict[str, Any]) -> str:
    events = summary.get("events", 0)
    pf_x1 = summary.get("pf_x1", 0.0)
    pf_x4 = summary.get("pf_x4", 0.0)
    test20 = summary.get("test20_pf_x1", 0.0)
    boot = summary.get("boot_pf_p05_x1", 0.0)
    median = summary.get("median_x1", 0.0)
    pf_2026 = summary.get("pf_2026_x1")
    y_ok = True if pf_2026 is None else pf_2026 >= 1.0

    if events >= MIN_EXACT_EVENTS and pf_x1 >= 1.25 and pf_x4 >= 1.05 and test20 >= 1.05 and boot >= 1.0 and median > 0 and y_ok:
        return "STAGE23B_PROMOTION_CANDIDATE_REVIEW_ONLY"
    if events >= MIN_EXACT_EVENTS and pf_x1 >= 1.15 and pf_x4 >= 1.0 and test20 >= 0.95 and boot >= 0.85 and y_ok:
        return "STAGE23B_KEEP_WATCHLIST_ONLY"
    return "STAGE23B_REJECT"


def _next_bar_index(df: pd.DataFrame, signal_time: pd.Timestamp) -> Optional[int]:
    idx = df["time"].searchsorted(signal_time, side="right")
    if idx >= len(df):
        return None
    return int(idx)


def replay_events(
    candles: pd.DataFrame,
    events: pd.DataFrame,
    candidate: Candidate,
    cost_usd: float,
) -> List[Trade]:
    """Fast array-based replay.

    v1 used DataFrame boolean slicing for every event, which can explode runtime on
    large M1 files. v2 uses searchsorted over numpy arrays and only scans the
    bounded horizon window.
    """
    if events.empty:
        return []

    c = candles.sort_values("time").reset_index(drop=True).copy()
    times = pd.to_datetime(c["time"]).to_numpy(dtype="datetime64[ns]")
    opens = c["open"].to_numpy(dtype=float)
    highs = c["high"].to_numpy(dtype=float)
    lows = c["low"].to_numpy(dtype=float)
    closes = c["close"].to_numpy(dtype=float)

    params = candidate.params
    horizon_min = int(params["horizon_min"])
    tp_atr = float(params["tp_atr"])
    sl_atr = float(params["sl_atr"])
    horizon_delta = np.timedelta64(horizon_min, "m")
    trades: List[Trade] = []

    for _, ev in events.sort_values("signal_time").iterrows():
        signal_time = np.datetime64(pd.Timestamp(ev["signal_time"]).to_datetime64(), "ns")
        direction = str(ev["direction"]).lower()
        atr = float(ev.get("atr", np.nan))
        if not np.isfinite(atr) or atr <= 0:
            continue

        entry_idx = int(np.searchsorted(times, signal_time, side="right"))
        if entry_idx >= len(times):
            continue

        entry_time64 = times[entry_idx]
        entry = float(opens[entry_idx])
        if direction == "long":
            tp = entry + tp_atr * atr
            sl = entry - sl_atr * atr
        elif direction == "short":
            tp = entry - tp_atr * atr
            sl = entry + sl_atr * atr
        else:
            continue

        cutoff = entry_time64 + horizon_delta
        end_idx = int(np.searchsorted(times, cutoff, side="right"))
        if end_idx <= entry_idx:
            continue

        exit_idx = end_idx - 1
        exit_price = float(closes[exit_idx])
        exit_reason = "horizon_close"

        for j in range(entry_idx, end_idx):
            hi = float(highs[j])
            lo = float(lows[j])
            if direction == "long":
                if lo <= sl:
                    exit_price = sl
                    exit_idx = j
                    exit_reason = "sl_conservative"
                    break
                if hi >= tp:
                    exit_price = tp
                    exit_idx = j
                    exit_reason = "tp"
                    break
            else:
                if hi >= sl:
                    exit_price = sl
                    exit_idx = j
                    exit_reason = "sl_conservative"
                    break
                if lo <= tp:
                    exit_price = tp
                    exit_idx = j
                    exit_reason = "tp"
                    break

        gross = (exit_price - entry) if direction == "long" else (entry - exit_price)
        signal_ts = pd.Timestamp(signal_time)
        entry_ts = pd.Timestamp(entry_time64)
        exit_ts = pd.Timestamp(times[exit_idx])
        trades.append(
            Trade(
                signal_time=str(signal_ts),
                entry_time=str(entry_ts),
                exit_time=str(exit_ts),
                direction=direction,
                entry=round(entry, 5),
                exit=round(exit_price, 5),
                tp=round(tp, 5),
                sl=round(sl, 5),
                gross=round(gross, 5),
                net_x1=round(gross - cost_usd, 5),
                net_x4=round(gross - 4.0 * cost_usd, 5),
                exit_reason=exit_reason,
                family=candidate.family,
                candidate=candidate.name,
            )
        )
    return trades


# ---------------------------------------------------------------------------
# Event generation
# ---------------------------------------------------------------------------


def _day_groups(m15: pd.DataFrame) -> Iterable[Tuple[Any, pd.DataFrame]]:
    x = m15.copy()
    x["day"] = pd.to_datetime(x["time"]).dt.date
    for day, g in x.groupby("day", sort=True):
        if len(g) >= 40:
            yield day, g.sort_values("time").reset_index(drop=True)


def _first_bar_at_or_after_hour(g: pd.DataFrame, hour: int) -> Optional[pd.Series]:
    t = pd.to_datetime(g["time"])
    sub = g[(t.dt.hour > hour) | ((t.dt.hour == hour) & (t.dt.minute >= 0))]
    if sub.empty:
        return None
    return sub.iloc[0]


def _session_slice(g: pd.DataFrame, start_hour: int, end_hour: int) -> pd.DataFrame:
    t = pd.to_datetime(g["time"])
    return g[(t.dt.hour >= start_hour) & (t.dt.hour < end_hour)]


def events_london_oneway_continuation(m15: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """Mirror of Stage23A fade: if one-way London fade fails, test same-direction NY continuation."""
    rows = []
    for _, g in _day_groups(m15):
        london = _session_slice(g, 7, 13)
        if len(london) < 8:
            continue
        entry = _first_bar_at_or_after_hour(g, int(params["entry_hour"]))
        if entry is None:
            continue
        atr = float(entry.get("atr", np.nan))
        if not np.isfinite(atr) or atr <= 0:
            continue
        lo = float(london["low"].min())
        hi = float(london["high"].max())
        london_open = float(london.iloc[0]["open"])
        london_close = float(london.iloc[-1]["close"])
        move = london_close - london_open
        if abs(move) <= 1e-9:
            continue
        direction_sign = 1.0 if move > 0 else -1.0
        move_atr = abs(move) / atr
        efficiency = abs(move) / max(1e-9, hi - lo)
        entry_close = float(entry["close"])
        adverse_pullback_atr = max(0.0, (london_close - entry_close) * direction_sign / atr)
        continuation_atr = max(0.0, (entry_close - london_close) * direction_sign / atr)
        if move_atr < float(params["london_move_atr_min"]):
            continue
        if efficiency < float(params["eff_min"]):
            continue
        if adverse_pullback_atr > float(params["pullback_atr_max"]):
            continue
        if continuation_atr < float(params["ny_confirm_atr_min"]):
            continue
        rows.append(
            {
                "signal_time": entry["time"],
                "direction": "long" if move > 0 else "short",
                "atr": atr,
                "move_atr": move_atr,
                "efficiency": efficiency,
                "adverse_pullback_atr": adverse_pullback_atr,
                "continuation_atr": continuation_atr,
            }
        )
    return pd.DataFrame(rows)


def events_asia_london_breakout_continuation(m15: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """Continuation after London closes outside Asia range instead of fading that extension."""
    rows = []
    for _, g in _day_groups(m15):
        asia = _session_slice(g, 0, 7)
        london = _session_slice(g, 7, 13)
        if len(asia) < 8 or len(london) < 8:
            continue
        entry = _first_bar_at_or_after_hour(g, int(params["entry_hour"]))
        if entry is None:
            continue
        atr = float(entry.get("atr", np.nan))
        if not np.isfinite(atr) or atr <= 0:
            continue
        asia_hi = float(asia["high"].max())
        asia_lo = float(asia["low"].min())
        asia_range_atr = (asia_hi - asia_lo) / atr
        if asia_range_atr > float(params["asia_range_atr_max"]):
            continue
        london_close = float(london.iloc[-1]["close"])
        ext_min = float(params["london_extension_atr_min"])
        if london_close > asia_hi + ext_min * atr:
            direction = "long"
            ext_atr = (london_close - asia_hi) / atr
        elif london_close < asia_lo - ext_min * atr:
            direction = "short"
            ext_atr = (asia_lo - london_close) / atr
        else:
            continue
        rows.append(
            {
                "signal_time": entry["time"],
                "direction": direction,
                "atr": atr,
                "asia_range_atr": asia_range_atr,
                "london_extension_atr": ext_atr,
            }
        )
    return pd.DataFrame(rows)


def events_prev_day_extreme_breakout_continuation(m15: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """Continuation after price holds beyond previous-day extreme; mirror of Stage23A range fade."""
    x = m15.copy()
    x["day"] = pd.to_datetime(x["time"]).dt.date
    daily = (
        x.groupby("day")
        .agg(day_high=("high", "max"), day_low=("low", "min"), day_close=("close", "last"), day_atr=("atr", "median"))
        .dropna()
    )
    daily["day_range_atr"] = (daily["day_high"] - daily["day_low"]) / daily["day_atr"].replace(0, np.nan)
    rows = []
    days = list(daily.index)
    for i in range(1, len(days)):
        day = days[i]
        prev = daily.loc[days[i - 1]]
        if float(prev["day_range_atr"]) < float(params["prev_day_range_atr_min"]):
            continue
        g = x[x["day"] == day].sort_values("time")
        if len(g) < 40:
            continue
        entry = _first_bar_at_or_after_hour(g, int(params["entry_hour"]))
        if entry is None:
            continue
        atr = float(entry.get("atr", np.nan))
        if not np.isfinite(atr) or atr <= 0:
            continue
        t = pd.to_datetime(g["time"])
        pre_entry = g[t <= pd.Timestamp(entry["time"])]
        ext = float(params["extension_atr_min"]) * atr
        entry_close = float(entry["close"])
        if float(pre_entry["high"].max()) >= float(prev["day_high"]) + ext and entry_close > float(prev["day_high"]):
            direction = "long"
        elif float(pre_entry["low"].min()) <= float(prev["day_low"]) - ext and entry_close < float(prev["day_low"]):
            direction = "short"
        else:
            continue
        rows.append(
            {
                "signal_time": entry["time"],
                "direction": direction,
                "atr": atr,
                "prev_day_range_atr": float(prev["day_range_atr"]),
            }
        )
    return pd.DataFrame(rows)


EVENT_GENERATORS = {
    "london_oneway_continuation": events_london_oneway_continuation,
    "asia_london_breakout_continuation": events_asia_london_breakout_continuation,
    "prev_day_extreme_breakout_continuation": events_prev_day_extreme_breakout_continuation,
}


def build_candidates() -> List[Candidate]:
    candidates: List[Candidate] = []

    # Family 1: mirror of the rejected Stage23A one-way London fade.
    for move_min in [0.9, 1.2, 1.5]:
        for eff_min in [0.60, 0.72]:
            for pullback_max in [0.10, 0.30]:
                for confirm_min in [0.0, 0.15]:
                    for entry_hour in [13, 15]:
                        for horizon in [90, 180]:
                            for tp_atr, sl_atr in [(0.40, 0.50), (0.60, 0.65)]:
                                params = {
                                    "london_move_atr_min": move_min,
                                    "eff_min": eff_min,
                                    "pullback_atr_max": pullback_max,
                                    "ny_confirm_atr_min": confirm_min,
                                    "entry_hour": entry_hour,
                                    "horizon_min": horizon,
                                    "tp_atr": tp_atr,
                                    "sl_atr": sl_atr,
                                }
                                name = f"london_oneway_cont_mv{move_min}_eff{eff_min}_pb{pullback_max}_conf{confirm_min}_h{horizon}_e{entry_hour}_tp{tp_atr}_sl{sl_atr}"
                                candidates.append(Candidate("london_oneway_continuation", name, params))

    # Family 2: Asia range breakout continuation through London/NY.
    for asia_max in [0.85, 1.15, 1.45]:
        for ext_min in [0.25, 0.45, 0.70]:
            for entry_hour in [13, 15]:
                for horizon in [90, 180]:
                    for tp_atr, sl_atr in [(0.40, 0.50), (0.60, 0.65)]:
                        params = {
                            "asia_range_atr_max": asia_max,
                            "london_extension_atr_min": ext_min,
                            "entry_hour": entry_hour,
                            "horizon_min": horizon,
                            "tp_atr": tp_atr,
                            "sl_atr": sl_atr,
                        }
                        name = f"asia_london_breakout_cont_asiaMax{asia_max}_ext{ext_min}_h{horizon}_e{entry_hour}_tp{tp_atr}_sl{sl_atr}"
                        candidates.append(Candidate("asia_london_breakout_continuation", name, params))

    # Family 3: previous-day extreme breakout continuation.
    for prev_range_min in [1.1, 1.6]:
        for extension_min in [0.05, 0.20, 0.35]:
            for entry_hour in [13, 15]:
                for horizon in [90, 180]:
                    for tp_atr, sl_atr in [(0.40, 0.50), (0.60, 0.65)]:
                        params = {
                            "prev_day_range_atr_min": prev_range_min,
                            "extension_atr_min": extension_min,
                            "entry_hour": entry_hour,
                            "horizon_min": horizon,
                            "tp_atr": tp_atr,
                            "sl_atr": sl_atr,
                        }
                        name = f"prev_day_extreme_cont_rng{prev_range_min}_ext{extension_min}_h{horizon}_e{entry_hour}_tp{tp_atr}_sl{sl_atr}"
                        candidates.append(Candidate("prev_day_extreme_breakout_continuation", name, params))

    return candidates[:MAX_CANDIDATES_TOTAL]


def _signal_cache_key(cand: Candidate) -> str:
    """Cache event-generation output for candidates sharing the same signal rule."""
    signal_params = {k: v for k, v in cand.params.items() if k not in {"tp_atr", "sl_atr", "horizon_min"}}
    return cand.family + "|" + json.dumps(signal_params, sort_keys=True, separators=(",", ":"))


def run_proxy_grid(m15: pd.DataFrame, candidates: List[Candidate], deadline_ts: float) -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame], bool]:
    rows = []
    event_cache: Dict[str, pd.DataFrame] = {}
    signal_event_cache: Dict[str, pd.DataFrame] = {}
    timed_out = False
    for idx, cand in enumerate(candidates, start=1):
        if time.monotonic() > deadline_ts:
            timed_out = True
            break
        gen = EVENT_GENERATORS[cand.family]
        sig_key = _signal_cache_key(cand)
        if sig_key in signal_event_cache:
            events = signal_event_cache[sig_key]
        else:
            events = gen(m15, cand.params)
            signal_event_cache[sig_key] = events
        event_cache[cand.name] = events
        if len(events) < MIN_PROXY_EVENTS:
            continue
        trades = replay_events(m15, events, cand, ROUNDTRIP_COST_USD)
        summary = summarize_trades(trades, "proxy_m15")
        if summary["events"] < MIN_PROXY_EVENTS:
            continue
        row = {"family": cand.family, "name": cand.name, **cand.params, **summary}
        row["proxy_rank_score"] = round(
            float(summary["pf_x1"]) * 2.0
            + float(summary["pf_x4"]) * 1.0
            + float(summary["test20_pf_x1"]) * 1.0
            + float(summary["boot_pf_p05_x1"]) * 1.0
            + min(float(summary["events"]), 160.0) / 160.0,
            5,
        )
        rows.append(row)
    if not rows:
        return pd.DataFrame(), event_cache, timed_out
    out = pd.DataFrame(rows).sort_values(
        ["proxy_rank_score", "pf_x4", "test20_pf_x1", "events"], ascending=[False, False, False, False]
    )
    return out.reset_index(drop=True), event_cache, timed_out


def select_exact_candidates(proxy_df: pd.DataFrame) -> pd.DataFrame:
    if proxy_df.empty:
        return proxy_df
    selected = []
    for family, g in proxy_df.groupby("family", sort=False):
        selected.append(g.head(MAX_EXACT_REPLAY_PER_FAMILY))
    out = pd.concat(selected).sort_values(
        ["proxy_rank_score", "pf_x4", "test20_pf_x1", "events"], ascending=[False, False, False, False]
    )
    return out.head(MAX_EXACT_REPLAY_TOTAL).reset_index(drop=True)


def run_exact_replay(m1: pd.DataFrame, exact_selection: pd.DataFrame, event_cache: Dict[str, pd.DataFrame], deadline_ts: float) -> Tuple[pd.DataFrame, pd.DataFrame, bool]:
    exact_rows = []
    all_trades: List[Trade] = []
    timed_out = False
    for _, row in exact_selection.iterrows():
        if time.monotonic() > deadline_ts:
            timed_out = True
            break
        family = str(row["family"])
        name = str(row["name"])
        params = {k: row[k] for k in row.index if k in PARAM_KEYS_BY_FAMILY[family]}
        params = {k: (float(v) if isinstance(v, (np.floating, float)) else int(v) if isinstance(v, (np.integer, int)) else v) for k, v in params.items()}
        cand = Candidate(family=family, name=name, params=params)
        events = event_cache.get(name)
        if events is None or events.empty:
            raise RuntimeError(f"missing proxy event cache for {name}")
        trades = replay_events(m1, events, cand, ROUNDTRIP_COST_USD)
        summary = summarize_trades(trades, "exact_m1")
        decision = decide_exact(summary)
        exact_rows.append({"family": family, "name": name, **params, **summary, "decision": decision})
        all_trades.extend(trades)
    exact_df = pd.DataFrame(exact_rows)
    if not exact_df.empty:
        exact_df = exact_df.sort_values(
            ["decision", "pf_x4", "test20_pf_x1", "boot_pf_p05_x1", "events"],
            ascending=[True, False, False, False, False],
        ).reset_index(drop=True)
    trades_df = pd.DataFrame([asdict(t) for t in all_trades]) if all_trades else pd.DataFrame()
    return exact_df, trades_df, timed_out


PARAM_KEYS_BY_FAMILY = {
    "london_oneway_continuation": {
        "london_move_atr_min",
        "eff_min",
        "pullback_atr_max",
        "ny_confirm_atr_min",
        "entry_hour",
        "horizon_min",
        "tp_atr",
        "sl_atr",
    },
    "asia_london_breakout_continuation": {
        "asia_range_atr_max",
        "london_extension_atr_min",
        "entry_hour",
        "horizon_min",
        "tp_atr",
        "sl_atr",
    },
    "prev_day_extreme_breakout_continuation": {
        "prev_day_range_atr_min",
        "extension_atr_min",
        "entry_hour",
        "horizon_min",
        "tp_atr",
        "sl_atr",
    },
}


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _finite_for_json(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _finite_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_finite_for_json(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        if math.isinf(float(obj)):
            return "inf"
        if math.isnan(float(obj)):
            return None
        return float(obj)
    if isinstance(obj, pd.Timestamp):
        return str(obj)
    return obj


def _df_records(df: pd.DataFrame, n: int) -> List[Dict[str, Any]]:
    if df.empty:
        return []
    return _finite_for_json(df.head(n).to_dict(orient="records"))


def markdown_table(df: pd.DataFrame, cols: List[str], n: int) -> str:
    if df.empty:
        return ""
    show = df[cols].head(n).copy()
    def fmt(v: Any) -> str:
        if pd.isna(v):
            return ""
        if isinstance(v, float):
            if math.isinf(v):
                return "inf"
            return f"{v:.4f}".rstrip("0").rstrip(".")
        text = str(v)
        return text.replace("|", "/")
    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    rows = []
    for _, row in show.iterrows():
        rows.append("| " + " | ".join(fmt(row[c]) for c in cols) + " |")
    return "\n".join([header, sep] + rows)


def render_markdown(report: Dict[str, Any], proxy_df: pd.DataFrame, exact_df: pd.DataFrame) -> str:
    data = report["data"]
    decision = report["decision"]
    lines = []
    lines.append(f"# Stage23B Continuation / No-Trade-Regime Discovery")
    lines.append("")
    lines.append(f"Generated UTC: {report['generated_utc']}")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append(f"```text\n{decision}\n```")
    lines.append("")
    lines.append("## Scope guardrails")
    lines.append("")
    lines.append("- Research/shadow only.")
    lines.append("- Stage18A v2 remains the active operational forward-shadow runner.")
    lines.append("- No EA change, no automatic trading, no paper/live/order authorization.")
    lines.append("- Stage19B/20A/21B/22A watchlist-only families are not touched or added to Stage18A.")
    lines.append("")
    lines.append("## Data")
    lines.append("")
    lines.append(f"- M1 rows: {data['m1_rows']} | span: {data['m1_start']} → {data['m1_end']}")
    lines.append(f"- H1 rows: {data['h1_rows']} | span: {data['h1_start']} → {data['h1_end']}")
    lines.append(f"- M15 proxy rows: {data['m15_rows']} | span: {data['m15_start']} → {data['m15_end']}")
    lines.append(f"- Roundtrip cost x1: {ROUNDTRIP_COST_USD}")
    lines.append(f"- Exact replay cap: {MAX_EXACT_REPLAY_TOTAL} total / {MAX_EXACT_REPLAY_PER_FAMILY} per family")
    lines.append(f"- Runtime cap seconds: {MAX_RUNTIME_SECONDS}")
    lines.append(f"- Candidate cap: {MAX_CANDIDATES_TOTAL}")
    lines.append(f"- Data load mode: {DATA_LOAD_MODE}")
    lines.append("")
    lines.append("## Discovery families")
    lines.append("")
    lines.append("1. `london_oneway_continuation` — mirror of rejected Stage23A one-way London fade.")
    lines.append("2. `asia_london_breakout_continuation` — continuation after London closes outside Asia range.")
    lines.append("3. `prev_day_extreme_breakout_continuation` — continuation after previous-day extreme hold.")
    lines.append("")
    lines.append("## Counts")
    lines.append("")
    lines.append(f"- Proxy candidates tested: {report['counts']['proxy_candidates_total']}")
    lines.append(f"- Proxy candidates passing min events: {report['counts']['proxy_candidates_reported']}")
    lines.append(f"- Exact replayed: {report['counts']['exact_replayed']}")
    lines.append(f"- Promotion-review candidates: {report['counts']['promotion_review']}")
    lines.append(f"- Watchlist-only candidates: {report['counts']['watchlist_only']}")
    lines.append("")

    lines.append("## Top exact M1 results")
    lines.append("")
    if exact_df.empty:
        lines.append("No exact candidates were replayed. This should only happen if the proxy runtime cap was reached before the exact reserve or if no proxy candidate passed the minimum-event filter.")
    else:
        cols = ["decision", "family", "name", "events", "pf_x1", "pf_x4", "test20_pf_x1", "pf_2026_x1", "boot_pf_p05_x1", "median_x1", "total_x1"]
        lines.append(markdown_table(exact_df, cols, 15))
    lines.append("")

    lines.append("## Top M15 proxy results")
    lines.append("")
    if proxy_df.empty:
        lines.append("No proxy candidates passed the minimum event threshold.")
    else:
        cols = ["family", "name", "events", "pf_x1", "pf_x4", "test20_pf_x1", "boot_pf_p05_x1", "median_x1", "proxy_rank_score"]
        lines.append(markdown_table(proxy_df, cols, 20))
    lines.append("")

    lines.append("## Operational reminder")
    lines.append("")
    lines.append("Stage23B is discovery only. Continue operational forward-shadow collection separately:")
    lines.append("")
    lines.append("```bash")
    lines.append("cd ~/Desktop/xauusd-trader")
    lines.append("python3 -m app.stage18a_unified_shadow_ops_cycle")
    lines.append("cat data/reports/stage18a_unified_shadow_ops_cycle/stage18a_unified_shadow_ops_cycle.md")
    lines.append("```")
    lines.append("")
    lines.append("## Output files")
    lines.append("")
    lines.append(f"- `{REPORT_DIR / 'stage23b_continuation_no_trade_discovery.json'}`")
    lines.append(f"- `{REPORT_DIR / 'stage23b_continuation_no_trade_discovery.md'}`")
    lines.append(f"- `{REPORT_DIR / 'stage23b_proxy_candidates.csv'}`")
    lines.append(f"- `{REPORT_DIR / 'stage23b_exact_candidates.csv'}`")
    lines.append(f"- `{REPORT_DIR / 'stage23b_exact_trades.csv'}`")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    started_monotonic = time.monotonic()
    deadline_ts = started_monotonic + MAX_RUNTIME_SECONDS
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")

    m1, h1, m15, load_meta = load_market_data()
    h1 = add_atr(h1)
    m15 = merge_atr(m15, h1)
    m1 = merge_atr(m1, h1)

    candidates = build_candidates()
    # Reserve part of the runtime for M1 exact replay. Without this, a weak but broad
    # proxy grid can consume the whole cap and produce Exact replayed = 0.
    exact_reserved = max(10, min(EXACT_RESERVED_SECONDS, max(10, MAX_RUNTIME_SECONDS // 2)))
    proxy_deadline_ts = min(deadline_ts, started_monotonic + max(30, MAX_RUNTIME_SECONDS - exact_reserved))
    proxy_df, event_cache, proxy_timed_out = run_proxy_grid(m15, candidates, proxy_deadline_ts)
    exact_selection = select_exact_candidates(proxy_df)
    exact_df, trades_df, exact_timed_out = run_exact_replay(m1, exact_selection, event_cache, deadline_ts)
    elapsed_seconds = round(time.monotonic() - started_monotonic, 2)

    promotion_review = 0 if exact_df.empty else int((exact_df["decision"] == "STAGE23B_PROMOTION_CANDIDATE_REVIEW_ONLY").sum())
    watchlist_only = 0 if exact_df.empty else int((exact_df["decision"] == "STAGE23B_KEEP_WATCHLIST_ONLY").sum())
    if promotion_review > 0:
        decision = "STAGE23B_HAS_PROMOTION_REVIEW_CANDIDATE_RESEARCH_ONLY"
    elif watchlist_only > 0:
        decision = "STAGE23B_HAS_WATCHLIST_ONLY_CANDIDATES"
    else:
        decision = "STAGE23B_NO_PROMOTION_KEEP_DISCOVERY_OPEN"

    report = {
        "stage": STAGE_NAME,
        "generated_utc": generated,
        "decision": decision,
        "scope": {
            "research_only": True,
            "stage18a_active_runner_unchanged": True,
            "automatic_trading_authorized": False,
            "paper_live_authorized": False,
            "orders_authorized": False,
            "watchlist_only_families_added_to_stage18a": False,
        },
        "data": {
            "m1_rows": int(len(m1)),
            "m1_start": str(m1["time"].min()),
            "m1_end": str(m1["time"].max()),
            "h1_rows": int(len(h1)),
            "h1_start": str(h1["time"].min()),
            "h1_end": str(h1["time"].max()),
            "m15_rows": int(len(m15)),
            "m15_start": str(m15["time"].min()),
            "m15_end": str(m15["time"].max()),
            "load_meta": load_meta,
        },
        "config": {
            "roundtrip_cost_usd": ROUNDTRIP_COST_USD,
            "max_exact_replay_total": MAX_EXACT_REPLAY_TOTAL,
            "max_exact_replay_per_family": MAX_EXACT_REPLAY_PER_FAMILY,
            "min_proxy_events": MIN_PROXY_EVENTS,
            "min_exact_events": MIN_EXACT_EVENTS,
            "max_runtime_seconds": MAX_RUNTIME_SECONDS,
            "max_candidates_total": MAX_CANDIDATES_TOTAL,
            "proxy_bootstrap_iters": PROXY_BOOTSTRAP_ITERS,
            "exact_bootstrap_iters": EXACT_BOOTSTRAP_ITERS,
            "data_load_mode": DATA_LOAD_MODE,
            "families": list(EVENT_GENERATORS.keys()),
        },
        "runtime": {
            "elapsed_seconds": elapsed_seconds,
            "proxy_timed_out": proxy_timed_out,
            "exact_timed_out": exact_timed_out,
        },
        "counts": {
            "proxy_candidates_total": int(len(candidates)),
            "proxy_candidates_reported": int(len(proxy_df)),
            "exact_replayed": int(len(exact_df)),
            "promotion_review": promotion_review,
            "watchlist_only": watchlist_only,
        },
        "top_proxy": _df_records(proxy_df, 30),
        "top_exact": _df_records(exact_df, 30),
    }

    proxy_path = REPORT_DIR / "stage23b_proxy_candidates.csv"
    exact_path = REPORT_DIR / "stage23b_exact_candidates.csv"
    trades_path = REPORT_DIR / "stage23b_exact_trades.csv"
    json_path = REPORT_DIR / "stage23b_continuation_no_trade_discovery.json"
    md_path = REPORT_DIR / "stage23b_continuation_no_trade_discovery.md"

    proxy_df.head(MAX_PROXY_ROWS_IN_REPORT).to_csv(proxy_path, index=False)
    exact_df.to_csv(exact_path, index=False)
    trades_df.to_csv(trades_path, index=False)
    json_path.write_text(json.dumps(_finite_for_json(report), indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(report, proxy_df, exact_df), encoding="utf-8")

    print(json.dumps(_finite_for_json({"stage": STAGE_NAME, "decision": decision, "elapsed_seconds": elapsed_seconds, "proxy_timed_out": proxy_timed_out, "exact_timed_out": exact_timed_out, "report_md": str(md_path), "report_json": str(json_path)}), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
