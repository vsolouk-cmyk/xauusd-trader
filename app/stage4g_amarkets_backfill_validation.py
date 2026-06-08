"""Stage 4G AMarkets broker-feed backfill validation for XAUUSD.

Standalone, stdlib-only validator/replay tool.

Purpose:
- Read AMarkets MT5 exported H1 and M1 CSV files.
- Re-run the locked Stage 5A strategy candidate on broker feed.
- Replay long entries with M1 path using TP/SL/time-exit.
- Produce JSON/Markdown/CSV reports under data/reports.

Hard rule: this is research/dry-run validation only. It does not place orders.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

TOOL_VERSION = "v1"
STRATEGY_ID = "xauusd_long_tp24_sl15_no_london_v1"

DEFAULT_H1 = "~/Downloads/amarkets_xauusd_1h.csv"
DEFAULT_M1 = "~/Downloads/amarkets_xauusd_1m.csv"
DEFAULT_OUT_DIR = "data/reports"

SMA_WINDOW = 10
DISTANCE_THRESHOLD_USD = 10.0
TP_USD = 24.0
SL_USD = 15.0
TIME_EXIT_HOURS = 12
ROUNDTRIP_COST_USD = 0.35

BLOCKED_SESSION = "london"
ALLOWED_SESSIONS = {"asia", "london_ny_overlap", "new_york", "other"}

DATE_FORMATS = (
    "%Y.%m.%d %H:%M:%S",
    "%Y.%m.%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
)

DANGEROUS_TERMS = (
    "OrderSend",
    "CTrade",
    ".Buy(",
    ".Sell(",
    "PositionOpen",
    "PositionClose",
)

@dataclass
class Candle:
    server_time: datetime
    utc_time: datetime
    open: float
    high: float
    low: float
    close: float
    tick_volume: Optional[float] = None
    spread: Optional[float] = None

@dataclass
class TradeResult:
    signal_server_time: str
    signal_utc_time: str
    entry_server_time: str
    entry_utc_time: str
    session: str
    close_h1: float
    sma10: float
    distance_usd: float
    entry_price: float
    tp_price: float
    sl_price: float
    exit_server_time: str
    exit_utc_time: str
    exit_price: float
    exit_reason: str
    gross_usd: float
    net_usd: float
    ambiguous_exit: bool
    bars_m1_used: int


def expand_path(path: str) -> Path:
    return Path(path).expanduser().resolve()


def detect_delimiter(sample: str) -> str:
    candidates = ["\t", ",", ";"]
    first_lines = [ln for ln in sample.splitlines()[:5] if ln.strip()]
    if not first_lines:
        return ","
    scores = {d: sum(line.count(d) for line in first_lines) for d in candidates}
    return max(scores, key=scores.get) if max(scores.values()) > 0 else ","


def read_text(path: Path) -> str:
    for enc in ("utf-8-sig", "utf-16", "utf-8", "cp1252"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeError:
            continue
    return path.read_text(errors="replace")


def normalize_header(value: str) -> str:
    v = value.strip().lower().replace("<", "").replace(">", "")
    v = v.replace(" ", "_").replace("-", "_").replace(".", "_")
    return v


def looks_like_header(row: Sequence[str]) -> bool:
    joined = "\t".join(row).lower()
    return any(token in joined for token in ("open", "high", "low", "close", "date", "time"))


def parse_dt(date_part: str, time_part: Optional[str] = None) -> datetime:
    raw = f"{date_part.strip()} {time_part.strip()}" if time_part is not None else date_part.strip()
    raw = raw.replace("/", ".")
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            pass
    # Last fallback: ISO-ish with T.
    try:
        return datetime.fromisoformat(raw.replace("T", " ")).replace(tzinfo=None)
    except ValueError as exc:
        raise ValueError(f"Could not parse datetime: {raw!r}") from exc


def to_float(value: str) -> float:
    v = str(value).strip().replace(" ", "").replace(",", ".")
    if v == "":
        return float("nan")
    return float(v)


def parse_mt5_csv(path: Path, server_utc_offset_hours: float) -> Tuple[List[Candle], Dict[str, object]]:
    text = read_text(path)
    delimiter = detect_delimiter(text[:5000])
    rows = list(csv.reader(text.splitlines(), delimiter=delimiter))
    rows = [r for r in rows if r and any(str(x).strip() for x in r)]
    if not rows:
        return [], {"path": str(path), "delimiter": delimiter, "rows_raw": 0, "has_header": False}

    has_header = looks_like_header(rows[0])
    header = [normalize_header(x) for x in rows[0]] if has_header else []
    data_rows = rows[1:] if has_header else rows

    def find_col(names: Sequence[str], fallback: Optional[int] = None) -> Optional[int]:
        for name in names:
            n = normalize_header(name)
            if n in header:
                return header.index(n)
        return fallback

    if has_header:
        date_idx = find_col(["date", "time", "datetime"])
        time_idx = None
        # Common MT5 export has separate DATE and TIME columns.
        if "date" in header and "time" in header and header.index("date") != header.index("time"):
            date_idx = header.index("date")
            time_idx = header.index("time")
        elif "datetime" in header:
            date_idx = header.index("datetime")
        elif "time" in header:
            date_idx = header.index("time")

        open_idx = find_col(["open"], 2)
        high_idx = find_col(["high"], 3)
        low_idx = find_col(["low"], 4)
        close_idx = find_col(["close"], 5)
        tick_idx = find_col(["tickvol", "tick_volume", "tick_volume_", "tickvol_"], None)
        spread_idx = find_col(["spread"], None)
    else:
        # MT5 default without header: DATE TIME OPEN HIGH LOW CLOSE TICKVOL VOL SPREAD
        date_idx, time_idx = 0, 1
        open_idx, high_idx, low_idx, close_idx = 2, 3, 4, 5
        tick_idx = 6 if len(rows[0]) > 6 else None
        spread_idx = 8 if len(rows[0]) > 8 else None

    required = [date_idx, open_idx, high_idx, low_idx, close_idx]
    if any(idx is None for idx in required):
        raise RuntimeError(f"Could not map required OHLC columns for {path}. header={header!r}")

    candles: List[Candle] = []
    bad_rows: List[Dict[str, object]] = []
    offset = timedelta(hours=server_utc_offset_hours)
    for row_no, row in enumerate(data_rows, start=2 if has_header else 1):
        try:
            max_idx = max(i for i in [date_idx, time_idx, open_idx, high_idx, low_idx, close_idx] if i is not None)
            if len(row) <= max_idx:
                raise ValueError(f"too few columns: {len(row)}")
            server_time = parse_dt(row[date_idx], row[time_idx] if time_idx is not None else None)
            utc_time = server_time - offset
            c = Candle(
                server_time=server_time,
                utc_time=utc_time,
                open=to_float(row[open_idx]),
                high=to_float(row[high_idx]),
                low=to_float(row[low_idx]),
                close=to_float(row[close_idx]),
                tick_volume=to_float(row[tick_idx]) if tick_idx is not None and len(row) > tick_idx else None,
                spread=to_float(row[spread_idx]) if spread_idx is not None and len(row) > spread_idx else None,
            )
            if any(math.isnan(x) for x in (c.open, c.high, c.low, c.close)):
                raise ValueError("NaN OHLC")
            candles.append(c)
        except Exception as exc:  # noqa: BLE001 - report all parse failures
            if len(bad_rows) < 10:
                bad_rows.append({"row_no": row_no, "row": row, "error": str(exc)})

    candles.sort(key=lambda x: x.server_time)
    meta: Dict[str, object] = {
        "path": str(path),
        "delimiter": "TAB" if delimiter == "\t" else delimiter,
        "rows_raw": len(rows),
        "has_header": has_header,
        "header": header,
        "rows_parsed": len(candles),
        "bad_row_count": len(data_rows) - len(candles),
        "bad_row_samples": bad_rows,
        "start_server": candles[0].server_time.isoformat() if candles else None,
        "end_server": candles[-1].server_time.isoformat() if candles else None,
        "start_utc": candles[0].utc_time.isoformat() if candles else None,
        "end_utc": candles[-1].utc_time.isoformat() if candles else None,
        "server_utc_offset_hours": server_utc_offset_hours,
    }
    return candles, meta


def session_name(utc_dt: datetime) -> str:
    h = utc_dt.hour + utc_dt.minute / 60.0
    if 0 <= h < 7:
        return "asia"
    if 7 <= h < 13:
        return "london"
    if 13 <= h < 16:
        return "london_ny_overlap"
    if 16 <= h < 21:
        return "new_york"
    return "other"


def max_drawdown(values: Sequence[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for v in values:
        equity += v
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return max_dd


def profit_factor(values: Sequence[float]) -> Optional[float]:
    wins = sum(v for v in values if v > 0)
    losses = -sum(v for v in values if v < 0)
    if losses == 0:
        return None if wins == 0 else float("inf")
    return wins / losses


def summarize(values: Sequence[float]) -> Dict[str, object]:
    vals = list(values)
    if not vals:
        return {
            "trades": 0,
            "total_net_usd": 0.0,
            "avg_net_usd": None,
            "median_net_usd": None,
            "win_rate": None,
            "profit_factor": None,
            "max_drawdown_usd": 0.0,
        }
    return {
        "trades": len(vals),
        "total_net_usd": round(sum(vals), 4),
        "avg_net_usd": round(sum(vals) / len(vals), 6),
        "median_net_usd": round(statistics.median(vals), 6),
        "win_rate": round(sum(1 for v in vals if v > 0) / len(vals), 6),
        "profit_factor": None if profit_factor(vals) is None else round(profit_factor(vals), 6),
        "max_drawdown_usd": round(max_drawdown(vals), 6),
        "best_net_usd": round(max(vals), 6),
        "worst_net_usd": round(min(vals), 6),
    }


def make_signals(h1: Sequence[Candle]) -> List[Dict[str, object]]:
    signals: List[Dict[str, object]] = []
    closes = [c.close for c in h1]
    for i in range(SMA_WINDOW - 1, len(h1) - 1):  # need next H1 open for entry
        sma = sum(closes[i - SMA_WINDOW + 1 : i + 1]) / SMA_WINDOW
        distance = h1[i].close - sma
        sess = session_name(h1[i].utc_time)
        if sess == BLOCKED_SESSION:
            continue
        if distance >= DISTANCE_THRESHOLD_USD:
            signals.append({
                "idx": i,
                "signal_candle": h1[i],
                "entry_candle": h1[i + 1],
                "sma10": sma,
                "distance_usd": distance,
                "session": sess,
            })
    return signals


def replay_signals(
    signals: Sequence[Dict[str, object]],
    m1: Sequence[Candle],
    roundtrip_cost_usd: float,
) -> Tuple[List[TradeResult], Dict[str, object]]:
    m1_by_time = {c.server_time: c for c in m1}
    m1_times = [c.server_time for c in m1]
    trades: List[TradeResult] = []
    skipped: List[Dict[str, object]] = []

    # Simple moving pointer for speed.
    start_ptr = 0
    for sig in signals:
        signal_c = sig["signal_candle"]
        entry_c = sig["entry_candle"]
        assert isinstance(signal_c, Candle) and isinstance(entry_c, Candle)
        entry_time = entry_c.server_time
        end_time = entry_time + timedelta(hours=TIME_EXIT_HOURS)
        while start_ptr < len(m1_times) and m1_times[start_ptr] < entry_time:
            start_ptr += 1
        j = start_ptr
        if j >= len(m1_times) or m1_times[j] >= end_time:
            skipped.append({"signal_server_time": signal_c.server_time.isoformat(), "reason": "no_m1_after_entry"})
            continue

        entry_price = entry_c.open
        tp_price = entry_price + TP_USD
        sl_price = entry_price - SL_USD
        exit_c: Optional[Candle] = None
        exit_reason = "time_exit"
        exit_price: Optional[float] = None
        ambiguous = False
        bars_used = 0
        last_in_window: Optional[Candle] = None

        while j < len(m1_times) and m1_times[j] < end_time:
            c = m1[j]
            bars_used += 1
            last_in_window = c
            hit_tp = c.high >= tp_price
            hit_sl = c.low <= sl_price
            if hit_tp and hit_sl:
                ambiguous = True
                # Conservative ordering for long in one-minute ambiguity.
                exit_c = c
                exit_reason = "ambiguous_sl_first"
                exit_price = sl_price
                break
            if hit_sl:
                exit_c = c
                exit_reason = "stop_loss"
                exit_price = sl_price
                break
            if hit_tp:
                exit_c = c
                exit_reason = "take_profit"
                exit_price = tp_price
                break
            j += 1

        if exit_c is None:
            if last_in_window is None:
                skipped.append({"signal_server_time": signal_c.server_time.isoformat(), "reason": "empty_m1_window"})
                continue
            exit_c = last_in_window
            exit_price = last_in_window.close
            exit_reason = "time_exit"

        gross = float(exit_price) - entry_price
        net = gross - roundtrip_cost_usd
        trades.append(TradeResult(
            signal_server_time=signal_c.server_time.isoformat(sep=" "),
            signal_utc_time=signal_c.utc_time.isoformat(sep=" "),
            entry_server_time=entry_time.isoformat(sep=" "),
            entry_utc_time=entry_c.utc_time.isoformat(sep=" "),
            session=str(sig["session"]),
            close_h1=round(signal_c.close, 5),
            sma10=round(float(sig["sma10"]), 5),
            distance_usd=round(float(sig["distance_usd"]), 5),
            entry_price=round(entry_price, 5),
            tp_price=round(tp_price, 5),
            sl_price=round(sl_price, 5),
            exit_server_time=exit_c.server_time.isoformat(sep=" "),
            exit_utc_time=exit_c.utc_time.isoformat(sep=" "),
            exit_price=round(float(exit_price), 5),
            exit_reason=exit_reason,
            gross_usd=round(gross, 5),
            net_usd=round(net, 5),
            ambiguous_exit=ambiguous,
            bars_m1_used=bars_used,
        ))

    return trades, {"skipped_count": len(skipped), "skipped_samples": skipped[:10]}


def group_summary(trades: Sequence[TradeResult], attr: str) -> Dict[str, Dict[str, object]]:
    groups: Dict[str, List[float]] = {}
    for t in trades:
        key = str(getattr(t, attr))
        groups.setdefault(key, []).append(t.net_usd)
    return {k: summarize(v) for k, v in sorted(groups.items())}


def year_summary(trades: Sequence[TradeResult]) -> Dict[str, Dict[str, object]]:
    groups: Dict[str, List[float]] = {}
    for t in trades:
        y = t.entry_utc_time[:4]
        groups.setdefault(y, []).append(t.net_usd)
    return {k: summarize(v) for k, v in sorted(groups.items())}


def cost_stress(trades: Sequence[TradeResult], base_cost: float) -> Dict[str, Dict[str, object]]:
    result = {}
    for mult in (1, 2, 3, 4):
        vals = [t.gross_usd - base_cost * mult for t in trades]
        result[f"cost_x{mult}"] = summarize(vals)
    return result


def write_trades_csv(path: Path, trades: Sequence[TradeResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(asdict(trades[0]).keys()) if trades else [
        "signal_server_time", "signal_utc_time", "entry_server_time", "entry_utc_time", "session",
        "close_h1", "sma10", "distance_usd", "entry_price", "tp_price", "sl_price",
        "exit_server_time", "exit_utc_time", "exit_price", "exit_reason", "gross_usd", "net_usd",
        "ambiguous_exit", "bars_m1_used",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for t in trades:
            w.writerow(asdict(t))


def determine_status(summary_x1: Dict[str, object], trades: Sequence[TradeResult], min_trades: int) -> Tuple[str, List[Dict[str, str]]]:
    checks: List[Dict[str, str]] = []
    def add(status: str, check: str, detail: str) -> None:
        checks.append({"status": status, "check": check, "detail": detail})

    n = len(trades)
    add("PASS" if n > 0 else "FAIL", "Trades produced", f"trades={n}")
    add("PASS" if n >= min_trades else "WARN", "Minimum trades", f"trades={n}, min_trades={min_trades}")

    total = float(summary_x1.get("total_net_usd") or 0.0)
    pf = summary_x1.get("profit_factor")
    med = summary_x1.get("median_net_usd")
    amb = sum(1 for t in trades if t.ambiguous_exit)
    amb_ratio = amb / n if n else 0.0

    add("PASS" if total > 0 else "FAIL", "Positive total net", f"total_net_usd={total}")
    add("PASS" if pf is not None and (pf == float("inf") or float(pf) >= 1.05) else "FAIL", "Profit factor", f"profit_factor={pf}, threshold=1.05")
    add("PASS" if med is not None and float(med) >= 0 else "WARN", "Median nonnegative", f"median_net_usd={med}")
    add("PASS" if amb_ratio <= 0.02 else "WARN", "Ambiguous exit ratio", f"ambiguous={amb}, ratio={amb_ratio:.4f}")

    if any(c["status"] == "FAIL" for c in checks):
        return "FAIL", checks
    if any(c["status"] == "WARN" for c in checks):
        return "PASS_WITH_WARNINGS", checks
    return "PASS", checks


def markdown_report(report: Dict[str, object]) -> str:
    lines: List[str] = []
    lines.append("# Stage 4G AMarkets Backfill Validation")
    lines.append("")
    lines.append(f"Generated UTC: `{report['generated_utc']}`")
    lines.append(f"Tool version: `{report['tool_version']}`")
    lines.append(f"Strategy ID: `{report['strategy_id']}`")
    lines.append(f"Overall status: **{report['status']}**")
    lines.append("")
    lines.append("> Hard rule: this is broker-feed backfill validation only. It does not authorize demo, paper, or live orders.")
    lines.append("")
    lines.append("## Inputs")
    for k, v in report["inputs"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")
    lines.append("## Data quality")
    for name in ("h1", "m1"):
        meta = report["data_quality"][name]
        lines.append(f"### {name.upper()}")
        for k in ("rows_parsed", "bad_row_count", "start_server", "end_server", "start_utc", "end_utc", "delimiter", "has_header"):
            lines.append(f"- {k}: `{meta.get(k)}`")
        lines.append("")
    lines.append("## Signal/replay stats")
    stats = report["stats"]
    for k, v in stats.items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")
    lines.append("## Main metrics, cost x1")
    for k, v in report["metrics_cost_x1"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")
    lines.append("## Cost stress")
    for label, metrics in report["cost_stress"].items():
        lines.append(f"### {label}")
        for k, v in metrics.items():
            lines.append(f"- {k}: `{v}`")
        lines.append("")
    lines.append("## Session breakdown")
    for sess, metrics in report["session_breakdown"].items():
        lines.append(f"### {sess}")
        for k, v in metrics.items():
            lines.append(f"- {k}: `{v}`")
        lines.append("")
    lines.append("## Year breakdown")
    for year, metrics in report["year_breakdown"].items():
        lines.append(f"### {year}")
        for k, v in metrics.items():
            lines.append(f"- {k}: `{v}`")
        lines.append("")
    lines.append("## Checks")
    lines.append("")
    lines.append("| Status | Check | Detail |")
    lines.append("|---|---|---|")
    for c in report["checks"]:
        lines.append(f"| {c['status']} | {c['check']} | {c['detail']} |")
    lines.append("")
    if report["status"] == "FAIL":
        lines.append("Decision: **Do not advance from dry-run based on this AMarkets backfill. Diagnose mismatch first.**")
    elif report["status"] == "PASS_WITH_WARNINGS":
        lines.append("Decision: **Backfill is usable but not sufficient alone for demo-order. Continue live dry-run and inspect warnings.**")
    else:
        lines.append("Decision: **Backfill passed local criteria. Continue live dry-run and prepare outcome tracking; this still does not authorize orders.**")
    lines.append("")
    return "\n".join(lines)


def run(args: argparse.Namespace) -> Dict[str, object]:
    h1_path = expand_path(args.h1)
    m1_path = expand_path(args.m1)
    if not h1_path.exists():
        raise FileNotFoundError(f"H1 file not found: {h1_path}")
    if not m1_path.exists():
        raise FileNotFoundError(f"M1 file not found: {m1_path}")

    h1, h1_meta = parse_mt5_csv(h1_path, args.server_utc_offset_hours)
    m1, m1_meta = parse_mt5_csv(m1_path, args.server_utc_offset_hours)
    signals = make_signals(h1)
    trades, replay_meta = replay_signals(signals, m1, args.roundtrip_cost_usd)
    nets = [t.net_usd for t in trades]
    metrics_x1 = summarize(nets)
    status, checks = determine_status(metrics_x1, trades, args.min_trades)

    out_dir = expand_path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    trades_csv = out_dir / "stage4g_amarkets_backfill_trades.csv"
    json_path = out_dir / "stage4g_amarkets_backfill_validation.json"
    md_path = out_dir / "stage4g_amarkets_backfill_validation.md"
    write_trades_csv(trades_csv, trades)

    exit_reasons: Dict[str, int] = {}
    for t in trades:
        exit_reasons[t.exit_reason] = exit_reasons.get(t.exit_reason, 0) + 1

    report: Dict[str, object] = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tool_version": TOOL_VERSION,
        "strategy_id": STRATEGY_ID,
        "status": status,
        "inputs": {
            "h1": str(h1_path),
            "m1": str(m1_path),
            "server_utc_offset_hours": args.server_utc_offset_hours,
            "roundtrip_cost_usd": args.roundtrip_cost_usd,
            "min_trades": args.min_trades,
        },
        "locked_rules": {
            "direction": "long-only",
            "signal_timeframe": "H1",
            "sma_window": SMA_WINDOW,
            "distance_threshold_usd": DISTANCE_THRESHOLD_USD,
            "tp_usd": TP_USD,
            "sl_usd": SL_USD,
            "time_exit_h1_bars": TIME_EXIT_HOURS,
            "blocked_session": BLOCKED_SESSION,
            "allowed_sessions": sorted(ALLOWED_SESSIONS),
        },
        "data_quality": {"h1": h1_meta, "m1": m1_meta},
        "stats": {
            "h1_rows": len(h1),
            "m1_rows": len(m1),
            "signals": len(signals),
            "replayed_trades": len(trades),
            "skipped_replay": replay_meta["skipped_count"],
            "ambiguous_exit_count": sum(1 for t in trades if t.ambiguous_exit),
            "exit_reasons": exit_reasons,
            "trades_csv": str(trades_csv),
        },
        "metrics_cost_x1": metrics_x1,
        "cost_stress": cost_stress(trades, args.roundtrip_cost_usd),
        "session_breakdown": group_summary(trades, "session"),
        "year_breakdown": year_summary(trades),
        "checks": checks,
        "replay_meta": replay_meta,
        "artifacts": {
            "json_report": str(json_path),
            "markdown_report": str(md_path),
            "trades_csv": str(trades_csv),
        },
    }
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(markdown_report(report), encoding="utf-8")
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Stage 4G AMarkets backfill validation for locked XAUUSD strategy.")
    parser.add_argument("--h1", default=DEFAULT_H1, help=f"H1 MT5 export CSV. Default: {DEFAULT_H1}")
    parser.add_argument("--m1", default=DEFAULT_M1, help=f"M1 MT5 export CSV. Default: {DEFAULT_M1}")
    parser.add_argument("--server-utc-offset-hours", type=float, default=2.0, help="Broker server time offset from UTC. AMarkets observed around +2 from live signal row.")
    parser.add_argument("--roundtrip-cost-usd", type=float, default=ROUNDTRIP_COST_USD, help="Roundtrip cost in USD price units, default from previous baseline lab.")
    parser.add_argument("--min-trades", type=int, default=20, help="Minimum trades for stronger confidence. Below this is WARN, not automatic fail.")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR, help="Output report directory.")
    args = parser.parse_args(argv)

    report = run(args)
    print(f"Stage 4G AMarkets backfill validation: {report['status']}")
    print(f"H1 rows: {report['stats']['h1_rows']}")
    print(f"M1 rows: {report['stats']['m1_rows']}")
    print(f"Signals: {report['stats']['signals']}")
    print(f"Replayed trades: {report['stats']['replayed_trades']}")
    print(f"JSON report: {report['artifacts']['json_report']}")
    print(f"Markdown report: {report['artifacts']['markdown_report']}")
    print(f"Trades CSV: {report['artifacts']['trades_csv']}")
    return 0 if report["status"] != "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
