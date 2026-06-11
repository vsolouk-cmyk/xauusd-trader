#!/usr/bin/env python3
"""
Stage 14C — Behavioral Filter Study for Prev-Day Low Sweep Rejection

Purpose:
- Improve the Stage 14A/14B candidate:
  prev_day_low_sweep_rejection / LONG / horizon_bars=4
- Test a small set of behavior-based filters, not classic indicator grids.
- Judge everything after roundtrip cost.

Hard rules:
- Research only.
- No EA change.
- No automatic trading.
- No paper/live/order authorization.
- No direct conversion to signal.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Sequence, Tuple

import pandas as pd

TOOL_VERSION = "v1"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_CANDIDATE = Path("data/reports/stage14b_prev_day_low_sweep_validation/stage14b_candidate_outcomes.csv")
DEFAULT_OUT_DIR = Path("data/reports/stage14c_behavioral_filter_study")

@dataclass(frozen=True)
class FilterSpec:
    name: str
    description: str
    predicate: Callable[[pd.DataFrame], pd.Series]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(db: Path) -> sqlite3.Connection:
    if not db.exists():
        raise FileNotFoundError(f"DB not found: {db}")
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    return conn


def load_bars(conn: sqlite3.Connection, tf: str) -> pd.DataFrame:
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
    df = df.dropna(subset=["utc_time", "open", "high", "low", "close"]).sort_values("utc_time").drop_duplicates("utc_time")
    return df.set_index("utc_time")


def resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    if df.empty:
        return df
    return df.resample(rule, label="right", closed="right").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna()


def load_intraday(conn: sqlite3.Connection) -> Tuple[pd.DataFrame, str]:
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


def load_h4(conn: sqlite3.Connection, intraday: pd.DataFrame) -> pd.DataFrame:
    h4 = load_bars(conn, "4h")
    if len(h4) > 100:
        return h4
    h1 = load_bars(conn, "1h")
    if len(h1) > 100:
        return resample_ohlc(h1, "4h")
    return resample_ohlc(intraday, "4h")


def atr(df: pd.DataFrame, n: int = 96) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat(
        [(df["high"] - df["low"]).abs(), (df["high"] - pc).abs(), (df["low"] - pc).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(n, min_periods=max(10, n // 4)).mean()


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


def metrics(df: pd.DataFrame, ret_col: str) -> Dict:
    if df.empty:
        return {"events": 0, "total": 0.0, "avg": 0.0, "median": 0.0, "win_rate": 0.0, "pf": 0.0, "max_dd": 0.0, "pos_years": 0, "years": 0}
    vals = df.sort_values("entry_dt")[ret_col].astype(float).tolist()
    s = pd.Series(vals)
    years = df["entry_dt"].dt.year
    by_year = df.assign(year=years).groupby("year")[ret_col].sum()
    return {
        "events": int(len(vals)),
        "total": round(float(s.sum()), 6),
        "avg": round(float(s.mean()), 6),
        "median": round(float(s.median()), 6),
        "win_rate": round(float((s > 0).mean()), 6),
        "pf": profit_factor(vals),
        "max_dd": max_dd(vals),
        "pos_years": int((by_year > 0).sum()),
        "years": int(len(by_year)),
    }


def chronological_split_metrics(df: pd.DataFrame, ret_col: str, frac: float = 0.70) -> Dict:
    x = df.sort_values("entry_dt").reset_index(drop=True)
    cut = int(len(x) * frac)
    return {"train": metrics(x.iloc[:cut], ret_col), "test": metrics(x.iloc[cut:], ret_col), "train_frac": frac}


def parse_context_value(text: str, key: str) -> float:
    m = re.search(rf"{re.escape(key)}=(-?\d+(?:\.\d+)?)", str(text))
    if not m:
        return float("nan")
    return float(m.group(1))


def session_name(hour: int) -> str:
    if 0 <= hour <= 6:
        return "asia"
    if 7 <= hour <= 12:
        return "london"
    if 13 <= hour <= 20:
        return "new_york"
    return "late_us"


def atr_percentile(series: pd.Series, window: int = 252) -> pd.Series:
    def pct_last(v):
        s = pd.Series(v)
        return float(s.rank(pct=True).iloc[-1])
    return series.rolling(window, min_periods=50).apply(pct_last, raw=False)


def add_features(candidate: pd.DataFrame, intraday: pd.DataFrame, h4: pd.DataFrame, cost_usd: float) -> pd.DataFrame:
    x = candidate.copy()
    x["event_dt"] = pd.to_datetime(x["event_utc"], utc=True, errors="coerce")
    x["entry_dt"] = pd.to_datetime(x["entry_utc"], utc=True, errors="coerce")
    x["ret_usd"] = pd.to_numeric(x["ret_usd"], errors="coerce")
    x["ref_level"] = pd.to_numeric(x["ref_level"], errors="coerce")
    x = x.dropna(subset=["event_dt", "entry_dt", "ret_usd", "ref_level"]).sort_values("entry_dt").reset_index(drop=True)
    x["net_x1"] = x["ret_usd"] - float(cost_usd)

    bars = intraday.copy()
    bars["atr96"] = atr(bars, 96)
    bars["atr_pct_rank_252"] = atr_percentile(bars["atr96"], 252)

    h4c = h4.copy()
    h4c["h4_sma20"] = h4c["close"].rolling(20, min_periods=5).mean()
    h4c["h4_slope3"] = h4c["h4_sma20"] - h4c["h4_sma20"].shift(3)
    h4_feat = h4c[["close", "h4_sma20", "h4_slope3"]].rename(columns={"close": "h4_close"}).reindex(bars.index, method="ffill")
    bars = bars.join(h4_feat, how="left")
    bars_day = bars.copy()
    bars_day["_day"] = bars_day.index.strftime("%Y-%m-%d")

    feat_rows = []
    for _, r in x.iterrows():
        ts = r["event_dt"]
        if ts in bars.index:
            ts_bar = ts
        else:
            pos = bars.index.searchsorted(ts)
            pos = min(max(pos, 0), len(bars) - 1)
            ts_bar = bars.index[pos]
        b = bars.loc[ts_bar]
        ref = float(r["ref_level"])
        rng = max(1e-9, float(b["high"] - b["low"]))
        body = max(1e-9, abs(float(b["close"] - b["open"])))
        lower_wick = max(0.0, min(float(b["open"]), float(b["close"])) - float(b["low"]))
        upper_wick = max(0.0, float(b["high"]) - max(float(b["open"]), float(b["close"])))
        sweep_depth = max(0.0, ref - float(b["low"]))
        reclaim = float(b["close"]) - ref

        pdh = parse_context_value(r.get("context", ""), "pdh")
        pdl = parse_context_value(r.get("context", ""), "pdl")
        prior_mid = (pdh + pdl) / 2 if pd.notna(pdh) and pd.notna(pdl) else float("nan")
        prior_range = pdh - pdl if pd.notna(pdh) and pd.notna(pdl) else float("nan")

        day = ts_bar.strftime("%Y-%m-%d")
        before = bars_day[(bars_day["_day"] == day) & (bars_day.index <= ts_bar)]
        breached = before[before["low"] < ref]
        bars_since_first_breach = int(len(before.loc[breached.index[0]:]) - 1) if not breached.empty else 0

        atr96 = float(b["atr96"]) if pd.notna(b["atr96"]) else float("nan")
        atr_pct = float(b["atr_pct_rank_252"]) if pd.notna(b["atr_pct_rank_252"]) else float("nan")
        h4_close = float(b["h4_close"]) if pd.notna(b.get("h4_close")) else float("nan")
        h4_sma20 = float(b["h4_sma20"]) if pd.notna(b.get("h4_sma20")) else float("nan")
        h4_slope3 = float(b["h4_slope3"]) if pd.notna(b.get("h4_slope3")) else float("nan")

        feat_rows.append({
            "event_bar_utc": ts_bar.isoformat(),
            "event_hour": int(ts_bar.hour),
            "event_session": session_name(int(ts_bar.hour)),
            "event_open": float(b["open"]),
            "event_high": float(b["high"]),
            "event_low": float(b["low"]),
            "event_close": float(b["close"]),
            "event_range": rng,
            "body": body,
            "lower_wick": lower_wick,
            "upper_wick": upper_wick,
            "lower_wick_to_range": lower_wick / rng,
            "lower_wick_to_body": lower_wick / body,
            "close_position_in_range": (float(b["close"]) - float(b["low"])) / rng,
            "sweep_depth": sweep_depth,
            "reclaim_above_ref": reclaim,
            "sweep_depth_atr": sweep_depth / atr96 if pd.notna(atr96) and atr96 > 0 else float("nan"),
            "atr96": atr96,
            "atr_pct_rank_252": atr_pct,
            "pdh": pdh,
            "pdl": pdl,
            "prior_mid": prior_mid,
            "prior_range": prior_range,
            "event_close_below_prior_mid": int(float(b["close"]) < prior_mid) if pd.notna(prior_mid) else 0,
            "event_close_above_prior_mid": int(float(b["close"]) > prior_mid) if pd.notna(prior_mid) else 0,
            "bars_since_first_breach": bars_since_first_breach,
            "h4_close": h4_close,
            "h4_sma20": h4_sma20,
            "h4_slope3": h4_slope3,
            "h4_up_context": int(pd.notna(h4_close) and pd.notna(h4_sma20) and h4_close > h4_sma20),
            "h4_slope_positive": int(pd.notna(h4_slope3) and h4_slope3 > 0),
        })

    return pd.concat([x.reset_index(drop=True), pd.DataFrame(feat_rows).reset_index(drop=True)], axis=1)


def qvals(s: pd.Series) -> Dict[str, float]:
    x = pd.to_numeric(s, errors="coerce").dropna()
    if x.empty:
        return {"q25": 0.0, "q50": 0.0, "q75": 0.0}
    return {"q25": float(x.quantile(0.25)), "q50": float(x.quantile(0.50)), "q75": float(x.quantile(0.75))}


def build_filters(df: pd.DataFrame) -> List[FilterSpec]:
    depth = qvals(df["sweep_depth"])
    reclaim = qvals(df["reclaim_above_ref"])
    wick = qvals(df["lower_wick_to_range"])
    filters: List[FilterSpec] = []

    for sess in ["london", "new_york", "late_us"]:
        filters.append(FilterSpec(f"session_{sess}", f"event_session == {sess}", lambda d, sess=sess: d["event_session"].eq(sess)))

    filters += [
        FilterSpec("session_london_or_ny", "event during London or New York", lambda d: d["event_session"].isin(["london", "new_york"])),
        FilterSpec("sweep_depth_ge_q50", "sweep depth >= median", lambda d, q=depth["q50"]: d["sweep_depth"] >= q),
        FilterSpec("sweep_depth_ge_q75", "sweep depth >= q75", lambda d, q=depth["q75"]: d["sweep_depth"] >= q),
        FilterSpec("sweep_depth_between_q25_q75", "sweep depth between q25 and q75", lambda d, a=depth["q25"], b=depth["q75"]: (d["sweep_depth"] >= a) & (d["sweep_depth"] <= b)),
        FilterSpec("reclaim_ge_q50", "close reclaim above prior low >= median", lambda d, q=reclaim["q50"]: d["reclaim_above_ref"] >= q),
        FilterSpec("reclaim_ge_q75", "close reclaim above prior low >= q75", lambda d, q=reclaim["q75"]: d["reclaim_above_ref"] >= q),
        FilterSpec("lower_wick_ratio_ge_q50", "lower wick/range >= median", lambda d, q=wick["q50"]: d["lower_wick_to_range"] >= q),
        FilterSpec("lower_wick_ratio_ge_q75", "lower wick/range >= q75", lambda d, q=wick["q75"]: d["lower_wick_to_range"] >= q),
        FilterSpec("close_pos_ge_60pct", "close in upper 40% of event candle", lambda d: d["close_position_in_range"] >= 0.60),
        FilterSpec("fast_reclaim_le_1bar", "reclaim within <=1 bar after first breach", lambda d: d["bars_since_first_breach"] <= 1),
        FilterSpec("atr_pct_mid_high", "ATR percentile >= 0.40", lambda d: d["atr_pct_rank_252"] >= 0.40),
        FilterSpec("atr_pct_not_extreme_high", "ATR percentile <= 0.85", lambda d: d["atr_pct_rank_252"] <= 0.85),
        FilterSpec("atr_pct_40_85", "ATR percentile between 0.40 and 0.85", lambda d: (d["atr_pct_rank_252"] >= 0.40) & (d["atr_pct_rank_252"] <= 0.85)),
        FilterSpec("close_below_prior_mid", "event close below previous-day midpoint", lambda d: d["event_close_below_prior_mid"].eq(1)),
        FilterSpec("close_above_prior_mid", "event close above previous-day midpoint", lambda d: d["event_close_above_prior_mid"].eq(1)),
        FilterSpec("h4_up_context", "H4 close above H4 SMA20", lambda d: d["h4_up_context"].eq(1)),
        FilterSpec("h4_slope_positive", "H4 SMA20 slope3 positive", lambda d: d["h4_slope_positive"].eq(1)),
        FilterSpec("h4_up_and_slope_positive", "H4 up and slope positive", lambda d: d["h4_up_context"].eq(1) & d["h4_slope_positive"].eq(1)),
        FilterSpec("london_or_ny_fast_reclaim", "London/NY plus fast reclaim <=1 bar", lambda d: d["event_session"].isin(["london", "new_york"]) & (d["bars_since_first_breach"] <= 1)),
        FilterSpec("london_or_ny_wick_quality", "London/NY plus lower wick/range >= median", lambda d, q=wick["q50"]: d["event_session"].isin(["london", "new_york"]) & (d["lower_wick_to_range"] >= q)),
        FilterSpec("deep_sweep_fast_reclaim", "deep sweep >= median plus fast reclaim <=1 bar", lambda d, q=depth["q50"]: (d["sweep_depth"] >= q) & (d["bars_since_first_breach"] <= 1)),
        FilterSpec("reclaim_strength_wick_quality", "strong reclaim >= median plus wick/range >= median", lambda d, q1=reclaim["q50"], q2=wick["q50"]: (d["reclaim_above_ref"] >= q1) & (d["lower_wick_to_range"] >= q2)),
        FilterSpec("h4_up_london_or_ny", "H4 up context plus London/NY event", lambda d: d["h4_up_context"].eq(1) & d["event_session"].isin(["london", "new_york"])),
        FilterSpec("h4_up_fast_reclaim", "H4 up context plus fast reclaim <=1 bar", lambda d: d["h4_up_context"].eq(1) & (d["bars_since_first_breach"] <= 1)),
    ]
    return filters


def evaluate_filters(df: pd.DataFrame, filters: List[FilterSpec], min_events: int) -> pd.DataFrame:
    rows = []
    baseline_net = metrics(df, "net_x1")
    for fs in filters:
        try:
            mask = fs.predicate(df).fillna(False)
        except Exception:
            continue
        sub = df[mask].copy()
        if len(sub) < max(1, min_events // 2):
            continue
        raw = metrics(sub, "ret_usd")
        net = metrics(sub, "net_x1")
        split = chronological_split_metrics(sub, "net_x1", 0.70)
        pass_basic = (
            net["events"] >= min_events
            and net["total"] > 0
            and net["pf"] >= 1.15
            and net["median"] > 0
            and net["win_rate"] >= 0.51
            and split["test"]["events"] >= max(20, int(min_events * 0.25))
            and split["test"]["total"] > 0
            and split["test"]["pf"] >= 1.05
        )
        rows.append({
            "filter": fs.name,
            "description": fs.description,
            "selected_events": int(len(sub)),
            "coverage": round(float(len(sub) / max(1, len(df))), 6),
            "raw_total": raw["total"], "raw_avg": raw["avg"], "raw_median": raw["median"], "raw_wr": raw["win_rate"], "raw_pf": raw["pf"], "raw_dd": raw["max_dd"],
            "net_total": net["total"], "net_avg": net["avg"], "net_median": net["median"], "net_wr": net["win_rate"], "net_pf": net["pf"], "net_dd": net["max_dd"],
            "net_pos_years": net["pos_years"], "net_years": net["years"],
            "test_net_total": split["test"]["total"], "test_net_median": split["test"]["median"], "test_net_pf": split["test"]["pf"], "test_net_wr": split["test"]["win_rate"],
            "candidate_flag": bool(pass_basic),
            "delta_net_total_vs_baseline": round(net["total"] - baseline_net["total"], 6),
            "delta_net_pf_vs_baseline": round(net["pf"] - baseline_net["pf"], 6),
            "delta_net_median_vs_baseline": round(net["median"] - baseline_net["median"], 6),
        })
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    return out.sort_values(["candidate_flag", "net_pf", "net_median", "net_total", "selected_events"], ascending=[False, False, False, False, False])


def decide(filter_summary: pd.DataFrame) -> Tuple[str, List[str]]:
    if filter_summary.empty:
        return "INCONCLUSIVE_NO_FILTER_RESULTS", ["No filter produced enough rows for evaluation."]
    cands = filter_summary[filter_summary["candidate_flag"] == True]
    if not cands.empty:
        top = cands.iloc[0].to_dict()
        return "FILTER_CANDIDATE_FOUND", [
            f"Top filter `{top['filter']}` passed net-after-cost basic checks.",
            "This permits one focused robustness/replay validation, not EA/paper/live.",
        ]
    top = filter_summary.iloc[0].to_dict()
    if top["net_total"] > 0 and top["net_pf"] > 1.05:
        return "WEAK_FILTER_IMPROVEMENT_ONLY", [
            f"Best filter `{top['filter']}` is net-positive but fails strict candidate thresholds.",
            "Candidate remains cost-sensitive; do not move to EA/replay yet.",
        ]
    return "NO_FILTER_IMPROVEMENT", [
        "No tested behavioral filter rescued the cost-fragile setup.",
        "This rejects this candidate/filter set, not the whole XAUUSD market.",
    ]


def run(db: Path, candidate_csv: Path, out_dir: Path, cost_usd: float, min_events: int) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = now_iso()
    if not candidate_csv.exists():
        raise FileNotFoundError(f"Candidate CSV not found: {candidate_csv}")
    cand = pd.read_csv(candidate_csv)
    conn = connect(db)
    intraday, intraday_source = load_intraday(conn)
    h4 = load_h4(conn, intraday)
    conn.close()

    featured = add_features(cand, intraday, h4, cost_usd)
    filters = build_filters(featured)
    filter_summary = evaluate_filters(featured, filters, min_events)
    final_decision, reasons = decide(filter_summary)
    baseline_raw = metrics(featured, "ret_usd")
    baseline_net = metrics(featured, "net_x1")

    feature_csv = out_dir / "stage14c_candidate_features.csv"
    filter_csv = out_dir / "stage14c_filter_summary.csv"
    json_path = out_dir / "stage14c_behavioral_filter_study.json"
    md_path = out_dir / "stage14c_behavioral_filter_study.md"
    featured.to_csv(feature_csv, index=False)
    filter_summary.to_csv(filter_csv, index=False)

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "inputs": {"db": str(db), "candidate_csv": str(candidate_csv), "cost_usd": float(cost_usd), "min_events": int(min_events)},
        "intraday_source": intraday_source,
        "candidate_rows": int(len(featured)),
        "filters_tested": int(len(filters)),
        "filters_reported": int(len(filter_summary)),
        "baseline_raw": baseline_raw,
        "baseline_net_x1": baseline_net,
        "final_decision": final_decision,
        "reasons": reasons,
        "top_filters": filter_summary.head(10).to_dict(orient="records") if not filter_summary.empty else [],
        "authorization_flags": {"trade_authorization": False, "ea_change_authorization": False, "paper_order_authorization": False, "live_order_authorization": False, "automatic_trading": False},
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    lines = [
        "# Stage 14C Behavioral Filter Study", "",
        f"Generated UTC: `{generated}`", f"Tool version: `{TOOL_VERSION}`", "",
        "> Hard rule: research only. No EA change, no automatic trading, no paper/live authorization.", "",
        "## Inputs",
        f"- db: `{db}`", f"- candidate_csv: `{candidate_csv}`", f"- intraday_source: `{intraday_source}`",
        f"- candidate_rows: `{len(featured)}`", f"- cost_usd: `{cost_usd}`", f"- min_events: `{min_events}`", f"- filters_tested: `{len(filters)}`", "",
        "## Final decision", f"- final_decision: `{final_decision}`", "",
        "## Reasons",
    ]
    for r in reasons:
        lines.append(f"- {r}")
    lines += [
        "", "## Baseline before filters",
        "| Metric set | Events | Total | Avg | Median | WR | PF | DD | Pos years |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        f"| raw | {baseline_raw['events']} | {baseline_raw['total']} | {baseline_raw['avg']} | {baseline_raw['median']} | {baseline_raw['win_rate']} | {baseline_raw['pf']} | {baseline_raw['max_dd']} | {baseline_raw['pos_years']}/{baseline_raw['years']} |",
        f"| net_x1 | {baseline_net['events']} | {baseline_net['total']} | {baseline_net['avg']} | {baseline_net['median']} | {baseline_net['win_rate']} | {baseline_net['pf']} | {baseline_net['max_dd']} | {baseline_net['pos_years']}/{baseline_net['years']} |",
        "", "## Top filters",
        "| Rank | Filter | Events | Coverage | Net total | Net avg | Net median | Net WR | Net PF | Net DD | Test PF | Test total | Candidate |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    if not filter_summary.empty:
        for i, r in enumerate(filter_summary.head(20).to_dict(orient="records"), start=1):
            lines.append(f"| {i} | {r['filter']} | {r['selected_events']} | {r['coverage']} | {r['net_total']} | {r['net_avg']} | {r['net_median']} | {r['net_wr']} | {r['net_pf']} | {r['net_dd']} | {r['test_net_pf']} | {r['test_net_total']} | {r['candidate_flag']} |")
    else:
        lines.append("| 0 | none | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | False |")
    lines += [
        "", "## Interpretation",
        "- `FILTER_CANDIDATE_FOUND` permits one focused robustness/replay validation for the top filter only.",
        "- `WEAK_FILTER_IMPROVEMENT_ONLY` means the behavior may exist but is still not strong enough after cost.",
        "- `NO_FILTER_IMPROVEMENT` rejects this candidate/filter set, not XAUUSD as a market.",
        "- Do not convert any filter directly to EA/paper/live.", "",
        "## Output files",
        f"- feature_csv: `{feature_csv}`", f"- filter_csv: `{filter_csv}`", f"- json: `{json_path}`", f"- md: `{md_path}`",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 14C behavioral filter study: DONE")
    print(f"final_decision={final_decision}")
    if not filter_summary.empty:
        top = filter_summary.iloc[0].to_dict()
        print(f"top_filter={top['filter']} net_pf={top['net_pf']} net_median={top['net_median']} events={top['selected_events']} candidate={top['candidate_flag']}")
    print(f"Report: {md_path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--candidate-csv", default=str(DEFAULT_CANDIDATE))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--cost-usd", type=float, default=0.35)
    p.add_argument("--min-events", type=int, default=80)
    args = p.parse_args()
    return run(Path(args.db), Path(args.candidate_csv), Path(args.out_dir), args.cost_usd, args.min_events)

if __name__ == "__main__":
    raise SystemExit(main())
