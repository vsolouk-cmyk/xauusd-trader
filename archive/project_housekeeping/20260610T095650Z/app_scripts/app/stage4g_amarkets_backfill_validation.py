"""
Stage 4G AMarkets broker-feed backfill validation v2.

Purpose:
- Validate locked XAUUSD dry-run candidate on AMarkets MT5 CSV exports.
- Report BOTH diagnostic overlapping replay and execution-realistic non-overlap replay.
- Non-overlap mode is the decision basis because the locked candidate has a 12 H1-bar trade horizon.

No orders. No broker/API access. Local CSV analysis only.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

STRATEGY_ID = "xauusd_long_tp24_sl15_no_london_v1"
TOOL_VERSION = "v2_non_overlap"

DEFAULT_H1 = "~/Downloads/amarkets_xauusd_1h.csv"
DEFAULT_M1 = "~/Downloads/amarkets_xauusd_1m.csv"
DEFAULT_OUT_DIR = "data/reports/stage4g_v2"

SMA_WINDOW = 10
DISTANCE_THRESHOLD_USD = 10.0
TP_USD = 24.0
SL_USD = 15.0
TIME_EXIT_H1_BARS = 12
ROUNDTRIP_COST_USD = 0.35


@dataclass
class Candle:
    server_time: datetime
    utc_time: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass
class Trade:
    replay_mode: str
    signal_server_time: str
    signal_utc_time: str
    entry_server_time: str
    entry_utc_time: str
    exit_server_time: str
    exit_utc_time: str
    session_utc: str
    entry_price: float
    close_h1: float
    sma10: float
    distance_usd: float
    tp_usd: float
    sl_usd: float
    time_exit_h1_bars: int
    exit_reason: str
    gross_usd: float
    net_usd: float
    ambiguous_exit: bool


def parse_dt(date_s: str, time_s: Optional[str] = None) -> datetime:
    s = (date_s or "").strip()
    if time_s is not None:
        s = f"{s} {(time_s or '').strip()}".strip()
    s = s.replace("/", ".").replace("-", ".")
    # common MT5 exports: 2026.06.08 13:00:00
    for fmt in ("%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M", "%Y.%m.%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    raise ValueError(f"unsupported datetime: {s!r}")


def sniff_delimiter(path: Path) -> str:
    sample = path.read_text(encoding="utf-8-sig", errors="replace")[:4096]
    candidates = ["\t", ",", ";"]
    return max(candidates, key=lambda d: sample.count(d))


def norm_key(k: str) -> str:
    return k.strip().lower().replace("<", "").replace(">", "").replace(" ", "_")


def find_col(fieldnames: Iterable[str], aliases: Iterable[str]) -> Optional[str]:
    lookup = {norm_key(f): f for f in fieldnames}
    for a in aliases:
        if norm_key(a) in lookup:
            return lookup[norm_key(a)]
    return None


def read_mt5_candles(path_str: str, server_utc_offset_hours: float) -> Tuple[List[Candle], Dict[str, object]]:
    path = Path(os.path.expanduser(path_str))
    if not path.exists():
        raise FileNotFoundError(path)
    delimiter = sniff_delimiter(path)
    candles: List[Candle] = []
    bad_rows: List[Dict[str, object]] = []

    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.reader(f, delimiter=delimiter)
        rows = list(reader)
    if not rows:
        return [], {"path": str(path), "delimiter": delimiter, "rows_parsed": 0, "bad_row_count": 0, "has_header": False}

    first = [c.strip() for c in rows[0]]
    has_header = any("date" in norm_key(c) or "time" in norm_key(c) or "open" in norm_key(c) for c in first)

    if has_header:
        headers = first
        date_col = find_col(headers, ["date", "time", "datetime"])
        time_col = find_col(headers, ["time"]) if date_col and norm_key(date_col) == "date" else None
        open_col = find_col(headers, ["open"])
        high_col = find_col(headers, ["high"])
        low_col = find_col(headers, ["low"])
        close_col = find_col(headers, ["close"])
        if not all([date_col, open_col, high_col, low_col, close_col]):
            raise ValueError(f"Cannot map OHLC columns in {path}. headers={headers}")
        dict_rows = [dict(zip(headers, r)) for r in rows[1:] if any(cell.strip() for cell in r)]
        for idx, r in enumerate(dict_rows, start=2):
            try:
                if time_col:
                    st = parse_dt(r[date_col], r[time_col])
                else:
                    st = parse_dt(r[date_col])
                candles.append(Candle(
                    server_time=st,
                    utc_time=st - timedelta(hours=server_utc_offset_hours),
                    open=float(r[open_col]),
                    high=float(r[high_col]),
                    low=float(r[low_col]),
                    close=float(r[close_col]),
                ))
            except Exception as e:
                bad_rows.append({"line": idx, "error": str(e), "row": r})
    else:
        # common no-header MT5 order: date, time, open, high, low, close, tickvol, vol, spread
        for idx, r in enumerate(rows, start=1):
            if not r or not any(cell.strip() for cell in r):
                continue
            try:
                if len(r) >= 6:
                    st = parse_dt(r[0], r[1])
                    o, h, l, c = float(r[2]), float(r[3]), float(r[4]), float(r[5])
                elif len(r) >= 5:
                    st = parse_dt(r[0])
                    o, h, l, c = float(r[1]), float(r[2]), float(r[3]), float(r[4])
                else:
                    raise ValueError("not enough columns")
                candles.append(Candle(st, st - timedelta(hours=server_utc_offset_hours), o, h, l, c))
            except Exception as e:
                bad_rows.append({"line": idx, "error": str(e), "row": r})

    candles.sort(key=lambda x: x.server_time)
    meta = {
        "path": str(path),
        "delimiter": "TAB" if delimiter == "\t" else delimiter,
        "has_header": has_header,
        "rows_parsed": len(candles),
        "bad_row_count": len(bad_rows),
        "bad_rows_sample": bad_rows[:5],
    }
    if candles:
        meta.update({
            "start_server": candles[0].server_time.isoformat(),
            "end_server": candles[-1].server_time.isoformat(),
            "start_utc": candles[0].utc_time.isoformat(),
            "end_utc": candles[-1].utc_time.isoformat(),
        })
    return candles, meta


def session_name_utc(dt: datetime) -> str:
    h = dt.hour
    if 0 <= h < 7:
        return "asia"
    if 7 <= h < 13:
        return "london"
    if 13 <= h < 16:
        return "london_ny_overlap"
    if 16 <= h < 21:
        return "new_york"
    return "other"


def generate_signals(h1: List[Candle]) -> List[Dict[str, object]]:
    signals = []
    closes = [c.close for c in h1]
    for i in range(SMA_WINDOW - 1, len(h1) - 1):  # need next H1 open for entry
        sma = sum(closes[i - SMA_WINDOW + 1:i + 1]) / SMA_WINDOW
        distance = h1[i].close - sma
        sess = session_name_utc(h1[i].utc_time)
        if sess == "london":
            continue
        if distance >= DISTANCE_THRESHOLD_USD:
            signals.append({
                "idx": i,
                "entry_idx": i + 1,
                "signal": h1[i],
                "entry_h1": h1[i + 1],
                "sma10": sma,
                "distance_usd": distance,
                "session_utc": sess,
            })
    return signals


def resolve_trade(sig: Dict[str, object], m1: List[Candle], m1_times: List[datetime], roundtrip_cost: float, mode: str) -> Optional[Trade]:
    signal: Candle = sig["signal"]  # type: ignore[assignment]
    entry_h1: Candle = sig["entry_h1"]  # type: ignore[assignment]
    entry_time = entry_h1.server_time
    horizon_time = entry_time + timedelta(hours=TIME_EXIT_H1_BARS)
    entry_price = entry_h1.open
    tp_price = entry_price + TP_USD
    sl_price = entry_price - SL_USD

    start = bisect_left(m1_times, entry_time)
    end = bisect_right(m1_times, horizon_time)
    path = m1[start:end]
    if not path:
        return None

    exit_candle = path[-1]
    exit_reason = "time_exit"
    gross = exit_candle.close - entry_price
    ambiguous = False

    for c in path:
        hit_tp = c.high >= tp_price
        hit_sl = c.low <= sl_price
        if hit_tp and hit_sl:
            ambiguous = True
            # Conservative for long when intraminute ordering is unknown.
            exit_candle = c
            exit_reason = "ambiguous_stop_first"
            gross = -SL_USD
            break
        if hit_sl:
            exit_candle = c
            exit_reason = "stop_loss"
            gross = -SL_USD
            break
        if hit_tp:
            exit_candle = c
            exit_reason = "take_profit"
            gross = TP_USD
            break

    net = gross - roundtrip_cost
    return Trade(
        replay_mode=mode,
        signal_server_time=signal.server_time.isoformat(sep=" "),
        signal_utc_time=signal.utc_time.isoformat(sep=" "),
        entry_server_time=entry_time.isoformat(sep=" "),
        entry_utc_time=entry_h1.utc_time.isoformat(sep=" "),
        exit_server_time=exit_candle.server_time.isoformat(sep=" "),
        exit_utc_time=exit_candle.utc_time.isoformat(sep=" "),
        session_utc=str(sig["session_utc"]),
        entry_price=round(entry_price, 5),
        close_h1=round(signal.close, 5),
        sma10=round(float(sig["sma10"]), 5),
        distance_usd=round(float(sig["distance_usd"]), 5),
        tp_usd=TP_USD,
        sl_usd=SL_USD,
        time_exit_h1_bars=TIME_EXIT_H1_BARS,
        exit_reason=exit_reason,
        gross_usd=round(gross, 6),
        net_usd=round(net, 6),
        ambiguous_exit=ambiguous,
    )


def replay(signals: List[Dict[str, object]], m1: List[Candle], mode: str, roundtrip_cost: float) -> Tuple[List[Trade], int]:
    m1_times = [c.server_time for c in m1]
    trades: List[Trade] = []
    skipped_by_overlap = 0
    open_until: Optional[datetime] = None

    for sig in signals:
        entry_h1: Candle = sig["entry_h1"]  # type: ignore[assignment]
        if mode == "non_overlap" and open_until is not None and entry_h1.server_time < open_until:
            skipped_by_overlap += 1
            continue
        tr = resolve_trade(sig, m1, m1_times, roundtrip_cost, mode)
        if tr is None:
            continue
        trades.append(tr)
        if mode == "non_overlap":
            open_until = datetime.fromisoformat(tr.exit_server_time)
    return trades, skipped_by_overlap


def max_drawdown(vals: List[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for v in vals:
        equity += v
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return round(max_dd, 6)


def median(vals: List[float]) -> float:
    if not vals:
        return 0.0
    xs = sorted(vals)
    n = len(xs)
    mid = n // 2
    if n % 2:
        return xs[mid]
    return (xs[mid - 1] + xs[mid]) / 2.0


def metrics(trades: List[Trade], cost_multiplier: float = 1.0, base_cost: float = ROUNDTRIP_COST_USD) -> Dict[str, object]:
    # Trades already include base cost once. Adjust to requested multiplier.
    nets = [t.gross_usd - base_cost * cost_multiplier for t in trades]
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x < 0]
    gross_profit = sum(wins)
    gross_loss = -sum(losses)
    pf = gross_profit / gross_loss if gross_loss > 0 else (math.inf if gross_profit > 0 else 0.0)
    return {
        "trades": len(trades),
        "total_net_usd": round(sum(nets), 6),
        "avg_net_usd": round(sum(nets) / len(nets), 6) if nets else 0.0,
        "median_net_usd": round(median(nets), 6),
        "win_rate": round(len(wins) / len(nets), 6) if nets else 0.0,
        "profit_factor": round(pf, 6) if math.isfinite(pf) else "inf",
        "max_drawdown_usd": max_drawdown(nets),
        "best_net_usd": round(max(nets), 6) if nets else 0.0,
        "worst_net_usd": round(min(nets), 6) if nets else 0.0,
        "ambiguous_exit_count": sum(1 for t in trades if t.ambiguous_exit),
    }


def group_metrics(trades: List[Trade], key_fn) -> Dict[str, Dict[str, object]]:
    groups: Dict[str, List[Trade]] = {}
    for t in trades:
        groups.setdefault(str(key_fn(t)), []).append(t)
    return {k: metrics(v) for k, v in sorted(groups.items())}


def write_trades_csv(path: Path, trades: List[Trade]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [asdict(t) for t in trades]
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def status_for(non_overlap: Dict[str, object]) -> Tuple[str, List[Tuple[str, str, str]]]:
    checks: List[Tuple[str, str, str]] = []
    def add(status: str, name: str, detail: str) -> None:
        checks.append((status, name, detail))

    trades = int(non_overlap.get("trades", 0))
    total = float(non_overlap.get("total_net_usd", 0.0))
    median_v = float(non_overlap.get("median_net_usd", 0.0))
    pf = non_overlap.get("profit_factor", 0.0)
    pf_f = float(pf) if pf != "inf" else 999.0

    add("PASS" if trades >= 20 else "FAIL", "Minimum non-overlap trades", f"trades={trades}, min=20")
    add("PASS" if total > 0 else "FAIL", "Positive total net", f"total_net_usd={total}")
    add("PASS" if pf_f >= 1.05 else "FAIL", "Profit factor", f"profit_factor={pf_f}, threshold=1.05")
    add("PASS" if median_v >= 0 else "WARN", "Median nonnegative", f"median_net_usd={median_v}")
    add("PASS" if int(non_overlap.get("ambiguous_exit_count", 0)) == 0 else "WARN", "Ambiguous exits", f"ambiguous={non_overlap.get('ambiguous_exit_count')}")

    if any(c[0] == "FAIL" for c in checks):
        return "FAIL", checks
    if any(c[0] == "WARN" for c in checks):
        return "PASS_WITH_WARNINGS", checks
    return "PASS", checks


def render_md(report: Dict[str, object]) -> str:
    lines: List[str] = []
    lines.append("# Stage 4G AMarkets Backfill Validation v2")
    lines.append("")
    lines.append(f"Generated UTC: `{datetime.utcnow().replace(microsecond=0).isoformat()}Z`")
    lines.append(f"Tool version: `{TOOL_VERSION}`")
    lines.append(f"Strategy ID: `{STRATEGY_ID}`")
    lines.append(f"Overall status: **{report['overall_status']}**")
    lines.append("")
    lines.append("> Hard rule: this is broker-feed backfill validation only. It does not authorize demo, paper, or live orders.")
    lines.append("")
    lines.append("## Critical interpretation")
    lines.append("")
    lines.append("- `overlap_every_signal` is diagnostic only: it opens a replay trade for every qualifying H1 signal.")
    lines.append("- `non_overlap` is the decision basis: it allows only one active dry-run trade at a time until TP, SL, or 12 H1-bar time-exit resolves.")
    lines.append("- Demo-order remains forbidden unless non-overlap replay, live dry-run outcomes, spread guard, and risk guards pass.")
    lines.append("")
    lines.append("## Inputs")
    for k, v in report["inputs"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")
    lines.append("## Data quality")
    for name in ("h1", "m1"):
        lines.append(f"### {name.upper()}")
        for k, v in report["data_quality"][name].items():
            if k != "bad_rows_sample":
                lines.append(f"- {k}: `{v}`")
        lines.append("")
    lines.append("## Signal counts")
    for k, v in report["signal_counts"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")
    lines.append("## Replay comparison")
    for mode in ("overlap_every_signal", "non_overlap"):
        lines.append(f"### {mode}")
        for k, v in report["metrics"][mode]["cost_x1"].items():
            lines.append(f"- {k}: `{v}`")
        lines.append("")
    lines.append("## Non-overlap cost stress")
    for label, m in report["metrics"]["non_overlap"].items():
        lines.append(f"### {label}")
        for k, v in m.items():
            lines.append(f"- {k}: `{v}`")
        lines.append("")
    lines.append("## Non-overlap session breakdown")
    for sess, m in report["session_breakdown_non_overlap"].items():
        lines.append(f"### {sess}")
        for k, v in m.items():
            lines.append(f"- {k}: `{v}`")
        lines.append("")
    lines.append("## Non-overlap year breakdown")
    for year, m in report["year_breakdown_non_overlap"].items():
        lines.append(f"### {year}")
        for k, v in m.items():
            lines.append(f"- {k}: `{v}`")
        lines.append("")
    lines.append("## Checks — decision basis: non_overlap")
    lines.append("")
    lines.append("| Status | Check | Detail |")
    lines.append("|---|---|---|")
    for status, name, detail in report["checks"]:
        lines.append(f"| {status} | {name} | {detail} |")
    lines.append("")
    lines.append(f"Decision: **{report['decision']}**")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--h1", default=DEFAULT_H1)
    ap.add_argument("--m1", default=DEFAULT_M1)
    ap.add_argument("--server-utc-offset-hours", type=float, default=2.0)
    ap.add_argument("--roundtrip-cost-usd", type=float, default=ROUNDTRIP_COST_USD)
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    h1, h1_meta = read_mt5_candles(args.h1, args.server_utc_offset_hours)
    m1, m1_meta = read_mt5_candles(args.m1, args.server_utc_offset_hours)
    signals = generate_signals(h1)

    overlap_trades, overlap_skipped = replay(signals, m1, "overlap_every_signal", args.roundtrip_cost_usd)
    non_overlap_trades, non_overlap_skipped = replay(signals, m1, "non_overlap", args.roundtrip_cost_usd)

    write_trades_csv(out_dir / "stage4g_v2_overlap_trades.csv", overlap_trades)
    write_trades_csv(out_dir / "stage4g_v2_non_overlap_trades.csv", non_overlap_trades)

    mode_metrics = {
        "overlap_every_signal": {
            "cost_x1": metrics(overlap_trades, 1, args.roundtrip_cost_usd),
            "cost_x2": metrics(overlap_trades, 2, args.roundtrip_cost_usd),
            "cost_x3": metrics(overlap_trades, 3, args.roundtrip_cost_usd),
            "cost_x4": metrics(overlap_trades, 4, args.roundtrip_cost_usd),
        },
        "non_overlap": {
            "cost_x1": metrics(non_overlap_trades, 1, args.roundtrip_cost_usd),
            "cost_x2": metrics(non_overlap_trades, 2, args.roundtrip_cost_usd),
            "cost_x3": metrics(non_overlap_trades, 3, args.roundtrip_cost_usd),
            "cost_x4": metrics(non_overlap_trades, 4, args.roundtrip_cost_usd),
        },
    }
    status, checks = status_for(mode_metrics["non_overlap"]["cost_x1"])
    decision = {
        "PASS": "Non-overlap AMarkets backfill passes baseline checks, but demo-order still requires live dry-run outcomes and guards.",
        "PASS_WITH_WARNINGS": "Non-overlap AMarkets backfill is usable with warnings. Continue live dry-run and inspect weak segments before demo-order.",
        "FAIL": "Non-overlap AMarkets backfill fails. Do not advance this candidate toward demo-order; revise or filter first.",
    }[status]

    report: Dict[str, object] = {
        "tool_version": TOOL_VERSION,
        "strategy_id": STRATEGY_ID,
        "overall_status": status,
        "inputs": {
            "h1": str(Path(os.path.expanduser(args.h1))),
            "m1": str(Path(os.path.expanduser(args.m1))),
            "server_utc_offset_hours": args.server_utc_offset_hours,
            "roundtrip_cost_usd": args.roundtrip_cost_usd,
            "decision_basis": "non_overlap",
        },
        "data_quality": {"h1": h1_meta, "m1": m1_meta},
        "signal_counts": {
            "h1_rows": len(h1),
            "m1_rows": len(m1),
            "raw_signals": len(signals),
            "overlap_replayed_trades": len(overlap_trades),
            "non_overlap_replayed_trades": len(non_overlap_trades),
            "non_overlap_skipped_by_open_position": non_overlap_skipped,
            "overlap_skipped": overlap_skipped,
        },
        "metrics": mode_metrics,
        "session_breakdown_non_overlap": group_metrics(non_overlap_trades, lambda t: t.session_utc),
        "year_breakdown_non_overlap": group_metrics(non_overlap_trades, lambda t: t.signal_utc_time[:4]),
        "checks": checks,
        "decision": decision,
        "outputs": {
            "overlap_trades_csv": str(out_dir / "stage4g_v2_overlap_trades.csv"),
            "non_overlap_trades_csv": str(out_dir / "stage4g_v2_non_overlap_trades.csv"),
            "json_report": str(out_dir / "stage4g_v2_amarkets_backfill_validation.json"),
            "markdown_report": str(out_dir / "stage4g_v2_amarkets_backfill_validation.md"),
        },
    }

    (out_dir / "stage4g_v2_amarkets_backfill_validation.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "stage4g_v2_amarkets_backfill_validation.md").write_text(render_md(report), encoding="utf-8")

    print(f"Stage 4G AMarkets backfill validation v2: {status}")
    print(f"Decision basis: non_overlap")
    print(f"JSON report: {out_dir / 'stage4g_v2_amarkets_backfill_validation.json'}")
    print(f"Markdown report: {out_dir / 'stage4g_v2_amarkets_backfill_validation.md'}")
    print(f"Non-overlap trades CSV: {out_dir / 'stage4g_v2_non_overlap_trades.csv'}")
    return 0 if status != "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
