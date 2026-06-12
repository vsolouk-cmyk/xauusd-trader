#!/usr/bin/env python3
"""
Stage 20A — London-to-NY Handoff Short Exact M1 Replay

Purpose:
- Stage19A found multiple London-to-NY handoff continuation SHORT variants as lite watchlist.
- Stage19B rejected/kept the compression breakout candidate as watchlist only.
- Stage20A exact-replays the strongest London-to-NY handoff SHORT variants with M1 path.

Behavior:
- If London session bias is negative enough:
    london_bias = london_close - london_open <= -bias_min
- During New York session:
    M15 close breaks below London low by buffer
- Side: SHORT
- Entry: next M15 open
- Exit: time exit after horizon bars
- Cooldown: 4 bars
- Cost: 0.35 USD default

Hard rules:
- Research validation only.
- No EA change.
- No automatic trading.
- No paper/live/order authorization.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import pandas as pd


TOOL_VERSION = "v1"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_OUT_DIR = Path("data/reports/stage20a_london_ny_handoff_short_exact_replay")

warnings.filterwarnings(
    "ignore",
    message="Converting to PeriodArray/Index representation will drop timezone information.",
    category=UserWarning,
)


@dataclass(frozen=True)
class Variant:
    name: str
    bias_min: float
    horizon_bars: int
    cooldown_bars: int = 4


VARIANTS = [
    Variant("london_ny_handoff_continuation_short_bias2_h8", 2.0, 8),
    Variant("london_ny_handoff_continuation_short_bias3_h8", 3.0, 8),
    Variant("london_ny_handoff_continuation_short_bias2_h24", 2.0, 24),
    Variant("london_ny_handoff_continuation_short_bias1_h8", 1.0, 8),
    Variant("london_ny_handoff_continuation_short_bias2_h16", 2.0, 16),
    Variant("london_ny_handoff_continuation_short_bias3_h24", 3.0, 24),
    Variant("london_ny_handoff_continuation_short_bias1_h16", 1.0, 16),
    Variant("london_ny_handoff_continuation_short_bias1_h24", 1.0, 24),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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


def period_no_tz(series: pd.Series, freq: str) -> pd.Series:
    dt = pd.to_datetime(series, utc=True, errors="coerce")
    return dt.dt.tz_localize(None).dt.to_period(freq)


def add_context(m15: pd.DataFrame) -> pd.DataFrame:
    x = m15.copy()
    x["date"] = x.index.strftime("%Y-%m-%d")
    x["hour"] = x.index.hour
    x["minute"] = x.index.minute
    x["session"] = "other"
    x.loc[(x["hour"] >= 0) & (x["hour"] < 7), "session"] = "asia"
    x.loc[(x["hour"] >= 7) & (x["hour"] < 12), "session"] = "london"
    x.loc[(x["hour"] >= 12) & (x["hour"] < 17), "session"] = "new_york"
    x.loc[(x["hour"] >= 17) & (x["hour"] < 22), "session"] = "late_us"

    base = x.reset_index()
    if "utc_time" in base.columns:
        base = base.rename(columns={"utc_time": "dt"})
    else:
        base = base.rename(columns={base.columns[0]: "dt"})

    london = base[(base["hour"] >= 7) & (base["hour"] < 12)].groupby("date").agg(
        london_high=("high", "max"),
        london_low=("low", "min"),
        london_open=("open", "first"),
        london_close=("close", "last"),
    )
    london["london_range"] = london["london_high"] - london["london_low"]
    london["london_bias"] = london["london_close"] - london["london_open"]
    base = base.merge(london.reset_index(), on="date", how="left")

    return base.sort_values("dt").reset_index(drop=True)


def apply_spacing(indices: Sequence[int], horizon_bars: int, cooldown_bars: int) -> List[int]:
    chosen = []
    next_allowed = -1
    for i in indices:
        if i < next_allowed:
            continue
        chosen.append(int(i))
        next_allowed = int(i) + int(horizon_bars) + int(cooldown_bars)
    return chosen


def signal_mask(x: pd.DataFrame, v: Variant, buffer_usd: float) -> pd.Series:
    return (
        x["london_low"].notna()
        & x["session"].eq("new_york")
        & (x["london_bias"] <= -float(v.bias_min))
        & (x["close"] < x["london_low"] - buffer_usd)
    ).fillna(False)


def get_entry_price(m15: pd.DataFrame, entry_dt: pd.Timestamp) -> Tuple[float, str]:
    if entry_dt in m15.index:
        return float(m15.loc[entry_dt]["open"]), "m15_exact_open"
    pos = m15.index.searchsorted(entry_dt)
    if pos < len(m15):
        return float(m15.iloc[pos]["open"]), "m15_next_open"
    return float("nan"), "entry_after_available_data"


def replay_variant(v: Variant, x: pd.DataFrame, m15: pd.DataFrame, m1: pd.DataFrame, cost_usd: float, buffer_usd: float) -> pd.DataFrame:
    mask = signal_mask(x, v, buffer_usd)
    idxs = apply_spacing(x.index[mask].tolist(), v.horizon_bars, v.cooldown_bars)
    rows = []
    for i in idxs:
        entry_i = i + 1
        if entry_i >= len(x):
            continue
        signal_dt = pd.to_datetime(x.iloc[i]["dt"], utc=True)
        entry_dt = pd.to_datetime(x.iloc[entry_i]["dt"], utc=True)
        exit_dt = entry_dt + pd.Timedelta(minutes=15 * v.horizon_bars)
        entry_price, src = get_entry_price(m15, entry_dt)
        if pd.isna(entry_price):
            continue
        path = m1[(m1.index > entry_dt) & (m1.index <= exit_dt)]
        if path.empty:
            continue

        exit_price = float(path.iloc[-1]["close"])
        gross = float(entry_price) - exit_price  # SHORT
        mfe = float(entry_price) - float(path["low"].min())
        mae = float(path["high"].max()) - float(entry_price)

        rows.append({
            "variant": v.name,
            "family": "london_ny_handoff_continuation_short",
            "side": "SHORT",
            "bias_min": v.bias_min,
            "horizon_bars": v.horizon_bars,
            "horizon_minutes": v.horizon_bars * 15,
            "cooldown_bars": v.cooldown_bars,
            "signal_dt": signal_dt,
            "entry_dt": entry_dt,
            "exit_dt": exit_dt,
            "entry_price": round(float(entry_price), 6),
            "entry_price_source": src,
            "exit_price": round(exit_price, 6),
            "gross_ret": round(gross, 6),
            "net_x1": round(gross - cost_usd, 6),
            "net_x2": round(gross - 2 * cost_usd, 6),
            "net_x4": round(gross - 4 * cost_usd, 6),
            "mfe": round(mfe, 6),
            "mae": round(mae, 6),
            "session": str(x.iloc[i].get("session", "")),
            "hour": int(x.iloc[i].get("hour", -1)),
            "london_open": float(x.iloc[i].get("london_open")) if pd.notna(x.iloc[i].get("london_open")) else float("nan"),
            "london_close": float(x.iloc[i].get("london_close")) if pd.notna(x.iloc[i].get("london_close")) else float("nan"),
            "london_low": float(x.iloc[i].get("london_low")) if pd.notna(x.iloc[i].get("london_low")) else float("nan"),
            "london_high": float(x.iloc[i].get("london_high")) if pd.notna(x.iloc[i].get("london_high")) else float("nan"),
            "london_bias": float(x.iloc[i].get("london_bias")) if pd.notna(x.iloc[i].get("london_bias")) else float("nan"),
            "signal_close": float(x.iloc[i].get("close")),
        })

    out = pd.DataFrame(rows)
    if not out.empty:
        for c in ["signal_dt", "entry_dt", "exit_dt"]:
            out[c] = pd.to_datetime(out[c], utc=True, errors="coerce")
        out = out.sort_values("entry_dt").reset_index(drop=True)
    return out


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
        return {"events": 0, "total": 0.0, "avg": 0.0, "median": 0.0, "wr": 0.0, "pf": 0.0, "dd": 0.0, "pos_years": 0, "years": 0, "pos_quarters": 0, "quarters": 0, "months": 0}
    x = df.sort_values("entry_dt").copy()
    vals = pd.to_numeric(x[col], errors="coerce").dropna().astype(float).tolist()
    if not vals:
        return {"events": 0, "total": 0.0, "avg": 0.0, "median": 0.0, "wr": 0.0, "pf": 0.0, "dd": 0.0, "pos_years": 0, "years": 0, "pos_quarters": 0, "quarters": 0, "months": 0}
    s = pd.Series(vals)
    years = x.groupby(x["entry_dt"].dt.year)[col].sum()
    quarters = x.groupby(period_no_tz(x["entry_dt"], "Q").astype(str))[col].sum()
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
        "pos_quarters": int((quarters > 0).sum()),
        "quarters": int(len(quarters)),
        "months": int(period_no_tz(x["entry_dt"], "M").nunique()),
    }


def split_metrics(df: pd.DataFrame, frac: float, col: str = "net_x1") -> Dict:
    x = df.sort_values("entry_dt").reset_index(drop=True)
    cut = int(len(x) * frac)
    return {"frac": frac, "train": metrics(x.iloc[:cut], col), "test": metrics(x.iloc[cut:], col)}


def bootstrap(df: pd.DataFrame, col: str = "net_x1", n: int = 300, seed: int = 20) -> Dict:
    if df.empty:
        return {"n": n, "total_p05": 0.0, "pf_p05": 0.0, "prob_total_gt_0": 0.0, "prob_pf_gt_1": 0.0, "prob_median_gt_0": 0.0}
    x = df.sort_values("entry_dt").reset_index(drop=True)
    totals, pfs, meds = [], [], []
    for i in range(n):
        s = x.sample(n=len(x), replace=True, random_state=seed + i)
        vals = pd.to_numeric(s[col], errors="coerce").dropna().astype(float).tolist()
        totals.append(sum(vals))
        pfs.append(profit_factor(vals))
        meds.append(float(pd.Series(vals).median()) if vals else 0.0)
    ts, ps, ms = pd.Series(totals), pd.Series(pfs), pd.Series(meds)
    return {
        "n": int(n),
        "total_p05": round(float(ts.quantile(0.05)), 6),
        "total_p50": round(float(ts.quantile(0.50)), 6),
        "pf_p05": round(float(ps.quantile(0.05)), 6),
        "pf_p50": round(float(ps.quantile(0.50)), 6),
        "median_p05": round(float(ms.quantile(0.05)), 6),
        "prob_total_gt_0": round(float((ts > 0).mean()), 6),
        "prob_pf_gt_1": round(float((ps > 1).mean()), 6),
        "prob_median_gt_0": round(float((ms > 0).mean()), 6),
    }


def decide(m1: Dict, m2: Dict, m4: Dict, s80: Dict, s70: Dict, y2026: Dict, boot: Dict) -> Tuple[str, List[str], float]:
    score = 0.0
    score += min(8, m1["pf"] * 2.5)
    score += min(5, max(0, m1["median"]) * 1.2)
    score += min(6, max(0, s80["test"]["pf"]) * 1.5)
    score += min(4, max(0, y2026["total"]) / 80.0)
    score += min(4, max(0, boot.get("prob_total_gt_0", 0)) * 4)
    score -= min(6, abs(min(0, m1["dd"])) / 200.0)

    if m1["events"] < 80:
        return "REJECT_TOO_FEW_EVENTS", ["events < 80"], -999.0

    promote = (
        m1["events"] >= 120
        and m1["total"] > 0
        and m1["pf"] >= 1.15
        and m1["median"] > 0
        and m2["total"] > 0
        and m2["pf"] >= 1.08
        and m4["pf"] >= 1.00
        and s80["test"]["events"] >= 20
        and s80["test"]["total"] > 0
        and s80["test"]["pf"] >= 1.05
        and s70["test"]["total"] > 0
        and (y2026["events"] < 15 or (y2026["total"] > 0 and y2026["pf"] >= 1.00))
        and m1["pos_years"] >= max(3, round(m1["years"] * 0.55))
        and boot.get("prob_total_gt_0", 0) >= 0.90
        and boot.get("pf_p05", 0) >= 1.00
    )
    if promote:
        return "PROMOTE_FORWARD_SHADOW_DESIGN_CANDIDATE", ["Exact replay passed strict robustness criteria."], round(score, 6)

    watch = (
        m1["events"] >= 100
        and m1["total"] > 0
        and m1["pf"] >= 1.05
        and s80["test"]["events"] >= 15
        and s80["test"]["total"] > 0
        and boot.get("prob_total_gt_0", 0) >= 0.75
    )
    if watch:
        return "KEEP_EXACT_WATCHLIST_ONLY", ["Positive exact replay but not robust enough for forward-shadow design."], round(score, 6)

    return "REJECT_EXACT_WEAK", ["Exact replay does not preserve enough robust edge."], round(score, 6)


def evaluate(v: Variant, trades: pd.DataFrame, bootstrap_n: int) -> Dict:
    m1 = metrics(trades, "net_x1")
    m2 = metrics(trades, "net_x2")
    m4 = metrics(trades, "net_x4")
    s70 = split_metrics(trades, 0.70, "net_x1")
    s80 = split_metrics(trades, 0.80, "net_x1")
    y2026 = metrics(trades[trades["entry_dt"].dt.year == 2026], "net_x1") if not trades.empty else metrics(trades)
    boot = bootstrap(trades, "net_x1", bootstrap_n)
    decision, reasons, score = decide(m1, m2, m4, s80, s70, y2026, boot)
    return {
        "variant": v.name,
        "family": "london_ny_handoff_continuation_short",
        "side": "SHORT",
        "bias_min": v.bias_min,
        "horizon_bars": v.horizon_bars,
        "horizon_minutes": v.horizon_bars * 15,
        "cooldown_bars": v.cooldown_bars,
        "decision": decision,
        "score": score,
        "reasons": "; ".join(reasons),
        "events": m1["events"],
        "freq_per_month": round(m1["events"] / max(1, m1["months"]), 6),
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
        "test30_events": s70["test"]["events"],
        "test30_total": s70["test"]["total"],
        "test30_pf": s70["test"]["pf"],
        "events_2026": y2026["events"],
        "total_2026": y2026["total"],
        "median_2026": y2026["median"],
        "pf_2026": y2026["pf"],
        "pos_years": m1["pos_years"],
        "years": m1["years"],
        "boot_total_p05": boot["total_p05"],
        "boot_pf_p05": boot["pf_p05"],
        "boot_prob_total_gt_0": boot["prob_total_gt_0"],
        "boot_prob_pf_gt_1": boot["prob_pf_gt_1"],
    }


def run(db: Path, out_dir: Path, cost_usd: float, buffer_usd: float, bootstrap_n: int, top_n_trades: int) -> int:
    generated = now_iso()
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = connect(db)
    try:
        m1 = load_m1(conn)
    finally:
        conn.close()

    m15 = resample_ohlc(m1, "15min")
    ctx = add_context(m15)

    summary_rows = []
    trade_parts = []
    for v in VARIANTS:
        trades = replay_variant(v, ctx, m15, m1, cost_usd=cost_usd, buffer_usd=buffer_usd)
        summary_rows.append(evaluate(v, trades, bootstrap_n))
        if not trades.empty:
            trade_parts.append(trades)

    summary = pd.DataFrame(summary_rows)
    order = {"PROMOTE_FORWARD_SHADOW_DESIGN_CANDIDATE": 0, "KEEP_EXACT_WATCHLIST_ONLY": 1, "REJECT_EXACT_WEAK": 2, "REJECT_TOO_FEW_EVENTS": 3}
    summary["_order"] = summary["decision"].map(order).fillna(9)
    summary = summary.sort_values(["_order", "score", "pf_x1", "events"], ascending=[True, False, False, False]).drop(columns=["_order"])

    all_trades = pd.concat(trade_parts, ignore_index=True) if trade_parts else pd.DataFrame()
    promoted = summary[summary["decision"].eq("PROMOTE_FORWARD_SHADOW_DESIGN_CANDIDATE")].copy()
    watch = summary[summary["decision"].eq("KEEP_EXACT_WATCHLIST_ONLY")].copy()

    if top_n_trades > 0 and not all_trades.empty:
        keep = summary.head(top_n_trades)["variant"].tolist()
        trades_out = all_trades[all_trades["variant"].isin(keep)].copy()
    else:
        trades_out = all_trades

    final_decision = "HANDOFF_SHORT_PROMOTIONS_FOUND" if len(promoted) else ("HANDOFF_SHORT_WATCHLIST_ONLY" if len(watch) else "HANDOFF_SHORT_REJECTED")

    summary_csv = out_dir / "stage20a_handoff_short_exact_summary.csv"
    promoted_csv = out_dir / "stage20a_handoff_short_promoted.csv"
    trades_csv = out_dir / "stage20a_handoff_short_exact_trades.csv"
    json_path = out_dir / "stage20a_london_ny_handoff_short_exact_replay.json"
    md_path = out_dir / "stage20a_london_ny_handoff_short_exact_replay.md"

    summary.to_csv(summary_csv, index=False)
    promoted.to_csv(promoted_csv, index=False)
    trades_out.to_csv(trades_csv, index=False)

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "inputs": {
            "db": str(db),
            "cost_usd": float(cost_usd),
            "buffer_usd": float(buffer_usd),
            "bootstrap_n": int(bootstrap_n),
        },
        "source": {
            "m1_rows": int(len(m1)),
            "m15_rows": int(len(m15)),
            "m1_first": m1.index.min().isoformat(),
            "m1_last": m1.index.max().isoformat(),
            "variants_tested": int(len(summary)),
        },
        "final_decision": final_decision,
        "counts": {
            "promoted": int(len(promoted)),
            "watchlist": int(len(watch)),
            "variants_tested": int(len(summary)),
        },
        "promoted": promoted.to_dict(orient="records"),
        "watchlist": watch.to_dict(orient="records"),
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
        "# Stage 20A London-to-NY Handoff Short Exact M1 Replay",
        "",
        f"Generated UTC: `{generated}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: research validation only. No EA change, no automatic trading, no paper/live authorization.",
        "",
        "## Purpose",
        "- Exact-replay London-to-NY handoff continuation SHORT variants from Stage19A watchlist.",
        "- Use exact M1 path before any forward-shadow design.",
        "",
        "## Inputs",
        f"- db: `{db}`",
        f"- m1_rows: `{len(m1)}`",
        f"- m15_rows: `{len(m15)}`",
        f"- m1_first: `{m1.index.min().isoformat()}`",
        f"- m1_last: `{m1.index.max().isoformat()}`",
        f"- cost_usd: `{cost_usd}`",
        f"- buffer_usd: `{buffer_usd}`",
        f"- variants_tested: `{len(summary)}`",
        "",
        "## Final decision",
        f"- final_decision: `{final_decision}`",
        "",
        "## Counts",
        f"- promoted: `{len(promoted)}`",
        f"- watchlist: `{len(watch)}`",
        "",
        "## Variant ranking",
        "| Rank | Variant | Decision | Events | Freq/mo | PF x1 | Median x1 | Total x1 | PF x2 | PF x4 | Test20 events | Test20 total | Test20 PF | 2026 total | 2026 PF | Boot PF p05 | Score |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for i, r in enumerate(summary.to_dict(orient="records"), 1):
        lines.append(
            f"| {i} | `{r['variant']}` | `{r['decision']}` | {r['events']} | {r['freq_per_month']} | {r['pf_x1']} | {r['median_x1']} | {r['total_x1']} | {r['pf_x2']} | {r['pf_x4']} | {r['test20_events']} | {r['test20_total']} | {r['test20_pf']} | {r['total_2026']} | {r['pf_2026']} | {r['boot_pf_p05']} | {r['score']} |"
        )

    lines += [
        "",
        "## Promoted candidates",
    ]
    if not promoted.empty:
        for r in promoted.to_dict(orient="records"):
            lines.append(f"- `{r['variant']}` — {r['reasons']}")
    else:
        lines.append("- none")

    lines += [
        "",
        "## Interpretation",
        "- Stage20A is exact historical validation, not forward proof.",
        "- Promoted variants may go to a later forward-shadow collector design.",
        "- Watchlist-only variants must not be added to Stage18A.",
        "- No paper/live/order escalation is authorized.",
        "",
        "## Output files",
        f"- summary_csv: `{summary_csv}`",
        f"- promoted_csv: `{promoted_csv}`",
        f"- trades_csv: `{trades_csv}`",
        f"- json: `{json_path}`",
        f"- md: `{md_path}`",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 20A London-to-NY handoff short exact replay: DONE")
    print(f"final_decision={final_decision}")
    print(f"promoted={len(promoted)} watchlist={len(watch)}")
    print(f"Report: {md_path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--cost-usd", type=float, default=0.35)
    p.add_argument("--buffer-usd", type=float, default=0.2)
    p.add_argument("--bootstrap-n", type=int, default=300)
    p.add_argument("--top-n-trades", type=int, default=8)
    args = p.parse_args()

    return run(
        db=Path(args.db),
        out_dir=Path(args.out_dir),
        cost_usd=float(args.cost_usd),
        buffer_usd=float(args.buffer_usd),
        bootstrap_n=int(args.bootstrap_n),
        top_n_trades=int(args.top_n_trades),
    )


if __name__ == "__main__":
    raise SystemExit(main())
