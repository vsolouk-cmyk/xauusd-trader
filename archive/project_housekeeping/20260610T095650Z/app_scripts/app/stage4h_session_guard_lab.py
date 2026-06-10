"""Stage 4H session/guard lab for XAUUSD AMarkets non-overlap trades.

Purpose:
- Read Stage 4G v2 non-overlap trade CSV.
- Test simple session filters without re-running the full M1 replay.
- Report which guard candidates are worth deeper replay / dry-run monitoring.

Hard rule: this analysis does not authorize demo, paper, or live orders.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

DEFAULT_TRADES_CSV = Path("data/reports/stage4g_v2/stage4g_v2_non_overlap_trades.csv")
DEFAULT_OUT_DIR = Path("data/reports/stage4h_session_guard_lab")
STRATEGY_ID = "xauusd_long_tp24_sl15_no_london_v1"
TOOL_VERSION = "v1"

SESSION_CANDIDATES = [
    "session",
    "session_utc",
    "session_name",
    "entry_session",
    "signal_session",
]
NET_CANDIDATES = [
    "net_usd",
    "net",
    "net_return_usd",
    "trade_net_usd",
    "pnl_usd",
    "profit_usd",
    "result_usd",
]
TIME_CANDIDATES = [
    "entry_time_utc",
    "entry_utc",
    "signal_time_utc",
    "closed_h1_time_utc",
    "closed_h1_utc",
    "signal_closed_h1_time_gmt_now",
    "signal_closed_h1_time_server",
    "entry_time",
    "open_time",
]
YEAR_CANDIDATES = ["year", "entry_year", "signal_year"]

FILTERS: Dict[str, Dict[str, Sequence[str]]] = {
    "base_all": {"include": (), "exclude": ()},
    "no_asia": {"include": (), "exclude": ("asia",)},
    "no_asia_no_new_york": {"include": (), "exclude": ("asia", "new_york")},
    "overlap_newyork_other": {"include": ("london_ny_overlap", "new_york", "other"), "exclude": ()},
    "overlap_other": {"include": ("london_ny_overlap", "other"), "exclude": ()},
    "london_ny_overlap_only": {"include": ("london_ny_overlap",), "exclude": ()},
    "new_york_only": {"include": ("new_york",), "exclude": ()},
    "other_only": {"include": ("other",), "exclude": ()},
}


def _normalize_key(s: str) -> str:
    return s.strip().lower().replace(" ", "_").replace("-", "_")


def _find_col(fieldnames: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    normalized = {_normalize_key(c): c for c in fieldnames}
    for cand in candidates:
        key = _normalize_key(cand)
        if key in normalized:
            return normalized[key]
    # fallback: contains match, conservative
    for cand in candidates:
        key = _normalize_key(cand)
        for norm, original in normalized.items():
            if key in norm or norm in key:
                return original
    return None


def _parse_float(value: object) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_dt(value: object) -> Optional[datetime]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    formats = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y.%m.%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y.%m.%d %H:%M",
        "%Y-%m-%d %H:%M",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except ValueError:
            pass
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except ValueError:
        return None


@dataclass
class Trade:
    row_index: int
    session: str
    net_usd: float
    when: Optional[datetime]
    raw: Dict[str, str]


def read_trades(path: Path) -> Tuple[List[Trade], Dict[str, object]]:
    if not path.exists():
        raise FileNotFoundError(f"Trade CSV not found: {path}")

    text = path.read_text(encoding="utf-8-sig", errors="replace")
    sample = text[:4096]
    delimiter = "\t" if sample.count("\t") >= sample.count(",") else ","
    reader = csv.DictReader(text.splitlines(), delimiter=delimiter)
    if not reader.fieldnames:
        raise ValueError(f"No CSV header found in {path}")

    session_col = _find_col(reader.fieldnames, SESSION_CANDIDATES)
    net_col = _find_col(reader.fieldnames, NET_CANDIDATES)
    time_col = _find_col(reader.fieldnames, TIME_CANDIDATES)
    year_col = _find_col(reader.fieldnames, YEAR_CANDIDATES)

    if not net_col:
        raise ValueError(
            "Could not infer net/PnL column. Header columns: " + ", ".join(reader.fieldnames)
        )
    if not session_col:
        raise ValueError(
            "Could not infer session column. Header columns: " + ", ".join(reader.fieldnames)
        )

    trades: List[Trade] = []
    bad_rows: List[Dict[str, object]] = []
    for idx, row in enumerate(reader, start=2):
        net = _parse_float(row.get(net_col))
        if net is None:
            bad_rows.append({"line": idx, "reason": "bad_net", "value": row.get(net_col)})
            continue
        session = str(row.get(session_col, "")).strip().lower()
        when = _parse_dt(row.get(time_col)) if time_col else None
        if when is None and year_col and row.get(year_col):
            year = _parse_float(row.get(year_col))
            if year:
                when = datetime(int(year), 1, 1)
        trades.append(Trade(row_index=idx, session=session, net_usd=net, when=when, raw=row))

    meta = {
        "path": str(path),
        "delimiter": "TAB" if delimiter == "\t" else delimiter,
        "fieldnames": reader.fieldnames,
        "session_col": session_col,
        "net_col": net_col,
        "time_col": time_col,
        "year_col": year_col,
        "rows_parsed": len(trades),
        "bad_rows": bad_rows[:20],
        "bad_row_count": len(bad_rows),
    }
    return trades, meta


def profit_factor(values: Sequence[float]) -> Optional[float]:
    gross_pos = sum(v for v in values if v > 0)
    gross_neg = -sum(v for v in values if v < 0)
    if gross_neg == 0:
        return None if gross_pos == 0 else math.inf
    return gross_pos / gross_neg


def max_drawdown(values: Sequence[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for v in values:
        equity += v
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return max_dd


def metrics(values: Sequence[float]) -> Dict[str, object]:
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
            "best_net_usd": None,
            "worst_net_usd": None,
        }
    pf = profit_factor(vals)
    return {
        "trades": len(vals),
        "total_net_usd": round(sum(vals), 6),
        "avg_net_usd": round(sum(vals) / len(vals), 6),
        "median_net_usd": round(median(vals), 6),
        "win_rate": round(sum(1 for v in vals if v > 0) / len(vals), 6),
        "profit_factor": None if pf is None else ("inf" if pf == math.inf else round(pf, 6)),
        "max_drawdown_usd": round(max_drawdown(vals), 6),
        "best_net_usd": round(max(vals), 6),
        "worst_net_usd": round(min(vals), 6),
    }


def apply_filter(trades: Sequence[Trade], include: Sequence[str], exclude: Sequence[str]) -> List[Trade]:
    inc = {s.lower() for s in include if s}
    exc = {s.lower() for s in exclude if s}
    out = []
    for t in trades:
        if inc and t.session not in inc:
            continue
        if exc and t.session in exc:
            continue
        out.append(t)
    return out


def cost_stress(values: Sequence[float], roundtrip_cost_usd: float) -> Dict[str, Dict[str, object]]:
    out: Dict[str, Dict[str, object]] = {}
    for mult in (1, 2, 3, 4):
        extra = roundtrip_cost_usd * (mult - 1)
        stressed = [v - extra for v in values]
        out[f"cost_x{mult}"] = metrics(stressed)
    return out


def by_year(trades: Sequence[Trade]) -> Dict[str, Dict[str, object]]:
    buckets: Dict[str, List[float]] = {}
    for t in trades:
        y = str(t.when.year) if t.when else "unknown"
        buckets.setdefault(y, []).append(t.net_usd)
    return {k: metrics(v) for k, v in sorted(buckets.items())}


def build_report(trades: List[Trade], meta: Dict[str, object], args: argparse.Namespace) -> Dict[str, object]:
    report: Dict[str, object] = {
        "tool_version": TOOL_VERSION,
        "strategy_id": STRATEGY_ID,
        "generated_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "input": meta,
        "roundtrip_cost_usd": args.roundtrip_cost_usd,
        "min_trades": args.min_trades,
        "filters": {},
    }
    for name, spec in FILTERS.items():
        ftrades = apply_filter(trades, spec.get("include", ()), spec.get("exclude", ()))
        values = [t.net_usd for t in ftrades]
        m = metrics(values)
        m["include_sessions"] = list(spec.get("include", ()))
        m["exclude_sessions"] = list(spec.get("exclude", ()))
        m["cost_stress"] = cost_stress(values, args.roundtrip_cost_usd)
        m["year_breakdown"] = by_year(ftrades)
        # Conservative quality flags. These are advisory only.
        pf = m.get("profit_factor")
        pf_float = None if pf in (None, "inf") else float(pf)
        med = m.get("median_net_usd")
        total = float(m.get("total_net_usd", 0.0))
        trades_n = int(m.get("trades", 0))
        cost_x3 = m["cost_stress"]["cost_x3"]
        cost_x4 = m["cost_stress"]["cost_x4"]
        flags = []
        if trades_n < args.min_trades:
            flags.append("too_few_trades")
        if total <= 0:
            flags.append("non_positive_total")
        if pf_float is not None and pf_float < args.min_pf:
            flags.append("pf_below_threshold")
        if med is not None and float(med) < 0:
            flags.append("negative_median")
        if float(cost_x3.get("total_net_usd") or 0.0) <= 0:
            flags.append("cost_x3_not_positive")
        if float(cost_x4.get("total_net_usd") or 0.0) <= 0:
            flags.append("cost_x4_not_positive")
        m["flags"] = flags
        m["guard_lab_status"] = "PASS" if not flags else ("WARN" if total > 0 and trades_n >= args.min_trades else "FAIL")
        report["filters"][name] = m
    return report


def md_metrics_block(name: str, m: Dict[str, object], include_cost: bool = False) -> List[str]:
    lines = [f"### {name}"]
    for key in [
        "guard_lab_status",
        "trades",
        "total_net_usd",
        "avg_net_usd",
        "median_net_usd",
        "win_rate",
        "profit_factor",
        "max_drawdown_usd",
        "best_net_usd",
        "worst_net_usd",
        "include_sessions",
        "exclude_sessions",
        "flags",
    ]:
        lines.append(f"- {key}: `{m.get(key)}`")
    if include_cost:
        lines.append("\n#### Cost stress")
        for cname, cm in m.get("cost_stress", {}).items():
            lines.append(f"- {cname}: total=`{cm.get('total_net_usd')}`, PF=`{cm.get('profit_factor')}`, median=`{cm.get('median_net_usd')}`, maxDD=`{cm.get('max_drawdown_usd')}`")
    return lines


def write_outputs(report: Dict[str, object], out_dir: Path) -> Tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "stage4h_session_guard_lab.json"
    md_path = out_dir / "stage4h_session_guard_lab.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines: List[str] = []
    lines.append("# Stage 4H Session Guard Lab")
    lines.append("")
    lines.append(f"Generated UTC: `{report['generated_utc']}`")
    lines.append(f"Tool version: `{TOOL_VERSION}`")
    lines.append(f"Strategy ID: `{STRATEGY_ID}`")
    lines.append("")
    lines.append("> Hard rule: this is filter research only. It does not authorize demo, paper, or live orders.")
    lines.append("")
    lines.append("## Interpretation")
    lines.append("- Stage 4G v2 non-overlap remains the decision basis.")
    lines.append("- This lab only tests simple session guards on the non-overlap trade list.")
    lines.append("- A promising filter requires deeper replay and live dry-run monitoring before any EA change.")
    lines.append("")
    lines.append("## Input")
    meta = report["input"]
    for k in ["path", "delimiter", "rows_parsed", "bad_row_count", "session_col", "net_col", "time_col", "year_col"]:
        lines.append(f"- {k}: `{meta.get(k)}`")
    lines.append("")
    lines.append("## Filter summary")
    lines.append("")
    lines.append("| Filter | Status | Trades | Total | PF | Median | Max DD | Flags |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
    for name, m in report["filters"].items():
        lines.append(
            f"| {name} | {m.get('guard_lab_status')} | {m.get('trades')} | {m.get('total_net_usd')} | {m.get('profit_factor')} | {m.get('median_net_usd')} | {m.get('max_drawdown_usd')} | {', '.join(m.get('flags') or [])} |"
        )
    lines.append("")
    lines.append("## Detailed candidates")
    for name in ["base_all", "no_asia", "overlap_newyork_other", "overlap_other", "london_ny_overlap_only", "new_york_only", "other_only"]:
        lines.extend(md_metrics_block(name, report["filters"][name], include_cost=True))
        lines.append("")
    lines.append("## Decision")
    lines.append("No demo-order authorization. Use this report to decide whether to run a deeper replay for a narrower session guard and to define Stage 5C live outcome tracking.")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Stage 4H session guard lab for XAUUSD AMarkets non-overlap trades")
    parser.add_argument("--trades-csv", default=str(DEFAULT_TRADES_CSV), help="Stage 4G v2 non-overlap trades CSV")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Output directory")
    parser.add_argument("--roundtrip-cost-usd", type=float, default=0.35, help="Base roundtrip cost already assumed in net values")
    parser.add_argument("--min-trades", type=int, default=50)
    parser.add_argument("--min-pf", type=float, default=1.10)
    args = parser.parse_args(argv)

    trades, meta = read_trades(Path(args.trades_csv).expanduser())
    report = build_report(trades, meta, args)
    json_path, md_path = write_outputs(report, Path(args.out_dir))

    base = report["filters"].get("base_all", {})
    print("Stage 4H session guard lab: DONE")
    print(f"Input trades: {meta.get('rows_parsed')} | base_total={base.get('total_net_usd')} | base_pf={base.get('profit_factor')}")
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
