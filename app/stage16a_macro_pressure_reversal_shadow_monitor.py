#!/usr/bin/env python3
"""
Stage 16A — Macro Pressure/Reversal Forward-Shadow Monitor

Research-only monitor for the validated Stage 15D branch:

Technical setup:
- prev_day_low_sweep_rejection
- LONG research direction
- sweep_depth >= 1.62
- reclaim_above_prev_day_low < 1.55

Macro context:
- real_yield_10y 5-observation change > 0

Interpretation:
- This is counterintuitive for classic gold macro logic.
- Treat as pressure/reversal context:
  rising real yield pressures gold, then a liquidity sweep/reclaim may mean-revert intraday.

Hard rules:
- Research shadow only.
- No EA change.
- No automatic trading.
- No paper/live/order authorization.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd


TOOL_VERSION = "v1"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_OUT_DIR = Path("data/reports/stage16a_macro_pressure_reversal_shadow_monitor")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def normalize_col(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).strip().lower()).strip("_")


def connect(db: Path) -> sqlite3.Connection:
    if not db.exists():
        raise FileNotFoundError(f"DB not found: {db}")
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    r = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return bool(r)


def load_bars(conn: sqlite3.Connection, tf: str) -> pd.DataFrame:
    if not table_exists(conn, "bars"):
        raise RuntimeError("Missing table: bars")
    rows = conn.execute(
        """
        SELECT utc_time, open, high, low, close
        FROM bars
        WHERE source='amarkets_mt5' AND symbol='XAUUSD' AND timeframe=?
        ORDER BY utc_time
        """,
        (tf,),
    ).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([dict(r) for r in rows])
    df["utc_time"] = pd.to_datetime(df["utc_time"], utc=True, errors="coerce")
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["utc_time", "open", "high", "low", "close"]).sort_values("utc_time").drop_duplicates("utc_time").set_index("utc_time")


def resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    if df.empty:
        return df
    return df.resample(rule, label="right", closed="right").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna()


def load_m15(conn: sqlite3.Connection) -> Tuple[pd.DataFrame, str]:
    m1 = load_bars(conn, "1m")
    if len(m1) > 1000:
        return resample_ohlc(m1, "15min"), "m1_to_m15"
    m5 = load_bars(conn, "5m")
    if len(m5) > 1000:
        return resample_ohlc(m5, "15min"), "m5_to_m15"
    m15 = load_bars(conn, "15m")
    if len(m15) > 500:
        return m15, "m15"
    h1 = load_bars(conn, "1h")
    if len(h1) > 500:
        return h1, "h1_fallback"
    raise RuntimeError("No usable 1m/5m/15m/h1 bars found.")


def detect_date_col(cols: Sequence[str]) -> Optional[str]:
    preferred = ["date", "dt", "datetime", "timestamp", "utc_time", "_date"]
    nmap = {normalize_col(c): c for c in cols}
    for p in preferred:
        if p in nmap:
            return nmap[p]
    for c in cols:
        n = normalize_col(c)
        if "date" in n or "time" in n:
            return c
    return None


def detect_real_yield_col(cols: Sequence[str]) -> Optional[str]:
    nmap = {normalize_col(c): c for c in cols}
    preferred = [
        "real_yield_10y",
        "dfii10",
        "real_yield",
        "real_yield_5d",
    ]
    for p in preferred:
        if p in nmap:
            return nmap[p]
    # avoid delta columns when possible, but fall back if needed
    for c in cols:
        n = normalize_col(c)
        if "real" in n and "yield" in n and "10" in n and not n.startswith("d_"):
            return c
    for c in cols:
        n = normalize_col(c)
        if "dfii10" in n:
            return c
    return None


def load_macro_real_yield(conn: sqlite3.Connection) -> Tuple[pd.DataFrame, Dict]:
    """
    Prefer macro_daily_regime.real_yield_10y; fall back to macro_numeric_observations.DFII10-like data.
    """
    audit = {
        "macro_source": None,
        "date_col": None,
        "real_yield_col": None,
        "rows": 0,
        "status": "missing",
        "reason": "",
    }

    # Wide daily regime table is preferred.
    if table_exists(conn, "macro_daily_regime"):
        df = pd.read_sql_query("SELECT * FROM macro_daily_regime ORDER BY 1", conn)
        date_col = detect_date_col(df.columns)
        ry_col = detect_real_yield_col(df.columns)
        if date_col and ry_col:
            out = pd.DataFrame({
                "dt": pd.to_datetime(df[date_col], utc=True, errors="coerce"),
                "real_yield_10y": pd.to_numeric(df[ry_col], errors="coerce"),
            }).dropna()
            if len(out) >= 10:
                out = out.sort_values("dt").drop_duplicates("dt", keep="last")
                out["real_yield_10y_chg5"] = out["real_yield_10y"] - out["real_yield_10y"].shift(5)
                audit.update({
                    "macro_source": "macro_daily_regime",
                    "date_col": date_col,
                    "real_yield_col": ry_col,
                    "rows": int(len(out)),
                    "status": "loaded",
                    "reason": "preferred_daily_regime",
                })
                return out.dropna(subset=["real_yield_10y_chg5"]), audit

    # Long/observations fallback.
    if table_exists(conn, "macro_numeric_observations"):
        df = pd.read_sql_query("SELECT * FROM macro_numeric_observations ORDER BY 1", conn)
        date_col = detect_date_col(df.columns)
        nmap = {normalize_col(c): c for c in df.columns}
        # Common long format: date, series_id, value
        series_col = None
        value_col = None
        for c in df.columns:
            if normalize_col(c) in {"series_id", "series", "symbol", "indicator"}:
                series_col = c
            if normalize_col(c) in {"value", "observation", "numeric_value"}:
                value_col = c
        if date_col and series_col and value_col:
            sub = df[df[series_col].astype(str).str.upper().str.contains("DFII10|REAL", regex=True, na=False)].copy()
            if not sub.empty:
                out = pd.DataFrame({
                    "dt": pd.to_datetime(sub[date_col], utc=True, errors="coerce"),
                    "real_yield_10y": pd.to_numeric(sub[value_col], errors="coerce"),
                }).dropna()
                if len(out) >= 10:
                    out = out.sort_values("dt").drop_duplicates("dt", keep="last")
                    out["real_yield_10y_chg5"] = out["real_yield_10y"] - out["real_yield_10y"].shift(5)
                    audit.update({
                        "macro_source": "macro_numeric_observations",
                        "date_col": date_col,
                        "real_yield_col": value_col,
                        "rows": int(len(out)),
                        "status": "loaded",
                        "reason": "fallback_numeric_observations",
                    })
                    return out.dropna(subset=["real_yield_10y_chg5"]), audit

        # Common wide format fallback.
        ry_col = detect_real_yield_col(df.columns)
        if date_col and ry_col:
            out = pd.DataFrame({
                "dt": pd.to_datetime(df[date_col], utc=True, errors="coerce"),
                "real_yield_10y": pd.to_numeric(df[ry_col], errors="coerce"),
            }).dropna()
            if len(out) >= 10:
                out = out.sort_values("dt").drop_duplicates("dt", keep="last")
                out["real_yield_10y_chg5"] = out["real_yield_10y"] - out["real_yield_10y"].shift(5)
                audit.update({
                    "macro_source": "macro_numeric_observations_wide",
                    "date_col": date_col,
                    "real_yield_col": ry_col,
                    "rows": int(len(out)),
                    "status": "loaded",
                    "reason": "fallback_wide_numeric_observations",
                })
                return out.dropna(subset=["real_yield_10y_chg5"]), audit

    audit["reason"] = "No usable real-yield series found."
    return pd.DataFrame(), audit


def previous_day_levels(m15: pd.DataFrame) -> pd.DataFrame:
    daily = resample_ohlc(m15, "1D")
    rows = []
    days = list(daily.index.strftime("%Y-%m-%d"))
    for i, day in enumerate(days):
        if i == 0:
            continue
        prev = daily.iloc[i - 1]
        rows.append({"day": day, "pdh": float(prev["high"]), "pdl": float(prev["low"])})
    return pd.DataFrame(rows)


def attach_macro(m15_events: pd.DataFrame, macro: pd.DataFrame) -> pd.DataFrame:
    if macro.empty:
        x = m15_events.copy()
        x["real_yield_10y"] = float("nan")
        x["real_yield_10y_chg5"] = float("nan")
        x["macro_real_yield_up"] = False
        return x
    left = m15_events.sort_values("event_utc").copy()
    right = macro.sort_values("dt").copy()
    out = pd.merge_asof(left, right, left_on="event_utc", right_on="dt", direction="backward")
    out["macro_real_yield_up"] = pd.to_numeric(out["real_yield_10y_chg5"], errors="coerce") > 0
    return out


def scan_signals(
    m15: pd.DataFrame,
    macro: pd.DataFrame,
    scan_days: int,
    sweep_depth_min: float,
    reclaim_max: float,
    buffer_usd: float,
) -> pd.DataFrame:
    x = m15.copy()
    if scan_days > 0:
        cutoff = x.index.max() - pd.Timedelta(days=scan_days)
        x = x[x.index >= cutoff].copy()

    levels = previous_day_levels(m15)
    if levels.empty or x.empty:
        return pd.DataFrame()

    x["day"] = x.index.strftime("%Y-%m-%d")
    x = x.reset_index().rename(columns={"utc_time": "event_utc"})
    # If index name is not utc_time, after reset it may be named "index".
    if "event_utc" not in x.columns:
        x = x.rename(columns={x.columns[0]: "event_utc"})

    x = x.merge(levels, on="day", how="left")
    x = x.dropna(subset=["pdl"])
    x["sweep_depth"] = x["pdl"] - x["low"]
    x["reclaim_above_pdl"] = x["close"] - x["pdl"]
    x["raw_prev_day_low_sweep_reclaim"] = (
        (x["low"] < x["pdl"] - buffer_usd)
        & (x["close"] > x["pdl"])
    )
    x["tech_condition"] = (
        x["raw_prev_day_low_sweep_reclaim"]
        & (x["sweep_depth"] >= sweep_depth_min)
        & (x["reclaim_above_pdl"] >= 0)
        & (x["reclaim_above_pdl"] < reclaim_max)
    )

    candidates = x[x["tech_condition"]].copy()
    if candidates.empty:
        return candidates

    candidates = attach_macro(candidates, macro)
    candidates["stage16a_signal"] = candidates["tech_condition"] & candidates["macro_real_yield_up"]
    candidates["research_side"] = "LONG"
    candidates["interpretation"] = "macro_pressure_reversal"
    candidates["authorization"] = "RESEARCH_SHADOW_ONLY_NO_ORDER"
    candidates["next_bar_theoretical_entry_utc"] = candidates["event_utc"] + pd.Timedelta(minutes=15)
    candidates["time_exit_target_utc"] = candidates["next_bar_theoretical_entry_utc"] + pd.Timedelta(minutes=60)

    cols = [
        "event_utc", "next_bar_theoretical_entry_utc", "time_exit_target_utc",
        "research_side", "stage16a_signal", "open", "high", "low", "close",
        "pdl", "sweep_depth", "reclaim_above_pdl",
        "real_yield_10y", "real_yield_10y_chg5", "macro_real_yield_up",
        "interpretation", "authorization",
    ]
    return candidates[[c for c in cols if c in candidates.columns]].sort_values("event_utc")


def latest_status(m15: pd.DataFrame, signals: pd.DataFrame, scan_days: int) -> Dict:
    latest_bar = m15.index.max() if not m15.empty else None
    if signals.empty:
        return {
            "latest_bar_utc": latest_bar.isoformat() if latest_bar is not None else None,
            "latest_signal_status": "NO_STAGE16A_SIGNAL_IN_SCAN_WINDOW",
            "latest_signal_utc": None,
            "bars_since_latest_signal": None,
            "scan_days": int(scan_days),
        }

    latest_signal = pd.to_datetime(signals["event_utc"], utc=True).max()
    # m15 bars are 15min labels; compute approximate bar distance.
    bars_since = None
    if latest_bar is not None and pd.notna(latest_signal):
        bars_since = int(max(0, round((latest_bar - latest_signal) / pd.Timedelta(minutes=15))))

    status = "SIGNAL_ON_LATEST_COMPLETED_BAR" if latest_bar == latest_signal else "HISTORICAL_SIGNAL_IN_SCAN_WINDOW"
    return {
        "latest_bar_utc": latest_bar.isoformat() if latest_bar is not None else None,
        "latest_signal_status": status,
        "latest_signal_utc": latest_signal.isoformat() if pd.notna(latest_signal) else None,
        "bars_since_latest_signal": bars_since,
        "scan_days": int(scan_days),
    }


def run(
    db: Path,
    out_dir: Path,
    scan_days: int,
    sweep_depth_min: float,
    reclaim_max: float,
    buffer_usd: float,
) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = now_iso()

    conn = connect(db)
    try:
        m15, intraday_source = load_m15(conn)
        macro, macro_audit = load_macro_real_yield(conn)
    finally:
        conn.close()

    signals_all_tech = scan_signals(
        m15=m15,
        macro=macro,
        scan_days=scan_days,
        sweep_depth_min=sweep_depth_min,
        reclaim_max=reclaim_max,
        buffer_usd=buffer_usd,
    )

    if signals_all_tech.empty:
        signals = signals_all_tech
        tech_count = 0
        macro_pass_count = 0
    else:
        tech_count = int(len(signals_all_tech))
        signals = signals_all_tech[signals_all_tech["stage16a_signal"] == True].copy()
        macro_pass_count = int(len(signals))

    status = latest_status(m15, signals, scan_days)

    signal_csv = out_dir / "stage16a_shadow_signals.csv"
    tech_csv = out_dir / "stage16a_technical_candidates_before_macro.csv"
    json_path = out_dir / "stage16a_macro_pressure_reversal_shadow_monitor.json"
    md_path = out_dir / "stage16a_macro_pressure_reversal_shadow_monitor.md"

    signals.to_csv(signal_csv, index=False)
    signals_all_tech.to_csv(tech_csv, index=False)

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "inputs": {
            "db": str(db),
            "scan_days": int(scan_days),
            "sweep_depth_min": float(sweep_depth_min),
            "reclaim_max": float(reclaim_max),
            "buffer_usd": float(buffer_usd),
        },
        "source": {
            "intraday_source": intraday_source,
            "m15_rows": int(len(m15)),
            "m15_first": m15.index.min().isoformat() if not m15.empty else None,
            "m15_last": m15.index.max().isoformat() if not m15.empty else None,
            "macro_audit": macro_audit,
            "macro_rows": int(len(macro)),
        },
        "counts": {
            "technical_candidates": tech_count,
            "stage16a_macro_pressure_reversal_signals": macro_pass_count,
        },
        "status": status,
        "latest_signal": signals.tail(1).to_dict(orient="records") if not signals.empty else [],
        "authorization_flags": {
            "trade_authorization": False,
            "ea_change_authorization": False,
            "paper_order_authorization": False,
            "live_order_authorization": False,
            "automatic_trading": False,
        },
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    lines = [
        "# Stage 16A Macro Pressure/Reversal Forward-Shadow Monitor",
        "",
        f"Generated UTC: `{generated}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: research shadow only. No EA change, no automatic trading, no paper/live authorization.",
        "",
        "## Research setup",
        "- setup: `prev_day_low_sweep_rejection`",
        "- side: `LONG` research direction",
        "- branch: `sweep_depth_ge_q50`",
        "- regime: `reclaim_lt_q50`",
        "- macro context: `real_yield_10y_chg5_up`",
        "- interpretation: `pressure/reversal`, not classic bullish macro support",
        "",
        "## Inputs",
        f"- db: `{db}`",
        f"- intraday_source: `{intraday_source}`",
        f"- m15_rows: `{len(m15)}`",
        f"- scan_days: `{scan_days}`",
        f"- sweep_depth_min: `{sweep_depth_min}`",
        f"- reclaim_max: `{reclaim_max}`",
        f"- buffer_usd: `{buffer_usd}`",
        "",
        "## Macro availability",
        f"- macro_status: `{macro_audit.get('status')}`",
        f"- macro_source: `{macro_audit.get('macro_source')}`",
        f"- real_yield_col: `{macro_audit.get('real_yield_col')}`",
        f"- macro_rows: `{len(macro)}`",
        f"- reason: `{macro_audit.get('reason')}`",
        "",
        "## Shadow status",
        f"- latest_bar_utc: `{status['latest_bar_utc']}`",
        f"- latest_signal_status: `{status['latest_signal_status']}`",
        f"- latest_signal_utc: `{status['latest_signal_utc']}`",
        f"- bars_since_latest_signal: `{status['bars_since_latest_signal']}`",
        "",
        "## Counts",
        f"- technical_candidates_before_macro: `{tech_count}`",
        f"- stage16a_macro_pressure_reversal_signals: `{macro_pass_count}`",
        "",
        "## Latest signal",
    ]

    if not signals.empty:
        last = signals.tail(1).iloc[0].to_dict()
        for k in [
            "event_utc", "next_bar_theoretical_entry_utc", "time_exit_target_utc",
            "sweep_depth", "reclaim_above_pdl", "real_yield_10y",
            "real_yield_10y_chg5", "authorization",
        ]:
            lines.append(f"- {k}: `{last.get(k)}`")
    else:
        lines.append("- none")

    lines += [
        "",
        "## Interpretation rules",
        "- This monitor can only create research shadow records.",
        "- A signal here means: the validated research setup condition exists in data.",
        "- It does not mean enter a trade.",
        "- It does not authorize EA/paper/live orders.",
        "- If the latest signal is historical, do not chase it.",
        "",
        "## Output files",
        f"- signal_csv: `{signal_csv}`",
        f"- technical_candidates_csv: `{tech_csv}`",
        f"- json: `{json_path}`",
        f"- md: `{md_path}`",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 16A macro pressure/reversal shadow monitor: DONE")
    print(f"latest_signal_status={status['latest_signal_status']}")
    print(f"technical_candidates={tech_count} stage16a_signals={macro_pass_count}")
    print(f"Report: {md_path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--scan-days", type=int, default=30)
    p.add_argument("--sweep-depth-min", type=float, default=1.62)
    p.add_argument("--reclaim-max", type=float, default=1.55)
    p.add_argument("--buffer-usd", type=float, default=0.2)
    args = p.parse_args()

    return run(
        db=Path(args.db),
        out_dir=Path(args.out_dir),
        scan_days=int(args.scan_days),
        sweep_depth_min=float(args.sweep_depth_min),
        reclaim_max=float(args.reclaim_max),
        buffer_usd=float(args.buffer_usd),
    )


if __name__ == "__main__":
    raise SystemExit(main())
