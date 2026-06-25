#!/usr/bin/env python3
"""Shared helpers for Stage66 H64L fast decision package.

No broker connection. No orders. Pure file-based research/audit utilities.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

DateLike = dt.date


def parse_date(value: Any) -> Optional[dt.date]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    # Date-only fast path
    try:
        if len(s) >= 10 and s[4] == "-" and s[7] == "-":
            return dt.date.fromisoformat(s[:10])
    except Exception:
        pass
    try:
        return dt.datetime.fromisoformat(s).date()
    except Exception:
        return None


def parse_datetime(value: Any) -> Optional[dt.datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        d = dt.datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(dt.timezone.utc)
    except Exception:
        d0 = parse_date(value)
        if d0 is None:
            return None
        return dt.datetime(d0.year, d0.month, d0.day, tzinfo=dt.timezone.utc)


def parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if not s or s.lower() in {"nan", "none", "null"}:
        return None
    try:
        x = float(s)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    except Exception:
        return None


def read_csv(path: Path) -> Tuple[List[Dict[str, str]], List[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = [dict(r) for r in reader]
        return rows, list(reader.fieldnames or [])


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_sha256(obj: Any) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def load_locked_rule(path: Path) -> Dict[str, Any]:
    rule = read_json(path)
    payload = rule.get("rule_lock_payload")
    expected = rule.get("rule_sha256")
    actual = canonical_sha256(payload)
    if expected != actual:
        raise ValueError(f"H64L rule hash mismatch: expected={expected} actual={actual}")
    return rule


def condition_pass(row: Dict[str, Any], condition: Dict[str, Any]) -> Tuple[bool, str]:
    field = condition["field"]
    op = condition["operator"]
    threshold = float(condition["threshold"])
    v = parse_float(row.get(field))
    if v is None:
        return False, f"{field}:MISSING{op}{threshold}"
    ok = False
    if op == ">":
        ok = v > threshold
    elif op == ">=":
        ok = v >= threshold
    elif op == "<":
        ok = v < threshold
    elif op == "<=":
        ok = v <= threshold
    elif op == "==":
        ok = v == threshold
    else:
        raise ValueError(f"Unsupported operator {op}")
    return ok, "" if ok else f"{field}:{v}{op}{threshold}"


def apply_h64l_rule(row: Dict[str, Any], locked_rule: Dict[str, Any]) -> Tuple[bool, List[str]]:
    failures: List[str] = []
    for cond in locked_rule["rule_lock_payload"]["conditions"]:
        ok, fail = condition_pass(row, cond)
        if not ok:
            failures.append(fail)
    return len(failures) == 0, failures


def get_date_col(fields: Iterable[str], preferred: Iterable[str]) -> Optional[str]:
    field_set = set(fields)
    for c in preferred:
        if c in field_set:
            return c
    return None


def sort_rows_by_date(rows: List[Dict[str, str]], date_col: str) -> List[Dict[str, str]]:
    return sorted([r for r in rows if parse_date(r.get(date_col)) is not None], key=lambda r: parse_date(r.get(date_col)))


def build_external_index(rows: List[Dict[str, str]], date_col: str = "date_utc", close_col: str = "close") -> List[Tuple[dt.date, float, Dict[str, str]]]:
    out: List[Tuple[dt.date, float, Dict[str, str]]] = []
    for r in rows:
        d = parse_date(r.get(date_col))
        c = parse_float(r.get(close_col))
        if d is not None and c is not None:
            out.append((d, c, r))
    out.sort(key=lambda x: x[0])
    return out


def first_index_on_or_after(series: List[Tuple[dt.date, float, Dict[str, str]]], d: dt.date) -> Optional[int]:
    lo, hi = 0, len(series)
    while lo < hi:
        mid = (lo + hi) // 2
        if series[mid][0] < d:
            lo = mid + 1
        else:
            hi = mid
    return lo if lo < len(series) else None


def horizon_return_bps(series: List[Tuple[dt.date, float, Dict[str, str]]], start_date: dt.date, horizon_trading_days: int) -> Tuple[Optional[float], Optional[dt.date], Optional[dt.date]]:
    i = first_index_on_or_after(series, start_date)
    if i is None:
        return None, None, None
    j = i + int(horizon_trading_days)
    if j >= len(series):
        return None, series[i][0], None
    start_close = series[i][1]
    end_close = series[j][1]
    if start_close <= 0:
        return None, series[i][0], series[j][0]
    return (end_close / start_close - 1.0) * 10000.0, series[i][0], series[j][0]


def filter_rows_asof(rows: List[Dict[str, str]], asof_date: dt.date, available_after_col: str = "sample_available_after_utc") -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    asof_dt = dt.datetime(asof_date.year, asof_date.month, asof_date.day, 23, 59, 59, tzinfo=dt.timezone.utc)
    for r in rows:
        a = parse_datetime(r.get(available_after_col))
        if a is not None and a <= asof_dt:
            out.append(r)
    return out


def assert_no_lookahead(rows: List[Dict[str, str]], asof_date: dt.date, available_after_col: str = "sample_available_after_utc") -> Tuple[bool, List[Dict[str, Any]]]:
    breaches: List[Dict[str, Any]] = []
    asof_dt = dt.datetime(asof_date.year, asof_date.month, asof_date.day, 23, 59, 59, tzinfo=dt.timezone.utc)
    for idx, r in enumerate(rows):
        a = parse_datetime(r.get(available_after_col))
        if a is None:
            breaches.append({"row_index": idx, "issue": "missing_or_unparseable_available_after"})
        elif a > asof_dt:
            breaches.append({"row_index": idx, "available_after": a.isoformat(), "asof_date": asof_date.isoformat()})
    return len(breaches) == 0, breaches


def mean(xs: List[float]) -> Optional[float]:
    xs = [x for x in xs if x is not None and not math.isnan(x)]
    return sum(xs) / len(xs) if xs else None


def stddev(xs: List[float]) -> Optional[float]:
    xs = [x for x in xs if x is not None and not math.isnan(x)]
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def max_drawdown_from_returns_bps(returns_bps: List[float]) -> Optional[float]:
    if not returns_bps:
        return None
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for rb in returns_bps:
        equity *= 1.0 + rb / 10000.0
        peak = max(peak, equity)
        if peak > 0:
            max_dd = min(max_dd, equity / peak - 1.0)
    return max_dd * 10000.0


def write_report(path: Path, title: str, sections: List[Tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {title}", ""]
    for heading, body in sections:
        lines.append(f"## {heading}")
        lines.append("")
        lines.append(body.rstrip())
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
