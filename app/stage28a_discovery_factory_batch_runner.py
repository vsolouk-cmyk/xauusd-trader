"""Stage28A DB-First Discovery Factory Batch Runner.

Research/shadow only. No EA, paper, live, or order authorization.

This module is intentionally self-contained and DB-first. It tries to reuse the
validated Stage25C loader when available, then falls back only to SQLite schema
introspection. It never reads market CSV files.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

DEFAULT_DB_PATH = Path("data/local/xauusd_local_store.sqlite")
REPORT_DIR = Path("data/reports/stage28a_discovery_factory_batch_runner")

RT_COST_X1 = float(os.getenv("STAGE28A_ROUNDTRIP_COST_X1", "0.35"))
MAX_RUNTIME_SECONDS = float(os.getenv("STAGE28A_MAX_RUNTIME_SECONDS", "210"))
MAX_EXACT = int(os.getenv("STAGE28A_MAX_EXACT", "18"))
MAX_EXACT_PER_FAMILY = int(os.getenv("STAGE28A_MAX_EXACT_PER_FAMILY", "3"))
MAX_CANDIDATES_PER_FAMILY = int(os.getenv("STAGE28A_MAX_CANDIDATES_PER_FAMILY", "6"))
MIN_EVENTS = int(os.getenv("STAGE28A_MIN_EVENTS", "45"))
BOOT_N = int(os.getenv("STAGE28A_BOOT_N", "160"))
RANDOM_SEED = int(os.getenv("STAGE28A_RANDOM_SEED", "270128"))

PROMOTION_PF_X4_MIN = float(os.getenv("STAGE28A_PROMO_PF_X4_MIN", "1.60"))
PROMOTION_PF_X6_MIN = float(os.getenv("STAGE28A_PROMO_PF_X6_MIN", "1.05"))
PROMOTION_BOOT_P05_MIN = float(os.getenv("STAGE28A_PROMO_BOOT_P05_X4_MIN", "1.05"))
PROMOTION_TOTAL_X4_MIN = float(os.getenv("STAGE28A_PROMO_TOTAL_X4_MIN", "20"))
WATCHLIST_PF_X4_MIN = float(os.getenv("STAGE28A_WATCH_PF_X4_MIN", "1.15"))


class Stage28ALoaderError(RuntimeError):
    pass


@dataclass(frozen=True)
class CandidateSpec:
    family: str
    name: str
    direction_mode: str
    entry_hour: int
    horizon_min: int
    tp_atr: float
    sl_atr: float
    params: Dict[str, Any]


def _utc(ts: pd.Series | pd.Index) -> pd.Series | pd.DatetimeIndex:
    return pd.to_datetime(ts, utc=True, errors="coerce")


def _ensure_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    if "timestamp" not in d.columns:
        for c in ["time", "datetime", "date", "broker_time", "ts", "bar_time"]:
            if c in d.columns:
                d = d.rename(columns={c: "timestamp"})
                break
    rename = {}
    for target, choices in {
        "open": ["open", "o", "Open", "OPEN"],
        "high": ["high", "h", "High", "HIGH"],
        "low": ["low", "l", "Low", "LOW"],
        "close": ["close", "c", "Close", "CLOSE"],
    }.items():
        if target not in d.columns:
            for c in choices:
                if c in d.columns:
                    rename[c] = target
                    break
    if rename:
        d = d.rename(columns=rename)
    need = ["timestamp", "open", "high", "low", "close"]
    missing = [c for c in need if c not in d.columns]
    if missing:
        raise Stage28ALoaderError(f"OHLC columns missing after schema introspection: {missing}; columns={list(df.columns)}")
    d["timestamp"] = _utc(d["timestamp"])
    d = d.dropna(subset=["timestamp", "open", "high", "low", "close"]).copy()
    for c in ["open", "high", "low", "close"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["open", "high", "low", "close"])
    d = d.sort_values("timestamp").drop_duplicates("timestamp", keep="last")
    d = d.set_index("timestamp")[["open", "high", "low", "close"]]
    return d


def _try_stage25c_loader(db_path: Path) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Dict[str, Any]]:
    """Best-effort wrapper around prior validated loaders with unknown signatures."""
    attempts: List[Tuple[str, Callable[..., Any]]] = []
    for mod_name in [
        "app.stage25c_deduped_filter_validation",
        "app.stage27c_db_first_h1_atr_gate_validation",
        "app.stage27d_db_first_h1_atr_filtered_forward_shadow",
        "app.stage25d_db_first_filtered_forward_shadow",
    ]:
        try:
            mod = __import__(mod_name, fromlist=["dummy"])
        except Exception:
            continue
        for fn_name in ["load_bars_from_db", "load_bars_from_db_stage25c", "load_ohlc_from_db"]:
            fn = getattr(mod, fn_name, None)
            if callable(fn):
                attempts.append((f"{mod_name}.{fn_name}", fn))
    errors: List[str] = []
    for label, fn in attempts:
        for args in [(db_path,), (str(db_path),), (db_path, "M1"), (str(db_path), "M1")]:
            try:
                out = fn(*args)
            except Exception as exc:
                errors.append(f"{label}{args}: {type(exc).__name__}: {exc}")
                continue
            try:
                if isinstance(out, tuple):
                    dfs = [x for x in out if isinstance(x, pd.DataFrame)]
                    if len(dfs) >= 2:
                        m1 = _ensure_ohlc(dfs[0].reset_index() if "timestamp" not in dfs[0].columns else dfs[0])
                        h1 = _ensure_ohlc(dfs[1].reset_index() if "timestamp" not in dfs[1].columns else dfs[1])
                        if len(m1) and len(h1):
                            return m1, h1, {"loader_mode": f"reused:{label}"}
                    if len(dfs) == 1:
                        m1 = _ensure_ohlc(dfs[0].reset_index() if "timestamp" not in dfs[0].columns else dfs[0])
                        if len(m1):
                            h1 = _resample(m1, "1h")
                            return m1, h1, {"loader_mode": f"reused_single:{label}"}
                elif isinstance(out, dict):
                    frames = [v for v in out.values() if isinstance(v, pd.DataFrame)]
                    if frames:
                        m1 = _ensure_ohlc(frames[0].reset_index() if "timestamp" not in frames[0].columns else frames[0])
                        h1 = _resample(m1, "1h")
                        return m1, h1, {"loader_mode": f"reused_dict:{label}"}
                elif isinstance(out, pd.DataFrame):
                    m1 = _ensure_ohlc(out.reset_index() if "timestamp" not in out.columns else out)
                    h1 = _resample(m1, "1h")
                    return m1, h1, {"loader_mode": f"reused_df:{label}"}
            except Exception as exc:
                errors.append(f"{label} normalization: {type(exc).__name__}: {exc}")
    return None, None, {"loader_mode": "stage25c_reuse_failed", "loader_errors_sample": errors[-8:]}


def _list_sqlite_tables(conn: sqlite3.Connection) -> List[str]:
    return [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]


def _table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _pick_col(cols: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    lower = {c.lower(): c for c in cols}
    for x in candidates:
        if x.lower() in lower:
            return lower[x.lower()]
    return None


def _load_sqlite_introspection(db_path: Path) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    if not db_path.exists():
        raise Stage28ALoaderError(f"SQLite DB not found: {db_path}")
    conn = sqlite3.connect(str(db_path))
    try:
        tables = _list_sqlite_tables(conn)
        if not tables:
            raise Stage28ALoaderError("No SQLite tables found")
        chosen = "bars" if "bars" in tables else tables[0]
        cols = _table_columns(conn, chosen)
        time_col = _pick_col(cols, ["timestamp", "time", "datetime", "broker_time", "ts", "bar_time", "date"])
        open_col = _pick_col(cols, ["open", "o"])
        high_col = _pick_col(cols, ["high", "h"])
        low_col = _pick_col(cols, ["low", "l"])
        close_col = _pick_col(cols, ["close", "c"])
        tf_col = _pick_col(cols, ["timeframe", "tf", "interval", "granularity"])
        if not all([time_col, open_col, high_col, low_col, close_col]):
            raise Stage28ALoaderError(f"Could not identify OHLC schema in {chosen}; columns={cols}")

        def read_for(tf_values: Optional[Sequence[str]]) -> pd.DataFrame:
            select = f'{time_col} as timestamp, {open_col} as open, {high_col} as high, {low_col} as low, {close_col} as close'
            where = ""
            params: List[Any] = []
            if tf_col and tf_values:
                ph = ",".join(["?"] * len(tf_values))
                where = f" WHERE UPPER(CAST({tf_col} AS TEXT)) IN ({ph})"
                params = [x.upper() for x in tf_values]
            q = f"SELECT {select} FROM {chosen}{where} ORDER BY {time_col}"
            return pd.read_sql_query(q, conn, params=params)

        m1_raw = read_for(["M1", "1M", "1MIN", "1MINUTE", "1_MINUTE", "MIN1"]) if tf_col else read_for(None)
        if len(m1_raw) == 0 and tf_col:
            # Some stores use lowercase/mixed labels or numeric minute labels.
            m1_raw = read_for(["1", "60"])
        m1 = _ensure_ohlc(m1_raw)
        if len(m1) == 0:
            raise Stage28ALoaderError("No M1 OHLC candles found after SQLite introspection")
        h1 = pd.DataFrame()
        if tf_col:
            h1_raw = read_for(["H1", "1H", "60M", "1HOUR", "1_HOUR", "HOUR1"])
            if len(h1_raw):
                h1 = _ensure_ohlc(h1_raw)
        if len(h1) == 0:
            h1 = _resample(m1, "1h")
        return m1, h1, {"loader_mode": "sqlite_schema_introspection", "table": chosen, "columns": cols, "timeframe_column": tf_col}
    finally:
        conn.close()


def _resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    o = df["open"].resample(rule, label="left", closed="left").first()
    h = df["high"].resample(rule, label="left", closed="left").max()
    l = df["low"].resample(rule, label="left", closed="left").min()
    c = df["close"].resample(rule, label="left", closed="left").last()
    out = pd.concat([o, h, l, c], axis=1).dropna()
    out.columns = ["open", "high", "low", "close"]
    return out


def load_market(db_path: Path = DEFAULT_DB_PATH) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    m1, h1, meta = _try_stage25c_loader(db_path)
    if m1 is None or h1 is None or len(m1) == 0 or len(h1) == 0:
        m1, h1, meta2 = _load_sqlite_introspection(db_path)
        meta.update(meta2)
    m15 = _resample(m1, "15min")
    meta.update({
        "db_path": str(db_path),
        "db_first": True,
        "csv_fallback_enabled": False,
        "m1_rows": int(len(m1)),
        "h1_rows": int(len(h1)),
        "m15_rows": int(len(m15)),
        "m1_span": f"{m1.index.min()} → {m1.index.max()}" if len(m1) else "unavailable",
        "h1_span": f"{h1.index.min()} → {h1.index.max()}" if len(h1) else "unavailable",
        "m15_span": f"{m15.index.min()} → {m15.index.max()}" if len(m15) else "unavailable",
    })
    return m1, h1, m15, meta


def _atr(df: pd.DataFrame, period: int = 20) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=max(5, period // 2)).mean()


def _pf(xs: pd.Series) -> float:
    xs = pd.to_numeric(xs, errors="coerce").dropna()
    pos = xs[xs > 0].sum()
    neg = -xs[xs < 0].sum()
    if len(xs) == 0:
        return 0.0
    if neg == 0:
        return math.inf if pos > 0 else 0.0
    return float(pos / neg)


def _bootstrap_pf_p05(xs: pd.Series, n: int = BOOT_N) -> float:
    xs = pd.to_numeric(xs, errors="coerce").dropna().to_numpy(dtype=float)
    if len(xs) < 20:
        return 0.0
    rng = np.random.default_rng(RANDOM_SEED)
    vals = []
    for _ in range(n):
        sample = rng.choice(xs, size=len(xs), replace=True)
        pos = sample[sample > 0].sum()
        neg = -sample[sample < 0].sum()
        vals.append(math.inf if neg == 0 and pos > 0 else (0.0 if neg == 0 else pos / neg))
    finite = np.array([v for v in vals if np.isfinite(v)], dtype=float)
    if len(finite) == 0:
        return 0.0
    return float(np.percentile(finite, 5))


def _metrics(df: pd.DataFrame, prefix: str = "net") -> Dict[str, Any]:
    out: Dict[str, Any] = {"events": int(len(df))}
    for x in ["x1", "x4", "x6"]:
        col = f"{prefix}_{x}"
        out[f"pf_{x}"] = _pf(df[col]) if col in df.columns else 0.0
    x4 = pd.to_numeric(df.get(f"{prefix}_x4", pd.Series(dtype=float)), errors="coerce").dropna()
    out["boot_pf_p05_x4"] = _bootstrap_pf_p05(x4)
    out["median_x4"] = float(x4.median()) if len(x4) else 0.0
    out["total_x4"] = float(x4.sum()) if len(x4) else 0.0
    out["win_rate_x4"] = float((x4 > 0).mean()) if len(x4) else 0.0
    if "entry_time" in df.columns and len(df):
        years = pd.to_datetime(df["entry_time"], utc=True, errors="coerce").dt.year
        tmp = pd.DataFrame({"year": years, "x4": x4.reindex(df.index)})
        yr = tmp.dropna().groupby("year")["x4"].sum()
        out["years_positive_x4"] = int((yr > 0).sum())
        out["year_count"] = int(len(yr))
    else:
        out["years_positive_x4"] = 0
        out["year_count"] = 0
    return out


def _decision(m: Dict[str, Any]) -> str:
    if (
        m.get("events", 0) >= MIN_EVENTS
        and m.get("pf_x4", 0) >= PROMOTION_PF_X4_MIN
        and m.get("pf_x6", 0) >= PROMOTION_PF_X6_MIN
        and m.get("boot_pf_p05_x4", 0) >= PROMOTION_BOOT_P05_MIN
        and m.get("total_x4", 0) >= PROMOTION_TOTAL_X4_MIN
    ):
        return "STAGE28A_CANDIDATE_REVIEW_ONLY"
    if m.get("events", 0) >= MIN_EVENTS and m.get("pf_x4", 0) >= WATCHLIST_PF_X4_MIN and m.get("total_x4", 0) > 0:
        return "STAGE28A_WATCHLIST_ONLY"
    return "STAGE28A_REJECT"


def _rank_score(m: Dict[str, Any]) -> float:
    return float(
        min(m.get("pf_x4", 0), 6) * 1.0
        + min(m.get("pf_x6", 0), 4) * 0.6
        + min(m.get("boot_pf_p05_x4", 0), 4) * 0.7
        + np.tanh(m.get("total_x4", 0) / 100.0) * 0.8
        + np.tanh((m.get("events", 0) - MIN_EVENTS) / 200.0) * 0.2
    )


def _bar_at_or_before(df: pd.DataFrame, ts: pd.Timestamp) -> Optional[pd.Series]:
    if len(df) == 0:
        return None
    ts = pd.Timestamp(ts).tz_convert("UTC") if pd.Timestamp(ts).tzinfo else pd.Timestamp(ts, tz="UTC")
    pos = df.index.searchsorted(ts, side="right") - 1
    if pos < 0:
        return None
    return df.iloc[pos]


def _m1_replay(m1: pd.DataFrame, entry_time: pd.Timestamp, direction: int, entry_price: float, atr: float, horizon_min: int, tp_atr: float, sl_atr: float) -> Dict[str, Any]:
    if not np.isfinite(entry_price) or not np.isfinite(atr) or atr <= 0:
        return {"exit_reason": "bad_input", "gross": 0.0, "exit_time": entry_time, "exit_price": entry_price}
    start = pd.Timestamp(entry_time)
    if start.tzinfo is None:
        start = start.tz_localize("UTC")
    else:
        start = start.tz_convert("UTC")
    end = start + pd.Timedelta(minutes=int(horizon_min))
    window = m1.loc[(m1.index > start) & (m1.index <= end)]
    if len(window) == 0:
        return {"exit_reason": "no_window", "gross": 0.0, "exit_time": start, "exit_price": entry_price}
    tp = entry_price + direction * tp_atr * atr
    sl = entry_price - direction * sl_atr * atr
    last_close = float(window["close"].iloc[-1])
    for t, r in window.iterrows():
        hit_tp = bool(r["high"] >= tp) if direction > 0 else bool(r["low"] <= tp)
        hit_sl = bool(r["low"] <= sl) if direction > 0 else bool(r["high"] >= sl)
        if hit_tp and hit_sl:
            # Conservative ordering when both hit inside one M1 candle.
            exit_price = sl
            gross = direction * (exit_price - entry_price)
            return {"exit_reason": "both_hit_conservative_sl", "gross": float(gross), "exit_time": t, "exit_price": float(exit_price)}
        if hit_tp:
            exit_price = tp
            gross = direction * (exit_price - entry_price)
            return {"exit_reason": "tp", "gross": float(gross), "exit_time": t, "exit_price": float(exit_price)}
        if hit_sl:
            exit_price = sl
            gross = direction * (exit_price - entry_price)
            return {"exit_reason": "sl", "gross": float(gross), "exit_time": t, "exit_price": float(exit_price)}
    gross = direction * (last_close - entry_price)
    return {"exit_reason": "horizon", "gross": float(gross), "exit_time": window.index[-1], "exit_price": last_close}


def _build_daily_features(m15: pd.DataFrame, h1: pd.DataFrame) -> pd.DataFrame:
    d = pd.DataFrame(index=pd.date_range(m15.index.min().floor("D"), m15.index.max().floor("D"), freq="D", tz="UTC"))
    m = m15.copy()
    m["date"] = m.index.floor("D")
    m["hour"] = m.index.hour
    # Broker/server times are treated consistently as UTC-normalized timestamps from the store.
    def rng_for(hours: Sequence[int]) -> pd.DataFrame:
        x = m[m["hour"].isin(hours)].groupby("date").agg(high=("high", "max"), low=("low", "min"), open=("open", "first"), close=("close", "last"))
        x["range"] = x["high"] - x["low"]
        x["dir"] = np.sign(x["close"] - x["open"]).replace(0, np.nan)
        return x
    asia = rng_for(range(0, 7))
    london = rng_for(range(7, 12))
    early_ny = rng_for(range(12, 15))
    prev = m.groupby("date").agg(pdh=("high", "max"), pdl=("low", "min"), pdo=("open", "first"), pdc=("close", "last")).shift(1)
    d = d.join(asia.add_prefix("asia_"), how="left")
    d = d.join(london.add_prefix("london_"), how="left")
    d = d.join(early_ny.add_prefix("early_ny_"), how="left")
    d = d.join(prev, how="left")
    h = h1.copy()
    h["atr20"] = _atr(h, 20)
    h["date"] = h.index.floor("D")
    # Use last completed H1 before 12:00/13:00 as reference features.
    h["hour"] = h.index.hour
    for ref_hour in [9, 12, 13, 14, 15]:
        z = h[h["hour"] < ref_hour].groupby("date").tail(1).set_index("date")
        d[f"h1_atr20_pre_h{ref_hour}"] = z["atr20"]
        d[f"h1_bias_pre_h{ref_hour}"] = np.sign(z["close"] - z["open"]).replace(0, np.nan)
    for col in ["asia_range", "london_range", "early_ny_range"]:
        if col in d.columns:
            d[f"{col}_q30"] = d[col].rolling(250, min_periods=60).quantile(0.30)
            d[f"{col}_q70"] = d[col].rolling(250, min_periods=60).quantile(0.70)
    for ref_hour in [9, 12, 13, 14, 15]:
        col = f"h1_atr20_pre_h{ref_hour}"
        d[f"{col}_q30"] = d[col].rolling(250, min_periods=60).quantile(0.30)
        d[f"{col}_q70"] = d[col].rolling(250, min_periods=60).quantile(0.70)
    return d


def _entry_bar(m15: pd.DataFrame, date: pd.Timestamp, hour: int) -> Optional[pd.Series]:
    ts = pd.Timestamp(date) + pd.Timedelta(hours=hour)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    if ts not in m15.index:
        return _bar_at_or_before(m15, ts + pd.Timedelta(minutes=14))
    return m15.loc[ts]


def registry() -> List[CandidateSpec]:
    specs: List[CandidateSpec] = []
    for hour in [9, 12, 13, 14]:
        for q in [0.3, 0.7]:
            for mode in ["follow_london", "fade_london"]:
                specs.append(CandidateSpec("session_compression_expansion_v1", f"sess_comp_exp_{mode}_h{hour}_q{q}_tp06_sl065", mode, hour, 180, 0.6, 0.65, {"range_q": q}))
    for hour in [12, 13, 14, 15]:
        for mode in ["follow_h1", "fade_h1"]:
            for regime in ["low_to_high", "high_cooling"]:
                specs.append(CandidateSpec("volatility_transition_v1", f"vol_trans_{mode}_{regime}_h{hour}_tp06_sl065", mode, hour, 180, 0.6, 0.65, {"regime": regime}))
    for hour in [12, 13, 14]:
        for lvl in ["pdh", "pdl", "asia_high", "asia_low"]:
            for mode in ["reclaim_fade", "breakout_follow"]:
                specs.append(CandidateSpec("liquidity_sweep_regime_v1", f"liq_{lvl}_{mode}_h{hour}_tp06_sl065", mode, hour, 180, 0.6, 0.65, {"level": lvl}))
    for hour in [13, 14, 15]:
        for mode in ["align_follow", "divergence_fade"]:
            specs.append(CandidateSpec("session_handoff_imbalance_v1", f"handoff_{mode}_h{hour}_tp06_sl065", mode, hour, 180, 0.6, 0.65, {}))
    for hour in [9, 13, 15]:
        for mode in ["drop_monday", "drop_friday", "keep_tue_wed_thu"]:
            specs.append(CandidateSpec("calendar_time_risk_proxy_v1", f"calendar_{mode}_h{hour}_tp06_sl065", mode, hour, 180, 0.6, 0.65, {}))
    return specs


def _direction_for(spec: CandidateSpec, drow: pd.Series) -> Optional[int]:
    mode = spec.direction_mode
    london_dir = drow.get("london_dir")
    h1_bias = drow.get(f"h1_bias_pre_h{spec.entry_hour}")
    if mode == "follow_london":
        return int(london_dir) if pd.notna(london_dir) and london_dir != 0 else None
    if mode == "fade_london":
        return int(-london_dir) if pd.notna(london_dir) and london_dir != 0 else None
    if mode == "follow_h1":
        return int(h1_bias) if pd.notna(h1_bias) and h1_bias != 0 else None
    if mode == "fade_h1":
        return int(-h1_bias) if pd.notna(h1_bias) and h1_bias != 0 else None
    if mode in ["align_follow", "divergence_fade"]:
        a, l = drow.get("asia_dir"), drow.get("london_dir")
        if pd.isna(a) or pd.isna(l) or a == 0 or l == 0:
            return None
        if mode == "align_follow" and a == l:
            return int(l)
        if mode == "divergence_fade" and a != l:
            return int(-l)
        return None
    # For liquidity and calendar rules, direction is assigned in filter when possible.
    return None


def _event_passes(spec: CandidateSpec, drow: pd.Series, entry: pd.Series) -> Tuple[bool, Optional[int], str]:
    family = spec.family
    p = spec.params
    direction = _direction_for(spec, drow)
    if family == "session_compression_expansion_v1":
        rng = drow.get("london_range")
        qcol = "london_range_q30" if p.get("range_q") == 0.3 else "london_range_q70"
        qv = drow.get(qcol)
        if pd.isna(rng) or pd.isna(qv):
            return False, None, "missing_london_range"
        if p.get("range_q") == 0.3 and not (rng <= qv):
            return False, None, "not_compressed"
        if p.get("range_q") == 0.7 and not (rng >= qv):
            return False, None, "not_expanded"
        return direction is not None, direction, f"london_range_vs_{qcol}"
    if family == "volatility_transition_v1":
        atr = drow.get(f"h1_atr20_pre_h{spec.entry_hour}")
        q30 = drow.get(f"h1_atr20_pre_h{spec.entry_hour}_q30")
        q70 = drow.get(f"h1_atr20_pre_h{spec.entry_hour}_q70")
        if pd.isna(atr) or pd.isna(q30) or pd.isna(q70):
            return False, None, "missing_h1_atr"
        reg = p.get("regime")
        if reg == "low_to_high" and not (atr >= q30):
            return False, None, "atr_below_q30"
        if reg == "high_cooling" and not (atr <= q70):
            return False, None, "atr_above_q70"
        return direction is not None, direction, reg
    if family == "liquidity_sweep_regime_v1":
        lvl = p.get("level")
        pdh, pdl = drow.get("pdh"), drow.get("pdl")
        ah, al = drow.get("asia_high"), drow.get("asia_low")
        if lvl == "pdh" and pd.notna(pdh):
            broke = bool(entry["high"] >= pdh)
            reclaimed = bool(entry["close"] < pdh)
            direction = -1 if spec.direction_mode == "reclaim_fade" else 1
            return (broke and (reclaimed if spec.direction_mode == "reclaim_fade" else True)), direction, "pdh_break"
        if lvl == "pdl" and pd.notna(pdl):
            broke = bool(entry["low"] <= pdl)
            reclaimed = bool(entry["close"] > pdl)
            direction = 1 if spec.direction_mode == "reclaim_fade" else -1
            return (broke and (reclaimed if spec.direction_mode == "reclaim_fade" else True)), direction, "pdl_break"
        if lvl == "asia_high" and pd.notna(ah):
            broke = bool(entry["high"] >= ah)
            reclaimed = bool(entry["close"] < ah)
            direction = -1 if spec.direction_mode == "reclaim_fade" else 1
            return (broke and (reclaimed if spec.direction_mode == "reclaim_fade" else True)), direction, "asia_high_break"
        if lvl == "asia_low" and pd.notna(al):
            broke = bool(entry["low"] <= al)
            reclaimed = bool(entry["close"] > al)
            direction = 1 if spec.direction_mode == "reclaim_fade" else -1
            return (broke and (reclaimed if spec.direction_mode == "reclaim_fade" else True)), direction, "asia_low_break"
        return False, None, "missing_level"
    if family == "session_handoff_imbalance_v1":
        return direction is not None, direction, spec.direction_mode
    if family == "calendar_time_risk_proxy_v1":
        dow = pd.Timestamp(drow.name).dayofweek
        if spec.direction_mode == "drop_monday" and dow == 0:
            return False, None, "monday_dropped"
        if spec.direction_mode == "drop_friday" and dow == 4:
            return False, None, "friday_dropped"
        if spec.direction_mode == "keep_tue_wed_thu" and dow not in [1, 2, 3]:
            return False, None, "not_tue_wed_thu"
        ldir = drow.get("london_dir")
        direction = int(ldir) if pd.notna(ldir) and ldir != 0 else 1
        return True, direction, spec.direction_mode
    return False, None, "unknown_family"



def _interleave_and_cap_specs(specs: List[CandidateSpec]) -> List[CandidateSpec]:
    """Return a family-balanced execution order.

    Stage28A v1 evaluated registry specs in family blocks, so a runtime cap could
    stop after only the first one or two families. This hotfix caps each family
    and interleaves families round-robin before evaluation, making partial runs
    diagnostically useful.
    """
    by_family: Dict[str, List[CandidateSpec]] = {}
    family_order: List[str] = []
    for spec in specs:
        if spec.family not in by_family:
            by_family[spec.family] = []
            family_order.append(spec.family)
        by_family[spec.family].append(spec)

    cap = MAX_CANDIDATES_PER_FAMILY
    if cap > 0:
        by_family = {fam: vals[:cap] for fam, vals in by_family.items()}

    out: List[CandidateSpec] = []
    max_len = max((len(v) for v in by_family.values()), default=0)
    for i in range(max_len):
        for fam in family_order:
            vals = by_family.get(fam, [])
            if i < len(vals):
                out.append(vals[i])
    return out

def evaluate_candidate(spec: CandidateSpec, m1: pd.DataFrame, m15: pd.DataFrame, daily: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    # M15 ATR proxy for sizing; exact replay uses M1 path.
    m15_atr = _atr(m15, 20)
    for date, drow in daily.iterrows():
        entry = _entry_bar(m15, date, spec.entry_hour)
        if entry is None:
            continue
        ok, direction, reason = _event_passes(spec, drow, entry)
        if not ok or direction is None:
            continue
        entry_time = entry.name
        atr = float(m15_atr.loc[entry_time]) if entry_time in m15_atr.index and pd.notna(m15_atr.loc[entry_time]) else float(entry["high"] - entry["low"])
        if not np.isfinite(atr) or atr <= 0:
            continue
        replay = _m1_replay(m1, entry_time, int(direction), float(entry["close"]), atr, spec.horizon_min, spec.tp_atr, spec.sl_atr)
        gross = float(replay["gross"])
        rows.append({
            "candidate": spec.name,
            "family": spec.family,
            "entry_time": entry_time,
            "entry_hour": spec.entry_hour,
            "direction": int(direction),
            "entry_price": float(entry["close"]),
            "atr": atr,
            "horizon_min": spec.horizon_min,
            "tp_atr": spec.tp_atr,
            "sl_atr": spec.sl_atr,
            "exit_time": replay["exit_time"],
            "exit_price": replay["exit_price"],
            "exit_reason": replay["exit_reason"],
            "reason": reason,
            "gross": gross,
            "net_x1": gross - RT_COST_X1,
            "net_x4": gross - 4 * RT_COST_X1,
            "net_x6": gross - 6 * RT_COST_X1,
        })
    trades = pd.DataFrame(rows)
    met = _metrics(trades, "net") if len(trades) else _metrics(pd.DataFrame(columns=["net_x1", "net_x4", "net_x6"]), "net")
    met.update(asdict(spec))
    met["params_json"] = json.dumps(spec.params, sort_keys=True)
    met["decision"] = _decision(met)
    met["rank_score"] = _rank_score(met)
    return trades, met


def _select_family_balanced(cands: pd.DataFrame) -> pd.DataFrame:
    if len(cands) == 0:
        return cands
    passing = cands[cands["events"] >= MIN_EVENTS].copy()
    if len(passing) == 0:
        passing = cands.copy()
    passing = passing.sort_values(["rank_score", "pf_x4", "total_x4"], ascending=False)
    selected_idx: List[int] = []
    for fam, g in passing.groupby("family", sort=False):
        selected_idx.extend(g.head(MAX_EXACT_PER_FAMILY).index.tolist())
    selected = passing.loc[selected_idx].drop_duplicates("name")
    if len(selected) > MAX_EXACT:
        selected = selected.sort_values(["rank_score", "pf_x4", "total_x4"], ascending=False).head(MAX_EXACT)
    return selected


def run() -> Dict[str, Any]:
    started = time.time()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    m1, h1, m15, db_meta = load_market(DEFAULT_DB_PATH)
    daily = _build_daily_features(m15, h1)
    raw_specs = registry()
    specs = _interleave_and_cap_specs(raw_specs)
    all_rows: List[Dict[str, Any]] = []
    exact_trade_parts: List[pd.DataFrame] = []
    family_status: Dict[str, Dict[str, Any]] = {}
    timed_out = False

    for spec in specs:
        if time.time() - started > MAX_RUNTIME_SECONDS:
            timed_out = True
            break
        trades, met = evaluate_candidate(spec, m1, m15, daily)
        all_rows.append(met)
        if len(trades):
            exact_trade_parts.append(trades)
        f = family_status.setdefault(spec.family, {"candidates_tested": 0, "passing_min_events": 0, "best_pf_x4": 0.0, "best_total_x4": -1e18})
        f["candidates_tested"] += 1
        if met["events"] >= MIN_EVENTS:
            f["passing_min_events"] += 1
        f["best_pf_x4"] = max(float(f["best_pf_x4"]), float(met.get("pf_x4", 0) if np.isfinite(met.get("pf_x4", 0)) else 999.0))
        f["best_total_x4"] = max(float(f["best_total_x4"]), float(met.get("total_x4", 0)))

    candidates = pd.DataFrame(all_rows)
    if len(candidates):
        candidates = candidates.sort_values(["decision", "rank_score", "pf_x4", "total_x4"], ascending=[True, False, False, False])
    exact_trades = pd.concat(exact_trade_parts, ignore_index=True) if exact_trade_parts else pd.DataFrame()
    selected = _select_family_balanced(candidates)
    family_rows = []
    for fam, d in family_status.items():
        family_rows.append({"family": fam, **d})
    family_df = pd.DataFrame(family_rows).sort_values("best_pf_x4", ascending=False) if family_rows else pd.DataFrame()

    review_count = int((candidates.get("decision", pd.Series(dtype=str)) == "STAGE28A_CANDIDATE_REVIEW_ONLY").sum()) if len(candidates) else 0
    watch_count = int((candidates.get("decision", pd.Series(dtype=str)) == "STAGE28A_WATCHLIST_ONLY").sum()) if len(candidates) else 0
    decision = "STAGE28A_HAS_CANDIDATE_REVIEW_ONLY" if review_count else ("STAGE28A_HAS_WATCHLIST_ONLY" if watch_count else "STAGE28A_NO_PROMOTION_KEEP_DISCOVERY_OPEN")

    candidates.to_csv(REPORT_DIR / "stage28a_all_candidates.csv", index=False)
    selected.to_csv(REPORT_DIR / "stage28a_family_balanced_shortlist.csv", index=False)
    exact_trades.to_csv(REPORT_DIR / "stage28a_exact_trades.csv", index=False)
    family_df.to_csv(REPORT_DIR / "stage28a_family_coverage.csv", index=False)
    pd.DataFrame([db_meta]).to_csv(REPORT_DIR / "stage28a_db_schema_diagnostic.csv", index=False)

    result = {
        "generated_utc": pd.Timestamp.utcnow().isoformat(),
        "decision": decision,
        "scope_guardrails": [
            "Research/shadow discovery only.",
            "Stage18A/Stage23D/Stage25D/Stage27D remain unchanged.",
            "No EA change, no automatic trading, no paper/live/order authorization.",
            "Candles are DB-first from SQLite; AMarkets CSV market fallback is disabled.",
        ],
        "db_source_of_truth": db_meta,
        "counts": {
            "registry_candidate_count": len(raw_specs),
            "scheduled_candidate_count": len(specs),
            "max_candidates_per_family": MAX_CANDIDATES_PER_FAMILY,
            "candidates_tested": int(len(candidates)),
            "candidates_passing_min_events": int((candidates.get("events", pd.Series(dtype=int)) >= MIN_EVENTS).sum()) if len(candidates) else 0,
            "candidate_review_count": review_count,
            "watchlist_only_count": watch_count,
            "family_count": int(candidates["family"].nunique()) if len(candidates) else 0,
            "timed_out": bool(timed_out),
            "runtime_seconds": round(time.time() - started, 2),
        },
        "top_candidates": candidates.head(20).to_dict(orient="records") if len(candidates) else [],
        "family_coverage": family_df.to_dict(orient="records") if len(family_df) else [],
        "output_files": [
            str(REPORT_DIR / "stage28a_discovery_factory_batch_runner.json"),
            str(REPORT_DIR / "stage28a_discovery_factory_batch_runner.md"),
            str(REPORT_DIR / "stage28a_all_candidates.csv"),
            str(REPORT_DIR / "stage28a_family_balanced_shortlist.csv"),
            str(REPORT_DIR / "stage28a_exact_trades.csv"),
            str(REPORT_DIR / "stage28a_family_coverage.csv"),
            str(REPORT_DIR / "stage28a_db_schema_diagnostic.csv"),
        ],
    }
    return result


def _fmt(x: Any) -> str:
    if isinstance(x, float):
        if math.isinf(x):
            return "inf"
        return f"{x:.4f}".rstrip("0").rstrip(".")
    return str(x)


def write_report(result: Dict[str, Any]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "stage28a_discovery_factory_batch_runner.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    lines: List[str] = []
    lines.append("# Stage28A DB-First Discovery Factory Batch Runner\n")
    lines.append(f"Generated UTC: `{result['generated_utc']}`\n")
    lines.append("## Decision\n")
    lines.append("```text")
    lines.append(str(result["decision"]))
    lines.append("```\n")
    lines.append("## Scope guardrails\n")
    for item in result["scope_guardrails"]:
        lines.append(f"- {item}")
    lines.append("\n## DB source of truth\n")
    for k, v in result["db_source_of_truth"].items():
        if k == "loader_errors_sample":
            continue
        lines.append(f"- {k}: `{v}`")
    lines.append("\n## Counts\n")
    for k, v in result["counts"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("\n## Family coverage\n")
    fam_cols = ["family", "candidates_tested", "passing_min_events", "best_pf_x4", "best_total_x4"]
    lines.append("| " + " | ".join(fam_cols) + " |")
    lines.append("| " + " | ".join(["---"] * len(fam_cols)) + " |")
    for r in result["family_coverage"][:30]:
        lines.append("| " + " | ".join(_fmt(r.get(c, "")) for c in fam_cols) + " |")
    lines.append("\n## Top candidate diagnostics\n")
    cols = ["decision", "family", "name", "events", "pf_x1", "pf_x4", "pf_x6", "boot_pf_p05_x4", "median_x4", "total_x4", "win_rate_x4", "rank_score"]
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("| " + " | ".join(["---"] * len(cols)) + " |")
    for r in result["top_candidates"][:20]:
        lines.append("| " + " | ".join(_fmt(r.get(c, "")) for c in cols) + " |")
    lines.append("\n## Interpretation\n")
    lines.append("- Stage28A is a discovery factory branch, not a modification of active forward trackers.")
    lines.append("- It tests multiple independent pattern families in one batch using DB-first candles.")
    lines.append("- Hotfix: registry execution is family-interleaved with a per-family cap so timeout-limited runs still cover all families.")
    lines.append("- Candidate-review results remain research-only and require dedicated validation plus separate forward-shadow tracking.")
    lines.append("- Negative families should be archived in the registry history to avoid repeated random mutation.")
    lines.append("\n## Operational reminder\n")
    lines.append("```bash")
    lines.append("cd ~/Desktop/xauusd-trader")
    lines.append("python3 -m app.run_active_shadow_suite")
    lines.append("python3 -m app.stage28a_discovery_factory_batch_runner")
    lines.append("```")
    lines.append("\n## Output files\n")
    for f in result["output_files"]:
        lines.append(f"- `{f}`")
    (REPORT_DIR / "stage28a_discovery_factory_batch_runner.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    try:
        result = run()
    except Exception as exc:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        result = {
            "generated_utc": pd.Timestamp.utcnow().isoformat(),
            "decision": "STAGE28A_ERROR_DIAGNOSTIC_ONLY",
            "error": f"{type(exc).__name__}: {exc}",
            "scope_guardrails": [
                "DB-first is enabled.",
                "CSV market fallback is intentionally disabled.",
                "Stage18A, Stage23D, Stage25D, and Stage27D remain unchanged.",
            ],
        }
        (REPORT_DIR / "stage28a_discovery_factory_batch_runner.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        (REPORT_DIR / "stage28a_discovery_factory_batch_runner.md").write_text(
            "# Stage28A DB-First Discovery Factory Batch Runner\n\n"
            "## Decision\n\n```text\nSTAGE28A_ERROR_DIAGNOSTIC_ONLY\n```\n\n"
            "## Error\n\n```text\n" + result["error"] + "\n```\n\n"
            "- DB-first is enabled.\n- CSV market fallback is intentionally disabled.\n- Active trackers remain unchanged.\n",
            encoding="utf-8",
        )
        raise
    write_report(result)


if __name__ == "__main__":
    main()
