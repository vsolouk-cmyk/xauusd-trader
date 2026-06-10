#!/usr/bin/env python3
"""
Stage 11A — Downtrend Short-Side Thesis Lab

Purpose:
- Build/test a short-side counterpart to the selected long-only Stage 8D thesis.
- Focus on H4 downtrend + H1 compression/liquidity continuation.
- Research only. No EA change, no order logic.

Inputs:
- SQLite DB:
  data/local/xauusd_local_store.sqlite
- bars table:
  source='amarkets_mt5', symbol='XAUUSD', timeframe='1h'

Outputs:
- data/reports/stage11a_downtrend_short_thesis_lab/stage11a_downtrend_short_thesis_lab.md
- data/reports/stage11a_downtrend_short_thesis_lab/stage11a_short_candidate_summary.csv
- data/reports/stage11a_downtrend_short_thesis_lab/stage11a_short_candidate_trades.csv
- data/reports/stage11a_downtrend_short_thesis_lab/stage11a_downtrend_short_thesis_lab.json

Hard rules:
- Research only.
- No EA change.
- No automatic trading.
- No demo/paper/live/order authorization.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd


TOOL_VERSION = "v1"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_OUT_DIR = Path("data/reports/stage11a_downtrend_short_thesis_lab")


@dataclass
class Variant:
    definition: str
    h4_sma: int
    h4_slope_lookback: int
    h1_break_lookback: int
    compression_lookback: int
    compression_max_atr: float
    cooldown_h: int
    exit_h: int
    emergency_stop_usd: float
    session_filter: str


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect_db(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(f"DB not found: {path}")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def load_h1(conn: sqlite3.Connection) -> pd.DataFrame:
    rows = conn.execute("""
        SELECT utc_time, open, high, low, close
        FROM bars
        WHERE source='amarkets_mt5' AND symbol='XAUUSD' AND timeframe='1h'
        ORDER BY utc_time ASC
    """).fetchall()
    if not rows:
        raise RuntimeError("No AMarkets MT5 H1 bars found in bars table.")
    df = pd.DataFrame([dict(r) for r in rows])
    df["utc_time"] = pd.to_datetime(df["utc_time"], utc=True)
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["utc_time", "open", "high", "low", "close"]).sort_values("utc_time").drop_duplicates("utc_time")
    df = df.set_index("utc_time")
    return df


def resample_h4(h1: pd.DataFrame) -> pd.DataFrame:
    h4 = h1.resample("4h", label="right", closed="right").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    }).dropna()
    return h4


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        (df["high"] - df["low"]).abs(),
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=n).mean()


def session_ok(ts: pd.Timestamp, session_filter: str) -> bool:
    h = int(ts.hour)
    if session_filter == "all":
        return True
    if session_filter == "no_asia":
        return 7 <= h <= 21
    if session_filter == "london_ny":
        return 7 <= h <= 20
    if session_filter == "ny_only":
        return 13 <= h <= 20
    return True


def build_features(h1: pd.DataFrame, h4: pd.DataFrame, v: Variant) -> pd.DataFrame:
    df = h1.copy()
    df["atr14"] = atr(df, 14)
    df["h1_range_n"] = df["high"].rolling(v.compression_lookback).max() - df["low"].rolling(v.compression_lookback).min()
    df["compression_ratio"] = df["h1_range_n"] / df["atr14"]

    df["prev_low_break"] = df["close"] < df["low"].rolling(v.h1_break_lookback).min().shift(1)
    df["lower_close"] = df["close"] < df["close"].shift(1)
    df["compression_ok"] = df["compression_ratio"] <= v.compression_max_atr

    h4f = h4.copy()
    h4f["h4_sma"] = h4f["close"].rolling(v.h4_sma, min_periods=v.h4_sma).mean()
    h4f["h4_sma_slope"] = h4f["h4_sma"] - h4f["h4_sma"].shift(v.h4_slope_lookback)
    h4f["h4_downtrend"] = (h4f["close"] < h4f["h4_sma"]) & (h4f["h4_sma_slope"] < 0)

    # Use last closed H4 value available at each H1 timestamp.
    h4_state = h4f[["h4_downtrend", "h4_sma", "h4_sma_slope"]].reindex(df.index, method="ffill")
    df = df.join(h4_state)
    df["session_ok"] = [session_ok(ts, v.session_filter) for ts in df.index]
    df["signal"] = (
        df["h4_downtrend"].fillna(False)
        & df["compression_ok"].fillna(False)
        & df["prev_low_break"].fillna(False)
        & df["lower_close"].fillna(False)
        & df["session_ok"].fillna(False)
    )
    return df


def simulate_variant(h1: pd.DataFrame, features: pd.DataFrame, v: Variant, unit_multiplier: float = 4.0, cost_per_unit: float = 0.35) -> List[dict]:
    rows = []
    times = list(features.index)
    idx_by_time = {t: i for i, t in enumerate(times)}
    last_exit_idx = -10**9

    for i, ts in enumerate(times):
        if not bool(features.iloc[i].get("signal", False)):
            continue
        if i <= last_exit_idx + v.cooldown_h:
            continue
        entry_i = i + 1
        exit_i = i + 1 + v.exit_h
        if exit_i >= len(h1):
            continue

        entry_ts = times[entry_i]
        entry_price = float(h1.iloc[entry_i]["open"])
        exit_ts = times[exit_i]
        exit_price = float(h1.iloc[exit_i]["close"])
        exit_reason = f"time_exit_{v.exit_h}h"

        # For short: adverse move is high above entry.
        window = h1.iloc[entry_i:exit_i + 1]
        stop_hit = window[window["high"] >= entry_price + v.emergency_stop_usd]
        if not stop_hit.empty:
            stop_ts = stop_hit.index[0]
            exit_ts = stop_ts
            exit_price = entry_price + v.emergency_stop_usd
            exit_i = idx_by_time.get(stop_ts, exit_i)
            exit_reason = f"emergency_stop_{v.emergency_stop_usd}"

        gross_per_unit = entry_price - exit_price
        net_x4 = gross_per_unit * unit_multiplier - cost_per_unit * unit_multiplier
        mfe = entry_price - float(window["low"].min())
        mae = float(window["high"].max()) - entry_price

        rows.append({
            "definition": v.definition,
            "direction": "SHORT",
            "guard_variant": "nonoverlap",
            "geometry": f"time_exit_{v.exit_h}h_stop{v.emergency_stop_usd}",
            "variant": variant_name(v),
            "signal_utc": ts.isoformat(),
            "entry_utc": entry_ts.isoformat(),
            "exit_utc": exit_ts.isoformat(),
            "entry_price": round(entry_price, 6),
            "exit_price": round(exit_price, 6),
            "exit_reason": exit_reason,
            "gross_per_unit": round(gross_per_unit, 6),
            "net_x4": round(net_x4, 6),
            "mfe_usd": round(mfe, 6),
            "mae_usd": round(mae, 6),
            "h4_sma": v.h4_sma,
            "h4_slope_lookback": v.h4_slope_lookback,
            "h1_break_lookback": v.h1_break_lookback,
            "compression_lookback": v.compression_lookback,
            "compression_max_atr": v.compression_max_atr,
            "cooldown_h": v.cooldown_h,
            "exit_h": v.exit_h,
            "session_filter": v.session_filter,
        })

        last_exit_idx = exit_i

    return rows


def variant_name(v: Variant) -> str:
    return (
        f"h4sma{v.h4_sma}_slope{v.h4_slope_lookback}_"
        f"break{v.h1_break_lookback}_comp{v.compression_lookback}_{v.compression_max_atr}_"
        f"cool{v.cooldown_h}_{v.session_filter}"
    )


def drawdown(vals: Sequence[float]) -> float:
    eq = 0.0
    peak = 0.0
    maxdd = 0.0
    for v in vals:
        eq += v
        peak = max(peak, eq)
        maxdd = min(maxdd, eq - peak)
    return round(maxdd, 6)


def pf(vals: Sequence[float]) -> float:
    wins = sum(v for v in vals if v > 0)
    losses = abs(sum(v for v in vals if v < 0))
    if losses == 0:
        return 999.0 if wins > 0 else 0.0
    return round(wins / losses, 6)


def summarize_trades(trades: List[dict], h1: pd.DataFrame) -> dict:
    if not trades:
        return {
            "trades": 0, "total_x4": 0.0, "median_x4": 0.0, "pf_x4": 0.0, "wr": 0.0,
            "dd_x4": 0.0, "train_total_x4": 0.0, "test_total_x4": 0.0,
            "pos_years": 0, "years": 0, "pos_quarters": 0, "quarters": 0,
        }
    vals = [float(t["net_x4"]) for t in trades]
    wins = [v for v in vals if v > 0]

    start = h1.index.min()
    end = h1.index.max()
    split_ts = start + (end - start) * 0.70

    train = [float(t["net_x4"]) for t in trades if pd.Timestamp(t["entry_utc"]) <= split_ts]
    test = [float(t["net_x4"]) for t in trades if pd.Timestamp(t["entry_utc"]) > split_ts]

    df = pd.DataFrame(trades)
    df["entry_dt"] = pd.to_datetime(df["entry_utc"], utc=True)
    df["year"] = df["entry_dt"].dt.year
    df["quarter"] = df["entry_dt"].dt.to_period("Q").astype(str)
    by_year = df.groupby("year")["net_x4"].sum()
    by_quarter = df.groupby("quarter")["net_x4"].sum()

    return {
        "trades": len(vals),
        "total_x4": round(sum(vals), 6),
        "median_x4": round(float(pd.Series(vals).median()), 6),
        "pf_x4": pf(vals),
        "wr": round(len(wins) / len(vals), 6),
        "dd_x4": drawdown(vals),
        "train_total_x4": round(sum(train), 6),
        "test_total_x4": round(sum(test), 6),
        "pos_years": int((by_year > 0).sum()),
        "years": int(len(by_year)),
        "pos_quarters": int((by_quarter > 0).sum()),
        "quarters": int(len(by_quarter)),
    }


def build_variants() -> List[Variant]:
    variants = []
    for h4_sma in [10, 20]:
        for slope_lb in [2, 3]:
            for break_lb in [6, 12, 18]:
                for comp_lb in [6, 12]:
                    for comp_max in [1.4, 1.8, 2.2]:
                        for cool in [1, 4]:
                            for sess in ["all", "no_asia", "london_ny", "ny_only"]:
                                variants.append(Variant(
                                    definition="h4_down_compression_liquidity_short_v1",
                                    h4_sma=h4_sma,
                                    h4_slope_lookback=slope_lb,
                                    h1_break_lookback=break_lb,
                                    compression_lookback=comp_lb,
                                    compression_max_atr=comp_max,
                                    cooldown_h=cool,
                                    exit_h=12,
                                    emergency_stop_usd=30.0,
                                    session_filter=sess,
                                ))
    return variants


def robust_flag(s: dict) -> bool:
    return (
        s["trades"] >= 40
        and s["total_x4"] > 0
        and s["test_total_x4"] > 0
        and s["pf_x4"] >= 1.15
        and s["pos_years"] >= max(1, int(0.60 * s["years"]))
        and s["pos_quarters"] >= max(1, int(0.55 * s["quarters"]))
        and s["dd_x4"] > -600
    )


def run(db_path: Path, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = now_iso()

    conn = connect_db(db_path)
    h1 = load_h1(conn)
    conn.close()
    h4 = resample_h4(h1)

    summaries = []
    all_trades = []
    for v in build_variants():
        features = build_features(h1, h4, v)
        trades = simulate_variant(h1, features, v)
        s = summarize_trades(trades, h1)
        s.update({
            "definition": v.definition,
            "direction": "SHORT",
            "guard_variant": "nonoverlap",
            "geometry": f"time_exit_{v.exit_h}h_stop{v.emergency_stop_usd}",
            "variant": variant_name(v),
            "h4_sma": v.h4_sma,
            "h4_slope_lookback": v.h4_slope_lookback,
            "h1_break_lookback": v.h1_break_lookback,
            "compression_lookback": v.compression_lookback,
            "compression_max_atr": v.compression_max_atr,
            "cooldown_h": v.cooldown_h,
            "session_filter": v.session_filter,
        })
        s["robust_candidate"] = robust_flag(s)
        summaries.append(s)
        all_trades.extend(trades)

    summary_df = pd.DataFrame(summaries)
    if not summary_df.empty:
        summary_df = summary_df.sort_values(
            ["robust_candidate", "test_total_x4", "pf_x4", "total_x4", "trades"],
            ascending=[False, False, False, False, False],
        )
    trades_df = pd.DataFrame(all_trades)

    summary_path = out_dir / "stage11a_short_candidate_summary.csv"
    trades_path = out_dir / "stage11a_short_candidate_trades.csv"
    summary_df.to_csv(summary_path, index=False)
    trades_df.to_csv(trades_path, index=False)

    robust_count = int(summary_df["robust_candidate"].sum()) if not summary_df.empty else 0
    top = summary_df.head(10).to_dict(orient="records") if not summary_df.empty else []
    decision = "short_candidate_found" if robust_count > 0 else "no_short_candidate_yet"

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "db_path": str(db_path),
        "h1_rows": int(len(h1)),
        "h4_rows": int(len(h4)),
        "variants_tested": int(len(summary_df)),
        "trades_generated": int(len(trades_df)),
        "robust_candidate_count": robust_count,
        "decision": decision,
        "top": top[:5],
    }
    (out_dir / "stage11a_downtrend_short_thesis_lab.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    lines = [
        "# Stage 11A Downtrend Short-Side Thesis Lab",
        "",
        f"Generated UTC: `{generated}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: research only. No EA change, no automatic trading, no paper/live authorization.",
        "",
        "## Inputs",
        f"- db: `{db_path}`",
        f"- h1_rows: `{len(h1)}`",
        f"- h4_rows: `{len(h4)}`",
        f"- variants_tested: `{len(summary_df)}`",
        f"- trades_generated: `{len(trades_df)}`",
        "",
        "## Decision",
        f"- decision: `{decision}`",
        f"- robust_candidate_count: `{robust_count}`",
        "",
        "## Top candidates",
        "| Rank | Variant | Trades | Total x4 | Test x4 | PF | WR | Median | DD | Pos years | Pos quarters | Robust |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    if top:
        for i, r in enumerate(top, start=1):
            lines.append(
                f"| {i} | {r['variant']} | {r['trades']} | {r['total_x4']} | {r['test_total_x4']} | "
                f"{r['pf_x4']} | {r['wr']} | {r['median_x4']} | {r['dd_x4']} | "
                f"{r['pos_years']}/{r['years']} | {r['pos_quarters']}/{r['quarters']} | {r['robust_candidate']} |"
            )
    else:
        lines.append("| 0 | none | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | False |")

    lines += [
        "",
        "## Interpretation",
        "- This lab tests a short-side counterpart to the long-only Stage 8D candidate.",
        "- A candidate is useful only if test-period performance is positive and robustness metrics are acceptable.",
        "- If no robust candidate appears, do not force a short EA; move to alternate short thesis geometry.",
        "",
        "## Outputs",
        f"- summary_csv: `{summary_path}`",
        f"- trades_csv: `{trades_path}`",
        f"- json: `{out_dir / 'stage11a_downtrend_short_thesis_lab.json'}`",
        "",
        "## Decision rule",
        "- `short_candidate_found` permits Stage 11B robustness/execution-replay research only.",
        "- It does not permit EA order code, paper order, or live execution.",
    ]
    (out_dir / "stage11a_downtrend_short_thesis_lab.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 11A downtrend short-side thesis lab: DONE")
    print(f"decision={decision} variants={len(summary_df)} trades={len(trades_df)} robust_candidates={robust_count}")
    print(f"Report: {out_dir / 'stage11a_downtrend_short_thesis_lab.md'}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = p.parse_args()
    return run(Path(args.db), Path(args.out_dir))


if __name__ == "__main__":
    raise SystemExit(main())
