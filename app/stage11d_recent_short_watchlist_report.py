#!/usr/bin/env python3
"""
Stage 11D — Recent Short Watchlist Report

Why:
- Stage 11A/11B found no robust all-history short candidate.
- Stage 11C classified several short_rally_rejection candidates as RECENT_REGIME_WATCHLIST_ONLY / SHORT_TERM_WATCHLIST_ONLY.
- These must not become EA rules, but can be monitored in forward-shadow reports.

Purpose:
- Build a report-only dashboard for recent short-watchlist candidates.
- Detect whether any watchlist candidate is active on the latest closed H1 bar.
- Show recent signal count and context for monitoring only.

Hard rules:
- Report/watchlist only.
- No EA change.
- No automatic trading.
- No paper/live/order authorization.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd


TOOL_VERSION = "v1"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_STAGE11B_SUMMARY = Path("data/reports/stage11b_alternative_short_thesis_lab/stage11b_short_candidate_summary.csv")
DEFAULT_STAGE11C_SUMMARY = Path("data/reports/stage11c_recent_short_regime_diagnostic/stage11c_recent_candidate_summary.csv")
DEFAULT_OUT_DIR = Path("data/reports/stage11d_recent_short_watchlist_report")


@dataclass(frozen=True)
class Variant:
    variant: str
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


def precompute(h1: pd.DataFrame, h4: pd.DataFrame) -> Dict[str, object]:
    idx = h1.index
    base = pd.DataFrame(index=idx)
    base["atr14"] = atr(h1, 14)
    base["body"] = h1["close"] - h1["open"]
    base["bearish_body"] = base["body"] < 0

    lookbacks = [6, 12, 18]
    comp_lbs = [6, 12]
    comp_maxs = [1.4, 1.8, 2.2, 2.8]
    rejection_lbs = [6, 12, 18]
    impulse_mults = [0.8, 1.2, 1.6]
    h4_smas = [10, 20]
    h4_slopes = [2, 3]
    sessions = ["all", "no_asia", "london", "london_ny", "ny_only"]

    breakdown = {}
    for lb in lookbacks:
        breakdown[lb] = (h1["close"] < h1["low"].rolling(lb).min().shift(1)).fillna(False).astype(bool)

    comp_ok = {}
    for lb in comp_lbs:
        range_n = h1["high"].rolling(lb).max() - h1["low"].rolling(lb).min()
        ratio = range_n / base["atr14"]
        for mx in comp_maxs:
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
        sig = h4_neutral_or_down & comp_ok[(v.compression_lookback, v.compression_max_atr)] & breakdown[v.h1_lookback] & base["bearish_body"] & sess
    elif v.definition == "short_rally_rejection":
        sig = h4_down & near_upper[v.rejection_lookback] & bearish_reject[v.rejection_lookback] & sess
    elif v.definition == "short_bearish_impulse_after_compression":
        sig = h4_neutral_or_down & comp_ok[(v.compression_lookback, v.compression_max_atr)] & bearish_impulse[(v.h1_lookback, v.impulse_atr_mult)] & sess
    else:
        sig = pd.Series(False, index=base.index)
    return sig.fillna(False).astype(bool)


def parse_variant_from_row(row: pd.Series) -> Optional[Variant]:
    # Prefer explicit columns from Stage 11B summary.
    try:
        return Variant(
            variant=str(row["variant"]),
            definition=str(row["definition"]),
            h4_sma=int(row.get("h4_sma", 20)),
            h4_slope_lookback=int(row.get("h4_slope_lookback", 3)),
            h1_lookback=int(row.get("h1_lookback", 12)),
            compression_lookback=int(row.get("compression_lookback", 6)),
            compression_max_atr=float(row.get("compression_max_atr", 1.8)),
            rejection_lookback=int(row.get("rejection_lookback", 6)),
            impulse_atr_mult=float(row.get("impulse_atr_mult", 1.2)),
            cooldown_h=int(row.get("cooldown_h", 1)),
            exit_h=int(row.get("exit_h", 6)),
            emergency_stop_usd=30.0,
            session_filter=str(row.get("session_filter", "all")),
        )
    except Exception:
        pass

    # Fallback parser for names like:
    # short_rally_rejection_h4sma20_slope3_look12_comp6_1.8_rej6_imp1.2_h6_cool1_all
    name = str(row.get("variant", ""))
    m = re.search(
        r"(?P<definition>short_[a-z_]+)_h4sma(?P<h4sma>\d+)_slope(?P<slope>\d+)_look(?P<look>\d+)_comp(?P<comp>\d+)_(?P<compmax>[0-9.]+)_rej(?P<rej>\d+)_imp(?P<imp>[0-9.]+)_h(?P<h>\d+)_cool(?P<cool>\d+)_(?P<session>[a-z_]+)$",
        name,
    )
    if not m:
        return None
    return Variant(
        variant=name,
        definition=m.group("definition"),
        h4_sma=int(m.group("h4sma")),
        h4_slope_lookback=int(m.group("slope")),
        h1_lookback=int(m.group("look")),
        compression_lookback=int(m.group("comp")),
        compression_max_atr=float(m.group("compmax")),
        rejection_lookback=int(m.group("rej")),
        impulse_atr_mult=float(m.group("imp")),
        cooldown_h=int(m.group("cool")),
        exit_h=int(m.group("h")),
        emergency_stop_usd=30.0,
        session_filter=m.group("session"),
    )


def load_watchlist(stage11b_summary: Path, stage11c_summary: Path, top_n: int) -> pd.DataFrame:
    if not stage11c_summary.exists():
        raise FileNotFoundError(f"Missing Stage 11C summary: {stage11c_summary}")
    c = pd.read_csv(stage11c_summary)
    c = c[c["verdict"].isin(["RECENT_REGIME_WATCHLIST_ONLY", "SHORT_TERM_WATCHLIST_ONLY"])].copy()
    if c.empty:
        return c

    # Merge Stage11B parameters if available.
    if stage11b_summary.exists():
        b = pd.read_csv(stage11b_summary)
        keep_cols = [
            "variant", "definition", "h4_sma", "h4_slope_lookback", "h1_lookback",
            "compression_lookback", "compression_max_atr", "rejection_lookback",
            "impulse_atr_mult", "cooldown_h", "exit_h", "session_filter",
        ]
        existing = [x for x in keep_cols if x in b.columns]
        if "variant" in existing:
            c = c.merge(b[existing].drop_duplicates("variant"), on="variant", how="left", suffixes=("", "_b"))
            if "definition_b" in c.columns:
                c["definition"] = c["definition"].fillna(c["definition_b"])
    c = c.sort_values(["recent_24m_total_x4", "recent_24m_pf_x4"], ascending=[False, False]).head(top_n)
    return c


def run(db_path: Path, stage11b_summary: Path, stage11c_summary: Path, out_dir: Path, top_n: int, recent_hours: int) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = now_iso()

    conn = connect_db(db_path)
    h1 = load_h1(conn)
    conn.close()
    h4 = resample_h4(h1)
    pc = precompute(h1, h4)

    watch = load_watchlist(stage11b_summary, stage11c_summary, top_n)
    rows: List[dict] = []
    recent_start = h1.index.max() - pd.Timedelta(hours=recent_hours)
    latest_closed_h1 = h1.index.max()

    for _, row in watch.iterrows():
        v = parse_variant_from_row(row)
        if v is None:
            continue
        sig = build_signal(v, pc)
        latest_active = bool(sig.iloc[-1])
        recent_count = int(sig[sig.index >= recent_start].sum())
        last_signal_ts = sig[sig].index.max() if sig.any() else None
        last_signal_age_h = None
        if last_signal_ts is not None and pd.notna(last_signal_ts):
            last_signal_age_h = round((latest_closed_h1 - last_signal_ts).total_seconds() / 3600.0, 2)

        rows.append({
            "variant": v.variant,
            "definition": v.definition,
            "verdict": row.get("verdict", ""),
            "latest_closed_h1": latest_closed_h1.isoformat(),
            "latest_active": int(latest_active),
            "recent_signal_count": recent_count,
            "recent_window_hours": recent_hours,
            "last_signal_utc": last_signal_ts.isoformat() if last_signal_ts is not None and pd.notna(last_signal_ts) else "",
            "last_signal_age_h": last_signal_age_h if last_signal_age_h is not None else "",
            "recent_24m_total_x4": row.get("recent_24m_total_x4", ""),
            "recent_24m_pf_x4": row.get("recent_24m_pf_x4", ""),
            "all_pf_x4": row.get("all_pf_x4", ""),
            "all_median_x4": row.get("all_median_x4", ""),
            "all_dd_x4": row.get("all_dd_x4", ""),
            "session_filter": v.session_filter,
            "exit_h": v.exit_h,
            "cooldown_h": v.cooldown_h,
            "status": "ACTIVE_WATCHLIST_ONLY" if latest_active else ("RECENT_WATCHLIST_SIGNAL_ONLY" if recent_count > 0 else "inactive"),
        })

    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["latest_active", "recent_signal_count", "recent_24m_total_x4"], ascending=[False, False, False])

    out_csv = out_dir / "stage11d_recent_short_watchlist_report.csv"
    out.to_csv(out_csv, index=False)

    active_count = int(out["latest_active"].sum()) if not out.empty else 0
    recent_count_total = int((out["recent_signal_count"] > 0).sum()) if not out.empty else 0
    decision = "short_watchlist_active_report_only" if active_count > 0 else ("recent_short_watchlist_seen_report_only" if recent_count_total > 0 else "short_watchlist_inactive")

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "db_path": str(db_path),
        "stage11b_summary": str(stage11b_summary),
        "stage11c_summary": str(stage11c_summary),
        "latest_closed_h1": latest_closed_h1.isoformat(),
        "watchlist_candidates_loaded": int(len(watch)),
        "watchlist_rows_reported": int(len(out)),
        "latest_active_count": active_count,
        "recent_signal_candidate_count": recent_count_total,
        "recent_hours": recent_hours,
        "decision": decision,
    }
    (out_dir / "stage11d_recent_short_watchlist_report.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    lines = [
        "# Stage 11D Recent Short Watchlist Report",
        "",
        f"Generated UTC: `{generated}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: report/watchlist only. No EA change, no automatic trading, no paper/live authorization.",
        "",
        "## Inputs",
        f"- db: `{db_path}`",
        f"- stage11b_summary: `{stage11b_summary}`",
        f"- stage11c_summary: `{stage11c_summary}`",
        f"- latest_closed_h1: `{latest_closed_h1.isoformat()}`",
        f"- watchlist_candidates_loaded: `{len(watch)}`",
        f"- recent_hours: `{recent_hours}`",
        "",
        "## Decision",
        f"- decision: `{decision}`",
        f"- latest_active_count: `{active_count}`",
        f"- recent_signal_candidate_count: `{recent_count_total}`",
        "",
        "## Watchlist status",
        "| Rank | Status | Verdict | Active now | Recent count | Last signal UTC | Age h | Recent24m total | Recent24m PF | All PF | All median | All DD | Variant |",
        "|---:|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    if not out.empty:
        for i, r in enumerate(out.head(20).to_dict(orient="records"), start=1):
            lines.append(
                f"| {i} | {r['status']} | {r['verdict']} | {r['latest_active']} | {r['recent_signal_count']} | "
                f"{r['last_signal_utc']} | {r['last_signal_age_h']} | {r['recent_24m_total_x4']} | {r['recent_24m_pf_x4']} | "
                f"{r['all_pf_x4']} | {r['all_median_x4']} | {r['all_dd_x4']} | {r['variant']} |"
            )
    else:
        lines.append("| 0 | none | none | 0 | 0 | none |  | 0 | 0 | 0 | 0 | 0 | none |")

    lines += [
        "",
        "## Interpretation",
        "- `ACTIVE_WATCHLIST_ONLY` is not a trade command.",
        "- It means a recent-regime short pattern is currently active and should be observed only.",
        "- Because Stage 11C did not find all-history robustness, these short candidates must not become EA rules.",
        "- Use this report as situational awareness while the validated long-only forward-shadow continues.",
        "",
        "## Outputs",
        f"- csv: `{out_csv}`",
        f"- json: `{out_dir / 'stage11d_recent_short_watchlist_report.json'}`",
    ]

    (out_dir / "stage11d_recent_short_watchlist_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 11D recent short watchlist report: DONE")
    print(f"decision={decision} latest_active={active_count} recent_candidates={recent_count_total}")
    print(f"Report: {out_dir / 'stage11d_recent_short_watchlist_report.md'}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--stage11b-summary", default=str(DEFAULT_STAGE11B_SUMMARY))
    p.add_argument("--stage11c-summary", default=str(DEFAULT_STAGE11C_SUMMARY))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--top-n", type=int, default=12)
    p.add_argument("--recent-hours", type=int, default=72)
    args = p.parse_args()

    return run(
        Path(args.db),
        Path(args.stage11b_summary),
        Path(args.stage11c_summary),
        Path(args.out_dir),
        args.top_n,
        args.recent_hours,
    )


if __name__ == "__main__":
    raise SystemExit(main())
