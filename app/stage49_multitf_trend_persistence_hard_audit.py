#!/usr/bin/env python3
"""
Stage49 Multi-Timeframe Trend Persistence Hard Audit.

Audits diagnostic survivors from Stage49 on broker-real AMarkets data.
No promotion, EA, paper-live, or live trading is authorized by this script.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import datetime as dt
import json
import math
import os
import sqlite3
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def expand_path(p: str | Path) -> Path:
    return Path(os.path.expanduser(str(p))).resolve()


def iso_to_dt(s: str) -> dt.datetime:
    ss = str(s).strip()
    if ss.endswith("Z"):
        ss = ss[:-1] + "+00:00"
    d = dt.datetime.fromisoformat(ss)
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc)


def dt_to_iso(d: dt.datetime) -> str:
    return d.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def to_epoch(s: str) -> int:
    return int(iso_to_dt(s).timestamp())


def utc_now() -> str:
    return dt_to_iso(dt.datetime.now(dt.timezone.utc))


def safe_float(x, default=None):
    try:
        if x is None or str(x).strip() == "":
            return default
        v = float(x)
        return v if math.isfinite(v) else default
    except Exception:
        return default


def safe_int(x, default=0):
    v = safe_float(x, None)
    return int(v) if v is not None else default


def percentile(vals: List[float], p: float) -> Optional[float]:
    if not vals:
        return None
    xs = sorted(vals)
    if len(xs) == 1:
        return xs[0]
    k = (len(xs) - 1) * (p / 100.0)
    lo = int(math.floor(k)); hi = int(math.ceil(k))
    if lo == hi:
        return xs[lo]
    return xs[lo] * (hi - k) + xs[hi] * (k - lo)


def mean(xs: List[float]) -> Optional[float]:
    return sum(xs) / len(xs) if xs else None


def median(xs: List[float]) -> Optional[float]:
    return statistics.median(xs) if xs else None


def stdev(xs: List[float]) -> float:
    return statistics.stdev(xs) if len(xs) > 1 else 0.0


def t_stat(xs: List[float]) -> Optional[float]:
    if len(xs) < 2:
        return None
    sd = stdev(xs)
    if sd == 0:
        return None
    return mean(xs) / (sd / math.sqrt(len(xs)))


def max_drawdown(cum_returns: List[float]) -> float:
    peak = 0.0
    worst = 0.0
    total = 0.0
    for r in cum_returns:
        total += r
        peak = max(peak, total)
        worst = min(worst, total - peak)
    return worst


@dataclass
class Bars:
    timeframe: str
    times: List[int]
    time_iso: List[str]
    open: List[float]
    high: List[float]
    low: List[float]
    close: List[float]
    spread_cost_bps: List[Optional[float]]


def detect_table(conn: sqlite3.Connection) -> Tuple[str, Dict[str, str]]:
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    candidates = []
    for t in tables:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({t})")]
        low = {c.lower(): c for c in cols}
        if {"timeframe", "open", "high", "low", "close"}.issubset(set(low)) and ("time_utc" in low or "utc_time" in low or "bar_ts_utc" in low):
            candidates.append((t, low))
    if not candidates:
        raise RuntimeError("No compatible bar table found. Expected amarkets_bars or a table with timeframe/time_utc/OHLC columns.")
    # Prefer the fast persistent importer table.
    candidates.sort(key=lambda x: 0 if x[0] == "amarkets_bars" else 1)
    table, low = candidates[0]
    mapping = {
        "time": low.get("time_utc") or low.get("utc_time") or low.get("bar_ts_utc"),
        "timeframe": low["timeframe"],
        "open": low["open"],
        "high": low["high"],
        "low": low["low"],
        "close": low["close"],
        "spread_cost_bps": low.get("spread_cost_bps"),
        "spread_points": low.get("spread_points") or low.get("spread"),
    }
    return table, mapping


def load_bars(conn: sqlite3.Connection, timeframe: str, point_size: float) -> Bars:
    table, m = detect_table(conn)
    cols = [m["time"], m["open"], m["high"], m["low"], m["close"]]
    if m.get("spread_cost_bps"):
        cols.append(m["spread_cost_bps"])
    elif m.get("spread_points"):
        cols.append(m["spread_points"])
    else:
        cols.append("NULL")
    sql = f"SELECT {', '.join(cols)} FROM {table} WHERE UPPER({m['timeframe']})=? ORDER BY {m['time']}"
    rows = conn.execute(sql, (timeframe.upper(),)).fetchall()
    times=[]; time_iso=[]; op=[]; hi=[]; lo=[]; cl=[]; sc=[]
    for row in rows:
        ts, o, h, l, c, spread = row
        try:
            e = to_epoch(ts)
            c = float(c); o = float(o); h = float(h); l = float(l)
        except Exception:
            continue
        if c <= 0 or h < max(o, c, l) or l > min(o, c, h):
            continue
        spread_cost = None
        if spread is not None:
            sp = safe_float(spread, None)
            if sp is not None:
                if m.get("spread_cost_bps"):
                    spread_cost = sp
                else:
                    spread_cost = (sp * point_size / c) * 10000.0
        times.append(e); time_iso.append(dt_to_iso(dt.datetime.fromtimestamp(e, tz=dt.timezone.utc)))
        op.append(o); hi.append(h); lo.append(l); cl.append(c); sc.append(spread_cost)
    return Bars(timeframe, times, time_iso, op, hi, lo, cl, sc)


def load_cost_model(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_candidates(path: Path, max_candidates: Optional[int] = None) -> List[dict]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    rows = [r for r in rows if "SURVIVOR" in str(r.get("decision", "")).upper()]
    rows.sort(key=lambda r: safe_float(r.get("oos_stress_mean_bps"), -1e9), reverse=True)
    if max_candidates:
        rows = rows[:max_candidates]
    return rows


def sma_at(bars: Bars, before_epoch: int, window: int) -> Optional[float]:
    idx = bisect.bisect_left(bars.times, before_epoch) - 1
    if idx < 0 or idx - window + 1 < 0:
        return None
    xs = bars.close[idx-window+1:idx+1]
    return sum(xs) / window


def close_at_or_before(bars: Bars, before_epoch: int) -> Optional[float]:
    idx = bisect.bisect_left(bars.times, before_epoch) - 1
    if idx < 0:
        return None
    return bars.close[idx]


def find_exact_or_next_index(bars: Bars, epoch: int) -> Optional[int]:
    idx = bisect.bisect_left(bars.times, epoch)
    if idx >= len(bars.times):
        return None
    return idx


def compute_candidate_trades(c: dict, m5: Bars, m15: Bars, h1: Bars, base_cost_bps: float, point_size: float) -> List[dict]:
    h1w = safe_int(c.get("h1_range_window"), 72)
    pct = safe_float(c.get("h1_range_percentile"), 85.0)
    m15w = safe_int(c.get("m15_sma_window"), 20)
    m5w = safe_int(c.get("m5_sma_window"), 20)
    horizon = safe_int(c.get("horizon_m5_bars"), 24)
    max_spread_gate = safe_float(c.get("max_spread_cost_bps"), 3.0)
    h1_ranges = [(h1.high[i] - h1.low[i]) / h1.close[i] * 10000.0 if h1.close[i] else 0.0 for i in range(len(h1.times))]
    trades: List[dict] = []
    for i in range(h1w, len(h1.times)):
        threshold = percentile(h1_ranges[i-h1w:i], pct)
        if threshold is None or h1_ranges[i] < threshold:
            continue
        direction = 1 if h1.close[i] > h1.open[i] else (-1 if h1.close[i] < h1.open[i] else 0)
        if direction == 0:
            continue
        entry_epoch = h1.times[i] + 3600  # H1 bar timestamp is assumed to be open time; enter after close.
        m15_close = close_at_or_before(m15, entry_epoch)
        m15_sma = sma_at(m15, entry_epoch, m15w)
        m5_close_prev = close_at_or_before(m5, entry_epoch)
        m5_sma = sma_at(m5, entry_epoch, m5w)
        if m15_close is None or m15_sma is None or m5_close_prev is None or m5_sma is None:
            continue
        if direction == 1 and not (m15_close > m15_sma and m5_close_prev > m5_sma):
            continue
        if direction == -1 and not (m15_close < m15_sma and m5_close_prev < m5_sma):
            continue
        entry_idx = find_exact_or_next_index(m5, entry_epoch)
        if entry_idx is None or entry_idx + horizon >= len(m5.times):
            continue
        entry_spread = m5.spread_cost_bps[entry_idx]
        if entry_spread is None or entry_spread > max_spread_gate:
            continue
        entry_price = m5.close[entry_idx]
        exit_price = m5.close[entry_idx + horizon]
        gross_bps = direction * (exit_price - entry_price) / entry_price * 10000.0
        net_bps = gross_bps - base_cost_bps
        entry_dt = dt.datetime.fromtimestamp(m5.times[entry_idx], tz=dt.timezone.utc)
        trades.append({
            "candidate_id": c.get("candidate_id"),
            "entry_time_utc": dt_to_iso(entry_dt),
            "exit_time_utc": m5.time_iso[entry_idx + horizon],
            "year": entry_dt.year,
            "month": f"{entry_dt.year}-{entry_dt.month:02d}",
            "direction": "LONG" if direction == 1 else "SHORT",
            "entry_price": entry_price,
            "exit_price": exit_price,
            "gross_bps": gross_bps,
            "stress_net_bps": net_bps,
            "entry_spread_cost_bps": entry_spread,
            "h1_range_bps": h1_ranges[i],
            "h1_threshold_bps": threshold,
        })
    return trades


def metric_block(vals: List[float]) -> dict:
    return {
        "count": len(vals),
        "mean_bps": mean(vals),
        "median_bps": median(vals),
        "win_rate": (sum(1 for x in vals if x > 0) / len(vals)) if vals else None,
        "t_stat": t_stat(vals),
        "total_bps": sum(vals) if vals else 0.0,
        "max_drawdown_bps": max_drawdown(vals) if vals else None,
    }


def split_metrics(trades: List[dict], key: str = "stress_net_bps") -> dict:
    vals = [float(t[key]) for t in trades]
    base = metric_block(vals)
    years: Dict[int, List[float]] = {}
    months: Dict[str, List[float]] = {}
    directions: Dict[str, List[float]] = {}
    for t in trades:
        years.setdefault(int(t["year"]), []).append(float(t[key]))
        months.setdefault(str(t["month"]), []).append(float(t[key]))
        directions.setdefault(str(t["direction"]), []).append(float(t[key]))
    year_stats = {str(y): metric_block(v) for y, v in sorted(years.items())}
    direction_stats = {d: metric_block(v) for d, v in directions.items()}
    positive_year_count = sum(1 for v in years.values() if mean(v) is not None and mean(v) > 0)
    negative_year_count = sum(1 for v in years.values() if mean(v) is not None and mean(v) <= 0)
    max_year_share = max((len(v) / len(trades) for v in years.values()), default=0.0)
    max_month_share = max((len(v) / len(trades) for v in months.values()), default=0.0)
    base.update({
        "positive_year_count": positive_year_count,
        "negative_year_count": negative_year_count,
        "max_year_share": max_year_share,
        "max_month_share": max_month_share,
        "year_stats": year_stats,
        "direction_stats": direction_stats,
    })
    return base


def chronological_folds(trades: List[dict], folds: int = 5) -> List[dict]:
    if not trades:
        return []
    out = []
    n = len(trades)
    for k in range(folds):
        a = int(k * n / folds)
        b = int((k + 1) * n / folds)
        chunk = trades[a:b]
        m = metric_block([float(t["stress_net_bps"]) for t in chunk])
        m["fold"] = k + 1
        m["start"] = chunk[0]["entry_time_utc"] if chunk else None
        m["end"] = chunk[-1]["entry_time_utc"] if chunk else None
        out.append(m)
    return out


def decluster(trades: List[dict], min_gap_bars: int, bar_seconds: int = 300) -> List[dict]:
    min_gap = min_gap_bars * bar_seconds
    out = []
    last_by_direction: Dict[str, int] = {}
    for t in trades:
        e = to_epoch(t["entry_time_utc"])
        d = t["direction"]
        if d in last_by_direction and e - last_by_direction[d] < min_gap:
            continue
        out.append(t)
        last_by_direction[d] = e
    return out


def audit_candidate(c: dict, trades: List[dict], stress_cost_bps: float, horizon: int) -> dict:
    # Base trades are already net of stress cost. For cost multipliers, subtract additional cost.
    base = split_metrics(trades)
    n = len(trades)
    is_cut = int(n * 0.8)
    is_trades = trades[:is_cut]
    oos_trades = trades[is_cut:]
    is_m = split_metrics(is_trades)
    oos_m = split_metrics(oos_trades)
    folds = chronological_folds(trades, 5)
    fold_means = [x.get("mean_bps") for x in folds if x.get("mean_bps") is not None]
    worst_fold_mean = min(fold_means) if fold_means else None
    decl = decluster(trades, horizon)
    decl_m = split_metrics(decl)
    x15_vals = [float(t["stress_net_bps"]) - stress_cost_bps * 0.5 for t in trades]
    x2_vals = [float(t["stress_net_bps"]) - stress_cost_bps for t in trades]
    x2_oos_vals = [float(t["stress_net_bps"]) - stress_cost_bps for t in oos_trades]
    x15 = metric_block(x15_vals)
    x2 = metric_block(x2_vals)
    x2_oos = metric_block(x2_oos_vals)
    reasons = []
    if base["count"] < 500: reasons.append("trade_count_lt_500")
    if oos_m["count"] < 100: reasons.append("oos_count_lt_100")
    if (base["mean_bps"] or -1e9) <= 0: reasons.append("mean_not_positive")
    if (base["win_rate"] or 0) < 0.52: reasons.append("win_rate_lt_52pct")
    if (oos_m["mean_bps"] or -1e9) <= 0: reasons.append("oos_mean_not_positive")
    if (oos_m["win_rate"] or 0) < 0.52: reasons.append("oos_win_rate_lt_52pct")
    if base["negative_year_count"] > 0: reasons.append("has_negative_year")
    if base["max_year_share"] > 0.35: reasons.append("year_concentration_gt_35pct")
    if base["max_month_share"] > 0.16: reasons.append("month_concentration_gt_16pct")
    if worst_fold_mean is None or worst_fold_mean <= 0: reasons.append("worst_chrono_fold_not_positive")
    if (x15["mean_bps"] or -1e9) <= 0: reasons.append("cost_x1_5_mean_not_positive")
    if (x2["mean_bps"] or -1e9) <= 0: reasons.append("cost_x2_mean_not_positive")
    if (x2_oos["mean_bps"] or -1e9) <= 0: reasons.append("cost_x2_oos_mean_not_positive")
    if decl_m["count"] < 250: reasons.append("declustered_count_lt_250")
    if (decl_m["mean_bps"] or -1e9) <= 0: reasons.append("declustered_mean_not_positive")
    if (decl_m["win_rate"] or 0) < 0.52: reasons.append("declustered_win_rate_lt_52pct")
    # Require both directions not to be catastrophically weak if present with enough samples.
    for direction, dm in base["direction_stats"].items():
        if dm["count"] >= 100 and (dm["mean_bps"] or -1e9) <= 0:
            reasons.append(f"{direction.lower()}_direction_mean_not_positive")
    decision = "HARD_AUDIT_PASS_NO_PROMOTION" if not reasons else "HARD_AUDIT_NO_PASS"
    return {
        "candidate_id": c.get("candidate_id"),
        "h1_range_window": safe_int(c.get("h1_range_window")),
        "h1_range_percentile": safe_float(c.get("h1_range_percentile")),
        "m15_sma_window": safe_int(c.get("m15_sma_window")),
        "m5_sma_window": safe_int(c.get("m5_sma_window")),
        "horizon_m5_bars": horizon,
        "trade_count": base["count"],
        "mean_bps": base["mean_bps"],
        "median_bps": base["median_bps"],
        "win_rate": base["win_rate"],
        "t_stat": base["t_stat"],
        "total_bps": base["total_bps"],
        "max_drawdown_bps": base["max_drawdown_bps"],
        "is_count": is_m["count"],
        "is_mean_bps": is_m["mean_bps"],
        "is_win_rate": is_m["win_rate"],
        "oos_count": oos_m["count"],
        "oos_mean_bps": oos_m["mean_bps"],
        "oos_win_rate": oos_m["win_rate"],
        "positive_year_count": base["positive_year_count"],
        "negative_year_count": base["negative_year_count"],
        "max_year_share": base["max_year_share"],
        "max_month_share": base["max_month_share"],
        "worst_fold_mean_bps": worst_fold_mean,
        "cost_x1_5_mean_bps": x15["mean_bps"],
        "cost_x2_mean_bps": x2["mean_bps"],
        "cost_x2_oos_mean_bps": x2_oos["mean_bps"],
        "declustered_count": decl_m["count"],
        "declustered_mean_bps": decl_m["mean_bps"],
        "declustered_win_rate": decl_m["win_rate"],
        "direction_stats": base["direction_stats"],
        "folds": folds,
        "decision": decision,
        "failure_reasons": reasons,
    }


def fmt4(x):
    return "NA" if x is None else f"{float(x):.4f}"


def write_report(summary: dict, audit_rows: List[dict]) -> str:
    lines = [
        "# Stage49 MultiTF Trend Persistence Hard Audit",
        "",
        f"- status: `{summary['status']}`",
        f"- next_allowed_step: `{summary['next_allowed_step']}`",
        "- promotion: `NO_GO`",
        "- EA: `NO_GO`",
        "- paper_live: `NO_GO`",
        "- live: `NO_GO`",
        "",
        "## Inputs",
        "",
        f"- db: `{summary['db']}`",
        f"- candidates_csv: `{summary['candidates_csv']}`",
        f"- cost_model: `{summary['cost_model']}`",
        f"- stress_cost_bps: `{summary['stress_cost_bps']:.4f}`",
        "",
        "## Result",
        "",
        f"- diagnostic_candidates_loaded: `{summary['diagnostic_candidates_loaded']}`",
        f"- audited_candidates: `{summary['audited_candidates']}`",
        f"- hard_audit_pass_count: `{summary['hard_audit_pass_count']}`",
        "",
        "## Top audited candidates",
        "",
    ]
    for r in audit_rows[:10]:
        lines.append(
            f"- `{r['candidate_id']}` trades={r['trade_count']} mean={fmt4(r['mean_bps'])} "
            f"oos_mean={fmt4(r['oos_mean_bps'])} decl_mean={fmt4(r['declustered_mean_bps'])} "
            f"x2_mean={fmt4(r['cost_x2_mean_bps'])} decision=`{r['decision']}` notes=`{';'.join(r['failure_reasons'])}`"
        )
    lines.extend([
        "",
        "## Interpretation",
        "",
        "This is a hard audit only. Passing this audit would still not authorize EA, paper-live, or live trading; it would only justify the next controlled forward-shadow design step.",
    ])
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Hard audit Stage49 MultiTF diagnostic survivors")
    ap.add_argument("--root", default=".")
    ap.add_argument("--db", default="data/broker_normalized/amarkets_multitf.sqlite")
    ap.add_argument("--candidates", default="reports/stage49_broker_multitf/stage49_multitf_trend_persistence_candidates.csv")
    ap.add_argument("--cost-model", default="reports/stage48f/stage48f_cost_model.json")
    ap.add_argument("--out", default="reports/stage49_broker_multitf")
    ap.add_argument("--point-size", type=float, default=0.01)
    ap.add_argument("--max-candidates", type=int, default=24)
    args = ap.parse_args(argv)

    root = expand_path(args.root)
    db_path = root / args.db
    cand_path = root / args.candidates
    cost_path = root / args.cost_model
    out_dir = root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    cost = load_cost_model(cost_path)
    stress_cost = safe_float(cost.get("stress_cost_bps"), None)
    if stress_cost is None:
        stress_cost = safe_float(cost.get("recommended_usage", {}).get("stress_scan_cost_bps"), 3.0)
    candidates = load_candidates(cand_path, args.max_candidates)

    conn = sqlite3.connect(str(db_path))
    m5 = load_bars(conn, "M5", args.point_size)
    m15 = load_bars(conn, "M15", args.point_size)
    h1 = load_bars(conn, "H1", args.point_size)
    conn.close()

    audit_rows = []
    sample_events = []
    for c in candidates:
        horizon = safe_int(c.get("horizon_m5_bars"), 24)
        trades = compute_candidate_trades(c, m5, m15, h1, stress_cost, args.point_size)
        res = audit_candidate(c, trades, stress_cost, horizon)
        audit_rows.append(res)
        for t in trades[:5]:
            sample_events.append(t)
    audit_rows.sort(key=lambda r: (r["decision"] != "HARD_AUDIT_PASS_NO_PROMOTION", -(r.get("oos_mean_bps") or -1e9)))
    pass_count = sum(1 for r in audit_rows if r["decision"] == "HARD_AUDIT_PASS_NO_PROMOTION")
    status = "HARD_AUDIT_PASS_SURVIVORS_NO_PROMOTION" if pass_count else "HARD_AUDIT_COMPLETE_NO_PASS_NO_PROMOTION"
    next_step = "FORWARD_SHADOW_DESIGN_NO_PROMOTION" if pass_count else "ARCHIVE_OR_REDESIGN_THESIS_NO_PROMOTION"
    summary = {
        "stage": "Stage49B_MULTITF_TREND_PERSISTENCE_HARD_AUDIT",
        "patch": "Stage49B_FAST_PERSISTENT_IMPORTER_AND_HARD_AUDIT",
        "status": status,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "next_allowed_step": next_step,
        "db": str(db_path),
        "candidates_csv": str(cand_path),
        "cost_model": str(cost_path),
        "rows": {"M5": len(m5.times), "M15": len(m15.times), "H1": len(h1.times)},
        "stress_cost_bps": stress_cost,
        "diagnostic_candidates_loaded": len(candidates),
        "audited_candidates": len(audit_rows),
        "hard_audit_pass_count": pass_count,
        "top_audited_candidates": audit_rows[:10],
        "generated_utc": utc_now(),
    }
    (out_dir / "stage49_multitf_trend_persistence_hard_audit_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out_dir / "stage49_multitf_trend_persistence_hard_audit_report.md").write_text(write_report(summary, audit_rows), encoding="utf-8")
    # Flatten selected fields for CSV.
    with (out_dir / "stage49_multitf_trend_persistence_hard_audit_candidates.csv").open("w", newline="", encoding="utf-8") as f:
        fields = [
            "candidate_id", "h1_range_window", "h1_range_percentile", "m15_sma_window", "m5_sma_window", "horizon_m5_bars",
            "trade_count", "mean_bps", "win_rate", "oos_count", "oos_mean_bps", "oos_win_rate",
            "positive_year_count", "negative_year_count", "max_year_share", "max_month_share", "worst_fold_mean_bps",
            "cost_x1_5_mean_bps", "cost_x2_mean_bps", "cost_x2_oos_mean_bps", "declustered_count", "declustered_mean_bps", "declustered_win_rate",
            "decision", "failure_reasons"
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in audit_rows:
            row = {k: r.get(k, "") for k in fields}
            row["failure_reasons"] = ";".join(r.get("failure_reasons", []))
            w.writerow(row)
    with (out_dir / "stage49_multitf_trend_persistence_hard_audit_event_sample.csv").open("w", newline="", encoding="utf-8") as f:
        if sample_events:
            w = csv.DictWriter(f, fieldnames=list(sample_events[0].keys()))
            w.writeheader(); w.writerows(sample_events[:500])
        else:
            w = csv.writer(f); w.writerow(["empty"])
    print(json.dumps({"stage": summary["stage"], "status": status, "hard_audit_pass_count": pass_count, "out": str(out_dir)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
