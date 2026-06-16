#!/usr/bin/env python3
"""
Stage25C — DB-first de-duplicated regime filter validation.

Purpose
-------
Validate Stage25A/25B filter candidates on a single canonical Stage23B/C candidate,
instead of using the duplicated Stage23C aggregate artifact as independent evidence.

Hard rules
----------
- Research/shadow diagnostic only.
- No EA, paper, live, or order authorization.
- No CSV fallback for candle data. SQLite local store is the candle source of truth.
- The Stage23C trade artifact is used only as the historical candidate trade list.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

ROOT = Path.cwd()
REPORT_DIR = ROOT / "data" / "reports" / "stage25c_deduped_filter_validation"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_DB_PATH = ROOT / "data" / "local" / "xauusd_local_store.sqlite"
DEFAULT_TRADES_PATH = ROOT / "data" / "reports" / "stage23c_promotion_candidate_validation" / "stage23c_exact_trades.csv"
DEFAULT_STAGE25B_CANDIDATES_PATH = ROOT / "data" / "reports" / "stage25b_db_first_regime_filter_validation" / "stage25b_filter_candidates.csv"

CANONICAL_CANDIDATE = os.getenv(
    "STAGE25C_CANONICAL_CANDIDATE",
    "S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65",
)

DB_PATH = Path(os.getenv("STAGE25C_DB_PATH", str(DEFAULT_DB_PATH))).expanduser()
TRADES_PATH = Path(os.getenv("STAGE25C_STAGE23C_TRADES_PATH", str(DEFAULT_TRADES_PATH))).expanduser()
STAGE25B_CANDIDATES_PATH = Path(
    os.getenv("STAGE25C_STAGE25B_CANDIDATES_PATH", str(DEFAULT_STAGE25B_CANDIDATES_PATH))
).expanduser()

ROUND_DIGITS = 4


class Stage25CError(RuntimeError):
    pass


def _norm_col(c: str) -> str:
    return str(c).strip().lower().replace("<", "").replace(">", "").replace(" ", "_")


def _safe_float(x: Any) -> float:
    try:
        if pd.isna(x):
            return float("nan")
        return float(x)
    except Exception:
        return float("nan")


def _fmt(x: Any) -> str:
    if isinstance(x, (list, tuple, set)):
        return ", ".join(map(str, x))
    if isinstance(x, dict):
        return json.dumps(x, ensure_ascii=False, default=str)
    if x is None:
        return ""
    try:
        if pd.isna(x):
            return ""
    except Exception:
        pass
    if isinstance(x, (float, np.floating)):
        if math.isinf(float(x)):
            return "inf"
        if math.isnan(float(x)):
            return ""
        return str(round(float(x), ROUND_DIGITS))
    return str(x)


def markdown_table(df: pd.DataFrame, columns: Sequence[str], max_rows: int = 40) -> str:
    if df is None or df.empty:
        return "No rows."
    show = df.loc[:, [c for c in columns if c in df.columns]].head(max_rows).copy()
    if show.empty:
        return "No rows."
    header = "| " + " | ".join(show.columns) + " |"
    sep = "| " + " | ".join(["---"] * len(show.columns)) + " |"
    rows = ["| " + " | ".join(_fmt(row[c]) for c in show.columns) + " |" for _, row in show.iterrows()]
    return "\n".join([header, sep] + rows)


def profit_factor(values: Iterable[float]) -> float:
    arr = np.asarray([float(v) for v in values if pd.notna(v)], dtype=float)
    if arr.size == 0:
        return 0.0
    gains = arr[arr > 0].sum()
    losses = arr[arr < 0].sum()
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return float(gains / abs(losses))


def metric_snapshot(df: pd.DataFrame, prefix: str = "") -> Dict[str, Any]:
    if df.empty:
        return {
            f"{prefix}events": 0,
            f"{prefix}pf_x1": 0.0,
            f"{prefix}pf_x4": 0.0,
            f"{prefix}pf_x6": 0.0,
            f"{prefix}total_x4": 0.0,
            f"{prefix}win_rate_x4": 0.0,
            f"{prefix}median_x4": 0.0,
        }
    out = {
        f"{prefix}events": int(len(df)),
        f"{prefix}pf_x1": profit_factor(df["net_x1"]),
        f"{prefix}pf_x4": profit_factor(df["net_x4"]),
        f"{prefix}pf_x6": profit_factor(df["net_x6"]),
        f"{prefix}total_x4": float(df["net_x4"].sum()),
        f"{prefix}win_rate_x4": float((df["net_x4"] > 0).mean()),
        f"{prefix}median_x4": float(df["net_x4"].median()),
    }
    return out


@dataclass
class CandleTable:
    table: str
    time_col: str
    open_col: str
    high_col: str
    low_col: str
    close_col: str
    timeframe_col: Optional[str]
    symbol_col: Optional[str]


def inspect_tables(conn: sqlite3.Connection) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    tbls = pd.read_sql_query("SELECT name, type FROM sqlite_master WHERE type IN ('table','view') ORDER BY name", conn)
    for _, tr in tbls.iterrows():
        name = str(tr["name"])
        try:
            info = pd.read_sql_query(f"PRAGMA table_info('{name}')", conn)
        except Exception as exc:
            rows.append({"table": name, "error": str(exc)})
            continue
        cols = [str(c) for c in info.get("name", [])]
        ncols = [_norm_col(c) for c in cols]
        try:
            count = pd.read_sql_query(f"SELECT COUNT(*) AS n FROM '{name}'", conn)["n"].iloc[0]
        except Exception:
            count = None
        rows.append({"table": name, "row_count": count, "columns": ", ".join(cols), "norm_columns": ", ".join(ncols)})
    return pd.DataFrame(rows)


def find_candle_table(conn: sqlite3.Connection) -> CandleTable:
    tables = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type IN ('table','view') ORDER BY name", conn)
    time_aliases = ["timestamp", "time", "datetime", "date_time", "bar_time", "broker_time", "utc_time", "ts"]
    open_aliases = ["open", "o"]
    high_aliases = ["high", "h"]
    low_aliases = ["low", "l"]
    close_aliases = ["close", "c"]
    tf_aliases = ["timeframe", "tf", "period", "interval"]
    symbol_aliases = ["symbol", "instrument", "pair"]

    for name in tables["name"].astype(str).tolist():
        try:
            info = pd.read_sql_query(f"PRAGMA table_info('{name}')", conn)
        except Exception:
            continue
        cols = list(info["name"].astype(str))
        norm_to_col = {_norm_col(c): c for c in cols}

        def pick(aliases: Sequence[str]) -> Optional[str]:
            for a in aliases:
                if a in norm_to_col:
                    return norm_to_col[a]
            return None

        time_col = pick(time_aliases)
        open_col = pick(open_aliases)
        high_col = pick(high_aliases)
        low_col = pick(low_aliases)
        close_col = pick(close_aliases)
        if time_col and open_col and high_col and low_col and close_col:
            return CandleTable(
                table=name,
                time_col=time_col,
                open_col=open_col,
                high_col=high_col,
                low_col=low_col,
                close_col=close_col,
                timeframe_col=pick(tf_aliases),
                symbol_col=pick(symbol_aliases),
            )
    raise Stage25CError("No OHLC candle table found in SQLite DB. CSV fallback is intentionally disabled.")


def _quote(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def load_bars_from_db(db_path: Path) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any], pd.DataFrame]:
    if not db_path.exists():
        raise Stage25CError(f"SQLite DB not found: {db_path}")
    conn = sqlite3.connect(str(db_path))
    try:
        schema_diag = inspect_tables(conn)
        ct = find_candle_table(conn)
        cols = [ct.time_col, ct.open_col, ct.high_col, ct.low_col, ct.close_col]
        if ct.timeframe_col:
            cols.append(ct.timeframe_col)
        if ct.symbol_col:
            cols.append(ct.symbol_col)
        col_expr = ", ".join(_quote(c) for c in cols)
        df = pd.read_sql_query(f"SELECT {col_expr} FROM {_quote(ct.table)}", conn)
    finally:
        conn.close()

    rename = {
        ct.time_col: "timestamp",
        ct.open_col: "open",
        ct.high_col: "high",
        ct.low_col: "low",
        ct.close_col: "close",
    }
    if ct.timeframe_col:
        rename[ct.timeframe_col] = "timeframe"
    if ct.symbol_col:
        rename[ct.symbol_col] = "symbol"
    df = df.rename(columns=rename)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["timestamp", "open", "high", "low", "close"]).sort_values("timestamp")

    if "timeframe" in df.columns:
        tf = df["timeframe"].astype(str).str.lower().str.replace(" ", "", regex=False)
        m1 = df.loc[tf.isin(["m1", "1m", "1", "60", "minute", "1min"])].copy()
        h1 = df.loc[tf.isin(["h1", "1h", "60m", "60min", "hour", "3600"])].copy()
    else:
        m1 = df.copy()
        h1 = pd.DataFrame()

    if m1.empty:
        # Fall back to the densest version of the candle table as M1, but never to CSV.
        m1 = df.copy()

    if h1.empty:
        h1 = (
            m1.set_index("timestamp")[["open", "high", "low", "close"]]
            .resample("1h", label="left", closed="left")
            .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
            .dropna()
            .reset_index()
        )
        h1_mode = "derived_from_m1_resample"
    else:
        h1_mode = "db_schema_introspection"

    meta = {
        "db_path": str(db_path),
        "candle_table": ct.table,
        "m1_mode": "db_schema_introspection",
        "m1_rows": int(len(m1)),
        "m1_span": f"{m1['timestamp'].min()} → {m1['timestamp'].max()}" if not m1.empty else "",
        "h1_mode": h1_mode,
        "h1_rows": int(len(h1)),
        "h1_span": f"{h1['timestamp'].min()} → {h1['timestamp'].max()}" if not h1.empty else "",
    }
    return m1.reset_index(drop=True), h1.reset_index(drop=True), meta, schema_diag


def load_stage23c_trades(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise Stage25CError(f"Stage23C trades artifact not found: {path}")
    df = pd.read_csv(path)
    df.columns = [_norm_col(c) for c in df.columns]
    col_aliases = {
        "candidate": ["candidate", "variant", "name", "strategy", "strategy_name"],
        "entry_time": ["entry_time", "timestamp", "time", "signal_time", "entry_ts"],
        "direction": ["direction", "side", "dir"],
        "net_x1": ["net_x1", "x1", "ret_x1", "pnl_x1"],
        "net_x4": ["net_x4", "x4", "ret_x4", "pnl_x4"],
        "net_x6": ["net_x6", "x6", "ret_x6", "pnl_x6"],
    }

    def pick(target: str) -> str:
        for c in col_aliases[target]:
            if c in df.columns:
                return c
        raise Stage25CError(f"Could not find required Stage23C trade column for {target}. Columns: {list(df.columns)}")

    rename = {pick(k): k for k in col_aliases.keys()}
    df = df.rename(columns=rename)
    df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True, errors="coerce")
    df["direction"] = df["direction"].astype(str).str.lower().str.strip()
    for c in ["net_x1", "net_x4", "net_x6"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["entry_time", "direction", "net_x1", "net_x4", "net_x6"])
    return df


def select_canonical_candidate(df: pd.DataFrame, candidate: str) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    all_candidates = sorted(df["candidate"].astype(str).unique().tolist()) if "candidate" in df.columns else []
    exact = df.loc[df["candidate"].astype(str) == candidate].copy()
    mode = "exact_candidate_name"
    if exact.empty:
        # Robust fallback for minor naming differences, but still one canonical non-duplicate candidate.
        name = df["candidate"].astype(str)
        mask = (
            name.str.contains("S23B_B", case=False, regex=False)
            & name.str.contains("pb0.1", case=False, regex=False)
            & name.str.contains("eff0.60", case=False, regex=False)
            & name.str.contains("h180", case=False, regex=False)
        )
        exact = df.loc[mask].copy()
        mode = "pattern_fallback_s23b_b_pb0.1_eff0.60_h180"
    if exact.empty:
        raise Stage25CError(
            "Canonical Stage23C candidate not found. "
            f"Requested={candidate}. Available candidates={all_candidates[:20]}"
        )
    before = len(exact)
    sig_cols = ["entry_time", "direction"]
    if "entry_price" in exact.columns:
        sig_cols.append("entry_price")
    exact = exact.drop_duplicates(subset=sig_cols, keep="first").copy()
    return exact, {
        "selection_mode": mode,
        "requested_candidate": candidate,
        "available_candidate_count": len(all_candidates),
        "canonical_rows_before_event_dedup": int(before),
        "canonical_rows_after_event_dedup": int(len(exact)),
        "available_candidates": all_candidates,
    }


def make_feature_frame(m1: pd.DataFrame) -> pd.DataFrame:
    df = m1.copy()
    df["date"] = df["timestamp"].dt.floor("D")
    df["hour"] = df["timestamp"].dt.hour

    daily = df.groupby("date").agg(
        day_open=("open", "first"),
        day_high=("high", "max"),
        day_low=("low", "min"),
        day_close=("close", "last"),
    ).reset_index()
    daily["day_range"] = daily["day_high"] - daily["day_low"]
    daily["prior_day_range"] = daily["day_range"].shift(1)
    daily["prior_day_direction"] = np.where(daily["day_close"].shift(1) >= daily["day_open"].shift(1), "long", "short")

    def session_agg(name: str, start_hour: int, end_hour: int) -> pd.DataFrame:
        s = df.loc[(df["hour"] >= start_hour) & (df["hour"] < end_hour)].copy()
        if s.empty:
            return pd.DataFrame({"date": []})
        out = s.groupby("date").agg(
            **{
                f"{name}_open": ("open", "first"),
                f"{name}_high": ("high", "max"),
                f"{name}_low": ("low", "min"),
                f"{name}_close": ("close", "last"),
            }
        ).reset_index()
        out[f"{name}_range"] = out[f"{name}_high"] - out[f"{name}_low"]
        out[f"{name}_eff"] = (out[f"{name}_close"] - out[f"{name}_open"]).abs() / out[f"{name}_range"].replace(0, np.nan)
        out[f"{name}_direction"] = np.where(out[f"{name}_close"] >= out[f"{name}_open"], "long", "short")
        return out

    features = daily
    for name, start, end in [
        ("asia", 0, 7),
        ("london", 7, 13),
        ("early_ny", 13, 16),
    ]:
        features = features.merge(session_agg(name, start, end), on="date", how="left")
    return features


def enrich_trades(trades: pd.DataFrame, m1: pd.DataFrame) -> pd.DataFrame:
    features = make_feature_frame(m1)
    out = trades.copy()
    out["date"] = out["entry_time"].dt.floor("D")
    out = out.merge(features, on="date", how="left")
    out["entry_hour"] = out["entry_time"].dt.hour
    out["london_aligned"] = out["direction"].astype(str) == out.get("london_direction", "").astype(str)
    out["prior_day_aligned"] = out["direction"].astype(str) == out.get("prior_day_direction", "").astype(str)
    return out


def quantile_filter(df: pd.DataFrame, col: str, mode: str, q: float) -> pd.Series:
    x = pd.to_numeric(df[col], errors="coerce")
    threshold = x.quantile(q)
    if mode == "drop_low":
        return x > threshold
    if mode == "drop_high":
        return x < threshold
    raise ValueError(mode)


def build_filters(df: pd.DataFrame) -> Dict[str, pd.Series]:
    idx = df.index
    filters: Dict[str, pd.Series] = {
        "keep_short_only": df["direction"].astype(str).eq("short"),
        "keep_long_only": df["direction"].astype(str).eq("long"),
        "keep_london_aligned": df["london_aligned"].fillna(False),
        "drop_london_aligned": ~df["london_aligned"].fillna(False),
        "keep_prior_day_aligned": df["prior_day_aligned"].fillna(False),
        "drop_prior_day_aligned": ~df["prior_day_aligned"].fillna(False),
    }
    for col in ["london_range", "asia_range", "early_ny_range", "prior_day_range", "london_eff"]:
        if col not in df.columns:
            continue
        for qname, q in [("low20", 0.20), ("low30", 0.30), ("high20", 0.80), ("high30", 0.70)]:
            if "low" in qname:
                filters[f"{col}_drop_{qname}"] = quantile_filter(df, col, "drop_low", q).reindex(idx).fillna(False)
            else:
                filters[f"{col}_drop_{qname}"] = quantile_filter(df, col, "drop_high", q).reindex(idx).fillna(False)
    # Top combinations that are interpretable and likely less overfit than arbitrary grid search.
    if "london_range_drop_low30" in filters:
        filters["short_and_london_range_drop_low30"] = filters["keep_short_only"] & filters["london_range_drop_low30"]
    if "early_ny_range_drop_low30" in filters:
        filters["short_and_early_ny_range_drop_low30"] = filters["keep_short_only"] & filters["early_ny_range_drop_low30"]
    if "asia_range_drop_low30" in filters:
        filters["short_and_asia_range_drop_low30"] = filters["keep_short_only"] & filters["asia_range_drop_low30"]
    if "london_range_drop_low30" in filters and "early_ny_range_drop_low30" in filters:
        filters["london_and_early_ny_range_drop_low30"] = filters["london_range_drop_low30"] & filters["early_ny_range_drop_low30"]
    return filters


def validate_filters(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    base = metric_snapshot(df, prefix="base_")
    base_pf_x4 = base["base_pf_x4"]
    base_pf_x6 = base["base_pf_x6"]
    rows: List[Dict[str, Any]] = []
    filters = build_filters(df)
    for name, mask in filters.items():
        kept = df.loc[mask.fillna(False)].copy()
        metrics = metric_snapshot(kept)
        retained = int(metrics["events"])
        retained_ratio = float(retained / len(df)) if len(df) else 0.0
        improve4 = float(metrics["pf_x4"] - base_pf_x4) if not math.isinf(metrics["pf_x4"]) and not math.isinf(base_pf_x4) else float("inf")
        improve6 = float(metrics["pf_x6"] - base_pf_x6) if not math.isinf(metrics["pf_x6"]) and not math.isinf(base_pf_x6) else float("inf")
        decision = "STAGE25C_REJECT"
        if (
            retained >= 35
            and 0.20 <= retained_ratio <= 0.90
            and metrics["pf_x4"] > base_pf_x4 + 0.25
            and metrics["pf_x6"] > base_pf_x6 + 0.10
            and metrics["total_x4"] > 0
        ):
            decision = "STAGE25C_DEDUPED_FILTER_CANDIDATE_REVIEW_ONLY"
        rows.append({
            "decision": decision,
            "filter_name": name,
            "retained_events": retained,
            "retained_ratio": retained_ratio,
            "pf_x1": metrics["pf_x1"],
            "pf_x4": metrics["pf_x4"],
            "pf_x6": metrics["pf_x6"],
            "improvement_pf_x4": improve4,
            "improvement_pf_x6": improve6,
            "total_x4": metrics["total_x4"],
            "win_rate_x4": metrics["win_rate_x4"],
            "median_x4": metrics["median_x4"],
        })
    res = pd.DataFrame(rows)
    if not res.empty:
        res = res.sort_values(["decision", "pf_x4", "pf_x6", "total_x4"], ascending=[True, False, False, False])
        # Put candidates first.
        res["_rank_decision"] = np.where(res["decision"].str.contains("CANDIDATE"), 0, 1)
        res = res.sort_values(["_rank_decision", "pf_x4", "pf_x6", "total_x4"], ascending=[True, False, False, False]).drop(columns=["_rank_decision"])
    return res, base


def compare_with_stage25b(stage25c: pd.DataFrame, stage25b_path: Path) -> pd.DataFrame:
    if not stage25b_path.exists() or stage25c.empty:
        return pd.DataFrame()
    try:
        b = pd.read_csv(stage25b_path)
    except Exception:
        return pd.DataFrame()
    b.columns = [_norm_col(c) for c in b.columns]
    c = stage25c.copy()
    if "filter_name" not in b.columns:
        return pd.DataFrame()
    keep_cols = [x for x in ["filter_name", "pf_x4", "pf_x6", "retained_events", "decision"] if x in b.columns]
    merged = c[["filter_name", "pf_x4", "pf_x6", "retained_events", "decision"]].merge(
        b[keep_cols], on="filter_name", how="left", suffixes=("_stage25c", "_stage25b")
    )
    for col in ["pf_x4", "pf_x6"]:
        if f"{col}_stage25b" in merged.columns:
            merged[f"delta_{col}_c_minus_b"] = merged[f"{col}_stage25c"] - merged[f"{col}_stage25b"]
    return merged


def write_error_report(error: Exception) -> None:
    md = REPORT_DIR / "stage25c_deduped_filter_validation.md"
    payload = {
        "decision": "STAGE25C_ERROR_DIAGNOSTIC_ONLY",
        "error": f"{type(error).__name__}: {error}",
    }
    (REPORT_DIR / "stage25c_deduped_filter_validation.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    lines = [
        "# Stage25C De-duplicated Filter Validation",
        "",
        "## Decision",
        "",
        "```text",
        "STAGE25C_ERROR_DIAGNOSTIC_ONLY",
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
        "- This is a diagnostic error, not an authorization change.",
        "- Stage18A v2 and Stage23D remain unchanged.",
        "- CSV fallback for candles remains intentionally disabled.",
    ]
    md.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    try:
        m1, h1, db_meta, schema_diag = load_bars_from_db(DB_PATH)
        schema_diag.to_csv(REPORT_DIR / "stage25c_db_schema_diagnostic.csv", index=False)
        all_trades = load_stage23c_trades(TRADES_PATH)
        canonical, sel_meta = select_canonical_candidate(all_trades, CANONICAL_CANDIDATE)
        enriched = enrich_trades(canonical, m1)
        filter_df, base_metrics = validate_filters(enriched)
        comparison = compare_with_stage25b(filter_df, STAGE25B_CANDIDATES_PATH)

        candidate_count = int(filter_df["decision"].str.contains("CANDIDATE").sum()) if not filter_df.empty else 0
        decision = "STAGE25C_DEDUPED_HAS_FILTER_CANDIDATE_REVIEW_ONLY" if candidate_count > 0 else "STAGE25C_DEDUPED_NO_FILTER_CANDIDATE_REVIEW_ONLY"

        filter_df.to_csv(REPORT_DIR / "stage25c_filter_candidates.csv", index=False)
        enriched.to_csv(REPORT_DIR / "stage25c_enriched_canonical_trades.csv", index=False)
        comparison.to_csv(REPORT_DIR / "stage25c_stage25b_comparison.csv", index=False)

        payload = {
            "decision": decision,
            "db_source_of_truth": db_meta,
            "trade_artifact_path": str(TRADES_PATH),
            "selection": sel_meta,
            "base_metrics": base_metrics,
            "candidate_count": candidate_count,
            "output_files": {
                "md": str(REPORT_DIR / "stage25c_deduped_filter_validation.md"),
                "json": str(REPORT_DIR / "stage25c_deduped_filter_validation.json"),
                "filter_candidates": str(REPORT_DIR / "stage25c_filter_candidates.csv"),
                "enriched_trades": str(REPORT_DIR / "stage25c_enriched_canonical_trades.csv"),
                "comparison": str(REPORT_DIR / "stage25c_stage25b_comparison.csv"),
                "schema": str(REPORT_DIR / "stage25c_db_schema_diagnostic.csv"),
            },
        }
        (REPORT_DIR / "stage25c_deduped_filter_validation.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

        lines = [
            "# Stage25C De-duplicated DB-First Filter Validation",
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
            "- Research/shadow diagnostic only.",
            "- Stage18A v2 remains unchanged.",
            "- Stage23D remains unchanged.",
            "- No EA change, no automatic trading, no paper/live/order authorization.",
            "- AMarkets CSV fallback is intentionally disabled; candle/regime features are DB-first.",
            "- Stage23C trade artifact is used only as the historical trade list; duplicate variants are not treated as independent evidence.",
            "",
            "## DB source of truth",
            "",
        ]
        for k, v in db_meta.items():
            lines.append(f"- {k}: `{v}`")
        lines += [
            "",
            "## Canonical trade selection",
            "",
        ]
        for k, v in sel_meta.items():
            if k == "available_candidates":
                lines.append(f"- available_candidates_sample: `{', '.join(v[:10])}`")
            else:
                lines.append(f"- {k}: `{v}`")
        lines += [
            "",
            "## Base canonical Stage23C metrics, DB-derived features",
            "",
            "```json",
            json.dumps(base_metrics, indent=2, default=str),
            "```",
            "",
            "## Top de-duplicated filter diagnostics",
            "",
            markdown_table(
                filter_df,
                [
                    "decision", "filter_name", "retained_events", "retained_ratio", "pf_x1", "pf_x4", "pf_x6",
                    "improvement_pf_x4", "improvement_pf_x6", "total_x4", "win_rate_x4", "median_x4",
                ],
                35,
            ),
            "",
            "## Stage25B aggregate vs Stage25C de-duplicated comparison",
            "",
            markdown_table(
                comparison,
                [
                    "filter_name", "decision_stage25c", "decision_stage25b", "pf_x4_stage25c", "pf_x4_stage25b",
                    "delta_pf_x4_c_minus_b", "pf_x6_stage25c", "pf_x6_stage25b", "delta_pf_x6_c_minus_b",
                    "retained_events_stage25c", "retained_events_stage25b",
                ],
                25,
            ),
            "",
            "## Interpretation",
            "",
            "- This module checks whether Stage25B's strong filters survive after de-duplicating the Stage23C evidence to one canonical Stage23B/C candidate.",
            "- `keep_short_only` is useful diagnostically, but it is a direction filter, not a market-regime filter by itself.",
            "- A robust next filter should ideally survive on the canonical candidate and remain interpretable, such as `london_range_drop_low30` or a conservative combination.",
            "- Any surviving filter remains research-only and requires forward-shadow validation before operational use.",
            "",
            "## Operational reminder",
            "",
            "```bash",
            "cd ~/Desktop/xauusd-trader",
            "python3 -m app.stage18a_unified_shadow_ops_cycle",
            "cat data/reports/stage18a_unified_shadow_ops_cycle/stage18a_unified_shadow_ops_cycle.md",
            "",
            "python3 -m app.stage23d_forward_shadow_candidate",
            "cat data/reports/stage23d_forward_shadow_candidate/stage23d_forward_shadow_candidate.md",
            "```",
            "",
            "## Output files",
            "",
            "- `data/reports/stage25c_deduped_filter_validation/stage25c_deduped_filter_validation.json`",
            "- `data/reports/stage25c_deduped_filter_validation/stage25c_deduped_filter_validation.md`",
            "- `data/reports/stage25c_deduped_filter_validation/stage25c_filter_candidates.csv`",
            "- `data/reports/stage25c_deduped_filter_validation/stage25c_enriched_canonical_trades.csv`",
            "- `data/reports/stage25c_deduped_filter_validation/stage25c_stage25b_comparison.csv`",
            "- `data/reports/stage25c_deduped_filter_validation/stage25c_db_schema_diagnostic.csv`",
        ]
        (REPORT_DIR / "stage25c_deduped_filter_validation.md").write_text("\n".join(lines), encoding="utf-8")
    except Exception as exc:
        write_error_report(exc)


if __name__ == "__main__":
    main()
