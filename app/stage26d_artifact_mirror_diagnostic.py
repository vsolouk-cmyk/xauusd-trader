"""Stage26D Artifact Mirror / Anti-Signal Diagnostic.

Hotfix 3: robust artifact normalizer and duplicate-column-safe metrics.

Purpose
-------
This diagnostic reads previous exact-trade artifacts from Stage26A/B/C and tests
whether rejected rules behave as anti-signals when mirrored. It does not create
orders and does not modify Stage18A/23D/25D.

Design choices
--------------
- Market data remains DB-first from SQLite. No AMarkets CSV market-data fallback
  is used.
- Exact-trade CSV files are treated as research artifacts, not market data.
- Stage26A/B exact-trade artifacts may not contain a column literally named
  ``timestamp``. This version no longer requires that column; it uses any known
  time/event column when present and otherwise keeps rows as artifact events.
- Mirror PnL is a diagnostic approximation unless a gross PnL column is present.
  If only net PnL is available, mirrored net PnL is estimated by reversing net
  PnL and charging symmetric roundtrip cost again.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

DEFAULT_DB_PATH = Path(os.getenv("XAUUSD_DB_PATH", "data/local/xauusd_local_store.sqlite"))
REPORT_DIR = Path("data/reports/stage26d_artifact_mirror_diagnostic")
ROUNDTRIP_COST_X1 = float(os.getenv("STAGE26D_ROUNDTRIP_COST_X1", "0.35"))
BOOT_SAMPLES = int(os.getenv("STAGE26D_BOOT_SAMPLES", "300"))
BOOT_SEED = int(os.getenv("STAGE26D_BOOT_SEED", "260104"))

ARTIFACTS = [
    {
        "source_stage": "stage26a",
        "path": Path("data/reports/stage26a_db_first_structured_behavior_discovery/stage26a_exact_trades.csv"),
    },
    {
        "source_stage": "stage26b",
        "path": Path("data/reports/stage26b_db_first_family_coverage_discovery/stage26b_exact_trades.csv"),
    },
    {
        "source_stage": "stage26c",
        "path": Path("data/reports/stage26c_db_first_failure_reversal_discovery/stage26c_exact_trades.csv"),
    },
]

TIME_COLUMNS = [
    "timestamp",
    "entry_time",
    "entry_timestamp",
    "entry_ts",
    "entry_dt",
    "entry_bar_time",
    "entry_bar_ts",
    "bar_time",
    "time",
    "datetime",
    "date_time",
    "event_time",
    "event_ts",
]
FAMILY_COLUMNS = ["family", "source_family", "rule_family", "strategy_family"]
CANDIDATE_COLUMNS = ["candidate", "name", "variant", "rule_name", "strategy", "id"]
DIRECTION_COLUMNS = ["direction_label", "direction", "side", "trade_direction"]
REASON_COLUMNS = ["reason", "signal_reason", "setup_reason", "trigger_reason"]
ENTRY_HOUR_COLUMNS = ["entry_hour", "hour", "signal_hour"]

# Preferred direct net columns. Later fallbacks include substring matching.
NET_X1_COLUMNS = ["net_x1", "pnl_x1", "ret_x1", "net", "pnl", "profit", "return", "outcome_x1"]
NET_X4_COLUMNS = ["net_x4", "pnl_x4", "ret_x4", "outcome_x4"]
NET_X6_COLUMNS = ["net_x6", "pnl_x6", "ret_x6", "outcome_x6"]
GROSS_X1_COLUMNS = ["gross_x1", "gross_pnl_x1", "gross_ret_x1", "gross", "raw_pnl", "raw_ret"]
GROSS_X4_COLUMNS = ["gross_x4", "gross_pnl_x4", "gross_ret_x4"]
GROSS_X6_COLUMNS = ["gross_x6", "gross_pnl_x6", "gross_ret_x6"]


class Stage26DHotfixError(RuntimeError):
    pass


@dataclass
class DBMeta:
    db_path: str
    candle_table: str
    db_first: bool
    csv_fallback_enabled: bool
    m1_rows: int
    m1_span: str
    h1_rows: int
    h1_span: str
    h1_mode: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm_col(c: Any) -> str:
    return str(c).strip().lower().replace(" ", "_").replace("-", "_")


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [_norm_col(c) for c in out.columns]
    return out


def _find_column(df: pd.DataFrame, candidates: Sequence[str]) -> Optional[str]:
    cols = set(df.columns)
    for c in candidates:
        if c in cols:
            return c
    return None


def _find_numeric_column(df: pd.DataFrame, candidates: Sequence[str], substrings: Sequence[str] = ()) -> Optional[str]:
    direct = _find_column(df, candidates)
    if direct is not None:
        return direct
    for col in df.columns:
        if any(s in col for s in substrings):
            converted = pd.to_numeric(df[col], errors="coerce")
            if converted.notna().sum() > 0:
                return col
    return None


def _safe_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _first_existing_table(conn: sqlite3.Connection) -> Optional[str]:
    tables = pd.read_sql_query(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name", conn
    )["name"].astype(str).tolist()
    preferred = ["bars", "ohlcv", "candles", "xauusd_bars", "price_bars"]
    for t in preferred:
        if t in tables:
            return t
    return tables[0] if tables else None


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _inspect_db(db_path: Path) -> DBMeta:
    if not db_path.exists():
        return DBMeta(str(db_path), "", True, False, 0, "missing_db", 0, "missing_db", "db_missing")

    with sqlite3.connect(str(db_path)) as conn:
        table = _first_existing_table(conn)
        if not table:
            return DBMeta(str(db_path), "", True, False, 0, "no_tables", 0, "no_tables", "no_tables")

        qtable = _quote_ident(table)
        cols_df = pd.read_sql_query(f"PRAGMA table_info({qtable})", conn)
        cols = [_norm_col(c) for c in cols_df.get("name", pd.Series(dtype=str)).tolist()]
        original_cols = cols_df.get("name", pd.Series(dtype=str)).astype(str).tolist()
        col_map = {_norm_col(c): c for c in original_cols}

        tf_col = None
        for c in ["timeframe", "tf", "interval", "granularity"]:
            if c in col_map:
                tf_col = col_map[c]
                break
        time_col = None
        for c in ["timestamp", "time", "datetime", "date", "bar_time", "open_time"]:
            if c in col_map:
                time_col = col_map[c]
                break

        def count_span(tf_value: Optional[str]) -> Tuple[int, str]:
            where = ""
            params: Tuple[Any, ...] = ()
            if tf_col and tf_value:
                where = f"WHERE lower({ _quote_ident(tf_col) }) = lower(?)"
                params = (tf_value,)
            count = int(pd.read_sql_query(f"SELECT COUNT(*) AS n FROM {qtable} {where}", conn, params=params)["n"].iloc[0])
            if time_col and count > 0:
                span_df = pd.read_sql_query(
                    f"SELECT MIN({_quote_ident(time_col)}) AS mn, MAX({_quote_ident(time_col)}) AS mx FROM {qtable} {where}",
                    conn,
                    params=params,
                )
                span = f"{span_df['mn'].iloc[0]} → {span_df['mx'].iloc[0]}"
            else:
                span = "unavailable"
            return count, span

        # If table has timeframe column, count exact M1/H1. Otherwise report full
        # table as M1-like and leave H1 unavailable. Existing Stage25C/23D reports
        # use timeframe-aware bars, so this should match them.
        m1_rows, m1_span = count_span("M1" if tf_col else None)
        h1_rows, h1_span = count_span("H1") if tf_col else (0, "not_separate")
        h1_mode = "db_schema_introspection" if h1_rows else "not_found_or_derived_elsewhere"
        return DBMeta(str(db_path), table, True, False, m1_rows, m1_span, h1_rows, h1_span, h1_mode)


def _profit_factor(values: pd.Series) -> float:
    vals = pd.to_numeric(values, errors="coerce").dropna()
    if vals.empty:
        return 0.0
    gains = vals[vals > 0].sum()
    losses = -vals[vals < 0].sum()
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return float(gains / losses)


def _boot_pf_p05(values: pd.Series, samples: int = BOOT_SAMPLES, seed: int = BOOT_SEED) -> float:
    vals = pd.to_numeric(values, errors="coerce").dropna().to_numpy(dtype=float)
    if len(vals) < 10:
        return 0.0
    rng = np.random.default_rng(seed)
    pfs: List[float] = []
    for _ in range(samples):
        draw = rng.choice(vals, size=len(vals), replace=True)
        gains = draw[draw > 0].sum()
        losses = -draw[draw < 0].sum()
        if losses == 0:
            pfs.append(float("inf") if gains > 0 else 0.0)
        else:
            pfs.append(float(gains / losses))
    finite = np.array([p for p in pfs if math.isfinite(p)], dtype=float)
    if finite.size == 0:
        return float("inf")
    return float(np.nanpercentile(finite, 5))


def _numeric_series(df: pd.DataFrame, col: str, fallback_col: Optional[str] = None) -> pd.Series:
    """Return a single numeric Series even when pandas sees duplicate column names.

    The Stage26D hotfix2 failure happened because renaming original_* columns
    onto mirror_* names produced duplicate labels; df.get()/df[col] then returned
    a DataFrame, not a 1-D Series. This helper makes metrics robust and the
    group-metrics path avoids duplicate labels entirely.
    """
    chosen: Optional[str] = None
    if col in df.columns:
        chosen = col
    elif fallback_col and fallback_col in df.columns:
        chosen = fallback_col
    if chosen is None:
        return pd.Series(dtype=float)
    obj = df.loc[:, chosen]
    if isinstance(obj, pd.DataFrame):
        obj = obj.iloc[:, 0]
    return pd.to_numeric(obj, errors="coerce")


def _metrics(df: pd.DataFrame, prefix: str = "mirror_net") -> Dict[str, Any]:
    x1 = f"{prefix}_x1"
    x4 = f"{prefix}_x4"
    x6 = f"{prefix}_x6"
    if df.empty or x1 not in df.columns:
        return {
            "events": 0,
            "pf_x1": 0.0,
            "pf_x4": 0.0,
            "pf_x6": 0.0,
            "boot_pf_p05_x4": 0.0,
            "median_x4": 0.0,
            "total_x4": 0.0,
            "win_rate_x4": 0.0,
        }

    x1s = _numeric_series(df, x1).dropna()
    x4s = _numeric_series(df, x4, fallback_col=x1).dropna()
    x6s = _numeric_series(df, x6, fallback_col=x1).dropna()
    if x1s.empty:
        return {
            "events": 0,
            "pf_x1": 0.0,
            "pf_x4": 0.0,
            "pf_x6": 0.0,
            "boot_pf_p05_x4": 0.0,
            "median_x4": 0.0,
            "total_x4": 0.0,
            "win_rate_x4": 0.0,
        }

    return {
        "events": int(len(df)),
        "pf_x1": round(_profit_factor(x1s), 4),
        "pf_x4": round(_profit_factor(x4s), 4),
        "pf_x6": round(_profit_factor(x6s), 4),
        "boot_pf_p05_x4": round(_boot_pf_p05(x4s), 4),
        "median_x4": round(float(x4s.median()) if not x4s.empty else 0.0, 4),
        "total_x4": round(float(x4s.sum()) if not x4s.empty else 0.0, 4),
        "win_rate_x4": round(float((x4s > 0).mean()) if not x4s.empty else 0.0, 4),
    }


def _decision(m: Dict[str, Any]) -> str:
    events = int(m.get("events", 0))
    pf_x4 = float(m.get("pf_x4", 0.0)) if math.isfinite(float(m.get("pf_x4", 0.0))) else 999.0
    pf_x6 = float(m.get("pf_x6", 0.0)) if math.isfinite(float(m.get("pf_x6", 0.0))) else 999.0
    total_x4 = float(m.get("total_x4", 0.0))
    boot = float(m.get("boot_pf_p05_x4", 0.0)) if math.isfinite(float(m.get("boot_pf_p05_x4", 0.0))) else 999.0
    if events >= 30 and pf_x4 >= 1.35 and pf_x6 >= 1.0 and total_x4 > 0 and boot >= 0.85:
        return "STAGE26D_MIRROR_PROMOTION_REVIEW_ONLY"
    if events >= 25 and pf_x4 >= 1.05 and total_x4 > 0:
        return "STAGE26D_MIRROR_WATCHLIST_ONLY"
    return "STAGE26D_REJECT"


def _choose_net_columns(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    return {
        "net_x1": _find_numeric_column(df, NET_X1_COLUMNS, ("net_x1", "pnl_x1", "ret_x1", "outcome_x1")),
        "net_x4": _find_numeric_column(df, NET_X4_COLUMNS, ("net_x4", "pnl_x4", "ret_x4", "outcome_x4")),
        "net_x6": _find_numeric_column(df, NET_X6_COLUMNS, ("net_x6", "pnl_x6", "ret_x6", "outcome_x6")),
        "gross_x1": _find_numeric_column(df, GROSS_X1_COLUMNS, ("gross_x1", "raw_pnl", "raw_ret")),
        "gross_x4": _find_numeric_column(df, GROSS_X4_COLUMNS, ("gross_x4", "gross_pnl_x4", "gross_ret_x4")),
        "gross_x6": _find_numeric_column(df, GROSS_X6_COLUMNS, ("gross_x6", "gross_pnl_x6", "gross_ret_x6")),
    }


def _normalise_artifact(source_stage: str, path: Path) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    manifest: Dict[str, Any] = {
        "source_stage": source_stage,
        "path": str(path),
        "exists": path.exists(),
        "rows": 0,
        "loaded_rows": 0,
        "status": "missing",
        "time_column_used": "",
        "net_column_mode": "",
        "columns": "",
    }
    if not path.exists():
        return pd.DataFrame(), manifest

    try:
        df_raw = pd.read_csv(path)
    except Exception as exc:  # pragma: no cover - diagnostic robustness
        manifest["status"] = f"read_error:{type(exc).__name__}:{exc}"
        return pd.DataFrame(), manifest

    manifest["rows"] = int(len(df_raw))
    df = _normalise_columns(df_raw)
    manifest["columns"] = ",".join(df.columns[:80])
    if df.empty:
        manifest["status"] = "empty"
        return pd.DataFrame(), manifest

    col_family = _find_column(df, FAMILY_COLUMNS)
    col_candidate = _find_column(df, CANDIDATE_COLUMNS)
    col_direction = _find_column(df, DIRECTION_COLUMNS)
    col_reason = _find_column(df, REASON_COLUMNS)
    col_hour = _find_column(df, ENTRY_HOUR_COLUMNS)
    col_time = _find_column(df, TIME_COLUMNS)
    col_decision = _find_column(df, ["decision", "status"])
    chosen = _choose_net_columns(df)

    if not chosen["net_x1"] and not chosen["gross_x1"]:
        manifest["status"] = "skipped_missing_pnl_columns"
        return pd.DataFrame(), manifest

    out = pd.DataFrame(index=df.index)
    out["source_stage"] = source_stage
    out["family"] = df[col_family].astype(str) if col_family else "unknown_family"
    out["candidate"] = df[col_candidate].astype(str) if col_candidate else "unknown_candidate"
    out["direction_label"] = df[col_direction].astype(str).str.lower() if col_direction else "unknown"
    out["reason"] = df[col_reason].astype(str) if col_reason else "unknown_reason"
    if col_hour:
        out["entry_hour"] = pd.to_numeric(df[col_hour], errors="coerce").fillna(-1).astype(int)
    elif col_time:
        ts = pd.to_datetime(df[col_time], errors="coerce", utc=True)
        out["entry_hour"] = ts.dt.hour.fillna(-1).astype(int)
    else:
        out["entry_hour"] = -1
    out["timestamp"] = df[col_time].astype(str) if col_time else ""
    out["source_decision"] = df[col_decision].astype(str) if col_decision else "unknown"

    # Original net values.
    if chosen["net_x1"]:
        out["original_net_x1"] = _safe_numeric(df[chosen["net_x1"]])
        mode = "net"
    else:
        out["original_net_x1"] = _safe_numeric(df[chosen["gross_x1"]]) - ROUNDTRIP_COST_X1
        mode = "gross_minus_cost"
    if chosen["net_x4"]:
        out["original_net_x4"] = _safe_numeric(df[chosen["net_x4"]])
    elif chosen["gross_x4"]:
        out["original_net_x4"] = _safe_numeric(df[chosen["gross_x4"]]) - 4 * ROUNDTRIP_COST_X1
    else:
        out["original_net_x4"] = out["original_net_x1"] - (3 * ROUNDTRIP_COST_X1)
    if chosen["net_x6"]:
        out["original_net_x6"] = _safe_numeric(df[chosen["net_x6"]])
    elif chosen["gross_x6"]:
        out["original_net_x6"] = _safe_numeric(df[chosen["gross_x6"]]) - 6 * ROUNDTRIP_COST_X1
    else:
        out["original_net_x6"] = out["original_net_x1"] - (5 * ROUNDTRIP_COST_X1)

    # Mirror net values. Prefer gross if present; otherwise reverse net and charge symmetric cost again.
    if chosen["gross_x1"]:
        out["mirror_net_x1"] = -_safe_numeric(df[chosen["gross_x1"]]) - ROUNDTRIP_COST_X1
        mirror_mode = "gross_reversal"
    else:
        out["mirror_net_x1"] = -out["original_net_x1"] - (2 * ROUNDTRIP_COST_X1)
        mirror_mode = "net_reversal_symmetric_cost"
    if chosen["gross_x4"]:
        out["mirror_net_x4"] = -_safe_numeric(df[chosen["gross_x4"]]) - 4 * ROUNDTRIP_COST_X1
    else:
        out["mirror_net_x4"] = -out["original_net_x4"] - (2 * 4 * ROUNDTRIP_COST_X1)
    if chosen["gross_x6"]:
        out["mirror_net_x6"] = -_safe_numeric(df[chosen["gross_x6"]]) - 6 * ROUNDTRIP_COST_X1
    else:
        out["mirror_net_x6"] = -out["original_net_x6"] - (2 * 6 * ROUNDTRIP_COST_X1)

    out = out.dropna(subset=["original_net_x1", "mirror_net_x1"])
    manifest["loaded_rows"] = int(len(out))
    manifest["status"] = "loaded" if len(out) else "no_numeric_rows_after_normalization"
    manifest["time_column_used"] = col_time or "not_required_missing"
    manifest["net_column_mode"] = f"original:{mode};mirror:{mirror_mode};cols:{json.dumps(chosen, ensure_ascii=False)}"
    return out, manifest


def _group_metrics(df: pd.DataFrame, group_cols: Sequence[str]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    if df.empty:
        return pd.DataFrame()
    for keys, g in df.groupby(list(group_cols), dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        row = {col: key for col, key in zip(group_cols, keys)}
        m = _metrics(g, "mirror_net")
        original_view = pd.DataFrame({
            "mirror_net_x1": _numeric_series(g, "original_net_x1"),
            "mirror_net_x4": _numeric_series(g, "original_net_x4", fallback_col="original_net_x1"),
            "mirror_net_x6": _numeric_series(g, "original_net_x6", fallback_col="original_net_x1"),
        })
        orig_m = _metrics(original_view, "mirror_net")
        row.update(m)
        row["original_pf_x4"] = orig_m["pf_x4"]
        row["original_total_x4"] = orig_m["total_x4"]
        row["mirror_minus_original_pf_x4"] = round(float(m["pf_x4"]) - float(orig_m["pf_x4"]), 4)
        row["decision"] = _decision(m)
        rows.append(row)
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    sort_cols = ["decision", "pf_x4", "total_x4", "events"]
    existing = [c for c in sort_cols if c in out.columns]
    out = out.sort_values(existing, ascending=[True, False, False, False][: len(existing)])
    return out


def _df_to_md(df: pd.DataFrame, max_rows: int = 30) -> str:
    if df is None or df.empty:
        return "No rows."
    view = df.head(max_rows).copy()
    for c in view.columns:
        if pd.api.types.is_float_dtype(view[c]):
            view[c] = view[c].map(lambda x: "inf" if math.isinf(x) else round(float(x), 4))
    return view.to_markdown(index=False)


def _write_outputs(
    db_meta: DBMeta,
    manifest: pd.DataFrame,
    normalized: pd.DataFrame,
    by_candidate: pd.DataFrame,
    by_family: pd.DataFrame,
    by_reason: pd.DataFrame,
    by_direction_hour: pd.DataFrame,
) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(REPORT_DIR / "stage26d_input_manifest.csv", index=False)
    normalized.to_csv(REPORT_DIR / "stage26d_normalized_source_trades.csv", index=False)
    by_candidate.to_csv(REPORT_DIR / "stage26d_mirror_by_candidate.csv", index=False)
    by_family.to_csv(REPORT_DIR / "stage26d_mirror_by_family.csv", index=False)
    by_reason.to_csv(REPORT_DIR / "stage26d_mirror_by_reason.csv", index=False)
    by_direction_hour.to_csv(REPORT_DIR / "stage26d_mirror_by_direction_hour.csv", index=False)
    pd.DataFrame([db_meta.__dict__]).to_csv(REPORT_DIR / "stage26d_db_schema_diagnostic.csv", index=False)

    promotion_count = int((by_candidate.get("decision", pd.Series(dtype=str)) == "STAGE26D_MIRROR_PROMOTION_REVIEW_ONLY").sum()) if not by_candidate.empty else 0
    watch_count = int((by_candidate.get("decision", pd.Series(dtype=str)) == "STAGE26D_MIRROR_WATCHLIST_ONLY").sum()) if not by_candidate.empty else 0
    if promotion_count > 0:
        decision = "STAGE26D_MIRROR_PROMOTION_REVIEW_ONLY_DIAGNOSTIC_ONLY"
    elif watch_count > 0:
        decision = "STAGE26D_MIRROR_WATCHLIST_ONLY_KEEP_DISCOVERY_OPEN"
    else:
        decision = "STAGE26D_NO_MIRROR_EDGE_KEEP_DISCOVERY_OPEN"

    payload = {
        "generated_utc": _utc_now(),
        "decision": decision,
        "db_source_of_truth": db_meta.__dict__,
        "counts": {
            "input_files_configured": len(ARTIFACTS),
            "input_files_loaded": int((manifest["status"] == "loaded").sum()) if not manifest.empty else 0,
            "source_trade_rows": int(len(normalized)),
            "mirror_candidate_groups": int(len(by_candidate)),
            "mirror_family_groups": int(len(by_family)),
            "mirror_promotion_review_candidates": promotion_count,
            "mirror_watchlist_only_candidates": watch_count,
        },
    }
    with open(REPORT_DIR / "stage26d_artifact_mirror_diagnostic.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    md = f"""# Stage26D Artifact Mirror / Anti-Signal Diagnostic

Generated UTC: `{payload['generated_utc']}`

## Decision

```text
{decision}
```

## Scope guardrails

- Research/shadow diagnostic only.
- Stage18A v2 remains the active operational forward-shadow runner.
- Stage23D and Stage25D remain separate DB-first trackers.
- No EA change, no automatic trading, no paper/live/order authorization.
- Market candles are DB-first from SQLite; AMarkets CSV market fallback is disabled.
- Previous exact-trade CSV outputs are used only as research artifacts, not as market-data fallback.
- Hotfix 3 no longer requires a literal `timestamp` column and makes metrics duplicate-column-safe.
- Mirrored results are anti-signal diagnostics only and require a later DB-first exact replay before any forward-shadow tracker.

## DB source of truth

- db_path: `{db_meta.db_path}`
- candle_table: `{db_meta.candle_table}`
- db_first: `{db_meta.db_first}`
- csv_fallback_enabled: `{db_meta.csv_fallback_enabled}`
- m1_rows: `{db_meta.m1_rows}` | span: `{db_meta.m1_span}`
- h1_rows: `{db_meta.h1_rows}` | span: `{db_meta.h1_span}`
- h1_mode: `{db_meta.h1_mode}`

## Counts

- input_files_configured: `{payload['counts']['input_files_configured']}`
- input_files_loaded: `{payload['counts']['input_files_loaded']}`
- source_trade_rows: `{payload['counts']['source_trade_rows']}`
- mirror_candidate_groups: `{payload['counts']['mirror_candidate_groups']}`
- mirror_family_groups: `{payload['counts']['mirror_family_groups']}`
- mirror_promotion_review_candidates: `{payload['counts']['mirror_promotion_review_candidates']}`
- mirror_watchlist_only_candidates: `{payload['counts']['mirror_watchlist_only_candidates']}`

## Input artifact manifest

{_df_to_md(manifest, 10)}

## Top mirrored candidate diagnostics

{_df_to_md(by_candidate, 30)}

## Mirrored family diagnostics

{_df_to_md(by_family, 30)}

## Mirrored reason diagnostics

{_df_to_md(by_reason, 30)}

## Mirrored direction/hour diagnostics

{_df_to_md(by_direction_hour, 30)}

## Interpretation

- Stage26D checks whether rejected exact trades from Stage26A/B/C behave as anti-signals.
- Unlike earlier Stage26D versions, Stage26A/B artifacts are not skipped just because they lack a literal `timestamp` column, and original-vs-mirror grouping avoids duplicate pandas column labels.
- A positive mirror result is not enough for promotion because path-dependent TP/SL execution must be replayed directly from DB candles in the mirrored direction.
- If this stage finds a promotion-review mirror candidate, the next step is a dedicated DB-first exact replay for that mirrored rule.
- If no mirror edge appears after all three artifacts load, discovery should move away from Stage26A/B/C families rather than repeatedly mutating them.

## Operational reminder

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage18a_unified_shadow_ops_cycle
python3 -m app.stage23d_forward_shadow_candidate
python3 -m app.stage25d_db_first_filtered_forward_shadow
```

## Output files

- `data/reports/stage26d_artifact_mirror_diagnostic/stage26d_artifact_mirror_diagnostic.json`
- `data/reports/stage26d_artifact_mirror_diagnostic/stage26d_artifact_mirror_diagnostic.md`
- `data/reports/stage26d_artifact_mirror_diagnostic/stage26d_input_manifest.csv`
- `data/reports/stage26d_artifact_mirror_diagnostic/stage26d_normalized_source_trades.csv`
- `data/reports/stage26d_artifact_mirror_diagnostic/stage26d_mirror_by_candidate.csv`
- `data/reports/stage26d_artifact_mirror_diagnostic/stage26d_mirror_by_family.csv`
- `data/reports/stage26d_artifact_mirror_diagnostic/stage26d_mirror_by_reason.csv`
- `data/reports/stage26d_artifact_mirror_diagnostic/stage26d_mirror_by_direction_hour.csv`
- `data/reports/stage26d_artifact_mirror_diagnostic/stage26d_db_schema_diagnostic.csv`
"""
    (REPORT_DIR / "stage26d_artifact_mirror_diagnostic.md").write_text(md, encoding="utf-8")


def run() -> None:
    db_meta = _inspect_db(DEFAULT_DB_PATH)
    manifests: List[Dict[str, Any]] = []
    frames: List[pd.DataFrame] = []
    for item in ARTIFACTS:
        df, manifest = _normalise_artifact(item["source_stage"], item["path"])
        manifests.append(manifest)
        if not df.empty:
            frames.append(df)
    manifest_df = pd.DataFrame(manifests)
    normalized = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    by_candidate = _group_metrics(normalized, ["source_stage", "family", "candidate"])
    by_family = _group_metrics(normalized, ["source_stage", "family"])
    by_reason = _group_metrics(normalized, ["source_stage", "family", "reason"])
    by_direction_hour = _group_metrics(normalized, ["source_stage", "family", "direction_label", "entry_hour"])

    _write_outputs(db_meta, manifest_df, normalized, by_candidate, by_family, by_reason, by_direction_hour)


def main() -> None:
    try:
        run()
    except Exception as exc:  # diagnostic report rather than silent failure
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        message = f"{type(exc).__name__}: {exc}"
        md = f"""# Stage26D Artifact Mirror / Anti-Signal Diagnostic

## Decision

```text
STAGE26D_ERROR_DIAGNOSTIC_ONLY
```

## Error

```text
{message}
```

- DB-first is enabled.
- CSV market fallback is intentionally disabled.
- Stage18A, Stage23D, and Stage25D remain unchanged.
"""
        (REPORT_DIR / "stage26d_artifact_mirror_diagnostic.md").write_text(md, encoding="utf-8")
        raise


if __name__ == "__main__":
    main()
