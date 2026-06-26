#!/usr/bin/env python3
"""
Stage67D6: download-format-aware local refresh, source repair, macro rebuild, optional Stage66J2.

No internet download. No broker/order/EA/paper-live/live action.
Uses only Python standard library so it can run on the user's Mac without extra packages.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
INVESTING_SLASH_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
MT5_DATE_RE = re.compile(r"^(\d{4})\.(\d{2})\.(\d{2})$")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize_header(s: Any) -> str:
    return str(s or "").strip().replace("\ufeff", "")


def to_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    txt = str(x).strip().replace(",", "")
    if not txt or txt in {".", "-", "—"} or txt.lower() in {"nan", "nat", "none", "null"}:
        return None
    if txt.endswith("%"):
        txt = txt[:-1]
    try:
        v = float(txt)
    except ValueError:
        return None
    if not math.isfinite(v):
        return None
    return v


def parse_iso_date(s: Any) -> Optional[date]:
    txt = str(s or "").strip()
    if not ISO_RE.match(txt):
        return None
    try:
        return datetime.strptime(txt, "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_investing_date_month_first(s: Any) -> Optional[date]:
    txt = str(s or "").strip()
    d = parse_iso_date(txt)
    if d:
        return d
    m = INVESTING_SLASH_RE.match(txt)
    if m:
        mm, dd, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(yy, mm, dd)
        except ValueError:
            return None
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(txt, fmt).date()
        except ValueError:
            pass
    return None


def parse_fred_date(s: Any) -> Optional[date]:
    return parse_iso_date(s)


def parse_mt5_date_time(d: Any, t: Any) -> Optional[datetime]:
    ds = str(d or "").strip()
    ts = str(t or "00:00:00").strip() or "00:00:00"
    m = MT5_DATE_RE.match(ds)
    if not m:
        return None
    try:
        return datetime.strptime(ds + " " + ts, "%Y.%m.%d %H:%M:%S")
    except ValueError:
        return None


def excel_serial_to_date(v: Any) -> Optional[date]:
    x = to_float(v)
    if x is None:
        return parse_iso_date(v)
    try:
        return (datetime(1899, 12, 30) + timedelta(days=x)).date()
    except Exception:
        return None


def sniff_dialect(path: Path) -> csv.Dialect:
    sample = path.read_text(encoding="utf-8-sig", errors="ignore")[:4096]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t")
    except Exception:
        return csv.get_dialect("excel")


def read_csv_dicts(path: Path) -> Tuple[List[Dict[str, str]], List[str]]:
    dialect = sniff_dialect(path)
    with path.open("r", encoding="utf-8-sig", newline="", errors="ignore") as f:
        rdr = csv.DictReader(f, dialect=dialect)
        rows = [dict(r) for r in rdr]
        cols = [normalize_header(c) for c in (rdr.fieldnames or [])]
    return rows, cols


def choose_col(cols: List[str], candidates: Iterable[str]) -> Optional[str]:
    exact = {normalize_header(c): normalize_header(c) for c in cols}
    lower = {normalize_header(c).lower(): normalize_header(c) for c in cols}
    for cand in candidates:
        c = normalize_header(cand)
        if c in exact:
            return exact[c]
        if c.lower() in lower:
            return lower[c.lower()]
    return None


def write_rows(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def write_series(path: Path, series_rows: List[Dict[str, Any]]) -> None:
    write_rows(path, series_rows, ["date_utc", "value"])


def inspect_csv_basic(path: Path) -> Dict[str, Any]:
    info: Dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        return info
    try:
        rows, cols = read_csv_dicts(path)
        info["columns"] = cols
        info["rows"] = len(rows)
        info["sha256"] = sha256_file(path)
        if rows and "date_utc" in cols:
            ds = [parse_iso_date(r.get("date_utc")) for r in rows]
            ds = [d for d in ds if d]
            if ds:
                info["min_date"] = min(ds).isoformat()
                info["max_date"] = max(ds).isoformat()
    except Exception as e:
        info["error"] = str(e)
    return info


def parse_investing_dxy(path: Path) -> Dict[str, Any]:
    rows, cols = read_csv_dicts(path)
    date_col = choose_col(cols, ["Date"])
    value_col = choose_col(cols, ["Price", "Close", "value"])
    if not date_col or not value_col:
        return {"status": "FAIL", "error": f"DXY columns not found; columns={cols}", "rows": 0}
    out: Dict[str, float] = {}
    parse_fail = value_fail = 0
    for r in rows:
        d = parse_investing_date_month_first(r.get(date_col))
        v = to_float(r.get(value_col))
        if d is None:
            parse_fail += 1
            continue
        if v is None:
            value_fail += 1
            continue
        out[d.isoformat()] = v
    dates = sorted(out)
    return {
        "status": "PASS" if dates else "FAIL",
        "source_format": "investing_csv_month_first",
        "path": str(path),
        "input_columns": cols,
        "date_col": date_col,
        "value_col": value_col,
        "rows_in": len(rows),
        "rows": len(dates),
        "parse_fail": parse_fail,
        "value_fail": value_fail,
        "min_date": dates[0] if dates else None,
        "max_date": dates[-1] if dates else None,
        "series": [{"date_utc": d, "value": out[d]} for d in dates],
    }


def parse_fred_series(path: Path, value_col_name: str, source_name: str) -> Dict[str, Any]:
    rows, cols = read_csv_dicts(path)
    date_col = choose_col(cols, ["observation_date", "date_utc", "DATE", "Date"])
    value_col = choose_col(cols, [value_col_name, "value"])
    if not date_col or not value_col:
        return {"status": "FAIL", "error": f"FRED columns not found; columns={cols}", "rows": 0}
    out: Dict[str, float] = {}
    parse_fail = value_fail = 0
    for r in rows:
        d = parse_fred_date(r.get(date_col))
        v = to_float(r.get(value_col))
        if d is None:
            parse_fail += 1
            continue
        if v is None:
            value_fail += 1
            continue
        out[d.isoformat()] = v
    dates = sorted(out)
    return {
        "status": "PASS" if dates else "FAIL",
        "source_format": f"fred_csv_{source_name}",
        "path": str(path),
        "input_columns": cols,
        "date_col": date_col,
        "value_col": value_col,
        "rows_in": len(rows),
        "rows": len(dates),
        "parse_fail": parse_fail,
        "value_fail": value_fail,
        "min_date": dates[0] if dates else None,
        "max_date": dates[-1] if dates else None,
        "series": [{"date_utc": d, "value": out[d]} for d in dates],
    }


def xlsx_shared_strings(z: zipfile.ZipFile) -> List[str]:
    ss: List[str] = []
    if "xl/sharedStrings.xml" not in z.namelist():
        return ss
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    for si in root.findall(NS + "si"):
        ss.append("".join(t.text or "" for t in si.iter(NS + "t")))
    return ss


def xlsx_sheets(z: zipfile.ZipFile) -> List[Tuple[str, str]]:
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    rmap = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}
    sheets: List[Tuple[str, str]] = []
    for sh in wb.find(NS + "sheets"):
        name = sh.attrib["name"]
        rid = sh.attrib[REL_NS]
        target = rmap[rid]
        xmlpath = "xl/" + target if not target.startswith("/") else target[1:]
        sheets.append((name, xmlpath))
    return sheets


def col_index_from_ref(ref: str) -> int:
    m = re.match(r"([A-Z]+)", ref or "")
    if not m:
        return 0
    n = 0
    for ch in m.group(1):
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_xlsx_sheet_rows(path: Path, wanted_sheet: str) -> Tuple[List[List[str]], Dict[str, Any]]:
    with zipfile.ZipFile(path) as z:
        ss = xlsx_shared_strings(z)
        sheets = xlsx_sheets(z)
        found = None
        for name, xmlpath in sheets:
            if name == wanted_sheet:
                found = (name, xmlpath)
                break
        if not found:
            return [], {"status": "FAIL", "error": f"sheet not found: {wanted_sheet}", "sheets": [s[0] for s in sheets]}
        _, xmlpath = found
        root = ET.fromstring(z.read(xmlpath))
        out: List[List[str]] = []
        for row in root.iter(NS + "row"):
            vals: Dict[int, str] = {}
            for c in row.findall(NS + "c"):
                ci = col_index_from_ref(c.attrib.get("r", ""))
                typ = c.attrib.get("t")
                v = c.find(NS + "v")
                isel = c.find(NS + "is")
                val = ""
                if typ == "s" and v is not None:
                    try:
                        idx = int(v.text or "0")
                        val = ss[idx] if idx < len(ss) else ""
                    except Exception:
                        val = ""
                elif typ == "inlineStr" and isel is not None:
                    val = "".join(t.text or "" for t in isel.iter(NS + "t"))
                elif v is not None:
                    val = v.text or ""
                vals[ci] = val
            if vals:
                out.append([vals.get(i, "") for i in range(max(vals) + 1)])
        return out, {"status": "PASS", "sheet": wanted_sheet, "sheet_count": len(sheets), "sheets": [s[0] for s in sheets], "rows": len(out)}


def parse_wgc_etf_demand_monthly(path: Path) -> Dict[str, Any]:
    rows, info = read_xlsx_sheet_rows(path, "Demand by month")
    if not rows:
        return {"status": "FAIL", **info, "rows": 0}
    # Expected structure in user's file:
    # row 6 (0-based 5): Date, Gold US$/oz, Ounces, Tonnes, Value (USD), ...
    # rows after that: A=Excel serial month end, D=aggregate monthly tonnes delta.
    out: Dict[str, float] = {}
    parse_fail = value_fail = 0
    for r in rows[6:]:
        if not r or not str(r[0]).strip():
            continue
        if len(r) > 1 and str(r[1]).startswith("Column :"):
            continue
        d = excel_serial_to_date(r[0])
        v = to_float(r[3] if len(r) > 3 else None)
        if d is None:
            parse_fail += 1
            continue
        if v is None:
            value_fail += 1
            continue
        out[d.isoformat()] = v
    dates = sorted(out)
    return {
        "status": "PASS" if dates else "FAIL",
        "source_format": "wgc_etf_xlsx_demand_by_month_col_d_fund_total_assets_tonnes_delta",
        "path": str(path),
        "selected_sheet": "Demand by month",
        "date_column": "A/Date Excel serial",
        "value_column": "D/Tonnes",
        "rows_in_sheet": len(rows),
        "rows": len(dates),
        "parse_fail": parse_fail,
        "value_fail": value_fail,
        "min_date": dates[0] if dates else None,
        "max_date": dates[-1] if dates else None,
        "sheet_info": info,
        "series": [{"date_utc": d, "value": out[d]} for d in dates],
    }


def extract_wgc_central_bank_cross_section(path: Path, out_path: Path) -> Dict[str, Any]:
    rows, info = read_xlsx_sheet_rows(path, "PDF")
    if not rows:
        return {"status": "FAIL", **info}
    records: List[Dict[str, Any]] = []
    # User file has two side-by-side rank tables: B/C/E and G/H/J, with Excel serial dates.
    for r in rows:
        for offset in (0, 5):
            rank_i = offset + 0
            country_i = offset + 1
            tonnes_i = offset + 2
            asof_i = offset + 4
            if len(r) <= tonnes_i:
                continue
            rank = str(r[rank_i]).strip() if len(r) > rank_i else ""
            country = str(r[country_i]).strip() if len(r) > country_i else ""
            tonnes = to_float(r[tonnes_i] if len(r) > tonnes_i else None)
            asof = excel_serial_to_date(r[asof_i] if len(r) > asof_i else None)
            if not country or tonnes is None or not rank.isdigit():
                continue
            records.append({
                "rank": int(rank),
                "country_or_holder": country,
                "gold_holdings_tonnes": tonnes,
                "holdings_as_of": asof.isoformat() if asof else "",
            })
    records.sort(key=lambda x: x["rank"])
    ensure_dir(out_path.parent)
    write_rows(out_path, records, ["rank", "country_or_holder", "gold_holdings_tonnes", "holdings_as_of"])
    return {
        "status": "PASS_CROSS_SECTION_ONLY_NOT_DEMAND_TIMESERIES" if records else "FAIL",
        "source_format": "wgc_world_official_gold_holdings_cross_section",
        "path": str(path),
        "selected_sheet": "PDF",
        "rows": len(records),
        "output_path": str(out_path),
        "min_holdings_as_of": min([r["holdings_as_of"] for r in records if r["holdings_as_of"]], default=None),
        "max_holdings_as_of": max([r["holdings_as_of"] for r in records if r["holdings_as_of"]], default=None),
        "note": "This workbook is a latest cross-section, not a 3-month demand time series; central_bank_demand_tonnes_3m remains blank until a true time-series source is provided.",
        "sheet_info": info,
    }


def parse_amarkets_m5_to_d1(path: Path) -> Dict[str, Any]:
    rows, cols = read_csv_dicts(path)
    required = ["<DATE>", "<TIME>", "<OPEN>", "<HIGH>", "<LOW>", "<CLOSE>"]
    if not all(c in cols for c in required):
        return {"status": "FAIL", "error": f"AMarkets MT5 columns not found; columns={cols}", "rows": 0}
    daily: Dict[str, Dict[str, Any]] = {}
    parse_fail = 0
    for r in rows:
        dt = parse_mt5_date_time(r.get("<DATE>"), r.get("<TIME>"))
        if dt is None:
            parse_fail += 1
            continue
        dkey = dt.date().isoformat()
        o = to_float(r.get("<OPEN>")); h = to_float(r.get("<HIGH>")); l = to_float(r.get("<LOW>")); c = to_float(r.get("<CLOSE>")); sp = to_float(r.get("<SPREAD>"))
        if o is None or h is None or l is None or c is None:
            continue
        ent = daily.get(dkey)
        if ent is None:
            daily[dkey] = {"date_utc": dkey, "open": o, "high": h, "low": l, "close": c, "m5_rows": 1, "spread_values": [sp] if sp is not None else []}
        else:
            ent["high"] = max(float(ent["high"]), h)
            ent["low"] = min(float(ent["low"]), l)
            ent["close"] = c
            ent["m5_rows"] = int(ent["m5_rows"]) + 1
            if sp is not None:
                ent["spread_values"].append(sp)
    out = []
    for d in sorted(daily):
        ent = daily[d]
        svals = sorted(ent.pop("spread_values", []))
        ent["volume"] = ent.get("m5_rows", "")
        ent["source"] = "amarkets_mt5_m5_derived_d1"
        if svals:
            ent["spread_median"] = svals[len(svals)//2]
        out.append(ent)
    return {
        "status": "PASS" if out else "FAIL",
        "source_format": "amarkets_mt5_tab_delimited_m5",
        "path": str(path),
        "input_columns": cols,
        "rows_in": len(rows),
        "rows": len(out),
        "parse_fail": parse_fail,
        "min_date": out[0]["date_utc"] if out else None,
        "max_date": out[-1]["date_utc"] if out else None,
        "d1_rows": out,
    }


def read_existing_gold_d1(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows, cols = read_csv_dicts(path)
    out = []
    for r in rows:
        d = parse_iso_date(r.get("date_utc"))
        close = to_float(r.get("close"))
        if d is None or close is None:
            continue
        out.append({
            "date_utc": d.isoformat(),
            "open": to_float(r.get("open")) if to_float(r.get("open")) is not None else close,
            "high": to_float(r.get("high")) if to_float(r.get("high")) is not None else close,
            "low": to_float(r.get("low")) if to_float(r.get("low")) is not None else close,
            "close": close,
            "volume": r.get("volume", r.get("m5_rows", "")),
            "source": r.get("source", "existing_gold_d1"),
            "spread_median": r.get("spread_median", ""),
        })
    return out


def merge_write_gold_d1(root: Path, gold_path: Path, amarkets_parsed: Dict[str, Any]) -> Dict[str, Any]:
    existing = {r["date_utc"]: r for r in read_existing_gold_d1(gold_path)}
    incoming = {r["date_utc"]: r for r in amarkets_parsed.get("d1_rows", [])}
    merged = dict(existing)
    for d, r in incoming.items():
        # Prefer AMarkets-derived recent bars where available, but preserve earlier external history.
        merged[d] = r
    rows = [merged[d] for d in sorted(merged)]
    hash_before = sha256_file(gold_path)
    backup = None
    if gold_path.exists():
        bdir = root / "data/macro_regime/raw/_repair_backups"
        ensure_dir(bdir)
        backup = bdir / f"broker_or_spot_gold_d1_before_stage67d6_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.csv"
        shutil.copy2(gold_path, backup)
    write_rows(gold_path, rows, ["date_utc", "open", "high", "low", "close", "volume", "source", "spread_median"])
    return {
        "status": "PASS" if rows else "FAIL",
        "target": str(gold_path),
        "hash_before": hash_before,
        "hash_after": sha256_file(gold_path),
        "backup_path": str(backup) if backup else None,
        "existing_rows": len(existing),
        "incoming_rows": len(incoming),
        "after_rows": len(rows),
        "min_date": rows[0]["date_utc"] if rows else None,
        "max_date": rows[-1]["date_utc"] if rows else None,
    }


def load_series_map(path: Path) -> Dict[str, float]:
    if not path.exists():
        return {}
    rows, cols = read_csv_dicts(path)
    if "date_utc" not in cols or "value" not in cols:
        return {}
    out: Dict[str, float] = {}
    for r in rows:
        d = parse_iso_date(r.get("date_utc"))
        v = to_float(r.get("value"))
        if d and v is not None:
            out[d.isoformat()] = v
    return out


def ffill_on_calendar(dates: List[str], source: Dict[str, float]) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    last: Optional[float] = None
    for d in dates:
        if d in source:
            last = source[d]
        out.append(last)
    return out


def monthly_sum_last_days(dates: List[str], monthly: Dict[str, float], lookback_days: int = 93) -> List[Optional[float]]:
    items = sorted((parse_iso_date(k), v) for k, v in monthly.items() if parse_iso_date(k) is not None)
    clean = [(d, v) for d, v in items if d is not None and v is not None]
    out: List[Optional[float]] = []
    j = 0
    for ds in dates:
        d = parse_iso_date(ds)
        if d is None:
            out.append(None)
            continue
        lb = d - timedelta(days=lookback_days)
        vals = [v for md, v in clean if lb <= md <= d]
        out.append(sum(vals) if vals else None)
    return out


def rolling_mean(vals: List[Optional[float]], window: int, idx: int) -> Optional[float]:
    if idx + 1 < window:
        return None
    seg = vals[idx + 1 - window: idx + 1]
    if any(v is None for v in seg):
        return None
    return sum(v for v in seg if v is not None) / window


def lag(vals: List[Optional[float]], n: int, idx: int) -> Optional[float]:
    return vals[idx - n] if idx >= n else None


def ratio_minus_one(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return a / b - 1.0


def fmt(v: Optional[float]) -> str:
    if v is None or not math.isfinite(v):
        return ""
    return repr(float(v))


def rebuild_macro(root: Path, cfg: Dict[str, Any]) -> Dict[str, Any]:
    gold_path = root / cfg["gold_d1_path"]
    macro_path = root / cfg["macro_dataset_path"]
    gold_rows_raw = read_existing_gold_d1(gold_path)
    gold_rows = sorted(gold_rows_raw, key=lambda r: r["date_utc"])
    if not gold_rows:
        return {"status": "FAIL", "error": f"no valid gold D1 rows at {gold_path}"}
    dates = [r["date_utc"] for r in gold_rows]
    gold_close = [float(r["close"]) for r in gold_rows]
    exo_dir = root / "data/exogenous"
    dxy_map = load_series_map(exo_dir / "dxy.csv")
    real_map = load_series_map(exo_dir / "real_yield.csv")
    vix_map = load_series_map(exo_dir / "vix.csv")
    etf_map = load_series_map(exo_dir / "etf_flow.csv")

    dxy = ffill_on_calendar(dates, dxy_map)
    real = ffill_on_calendar(dates, real_map)
    vix = ffill_on_calendar(dates, vix_map)
    etf_monthly_3m = monthly_sum_last_days(dates, etf_map, 93)
    cb_3m = [None for _ in dates]

    out_rows: List[Dict[str, Any]] = []
    for i, base in enumerate(gold_rows):
        g20 = rolling_mean(gold_close, 20, i)
        g50 = rolling_mean(gold_close, 50, i)
        g200 = rolling_mean(gold_close, 200, i)
        dxy20 = rolling_mean(dxy, 20, i)
        dxy50 = rolling_mean(dxy, 50, i)
        dxy_l20 = lag(dxy, 20, i)
        real_l20 = lag(real, 20, i)
        vix_l20 = lag(vix, 20, i)
        out_rows.append({
            "feature_date_utc": base["date_utc"],
            "sample_available_after_utc": base["date_utc"] + "T23:59:59Z",
            "gold_close": fmt(gold_close[i]),
            "gold_sma20_over_50": fmt(ratio_minus_one(g20, g50)),
            "gold_sma50_over_200": fmt(ratio_minus_one(g50, g200)),
            "dxy_ret_20d": fmt(ratio_minus_one(dxy[i], dxy_l20)),
            "dxy_sma20_over_50": fmt(ratio_minus_one(dxy20, dxy50)),
            "real_yield_change_20d": fmt(None if real[i] is None or real_l20 is None else real[i] - real_l20),
            "vix_change_20d": fmt(None if vix[i] is None or vix_l20 is None else vix[i] - vix_l20),
            "etf_flow_tonnes_3m": fmt(etf_monthly_3m[i]),
            "central_bank_demand_tonnes_3m": fmt(cb_3m[i]),
            "date_utc": base["date_utc"],
            "open": fmt(to_float(base.get("open"))),
            "high": fmt(to_float(base.get("high"))),
            "low": fmt(to_float(base.get("low"))),
            "close": fmt(to_float(base.get("close"))),
            "volume": base.get("volume", ""),
            "source": base.get("source", "broker_or_spot_gold_d1"),
            "available_after_utc": base["date_utc"] + "T23:59:59Z",
            "spread_median": base.get("spread_median", ""),
            "gold_sma20": fmt(g20),
            "gold_sma50": fmt(g50),
            "gold_sma200": fmt(g200),
            "dxy": fmt(dxy[i]),
            "real_yield": fmt(real[i]),
            "vix": fmt(vix[i]),
            "etf_flow": fmt(etf_map.get(base["date_utc"])),
            "dxy_sma20": fmt(dxy20),
            "dxy_sma50": fmt(dxy50),
        })
    fieldnames = [
        "feature_date_utc", "sample_available_after_utc", "gold_close", "gold_sma20_over_50",
        "gold_sma50_over_200", "dxy_ret_20d", "dxy_sma20_over_50", "real_yield_change_20d",
        "vix_change_20d", "etf_flow_tonnes_3m", "central_bank_demand_tonnes_3m", "date_utc",
        "open", "high", "low", "close", "volume", "source", "available_after_utc", "spread_median",
        "gold_sma20", "gold_sma50", "gold_sma200", "dxy", "real_yield", "vix", "etf_flow", "dxy_sma20", "dxy_sma50",
    ]
    hash_before = sha256_file(macro_path)
    write_rows(macro_path, out_rows, fieldnames)
    hash_after = sha256_file(macro_path)

    def coverage(vals: List[Optional[float]]) -> Dict[str, Any]:
        n = sum(v is not None for v in vals)
        return {"coverage_rows": n, "coverage_pct": round(100.0 * n / len(vals), 3) if vals else 0.0}

    issues: List[str] = []
    today = datetime.now(timezone.utc).date()
    for key, smap in (("dxy", dxy_map), ("real_yield", real_map), ("vix", vix_map)):
        ds = [parse_iso_date(k) for k in smap]
        ds = [d for d in ds if d]
        if ds and max(ds) > today + timedelta(days=2):
            issues.append(f"{key.upper()}_FUTURE_DATE_PARSE_ERROR")
    guards = cfg.get("guards", {})
    if len(out_rows) < int(guards.get("macro_min_rows", 1000)):
        issues.append("MACRO_ROWS_TOO_SHORT")
    if coverage(dxy)["coverage_pct"] < float(guards.get("min_dxy_macro_coverage_pct", 90)):
        issues.append("DXY_MACRO_COVERAGE_TOO_LOW")
    if coverage(real)["coverage_pct"] < float(guards.get("min_real_yield_macro_coverage_pct", 90)):
        issues.append("REAL_YIELD_MACRO_COVERAGE_TOO_LOW")
    if coverage(vix)["coverage_pct"] < float(guards.get("min_vix_macro_coverage_pct", 90)):
        issues.append("VIX_MACRO_COVERAGE_TOO_LOW")
    return {
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "macro_path": str(macro_path),
        "rows": len(out_rows),
        "latest_after": out_rows[-1]["feature_date_utc"] if out_rows else None,
        "hash_before": hash_before,
        "hash_after": hash_after,
        "hash_changed": hash_before != hash_after,
        "coverage": {
            "dxy": coverage(dxy),
            "real_yield": coverage(real),
            "vix": coverage(vix),
            "etf_flow_tonnes_3m": coverage(etf_monthly_3m),
            "central_bank_demand_tonnes_3m": coverage(cb_3m),
        },
    }


def find_download(downloads: Path, candidates: List[str]) -> Optional[Path]:
    for c in candidates:
        p = downloads / c
        if p.exists():
            return p
    return None


def guard_parsed_series(key: str, parsed: Dict[str, Any], min_rows: int, max_future_days: int) -> List[str]:
    issues: List[str] = []
    if parsed.get("status") != "PASS":
        return [f"{key.upper()}_PARSE_FAIL"]
    if int(parsed.get("rows") or 0) < min_rows:
        issues.append(f"{key.upper()}_HISTORY_TOO_SHORT_FOR_ROLLING_FEATURES")
    mx = parse_iso_date(parsed.get("max_date"))
    today = datetime.now(timezone.utc).date()
    if mx and mx > today + timedelta(days=max_future_days):
        issues.append(f"{key.upper()}_FUTURE_DATE_PARSE_ERROR")
    return issues


def build_sources(root: Path, cfg: Dict[str, Any]) -> Dict[str, Any]:
    downloads = Path(os.path.expanduser(cfg["downloads_dir"]))
    exo_dir = root / "data/exogenous"
    raw_dir = exo_dir / "wgc_raw_extracted"
    ensure_dir(exo_dir)
    ensure_dir(raw_dir)
    backup_dir = exo_dir / "_repair_backups"
    ensure_dir(backup_dir)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    max_future_days = int(cfg.get("guards", {}).get("max_future_days_allowed", 2))
    result: Dict[str, Any] = {"download_dir": str(downloads), "formats": {}, "series": {}, "issues": []}

    sources = cfg["sources"]
    # DXY
    dxy_src = find_download(downloads, sources["dxy"]["incoming_candidates"])
    if dxy_src:
        parsed = parse_investing_dxy(dxy_src)
        issues = guard_parsed_series("dxy", parsed, int(sources["dxy"].get("min_rows", 1000)), max_future_days)
        result["formats"]["dxy"] = {k: v for k, v in parsed.items() if k != "series"}
        if issues:
            result["issues"].extend(issues)
            result["series"]["dxy"] = {"status": "GUARD_FAIL_NO_WRITE", "issues": issues, "source": str(dxy_src)}
        else:
            target = root / sources["dxy"]["target"]
            if target.exists():
                shutil.copy2(target, backup_dir / f"dxy_before_stage67d6_{ts}.csv")
            write_series(target, parsed["series"])
            result["series"]["dxy"] = {"status": "PASS_WRITTEN", "source": str(dxy_src), "target": str(target), **{k: v for k, v in parsed.items() if k != "series"}, "target_sha256": sha256_file(target)}
    else:
        result["issues"].append("DXY_INCOMING_MISSING")
        result["series"]["dxy"] = {"status": "MISSING_INCOMING"}

    # FRED real yield and VIX
    for key, value_col in (("real_yield", "DFII10"), ("vix", "VIXCLS")):
        src = find_download(downloads, sources[key]["incoming_candidates"])
        if src:
            parsed = parse_fred_series(src, value_col, value_col)
            issues = guard_parsed_series(key, parsed, int(sources[key].get("min_rows", 1000)), max_future_days)
            result["formats"][key] = {k: v for k, v in parsed.items() if k != "series"}
            if issues:
                result["issues"].extend(issues)
                result["series"][key] = {"status": "GUARD_FAIL_NO_WRITE", "issues": issues, "source": str(src)}
            else:
                target = root / sources[key]["target"]
                if target.exists():
                    shutil.copy2(target, backup_dir / f"{key}_before_stage67d6_{ts}.csv")
                write_series(target, parsed["series"])
                result["series"][key] = {"status": "PASS_WRITTEN", "source": str(src), "target": str(target), **{k: v for k, v in parsed.items() if k != "series"}, "target_sha256": sha256_file(target)}
        else:
            result["issues"].append(f"{key.upper()}_INCOMING_MISSING")
            result["series"][key] = {"status": "MISSING_INCOMING"}

    # ETF xlsx monthly demand/flows in tonnes
    etf_src = find_download(downloads, sources["etf_flow"]["incoming_candidates"])
    if etf_src:
        parsed = parse_wgc_etf_demand_monthly(etf_src)
        result["formats"]["etf_flow"] = {k: v for k, v in parsed.items() if k != "series"}
        if parsed.get("status") == "PASS":
            target = root / sources["etf_flow"]["target"]
            if target.exists():
                shutil.copy2(target, backup_dir / f"etf_flow_before_stage67d6_{ts}.csv")
            write_series(target, parsed["series"])
            result["series"]["etf_flow"] = {"status": "PASS_WRITTEN", "source": str(etf_src), "target": str(target), **{k: v for k, v in parsed.items() if k != "series"}, "target_sha256": sha256_file(target)}
        else:
            result["issues"].append("ETF_FLOW_XLSX_PARSE_FAIL")
            result["series"]["etf_flow"] = {"status": "FAIL", "source": str(etf_src), "parse_info": {k: v for k, v in parsed.items() if k != "series"}}
    else:
        result["issues"].append("ETF_FLOW_INCOMING_MISSING")
        result["series"]["etf_flow"] = {"status": "MISSING_INCOMING"}

    # Central bank cross-section only. Do not generate false 3m demand.
    cb_src = find_download(downloads, sources["central_bank_demand"]["incoming_candidates"])
    if cb_src:
        cb_out = raw_dir / "central_bank_gold_holdings_cross_section_latest.csv"
        cb = extract_wgc_central_bank_cross_section(cb_src, cb_out)
        result["formats"]["central_bank"] = cb
        result["series"]["central_bank_demand"] = {"status": "CROSS_SECTION_ONLY_NO_3M_DEMAND_SERIES", "source": str(cb_src), "cross_section_output": str(cb_out)}
        result["issues"].append("CENTRAL_BANK_SOURCE_IS_CROSS_SECTION_NOT_3M_DEMAND_TIMESERIES")
    else:
        result["series"]["central_bank_demand"] = {"status": "MISSING_INCOMING"}

    # Gold D1 merge from AMarkets M5
    gold_src = find_download(downloads, cfg["gold_m5_candidates"])
    if gold_src:
        parsed_gold = parse_amarkets_m5_to_d1(gold_src)
        result["formats"]["amarkets_gold_m5"] = {k: v for k, v in parsed_gold.items() if k != "d1_rows"}
        if parsed_gold.get("status") == "PASS":
            result["gold_import"] = merge_write_gold_d1(root, root / cfg["gold_d1_path"], parsed_gold)
        else:
            result["issues"].append("GOLD_M5_PARSE_FAIL")
            result["gold_import"] = parsed_gold
    else:
        result["issues"].append("GOLD_M5_INCOMING_MISSING")
        result["gold_import"] = {"status": "MISSING_INCOMING"}

    # Central bank issue is informational, not a hard source fail for rebuild.
    hard_issues = [x for x in result["issues"] if x != "CENTRAL_BANK_SOURCE_IS_CROSS_SECTION_NOT_3M_DEMAND_TIMESERIES"]
    result["status"] = "PASS" if not hard_issues else "FAIL"
    result["hard_issues"] = hard_issues
    return result


def run_readiness(root: Path, cfg: Dict[str, Any], timeout_seconds: int) -> Dict[str, Any]:
    rcfg = cfg.get("readiness", {})
    cmd = [
        sys.executable,
        str(root / rcfg.get("script", "app/stage66j2_multi_readiness_daily_ops.py")),
        "--root", str(root),
        "--config", str(root / rcfg.get("config", "configs/stage66j2_multi_readiness_daily_ops.json")),
        "--out", str(root / rcfg.get("out", "reports/stage66j2_multi_readiness_daily_ops")),
    ]
    try:
        cp = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True, timeout=timeout_seconds)
        return {"attempted": True, "cmd": cmd, "returncode": cp.returncode, "status": "PASS" if cp.returncode == 0 else "FAIL", "stdout_tail": cp.stdout[-2000:], "stderr_tail": cp.stderr[-2000:], "timeout_seconds": timeout_seconds}
    except subprocess.TimeoutExpired as e:
        return {"attempted": True, "cmd": cmd, "status": "TIMEOUT", "stdout_tail": (e.stdout or "")[-2000:] if isinstance(e.stdout, str) else "", "stderr_tail": (e.stderr or "")[-2000:] if isinstance(e.stderr, str) else "", "timeout_seconds": timeout_seconds}


def write_report(path: Path, summary: Dict[str, Any]) -> None:
    lines = [
        "# Stage67D6 Download-Format-Aware Rebuild Macro",
        "",
        "## Decision",
        "",
        f"- status: `{summary['status']}`",
        f"- decision: `{summary['decision']}`",
        f"- classification: `{summary['classification']}`",
        "",
        "## Issues",
        "",
    ]
    if summary.get("issues"):
        lines += [f"- `{x}`" for x in summary["issues"]]
    else:
        lines.append("- none")
    for title, key in (("Source refresh and format manifest", "source_refresh"), ("Macro rebuild", "macro_rebuild"), ("Readiness run", "readiness_run")):
        lines += ["", f"## {title}", "", "```json", json.dumps(summary.get(key, {}), indent=2, ensure_ascii=False), "```"]
    lines += ["", "## Hard blocks", ""]
    lines += [f"- `{x}`" for x in summary.get("hard_blocks", [])]
    ensure_dir(path.parent)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def append_ledger(root: Path, summary: Dict[str, Any]) -> None:
    ledger = root / "data/forward_shadow/stage67d6_download_format_aware_rebuild_macro_ledger.csv"
    ensure_dir(ledger.parent)
    exists = ledger.exists()
    with ledger.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["generated_utc", "status", "decision", "classification", "issues", "macro_latest", "readiness_status"])
        if not exists:
            w.writeheader()
        w.writerow({
            "generated_utc": summary.get("generated_utc"),
            "status": summary.get("status"),
            "decision": summary.get("decision"),
            "classification": summary.get("classification"),
            "issues": ";".join(summary.get("issues", [])),
            "macro_latest": summary.get("macro_rebuild", {}).get("latest_after"),
            "readiness_status": summary.get("readiness_run", {}).get("status"),
        })


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", default="configs/stage67d6_download_format_aware_rebuild_macro.json")
    ap.add_argument("--out", default="reports/stage67d6_download_format_aware_rebuild_macro")
    ap.add_argument("--run-readiness", action="store_true")
    ap.add_argument("--timeout-seconds", type=int, default=120)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    cfg_path = Path(args.config) if Path(args.config).is_absolute() else root / args.config
    cfg = read_json(cfg_path)
    out_dir = Path(args.out) if Path(args.out).is_absolute() else root / args.out
    ensure_dir(out_dir)

    summary: Dict[str, Any] = {
        "stage": cfg.get("stage", "Stage67D6_DOWNLOAD_FORMAT_AWARE_REBUILD_MACRO"),
        "root": str(root),
        "config": str(args.config),
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hard_blocks": cfg.get("hard_blocks", []),
        "issues": [],
    }
    source_refresh = build_sources(root, cfg)
    summary["source_refresh"] = source_refresh
    summary["issues"].extend(source_refresh.get("hard_issues", []))

    if source_refresh.get("status") == "PASS":
        macro = rebuild_macro(root, cfg)
    else:
        macro = {"status": "SKIPPED_DUE_SOURCE_REFRESH_HARD_ISSUES"}
    summary["macro_rebuild"] = macro
    if macro.get("status") != "PASS":
        summary["issues"].extend(macro.get("issues", []) or ["MACRO_REBUILD_FAILED_OR_SKIPPED"])

    if args.run_readiness and macro.get("status") == "PASS":
        readiness = run_readiness(root, cfg, args.timeout_seconds)
        summary["readiness_run"] = readiness
        if readiness.get("status") != "PASS":
            summary["issues"].append("STAGE66J2_TIMEOUT_OR_FAILURE")
    else:
        summary["readiness_run"] = {"attempted": False, "status": "SKIPPED" if not args.run_readiness else "SKIPPED_DUE_REBUILD_ISSUES"}

    # Do not hard-stop on central bank cross-section informational issue.
    if summary["issues"]:
        summary["status"] = "STAGE67D6_COMPLETE_WITH_ISSUES_NO_PROMOTION"
        summary["decision"] = "STAGE67D6_STOP_SOURCE_OR_REBUILD_OR_READINESS_ISSUE_NO_ORDER"
        summary["classification"] = "S67D6_STOP"
        code = 2
    else:
        summary["status"] = "STAGE67D6_COMPLETE_NO_PROMOTION"
        summary["decision"] = "STAGE67D6_REBUILD_COMPLETE_NO_ORDER" if not args.run_readiness else "STAGE67D6_REBUILD_AND_READINESS_COMPLETE_NO_ORDER"
        summary["classification"] = "S67D6_REBUILD_COMPLETE" if not args.run_readiness else "S67D6_REBUILD_READINESS_COMPLETE"
        code = 0

    summary["operator_notes"] = [
        "ETF xlsx is mapped from 'Demand by month' column D / Tonnes as monthly fund_total_assets_tonnes_delta.",
        "Central-bank WGC workbook is a latest holdings cross-section, not a 3-month demand time series; it is extracted separately and not used to fabricate central_bank_demand_tonnes_3m.",
        "No order, broker, EA, paper-live, or live path is authorized.",
    ]
    summary["outputs"] = {
        "summary_json": str(out_dir / "stage67d6_download_format_aware_rebuild_macro_summary.json"),
        "report_md": str(out_dir / "stage67d6_download_format_aware_rebuild_macro_report.md"),
        "ledger_csv": "data/forward_shadow/stage67d6_download_format_aware_rebuild_macro_ledger.csv",
    }
    (out_dir / "stage67d6_download_format_aware_rebuild_macro_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_report(out_dir / "stage67d6_download_format_aware_rebuild_macro_report.md", summary)
    append_ledger(root, summary)
    print(json.dumps({"stage": summary["stage"], "status": summary["status"], "decision": summary["decision"], "classification": summary["classification"], "issues": summary.get("issues", []), "summary_json": summary["outputs"]["summary_json"], "report_md": summary["outputs"]["report_md"]}, indent=2, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
