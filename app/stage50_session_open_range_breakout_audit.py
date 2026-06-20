#!/usr/bin/env python3
"""
Stage50 broker-real session open range breakout audit.

Distinct thesis after Stage49B failure:
- fixed UTC session opening ranges on AMarkets broker-real M5
- optional M15 trend confirmation using closed bars only
- Stage48F broker-real stress cost and spread gate
- diagnostic and hard-audit style gates in one executable

No promotion, EA, paper-live, or live authorization is granted by this script.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

UTC = timezone.utc

TF_ALIASES = {
    "M1": {"m1", "1m", "1min", "minute1"},
    "M5": {"m5", "5m", "5min", "minute5"},
    "M15": {"m15", "15m", "15min", "minute15"},
    "M30": {"m30", "30m", "30min", "minute30"},
    "H1": {"h1", "1h", "60m", "60min", "hour1"},
}

TS_COLS = ["time_utc", "utc_time", "timestamp", "datetime", "bar_ts_utc", "time"]
OPEN_COLS = ["open", "<open>"]
HIGH_COLS = ["high", "<high>"]
LOW_COLS = ["low", "<low>"]
CLOSE_COLS = ["close", "<close>"]
SPREAD_COLS = ["spread_points", "spread", "<spread>"]
TF_COLS = ["timeframe", "tf", "interval"]

@dataclass
class Bar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    spread_points: Optional[float]


def parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        pass
    for fmt in ("%Y.%m.%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y.%m.%d", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt).replace(tzinfo=UTC)
            return dt
        except Exception:
            continue
    return None


def norm_col(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def pick_col(cols: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    nmap = {norm_col(c): c for c in cols}
    for cand in candidates:
        if norm_col(cand) in nmap:
            return nmap[norm_col(cand)]
    # angle-bracket columns may be stored without brackets by importer
    for cand in candidates:
        cc = norm_col(cand).strip("<>")
        if cc in nmap:
            return nmap[cc]
    return None


def to_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        s = str(x).strip().replace(",", "")
        if s == "":
            return None
        v = float(s)
        if not math.isfinite(v):
            return None
        return v
    except Exception:
        return None


def table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({quote_ident(table)})").fetchall()]


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def table_row_count(conn: sqlite3.Connection, table: str) -> int:
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {quote_ident(table)}").fetchone()[0])
    except Exception:
        return 0


def tf_matches_value(value: Any, tf: str) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in TF_ALIASES.get(tf.upper(), {tf.lower()})


def table_name_matches_tf(table: str, tf: str) -> bool:
    t = table.lower()
    aliases = TF_ALIASES.get(tf.upper(), {tf.lower()})
    return any(a in t for a in aliases)


def discover_table(conn: sqlite3.Connection, tf: str) -> Tuple[str, Dict[str, Optional[str]], bool]:
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    best = None
    best_score = -1
    best_map = None
    best_has_tf = False
    for table in tables:
        cols = table_columns(conn, table)
        if not cols:
            continue
        cmap = {
            "ts": pick_col(cols, TS_COLS),
            "open": pick_col(cols, OPEN_COLS),
            "high": pick_col(cols, HIGH_COLS),
            "low": pick_col(cols, LOW_COLS),
            "close": pick_col(cols, CLOSE_COLS),
            "spread": pick_col(cols, SPREAD_COLS),
            "timeframe": pick_col(cols, TF_COLS),
        }
        required = [cmap["ts"], cmap["open"], cmap["high"], cmap["low"], cmap["close"]]
        if not all(required):
            continue
        score = 100
        if cmap["spread"]:
            score += 20
        if cmap["timeframe"]:
            score += 30
        if table_name_matches_tf(table, tf):
            score += 25
        score += min(table_row_count(conn, table) // 1000, 50)
        if score > best_score:
            best = table
            best_score = score
            best_map = cmap
            best_has_tf = bool(cmap["timeframe"])
    if not best or not best_map:
        raise RuntimeError(f"Could not discover OHLC table for {tf}")
    return best, best_map, best_has_tf


def load_bars(conn: sqlite3.Connection, tf: str, limit: Optional[int] = None) -> Tuple[List[Bar], Dict[str, Any]]:
    table, cmap, has_tf = discover_table(conn, tf)
    cols = [cmap[k] for k in ("ts", "open", "high", "low", "close", "spread", "timeframe") if cmap.get(k)]
    qcols = ", ".join(quote_ident(c) for c in cols)
    sql = f"SELECT {qcols} FROM {quote_ident(table)}"
    params: List[Any] = []
    # Use SQL timeframe filter only if a column is present. Otherwise table-name discovery decides.
    if has_tf and cmap["timeframe"]:
        aliases = sorted(TF_ALIASES.get(tf.upper(), {tf.lower()}))
        placeholders = ",".join("?" for _ in aliases)
        sql += f" WHERE lower({quote_ident(cmap['timeframe'])}) IN ({placeholders})"
        params = aliases
    sql += f" ORDER BY {quote_ident(cmap['ts'])}"
    if limit:
        sql += f" LIMIT {int(limit)}"
    cur = conn.execute(sql, params)
    idx = {c: i for i, c in enumerate(cols)}
    bars: List[Bar] = []
    bad = 0
    for row in cur:
        try:
            ts = parse_dt(row[idx[cmap["ts"]]])
            o = to_float(row[idx[cmap["open"]]])
            h = to_float(row[idx[cmap["high"]]])
            l = to_float(row[idx[cmap["low"]]])
            c = to_float(row[idx[cmap["close"]]])
            sp = to_float(row[idx[cmap["spread"]]]) if cmap.get("spread") else None
            if ts is None or o is None or h is None or l is None or c is None:
                bad += 1
                continue
            if not (h >= max(o, c, l) and l <= min(o, c, h)):
                bad += 1
                continue
            bars.append(Bar(ts, o, h, l, c, sp))
        except Exception:
            bad += 1
    # remove duplicate timestamps, keep last by order
    by_ts = {b.ts: b for b in bars}
    bars = sorted(by_ts.values(), key=lambda b: b.ts)
    meta = {"table": table, "mapping": cmap, "rows": len(bars), "bad_rows": bad, "has_timeframe_col": has_tf}
    return bars, meta


def rolling_sma(values: List[float], window: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= window:
            s -= values[i-window]
        if i >= window - 1:
            out[i] = s / window
    return out


def compute_m15_trend(m15: List[Bar], window: int) -> Dict[datetime, str]:
    closes = [b.close for b in m15]
    sma = rolling_sma(closes, window)
    trend = {}
    for i, b in enumerate(m15):
        if sma[i] is None:
            continue
        if b.close > sma[i]:
            trend[b.ts] = "LONG"
        elif b.close < sma[i]:
            trend[b.ts] = "SHORT"
        else:
            trend[b.ts] = "FLAT"
    return trend


def latest_trend_before(trend: Dict[datetime, str], ts: datetime) -> Optional[str]:
    # trend dict is reasonably small; binary-friendly sorted keys cached outside would be faster, but adequate for this audit.
    # replaced by sorted key search in evaluate.
    return None


def pct_bps(a: float, b: float) -> float:
    return (a - b) / b * 10000.0 if b else 0.0


def stats(vals: Sequence[float]) -> Dict[str, Any]:
    if not vals:
        return {"count": 0, "mean_bps": None, "median_bps": None, "win_rate": None, "t_stat": None, "total_bps": 0.0, "max_drawdown_bps": 0.0}
    m = mean(vals)
    sd = pstdev(vals) if len(vals) > 1 else 0.0
    t = m / (sd / math.sqrt(len(vals))) if sd > 0 and len(vals) > 1 else None
    eq = 0.0
    peak = 0.0
    maxdd = 0.0
    for v in vals:
        eq += v
        peak = max(peak, eq)
        maxdd = min(maxdd, eq - peak)
    return {
        "count": len(vals),
        "mean_bps": m,
        "median_bps": median(vals),
        "win_rate": sum(1 for v in vals if v > 0) / len(vals),
        "t_stat": t,
        "total_bps": sum(vals),
        "max_drawdown_bps": maxdd,
    }


def chronological_folds(vals: Sequence[Tuple[datetime, float]], n: int = 5) -> List[Dict[str, Any]]:
    vals = sorted(vals, key=lambda x: x[0])
    if not vals:
        return []
    out = []
    size = max(1, len(vals) // n)
    for i in range(n):
        chunk = vals[i*size:] if i == n-1 else vals[i*size:(i+1)*size]
        if not chunk:
            continue
        st = stats([v for _, v in chunk])
        st.update({"fold": i+1, "start": chunk[0][0].isoformat().replace("+00:00", "Z"), "end": chunk[-1][0].isoformat().replace("+00:00", "Z")})
        out.append(st)
    return out


def year_month_stats(events: List[Dict[str, Any]]) -> Tuple[int, int, float, float]:
    by_year: Dict[int, List[float]] = {}
    by_month: Dict[str, int] = {}
    for e in events:
        ts = e["entry_ts"]
        by_year.setdefault(ts.year, []).append(e["net_bps"])
        by_month[f"{ts.year:04d}-{ts.month:02d}"] = by_month.get(f"{ts.year:04d}-{ts.month:02d}", 0) + 1
    pos = sum(1 for vs in by_year.values() if mean(vs) > 0)
    neg = sum(1 for vs in by_year.values() if mean(vs) <= 0)
    total = len(events) or 1
    max_year_share = max((len(vs) / total for vs in by_year.values()), default=0.0)
    max_month_share = max((c / total for c in by_month.values()), default=0.0)
    return pos, neg, max_year_share, max_month_share


def load_cost_model(path: Path) -> Dict[str, float]:
    data = json.loads(path.read_text(encoding="utf-8"))
    # support both wrapped and flat structures
    return {
        "stress_cost_bps": float(data.get("stress_cost_bps") or data.get("recommended_usage", {}).get("stress_scan_cost_bps") or data.get("recommended_cost_bps") or 3.0),
        "extreme_cost_bps": float(data.get("extreme_cost_bps") or data.get("recommended_usage", {}).get("extreme_spread_filter_reference_bps") or 3.1),
        "default_cost_bps": float(data.get("recommended_cost_bps") or data.get("recommended_usage", {}).get("default_scan_cost_bps") or 3.0),
    }


def evaluate_candidate(
    m5: List[Bar],
    m15_trend_keys: List[datetime],
    m15_trend: Dict[datetime, str],
    point_size: float,
    stress_cost_bps: float,
    extreme_spread_gate_bps: float,
    session_name: str,
    session_hour: int,
    range_bars: int,
    breakout_window_bars: int,
    horizon_bars: int,
    buffer_bps: float,
    m15_window: int,
    require_m15: bool,
) -> Dict[str, Any]:
    by_date: Dict[str, List[Tuple[int, Bar]]] = {}
    for i, b in enumerate(m5):
        if b.ts.hour < session_hour or b.ts.hour >= session_hour + 6:
            continue
        if b.ts.hour == session_hour and b.ts.minute < 0:
            continue
        key = b.ts.date().isoformat()
        by_date.setdefault(key, []).append((i, b))
    events: List[Dict[str, Any]] = []
    m15_keys = m15_trend_keys
    for _, pairs in sorted(by_date.items()):
        pairs = sorted(pairs, key=lambda x: x[1].ts)
        # select contiguous-ish bars starting at first bar >= session_hour
        if len(pairs) < range_bars + 2:
            continue
        range_pairs = pairs[:range_bars]
        r_high = max(b.high for _, b in range_pairs)
        r_low = min(b.low for _, b in range_pairs)
        r_mid = (r_high + r_low) / 2
        after = pairs[range_bars:range_bars + breakout_window_bars]
        chosen: Optional[Tuple[int, Bar, str]] = None
        for idx, b in after:
            buf_price = b.close * buffer_bps / 10000.0
            direction = None
            if b.close > r_high + buf_price:
                direction = "LONG"
            elif b.close < r_low - buf_price:
                direction = "SHORT"
            if not direction:
                continue
            # spread gate at entry bar
            if b.spread_points is not None:
                sp_cost = (b.spread_points * point_size) / b.close * 10000.0
                if sp_cost > extreme_spread_gate_bps:
                    continue
            if require_m15:
                # latest M15 trend strictly before or at entry timestamp
                import bisect
                j = bisect.bisect_right(m15_keys, b.ts) - 1
                if j < 0:
                    continue
                tr = m15_trend.get(m15_keys[j])
                if tr != direction:
                    continue
            chosen = (idx, b, direction)
            break
        if not chosen:
            continue
        idx, entry, direction = chosen
        exit_idx = idx + horizon_bars
        if exit_idx >= len(m5):
            continue
        exit_bar = m5[exit_idx]
        gross = pct_bps(exit_bar.close, entry.close)
        if direction == "SHORT":
            gross = -gross
        net = gross - stress_cost_bps
        events.append({
            "candidate_id": "",
            "session": session_name,
            "entry_ts": entry.ts,
            "exit_ts": exit_bar.ts,
            "direction": direction,
            "entry_price": entry.close,
            "exit_price": exit_bar.close,
            "gross_bps": gross,
            "net_bps": net,
            "range_high": r_high,
            "range_low": r_low,
            "range_bps": (r_high-r_low)/r_mid*10000.0 if r_mid else 0.0,
            "spread_points": entry.spread_points,
        })
    vals = [e["net_bps"] for e in events]
    st = stats(vals)
    # IS/OOS chronological 80/20
    events_sorted = sorted(events, key=lambda e: e["entry_ts"])
    cut = int(len(events_sorted)*0.8)
    is_events = events_sorted[:cut]
    oos_events = events_sorted[cut:]
    is_st = stats([e["net_bps"] for e in is_events])
    oos_st = stats([e["net_bps"] for e in oos_events])
    folds = chronological_folds([(e["entry_ts"], e["net_bps"]) for e in events_sorted], 5)
    pos_y, neg_y, max_y_share, max_m_share = year_month_stats(events_sorted)
    direction_stats = {d: stats([e["net_bps"] for e in events_sorted if e["direction"] == d]) for d in ("LONG", "SHORT")}
    cost_x15_vals = [v - stress_cost_bps*0.5 for v in vals]
    cost_x2_vals = [v - stress_cost_bps for v in vals]
    # hard decision
    failure = []
    if st["count"] < 250: failure.append("trade_count_lt_250")
    if (st["mean_bps"] or -1) <= 0: failure.append("mean_not_positive")
    if (st["win_rate"] or 0) < 0.52: failure.append("win_rate_lt_52pct")
    if (oos_st["mean_bps"] or -1) <= 0: failure.append("oos_mean_not_positive")
    if (oos_st["win_rate"] or 0) < 0.52: failure.append("oos_win_rate_lt_52pct")
    if neg_y > 0: failure.append("has_negative_year")
    if any((f.get("mean_bps") or -1) <= 0 for f in folds): failure.append("worst_chrono_fold_not_positive")
    if mean(cost_x15_vals) <= 0 if cost_x15_vals else True: failure.append("cost_x1_5_mean_not_positive")
    if mean(cost_x2_vals) <= 0 if cost_x2_vals else True: failure.append("cost_x2_mean_not_positive")
    if max_y_share > 0.40: failure.append("max_year_share_gt_40pct")
    decision = "HARD_AUDIT_PASS_NEEDS_FORWARD_SHADOW_DESIGN_NO_PROMOTION" if not failure else "HARD_AUDIT_NO_PASS"
    candidate_id = f"S50_ORB_{session_name.upper()}_R{range_bars}_W{breakout_window_bars}_B{int(buffer_bps)}_M15{m15_window if require_m15 else 0}_H{horizon_bars}"
    for e in events:
        e["candidate_id"] = candidate_id
    result = {
        "candidate_id": candidate_id,
        "session": session_name,
        "session_hour_utc": session_hour,
        "range_bars": range_bars,
        "breakout_window_bars": breakout_window_bars,
        "buffer_bps": buffer_bps,
        "m15_sma_window": m15_window if require_m15 else 0,
        "horizon_m5_bars": horizon_bars,
        "trade_count": st["count"],
        "mean_bps": st["mean_bps"],
        "median_bps": st["median_bps"],
        "win_rate": st["win_rate"],
        "t_stat": st["t_stat"],
        "total_bps": st["total_bps"],
        "max_drawdown_bps": st["max_drawdown_bps"],
        "is_count": is_st["count"],
        "is_mean_bps": is_st["mean_bps"],
        "is_win_rate": is_st["win_rate"],
        "oos_count": oos_st["count"],
        "oos_mean_bps": oos_st["mean_bps"],
        "oos_win_rate": oos_st["win_rate"],
        "positive_year_count": pos_y,
        "negative_year_count": neg_y,
        "max_year_share": max_y_share,
        "max_month_share": max_m_share,
        "worst_fold_mean_bps": min((f.get("mean_bps") for f in folds if f.get("mean_bps") is not None), default=None),
        "cost_x1_5_mean_bps": mean(cost_x15_vals) if cost_x15_vals else None,
        "cost_x2_mean_bps": mean(cost_x2_vals) if cost_x2_vals else None,
        "direction_stats": direction_stats,
        "folds": folds,
        "decision": decision,
        "failure_reasons": failure,
    }
    return {"summary": result, "events": events_sorted[:200]}


def write_csv(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            out = {}
            for k in fields:
                v = r.get(k)
                if isinstance(v, datetime):
                    v = v.isoformat().replace("+00:00", "Z")
                out[k] = v
            w.writerow(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--db", default="data/broker_normalized/amarkets_multitf.sqlite")
    ap.add_argument("--cost-model", default="reports/stage48f/stage48f_cost_model.json")
    ap.add_argument("--point-size", type=float, default=0.01)
    ap.add_argument("--out", default="reports/stage50_session_open_range")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    db_path = (root / args.db).resolve() if not os.path.isabs(args.db) else Path(args.db)
    cost_path = (root / args.cost_model).resolve() if not os.path.isabs(args.cost_model) else Path(args.cost_model)
    out = (root / args.out).resolve() if not os.path.isabs(args.out) else Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    costs = load_cost_model(cost_path)
    conn = sqlite3.connect(str(db_path))
    m5, m5_meta = load_bars(conn, "M5")
    m15, m15_meta = load_bars(conn, "M15")
    if not m5 or not m15:
        raise RuntimeError("M5 and M15 bars are required")

    # Precompute trend maps by M15 SMA window.
    trend_maps: Dict[int, Tuple[List[datetime], Dict[datetime, str]]] = {}
    for win in (20, 40):
        tr = compute_m15_trend(m15, win)
        keys = sorted(tr.keys())
        trend_maps[win] = (keys, tr)

    grid = []
    sessions = [("london", 7), ("new_york", 13)]
    for session_name, session_hour in sessions:
        for range_bars in (6, 12):
            for breakout_window_bars in (12, 24):
                for buffer_bps in (0.0, 5.0):
                    for m15_window in (20, 40):
                        for horizon in (12, 24, 48):
                            grid.append((session_name, session_hour, range_bars, breakout_window_bars, horizon, buffer_bps, m15_window, True))

    candidates: List[Dict[str, Any]] = []
    sample_events: List[Dict[str, Any]] = []
    for (session_name, session_hour, range_bars, breakout_window_bars, horizon, buffer_bps, m15_window, require_m15) in grid:
        keys, tr = trend_maps[m15_window]
        res = evaluate_candidate(
            m5=m5,
            m15_trend_keys=keys,
            m15_trend=tr,
            point_size=args.point_size,
            stress_cost_bps=costs["stress_cost_bps"],
            extreme_spread_gate_bps=costs["extreme_cost_bps"],
            session_name=session_name,
            session_hour=session_hour,
            range_bars=range_bars,
            breakout_window_bars=breakout_window_bars,
            horizon_bars=horizon,
            buffer_bps=buffer_bps,
            m15_window=m15_window,
            require_m15=require_m15,
        )
        candidates.append(res["summary"])
        if len(sample_events) < 200:
            sample_events.extend(res["events"][: max(0, 200-len(sample_events))])

    candidates.sort(key=lambda r: ((r.get("decision") or ""), -(r.get("oos_mean_bps") or -1e9), -(r.get("mean_bps") or -1e9)))
    pass_count = sum(1 for c in candidates if c["decision"].startswith("HARD_AUDIT_PASS"))
    status = "SESSION_OPEN_RANGE_HARD_AUDIT_PASS_NEEDS_FORWARD_SHADOW_NO_PROMOTION" if pass_count else "SESSION_OPEN_RANGE_HARD_AUDIT_COMPLETE_NO_PASS_NO_PROMOTION"
    next_step = "FORWARD_SHADOW_DESIGN_NO_PROMOTION" if pass_count else "ARCHIVE_OR_REDESIGN_THESIS_NO_PROMOTION"

    summary = {
        "stage": "Stage50_BROKER_REAL_SESSION_OPEN_RANGE_BREAKOUT_AUDIT",
        "status": status,
        "promotion": "NO_GO", "EA": "NO_GO", "paper_live": "NO_GO", "live": "NO_GO",
        "next_allowed_step": next_step,
        "db": str(db_path),
        "cost_model": str(cost_path),
        "rows": {"M5": len(m5), "M15": len(m15)},
        "m5_meta": m5_meta,
        "m15_meta": m15_meta,
        "costs": costs,
        "grid_candidate_count": len(candidates),
        "hard_audit_pass_count": pass_count,
        "top_candidates": candidates[:10],
    }

    (out / "stage50_session_open_range_breakout_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    report_lines = [
        "# Stage50 Broker-Real Session Open Range Breakout Audit",
        "",
        f"- status: `{status}`",
        f"- next_allowed_step: `{next_step}`",
        "- promotion: `NO_GO`",
        "- EA: `NO_GO`",
        "- paper_live: `NO_GO`",
        "- live: `NO_GO`",
        "",
        "## Inputs",
        f"- M5 rows: `{len(m5)}`",
        f"- M15 rows: `{len(m15)}`",
        f"- stress_cost_bps: `{costs['stress_cost_bps']:.4f}`",
        f"- extreme_spread_gate_bps: `{costs['extreme_cost_bps']:.4f}`",
        "",
        "## Top candidates",
    ]
    for c in candidates[:10]:
        report_lines.append(f"- `{c['candidate_id']}` trades=`{c['trade_count']}` mean=`{c.get('mean_bps')}` oos_mean=`{c.get('oos_mean_bps')}` decision=`{c['decision']}` notes=`{';'.join(c['failure_reasons'])}`")
    report_lines += ["", "## Interpretation", "This is a broker-real hard-audit style diagnostic. It does not authorize promotion, EA, paper-live, or live trading."]
    (out / "stage50_session_open_range_breakout_report.md").write_text("\n".join(report_lines), encoding="utf-8")

    flat_fields = [
        "candidate_id","session","session_hour_utc","range_bars","breakout_window_bars","buffer_bps","m15_sma_window","horizon_m5_bars",
        "trade_count","mean_bps","median_bps","win_rate","t_stat","total_bps","max_drawdown_bps","is_count","is_mean_bps","is_win_rate","oos_count","oos_mean_bps","oos_win_rate","positive_year_count","negative_year_count","max_year_share","max_month_share","worst_fold_mean_bps","cost_x1_5_mean_bps","cost_x2_mean_bps","decision","failure_reasons"
    ]
    rows_for_csv = []
    for c in candidates:
        rr = dict(c)
        rr["failure_reasons"] = ";".join(c.get("failure_reasons") or [])
        rows_for_csv.append(rr)
    write_csv(out / "stage50_session_open_range_breakout_candidates.csv", rows_for_csv, flat_fields)
    event_fields = ["candidate_id","session","entry_ts","exit_ts","direction","entry_price","exit_price","gross_bps","net_bps","range_high","range_low","range_bps","spread_points"]
    write_csv(out / "stage50_session_open_range_breakout_event_sample.csv", sample_events[:200], event_fields)

    print(json.dumps({"stage": summary["stage"], "status": status, "hard_audit_pass_count": pass_count, "candidate_count": len(candidates), "out": str(out)}))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
