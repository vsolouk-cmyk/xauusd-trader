#!/usr/bin/env python3
"""
Stage 7C — Edge Diagnostics Lab

Purpose:
- Diagnose why Stage 7B thesis families failed.
- Separate ENTRY EDGE failure from EXIT / TP-SL design failure.
- Compute MFE/MAE after each candidate entry using M1 broker-feed data.
- Avoid filter-mining.

Definitions:
- MFE = Maximum Favorable Excursion: best price movement in trade direction after entry.
- MAE = Maximum Adverse Excursion: worst price movement against trade direction after entry.
- If MFE is poor and MAE is large, entry thesis is weak.
- If MFE is meaningful but realized exits are bad, exit/risk design may be weak.

Hard rules:
- Research only.
- Read-only SQLite.
- Reads Stage 7B trades CSV.
- No EA modification.
- No order sending.
- No demo/paper/live authorization.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Dict, List, Optional, Sequence, Tuple


TOOL_VERSION = "v1"

DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_TRADES = Path("data/reports/stage7b_strategy_redesign_lab/stage7b_strategy_trades.csv")
DEFAULT_OUT_DIR = Path("data/reports/stage7c_edge_diagnostics_lab")


@dataclass
class M1Bar:
    t: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass
class DiagnosticRow:
    family: str
    design: str
    guard_variant: str
    direction: str
    session: str
    entry_utc: str
    entry_price: float
    realized_exit_reason: str
    realized_net_x1: float
    horizon_hours: int
    mfe_usd: float
    mae_usd: float
    close_move_usd: float
    hit_plus_10: bool
    hit_plus_15: bool
    hit_plus_24: bool
    hit_minus_10: bool
    hit_minus_15: bool
    hit_minus_20: bool
    first_hit_15_15: str
    first_hit_24_15: str
    bars_checked: int


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_time(v: str) -> Optional[datetime]:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M"):
        try:
            dt = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            pass
    return None


def safe_float(v, default=0.0) -> float:
    try:
        if v is None or str(v).strip() == "":
            return default
        return float(str(v).strip())
    except Exception:
        return default


def connect_ro(db: Path) -> sqlite3.Connection:
    if not db.exists():
        raise FileNotFoundError(f"DB not found: {db}")
    conn = sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_m1(conn: sqlite3.Connection) -> List[M1Bar]:
    rows = conn.execute(
        """
        SELECT utc_time, open, high, low, close
        FROM bars
        WHERE source='amarkets_mt5' AND symbol='XAUUSD' AND timeframe='1m'
        ORDER BY utc_time ASC
        """
    ).fetchall()
    out = []
    for r in rows:
        t = parse_time(r["utc_time"])
        if t is None:
            continue
        out.append(M1Bar(t=t, open=float(r["open"]), high=float(r["high"]), low=float(r["low"]), close=float(r["close"])))
    return out


def read_trades(path: Path) -> List[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Stage 7B trades CSV not found: {path}. Run Stage 7B first.")
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    rows = list(csv.DictReader(text.splitlines()))
    return rows


def first_hit(path: Sequence[M1Bar], direction: str, entry: float, plus: float, minus: float) -> str:
    if not path:
        return "none"
    if direction == "long":
        tp = entry + plus
        sl = entry - minus
        for b in path:
            hit_tp = b.high >= tp
            hit_sl = b.low <= sl
            if hit_tp and hit_sl:
                return "ambiguous_conservative_sl"
            if hit_sl:
                return "sl_first"
            if hit_tp:
                return "tp_first"
    else:
        tp = entry - plus
        sl = entry + minus
        for b in path:
            hit_tp = b.low <= tp
            hit_sl = b.high >= sl
            if hit_tp and hit_sl:
                return "ambiguous_conservative_sl"
            if hit_sl:
                return "sl_first"
            if hit_tp:
                return "tp_first"
    return "none"


def diagnose_trade(tr: dict, m1: Sequence[M1Bar], times: Sequence[datetime], horizon_h: int) -> Optional[DiagnosticRow]:
    entry_t = parse_time(tr.get("entry_utc"))
    if entry_t is None:
        return None
    entry = safe_float(tr.get("entry_price"))
    direction = tr.get("direction", "").strip().lower()
    if direction not in {"long", "short"}:
        return None

    si = bisect.bisect_left(times, entry_t)
    ei = bisect.bisect_left(times, entry_t + timedelta(hours=horizon_h))
    if si >= len(m1) or si >= ei:
        return None
    path = m1[si:ei]

    if direction == "long":
        mfe = max(b.high for b in path) - entry
        mae = min(b.low for b in path) - entry
        close_move = path[-1].close - entry
        hit_plus_10 = any(b.high >= entry + 10 for b in path)
        hit_plus_15 = any(b.high >= entry + 15 for b in path)
        hit_plus_24 = any(b.high >= entry + 24 for b in path)
        hit_minus_10 = any(b.low <= entry - 10 for b in path)
        hit_minus_15 = any(b.low <= entry - 15 for b in path)
        hit_minus_20 = any(b.low <= entry - 20 for b in path)
    else:
        mfe = entry - min(b.low for b in path)
        mae = entry - max(b.high for b in path)
        close_move = entry - path[-1].close
        hit_plus_10 = any(b.low <= entry - 10 for b in path)
        hit_plus_15 = any(b.low <= entry - 15 for b in path)
        hit_plus_24 = any(b.low <= entry - 24 for b in path)
        hit_minus_10 = any(b.high >= entry + 10 for b in path)
        hit_minus_15 = any(b.high >= entry + 15 for b in path)
        hit_minus_20 = any(b.high >= entry + 20 for b in path)

    return DiagnosticRow(
        family=tr.get("family", ""),
        design=tr.get("design", ""),
        guard_variant=tr.get("guard_variant", ""),
        direction=direction,
        session=tr.get("session", ""),
        entry_utc=entry_t.isoformat(),
        entry_price=round(entry, 6),
        realized_exit_reason=tr.get("exit_reason", ""),
        realized_net_x1=safe_float(tr.get("net_x1")),
        horizon_hours=horizon_h,
        mfe_usd=round(mfe, 6),
        mae_usd=round(mae, 6),
        close_move_usd=round(close_move, 6),
        hit_plus_10=hit_plus_10,
        hit_plus_15=hit_plus_15,
        hit_plus_24=hit_plus_24,
        hit_minus_10=hit_minus_10,
        hit_minus_15=hit_minus_15,
        hit_minus_20=hit_minus_20,
        first_hit_15_15=first_hit(path, direction, entry, 15, 15),
        first_hit_24_15=first_hit(path, direction, entry, 24, 15),
        bars_checked=len(path),
    )


def pct(flag_values: Sequence[bool]) -> float:
    if not flag_values:
        return 0.0
    return round(sum(1 for x in flag_values if x) / len(flag_values), 6)


def summarize_group(rows: List[DiagnosticRow]) -> dict:
    mfes = [r.mfe_usd for r in rows]
    maes = [r.mae_usd for r in rows]
    closes = [r.close_move_usd for r in rows]
    realized = [r.realized_net_x1 for r in rows]
    tp15_first = [r.first_hit_15_15 == "tp_first" for r in rows]
    sl15_first = [r.first_hit_15_15 in {"sl_first", "ambiguous_conservative_sl"} for r in rows]
    tp24_first = [r.first_hit_24_15 == "tp_first" for r in rows]
    sl24_first = [r.first_hit_24_15 in {"sl_first", "ambiguous_conservative_sl"} for r in rows]

    summary = {
        "family": rows[0].family if rows else "",
        "design": rows[0].design if rows else "",
        "guard_variant": rows[0].guard_variant if rows else "",
        "horizon_hours": rows[0].horizon_hours if rows else 0,
        "trades": len(rows),
        "median_mfe": round(median(mfes), 6) if mfes else 0.0,
        "median_mae": round(median(maes), 6) if maes else 0.0,
        "median_close_move": round(median(closes), 6) if closes else 0.0,
        "median_realized_net": round(median(realized), 6) if realized else 0.0,
        "hit_plus_10_rate": pct([r.hit_plus_10 for r in rows]),
        "hit_plus_15_rate": pct([r.hit_plus_15 for r in rows]),
        "hit_plus_24_rate": pct([r.hit_plus_24 for r in rows]),
        "hit_minus_10_rate": pct([r.hit_minus_10 for r in rows]),
        "hit_minus_15_rate": pct([r.hit_minus_15 for r in rows]),
        "hit_minus_20_rate": pct([r.hit_minus_20 for r in rows]),
        "tp15_first_rate": pct(tp15_first),
        "sl15_first_rate": pct(sl15_first),
        "tp24_first_rate": pct(tp24_first),
        "sl24_first_rate": pct(sl24_first),
        "avg_mfe_minus_abs_mae": round((sum(mfes) / len(mfes)) - abs(sum(maes) / len(maes)), 6) if rows else 0.0,
    }
    summary["diagnosis"] = diagnose_summary(summary)
    return summary


def diagnose_summary(s: dict) -> str:
    if s["trades"] < 80:
        return "INSUFFICIENT_SAMPLE"
    if s["median_mfe"] < 8 and abs(s["median_mae"]) >= 8:
        return "ENTRY_EDGE_WEAK"
    if s["tp15_first_rate"] <= s["sl15_first_rate"]:
        return "ENTRY_OR_STOP_GEOMETRY_WEAK"
    if s["hit_plus_15_rate"] >= 0.55 and s["tp15_first_rate"] > s["sl15_first_rate"] and s["median_realized_net"] < 0:
        return "EXIT_DESIGN_WEAK_ENTRY_HAS_SOME_MFE"
    if s["hit_plus_24_rate"] < 0.35 and s["hit_plus_15_rate"] >= 0.48:
        return "TP_TOO_FAR_CONSIDER_SMALLER_TARGET_RESEARCH_ONLY"
    if s["avg_mfe_minus_abs_mae"] > 1.5 and s["median_close_move"] > 0:
        return "WATCHLIST_ENTRY_EDGE_POSSIBLE"
    return "NO_CLEAR_EDGE"


def run_diagnostics(trades: List[dict], m1: List[M1Bar], horizons: Sequence[int]) -> Tuple[List[DiagnosticRow], List[dict]]:
    times = [b.t for b in m1]
    diag_rows: List[DiagnosticRow] = []
    for tr in trades:
        for h in horizons:
            r = diagnose_trade(tr, m1, times, h)
            if r is not None:
                diag_rows.append(r)

    groups: Dict[Tuple[str, str, str, int], List[DiagnosticRow]] = {}
    for r in diag_rows:
        groups.setdefault((r.family, r.design, r.guard_variant, r.horizon_hours), []).append(r)
    summaries = [summarize_group(v) for k, v in sorted(groups.items())]
    summaries.sort(key=lambda x: (x["diagnosis"].startswith("WATCHLIST"), x["tp15_first_rate"], x["avg_mfe_minus_abs_mae"]), reverse=True)
    return diag_rows, summaries


def write_outputs(out_dir: Path, payload: dict, rows: List[DiagnosticRow], summaries: List[dict]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload["summaries"] = summaries
    (out_dir / "stage7c_edge_diagnostics_lab.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    if rows:
        with (out_dir / "stage7c_trade_diagnostics.csv").open("w", newline="", encoding="utf-8") as f:
            cols = list(asdict(rows[0]).keys())
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for r in rows:
                w.writerow(asdict(r))

    with (out_dir / "stage7c_edge_summaries.csv").open("w", newline="", encoding="utf-8") as f:
        cols = [
            "family", "design", "guard_variant", "horizon_hours", "diagnosis", "trades",
            "median_mfe", "median_mae", "median_close_move", "median_realized_net",
            "hit_plus_10_rate", "hit_plus_15_rate", "hit_plus_24_rate",
            "hit_minus_10_rate", "hit_minus_15_rate", "hit_minus_20_rate",
            "tp15_first_rate", "sl15_first_rate", "tp24_first_rate", "sl24_first_rate",
            "avg_mfe_minus_abs_mae",
        ]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for s in summaries:
            w.writerow({c: s.get(c) for c in cols})

    lines = [
        "# Stage 7C Edge Diagnostics Lab",
        "",
        f"Generated UTC: `{payload['generated_utc']}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: research only. This does not authorize demo, paper, or live orders.",
        "",
        "## Inputs",
        f"- db: `{payload['db_path']}`",
        f"- trades_csv: `{payload['trades_csv']}`",
        f"- m1_rows: `{payload['m1_rows']}`",
        f"- trades_loaded: `{payload['trades_loaded']}`",
        f"- horizons: `{payload['horizons']}`",
        "",
        "## Summary ranking",
        "| Family | Design | Guard | Horizon | Diagnosis | Trades | Median MFE | Median MAE | TP15 first | SL15 first | TP24 first | SL24 first | MFE-absMAE |",
        "|---|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in summaries:
        lines.append(
            f"| {s['family']} | {s['design']} | {s['guard_variant']} | {s['horizon_hours']} | {s['diagnosis']} | "
            f"{s['trades']} | {s['median_mfe']} | {s['median_mae']} | {s['tp15_first_rate']} | {s['sl15_first_rate']} | "
            f"{s['tp24_first_rate']} | {s['sl24_first_rate']} | {s['avg_mfe_minus_abs_mae']} |"
        )

    lines += [
        "",
        "## Interpretation",
        "- `ENTRY_EDGE_WEAK`: price usually does not move favorably enough after entry.",
        "- `ENTRY_OR_STOP_GEOMETRY_WEAK`: even 15/15 first-hit test does not favor TP.",
        "- `EXIT_DESIGN_WEAK_ENTRY_HAS_SOME_MFE`: entry has some favorable excursion, but realized exit design is poor.",
        "- `TP_TOO_FAR_CONSIDER_SMALLER_TARGET_RESEARCH_ONLY`: 24 USD target may be too far relative to signal quality.",
        "- `WATCHLIST_ENTRY_EDGE_POSSIBLE`: only a research candidate; still requires Stage 7D validation.",
        "",
        "## Decision",
        "- Do not add more filters before reading this diagnosis.",
        "- If all groups are weak, redesign entries from higher-level market structure or add discretionary/macro regime layer.",
        "- No EA change is allowed from this report.",
    ]
    (out_dir / "stage7c_edge_diagnostics_lab.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--trades-csv", default=str(DEFAULT_TRADES))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--horizons", default="3,6,12", help="Comma-separated horizon hours")
    args = p.parse_args()

    horizons = [int(x.strip()) for x in args.horizons.split(",") if x.strip()]
    conn = connect_ro(Path(args.db))
    m1 = load_m1(conn)
    conn.close()
    trades = read_trades(Path(args.trades_csv))

    rows, summaries = run_diagnostics(trades, m1, horizons)
    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": now_iso(),
        "db_path": str(Path(args.db)),
        "trades_csv": str(Path(args.trades_csv)),
        "m1_rows": len(m1),
        "trades_loaded": len(trades),
        "horizons": horizons,
    }
    write_outputs(Path(args.out_dir), payload, rows, summaries)

    print("Stage 7C edge diagnostics lab: DONE")
    print(f"trades_loaded={len(trades)} diagnostics={len(rows)} m1_rows={len(m1)}")
    print(f"Report: {Path(args.out_dir) / 'stage7c_edge_diagnostics_lab.md'}")
    print(f"Summary CSV: {Path(args.out_dir) / 'stage7c_edge_summaries.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
