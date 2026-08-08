#!/usr/bin/env python3
from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import math
import shutil
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Any

import numpy as np
import pandas as pd

PROGRAM = "PRECIOUS_METALS_FINAL_RV_AND_CLUSTERED_REGIME_CALIBRATION_V1_2_DERIVED_HISTORY_CONTRACT_REPAIR"
PREFLIGHT_PASS = "PASS_PRECIOUS_METALS_RV_PREFLIGHT_REFERENCE_ONLY"
REGIME_FAIL = "REGIME_VALIDATOR_RECALIBRATION_REQUIRED"
REF_FAIL = "GOLD_SILVER_RV_NO_REFERENCE_EDGE_CLOSE_ALPHA_EXPANSION"
REF_PASS_DIAG_FAIL = "GOLD_SILVER_RV_REFERENCE_PASS_DIAGNOSTIC_BREAKDOWN"
REF_PASS_DIAG_PASS = "GOLD_SILVER_RV_REFERENCE_PASS_READY_FOR_INDEPENDENT_REPLICATION"
FAIL_CLOSED = "PRECIOUS_METALS_FINAL_RV_FAIL_CLOSED"


class CampaignError(RuntimeError):
    pass


@dataclass
class TradeMetricBundle:
    metrics: dict[str, Any]
    gates: dict[str, bool]
    passed: bool


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def last_sunday(year: int, month: int) -> int:
    last_day = calendar.monthrange(year, month)[1]
    d = datetime(year, month, last_day)
    return last_day - ((d.weekday() + 1) % 7)


def eu_dst_utc(dt_utc: datetime) -> bool:
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    else:
        dt_utc = dt_utc.astimezone(timezone.utc)
    y = dt_utc.year
    start = datetime(y, 3, last_sunday(y, 3), 1, 0, tzinfo=timezone.utc)
    end = datetime(y, 10, last_sunday(y, 10), 1, 0, tzinfo=timezone.utc)
    return start <= dt_utc < end


def server_naive_to_utc(ts: pd.Timestamp, std_minutes: int, dst_minutes: int) -> pd.Timestamp:
    py = ts.to_pydatetime().replace(tzinfo=None)
    cand_std = (py + timedelta(minutes=std_minutes)).replace(tzinfo=timezone.utc)
    cand_dst = (py + timedelta(minutes=dst_minutes)).replace(tzinfo=timezone.utc)
    std_valid = not eu_dst_utc(cand_std)
    dst_valid = eu_dst_utc(cand_dst)
    if std_valid and not dst_valid:
        return pd.Timestamp(cand_std)
    if dst_valid and not std_valid:
        return pd.Timestamp(cand_dst)
    if dst_valid:
        return pd.Timestamp(cand_dst)
    return pd.Timestamp(cand_std)


def utc_to_server_date(ts: pd.Timestamp) -> pd.Timestamp:
    py = ts.to_pydatetime().astimezone(timezone.utc)
    hours = 3 if eu_dst_utc(py) else 2
    server = ts + pd.Timedelta(hours=hours)
    return pd.Timestamp(server.date())


def _find_col(columns: Iterable[str], names: list[str]) -> str | None:
    exact = {str(c).strip().lower(): str(c) for c in columns}
    for n in names:
        if n.lower() in exact:
            return exact[n.lower()]
    return None


def amarkets_shift_minutes(server_epoch: pd.Series) -> pd.Series:
    """Return the locked AMarkets server->UTC shift for server-clock epochs.

    This deliberately matches the already-qualified cross-asset panel loader:
    winter server clock is UTC+2 (shift -120m), EU-DST summer UTC+3 (shift -180m).
    ``time_server_epoch`` is an MT5 server-clock epoch, not a true UTC Unix timestamp.
    """
    values = pd.to_numeric(server_epoch, errors="coerce")
    if values.isna().any():
        raise CampaignError("non-numeric time_server_epoch")
    parsed_server = pd.to_datetime(values.astype("int64"), unit="s", errors="coerce")
    if parsed_server.isna().any():
        raise CampaignError("invalid time_server_epoch")
    dates = parsed_server.dt.date
    out = np.full(len(parsed_server), int(-120), dtype="int64")
    for year in sorted({x.year for x in dates}):
        start_day = last_sunday(year, 3)
        end_day = last_sunday(year, 10)
        start = datetime(year, 3, start_day).date()
        end = datetime(year, 10, end_day).date()
        mask = np.array([(x >= start and x < end) for x in dates])
        out[mask] = -180
    return pd.Series(out, index=server_epoch.index, dtype="int64")


def server_epoch_to_utc(server_epoch: pd.Series) -> pd.Series:
    """Convert the established XAUUSD_CROSS_ASSET_HISTORY server epoch contract to UTC."""
    values = pd.to_numeric(server_epoch, errors="coerce")
    if values.isna().any():
        raise CampaignError("non-numeric time_server_epoch")
    naive_server = pd.to_datetime(values.astype("int64"), unit="s", errors="coerce")
    if naive_server.isna().any():
        raise CampaignError("invalid time_server_epoch")
    shifts = amarkets_shift_minutes(values.astype("int64"))
    utc = naive_server + pd.to_timedelta(shifts, unit="m")
    return pd.to_datetime(utc, utc=True)


def load_mt5_h1(path: Path, cfg: dict, symbol: str) -> pd.DataFrame:
    if not path.is_file():
        raise CampaignError(f"{symbol} H1 input not found: {path}")
    with path.open("r", encoding="utf-8-sig", errors="ignore") as fh:
        first = fh.readline()
    if "\t" in first:
        sep = "\t"
    elif ";" in first and first.count(";") > first.count(","):
        sep = ";"
    else:
        sep = ","
    df = pd.read_csv(path, sep=sep, low_memory=False)
    if df.empty:
        raise CampaignError(f"{symbol} H1 input is empty")

    cols = [str(c) for c in df.columns]
    date_col = _find_col(cols, ["<DATE>", "date"])
    time_col = _find_col(cols, ["<TIME>", "time"])
    ts_col = _find_col(cols, ["timestamp", "timestamp_utc", "datetime", "dt", "time_utc"])
    server_epoch_col = _find_col(cols, ["time_server_epoch"])
    symbol_col = _find_col(cols, ["symbol"])
    timeframe_col = _find_col(cols, ["timeframe"])
    open_col = _find_col(cols, ["<OPEN>", "open"])
    high_col = _find_col(cols, ["<HIGH>", "high"])
    low_col = _find_col(cols, ["<LOW>", "low"])
    close_col = _find_col(cols, ["<CLOSE>", "close"])

    if not all([open_col, high_col, low_col, close_col]):
        raise CampaignError(f"{symbol} OHLC schema not recognized; columns={cols}")

    # The canonical XAUUSD_CROSS_ASSET_HISTORY files use the schema:
    # program,symbol,timeframe,time_server_epoch,open,high,low,close,...
    # Filter those identity fields before timestamp conversion so a wrong file fails closed.
    if server_epoch_col:
        if symbol_col:
            df = df[df[symbol_col].astype(str).str.strip().str.upper() == symbol.upper()].copy()
            if df.empty:
                raise CampaignError(f"{symbol} server-epoch export has no matching symbol rows")
        if timeframe_col:
            df = df[df[timeframe_col].astype(str).str.strip().str.upper() == "H1"].copy()
            if df.empty:
                raise CampaignError(f"{symbol} server-epoch export has no H1 rows")

    if date_col and time_col:
        naive = pd.to_datetime(
            df[date_col].astype(str).str.strip() + " " + df[time_col].astype(str).str.strip(),
            errors="coerce",
        )
        tc = cfg["time_contract"]
        converted = [
            server_naive_to_utc(x, int(tc["standard_shift_minutes"]), int(tc["dst_shift_minutes"]))
            if not pd.isna(x) else pd.NaT
            for x in naive
        ]
        ts = pd.to_datetime(converted, utc=True, errors="coerce")
        session_date = pd.to_datetime(df[date_col], errors="coerce").dt.floor("D")
        loader = "MT5_DATE_TIME_EU_DST"
    elif server_epoch_col:
        values = pd.to_numeric(df[server_epoch_col], errors="coerce")
        if values.isna().any():
            raise CampaignError(f"{symbol} non-numeric time_server_epoch rows={int(values.isna().sum())}")
        # Preserve the actual broker-session calendar date from the server clock.
        server_naive = pd.to_datetime(values.astype("int64"), unit="s", errors="coerce")
        if server_naive.isna().any():
            raise CampaignError(f"{symbol} invalid time_server_epoch rows={int(server_naive.isna().sum())}")
        ts = server_epoch_to_utc(values)
        session_date = server_naive.dt.floor("D")
        loader = "CROSS_ASSET_SERVER_EPOCH_EU_DST"
    elif ts_col:
        ts = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
        session_date = pd.Series([utc_to_server_date(x) if not pd.isna(x) else pd.NaT for x in ts], index=df.index)
        loader = "DIRECT_UTC_TIMESTAMP"
    else:
        raise CampaignError(f"{symbol} timestamp schema not recognized; columns={cols}")

    out = pd.DataFrame({
        "timestamp_utc": ts,
        "session_date": pd.to_datetime(session_date, errors="coerce"),
        "open": pd.to_numeric(df[open_col], errors="coerce"),
        "high": pd.to_numeric(df[high_col], errors="coerce"),
        "low": pd.to_numeric(df[low_col], errors="coerce"),
        "close": pd.to_numeric(df[close_col], errors="coerce"),
    })
    raw_rows = len(out)
    out = out.dropna(subset=["timestamp_utc", "session_date", "open", "high", "low", "close"]).sort_values("timestamp_utc")
    out = out.drop_duplicates("timestamp_utc", keep="last").reset_index(drop=True)
    valid = (
        (out["high"] >= out[["open", "close", "low"]].max(axis=1))
        & (out["low"] <= out[["open", "close", "high"]].min(axis=1))
        & (out[["open", "high", "low", "close"]] > 0).all(axis=1)
    )
    if not bool(valid.all()):
        raise CampaignError(f"{symbol} OHLC invariant failure rows={int((~valid).sum())}")
    min_rows = int(cfg["data_contract"]["minimum_h1_rows"])
    if len(out) < min_rows:
        raise CampaignError(f"{symbol} insufficient H1 rows: {len(out)}; need >= {min_rows}")
    out.attrs["raw_rows"] = raw_rows
    out.attrs["loader"] = loader
    out.attrs["symbol"] = symbol
    return out


def _candidate_path(raw: str, root: Path) -> Path:
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = root / p
    return p


def resolve_symbol_input(root: Path, cfg: dict, symbol_key: str, explicit: str | None) -> Path:
    symbol = cfg["inputs"][symbol_key]["symbol"]
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.is_file():
            raise CampaignError(f"explicit {symbol} H1 input not found: {p}")
        return p
    for raw in cfg["inputs"][symbol_key].get("candidates", []):
        p = _candidate_path(raw, root)
        if p.is_file():
            return p.resolve()
    export_dir = Path(cfg["inputs"].get("mt5_export_directory", "")).expanduser()
    if export_dir.is_dir():
        tokens = [symbol.lower(), symbol.lower().replace("usd", "")]
        matches: list[Path] = []
        for p in export_dir.glob("*.csv"):
            name = p.name.lower()
            if "h1" in name and any(t in name for t in tokens):
                matches.append(p)
        if matches:
            return sorted(matches, key=lambda p: p.stat().st_size, reverse=True)[0].resolve()
    raise CampaignError(f"no {symbol} H1 file found; use explicit CLI path")


def synchronize_h1(xau: pd.DataFrame, xag: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    a = xau.rename(columns={c: f"xau_{c}" for c in ["open", "high", "low", "close"]})
    b = xag.rename(columns={c: f"xag_{c}" for c in ["open", "high", "low", "close"]})
    m = a.merge(b, on="timestamp_utc", how="inner", suffixes=("_xau", "_xag")).sort_values("timestamp_utc").reset_index(drop=True)
    if m.empty:
        raise CampaignError("no synchronized XAUUSD/XAGUSD H1 timestamps")
    if "session_date_xau" not in m.columns or "session_date_xag" not in m.columns:
        raise CampaignError("synchronized H1 data missing broker session date")
    mismatch = pd.to_datetime(m["session_date_xau"]) != pd.to_datetime(m["session_date_xag"])
    if bool(mismatch.any()):
        raise CampaignError(f"XAU/XAG broker session-date mismatch rows={int(mismatch.sum())}")
    m["session_date"] = pd.to_datetime(m["session_date_xau"]).dt.floor("D")
    m = m.drop(columns=["session_date_xau", "session_date_xag"])
    cov = len(m) / max(1, min(len(xau), len(xag)))
    if cov < float(cfg["data_contract"]["minimum_h1_overlap_fraction"]):
        raise CampaignError(f"insufficient H1 overlap fraction={cov:.6f}")
    m.attrs["overlap_fraction"] = cov
    return m


def build_common_daily(sync: pd.DataFrame) -> pd.DataFrame:
    x = sync.copy()
    # Broker-session date is preserved from MT5 before UTC conversion. This avoids Sunday partial UTC days.
    rows = []
    for d, g in x.groupby("session_date", sort=True):
        g = g.sort_values("timestamp_utc")
        if len(g) < 2:
            continue
        first = g.iloc[0]
        last = g.iloc[-1]
        rows.append({
            "date": pd.Timestamp(d, tz="UTC") if pd.Timestamp(d).tzinfo is None else pd.Timestamp(d).tz_convert("UTC"),
            "open_time_utc": first["timestamp_utc"],
            "close_time_utc": last["timestamp_utc"] + pd.Timedelta(hours=1),
            "xau_open": float(first["xau_open"]),
            "xau_close": float(last["xau_close"]),
            "xag_open": float(first["xag_open"]),
            "xag_close": float(last["xag_close"]),
            "common_h1_bars": int(len(g)),
        })
    daily = pd.DataFrame(rows)
    if daily.empty:
        raise CampaignError("daily synchronized XAU/XAG dataset is empty")
    daily = daily.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)
    daily["xau_log_close"] = np.log(daily["xau_close"])
    daily["xag_log_close"] = np.log(daily["xag_close"])
    daily["naive_spread_return_bps"] = (daily["xau_log_close"].diff() - daily["xag_log_close"].diff()) * 10000.0
    return daily


def ols_y_on_x(y: np.ndarray, x: np.ndarray) -> tuple[float, float, np.ndarray, float]:
    y = np.asarray(y, dtype=float)
    x = np.asarray(x, dtype=float)
    if len(y) != len(x) or len(y) < 5:
        raise CampaignError("OLS requires aligned arrays with at least 5 observations")
    X = np.column_stack([np.ones(len(x)), x])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    alpha, beta = float(coef[0]), float(coef[1])
    resid = y - (alpha + beta * x)
    sst = float(np.sum((y - y.mean()) ** 2))
    ssr = float(np.sum(resid ** 2))
    r2 = float(1.0 - ssr / sst) if sst > 0 else float("nan")
    return alpha, beta, resid, r2


def residual_ar1_diagnostics(resid: np.ndarray) -> dict[str, float | None]:
    r = np.asarray(resid, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < 20:
        return {"ar1_phi": None, "half_life_days": None, "df_t_stat": None}
    y = r[1:]
    x = r[:-1]
    X = np.column_stack([np.ones(len(x)), x])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    phi = float(coef[1])
    half = None
    if 0.0 < phi < 1.0:
        half = float(-math.log(2.0) / math.log(phi))

    dy = np.diff(r)
    lag = r[:-1]
    XD = np.column_stack([np.ones(len(lag)), lag])
    b, *_ = np.linalg.lstsq(XD, dy, rcond=None)
    err = dy - XD @ b
    dof = max(1, len(dy) - XD.shape[1])
    sigma2 = float(np.sum(err * err) / dof)
    try:
        cov = sigma2 * np.linalg.inv(XD.T @ XD)
        se = math.sqrt(max(float(cov[1, 1]), 0.0))
        tstat = float(b[1] / se) if se > 0 else None
    except np.linalg.LinAlgError:
        tstat = None
    return {"ar1_phi": phi, "half_life_days": half, "df_t_stat": tstat}


def formation_at(daily: pd.DataFrame, decision_idx: int, cfg: dict) -> dict[str, Any] | None:
    w = int(cfg["strategy"]["formation_days"])
    if decision_idx < w:
        return None
    train = daily.iloc[decision_idx - w:decision_idx]
    y = train["xau_log_close"].to_numpy(dtype=float)
    x = train["xag_log_close"].to_numpy(dtype=float)
    alpha, beta, resid, r2 = ols_y_on_x(y, x)
    resid_std = float(np.std(resid, ddof=1))
    if not np.isfinite(resid_std) or resid_std <= 1e-12:
        return None
    cur = daily.iloc[decision_idx]
    spread = float(cur["xau_log_close"] - alpha - beta * cur["xag_log_close"])
    z = spread / resid_std
    d = residual_ar1_diagnostics(resid)
    return {
        "alpha": alpha,
        "beta": beta,
        "resid_std": resid_std,
        "z": float(z),
        "formation_r2": r2,
        **d,
    }


def _pair_weights(side: int, beta: float) -> tuple[float, float]:
    denom = 1.0 + abs(beta)
    return float(side / denom), float(-side * beta / denom)


def simulate_pair_trades(daily: pd.DataFrame, cfg: dict, entry_start: pd.Timestamp, entry_end: pd.Timestamp) -> pd.DataFrame:
    s = cfg["strategy"]
    entry_z = float(s["entry_abs_z"])
    stop_z = float(s["stop_abs_z"])
    max_hold = int(s["maximum_holding_days"])
    normal_cost = float(s["normal_roundtrip_cost_bps"]) / 10000.0
    severe_cost = float(s["severe_roundtrip_cost_bps"]) / 10000.0

    trades: list[dict[str, Any]] = []
    i = int(s["formation_days"])
    n = len(daily)
    while i < n - 1:
        decision_date = pd.Timestamp(daily.iloc[i]["date"])
        if decision_date < entry_start:
            i += 1
            continue
        if decision_date >= entry_end:
            break
        f = formation_at(daily, i, cfg)
        if not f or not np.isfinite(f["z"]) or abs(float(f["z"])) < entry_z:
            i += 1
            continue
        beta = float(f["beta"])
        if not np.isfinite(beta) or beta <= 0:
            i += 1
            continue
        side = -1 if float(f["z"]) > 0 else 1
        entry_idx = i + 1
        if entry_idx >= n:
            break
        entry_row = daily.iloc[entry_idx]
        entry_date = pd.Timestamp(entry_row["date"])
        if entry_date >= entry_end:
            break
        w_xau, w_xag = _pair_weights(side, beta)

        exit_reason = None
        exit_signal_idx = None
        last_possible = min(n - 2, entry_idx + max_hold - 1)
        for j in range(entry_idx, last_possible + 1):
            row = daily.iloc[j]
            spread = float(row["xau_log_close"] - float(f["alpha"]) - beta * row["xag_log_close"])
            z_now = spread / float(f["resid_std"])
            mean_cross = (side == 1 and z_now >= 0.0) or (side == -1 and z_now <= 0.0)
            adverse_stop = (side == 1 and z_now <= -stop_z) or (side == -1 and z_now >= stop_z)
            maxed = (j - entry_idx + 1) >= max_hold
            if mean_cross:
                exit_reason = "MEAN_CROSS"
                exit_signal_idx = j
                break
            if adverse_stop:
                exit_reason = "Z_STOP"
                exit_signal_idx = j
                break
            if maxed:
                exit_reason = "MAX_HOLD"
                exit_signal_idx = j
                break
        if exit_signal_idx is None:
            i = entry_idx + 1
            continue
        exit_idx = exit_signal_idx + 1
        if exit_idx >= n:
            break
        exit_row = daily.iloc[exit_idx]
        exit_date = pd.Timestamp(exit_row["date"])
        if exit_date >= entry_end:
            # Strict boundary: a reference trade may not consume post-boundary prices.
            i = exit_idx
            continue

        xau_ret = float(exit_row["xau_open"] / entry_row["xau_open"] - 1.0)
        xag_ret = float(exit_row["xag_open"] / entry_row["xag_open"] - 1.0)
        gross = float(w_xau * xau_ret + w_xag * xag_ret)
        normal = gross - normal_cost
        severe = gross - severe_cost
        inverted_severe = -gross - severe_cost
        trades.append({
            "decision_date": decision_date,
            "entry_date": entry_date,
            "exit_date": exit_date,
            "entry_z": float(f["z"]),
            "side": "LONG_SPREAD" if side == 1 else "SHORT_SPREAD",
            "side_sign": side,
            "alpha": float(f["alpha"]),
            "beta": beta,
            "formation_resid_std": float(f["resid_std"]),
            "formation_r2": float(f["formation_r2"]),
            "formation_ar1_phi": f["ar1_phi"],
            "formation_half_life_days": f["half_life_days"],
            "formation_df_t_stat": f["df_t_stat"],
            "w_xau": w_xau,
            "w_xag": w_xag,
            "entry_xau_open": float(entry_row["xau_open"]),
            "entry_xag_open": float(entry_row["xag_open"]),
            "exit_xau_open": float(exit_row["xau_open"]),
            "exit_xag_open": float(exit_row["xag_open"]),
            "xau_return": xau_ret,
            "xag_return": xag_ret,
            "gross_return": gross,
            "normal_net_return": normal,
            "severe_net_return": severe,
            "inverted_severe_return": inverted_severe,
            "holding_days": int(exit_idx - entry_idx),
            "exit_reason": exit_reason,
        })
        i = exit_idx
    out = pd.DataFrame(trades)
    for c in ["decision_date", "entry_date", "exit_date"]:
        if c in out.columns:
            out[c] = pd.to_datetime(out[c], utc=True)
    return out


def profit_factor(values: Iterable[float]) -> float:
    arr = np.asarray(list(values), dtype=float)
    arr = arr[np.isfinite(arr)]
    pos = float(arr[arr > 0].sum())
    neg = float(-arr[arr < 0].sum())
    if neg <= 0:
        return float("inf") if pos > 0 else 0.0
    return pos / neg


def moving_block_bootstrap_means(values: np.ndarray, reps: int, block: int, seed: int) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        return np.asarray([], dtype=float)
    rng = np.random.default_rng(seed)
    n = len(arr)
    block = max(1, min(int(block), n))
    blocks_needed = int(math.ceil(n / block))
    starts = rng.integers(0, n, size=(int(reps), blocks_needed))
    offsets = np.arange(block, dtype=int)
    idx = (starts[:, :, None] + offsets[None, None, :]) % n
    idx = idx.reshape(int(reps), -1)[:, :n]
    return arr[idx].mean(axis=1)


def compounded_annualized(values: Iterable[float], years: float) -> float:
    eq = 1.0
    for v in values:
        eq *= max(1e-12, 1.0 + float(v))
    return float(eq ** (1.0 / max(years, 1e-9)) - 1.0) if eq > 0 else -1.0


def max_drawdown(values: Iterable[float]) -> float:
    eq = 1.0
    peak = 1.0
    worst = 0.0
    for v in values:
        eq *= max(1e-12, 1.0 + float(v))
        peak = max(peak, eq)
        worst = min(worst, eq / peak - 1.0)
    return float(worst)


def reference_years(cfg: dict) -> float:
    start = pd.Timestamp(cfg["selection"]["reference_start_utc"])
    end = pd.Timestamp(cfg["selection"]["reference_end_utc"])
    return max((end - start).total_seconds() / (365.2425 * 86400.0), 1e-9)


def fold_metrics(trades: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(columns=["fold", "trades", "mean_severe_return", "annualized_return"])
    start = pd.Timestamp(cfg["selection"]["reference_start_utc"])
    end = pd.Timestamp(cfg["selection"]["reference_end_utc"])
    edges = pd.date_range(start=start, end=end, periods=4)
    rows = []
    for k in range(3):
        a, b = edges[k], edges[k + 1]
        m = trades[(trades["entry_date"] >= a) & (trades["entry_date"] < b)]
        years = max((b - a).total_seconds() / (365.2425 * 86400.0), 1e-9)
        rows.append({
            "fold": f"F{k+1}",
            "start_utc": a,
            "end_utc": b,
            "trades": int(len(m)),
            "mean_severe_return": float(m["severe_net_return"].mean()) if len(m) else float("nan"),
            "annualized_return": compounded_annualized(m["severe_net_return"], years) if len(m) else float("nan"),
        })
    return pd.DataFrame(rows)


def year_metrics(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(columns=["year", "trades", "net_return", "mean_severe_return"])
    t = trades.copy()
    t["year"] = t["exit_date"].dt.year
    rows = []
    for y, g in t.groupby("year"):
        rows.append({
            "year": int(y),
            "trades": int(len(g)),
            "net_return": float(np.prod(1.0 + g["severe_net_return"].to_numpy(dtype=float)) - 1.0),
            "mean_severe_return": float(g["severe_net_return"].mean()),
        })
    return pd.DataFrame(rows).sort_values("year").reset_index(drop=True)


def random_side_control(trades: pd.DataFrame, cfg: dict) -> dict[str, float | int | None]:
    if trades.empty:
        return {"reps": 0, "actual_mean": None, "random_mean_p90": None, "random_mean_p95": None, "actual_percentile": None}
    c = cfg["validation"]["random_side_control"]
    reps = int(c["reps"])
    seed = int(c["seed"])
    rng = np.random.default_rng(seed)
    gross_abs_directionless = np.abs(trades["gross_return"].to_numpy(dtype=float))
    cost = float(cfg["strategy"]["severe_roundtrip_cost_bps"]) / 10000.0
    means = np.empty(reps, dtype=float)
    for i in range(reps):
        signs = rng.choice(np.asarray([-1.0, 1.0]), size=len(gross_abs_directionless))
        means[i] = float(np.mean(signs * gross_abs_directionless - cost))
    actual = float(trades["severe_net_return"].mean())
    pct = float(np.mean(means < actual))
    return {
        "reps": reps,
        "actual_mean": actual,
        "random_mean_p90": float(np.quantile(means, 0.90)),
        "random_mean_p95": float(np.quantile(means, 0.95)),
        "actual_percentile": pct,
    }


def evaluate_reference(trades: pd.DataFrame, cfg: dict) -> TradeMetricBundle:
    v = cfg["validation"]
    g = v["reference_gates"]
    arr = trades["severe_net_return"].to_numpy(dtype=float) if not trades.empty else np.asarray([], dtype=float)
    years = reference_years(cfg)
    boots = moving_block_bootstrap_means(arr, int(v["bootstrap_reps"]), int(v["bootstrap_block_trades"]), int(v["bootstrap_seed"]))
    p10 = float(np.quantile(boots, 0.10)) if len(boots) else float("nan")
    remove_best = float((arr.sum() - arr.max()) / (len(arr) - 1)) if len(arr) >= 2 else float("nan")
    folds = fold_metrics(trades, cfg)
    finite_fold_ann = folds["annualized_return"].dropna().to_numpy(dtype=float) if not folds.empty else np.asarray([], dtype=float)
    positive_folds = int(np.sum(finite_fold_ann > 0))
    years_df = year_metrics(trades)
    positive_year_share = float(np.mean(years_df["net_return"] > 0)) if len(years_df) else float("nan")
    pos_years = years_df.loc[years_df["net_return"] > 0, "net_return"].to_numpy(dtype=float) if len(years_df) else np.asarray([], dtype=float)
    pos_year_conc = float(pos_years.max() / pos_years.sum()) if len(pos_years) and pos_years.sum() > 0 else float("nan")
    pos_trades = arr[arr > 0]
    trade_conc = float(pos_trades.max() / pos_trades.sum()) if len(pos_trades) and pos_trades.sum() > 0 else float("nan")
    control = random_side_control(trades, cfg)
    metrics = {
        "trades": int(len(trades)),
        "mean_severe_return": float(np.mean(arr)) if len(arr) else float("nan"),
        "mean_severe_bps": float(np.mean(arr) * 10000.0) if len(arr) else float("nan"),
        "profit_factor": profit_factor(arr),
        "bootstrap_p10_mean_return": p10,
        "bootstrap_p10_mean_bps": p10 * 10000.0 if np.isfinite(p10) else float("nan"),
        "remove_best_trade_mean_return": remove_best,
        "annualized_return": compounded_annualized(arr, years) if len(arr) else float("nan"),
        "max_drawdown": max_drawdown(arr) if len(arr) else float("nan"),
        "positive_folds": positive_folds,
        "worst_fold_annualized_return": float(np.min(finite_fold_ann)) if len(finite_fold_ann) else float("nan"),
        "positive_year_share": positive_year_share,
        "max_positive_year_profit_share": pos_year_conc,
        "max_positive_trade_profit_share": trade_conc,
        "inverted_mean_severe_return": float(trades["inverted_severe_return"].mean()) if len(trades) else float("nan"),
        "random_side_actual_percentile": control["actual_percentile"],
        "random_side_p90_mean": control["random_mean_p90"],
        "median_holding_days": float(trades["holding_days"].median()) if len(trades) else float("nan"),
        "median_formation_r2": float(trades["formation_r2"].median()) if len(trades) else float("nan"),
        "median_half_life_days": float(trades["formation_half_life_days"].dropna().median()) if len(trades) and trades["formation_half_life_days"].notna().any() else float("nan"),
    }
    checks = {
        "minimum_trades": metrics["trades"] >= int(g["minimum_trades"]),
        "mean_severe_positive": metrics["mean_severe_return"] > 0.0,
        "profit_factor": metrics["profit_factor"] >= float(g["minimum_profit_factor"]),
        "bootstrap_p10_positive": metrics["bootstrap_p10_mean_return"] > 0.0,
        "remove_best_positive": metrics["remove_best_trade_mean_return"] > 0.0,
        "annualized_return": metrics["annualized_return"] >= float(g["minimum_annualized_return"]),
        "max_drawdown": metrics["max_drawdown"] >= -float(g["maximum_drawdown_abs"]),
        "positive_folds": metrics["positive_folds"] >= int(g["minimum_positive_folds"]),
        "worst_fold": metrics["worst_fold_annualized_return"] >= float(g["minimum_worst_fold_annualized_return"]),
        "positive_year_share": metrics["positive_year_share"] >= float(g["minimum_positive_year_share"]),
        "year_concentration": np.isfinite(metrics["max_positive_year_profit_share"]) and metrics["max_positive_year_profit_share"] <= float(g["maximum_positive_year_profit_share"]),
        "trade_concentration": np.isfinite(metrics["max_positive_trade_profit_share"]) and metrics["max_positive_trade_profit_share"] <= float(g["maximum_positive_trade_profit_share"]),
        "beats_inverted": metrics["mean_severe_return"] > metrics["inverted_mean_severe_return"],
        "random_side_control": metrics["random_side_actual_percentile"] is not None and metrics["random_side_actual_percentile"] >= float(g["minimum_random_side_percentile"]),
    }
    return TradeMetricBundle(metrics=metrics, gates=checks, passed=all(checks.values()))


def evaluate_diagnostic(trades: pd.DataFrame, cfg: dict) -> TradeMetricBundle:
    if trades.empty:
        return TradeMetricBundle(metrics={"trades": 0}, gates={"minimum_trades": False}, passed=False)
    d = cfg["validation"]["diagnostic_gates"]
    arr = trades["severe_net_return"].to_numpy(dtype=float)
    years = max((trades["exit_date"].max() - trades["entry_date"].min()).total_seconds() / (365.2425 * 86400.0), 1e-9)
    metrics = {
        "trades": int(len(trades)),
        "mean_severe_return": float(arr.mean()),
        "profit_factor": profit_factor(arr),
        "annualized_return": compounded_annualized(arr, years),
        "max_drawdown": max_drawdown(arr),
    }
    gates = {
        "minimum_trades": metrics["trades"] >= int(d["minimum_trades"]),
        "mean_positive": metrics["mean_severe_return"] > 0,
        "profit_factor": metrics["profit_factor"] >= float(d["minimum_profit_factor"]),
        "annualized_return": metrics["annualized_return"] >= float(d["minimum_annualized_return"]),
        "max_drawdown": metrics["max_drawdown"] >= -float(d["maximum_drawdown_abs"]),
    }
    return TradeMetricBundle(metrics=metrics, gates=gates, passed=all(gates.values()))


def deterministic_cluster_mask(dates: pd.Series, clusters: int, cluster_days: int) -> np.ndarray:
    n = len(dates)
    mask = np.zeros(n, dtype=bool)
    if n < clusters * cluster_days:
        raise CampaignError("insufficient daily rows for clustered calibration")
    edges = np.linspace(0, n, clusters + 1, dtype=int)
    for k in range(clusters):
        a, b = edges[k], edges[k + 1]
        width = b - a
        if width < cluster_days:
            raise CampaignError("calibration partition shorter than requested cluster")
        start = a + (width - cluster_days) // 2
        mask[start:start + cluster_days] = True
    return mask


def block_resample(arr: np.ndarray, n: int, block: int, rng: np.random.Generator) -> np.ndarray:
    x = np.asarray(arr, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < 10:
        raise CampaignError("insufficient empirical spread returns for calibration")
    block = max(1, min(int(block), len(x)))
    out = []
    while len(out) < n:
        start = int(rng.integers(0, len(x)))
        for j in range(block):
            out.append(float(x[(start + j) % len(x)]))
            if len(out) >= n:
                break
    return np.asarray(out, dtype=float)


def clustered_gate(values: np.ndarray, cluster_id: np.ndarray, cfg: dict, seed: int) -> bool:
    c = cfg["clustered_calibration"]
    rng = np.random.default_rng(seed)
    arr = np.asarray(values, dtype=float)
    boots = moving_block_bootstrap_means(arr, int(c["bootstrap_reps"]), int(c["bootstrap_block_trades"]), int(rng.integers(1, 2**31 - 1)))
    p10 = float(np.quantile(boots, 0.10)) if len(boots) else float("nan")
    remove_best = float((arr.sum() - arr.max()) / (len(arr) - 1)) if len(arr) >= 2 else float("nan")
    cluster_means = []
    cluster_sums = []
    for cid in sorted(set(int(x) for x in cluster_id)):
        v = arr[cluster_id == cid]
        cluster_means.append(float(v.mean()))
        cluster_sums.append(float(v.sum()))
    positive_clusters = sum(x > 0 for x in cluster_means)
    positive_sums = [x for x in cluster_sums if x > 0]
    concentration = float(max(positive_sums) / sum(positive_sums)) if positive_sums and sum(positive_sums) > 0 else float("nan")
    checks = [
        float(arr.mean()) > 0,
        p10 > 0,
        remove_best > 0,
        positive_clusters >= int(c["minimum_positive_clusters"]),
        np.isfinite(concentration) and concentration <= float(c["maximum_positive_cluster_profit_share"]),
    ]
    return all(checks)


def run_clustered_regime_calibration(daily_ref: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, dict[str, Any]]:
    c = cfg["clustered_calibration"]
    dates = daily_ref["date"].reset_index(drop=True)
    mask = deterministic_cluster_mask(dates, int(c["clusters"]), int(c["cluster_days"]))
    selected_idx = np.flatnonzero(mask)
    cluster_id_full = np.full(len(dates), -1, dtype=int)
    edges = np.linspace(0, len(dates), int(c["clusters"]) + 1, dtype=int)
    for k in range(int(c["clusters"])):
        a, b = edges[k], edges[k + 1]
        width = b - a
        start = a + (width - int(c["cluster_days"])) // 2
        cluster_id_full[start:start + int(c["cluster_days"])] = k
    cluster_ids = cluster_id_full[selected_idx]

    empirical = daily_ref["naive_spread_return_bps"].dropna().to_numpy(dtype=float)
    sigma = float(np.std(empirical, ddof=1))
    if not np.isfinite(sigma) or sigma <= 0:
        raise CampaignError("invalid empirical spread-return sigma for calibration")
    planted_edge_bps = float(c["planted_edge_sigma_fraction"]) * sigma
    trials = int(c["trials"])
    seed = int(c["seed"])
    rows = []
    for kind, edge in [("NULL", 0.0), ("OBSERVABLE_CLUSTERED_EDGE", planted_edge_bps)]:
        passes = 0
        for trial in range(trials):
            rng = np.random.default_rng(seed + trial + (100000 if edge else 0))
            noise = block_resample(empirical, len(dates), int(c["empirical_resample_block_days"]), rng)
            noise = noise - float(np.mean(noise))
            vals = noise[selected_idx] + edge
            passed = clustered_gate(vals, cluster_ids, cfg, seed + trial * 31 + (1 if edge else 0))
            passes += int(passed)
        rows.append({
            "control": kind,
            "trials": trials,
            "selected_regime_trades": int(len(selected_idx)),
            "cluster_count": int(c["clusters"]),
            "cluster_days": int(c["cluster_days"]),
            "empirical_spread_sigma_bps": sigma,
            "planted_edge_bps": edge,
            "gate_pass_rate": passes / trials,
        })
    curve = pd.DataFrame(rows)
    null_rate = float(curve.loc[curve["control"] == "NULL", "gate_pass_rate"].iloc[0])
    edge_rate = float(curve.loc[curve["control"] == "OBSERVABLE_CLUSTERED_EDGE", "gate_pass_rate"].iloc[0])
    checks = {
        "null_false_positive": null_rate <= float(c["maximum_null_pass_rate"]),
        "clustered_edge_detection": edge_rate >= float(c["minimum_edge_detection_rate"]),
    }
    summary = {
        "decision": "REGIME_VALIDATOR_CALIBRATED_PASS" if all(checks.values()) else REGIME_FAIL,
        "pass": all(checks.values()),
        "checks": checks,
        "null_pass_rate": null_rate,
        "observable_clustered_edge_detection_rate": edge_rate,
        "planted_edge_bps": planted_edge_bps,
        "empirical_spread_sigma_bps": sigma,
        "regime_contract": "4 deterministic time clusters defined independently of returns; synthetic regime flag is known before simulated outcome; empirical spread-return noise is block-resampled.",
    }
    return curve, summary


def static_execution_violations(root: Path) -> list[str]:
    # AST-based scan avoids false positives from documentation/checker literals.
    import ast
    path = root / "app" / "precious_metals_final_rv.py"
    if not path.is_file():
        return ["APP_FILE_MISSING"]
    tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    violations: list[str] = []
    banned_import_roots = {"MetaTrader5", "requests", "urllib", "socket", "subprocess"}
    banned_call_suffixes = {"order_send", "initialize", "urlopen", "request", "run", "Popen"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in banned_import_roots:
                    violations.append(f"IMPORT:{alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.split(".")[0] in banned_import_roots:
                violations.append(f"IMPORT_FROM:{module}")
        elif isinstance(node, ast.Call):
            fn = node.func
            name = None
            if isinstance(fn, ast.Name):
                name = fn.id
            elif isinstance(fn, ast.Attribute):
                name = fn.attr
            if name in banned_call_suffixes:
                # Only flag dangerous call names when their module/object is explicit enough.
                rendered = ast.unparse(fn) if hasattr(ast, "unparse") else str(name)
                if any(tok in rendered for tok in ["mt5", "MetaTrader5", "requests", "urllib", "socket", "subprocess"]) or name == "order_send":
                    violations.append(f"CALL:{rendered}")
    return sorted(set(violations))


def output_manifest(outdir: Path, exclude: set[str] | None = None) -> dict:
    exclude = exclude or set()
    files = []
    for p in sorted(outdir.rglob("*")):
        if not p.is_file() or p.name in exclude:
            continue
        files.append({
            "path": str(p.relative_to(outdir)),
            "bytes": p.stat().st_size,
            "sha256": sha256_file(p),
        })
    return {"generated_utc": utc_now(), "files": files}


def archive_existing(outdir: Path) -> str | None:
    if not outdir.exists() or not any(outdir.iterdir()):
        outdir.mkdir(parents=True, exist_ok=True)
        return None
    parent = outdir.parent / "_archive_precious_metals_final_rv"
    parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = parent / stamp
    shutil.move(str(outdir), str(dest))
    outdir.mkdir(parents=True, exist_ok=True)
    return str(dest)



def validate_reference_history(daily: pd.DataFrame, cfg: dict) -> dict[str, Any]:
    """Validate preflight history using requirements derived from the locked strategy.

    The contract is one full formation window plus at least six post-formation
    evaluation years, supporting the predeclared three-fold stability review at
    roughly two years per fold. This is a data-adequacy contract, not a performance gate.
    """
    ref_end = pd.Timestamp(cfg["selection"]["reference_end_utc"])
    ref_start = pd.Timestamp(cfg["selection"]["reference_start_utc"])
    formation_days = int(cfg["strategy"]["formation_days"])
    min_eval_years = int(cfg["data_contract"]["minimum_post_formation_reference_years"])
    min_eval_rows = int(min_eval_years * 252)
    ref = daily[daily["date"] < ref_end].copy().reset_index(drop=True)
    if len(ref) <= formation_days:
        raise CampaignError(
            f"insufficient synchronized daily rows for formation: rows={len(ref)} formation={formation_days}"
        )
    effective = ref.iloc[formation_days:].copy()
    effective = effective[effective["date"] >= ref_start].copy()
    if len(effective) < min_eval_rows:
        raise CampaignError(
            "insufficient post-formation reference history: "
            f"effective_rows={len(effective)} required={min_eval_rows} "
            f"formation={formation_days} min_eval_years={min_eval_years}"
        )
    effective_years = int(effective["date"].dt.year.nunique())
    if effective_years < min_eval_years:
        raise CampaignError(
            "insufficient distinct post-formation reference years: "
            f"years={effective_years} required={min_eval_years}"
        )
    return {
        "formation_days": formation_days,
        "minimum_post_formation_reference_years": min_eval_years,
        "minimum_post_formation_reference_rows": min_eval_rows,
        "effective_reference_rows_after_formation": int(len(effective)),
        "effective_reference_distinct_years": effective_years,
        "effective_reference_first_date": str(effective["date"].min()),
        "effective_reference_last_date": str(effective["date"].max()),
    }

def preflight(root: Path, config_path: Path, xau_arg: str | None, xag_arg: str | None) -> dict:
    cfg = read_json(config_path)
    xau_path = resolve_symbol_input(root, cfg, "xau", xau_arg)
    xag_path = resolve_symbol_input(root, cfg, "xag", xag_arg)
    xau = load_mt5_h1(xau_path, cfg, "XAUUSD")
    xag = load_mt5_h1(xag_path, cfg, "XAGUSD")
    sync = synchronize_h1(xau, xag, cfg)
    daily = build_common_daily(sync)
    ref_end = pd.Timestamp(cfg["selection"]["reference_end_utc"])
    ref_start = pd.Timestamp(cfg["selection"]["reference_start_utc"])
    history = validate_reference_history(daily, cfg)
    violations = static_execution_violations(root)
    if violations:
        raise CampaignError(f"static execution/network violations: {violations}")
    return {
        "program": PROGRAM,
        "generated_utc": utc_now(),
        "decision": PREFLIGHT_PASS,
        "pass": True,
        "paper_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
        "xau_path": str(xau_path),
        "xag_path": str(xag_path),
        "xau_rows": int(len(xau)),
        "xag_rows": int(len(xag)),
        "synchronized_h1_rows": int(len(sync)),
        "h1_overlap_fraction": float(sync.attrs["overlap_fraction"]),
        "daily_rows": int(len(daily)),
        "first_daily_date": str(daily["date"].min()),
        "last_daily_date": str(daily["date"].max()),
        **history,
        "reference_end_utc": str(ref_end),
        "diagnostic_policy": "2025_PLUS_NOT_COMPUTED_UNLESS_REFERENCE_PASS",
        "static_execution_violations": [],
        "scope_contract": "Gold-centered precious-metals relative-value test. Broader diversified portfolio scope is allowed by project policy but is not scanned by this package.",
    }


def run_campaign(root: Path, config_path: Path, xau_arg: str | None, xag_arg: str | None) -> dict:
    cfg = read_json(config_path)
    outdir = root / cfg["outputs"]["report_dir"]
    archived = archive_existing(outdir)
    xau_path = resolve_symbol_input(root, cfg, "xau", xau_arg)
    xag_path = resolve_symbol_input(root, cfg, "xag", xag_arg)
    xau = load_mt5_h1(xau_path, cfg, "XAUUSD")
    xag = load_mt5_h1(xag_path, cfg, "XAGUSD")
    sync = synchronize_h1(xau, xag, cfg)
    daily = build_common_daily(sync)

    ref_start = pd.Timestamp(cfg["selection"]["reference_start_utc"])
    ref_end = pd.Timestamp(cfg["selection"]["reference_end_utc"])
    diag_end = pd.Timestamp(cfg["selection"]["diagnostic_end_utc"])
    calibration_daily = daily[(daily["date"] >= ref_start) & (daily["date"] < ref_end)].copy().reset_index(drop=True)
    curve, cal_summary = run_clustered_regime_calibration(calibration_daily, cfg)
    curve.to_csv(outdir / "clustered_regime_calibration_curve.csv", index=False)
    write_json(outdir / "clustered_regime_calibration_summary.json", cal_summary)

    summary: dict[str, Any] = {
        "program": PROGRAM,
        "generated_utc": utc_now(),
        "paper_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
        "parameter_scan": False,
        "portfolio_scan": False,
        "archived_previous_report": archived,
        "xau_path": str(xau_path),
        "xag_path": str(xag_path),
        "xau_sha256": sha256_file(xau_path),
        "xag_sha256": sha256_file(xag_path),
        "xau_rows": int(len(xau)),
        "xag_rows": int(len(xag)),
        "synchronized_h1_rows": int(len(sync)),
        "daily_rows": int(len(daily)),
        "reference_start_utc": str(ref_start),
        "reference_end_utc": str(ref_end),
        "diagnostic_end_utc": str(diag_end),
        "strategy_contract": cfg["strategy"],
        "clustered_regime_calibration": cal_summary,
        "diagnostic_2025_plus_evaluated": False,
        "scope_contract": "Gold-centered precious-metals relative-value. Multi-asset portfolio expansion is allowed as a future managerial choice, not an automatic fallback.",
    }

    if not bool(cal_summary["pass"]):
        summary["decision"] = REGIME_FAIL
        summary["pass"] = False
        summary["reference_rv_evaluated"] = False
        write_json(outdir / "precious_metals_final_rv_summary.json", summary)
        (outdir / "precious_metals_final_rv_decision.md").write_text(
            f"# Decision\n\n`{REGIME_FAIL}`\n\nGold-Silver RV was not evaluated because the clustered observable-regime calibration failed.\n",
            encoding="utf-8",
        )
        write_json(outdir / "RESULTS_MANIFEST.json", output_manifest(outdir, {"RESULTS_MANIFEST.json"}))
        return summary

    ref_trades = simulate_pair_trades(daily, cfg, ref_start, ref_end)
    ref_trades.to_csv(outdir / "reference_gold_silver_rv_trades.csv", index=False)
    folds = fold_metrics(ref_trades, cfg)
    folds.to_csv(outdir / "reference_fold_metrics.csv", index=False)
    years = year_metrics(ref_trades)
    years.to_csv(outdir / "reference_year_metrics.csv", index=False)
    ref_eval = evaluate_reference(ref_trades, cfg)
    control = random_side_control(ref_trades, cfg)
    write_json(outdir / "reference_random_side_control.json", control)

    summary["reference_rv_evaluated"] = True
    summary["reference_metrics"] = ref_eval.metrics
    summary["reference_gates"] = ref_eval.gates
    summary["reference_pass"] = ref_eval.passed
    summary["reference_trade_count"] = int(len(ref_trades))
    summary["reference_first_entry"] = str(ref_trades["entry_date"].min()) if len(ref_trades) else None
    summary["reference_last_exit"] = str(ref_trades["exit_date"].max()) if len(ref_trades) else None

    if not ref_eval.passed:
        summary["decision"] = REF_FAIL
        summary["pass"] = False
        summary["diagnostic_2025_plus_evaluated"] = False
    else:
        diag_trades = simulate_pair_trades(daily, cfg, ref_end, diag_end)
        diag_trades.to_csv(outdir / "diagnostic_2025_plus_gold_silver_rv_trades.csv", index=False)
        diag_eval = evaluate_diagnostic(diag_trades, cfg)
        summary["diagnostic_2025_plus_evaluated"] = True
        summary["diagnostic_metrics"] = diag_eval.metrics
        summary["diagnostic_gates"] = diag_eval.gates
        summary["diagnostic_pass"] = diag_eval.passed
        summary["decision"] = REF_PASS_DIAG_PASS if diag_eval.passed else REF_PASS_DIAG_FAIL
        summary["pass"] = bool(diag_eval.passed)

    write_json(outdir / "precious_metals_final_rv_summary.json", summary)
    decision_lines = [
        "# Precious Metals Final RV Decision",
        "",
        f"**Decision:** `{summary['decision']}`",
        "",
        f"- Clustered regime calibration: `{cal_summary['decision']}`",
        f"- Reference trades: {summary.get('reference_trade_count', 0)}",
        f"- Reference pass: {summary.get('reference_pass', False)}",
        f"- 2025+ diagnostic evaluated: {summary.get('diagnostic_2025_plus_evaluated', False)}",
        "- Paper/demo/live orders: forbidden.",
        "- No parameter grid, no breakpoint hindsight, no post-failure rescue.",
        "",
        "A failure closes this exact Gold-Silver RV formulation. It does not automatically authorize a futures/options/portfolio scan.",
    ]
    (outdir / "precious_metals_final_rv_decision.md").write_text("\n".join(decision_lines) + "\n", encoding="utf-8")
    write_json(outdir / "RESULTS_MANIFEST.json", output_manifest(outdir, {"RESULTS_MANIFEST.json"}))
    return summary


def collect(root: Path, config_path: Path) -> Path:
    cfg = read_json(config_path)
    outdir = root / cfg["outputs"]["report_dir"]
    summary_path = outdir / "precious_metals_final_rv_summary.json"
    manifest_path = outdir / "RESULTS_MANIFEST.json"
    if not summary_path.is_file() or not manifest_path.is_file():
        raise CampaignError("run outputs are incomplete; summary/manifest missing")
    downloads = Path(cfg["outputs"]["downloads_dir"]).expanduser()
    downloads.mkdir(parents=True, exist_ok=True)
    target = downloads / cfg["outputs"]["results_zip"]
    if target.exists():
        target.unlink()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(outdir.rglob("*")):
            if p.is_file():
                z.write(p, arcname=p.relative_to(outdir))
    return target


def failure_record(root: Path, config_path: Path, stage: str, exc: Exception) -> None:
    try:
        cfg = read_json(config_path)
        outdir = root / cfg["outputs"]["report_dir"]
        outdir.mkdir(parents=True, exist_ok=True)
        write_json(outdir / "precious_metals_final_rv_failure.json", {
            "program": PROGRAM,
            "generated_utc": utc_now(),
            "decision": FAIL_CLOSED,
            "pass": False,
            "paper_order_allowed": False,
            "demo_order_allowed": False,
            "live_order_allowed": False,
            "stage": stage,
            "error_type": type(exc).__name__,
            "error": str(exc),
        })
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=PROGRAM)
    parser.add_argument("command", choices=["preflight", "run", "collect"])
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", default="configs/precious_metals_final_rv.json")
    parser.add_argument("--xau-h1", default=None)
    parser.add_argument("--xag-h1", default=None)
    args = parser.parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    config_path = Path(args.config).expanduser()
    if not config_path.is_absolute():
        config_path = root / config_path
    try:
        if args.command == "preflight":
            payload = preflight(root, config_path, args.xau_h1, args.xag_h1)
            print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
            return 0
        if args.command == "run":
            payload = run_campaign(root, config_path, args.xau_h1, args.xag_h1)
            print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
            return 0 if payload.get("decision") != FAIL_CLOSED else 2
        target = collect(root, config_path)
        print(f"OUTPUT={target}")
        print(f"ZIP_SIZE_BYTES={target.stat().st_size}")
        print(f"ZIP_SHA256={sha256_file(target)}")
        return 0
    except Exception as exc:
        failure_record(root, config_path, args.command, exc)
        print(json.dumps({
            "program": PROGRAM,
            "decision": FAIL_CLOSED,
            "pass": False,
            "stage": args.command,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }, indent=2, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
