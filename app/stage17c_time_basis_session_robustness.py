#!/usr/bin/env python3
"""
Stage 17C — Time-Basis and Session Robustness Audit

Why this matters:
- AMarkets/MT5 CSV timestamps may be broker server time, not true UTC.
- Recent reports show bar timestamps can be ahead of report generation UTC.
- Forward-shadow collection must not compare wall-clock UTC against broker-time bars
  as if both were the same clock.
- Session-dependent strategies must be tested under plausible clock offsets.

Candidate audited:
- pdh_breakout_continuation_long_h32_cool4
- LONG
- previous-day high breakout continuation
- horizon = 32 M15 bars
- cooldown = 4 M15 bars
- entry = next M15 open
- exit = 8h time exit

Hard rules:
- Research audit only.
- No EA change.
- No automatic trading.
- No paper/live/order authorization.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import pandas as pd


TOOL_VERSION = "v1"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_OUT_DIR = Path("data/reports/stage17c_time_basis_session_robustness")


def now_utc() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(timezone.utc)).replace(microsecond=0)


def now_iso() -> str:
    return now_utc().isoformat()


def connect(db: Path) -> sqlite3.Connection:
    if not db.exists():
        raise FileNotFoundError(f"DB not found: {db}")
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    return conn


def load_m1(conn: sqlite3.Connection) -> pd.DataFrame:
    rows = conn.execute(
        """
        SELECT utc_time, open, high, low, close
        FROM bars
        WHERE source='amarkets_mt5' AND symbol='XAUUSD' AND timeframe='1m'
        ORDER BY utc_time
        """
    ).fetchall()
    if not rows:
        raise RuntimeError("No AMarkets MT5 M1 bars found.")
    df = pd.DataFrame([dict(r) for r in rows])
    df["utc_time"] = pd.to_datetime(df["utc_time"], utc=True, errors="coerce")
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return (
        df.dropna(subset=["utc_time", "open", "high", "low", "close"])
        .sort_values("utc_time")
        .drop_duplicates("utc_time")
        .set_index("utc_time")
    )


def resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    return df.resample(rule, label="right", closed="right").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna()


def profit_factor(vals: Sequence[float]) -> float:
    vals = [float(v) for v in vals]
    wins = sum(v for v in vals if v > 0)
    losses = abs(sum(v for v in vals if v < 0))
    if losses == 0:
        return 999.0 if wins > 0 else 0.0
    return round(wins / losses, 6)


def max_dd(vals: Sequence[float]) -> float:
    eq = peak = 0.0
    dd = 0.0
    for v in vals:
        eq += float(v)
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return round(dd, 6)


def metrics(df: pd.DataFrame, col: str = "net_x1") -> Dict:
    if df.empty or col not in df.columns:
        return {
            "events": 0, "total": 0.0, "avg": 0.0, "median": 0.0,
            "wr": 0.0, "pf": 0.0, "dd": 0.0,
            "pos_years": 0, "years": 0, "months": 0,
        }
    x = df.sort_values("entry_dt").copy()
    vals = pd.to_numeric(x[col], errors="coerce").dropna().astype(float).tolist()
    if not vals:
        return {
            "events": 0, "total": 0.0, "avg": 0.0, "median": 0.0,
            "wr": 0.0, "pf": 0.0, "dd": 0.0,
            "pos_years": 0, "years": 0, "months": 0,
        }
    s = pd.Series(vals)
    years = x.groupby(x["entry_dt"].dt.year)[col].sum()
    return {
        "events": int(len(vals)),
        "total": round(float(s.sum()), 6),
        "avg": round(float(s.mean()), 6),
        "median": round(float(s.median()), 6),
        "wr": round(float((s > 0).mean()), 6),
        "pf": profit_factor(vals),
        "dd": max_dd(vals),
        "pos_years": int((years > 0).sum()),
        "years": int(len(years)),
        "months": int(x["entry_dt"].dt.to_period("M").nunique()),
    }


def split_metrics(df: pd.DataFrame, frac: float, col: str = "net_x1") -> Dict:
    x = df.sort_values("entry_dt").reset_index(drop=True)
    cut = int(len(x) * frac)
    return {"train": metrics(x.iloc[:cut], col), "test": metrics(x.iloc[cut:], col), "frac": float(frac)}


def apply_spacing(indices: Sequence[int], horizon_bars: int, cooldown_bars: int) -> List[int]:
    chosen = []
    next_allowed = -1
    for i in indices:
        if i < next_allowed:
            continue
        chosen.append(int(i))
        next_allowed = int(i) + int(horizon_bars) + int(cooldown_bars)
    return chosen


def previous_day_levels(m15: pd.DataFrame) -> pd.DataFrame:
    daily = resample_ohlc(m15, "1D")
    rows = []
    days = list(daily.index.strftime("%Y-%m-%d"))
    for i, day in enumerate(days):
        if i == 0:
            continue
        prev = daily.iloc[i - 1]
        rows.append({
            "date": day,
            "pdh": float(prev["high"]),
            "pdl": float(prev["low"]),
            "prev_range": float(prev["high"] - prev["low"]),
        })
    return pd.DataFrame(rows)


def add_context(m15: pd.DataFrame) -> pd.DataFrame:
    x = m15.copy()
    x["date"] = x.index.strftime("%Y-%m-%d")
    x["hour"] = x.index.hour
    x["session"] = "other"
    x.loc[(x["hour"] >= 0) & (x["hour"] < 7), "session"] = "asia"
    x.loc[(x["hour"] >= 7) & (x["hour"] < 12), "session"] = "london"
    x.loc[(x["hour"] >= 12) & (x["hour"] < 17), "session"] = "new_york"
    x.loc[(x["hour"] >= 17) & (x["hour"] < 22), "session"] = "late_us"

    prev = previous_day_levels(m15)
    x = x.reset_index()
    if "utc_time" in x.columns:
        x = x.rename(columns={"utc_time": "dt"})
    else:
        x = x.rename(columns={x.columns[0]: "dt"})
    x = x.merge(prev, on="date", how="left")
    return x.sort_values("dt").reset_index(drop=True)


def replay_candidate(
    m1_raw: pd.DataFrame,
    shift_hours: float,
    cost_usd: float,
    buffer_usd: float,
    close_above_pdh: float,
    horizon_bars: int,
    cooldown_bars: int,
) -> pd.DataFrame:
    # Shift bar clock for session/day logic and replay alignment.
    m1 = m1_raw.copy()
    m1.index = m1.index + pd.Timedelta(hours=shift_hours)
    m15 = resample_ohlc(m1, "15min")
    x = add_context(m15)

    cond = (
        x["pdh"].notna()
        & x["session"].isin(["london", "new_york"])
        & (x["high"] > x["pdh"] + buffer_usd)
        & (x["close"] > x["pdh"] + close_above_pdh)
    )
    idxs = apply_spacing(x.index[cond].tolist(), horizon_bars=horizon_bars, cooldown_bars=cooldown_bars)
    rows = []
    for i in idxs:
        entry_i = i + 1
        exit_i = entry_i + horizon_bars
        if entry_i >= len(x) or exit_i >= len(x):
            continue
        entry_dt = pd.to_datetime(x.iloc[entry_i]["dt"], utc=True)
        exit_dt = pd.to_datetime(x.iloc[exit_i]["dt"], utc=True)
        entry = float(x.iloc[entry_i]["open"])
        path = m1[(m1.index > entry_dt) & (m1.index <= exit_dt)]
        if path.empty:
            continue
        exitp = float(path.iloc[-1]["close"])
        gross = exitp - entry
        rows.append({
            "shift_hours": float(shift_hours),
            "signal_dt": pd.to_datetime(x.iloc[i]["dt"], utc=True),
            "entry_dt": entry_dt,
            "exit_dt": exit_dt,
            "session": x.iloc[i]["session"],
            "hour": int(x.iloc[i]["hour"]),
            "entry_price": entry,
            "exit_price": exitp,
            "gross_ret": round(gross, 6),
            "net_x1": round(gross - cost_usd, 6),
            "net_x2": round(gross - 2 * cost_usd, 6),
            "net_x4": round(gross - 4 * cost_usd, 6),
            "pdh": float(x.iloc[i]["pdh"]),
            "close_above_pdh": round(float(x.iloc[i]["close"] - x.iloc[i]["pdh"]), 6),
            "break_above_pdh": round(float(x.iloc[i]["high"] - x.iloc[i]["pdh"]), 6),
        })
    out = pd.DataFrame(rows)
    return out.sort_values("entry_dt").reset_index(drop=True) if not out.empty else out


def evaluate_shift(trades: pd.DataFrame) -> Dict:
    m1 = metrics(trades, "net_x1")
    m2 = metrics(trades, "net_x2")
    m4 = metrics(trades, "net_x4")
    s80 = split_metrics(trades, 0.80, "net_x1")
    y2026 = metrics(trades[trades["entry_dt"].dt.year == 2026], "net_x1") if not trades.empty else metrics(trades)
    return {
        "events": m1["events"],
        "total_x1": m1["total"],
        "median_x1": m1["median"],
        "wr_x1": m1["wr"],
        "pf_x1": m1["pf"],
        "dd_x1": m1["dd"],
        "total_x2": m2["total"],
        "pf_x2": m2["pf"],
        "total_x4": m4["total"],
        "pf_x4": m4["pf"],
        "test20_events": s80["test"]["events"],
        "test20_total": s80["test"]["total"],
        "test20_median": s80["test"]["median"],
        "test20_pf": s80["test"]["pf"],
        "events_2026": y2026["events"],
        "total_2026": y2026["total"],
        "median_2026": y2026["median"],
        "pf_2026": y2026["pf"],
        "pos_years": m1["pos_years"],
        "years": m1["years"],
        "months": m1["months"],
    }


def decide(clock_ahead_hours: float, rows: pd.DataFrame) -> Tuple[str, List[str]]:
    reasons: List[str] = []

    if clock_ahead_hours > 0.5:
        reasons.append(
            "Latest bar timestamp is ahead of report wall-clock UTC; MT5 CSV timestamps are likely broker/server time, not true UTC."
        )

    base = rows[rows["shift_hours"].eq(0.0)]
    minus3 = rows[rows["shift_hours"].eq(-3.0)]
    if base.empty:
        return "TIME_BASIS_AUDIT_FAILED_NO_BASE", ["No base shift row produced."]

    b = base.iloc[0].to_dict()
    base_pass = (
        b["events"] >= 200
        and b["total_x1"] > 0
        and b["pf_x1"] >= 1.15
        and b["test20_total"] > 0
        and b["test20_pf"] >= 1.05
    )

    offset_rows = rows[(rows["shift_hours"].isin([-2.0, -3.0, -4.0]))]
    offset_pass_count = int(
        (
            (offset_rows["events"] >= 150)
            & (offset_rows["total_x1"] > 0)
            & (offset_rows["pf_x1"] >= 1.05)
            & (offset_rows["test20_total"] > 0)
            & (offset_rows["test20_pf"] >= 1.0)
        ).sum()
    )

    if clock_ahead_hours > 0.5 and base_pass and offset_pass_count == 0:
        reasons.append("Candidate is strong under raw broker clock but not robust to plausible UTC shifts.")
        reasons.append("Forward collection must explicitly use broker-time boundary, not wall-clock UTC.")
        return "BROKER_TIME_REQUIRED_NOT_UTC_FORWARD_READY", reasons

    if clock_ahead_hours > 0.5 and base_pass and offset_pass_count > 0:
        reasons.append("Candidate survives at least one plausible clock shift, but forward collection still needs broker-time boundary handling.")
        return "TIME_OFFSET_AWARE_FORWARD_DESIGN_REQUIRED", reasons

    if base_pass:
        reasons.append("No material wall-clock/bar-clock issue detected and base candidate remains valid.")
        return "TIME_BASIS_OK_FOR_FORWARD_DESIGN", reasons

    reasons.append("Base candidate no longer passes under time-basis audit.")
    return "TIME_BASIS_REJECT_OR_RECHECK_CANDIDATE", reasons


def run(
    db: Path,
    out_dir: Path,
    cost_usd: float,
    buffer_usd: float,
    close_above_pdh: float,
    horizon_bars: int,
    cooldown_bars: int,
    shifts: Sequence[float],
) -> int:
    generated_ts = now_utc()
    generated = generated_ts.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = connect(db)
    try:
        m1 = load_m1(conn)
    finally:
        conn.close()

    latest_raw = m1.index.max()
    clock_ahead_hours = round(float((latest_raw - generated_ts) / pd.Timedelta(hours=1)), 6)

    summary_rows = []
    trade_parts = []
    for sh in shifts:
        tr = replay_candidate(
            m1_raw=m1,
            shift_hours=float(sh),
            cost_usd=cost_usd,
            buffer_usd=buffer_usd,
            close_above_pdh=close_above_pdh,
            horizon_bars=horizon_bars,
            cooldown_bars=cooldown_bars,
        )
        if not tr.empty:
            trade_parts.append(tr)
        row = {"shift_hours": float(sh)}
        row.update(evaluate_shift(tr))
        summary_rows.append(row)

    summary = pd.DataFrame(summary_rows).sort_values("shift_hours")
    all_trades = pd.concat(trade_parts, ignore_index=True) if trade_parts else pd.DataFrame()
    final_decision, reasons = decide(clock_ahead_hours, summary)

    summary_csv = out_dir / "stage17c_time_shift_summary.csv"
    trades_csv = out_dir / "stage17c_time_shift_trades.csv"
    json_path = out_dir / "stage17c_time_basis_session_robustness.json"
    md_path = out_dir / "stage17c_time_basis_session_robustness.md"

    summary.to_csv(summary_csv, index=False)
    all_trades.to_csv(trades_csv, index=False)

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "candidate": {
            "variant": "pdh_breakout_continuation_long_h32_cool4",
            "side": "LONG",
            "horizon_bars": int(horizon_bars),
            "horizon_minutes": int(horizon_bars * 15),
            "cooldown_bars": int(cooldown_bars),
            "buffer_usd": float(buffer_usd),
            "close_above_pdh": float(close_above_pdh),
            "cost_usd": float(cost_usd),
        },
        "clock_audit": {
            "m1_first_raw": m1.index.min().isoformat(),
            "m1_last_raw": latest_raw.isoformat(),
            "generated_utc": generated,
            "latest_raw_minus_generated_hours": clock_ahead_hours,
            "bar_clock_likely_broker_server_time": bool(clock_ahead_hours > 0.5),
        },
        "final_decision": final_decision,
        "reasons": reasons,
        "summary": summary.to_dict(orient="records"),
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
        "# Stage 17C Time-Basis and Session Robustness Audit",
        "",
        f"Generated UTC: `{generated}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: research audit only. No EA change, no automatic trading, no paper/live authorization.",
        "",
        "## Candidate",
        "- variant: `pdh_breakout_continuation_long_h32_cool4`",
        "- side: `LONG`",
        "- behavior: `previous-day high breakout continuation`",
        f"- horizon_bars: `{horizon_bars}`",
        f"- horizon_minutes: `{horizon_bars * 15}`",
        f"- cooldown_bars: `{cooldown_bars}`",
        "",
        "## Clock audit",
        f"- m1_first_raw: `{m1.index.min().isoformat()}`",
        f"- m1_last_raw: `{latest_raw.isoformat()}`",
        f"- generated_utc: `{generated}`",
        f"- latest_raw_minus_generated_hours: `{clock_ahead_hours}`",
        f"- bar_clock_likely_broker_server_time: `{clock_ahead_hours > 0.5}`",
        "",
        "## Final decision",
        f"- final_decision: `{final_decision}`",
        "",
        "## Reasons",
    ]
    for r in reasons:
        lines.append(f"- {r}")

    lines += [
        "",
        "## Time-shift robustness summary",
        "| Shift hours | Events | Total x1 | Median x1 | PF x1 | DD x1 | PF x2 | PF x4 | Test20 events | Test20 total | Test20 PF | 2026 total | 2026 PF |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in summary.to_dict(orient="records"):
        lines.append(
            f"| {r['shift_hours']} | {r['events']} | {r['total_x1']} | {r['median_x1']} | {r['pf_x1']} | {r['dd_x1']} | {r['pf_x2']} | {r['pf_x4']} | {r['test20_events']} | {r['test20_total']} | {r['test20_pf']} | {r['total_2026']} | {r['pf_2026']} |"
        )

    lines += [
        "",
        "## Interpretation",
        "- If bar timestamps are ahead of wall-clock UTC, forward collectors must use broker-time boundaries or a calibrated offset.",
        "- If the candidate only works under raw broker clock, that is not automatically wrong, but the system must explicitly declare broker-time execution logic.",
        "- If shifted variants also work, the behavior is less dependent on exact timestamp convention.",
        "- No paper/live/order authorization is granted.",
        "",
        "## Output files",
        f"- summary_csv: `{summary_csv}`",
        f"- trades_csv: `{trades_csv}`",
        f"- json: `{json_path}`",
        f"- md: `{md_path}`",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 17C time-basis/session robustness audit: DONE")
    print(f"final_decision={final_decision}")
    print(f"latest_raw_minus_generated_hours={clock_ahead_hours}")
    print(f"Report: {md_path}")
    return 0


def parse_shifts(s: str) -> List[float]:
    return [float(x.strip()) for x in s.split(",") if x.strip()]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--cost-usd", type=float, default=0.35)
    p.add_argument("--buffer-usd", type=float, default=0.2)
    p.add_argument("--close-above-pdh", type=float, default=0.8)
    p.add_argument("--horizon-bars", type=int, default=32)
    p.add_argument("--cooldown-bars", type=int, default=4)
    p.add_argument("--shifts", default="0,-1,-2,-3,-4", help="Comma-separated hour shifts applied to bar timestamps.")
    args = p.parse_args()

    return run(
        db=Path(args.db),
        out_dir=Path(args.out_dir),
        cost_usd=float(args.cost_usd),
        buffer_usd=float(args.buffer_usd),
        close_above_pdh=float(args.close_above_pdh),
        horizon_bars=int(args.horizon_bars),
        cooldown_bars=int(args.cooldown_bars),
        shifts=parse_shifts(args.shifts),
    )


if __name__ == "__main__":
    raise SystemExit(main())
