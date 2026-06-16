#!/usr/bin/env python3
"""
Stage27C — DB-first H1 ATR gate validation.

Purpose
-------
Stage27B found h1_atr_drop_low30 as the strongest gate candidate around the
Stage23/25 canonical lineage. Stage27C validates that single gate independently,
with explicit anti-leakage handling for H1 ATR: the H1 bar used at entry must be
fully completed before the entry timestamp. For left-labeled H1 bars, this means
bar_start + 1 hour <= entry_time.

Hard rules
----------
- Research/shadow validation only.
- No EA, paper, live, or order authorization.
- Candles/regime features are DB-first from SQLite through the validated Stage25C loader.
- AMarkets CSV market fallback is intentionally disabled.
- Prior trade CSV is a research artifact, not market-data fallback.
- Stage18A, Stage23D, and Stage25D are not modified.
"""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

try:
    from app.stage25c_deduped_filter_validation import load_bars_from_db as load_bars_from_db_stage25c
except Exception:  # reported clearly at runtime
    load_bars_from_db_stage25c = None

STAGE = "stage27c_db_first_h1_atr_gate_validation"
REPORT_DIR = Path("data/reports") / STAGE
DEFAULT_DB_PATH = Path(os.environ.get("STAGE27C_DB_PATH", "data/local/xauusd_local_store.sqlite"))
ROUNDTRIP_COST_X1 = float(os.environ.get("STAGE27C_ROUNDTRIP_COST_X1", "0.35"))
MIN_EVENTS = int(os.environ.get("STAGE27C_MIN_EVENTS", "35"))
MIN_CALIBRATION_DAYS = int(os.environ.get("STAGE27C_MIN_CALIBRATION_DAYS", "250"))
ATR_PERIOD = int(os.environ.get("STAGE27C_H1_ATR_PERIOD", "20"))
BOOT_N = int(os.environ.get("STAGE27C_BOOT_N", "220"))
RNG_SEED = int(os.environ.get("STAGE27C_RNG_SEED", "27003"))
CANONICAL_CANDIDATE = os.environ.get("STAGE27C_CANONICAL_CANDIDATE", "S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65")
TRADE_ARTIFACT = Path(os.environ.get("STAGE27C_TRADE_ARTIFACT", "data/reports/stage25c_deduped_filter_validation/stage25c_enriched_canonical_trades.csv"))


class Stage27CError(RuntimeError):
    pass


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


def markdown_table(df: pd.DataFrame, cols: Sequence[str], n: int = 40) -> str:
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


def bootstrap_pf_p05(values: Sequence[float], n: int = BOOT_N, seed: int = RNG_SEED) -> float:
    arr = np.asarray([float(v) for v in values if pd.notna(v)], dtype=float)
    if arr.size < 25:
        return 0.0
    rng = np.random.default_rng(seed)
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
        if c not in out.columns:
            raise Stage27CError(f"Trade rows missing {c} column.")
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


def resample_ohlc(df: pd.DataFrame, rule: str, label: str = "left") -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close"])
    x = df.copy()
    x["timestamp"] = pd.to_datetime(x["timestamp"], utc=True, errors="coerce")
    for c in ["open", "high", "low", "close"]:
        x[c] = pd.to_numeric(x[c], errors="coerce")
    x = x.dropna(subset=["timestamp", "open", "high", "low", "close"]).sort_values("timestamp")
    if x.empty:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close"])
    out = x.set_index("timestamp").resample(rule, label=label, closed="left").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last")
    )
    return out.dropna().reset_index()


def normalize_bars(m1: pd.DataFrame, h1: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    m1x = m1.copy()
    if "timestamp" not in m1x.columns:
        raise Stage27CError("Stage25C DB loader returned M1 bars without timestamp column.")
    m1x["timestamp"] = pd.to_datetime(m1x["timestamp"], utc=True, errors="coerce")
    for c in ["open", "high", "low", "close"]:
        if c not in m1x.columns:
            raise Stage27CError(f"Stage25C DB loader returned M1 bars without {c} column.")
        m1x[c] = pd.to_numeric(m1x[c], errors="coerce")
    m1x = m1x.dropna(subset=["timestamp", "open", "high", "low", "close"]).sort_values("timestamp").reset_index(drop=True)
    if m1x.empty:
        raise Stage27CError("No M1 OHLC candles found after Stage25C DB loader. CSV fallback is intentionally disabled.")

    h1x = h1.copy() if h1 is not None and not h1.empty else pd.DataFrame()
    if h1x.empty:
        h1x = resample_ohlc(m1x, "1h", label="left")
    if "timestamp" not in h1x.columns:
        raise Stage27CError("H1 bars missing timestamp column after DB loader/resample.")
    h1x["timestamp"] = pd.to_datetime(h1x["timestamp"], utc=True, errors="coerce")
    for c in ["open", "high", "low", "close"]:
        if c not in h1x.columns:
            raise Stage27CError(f"H1 bars missing {c} column after DB loader/resample.")
        h1x[c] = pd.to_numeric(h1x[c], errors="coerce")
    h1x = h1x.dropna(subset=["timestamp", "open", "high", "low", "close"]).sort_values("timestamp").reset_index(drop=True)
    if h1x.empty:
        raise Stage27CError("No H1 OHLC candles found after DB loader/resample. CSV fallback is intentionally disabled.")

    meta = {
        "m1_rows_stage27c": int(len(m1x)),
        "m1_span_stage27c": f"{m1x['timestamp'].min()} → {m1x['timestamp'].max()}",
        "h1_rows_stage27c": int(len(h1x)),
        "h1_span_stage27c": f"{h1x['timestamp'].min()} → {h1x['timestamp'].max()}",
    }
    return m1x, h1x, meta


def add_h1_atr_features(h1: pd.DataFrame) -> pd.DataFrame:
    out = h1.copy().sort_values("timestamp").reset_index(drop=True)
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    for c in ["open", "high", "low", "close"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(subset=["timestamp", "open", "high", "low", "close"]).reset_index(drop=True)
    prev_close = out["close"].shift(1)
    tr = pd.concat(
        [(out["high"] - out["low"]).abs(), (out["high"] - prev_close).abs(), (out["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    out["h1_atr"] = tr.rolling(ATR_PERIOD, min_periods=max(5, ATR_PERIOD // 2)).mean()
    calibration_window = MIN_CALIBRATION_DAYS * 24
    # Shift(1) keeps the threshold based only on H1 bars before the current H1 bar.
    for q in [0.20, 0.25, 0.30, 0.35, 0.40, 0.70]:
        out[f"h1_atr_q{int(q*100)}"] = out["h1_atr"].rolling(calibration_window, min_periods=MIN_CALIBRATION_DAYS).quantile(q).shift(1)
    out["bar_end"] = out["timestamp"] + pd.Timedelta(hours=1)
    return out


def first_present(df: pd.DataFrame, names: Sequence[str]) -> Optional[str]:
    for n in names:
        if n in df.columns:
            return n
    return None


def load_trade_artifact() -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    manifest = pd.DataFrame([{"path": str(TRADE_ARTIFACT), "exists": TRADE_ARTIFACT.exists(), "rows": 0, "status": "missing"}])
    if not TRADE_ARTIFACT.exists():
        raise Stage27CError(f"Trade artifact not found: {TRADE_ARTIFACT}")
    raw = pd.read_csv(TRADE_ARTIFACT)
    manifest.loc[0, "rows"] = int(len(raw))
    manifest.loc[0, "status"] = "loaded"
    if raw.empty:
        raise Stage27CError(f"Trade artifact has no rows: {TRADE_ARTIFACT}")

    out = raw.copy()
    time_col = first_present(out, ["timestamp", "entry_time", "entry_ts", "time", "date_time"])
    if time_col is None:
        raise Stage27CError("Trade artifact has no timestamp/entry_time column.")
    out["timestamp"] = pd.to_datetime(out[time_col], utc=True, errors="coerce")
    out = out.dropna(subset=["timestamp"])
    if out.empty:
        raise Stage27CError("Trade artifact timestamps could not be parsed.")

    cand_col = first_present(out, ["candidate", "name", "variant"])
    rows_before_candidate = int(len(out))
    if cand_col is not None and CANONICAL_CANDIDATE:
        mask = out[cand_col].astype(str).str.contains(CANONICAL_CANDIDATE, regex=False, na=False)
        if mask.any():
            out = out[mask].copy()
    rows_after_candidate = int(len(out))

    dir_col = first_present(out, ["direction", "direction_label", "side", "dir", "dir_mult", "direction_num"])
    if dir_col is None:
        raise Stage27CError("Trade artifact has no direction/side column.")
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
            raise Stage27CError(f"Trade artifact has neither {col} nor gross column.")
    out = out.dropna(subset=["net_x1", "net_x4", "net_x6"])
    if out.empty:
        raise Stage27CError("Trade artifact has no valid net_x1/net_x4/net_x6 rows after normalization.")

    price_col = first_present(out, ["entry_price", "price"])
    out["entry_price_norm"] = pd.to_numeric(out[price_col], errors="coerce") if price_col else np.nan
    out["year"] = out["timestamp"].dt.year
    out["date"] = out["timestamp"].dt.floor("D")
    out["entry_hour"] = out["timestamp"].dt.hour
    out["dow"] = out["timestamp"].dt.dayofweek
    rows_before_dedup = int(len(out))
    out = out.drop_duplicates(subset=["timestamp", "direction_num", "entry_price_norm"]).reset_index(drop=True)

    meta = {
        "time_column_used": time_col,
        "direction_column_used": dir_col,
        "candidate_column_used": cand_col or "",
        "rows_before_candidate_filter": rows_before_candidate,
        "rows_after_candidate_filter": rows_after_candidate,
        "rows_before_event_dedup": rows_before_dedup,
        "rows_after_event_dedup": int(len(out)),
    }
    return out, manifest, meta


def h1_lookup_arrays(h1f: pd.DataFrame) -> Dict[str, Any]:
    h = h1f.copy().sort_values("timestamp").reset_index(drop=True)
    # Store bar_end as UTC int64 nanoseconds to avoid np.datetime64 timezone warnings.
    end_ns = pd.to_datetime(h["bar_end"], utc=True).astype("int64").to_numpy()
    start_vals = pd.to_datetime(h["timestamp"], utc=True).to_numpy()
    return {
        "bar_end_ns": end_ns,
        "bar_start": start_vals,
        "h1_atr": pd.to_numeric(h["h1_atr"], errors="coerce").to_numpy(dtype=float),
        "q20": pd.to_numeric(h["h1_atr_q20"], errors="coerce").to_numpy(dtype=float),
        "q25": pd.to_numeric(h["h1_atr_q25"], errors="coerce").to_numpy(dtype=float),
        "q30": pd.to_numeric(h["h1_atr_q30"], errors="coerce").to_numpy(dtype=float),
        "q35": pd.to_numeric(h["h1_atr_q35"], errors="coerce").to_numpy(dtype=float),
        "q40": pd.to_numeric(h["h1_atr_q40"], errors="coerce").to_numpy(dtype=float),
        "q70": pd.to_numeric(h["h1_atr_q70"], errors="coerce").to_numpy(dtype=float),
    }


def enrich_with_completed_h1_atr(trades: pd.DataFrame, h1f: pd.DataFrame) -> pd.DataFrame:
    out = trades.copy()
    arr = h1_lookup_arrays(h1f)
    entry_ns = pd.to_datetime(out["timestamp"], utc=True).astype("int64").to_numpy()
    # Strict anti-leakage: use the latest H1 bar whose end time is <= entry time.
    idxs = np.searchsorted(arr["bar_end_ns"], entry_ns, side="right") - 1
    valid = idxs >= 0

    for col in ["h1_atr", "q20", "q25", "q30", "q35", "q40", "q70"]:
        vals = np.full(len(out), np.nan, dtype=float)
        vals[valid] = arr[col][idxs[valid]]
        out[f"completed_{col}"] = vals

    starts = np.full(len(out), np.datetime64("NaT"), dtype="datetime64[ns]")
    starts[valid] = arr["bar_start"][idxs[valid]]
    out["completed_h1_bar_start"] = pd.to_datetime(starts, utc=True, errors="coerce")
    out["completed_h1_bar_end"] = out["completed_h1_bar_start"] + pd.Timedelta(hours=1)
    out["completed_h1_is_strict"] = out["completed_h1_bar_end"] <= out["timestamp"]
    out["completed_h1_age_minutes"] = (out["timestamp"] - out["completed_h1_bar_end"]).dt.total_seconds() / 60.0

    # Loose diagnostic to compare with Stage27B-like <= bar_start lookup.
    h_start_ns = pd.to_datetime(h1f["timestamp"], utc=True).astype("int64").to_numpy()
    loose_idxs = np.searchsorted(h_start_ns, entry_ns, side="right") - 1
    loose_valid = loose_idxs >= 0
    loose_atr = np.full(len(out), np.nan, dtype=float)
    loose_q30 = np.full(len(out), np.nan, dtype=float)
    h1_atr_arr = pd.to_numeric(h1f["h1_atr"], errors="coerce").to_numpy(dtype=float)
    q30_arr = pd.to_numeric(h1f["h1_atr_q30"], errors="coerce").to_numpy(dtype=float)
    loose_atr[loose_valid] = h1_atr_arr[loose_idxs[loose_valid]]
    loose_q30[loose_valid] = q30_arr[loose_idxs[loose_valid]]
    out["loose_h1_atr_at_entry"] = loose_atr
    out["loose_h1_atr_q30_at_entry"] = loose_q30
    out["gate_loose_h1_atr_drop_low30"] = out["loose_h1_atr_at_entry"] > out["loose_h1_atr_q30_at_entry"]
    return out


def evaluate_gate(enriched: pd.DataFrame, gate_name: str, q_col: str) -> Dict[str, Any]:
    base_m = metrics(enriched)
    mask = pd.to_numeric(enriched["completed_h1_atr"], errors="coerce") > pd.to_numeric(enriched[q_col], errors="coerce")
    kept = enriched[mask.fillna(False)].copy()
    m = metrics(kept)
    retained_ratio = float(len(kept) / len(enriched)) if len(enriched) else 0.0
    decision = "STAGE27C_REJECT"
    if m["events"] >= MIN_EVENTS and retained_ratio >= 0.25 and m["total_x4"] > 0:
        if m["pf_x4"] >= 1.30 and m["pf_x6"] >= 1.05 and m["boot_pf_p05_x4"] >= 1.05 and m["pf_x4"] > base_m["pf_x4"] + 0.35:
            decision = "STAGE27C_GATE_VALIDATED_REVIEW_ONLY"
        elif m["pf_x4"] > base_m["pf_x4"] + 0.20 and m["pf_x4"] >= 1.05:
            decision = "STAGE27C_WATCHLIST_ONLY"
    return {
        "decision": decision,
        "gate_name": gate_name,
        "gate_rule": f"completed_h1_atr > {q_col}",
        "retained_events": int(len(kept)),
        "retained_ratio": retained_ratio,
        **m,
        "base_pf_x4": base_m["pf_x4"],
        "base_pf_x6": base_m["pf_x6"],
        "base_total_x4": base_m["total_x4"],
        "improvement_pf_x4": float(m["pf_x4"] - base_m["pf_x4"]),
        "improvement_pf_x6": float(m["pf_x6"] - base_m["pf_x6"]),
        "improvement_total_x4": float(m["total_x4"] - base_m["total_x4"]),
    }


def split_diagnostics(df: pd.DataFrame, gate_name: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    mask = (pd.to_numeric(df["completed_h1_atr"], errors="coerce") > pd.to_numeric(df["completed_q30"], errors="coerce")).fillna(False)
    kept = df[mask].copy()
    rows: List[Dict[str, Any]] = []
    for split_name, cols in [("year", ["year"]), ("direction", ["direction_num"]), ("entry_hour", ["entry_hour"]), ("dow", ["dow"]), ("year_direction", ["year", "direction_num"]), ("year_dow", ["year", "dow"] )]:
        for key, g in kept.groupby(cols):
            m = metrics(g)
            key_text = "/".join(str(x) for x in key) if isinstance(key, tuple) else str(key)
            rows.append({"gate_name": gate_name, "split": split_name, "bucket": key_text, **m})
    return pd.DataFrame(rows)


def leakage_diagnostics(enriched: pd.DataFrame) -> Dict[str, Any]:
    strict_gate = (pd.to_numeric(enriched["completed_h1_atr"], errors="coerce") > pd.to_numeric(enriched["completed_q30"], errors="coerce")).fillna(False)
    loose_gate = enriched["gate_loose_h1_atr_drop_low30"].fillna(False).astype(bool)
    mismatch = strict_gate != loose_gate
    incomplete_used = ~enriched["completed_h1_is_strict"].fillna(False).astype(bool)
    return {
        "strict_completed_h1_rows_missing": int(enriched["completed_h1_atr"].isna().sum()),
        "strict_completed_h1_not_complete_count": int(incomplete_used.sum()),
        "strict_vs_loose_gate_mismatch_count": int(mismatch.sum()),
        "strict_kept_events_q30": int(strict_gate.sum()),
        "loose_kept_events_q30": int(loose_gate.sum()),
        "min_completed_h1_age_minutes": float(enriched["completed_h1_age_minutes"].min()) if enriched["completed_h1_age_minutes"].notna().any() else None,
        "median_completed_h1_age_minutes": float(enriched["completed_h1_age_minutes"].median()) if enriched["completed_h1_age_minutes"].notna().any() else None,
        "max_completed_h1_age_minutes": float(enriched["completed_h1_age_minutes"].max()) if enriched["completed_h1_age_minutes"].notna().any() else None,
    }


def write_error_report(exc: Exception) -> None:
    ensure_report_dir()
    payload = {"decision": "STAGE27C_ERROR_DIAGNOSTIC_ONLY", "error": f"{type(exc).__name__}: {exc}"}
    (REPORT_DIR / f"{STAGE}.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    md = [
        "# Stage27C DB-First H1 ATR Gate Validation",
        "",
        "## Decision",
        "",
        "```text",
        "STAGE27C_ERROR_DIAGNOSTIC_ONLY",
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
        raise Stage27CError("Could not import Stage25C DB loader. Apply Stage25C patch first; CSV fallback is intentionally disabled.")

    m1_raw, h1_raw, db_meta, schema_diag = load_bars_from_db_stage25c(DEFAULT_DB_PATH)
    m1, h1, norm_meta = normalize_bars(m1_raw, h1_raw)
    h1f = add_h1_atr_features(h1)
    trades, manifest, trade_meta = load_trade_artifact()
    enriched = enrich_with_completed_h1_atr(trades, h1f)
    base_m = metrics(enriched)

    gate_rows = []
    for q in [20, 25, 30, 35, 40]:
        gate_rows.append(evaluate_gate(enriched, f"h1_atr_drop_low{q}_strict_completed", f"completed_q{q}"))
    gate_df = pd.DataFrame(gate_rows).sort_values(["decision", "pf_x4", "pf_x6", "total_x4"], ascending=[True, False, False, False])

    primary = gate_df[gate_df["gate_name"] == "h1_atr_drop_low30_strict_completed"].iloc[0].to_dict()
    validated_count = int(gate_df["decision"].str.contains("VALIDATED", na=False).sum())
    watch_count = int(gate_df["decision"].str.contains("WATCHLIST", na=False).sum())
    decision = "STAGE27C_NO_GATE_VALIDATION_KEEP_REVIEW_OPEN"
    if str(primary.get("decision")) == "STAGE27C_GATE_VALIDATED_REVIEW_ONLY":
        decision = "STAGE27C_H1_ATR_GATE_VALIDATED_REVIEW_ONLY"
    elif validated_count > 0:
        decision = "STAGE27C_ALT_H1_ATR_GATE_VALIDATED_REVIEW_ONLY"
    elif watch_count > 0:
        decision = "STAGE27C_WATCHLIST_ONLY_KEEP_REVIEW_OPEN"

    splits = split_diagnostics(enriched, "h1_atr_drop_low30_strict_completed")
    leak = leakage_diagnostics(enriched)

    manifest.to_csv(REPORT_DIR / "stage27c_artifact_manifest.csv", index=False)
    enriched.to_csv(REPORT_DIR / "stage27c_enriched_h1_atr_trades.csv", index=False)
    gate_df.to_csv(REPORT_DIR / "stage27c_gate_validation.csv", index=False)
    splits.to_csv(REPORT_DIR / "stage27c_h1_atr_gate_splits.csv", index=False)
    try:
        schema_diag.to_csv(REPORT_DIR / "stage27c_db_schema_diagnostic.csv", index=False)
    except Exception:
        pd.DataFrame().to_csv(REPORT_DIR / "stage27c_db_schema_diagnostic.csv", index=False)

    payload = {
        "decision": decision,
        "db_meta": db_meta,
        "norm_meta": norm_meta,
        "trade_meta": trade_meta,
        "base_metrics": base_m,
        "primary_gate": primary,
        "leakage_diagnostics": leak,
        "counts": {
            "gate_variants_tested": int(len(gate_df)),
            "validated_count": validated_count,
            "watchlist_only_count": watch_count,
            "runtime_seconds": round(time.time() - start, 2),
        },
    }
    (REPORT_DIR / f"{STAGE}.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    md: List[str] = []
    md += [
        "# Stage27C DB-First H1 ATR Gate Validation",
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
        "- Research/shadow validation only.",
        "- Stage18A v2 remains the active operational forward-shadow runner.",
        "- Stage23D and Stage25D remain separate DB-first trackers.",
        "- No EA change, no automatic trading, no paper/live/order authorization.",
        "- Candles/regime features are DB-first from SQLite via the validated Stage25C loader; AMarkets CSV market fallback is disabled.",
        "- Prior trade CSV is used only as a research artifact, not as market-data fallback.",
        "- H1 ATR gate is anti-leakage validated: H1 bar_end must be <= entry_time.",
        "",
        "## DB source of truth",
        "",
        f"- db_path: `{DEFAULT_DB_PATH}`",
        f"- db_first: `True`",
        f"- csv_fallback_enabled: `False`",
        f"- m1_rows: `{norm_meta.get('m1_rows_stage27c')}` | span: `{norm_meta.get('m1_span_stage27c')}`",
        f"- h1_rows: `{norm_meta.get('h1_rows_stage27c')}` | span: `{norm_meta.get('h1_span_stage27c')}`",
        "",
        "## Trade artifact",
        "",
        f"- selected_artifact: `{TRADE_ARTIFACT}`",
        f"- requested_candidate: `{CANONICAL_CANDIDATE}`",
        f"- rows_after_event_dedup: `{trade_meta.get('rows_after_event_dedup')}`",
        "",
        markdown_table(manifest, ["path", "exists", "rows", "status"], 5),
        "",
        "## Base lineage metrics before strict H1 ATR gate",
        "",
        "```json",
        json.dumps(base_m, indent=2, default=str),
        "```",
        "",
        "## Anti-leakage diagnostics",
        "",
        "```json",
        json.dumps(leak, indent=2, default=str),
        "```",
        "",
        "## H1 ATR gate validation diagnostics",
        markdown_table(gate_df, [
            "decision", "gate_name", "retained_events", "retained_ratio", "pf_x1", "pf_x4", "pf_x6",
            "boot_pf_p05_x4", "median_x4", "total_x4", "win_rate_x4", "years_positive_x4", "year_count",
            "improvement_pf_x4", "improvement_pf_x6", "improvement_total_x4"
        ], 20),
        "",
        "## Primary gate split diagnostics",
        markdown_table(splits, ["gate_name", "split", "bucket", "events", "pf_x4", "pf_x6", "total_x4", "win_rate_x4"], 80),
        "",
        "## Interpretation",
        "",
        "- Stage27C validates Stage27B's strongest gate with strict completed-H1 anti-leakage logic.",
        "- The primary gate is `h1_atr_drop_low30_strict_completed`, which keeps trades only when completed H1 ATR is above its prior rolling q30 threshold.",
        "- A validated result remains research-only and requires a separate filtered forward-shadow tracker before any operational consideration.",
        "- If strict completed-H1 validation materially degrades Stage27B's gate, the gate should stay review-only and not be added to any tracker.",
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
        f"- `data/reports/{STAGE}/stage27c_artifact_manifest.csv`",
        f"- `data/reports/{STAGE}/stage27c_enriched_h1_atr_trades.csv`",
        f"- `data/reports/{STAGE}/stage27c_gate_validation.csv`",
        f"- `data/reports/{STAGE}/stage27c_h1_atr_gate_splits.csv`",
        f"- `data/reports/{STAGE}/stage27c_db_schema_diagnostic.csv`",
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
