
#!/usr/bin/env python3
"""
Stage 5C v2 — Live dry-run outcome tracker.

Fixes vs v1:
- Handles multiple signal rows.
- Deduplicates repeated EA rows by default.
- Uses signal_closed_h1_time_server converted by broker server UTC offset
  as the canonical closed H1 time.
- Treats signal_closed_h1_time_gmt_now as diagnostic only, because the EA
  field name is misleading in the current schema.
- Keeps signals OPEN_OR_UNRESOLVED if the M1 export does not cover the entry
  and full 12-hour horizon.
- Does not authorize demo, paper, or live trading.
"""

from __future__ import annotations

import argparse, csv, json, math
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Sequence, Dict, Tuple

TOOL_VERSION = "v2"
STRATEGY_ID = "xauusd_long_tp24_sl15_no_london_v1"

DEFAULT_SIGNALS = Path("~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/XAUUSD_DryRun_v1_signals.csv").expanduser()
DEFAULT_M1 = Path("~/Downloads/amarkets_xauusd_1m.csv").expanduser()
DEFAULT_OUT_DIR = Path("data/reports/stage5c_live_outcome_tracker")


def parse_time(value: str) -> Optional[datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    for fmt in ("%Y.%m.%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def parse_float(v, default=0.0) -> float:
    try:
        if v is None or str(v).strip() == "":
            return default
        return float(str(v).strip())
    except Exception:
        return default


def detect_delimiter(text: str) -> str:
    sample = text[:4096]
    return "\t" if sample.count("\t") >= sample.count(",") else ","


def read_dict_csv(path: Path) -> List[dict]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if not text.strip():
        return []
    delim = detect_delimiter(text)
    rows = []
    for row in csv.DictReader(text.splitlines(), delimiter=delim):
        if row:
            rows.append({str(k).strip(): ("" if v is None else str(v).strip()) for k, v in row.items() if k is not None})
    return rows


def infer_ohlc_cols(rows: Sequence[dict]) -> Dict[str, str]:
    if not rows:
        return {}
    norm = {k.lower().strip("<>").replace("_", "").replace(" ", ""): k for k in rows[0].keys()}
    def pick(names):
        for n in names:
            key = n.lower().strip("<>").replace("_", "").replace(" ", "")
            if key in norm:
                return norm[key]
        return None
    return {
        "time": pick(["time", "datetime", "date", "timestamp"]),
        "open": pick(["open"]),
        "high": pick(["high"]),
        "low": pick(["low"]),
        "close": pick(["close"]),
    }


@dataclass
class Signal:
    source_row: int
    logged_at_gmt: str
    symbol: str
    strategy_id: str
    closed_h1_server_raw: str
    closed_h1_utc: Optional[str]
    diagnostic_gmt_now_raw: str
    session_utc: str
    close_h1: float
    sma10: float
    distance_usd: float
    direction: str
    tp_usd: float
    sl_usd: float
    time_exit_h1_bars: int
    dry_run_only: str
    duplicate_key: str


@dataclass
class Outcome:
    source_row: int
    symbol: str
    session_utc: str
    status: str
    reason: str
    closed_h1_utc: Optional[str]
    entry_utc: Optional[str]
    entry_price: Optional[float]
    tp_price: Optional[float]
    sl_price: Optional[float]
    exit_utc: Optional[str]
    exit_price: Optional[float]
    net_usd_x1: Optional[float]
    m1_bars_checked: int


def load_signals(path: Path, server_offset_hours: float, dedupe: bool = True) -> Tuple[List[Signal], int, int]:
    rows = read_dict_csv(path)
    out: List[Signal] = []
    seen = set()
    offset = timedelta(hours=server_offset_hours)
    for i, r in enumerate(rows, start=1):
        if r.get("strategy_id") and r.get("strategy_id") != STRATEGY_ID:
            continue
        closed_server = parse_time(r.get("signal_closed_h1_time_server", ""))
        closed_utc = None
        if closed_server is not None:
            closed_utc_dt = closed_server - offset
            closed_utc = closed_utc_dt.isoformat()
        key = "|".join([
            r.get("symbol", ""),
            r.get("strategy_id", ""),
            r.get("signal_closed_h1_time_server", ""),
            r.get("session_utc", ""),
            r.get("close_h1", ""),
            r.get("sma10", ""),
            r.get("distance_usd", ""),
            r.get("direction", ""),
        ])
        if dedupe and key in seen:
            continue
        seen.add(key)
        out.append(Signal(
            source_row=i,
            logged_at_gmt=r.get("logged_at_gmt", ""),
            symbol=r.get("symbol", ""),
            strategy_id=r.get("strategy_id", ""),
            closed_h1_server_raw=r.get("signal_closed_h1_time_server", ""),
            closed_h1_utc=closed_utc,
            diagnostic_gmt_now_raw=r.get("signal_closed_h1_time_gmt_now", ""),
            session_utc=r.get("session_utc", ""),
            close_h1=parse_float(r.get("close_h1")),
            sma10=parse_float(r.get("sma10")),
            distance_usd=parse_float(r.get("distance_usd")),
            direction=r.get("direction", ""),
            tp_usd=parse_float(r.get("tp_usd"), 24.0),
            sl_usd=parse_float(r.get("sl_usd"), 15.0),
            time_exit_h1_bars=int(parse_float(r.get("time_exit_h1_bars"), 12.0)),
            dry_run_only=r.get("dry_run_only", "").lower(),
            duplicate_key=key,
        ))
    return out, len(rows), len(rows) - len(out)


def load_m1(path: Path, server_offset_hours: float) -> List[dict]:
    rows = read_dict_csv(path)
    cols = infer_ohlc_cols(rows)
    if not rows or not all(cols.get(k) for k in ("time", "open", "high", "low", "close")):
        return []
    offset = timedelta(hours=server_offset_hours)
    out = []
    for r in rows:
        t_server = parse_time(r.get(cols["time"], ""))
        if t_server is None:
            continue
        t_utc = t_server - offset
        out.append({
            "utc": t_utc,
            "open": parse_float(r.get(cols["open"])),
            "high": parse_float(r.get(cols["high"])),
            "low": parse_float(r.get(cols["low"])),
            "close": parse_float(r.get(cols["close"])),
        })
    out.sort(key=lambda x: x["utc"])
    return out


def resolve(sig: Signal, m1: Sequence[dict], roundtrip_cost_usd: float) -> Outcome:
    if not sig.closed_h1_utc:
        return Outcome(sig.source_row, sig.symbol, sig.session_utc, "UNRESOLVED", "missing_closed_h1_server_time", None, None, None, None, None, None, None, None, 0)

    closed = datetime.fromisoformat(sig.closed_h1_utc)
    entry_utc = closed + timedelta(hours=1)
    horizon_end = entry_utc + timedelta(hours=sig.time_exit_h1_bars)

    if not m1:
        return Outcome(sig.source_row, sig.symbol, sig.session_utc, "UNRESOLVED", "missing_m1_data", sig.closed_h1_utc, entry_utc.isoformat(), None, None, None, None, None, None, 0)

    if m1[-1]["utc"] < entry_utc:
        return Outcome(sig.source_row, sig.symbol, sig.session_utc, "OPEN_OR_UNRESOLVED", "m1_export_ends_before_signal_entry", sig.closed_h1_utc, entry_utc.isoformat(), None, None, None, None, None, None, 0)

    bars = [b for b in m1 if entry_utc <= b["utc"] < horizon_end]
    if not bars:
        return Outcome(sig.source_row, sig.symbol, sig.session_utc, "OPEN_OR_UNRESOLVED", "no_m1_bars_in_signal_window", sig.closed_h1_utc, entry_utc.isoformat(), None, None, None, None, None, None, 0)

    entry = bars[0]["open"]
    tp = entry + sig.tp_usd
    sl = entry - sig.sl_usd
    exit_time = None
    exit_price = None
    reason = None

    for b in bars:
        hit_tp = b["high"] >= tp
        hit_sl = b["low"] <= sl
        if hit_tp and hit_sl:
            exit_time, exit_price, reason = b["utc"], sl, "ambiguous_tp_sl_same_m1_bar_conservative_sl"
            break
        if hit_sl:
            exit_time, exit_price, reason = b["utc"], sl, "stop_loss"
            break
        if hit_tp:
            exit_time, exit_price, reason = b["utc"], tp, "take_profit"
            break

    if exit_time is None:
        if m1[-1]["utc"] < horizon_end - timedelta(minutes=1):
            return Outcome(sig.source_row, sig.symbol, sig.session_utc, "OPEN", "horizon_not_fully_covered_by_m1_export", sig.closed_h1_utc, entry_utc.isoformat(), round(entry, 6), round(tp, 6), round(sl, 6), None, None, None, len(bars))
        last = bars[-1]
        exit_time, exit_price, reason = last["utc"], last["close"], "time_exit"

    net = (exit_price - entry) - roundtrip_cost_usd
    return Outcome(sig.source_row, sig.symbol, sig.session_utc, "RESOLVED", reason, sig.closed_h1_utc, entry_utc.isoformat(), round(entry, 6), round(tp, 6), round(sl, 6), exit_time.isoformat(), round(exit_price, 6), round(net, 6), len(bars))


def write_reports(out_dir: Path, signals_path: Path, m1_path: Path, signals: List[Signal], raw_rows: int, skipped_dupes: int, outcomes: List[Outcome], server_offset: float):
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "tool_version": TOOL_VERSION,
        "strategy_id": STRATEGY_ID,
        "generated_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "signals_csv": str(signals_path),
        "m1_csv": str(m1_path),
        "server_utc_offset_hours": server_offset,
        "raw_signal_rows": raw_rows,
        "deduped_signals": len(signals),
        "skipped_duplicate_rows": skipped_dupes,
        "signals": [asdict(s) for s in signals],
        "outcomes": [asdict(o) for o in outcomes],
    }
    (out_dir / "stage5c_live_outcome_tracker.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    if outcomes:
        with (out_dir / "stage5c_live_outcomes.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(asdict(outcomes[0]).keys()))
            w.writeheader()
            for o in outcomes:
                w.writerow(asdict(o))

    resolved = [o for o in outcomes if o.status == "RESOLVED"]
    openish = [o for o in outcomes if o.status != "RESOLVED"]
    total_net = sum(o.net_usd_x1 or 0.0 for o in resolved)

    lines = []
    lines.append("# Stage 5C Live Dry-run Outcome Tracker v2")
    lines.append("")
    lines.append(f"Generated UTC: `{payload['generated_utc']}`")
    lines.append(f"Tool version: `{TOOL_VERSION}`")
    lines.append(f"Strategy ID: `{STRATEGY_ID}`")
    lines.append("")
    lines.append("> Hard rule: this resolves dry-run signals only. It does not authorize demo, paper, or live orders.")
    lines.append("")
    lines.append("## Inputs")
    lines.append(f"- signals_csv: `{signals_path}`")
    lines.append(f"- m1_csv: `{m1_path}`")
    lines.append(f"- server_utc_offset_hours: `{server_offset}`")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- raw_signal_rows: `{raw_rows}`")
    lines.append(f"- deduped_signals: `{len(signals)}`")
    lines.append(f"- skipped_duplicate_rows: `{skipped_dupes}`")
    lines.append(f"- resolved: `{len(resolved)}`")
    lines.append(f"- open_or_unresolved: `{len(openish)}`")
    lines.append(f"- total_net_x1_resolved: `{round(total_net, 6)}`")
    lines.append("")
    lines.append("## Outcomes")
    lines.append("| Row | Status | Reason | Session | Closed H1 UTC | Entry UTC | Entry | TP | SL | Exit UTC | Exit | Net x1 |")
    lines.append("|---:|---|---|---|---|---|---:|---:|---:|---|---:|---:|")
    for o in outcomes:
        lines.append(f"| {o.source_row} | {o.status} | {o.reason} | {o.session_utc} | {o.closed_h1_utc or ''} | {o.entry_utc or ''} | {'' if o.entry_price is None else o.entry_price} | {'' if o.tp_price is None else o.tp_price} | {'' if o.sl_price is None else o.sl_price} | {o.exit_utc or ''} | {'' if o.exit_price is None else o.exit_price} | {'' if o.net_usd_x1 is None else o.net_usd_x1} |")
    lines.append("")
    lines.append("## Decision")
    lines.append("- Continue dry-run logging. Do not use this report to place orders.")
    if openish:
        lines.append("- Some signals are open/unresolved. Export fresh AMarkets M1 after the 12-hour horizon and rerun this tracker.")
    (out_dir / "stage5c_live_outcome_tracker.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--signals-csv", default=str(DEFAULT_SIGNALS))
    p.add_argument("--m1-csv", default=str(DEFAULT_M1))
    p.add_argument("--server-utc-offset-hours", type=float, default=2.0)
    p.add_argument("--roundtrip-cost-usd", type=float, default=0.35)
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--no-dedupe", action="store_true")
    args = p.parse_args()

    signals_path = Path(args.signals_csv).expanduser()
    m1_path = Path(args.m1_csv).expanduser()
    signals, raw_rows, skipped_dupes = load_signals(signals_path, args.server_utc_offset_hours, dedupe=not args.no_dedupe)
    m1 = load_m1(m1_path, args.server_utc_offset_hours)
    outcomes = [resolve(s, m1, args.roundtrip_cost_usd) for s in signals]
    out_dir = Path(args.out_dir)
    write_reports(out_dir, signals_path, m1_path, signals, raw_rows, skipped_dupes, outcomes, args.server_utc_offset_hours)

    print("Stage 5C live dry-run outcome tracker: DONE")
    print(f"raw_rows={raw_rows} | deduped_signals={len(signals)} | resolved={sum(1 for o in outcomes if o.status=='RESOLVED')} | open/unresolved={sum(1 for o in outcomes if o.status!='RESOLVED')}")
    print(f"Markdown report: {out_dir / 'stage5c_live_outcome_tracker.md'}")
    print(f"CSV outcomes: {out_dir / 'stage5c_live_outcomes.csv'}")

if __name__ == "__main__":
    main()
