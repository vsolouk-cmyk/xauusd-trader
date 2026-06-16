#!/usr/bin/env python3
"""
Stage27B — DB-first lineage gate discovery.

Purpose
-------
Stage27A showed that broad raw outcome surfaces do not produce a promotion candidate. Stage27B
therefore stops inventing fresh entries and studies forward-safe no-trade/regime gates around the
stronger Stage23B/23C/25 lineage. It uses previous trade CSVs as research artifacts only; market
candles and regime features are DB-first from SQLite via the validated Stage25C loader.

Hard rules
----------
- Research/shadow discovery only.
- No EA, paper, live, or order authorization.
- Candles/regime features are DB-first from SQLite through the Stage25C loader.
- AMarkets CSV market fallback is intentionally disabled.
- Prior trade CSVs are research artifacts, not market-data fallback.
- Stage18A, Stage23D, and Stage25D are not modified.
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

try:
    from app.stage25c_deduped_filter_validation import load_bars_from_db as load_bars_from_db_stage25c
except Exception:  # reported clearly at runtime
    load_bars_from_db_stage25c = None


STAGE = "stage27b_db_first_lineage_gate_discovery"
REPORT_DIR = Path("data/reports") / STAGE
DEFAULT_DB_PATH = Path(os.environ.get("STAGE27B_DB_PATH", "data/local/xauusd_local_store.sqlite"))
ROUNDTRIP_COST_X1 = float(os.environ.get("STAGE27B_ROUNDTRIP_COST_X1", "0.35"))
MIN_EVENTS = int(os.environ.get("STAGE27B_MIN_EVENTS", "35"))
MIN_CALIBRATION_DAYS = int(os.environ.get("STAGE27B_MIN_CALIBRATION_DAYS", "250"))
BOOT_N = int(os.environ.get("STAGE27B_BOOT_N", "160"))
RNG_SEED = int(os.environ.get("STAGE27B_RNG_SEED", "27002"))
CANONICAL_CANDIDATE = os.environ.get("STAGE27B_CANONICAL_CANDIDATE", "S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65")

TRADE_ARTIFACT_CANDIDATES = [
    Path(os.environ.get("STAGE27B_TRADE_ARTIFACT", "")) if os.environ.get("STAGE27B_TRADE_ARTIFACT") else None,
    Path("data/reports/stage25c_deduped_filter_validation/stage25c_enriched_canonical_trades.csv"),
    Path("data/reports/stage25c_deduped_filter_validation/stage25c_exact_canonical_trades.csv"),
    Path("data/reports/stage23c_promotion_candidate_validation/stage23c_exact_trades.csv"),
]


class Stage27BError(RuntimeError):
    pass


@dataclass(frozen=True)
class GateCandidate:
    name: str
    description: str
    kind: str
    apply: Callable[[pd.DataFrame], pd.Series]


def ensure_report_dir() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)


def fmt(v: Any) -> str:
    if isinstance(v, (float, np.floating)):
        f = float(v)
        if math.isinf(f):
            return "inf"
        if math.isnan(f):
            return ""
        return f"{f:.4f}".rstrip("0").rstrip(".")
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, default=str)
    return str(v)


def markdown_table(df: pd.DataFrame, cols: Sequence[str], n: int = 30) -> str:
    if df is None or df.empty:
        return "No rows."
    available = [c for c in cols if c in df.columns]
    if not available:
        return "No rows."
    show = df.loc[:, available].head(n).copy()
    lines = ["| " + " | ".join(available) + " |", "| " + " | ".join(["---"] * len(available)) + " |"]
    for _, row in show.iterrows():
        lines.append("| " + " | ".join(fmt(row[c]) for c in available) + " |")
    return "\n".join(lines)


def profit_factor(values: Iterable[float]) -> float:
    arr = np.asarray([float(v) for v in values if pd.notna(v)], dtype=float)
    if arr.size == 0:
        return 0.0
    gains = arr[arr > 0].sum()
    losses = arr[arr < 0].sum()
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return float(gains / abs(losses))


def bootstrap_pf_p05(values: Sequence[float], n: int = BOOT_N) -> float:
    arr = np.asarray([float(v) for v in values if pd.notna(v)], dtype=float)
    if arr.size < 25:
        return 0.0
    rng = np.random.default_rng(RNG_SEED)
    pfs: List[float] = []
    for _ in range(n):
        sample = rng.choice(arr, size=arr.size, replace=True)
        pfs.append(profit_factor(sample))
    finite = np.asarray([x for x in pfs if math.isfinite(x)], dtype=float)
    if finite.size == 0:
        return float("inf") if pfs and all(math.isinf(x) for x in pfs) else 0.0
    return float(np.percentile(finite, 5))


def metrics(df: pd.DataFrame) -> Dict[str, Any]:
    if df is None or df.empty:
        return {
            "events": 0,
            "pf_x1": 0.0,
            "pf_x4": 0.0,
            "pf_x6": 0.0,
            "boot_pf_p05_x4": 0.0,
            "median_x4": 0.0,
            "total_x4": 0.0,
            "win_rate_x4": 0.0,
            "years_positive_x4": 0,
            "year_count": 0,
        }
    out = df.copy()
    for c in ["net_x1", "net_x4", "net_x6"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(subset=["net_x1", "net_x4", "net_x6"])
    if out.empty:
        return metrics(pd.DataFrame())
    year_stats = out.groupby("year")["net_x4"].sum() if "year" in out.columns else pd.Series(dtype=float)
    return {
        "events": int(len(out)),
        "pf_x1": profit_factor(out["net_x1"]),
        "pf_x4": profit_factor(out["net_x4"]),
        "pf_x6": profit_factor(out["net_x6"]),
        "boot_pf_p05_x4": bootstrap_pf_p05(out["net_x4"].tolist()),
        "median_x4": float(out["net_x4"].median()),
        "total_x4": float(out["net_x4"].sum()),
        "win_rate_x4": float((out["net_x4"] > 0).mean()),
        "years_positive_x4": int((year_stats > 0).sum()) if not year_stats.empty else 0,
        "year_count": int(len(year_stats)) if not year_stats.empty else 0,
    }


def normalize_bars(m1: pd.DataFrame, h1: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    m1x = m1.copy()
    if "timestamp" not in m1x.columns:
        raise Stage27BError("Stage25C DB loader returned M1 bars without timestamp column.")
    m1x["timestamp"] = pd.to_datetime(m1x["timestamp"], utc=True, errors="coerce")
    for c in ["open", "high", "low", "close"]:
        if c not in m1x.columns:
            raise Stage27BError(f"Stage25C DB loader returned M1 bars without {c} column.")
        m1x[c] = pd.to_numeric(m1x[c], errors="coerce")
    m1x = m1x.dropna(subset=["timestamp", "open", "high", "low", "close"]).sort_values("timestamp").reset_index(drop=True)
    if m1x.empty:
        raise Stage27BError("No M1 OHLC candles found after Stage25C DB loader. CSV fallback is intentionally disabled.")

    h1x = h1.copy() if h1 is not None and not h1.empty else pd.DataFrame()
    if h1x.empty:
        h1x = resample_ohlc(m1x, "1h", label="left")
    h1x["timestamp"] = pd.to_datetime(h1x["timestamp"], utc=True, errors="coerce")
    for c in ["open", "high", "low", "close"]:
        h1x[c] = pd.to_numeric(h1x[c], errors="coerce")
    h1x = h1x.dropna(subset=["timestamp", "open", "high", "low", "close"]).sort_values("timestamp").reset_index(drop=True)
    m15x = resample_ohlc(m1x, "15min", label="right")

    meta = {
        "m1_rows_stage27b": int(len(m1x)),
        "m1_span_stage27b": f"{m1x['timestamp'].min()} → {m1x['timestamp'].max()}",
        "h1_rows_stage27b": int(len(h1x)),
        "h1_span_stage27b": f"{h1x['timestamp'].min()} → {h1x['timestamp'].max()}" if not h1x.empty else "",
        "m15_rows_stage27b": int(len(m15x)),
        "m15_span_stage27b": f"{m15x['timestamp'].min()} → {m15x['timestamp'].max()}" if not m15x.empty else "",
    }
    return m1x, h1x, m15x, meta


def resample_ohlc(df: pd.DataFrame, rule: str, label: str = "right") -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close"])
    x = df.copy()
    x["timestamp"] = pd.to_datetime(x["timestamp"], utc=True, errors="coerce")
    for c in ["open", "high", "low", "close"]:
        x[c] = pd.to_numeric(x[c], errors="coerce")
    x = x.dropna(subset=["timestamp", "open", "high", "low", "close"]).sort_values("timestamp")
    out = x.set_index("timestamp").resample(rule, label=label, closed=label).agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last")
    )
    return out.dropna().reset_index()


def add_atr(df: pd.DataFrame, period: int = 32) -> pd.DataFrame:
    out = df.copy().sort_values("timestamp").reset_index(drop=True)
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    for c in ["open", "high", "low", "close"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(subset=["timestamp", "open", "high", "low", "close"]).reset_index(drop=True)
    prev_close = out["close"].shift(1)
    tr = pd.concat(
        [(out["high"] - out["low"]).abs(), (out["high"] - prev_close).abs(), (out["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    out["atr"] = tr.rolling(period, min_periods=max(5, period // 3)).mean()
    out["date"] = out["timestamp"].dt.floor("D")
    out["hour"] = out["timestamp"].dt.hour
    out["minute"] = out["timestamp"].dt.minute
    return out


def prepare_regime_features(m15: pd.DataFrame, h1: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    m = add_atr(m15, 32)
    h = add_atr(h1, 20)
    h["sma20"] = h["close"].rolling(20, min_periods=10).mean()
    h["sma50"] = h["close"].rolling(50, min_periods=20).mean()
    h["h1_bias"] = np.where(h["sma20"] > h["sma50"], 1, np.where(h["sma20"] < h["sma50"], -1, 0))
    h["h1_atr_q70"] = h["atr"].rolling(MIN_CALIBRATION_DAYS * 24, min_periods=MIN_CALIBRATION_DAYS).quantile(0.70).shift(1)
    h["h1_atr_q30"] = h["atr"].rolling(MIN_CALIBRATION_DAYS * 24, min_periods=MIN_CALIBRATION_DAYS).quantile(0.30).shift(1)

    sessions: List[pd.DataFrame] = []
    for name, start_h, end_h in [("asia", 0, 7), ("london", 7, 13)]:
        s = m[(m["hour"] >= start_h) & (m["hour"] < end_h)].copy()
        if s.empty:
            continue
        agg = s.groupby("date").agg(
            **{
                f"{name}_open": ("open", "first"),
                f"{name}_high": ("high", "max"),
                f"{name}_low": ("low", "min"),
                f"{name}_close": ("close", "last"),
                f"{name}_atr": ("atr", "median"),
            }
        ).reset_index()
        agg[f"{name}_range"] = agg[f"{name}_high"] - agg[f"{name}_low"]
        agg[f"{name}_range_atr"] = agg[f"{name}_range"] / agg[f"{name}_atr"].replace(0, np.nan)
        agg[f"{name}_eff"] = (agg[f"{name}_close"] - agg[f"{name}_open"]).abs() / agg[f"{name}_range"].replace(0, np.nan)
        agg[f"{name}_dir"] = np.where(agg[f"{name}_close"] >= agg[f"{name}_open"], 1, -1)
        sessions.append(agg)

    daily = m.groupby("date").agg(
        day_open=("open", "first"),
        day_high=("high", "max"),
        day_low=("low", "min"),
        day_close=("close", "last"),
        day_atr=("atr", "median"),
    ).reset_index()
    daily["prior_high"] = daily["day_high"].shift(1)
    daily["prior_low"] = daily["day_low"].shift(1)
    daily["prior_range"] = daily["day_high"].shift(1) - daily["day_low"].shift(1)
    daily["prior_range_atr"] = daily["prior_range"] / daily["day_atr"].replace(0, np.nan)
    daily["dow"] = daily["date"].dt.dayofweek
    for s in sessions:
        daily = daily.merge(s, on="date", how="left")

    for field in ["london_range_atr", "london_eff", "asia_range_atr", "prior_range_atr"]:
        if field in daily.columns:
            for q in [0.2, 0.3, 0.4, 0.6, 0.7, 0.8]:
                daily[f"{field}_q{int(q*100)}"] = daily[field].rolling(MIN_CALIBRATION_DAYS, min_periods=MIN_CALIBRATION_DAYS).quantile(q).shift(1)
    return m, h, daily


def find_existing_artifact() -> Tuple[Optional[Path], pd.DataFrame]:
    manifest_rows: List[Dict[str, Any]] = []
    for p in TRADE_ARTIFACT_CANDIDATES:
        if p is None:
            continue
        row = {"path": str(p), "exists": p.exists(), "rows": 0, "status": "missing"}
        if not p.exists():
            manifest_rows.append(row)
            continue
        try:
            df = pd.read_csv(p)
            row.update({"rows": int(len(df)), "status": "loaded"})
            manifest_rows.append(row)
            return p, pd.DataFrame(manifest_rows), df
        except Exception as exc:
            row.update({"status": f"error:{type(exc).__name__}:{exc}"})
            manifest_rows.append(row)
    return None, pd.DataFrame(manifest_rows), pd.DataFrame()


def first_present(df: pd.DataFrame, names: Sequence[str]) -> Optional[str]:
    for n in names:
        if n in df.columns:
            return n
    return None


def normalize_trade_artifact(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    if df is None or df.empty:
        raise Stage27BError("No research trade artifact rows found. Run Stage25C or provide STAGE27B_TRADE_ARTIFACT.")
    out = df.copy()
    time_col = first_present(out, ["timestamp", "entry_time", "entry_ts", "time", "date_time"])
    if time_col is None:
        raise Stage27BError("Trade artifact has no timestamp/entry_time column.")
    out["timestamp"] = pd.to_datetime(out[time_col], utc=True, errors="coerce")
    out = out.dropna(subset=["timestamp"])
    if out.empty:
        raise Stage27BError("Trade artifact timestamps could not be parsed.")

    cand_col = first_present(out, ["candidate", "name", "variant"])
    rows_before_candidate = len(out)
    if cand_col is not None and CANONICAL_CANDIDATE:
        mask = out[cand_col].astype(str).str.contains(CANONICAL_CANDIDATE, regex=False, na=False)
        if mask.any():
            out = out[mask].copy()
    rows_after_candidate = len(out)

    dir_col = first_present(out, ["direction", "direction_label", "side", "dir", "dir_mult"])
    if dir_col is None:
        raise Stage27BError("Trade artifact has no direction/side column.")
    raw_dir = out[dir_col]
    if pd.api.types.is_numeric_dtype(raw_dir):
        out["direction_num"] = np.where(pd.to_numeric(raw_dir, errors="coerce") >= 0, 1, -1)
    else:
        s = raw_dir.astype(str).str.lower()
        out["direction_num"] = np.where(s.str.contains("short|-1|sell"), -1, 1)

    for mult in [1, 4, 6]:
        col = f"net_x{mult}"
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
        elif "gross" in out.columns:
            out[col] = pd.to_numeric(out["gross"], errors="coerce") - ROUNDTRIP_COST_X1 * mult
        else:
            raise Stage27BError(f"Trade artifact has neither {col} nor gross column.")
    out = out.dropna(subset=["net_x1", "net_x4", "net_x6"])
    if out.empty:
        raise Stage27BError("Trade artifact has no valid net_x1/net_x4/net_x6 rows after normalization.")

    price_col = first_present(out, ["entry_price", "price"])
    if price_col and price_col in out.columns:
        out["entry_price_norm"] = pd.to_numeric(out[price_col], errors="coerce")
    else:
        out["entry_price_norm"] = np.nan
    out["year"] = out["timestamp"].dt.year
    out["date"] = out["timestamp"].dt.floor("D")
    out["entry_hour"] = out["timestamp"].dt.hour
    dedup_cols = ["timestamp", "direction_num", "entry_price_norm"]
    rows_before_dedup = len(out)
    out = out.drop_duplicates(subset=dedup_cols).reset_index(drop=True)

    meta = {
        "time_column_used": time_col,
        "direction_column_used": dir_col,
        "candidate_column_used": cand_col or "",
        "rows_before_candidate_filter": int(rows_before_candidate),
        "rows_after_candidate_filter": int(rows_after_candidate),
        "rows_before_event_dedup": int(rows_before_dedup),
        "rows_after_event_dedup": int(len(out)),
    }
    return out, meta


def latest_h1_row(h1: pd.DataFrame, ts: pd.Timestamp) -> Optional[pd.Series]:
    rows = h1[h1["timestamp"] <= ts]
    if rows.empty:
        return None
    return rows.iloc[-1]


def enrich_trades(trades: pd.DataFrame, h1: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    out = trades.copy()
    out = out.merge(daily, on="date", how="left", suffixes=("", "_daily"))
    h_bias: List[int] = []
    h_atr: List[float] = []
    h_atr_q30: List[float] = []
    h_atr_q70: List[float] = []
    for ts in out["timestamp"]:
        row = latest_h1_row(h1, pd.Timestamp(ts))
        if row is None:
            h_bias.append(0)
            h_atr.append(np.nan)
            h_atr_q30.append(np.nan)
            h_atr_q70.append(np.nan)
        else:
            h_bias.append(int(row.get("h1_bias", 0)) if pd.notna(row.get("h1_bias", np.nan)) else 0)
            h_atr.append(float(row.get("atr", np.nan)))
            h_atr_q30.append(float(row.get("h1_atr_q30", np.nan)))
            h_atr_q70.append(float(row.get("h1_atr_q70", np.nan)))
    out["h1_bias_at_entry"] = h_bias
    out["h1_atr_at_entry"] = h_atr
    out["h1_atr_q30_at_entry"] = h_atr_q30
    out["h1_atr_q70_at_entry"] = h_atr_q70
    out["h1_aligned"] = (out["direction_num"] * out["h1_bias_at_entry"] > 0)
    out["london_aligned"] = (out["direction_num"] * pd.to_numeric(out.get("london_dir", 0), errors="coerce") > 0)
    out["asia_aligned"] = (out["direction_num"] * pd.to_numeric(out.get("asia_dir", 0), errors="coerce") > 0)
    return out


def gt_col(col: str, qcol: str) -> Callable[[pd.DataFrame], pd.Series]:
    def _f(df: pd.DataFrame) -> pd.Series:
        return pd.to_numeric(df.get(col), errors="coerce") > pd.to_numeric(df.get(qcol), errors="coerce")
    return _f


def lt_col(col: str, qcol: str) -> Callable[[pd.DataFrame], pd.Series]:
    def _f(df: pd.DataFrame) -> pd.Series:
        return pd.to_numeric(df.get(col), errors="coerce") < pd.to_numeric(df.get(qcol), errors="coerce")
    return _f


def and_gate(*funcs: Callable[[pd.DataFrame], pd.Series]) -> Callable[[pd.DataFrame], pd.Series]:
    def _f(df: pd.DataFrame) -> pd.Series:
        if df.empty:
            return pd.Series(dtype=bool)
        mask = pd.Series(True, index=df.index)
        for fn in funcs:
            mask = mask & fn(df).fillna(False)
        return mask
    return _f


def generate_gates() -> List[GateCandidate]:
    gates: List[GateCandidate] = []
    # Forward-safe regime gates. All thresholds are rolling/shifted from prior days.
    for q in [20, 30, 40]:
        gates.append(GateCandidate(f"london_range_drop_low{q}", f"Keep trades when London range is above prior rolling q{q}; drop low-vol London days.", "regime", gt_col("london_range_atr", f"london_range_atr_q{q}")))
        gates.append(GateCandidate(f"asia_range_drop_low{q}", f"Keep trades when Asia range is above prior rolling q{q}; drop low-vol Asia days.", "regime", gt_col("asia_range_atr", f"asia_range_atr_q{q}")))
        gates.append(GateCandidate(f"prior_range_drop_low{q}", f"Keep trades when prior-day range is above prior rolling q{q}; drop compressed prior days.", "regime", gt_col("prior_range_atr", f"prior_range_atr_q{q}")))
    for q in [70, 80]:
        gates.append(GateCandidate(f"london_range_drop_high{q}", f"Keep trades when London range is below prior rolling q{q}; drop overextended London days.", "regime", lt_col("london_range_atr", f"london_range_atr_q{q}")))
        gates.append(GateCandidate(f"asia_range_drop_high{q}", f"Keep trades when Asia range is below prior rolling q{q}; drop overextended Asia days.", "regime", lt_col("asia_range_atr", f"asia_range_atr_q{q}")))
    for q in [20, 30]:
        gates.append(GateCandidate(f"london_eff_drop_low{q}", f"Keep trades when London directional efficiency is above prior rolling q{q}.", "regime", gt_col("london_eff", f"london_eff_q{q}")))
    gates += [
        GateCandidate("keep_h1_aligned", "Keep trades aligned with H1 SMA20/SMA50 bias at entry.", "bias", lambda df: df["h1_aligned"]),
        GateCandidate("drop_h1_aligned", "Keep trades not aligned with H1 bias at entry.", "bias", lambda df: ~df["h1_aligned"]),
        GateCandidate("keep_london_aligned", "Keep trades aligned with pre-entry London direction.", "bias", lambda df: df["london_aligned"]),
        GateCandidate("drop_london_aligned", "Keep trades against pre-entry London direction.", "bias", lambda df: ~df["london_aligned"]),
        GateCandidate("keep_short_only", "Diagnostic direction-only gate; not a standalone market-regime filter.", "direction_diag", lambda df: df["direction_num"] < 0),
        GateCandidate("keep_long_only", "Diagnostic direction-only gate; not a standalone market-regime filter.", "direction_diag", lambda df: df["direction_num"] > 0),
        GateCandidate("drop_monday", "Drop Monday entries.", "calendar", lambda df: df["dow"] != 0),
        GateCandidate("drop_friday", "Drop Friday entries.", "calendar", lambda df: df["dow"] != 4),
        GateCandidate("h1_atr_drop_high70", "Drop high H1 ATR regimes using rolling q70 known at entry.", "volatility", lambda df: pd.to_numeric(df["h1_atr_at_entry"], errors="coerce") < pd.to_numeric(df["h1_atr_q70_at_entry"], errors="coerce")),
        GateCandidate("h1_atr_drop_low30", "Drop low H1 ATR regimes using rolling q30 known at entry.", "volatility", lambda df: pd.to_numeric(df["h1_atr_at_entry"], errors="coerce") > pd.to_numeric(df["h1_atr_q30_at_entry"], errors="coerce")),
    ]
    # Conservative two-gate combinations seeded from Stage25C/25D lineage.
    gates += [
        GateCandidate("london_range_drop_low30_and_h1_atr_drop_high70", "London low-range gate plus removal of high H1 volatility.", "combo", and_gate(gt_col("london_range_atr", "london_range_atr_q30"), lambda df: pd.to_numeric(df["h1_atr_at_entry"], errors="coerce") < pd.to_numeric(df["h1_atr_q70_at_entry"], errors="coerce"))),
        GateCandidate("london_range_drop_low30_and_london_aligned", "London low-range gate plus London-direction alignment.", "combo", and_gate(gt_col("london_range_atr", "london_range_atr_q30"), lambda df: df["london_aligned"])),
        GateCandidate("london_range_drop_low30_and_h1_aligned", "London low-range gate plus H1-bias alignment.", "combo", and_gate(gt_col("london_range_atr", "london_range_atr_q30"), lambda df: df["h1_aligned"])),
        GateCandidate("london_range_drop_low30_and_short_only", "Diagnostic: London low-range gate plus short-only direction filter.", "combo_direction_diag", and_gate(gt_col("london_range_atr", "london_range_atr_q30"), lambda df: df["direction_num"] < 0)),
    ]
    return gates


def evaluate_gate(base: pd.DataFrame, gate: GateCandidate, base_m: Dict[str, Any]) -> Tuple[Dict[str, Any], pd.DataFrame]:
    try:
        mask = gate.apply(base).fillna(False)
    except Exception as exc:
        row = {"decision": "STAGE27B_ERROR_GATE", "gate_name": gate.name, "gate_kind": gate.kind, "error": f"{type(exc).__name__}: {exc}", "events": 0}
        return row, pd.DataFrame()
    kept = base[mask].copy()
    m = metrics(kept)
    retained_ratio = float(len(kept) / len(base)) if len(base) else 0.0
    decision = "STAGE27B_REJECT"
    direction_diag = gate.kind in {"direction_diag", "combo_direction_diag"}
    if m["events"] >= MIN_EVENTS and retained_ratio >= 0.25 and m["total_x4"] > 0:
        if (not direction_diag and m["pf_x4"] >= 1.30 and m["pf_x6"] >= 1.05 and m["boot_pf_p05_x4"] >= 1.05 and m["pf_x4"] > base_m["pf_x4"] + 0.35):
            decision = "STAGE27B_GATE_CANDIDATE_REVIEW_ONLY"
        elif m["pf_x4"] > base_m["pf_x4"] + 0.20 and m["pf_x4"] >= 1.05:
            decision = "STAGE27B_WATCHLIST_ONLY"
    row = {
        "decision": decision,
        "gate_name": gate.name,
        "gate_kind": gate.kind,
        "description": gate.description,
        "retained_events": int(len(kept)),
        "retained_ratio": retained_ratio,
        **m,
        "improvement_pf_x4": float(m["pf_x4"] - base_m["pf_x4"]),
        "improvement_pf_x6": float(m["pf_x6"] - base_m["pf_x6"]),
        "improvement_total_x4": float(m["total_x4"] - base_m["total_x4"]),
    }
    kept["gate_name"] = gate.name
    kept["gate_kind"] = gate.kind
    return row, kept


def split_diagnostics(df: pd.DataFrame, gate_name: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    rows: List[Dict[str, Any]] = []
    for split_name, cols in [("year", ["year"]), ("direction", ["direction_num"]), ("entry_hour", ["entry_hour"]), ("year_direction", ["year", "direction_num"]), ("dow", ["dow"] )]:
        for key, g in df.groupby(cols):
            m = metrics(g)
            if isinstance(key, tuple):
                key_text = "/".join(str(x) for x in key)
            else:
                key_text = str(key)
            rows.append({"gate_name": gate_name, "split": split_name, "bucket": key_text, **m})
    return pd.DataFrame(rows)


def write_error_report(exc: Exception) -> None:
    ensure_report_dir()
    payload = {"decision": "STAGE27B_ERROR_DIAGNOSTIC_ONLY", "error": f"{type(exc).__name__}: {exc}"}
    (REPORT_DIR / f"{STAGE}.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    md = [
        "# Stage27B DB-First Lineage Gate Discovery",
        "",
        "## Decision",
        "",
        "```text",
        "STAGE27B_ERROR_DIAGNOSTIC_ONLY",
        "```",
        "",
        "## Error",
        "",
        "```text",
        f"{type(exc).__name__}: {exc}",
        "```",
        "",
        "- DB-first is enabled.",
        "- CSV market fallback is intentionally disabled.",
        "- Stage18A, Stage23D, and Stage25D remain unchanged.",
    ]
    (REPORT_DIR / f"{STAGE}.md").write_text("\n".join(md), encoding="utf-8")


def run() -> Dict[str, Any]:
    ensure_report_dir()
    start = time.time()
    if load_bars_from_db_stage25c is None:
        raise Stage27BError("Could not import Stage25C DB loader. Apply Stage25C patch first; CSV fallback is intentionally disabled.")

    m1_raw, h1_raw, db_meta, schema_diag = load_bars_from_db_stage25c(DEFAULT_DB_PATH)
    m1, h1, m15, norm_meta = normalize_bars(m1_raw, h1_raw)
    _, h1f, daily = prepare_regime_features(m15, h1)

    artifact_path, artifact_manifest, raw_trades = find_existing_artifact()
    trades, trade_meta = normalize_trade_artifact(raw_trades)
    enriched = enrich_trades(trades, h1f, daily)
    base_m = metrics(enriched)

    rows: List[Dict[str, Any]] = []
    kept_frames: List[pd.DataFrame] = []
    for gate in generate_gates():
        row, kept = evaluate_gate(enriched, gate, base_m)
        rows.append(row)
        if not kept.empty:
            kept_frames.append(kept)
    gates_df = pd.DataFrame(rows)
    if not gates_df.empty:
        gates_df["_rank_decision"] = np.select(
            [gates_df["decision"].str.contains("CANDIDATE"), gates_df["decision"].str.contains("WATCHLIST")],
            [0, 1],
            default=2,
        )
        gates_df = gates_df.sort_values(["_rank_decision", "pf_x4", "pf_x6", "total_x4"], ascending=[True, False, False, False]).drop(columns=["_rank_decision"])

    top_name = str(gates_df.iloc[0]["gate_name"]) if not gates_df.empty else ""
    top_kept = next((k for k in kept_frames if not k.empty and str(k.iloc[0].get("gate_name")) == top_name), pd.DataFrame())
    splits = split_diagnostics(top_kept, top_name)

    gate_candidate_count = int(gates_df["decision"].str.contains("CANDIDATE", na=False).sum()) if not gates_df.empty else 0
    watch_count = int(gates_df["decision"].str.contains("WATCHLIST", na=False).sum()) if not gates_df.empty else 0
    decision = "STAGE27B_NO_GATE_CANDIDATE_KEEP_DISCOVERY_OPEN"
    if gate_candidate_count > 0:
        decision = "STAGE27B_HAS_GATE_CANDIDATE_REVIEW_ONLY"
    elif watch_count > 0:
        decision = "STAGE27B_HAS_WATCHLIST_ONLY_KEEP_DISCOVERY_OPEN"

    artifact_manifest.to_csv(REPORT_DIR / "stage27b_artifact_manifest.csv", index=False)
    enriched.to_csv(REPORT_DIR / "stage27b_enriched_lineage_trades.csv", index=False)
    gates_df.to_csv(REPORT_DIR / "stage27b_gate_candidates.csv", index=False)
    splits.to_csv(REPORT_DIR / "stage27b_top_gate_splits.csv", index=False)
    try:
        schema_diag.to_csv(REPORT_DIR / "stage27b_db_schema_diagnostic.csv", index=False)
    except Exception:
        pd.DataFrame().to_csv(REPORT_DIR / "stage27b_db_schema_diagnostic.csv", index=False)

    payload = {
        "decision": decision,
        "db_meta": db_meta,
        "norm_meta": norm_meta,
        "artifact_path": str(artifact_path) if artifact_path else "",
        "trade_meta": trade_meta,
        "base_metrics": base_m,
        "counts": {
            "gate_candidates_tested": int(len(gates_df)),
            "gate_candidate_review_count": gate_candidate_count,
            "watchlist_only_count": watch_count,
            "runtime_seconds": round(time.time() - start, 2),
        },
    }
    (REPORT_DIR / f"{STAGE}.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    md: List[str] = []
    md += [
        "# Stage27B DB-First Lineage Gate Discovery",
        "",
        f"Generated UTC: `{pd.Timestamp.utcnow().isoformat()}`",
        "",
        "## Decision",
        "",
        "```text",
        decision,
        "```",
        "",
        "## Scope guardrails",
        "",
        "- Research/shadow gate discovery only.",
        "- Stage18A v2 remains the active operational forward-shadow runner.",
        "- Stage23D and Stage25D remain separate DB-first trackers.",
        "- No EA change, no automatic trading, no paper/live/order authorization.",
        "- Candles/regime features are DB-first from SQLite via the validated Stage25C loader; AMarkets CSV market fallback is disabled.",
        "- Prior trade CSVs are used only as research artifacts, not as market-data fallback.",
        "",
        "## DB source of truth",
        "",
        f"- db_path: `{DEFAULT_DB_PATH}`",
        f"- candle_table: `{db_meta.get('candle_table', 'unknown') if isinstance(db_meta, dict) else 'unknown'}`",
        "- db_first: `True`",
        "- csv_fallback_enabled: `False`",
        f"- m1_rows: `{norm_meta['m1_rows_stage27b']}` | span: `{norm_meta['m1_span_stage27b']}`",
        f"- h1_rows: `{norm_meta['h1_rows_stage27b']}` | span: `{norm_meta['h1_span_stage27b']}`",
        f"- m15_rows: `{norm_meta['m15_rows_stage27b']}` | span: `{norm_meta['m15_span_stage27b']}`",
        "",
        "## Trade artifact",
        "",
        f"- selected_artifact: `{artifact_path}`",
        f"- requested_candidate: `{CANONICAL_CANDIDATE}`",
        f"- rows_after_event_dedup: `{trade_meta.get('rows_after_event_dedup')}`",
        "",
        markdown_table(artifact_manifest, ["path", "exists", "rows", "status"], n=10),
        "",
        "## Base lineage metrics before new gates",
        "",
        "```json",
        json.dumps(base_m, indent=2, default=str),
        "```",
        "",
        "## Counts",
        "",
        f"- gate_candidates_tested: `{len(gates_df)}`",
        f"- gate_candidate_review_count: `{gate_candidate_count}`",
        f"- watchlist_only_count: `{watch_count}`",
        f"- runtime_seconds: `{round(time.time() - start, 2)}`",
        "",
        "## Top gate diagnostics",
        markdown_table(
            gates_df,
            [
                "decision",
                "gate_name",
                "gate_kind",
                "retained_events",
                "retained_ratio",
                "pf_x1",
                "pf_x4",
                "pf_x6",
                "boot_pf_p05_x4",
                "median_x4",
                "total_x4",
                "win_rate_x4",
                "years_positive_x4",
                "year_count",
                "improvement_pf_x4",
                "improvement_pf_x6",
            ],
            n=30,
        ),
        "",
        "## Top gate split diagnostics",
        markdown_table(splits, ["gate_name", "split", "bucket", "events", "pf_x4", "pf_x6", "total_x4", "win_rate_x4"], n=40),
        "",
        "## Interpretation",
        "",
        "- Stage27B does not invent a new entry rule; it evaluates forward-safe no-trade/regime gates around the stronger Stage23/25 lineage.",
        "- Direction-only gates are marked diagnostic and are not standalone market-regime filters.",
        "- A gate-candidate result remains research-only and requires a dedicated validation stage plus a separate forward-shadow tracker before any operational consideration.",
        "- If no gate candidate improves the canonical lineage, discovery should move toward broader data-quality/broker-source checks or higher-timeframe thesis changes rather than repeated micro-entry mutations.",
        "",
        "## Operational reminder",
        "",
        "```bash",
        "cd ~/Desktop/xauusd-trader",
        "python3 -m app.stage18a_unified_shadow_ops_cycle",
        "python3 -m app.stage23d_forward_shadow_candidate",
        "python3 -m app.stage25d_db_first_filtered_forward_shadow",
        "```",
        "",
        "## Output files",
        "",
        f"- `data/reports/{STAGE}/{STAGE}.json`",
        f"- `data/reports/{STAGE}/{STAGE}.md`",
        f"- `data/reports/{STAGE}/stage27b_artifact_manifest.csv`",
        f"- `data/reports/{STAGE}/stage27b_enriched_lineage_trades.csv`",
        f"- `data/reports/{STAGE}/stage27b_gate_candidates.csv`",
        f"- `data/reports/{STAGE}/stage27b_top_gate_splits.csv`",
        f"- `data/reports/{STAGE}/stage27b_db_schema_diagnostic.csv`",
    ]
    (REPORT_DIR / f"{STAGE}.md").write_text("\n".join(md), encoding="utf-8")
    return payload


def main() -> None:
    try:
        run()
    except Exception as exc:
        write_error_report(exc)
        raise


if __name__ == "__main__":
    main()
