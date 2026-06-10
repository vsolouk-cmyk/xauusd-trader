#!/usr/bin/env python3
"""
Stage 11B v2 — Alternative Short Thesis Lab, Fast Grid

Why v2:
- v1 created a very large grid (~23k variants) and recomputed rolling/H4 features per variant.
- On an older MacBook this can take many hours.
- v2 precomputes common features once and uses a smaller default "fast" grid.

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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Sequence

import pandas as pd


TOOL_VERSION = "v2_fast_grid"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_OUT_DIR = Path("data/reports/stage11b_alternative_short_thesis_lab")


@dataclass(frozen=True)
class Variant:
    definition: str
    h4_sma: int
    h4_slope_lookback: int
    h1_lookback: int
    compression_lookback: int
    compression_max_atr: float
    rejection_lookback: int
    impulse_atr_mult: float
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
    return df.set_index("utc_time")


def resample_h4(h1: pd.DataFrame) -> pd.DataFrame:
    return h1.resample("4h", label="right", closed="right").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    }).dropna()


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        (df["high"] - df["low"]).abs(),
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=n).mean()


def session_mask(index: pd.DatetimeIndex, session_filter: str) -> pd.Series:
    hours = pd.Series(index.hour, index=index)
    if session_filter == "all":
        return pd.Series(True, index=index)
    if session_filter == "no_asia":
        return (hours >= 7) & (hours <= 21)
    if session_filter == "london":
        return (hours >= 7) & (hours <= 12)
    if session_filter == "london_ny":
        return (hours >= 7) & (hours <= 20)
    if session_filter == "ny_only":
        return (hours >= 13) & (hours <= 20)
    return pd.Series(True, index=index)


def precompute_features(h1: pd.DataFrame, h4: pd.DataFrame) -> Dict[str, object]:
    idx = h1.index
    base = pd.DataFrame(index=idx)
    base["atr14"] = atr(h1, 14)
    base["body"] = h1["close"] - h1["open"]
    base["bearish_body"] = (base["body"] < 0)
    base["lower_close"] = (h1["close"] < h1["close"].shift(1))

    lookbacks = [6, 12, 18]
    comp_lbs = [6, 12]
    rejection_lbs = [6, 12, 18]
    impulse_mults = [0.8, 1.2, 1.6]
    h4_smas = [10, 20]
    h4_slopes = [2, 3]
    sessions = ["all", "no_asia", "london", "london_ny", "ny_only"]

    prev_lows = {lb: h1["low"].rolling(lb).min().shift(1) for lb in lookbacks}
    breakdown = {lb: (h1["close"] < prev_lows[lb]).fillna(False).astype(bool) for lb in lookbacks}

    comp_ok = {}
    for lb in comp_lbs:
        range_n = h1["high"].rolling(lb).max() - h1["low"].rolling(lb).min()
        ratio = range_n / base["atr14"]
        for mx in [1.4, 1.8, 2.2, 2.8]:
            comp_ok[(lb, mx)] = (ratio <= mx).fillna(False).astype(bool)

    near_upper = {}
    bearish_reject = {}
    for lb in rejection_lbs:
        local_high = h1["high"].rolling(lb).max().shift(1)
        local_low = h1["low"].rolling(lb).min().shift(1)
        pos = (h1["close"] - local_low) / (local_high - local_low)
        near_upper[lb] = (pos >= 0.65).fillna(False).astype(bool)
        bearish_reject[lb] = ((h1["high"] >= local_high * 0.998) & (h1["close"] < h1["open"]) & (h1["close"] < h1["close"].shift(1))).fillna(False).astype(bool)

    bearish_impulse = {}
    for lb in lookbacks:
        for mult in impulse_mults:
            bearish_impulse[(lb, mult)] = (((h1["open"] - h1["close"]) >= mult * base["atr14"]) & breakdown[lb]).fillna(False).astype(bool)

    h4_states = {}
    for sma in h4_smas:
        for slope_lb in h4_slopes:
            h4f = h4.copy()
            h4f["h4_sma"] = h4f["close"].rolling(sma, min_periods=sma).mean()
            h4f["h4_sma_slope"] = h4f["h4_sma"] - h4f["h4_sma"].shift(slope_lb)
            h4_down = ((h4f["close"] < h4f["h4_sma"]) & (h4f["h4_sma_slope"] < 0)).astype(bool)
            h4_neutral_or_down = ((h4f["close"] <= h4f["h4_sma"] * 1.002) | (h4f["h4_sma_slope"] <= 0)).astype(bool)
            h4_states[(sma, slope_lb, "down")] = h4_down.reindex(idx, method="ffill").fillna(False).astype(bool)
            h4_states[(sma, slope_lb, "neutral_or_down")] = h4_neutral_or_down.reindex(idx, method="ffill").fillna(False).astype(bool)

    session_masks = {s: session_mask(idx, s).fillna(False).astype(bool) for s in sessions}

    return {
        "base": base,
        "breakdown": breakdown,
        "comp_ok": comp_ok,
        "near_upper": near_upper,
        "bearish_reject": bearish_reject,
        "bearish_impulse": bearish_impulse,
        "h4_states": h4_states,
        "session_masks": session_masks,
    }


def variant_name(v: Variant) -> str:
    return (
        f"{v.definition}_h4sma{v.h4_sma}_slope{v.h4_slope_lookback}_"
        f"look{v.h1_lookback}_comp{v.compression_lookback}_{v.compression_max_atr}_"
        f"rej{v.rejection_lookback}_imp{v.impulse_atr_mult}_h{v.exit_h}_cool{v.cooldown_h}_{v.session_filter}"
    )


def build_signal(v: Variant, pc: Dict[str, object]) -> pd.Series:
    base = pc["base"]
    breakdown = pc["breakdown"]
    comp_ok = pc["comp_ok"]
    near_upper = pc["near_upper"]
    bearish_reject = pc["bearish_reject"]
    bearish_impulse = pc["bearish_impulse"]
    h4_states = pc["h4_states"]
    session_masks = pc["session_masks"]

    h4_down = h4_states[(v.h4_sma, v.h4_slope_lookback, "down")]
    h4_neutral_or_down = h4_states[(v.h4_sma, v.h4_slope_lookback, "neutral_or_down")]
    sess = session_masks[v.session_filter]

    if v.definition == "short_compression_breakdown":
        sig = (
            h4_neutral_or_down
            & comp_ok[(v.compression_lookback, v.compression_max_atr)]
            & breakdown[v.h1_lookback]
            & base["bearish_body"]
            & sess
        )
    elif v.definition == "short_rally_rejection":
        sig = (
            h4_down
            & near_upper[v.rejection_lookback]
            & bearish_reject[v.rejection_lookback]
            & sess
        )
    elif v.definition == "short_bearish_impulse_after_compression":
        sig = (
            h4_neutral_or_down
            & comp_ok[(v.compression_lookback, v.compression_max_atr)]
            & bearish_impulse[(v.h1_lookback, v.impulse_atr_mult)]
            & sess
        )
    else:
        sig = pd.Series(False, index=base.index)

    return sig.fillna(False).astype(bool)


def simulate_variant(h1: pd.DataFrame, signal: pd.Series, v: Variant, unit_multiplier: float = 4.0, cost_per_unit: float = 0.35) -> List[dict]:
    rows = []
    times = list(h1.index)
    last_exit_idx = -10**9
    signal_positions = signal[signal].index

    for ts in signal_positions:
        i = h1.index.get_loc(ts)
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

        window = h1.iloc[entry_i:exit_i + 1]
        stop_hit = window[window["high"] >= entry_price + v.emergency_stop_usd]
        if not stop_hit.empty:
            stop_ts = stop_hit.index[0]
            exit_ts = stop_ts
            exit_price = entry_price + v.emergency_stop_usd
            exit_i = h1.index.get_loc(stop_ts)
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
            "h1_lookback": v.h1_lookback,
            "compression_lookback": v.compression_lookback,
            "compression_max_atr": v.compression_max_atr,
            "rejection_lookback": v.rejection_lookback,
            "impulse_atr_mult": v.impulse_atr_mult,
            "cooldown_h": v.cooldown_h,
            "exit_h": v.exit_h,
            "session_filter": v.session_filter,
        })
        last_exit_idx = exit_i

    return rows


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
    df["year"] = df["entry_dt"].dt.year.astype(int)
    q = df["entry_dt"].dt.quarter.astype(int)
    df["quarter"] = df["entry_dt"].dt.year.astype(str) + "Q" + q.astype(str)

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


def build_variants(mode: str) -> List[Variant]:
    if mode == "full":
        h4_smas = [10, 20]
        slope_lbs = [2, 3]
        lookbacks = [6, 12, 18]
        comp_lbs = [6, 12]
        comp_maxs = [1.4, 1.8, 2.2, 2.8]
        rejection_lbs = [6, 12, 18]
        impulse_mults = [0.8, 1.2, 1.6]
        exit_hs = [3, 6, 12]
        cooldowns = [1, 4]
        sessions = ["all", "no_asia", "london", "london_ny", "ny_only"]
    else:
        h4_smas = [10, 20]
        slope_lbs = [3]
        lookbacks = [6, 12]
        comp_lbs = [6]
        comp_maxs = [1.8, 2.2]
        rejection_lbs = [6, 12]
        impulse_mults = [1.2]
        exit_hs = [3, 6, 12]
        cooldowns = [1, 4]
        sessions = ["all", "no_asia", "ny_only"]

    variants: List[Variant] = []

    # 1) Compression breakdown.
    for h4_sma in h4_smas:
        for slope_lb in slope_lbs:
            for lookback in lookbacks:
                for comp_lb in comp_lbs:
                    for comp_max in comp_maxs:
                        for exit_h in exit_hs:
                            for cool in cooldowns:
                                for sess in sessions:
                                    variants.append(Variant(
                                        "short_compression_breakdown", h4_sma, slope_lb, lookback,
                                        comp_lb, comp_max, 6, 1.2, cool, exit_h, 30.0, sess
                                    ))

    # 2) Rally rejection.
    for h4_sma in h4_smas:
        for slope_lb in slope_lbs:
            for rej_lb in rejection_lbs:
                for exit_h in exit_hs:
                    for cool in cooldowns:
                        for sess in sessions:
                            variants.append(Variant(
                                "short_rally_rejection", h4_sma, slope_lb, 12,
                                6, 1.8, rej_lb, 1.2, cool, exit_h, 30.0, sess
                            ))

    # 3) Bearish impulse after compression.
    for h4_sma in h4_smas:
        for slope_lb in slope_lbs:
            for lookback in lookbacks:
                for comp_lb in comp_lbs:
                    for comp_max in comp_maxs:
                        for imp in impulse_mults:
                            for exit_h in exit_hs:
                                for cool in cooldowns:
                                    for sess in sessions:
                                        variants.append(Variant(
                                            "short_bearish_impulse_after_compression", h4_sma, slope_lb, lookback,
                                            comp_lb, comp_max, 6, imp, cool, exit_h, 30.0, sess
                                        ))

    return variants


def robust_flag(s: dict) -> bool:
    return (
        s["trades"] >= 40
        and s["total_x4"] > 0
        and s["test_total_x4"] > 0
        and s["pf_x4"] >= 1.18
        and s["median_x4"] >= -2.0
        and s["pos_years"] >= max(1, int(0.60 * s["years"]))
        and s["pos_quarters"] >= max(1, int(0.55 * s["quarters"]))
        and s["dd_x4"] > -550
    )


def run(db_path: Path, out_dir: Path, mode: str, progress_every: int) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = now_iso()

    conn = connect_db(db_path)
    h1 = load_h1(conn)
    conn.close()
    h4 = resample_h4(h1)

    variants = build_variants(mode)
    print(f"Stage 11B v2: mode={mode} variants={len(variants)} h1_rows={len(h1)} h4_rows={len(h4)}")
    print("Stage 11B v2: precomputing shared features...")
    pc = precompute_features(h1, h4)
    print("Stage 11B v2: feature cache ready.")

    summaries = []
    all_trades = []

    for n, v in enumerate(variants, start=1):
        signal = build_signal(v, pc)
        trades = simulate_variant(h1, signal, v)
        s = summarize_trades(trades, h1)
        s.update({
            "definition": v.definition,
            "direction": "SHORT",
            "guard_variant": "nonoverlap",
            "geometry": f"time_exit_{v.exit_h}h_stop{v.emergency_stop_usd}",
            "variant": variant_name(v),
            "h4_sma": v.h4_sma,
            "h4_slope_lookback": v.h4_slope_lookback,
            "h1_lookback": v.h1_lookback,
            "compression_lookback": v.compression_lookback,
            "compression_max_atr": v.compression_max_atr,
            "rejection_lookback": v.rejection_lookback,
            "impulse_atr_mult": v.impulse_atr_mult,
            "cooldown_h": v.cooldown_h,
            "exit_h": v.exit_h,
            "session_filter": v.session_filter,
        })
        s["robust_candidate"] = robust_flag(s)
        summaries.append(s)
        all_trades.extend(trades)

        if progress_every > 0 and (n % progress_every == 0 or n == len(variants)):
            print(f"Stage 11B progress: {n}/{len(variants)} variants")

    summary_df = pd.DataFrame(summaries)
    if not summary_df.empty:
        summary_df = summary_df.sort_values(
            ["robust_candidate", "test_total_x4", "pf_x4", "median_x4", "total_x4", "trades"],
            ascending=[False, False, False, False, False, False],
        )
    trades_df = pd.DataFrame(all_trades)

    summary_path = out_dir / "stage11b_short_candidate_summary.csv"
    trades_path = out_dir / "stage11b_short_candidate_trades.csv"
    summary_df.to_csv(summary_path, index=False)
    trades_df.to_csv(trades_path, index=False)

    robust_count = int(summary_df["robust_candidate"].sum()) if not summary_df.empty else 0
    top = summary_df.head(12).to_dict(orient="records") if not summary_df.empty else []
    decision = "short_candidate_found" if robust_count > 0 else "no_short_candidate_yet"

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "mode": mode,
        "db_path": str(db_path),
        "h1_rows": int(len(h1)),
        "h4_rows": int(len(h4)),
        "variants_tested": int(len(summary_df)),
        "trades_generated": int(len(trades_df)),
        "robust_candidate_count": robust_count,
        "decision": decision,
        "top": top[:5],
    }
    (out_dir / "stage11b_alternative_short_thesis_lab.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    lines = [
        "# Stage 11B Alternative Short Thesis Lab",
        "",
        f"Generated UTC: `{generated}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: research only. No EA change, no automatic trading, no paper/live authorization.",
        "",
        "## Inputs",
        f"- db: `{db_path}`",
        f"- mode: `{mode}`",
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
        "| Rank | Definition | Variant | Trades | Total x4 | Test x4 | PF | WR | Median | DD | Pos years | Pos quarters | Robust |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    if top:
        for i, r in enumerate(top, start=1):
            lines.append(
                f"| {i} | {r['definition']} | {r['variant']} | {r['trades']} | {r['total_x4']} | {r['test_total_x4']} | "
                f"{r['pf_x4']} | {r['wr']} | {r['median_x4']} | {r['dd_x4']} | "
                f"{r['pos_years']}/{r['years']} | {r['pos_quarters']}/{r['quarters']} | {r['robust_candidate']} |"
            )
    else:
        lines.append("| 0 | none | none | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | False |")

    lines += [
        "",
        "## Interpretation",
        "- Stage 11B v2 uses a cached fast grid by default.",
        "- If `mode=fast` finds a promising candidate, run strict robustness next.",
        "- If no candidate appears, do not run full-grid automatically on the MacBook.",
        "",
        "## Outputs",
        f"- summary_csv: `{summary_path}`",
        f"- trades_csv: `{trades_path}`",
        f"- json: `{out_dir / 'stage11b_alternative_short_thesis_lab.json'}`",
    ]
    (out_dir / "stage11b_alternative_short_thesis_lab.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 11B alternative short thesis lab: DONE")
    print(f"decision={decision} mode={mode} variants={len(summary_df)} trades={len(trades_df)} robust_candidates={robust_count}")
    print(f"Report: {out_dir / 'stage11b_alternative_short_thesis_lab.md'}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--mode", default="fast", choices=["fast", "full"])
    p.add_argument("--progress-every", type=int, default=100)
    args = p.parse_args()
    return run(Path(args.db), Path(args.out_dir), args.mode, args.progress_every)


if __name__ == "__main__":
    raise SystemExit(main())
