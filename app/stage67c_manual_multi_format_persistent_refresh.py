#!/usr/bin/env python3
"""Stage67C manual multi-format persistent data refresh + Stage66J2 runner.

Local only. No internet download. No order/broker/EA/live authorization.
Supports:
- MT5/AMarkets CSV with <DATE>, <TIME>, <OPEN>, ... headers
- Investing DXY CSV
- FRED DFII10 / VIXCLS CSV
- WGC XLSX raw extraction and best-effort canonical extraction with anti-truncation
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
import xml.etree.ElementTree as ET

try:
    import pandas as pd
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"pandas is required by Stage67C: {exc}")

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE67C",
    "NO_INTERNET_DOWNLOAD_FROM_STAGE67C",
    "NO_THRESHOLD_TUNING",
    "NO_PROMOTION_FROM_DATA_REFRESH_ONLY",
]


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_path(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")


def normalize_col(c: Any) -> str:
    s = str(c).strip()
    s = s.strip("\ufeff")
    s = s.strip()
    s = re.sub(r"[<>]", "", s)
    s = re.sub(r"\s+", "_", s)
    s = s.lower()
    return s


def parse_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    s = str(x).strip()
    if not s or s in {".", "-", "--", "nan", "NaN", "N/A"}:
        return None
    s = s.replace(",", "")
    s = s.replace("%", "")
    s = re.sub(r"[^0-9eE+\-.]", "", s)
    if not s or s in {".", "-", "+"}:
        return None
    try:
        return float(s)
    except Exception:
        return None


def parse_date_any(x: Any) -> Optional[pd.Timestamp]:
    if x is None:
        return None
    if isinstance(x, (dt.date, dt.datetime)):
        return pd.to_datetime(x).tz_localize(None)
    s = str(x).strip()
    if not s or s.lower() in {"nan", "none"}:
        return None
    # Excel serial dates sometimes arrive as numbers.
    num = parse_float(s)
    if num is not None and 20000 < num < 60000 and re.fullmatch(r"\d+(\.0+)?", s):
        try:
            return (pd.Timestamp("1899-12-30") + pd.to_timedelta(int(num), unit="D")).tz_localize(None)
        except Exception:
            pass
    for dayfirst in (False, True):
        try:
            ts = pd.to_datetime(s, errors="raise", dayfirst=dayfirst)
            if pd.isna(ts):
                return None
            return pd.Timestamp(ts).tz_localize(None) if getattr(ts, "tzinfo", None) else pd.Timestamp(ts)
        except Exception:
            continue
    return None


def find_source(download_dir: Path, candidates: List[str]) -> Optional[Path]:
    for name in candidates:
        p = download_dir / name
        if p.exists():
            return p
    for pattern in candidates:
        if any(ch in pattern for ch in "*?[]"):
            matches = sorted(download_dir.glob(pattern), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
            if matches:
                return matches[0]
    return None


def read_csv_loose(path: Path) -> pd.DataFrame:
    # Try common separators and encodings.
    last_exc: Optional[Exception] = None
    for enc in ("utf-8-sig", "utf-16", "latin1"):
        for sep in (None, ",", "\t", ";"):
            try:
                kwargs = {"encoding": enc, "engine": "python"}
                if sep is not None:
                    kwargs["sep"] = sep
                df = pd.read_csv(path, **kwargs)
                if len(df.columns) >= 2:
                    df.columns = [str(c).strip() for c in df.columns]
                    return df
            except Exception as exc:
                last_exc = exc
    raise ValueError(f"cannot read CSV {path}: {last_exc}")


def canonicalize_mt5_gold_m5(path: Path) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    df = read_csv_loose(path)
    original_cols = list(df.columns)
    cols = {normalize_col(c): c for c in df.columns}
    required = ["date", "time", "open", "high", "low", "close"]
    missing = [c for c in required if c not in cols]
    if missing:
        raise ValueError(f"MT5 OHLC columns missing {missing}; columns={original_cols}")
    date_s = df[cols["date"]].astype(str).str.strip()
    time_s = df[cols["time"]].astype(str).str.strip()
    ts = pd.to_datetime(date_s + " " + time_s, errors="coerce", utc=True)
    out = pd.DataFrame({
        "utc_time": ts.dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "open": pd.to_numeric(df[cols["open"]].map(parse_float), errors="coerce"),
        "high": pd.to_numeric(df[cols["high"]].map(parse_float), errors="coerce"),
        "low": pd.to_numeric(df[cols["low"]].map(parse_float), errors="coerce"),
        "close": pd.to_numeric(df[cols["close"]].map(parse_float), errors="coerce"),
    })
    if "spread" in cols:
        out["spread"] = pd.to_numeric(df[cols["spread"]].map(parse_float), errors="coerce")
    out = out.dropna(subset=["utc_time", "open", "high", "low", "close"]).drop_duplicates("utc_time").sort_values("utc_time")
    if out.empty:
        raise ValueError("MT5 gold file parsed to zero valid rows")
    return out, {"input_columns": original_cols, "rows": int(len(out)), "min_utc": out["utc_time"].iloc[0], "max_utc": out["utc_time"].iloc[-1]}


def m5_to_d1(m5: pd.DataFrame) -> pd.DataFrame:
    z = m5.copy()
    z["dt"] = pd.to_datetime(z["utc_time"], utc=True, errors="coerce")
    z = z.dropna(subset=["dt"]).sort_values("dt")
    z["date_utc"] = z["dt"].dt.strftime("%Y-%m-%d")
    g = z.groupby("date_utc", sort=True)
    d1 = pd.DataFrame({
        "date_utc": g["date_utc"].first().index,
        "open": g["open"].first().values,
        "high": g["high"].max().values,
        "low": g["low"].min().values,
        "close": g["close"].last().values,
    })
    if "spread" in z.columns:
        d1["spread_median"] = g["spread"].median().values
    return d1.dropna(subset=["open", "high", "low", "close"]).sort_values("date_utc")


def canonicalize_market_csv(path: Path, series_name: str) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    df = read_csv_loose(path)
    original_cols = list(df.columns)
    norm = {normalize_col(c): c for c in df.columns}
    date_col = None
    for cand in ["date", "observation_date", "time", "datetime"]:
        if cand in norm:
            date_col = norm[cand]
            break
    if date_col is None:
        # fallback: first column with enough date-like values
        best = None
        best_count = 0
        for c in df.columns:
            cnt = sum(parse_date_any(v) is not None for v in df[c].head(100).tolist())
            if cnt > best_count:
                best, best_count = c, cnt
        if best_count > 5:
            date_col = best
    if date_col is None:
        raise ValueError(f"date column not found for {series_name}; columns={original_cols}")
    value_col = None
    if series_name == "dxy":
        for cand in ["price", "close", "last", "value"]:
            if cand in norm:
                value_col = norm[cand]
                break
    elif series_name == "real_yield":
        for cand in ["dfii10", "value", "price", "close"]:
            if cand in norm:
                value_col = norm[cand]
                break
    elif series_name == "vix":
        for cand in ["vixcls", "value", "price", "close"]:
            if cand in norm:
                value_col = norm[cand]
                break
    if value_col is None:
        # fallback: first numeric-like non-date column
        best = None
        best_count = 0
        for c in df.columns:
            if c == date_col:
                continue
            cnt = sum(parse_float(v) is not None for v in df[c].head(200).tolist())
            if cnt > best_count:
                best, best_count = c, cnt
        if best_count > 5:
            value_col = best
    if value_col is None:
        raise ValueError(f"value column not found for {series_name}; columns={original_cols}")
    out = pd.DataFrame({
        "date_utc": [parse_date_any(v) for v in df[date_col]],
        series_name: [parse_float(v) for v in df[value_col]],
    })
    out = out.dropna(subset=["date_utc", series_name])
    out["date_utc"] = pd.to_datetime(out["date_utc"]).dt.strftime("%Y-%m-%d")
    out = out.drop_duplicates("date_utc", keep="last").sort_values("date_utc")
    return out, {"input_columns": original_cols, "date_col": str(date_col), "value_col": str(value_col), "rows": int(len(out)), "min_date": out["date_utc"].min() if not out.empty else None, "max_date": out["date_utc"].max() if not out.empty else None}


def xlsx_shared_strings(zf: zipfile.ZipFile) -> List[str]:
    try:
        xml = zf.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(xml)
    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    strings: List[str] = []
    for si in root.findall("a:si", ns):
        texts = [t.text or "" for t in si.findall(".//a:t", ns)]
        strings.append("".join(texts))
    return strings


def xlsx_sheet_names(zf: zipfile.ZipFile) -> List[Tuple[str, str]]:
    ns = {
        "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    }
    wb = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rel_map = {r.attrib.get("Id"): r.attrib.get("Target") for r in rels}
    out = []
    for sh in wb.findall(".//a:sheet", ns):
        name = sh.attrib.get("name", "Sheet")
        rid = sh.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        target = rel_map.get(rid, "")
        if target and not target.startswith("xl/"):
            target = "xl/" + target.lstrip("/")
        out.append((name, target))
    return out


def cell_col_index(ref: str) -> int:
    letters = re.sub(r"[^A-Z]", "", ref.upper())
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n - 1


def read_xlsx_rows(path: Path) -> Dict[str, List[List[Any]]]:
    sheets: Dict[str, List[List[Any]]] = {}
    with zipfile.ZipFile(path) as zf:
        shared = xlsx_shared_strings(zf)
        ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        for name, target in xlsx_sheet_names(zf):
            if not target or target not in zf.namelist():
                continue
            root = ET.fromstring(zf.read(target))
            rows: List[List[Any]] = []
            for row in root.findall(".//a:sheetData/a:row", ns):
                vals: List[Any] = []
                for c in row.findall("a:c", ns):
                    ref = c.attrib.get("r", "A1")
                    idx = cell_col_index(ref)
                    while len(vals) <= idx:
                        vals.append(None)
                    typ = c.attrib.get("t")
                    v = c.find("a:v", ns)
                    is_node = c.find("a:is", ns)
                    val: Any = None
                    if typ == "s" and v is not None:
                        try:
                            val = shared[int(v.text or "0")]
                        except Exception:
                            val = v.text
                    elif typ == "inlineStr" and is_node is not None:
                        texts = [t.text or "" for t in is_node.findall(".//a:t", ns)]
                        val = "".join(texts)
                    elif v is not None:
                        val = v.text
                    vals[idx] = val
                rows.append(vals)
            sheets[name] = rows
    return sheets


def rows_to_raw_csvs(path: Path, raw_dir: Path) -> Dict[str, Any]:
    ensure_parent(raw_dir / "dummy")
    sheets = read_xlsx_rows(path)
    exported = []
    for name, rows in sheets.items():
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_") or "sheet"
        out = raw_dir / f"{path.stem}__{safe}.csv"
        with out.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerows(rows)
        exported.append(str(out))
    return {"sheet_count": len(sheets), "raw_csvs": exported}


def canonicalize_wgc_xlsx(path: Path, series_name: str, raw_dir: Path) -> Tuple[Optional[pd.DataFrame], Dict[str, Any]]:
    info = rows_to_raw_csvs(path, raw_dir)
    sheets = read_xlsx_rows(path)
    keyword_sets = {
        "etf_flow": ["flow", "tonne"],
        "central_bank_demand": ["change", "tonne"],
    }
    value_keywords = keyword_sets.get(series_name, [])
    candidates: List[Tuple[int, str, int, int, List[Any], pd.DataFrame]] = []
    for sheet_name, rows in sheets.items():
        for i, row in enumerate(rows[:60]):
            header = [str(x).strip() if x is not None else "" for x in row]
            lower = [h.lower() for h in header]
            date_cols = [j for j, h in enumerate(lower) if any(k in h for k in ["date", "month", "quarter", "period"])]
            value_cols = []
            for j, h in enumerate(lower):
                if j in date_cols:
                    continue
                if value_keywords and all(k in h for k in value_keywords):
                    value_cols.append(j)
                elif "tonne" in h and ("flow" in h or "change" in h or "net" in h):
                    value_cols.append(j)
            if not date_cols or not value_cols:
                continue
            for dc in date_cols:
                for vc in value_cols:
                    records = []
                    for r in rows[i+1:]:
                        dv = r[dc] if dc < len(r) else None
                        vv = r[vc] if vc < len(r) else None
                        d = parse_date_any(dv)
                        val = parse_float(vv)
                        if d is not None and val is not None:
                            records.append((pd.Timestamp(d).strftime("%Y-%m-%d"), val))
                    if len(records) >= 3:
                        df = pd.DataFrame(records, columns=["date_utc", series_name]).drop_duplicates("date_utc", keep="last").sort_values("date_utc")
                        score = len(records)
                        candidates.append((score, sheet_name, dc, vc, header, df))
    if not candidates:
        info.update({"canonical_status": "RAW_ONLY_MAPPING_UNRESOLVED", "series_name": series_name})
        return None, info
    candidates.sort(key=lambda x: x[0], reverse=True)
    score, sheet_name, dc, vc, header, df = candidates[0]
    info.update({
        "canonical_status": "PASS_BEST_EFFORT",
        "series_name": series_name,
        "selected_sheet": sheet_name,
        "date_header": header[dc] if dc < len(header) else None,
        "value_header": header[vc] if vc < len(header) else None,
        "rows": int(len(df)),
        "min_date": df["date_utc"].min() if not df.empty else None,
        "max_date": df["date_utc"].max() if not df.empty else None,
    })
    return df, info


def load_existing_csv(path: Path) -> pd.DataFrame:
    if path.exists():
        return read_csv_loose(path)
    return pd.DataFrame()


def merge_on_key(existing: pd.DataFrame, incoming: pd.DataFrame, key: str = "date_utc") -> Tuple[pd.DataFrame, Dict[str, Any]]:
    before_rows = int(len(existing)) if not existing.empty else 0
    before_latest = None
    if before_rows and key in existing.columns:
        before_latest = str(pd.to_datetime(existing[key], errors="coerce").max().date())
    if incoming is None or incoming.empty:
        return existing, {"incoming_rows": 0, "before_rows": before_rows, "after_rows": before_rows, "new_rows": 0, "latest_advanced": False, "before_latest": before_latest, "after_latest": before_latest, "hash_changed": False}
    if existing.empty:
        combined = incoming.copy()
    else:
        combined = pd.concat([existing, incoming], ignore_index=True, sort=False)
    combined[key] = pd.to_datetime(combined[key], errors="coerce").dt.strftime("%Y-%m-%d")
    combined = combined.dropna(subset=[key]).drop_duplicates(subset=[key], keep="last").sort_values(key)
    after_rows = int(len(combined))
    after_latest = str(pd.to_datetime(combined[key], errors="coerce").max().date()) if after_rows else None
    new_rows = max(0, after_rows - before_rows)
    return combined, {"incoming_rows": int(len(incoming)), "before_rows": before_rows, "after_rows": after_rows, "new_rows": new_rows, "latest_advanced": bool(before_latest is None or (after_latest and after_latest > before_latest)), "before_latest": before_latest, "after_latest": after_latest}


def save_csv(df: pd.DataFrame, path: Path) -> None:
    ensure_parent(path)
    df.to_csv(path, index=False)


def refresh_gold(root: Path, source: Optional[Path], gold_d1_path: Path) -> Dict[str, Any]:
    result = {"source": str(source) if source else None, "status": "SKIP_NO_SOURCE"}
    if source is None:
        return result
    before_hash = sha256_path(gold_d1_path)
    try:
        m5, parse_info = canonicalize_mt5_gold_m5(source)
        d1_in = m5_to_d1(m5)
        existing = load_existing_csv(gold_d1_path)
        combined, merge_info = merge_on_key(existing, d1_in, "date_utc")
        after_hash_pre = hashlib.sha256(combined.to_csv(index=False).encode()).hexdigest()
        if before_hash != after_hash_pre:
            save_csv(combined, gold_d1_path)
        after_hash = sha256_path(gold_d1_path)
        result.update({"status": "PASS", "parse_info": parse_info, "merge_info": merge_info, "hash_before": before_hash, "hash_after": after_hash, "hash_changed": before_hash != after_hash})
    except Exception as exc:
        result.update({"status": "FAIL", "error": str(exc)})
    return result


def refresh_exogenous(root: Path, download_dir: Path, config: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    exog_dir = root / config["paths"]["exogenous_dir"]
    raw_dir = exog_dir / "wgc_raw_extracted"
    results: Dict[str, Any] = {}
    any_new = False
    for series in ["dxy", "real_yield", "vix", "etf_flow", "central_bank_demand"]:
        source = find_source(download_dir, config["sources"].get(series, []))
        target = exog_dir / f"{series}.csv"
        before_hash = sha256_path(target)
        res: Dict[str, Any] = {"source": str(source) if source else None, "target": str(target), "status": "SKIP_NO_SOURCE", "hash_before": before_hash}
        if source is None:
            res["exists_existing"] = target.exists()
            res["hash_after"] = before_hash
            results[series] = res
            continue
        try:
            if source.suffix.lower() == ".xlsx":
                incoming, info = canonicalize_wgc_xlsx(source, series, raw_dir)
                res["xlsx_info"] = info
                if incoming is None:
                    res["status"] = "RAW_ONLY_MAPPING_UNRESOLVED_EXISTING_PRESERVED"
                    res["hash_after"] = before_hash
                    results[series] = res
                    continue
            else:
                incoming, info = canonicalize_market_csv(source, series)
                res["parse_info"] = info
            existing = load_existing_csv(target)
            combined, merge_info = merge_on_key(existing, incoming, "date_utc")
            candidate_hash = hashlib.sha256(combined.to_csv(index=False).encode()).hexdigest()
            if before_hash != candidate_hash:
                save_csv(combined, target)
            after_hash = sha256_path(target)
            res.update({"status": "PASS", "merge_info": merge_info, "hash_after": after_hash, "hash_changed": before_hash != after_hash})
            any_new = any_new or bool(merge_info.get("latest_advanced") or merge_info.get("new_rows", 0) > 0 or before_hash != after_hash)
        except Exception as exc:
            res.update({"status": "FAIL", "error": str(exc), "hash_after": sha256_path(target)})
        results[series] = res
    return results, any_new


def build_macro_dataset(root: Path, config: Dict[str, Any]) -> Dict[str, Any]:
    macro_path = root / config["paths"]["macro_dataset"]
    gold_path = root / config["paths"]["gold_d1"]
    before_hash = sha256_path(macro_path)
    result: Dict[str, Any] = {"macro_path": str(macro_path), "hash_before": before_hash}
    if not gold_path.exists():
        result.update({"status": "FAIL", "error": f"gold D1 not found: {gold_path}"})
        return result
    gold = read_csv_loose(gold_path)
    if "date_utc" not in gold.columns or "close" not in gold.columns:
        result.update({"status": "FAIL", "error": "gold D1 requires date_utc and close"})
        return result
    df = gold.copy()
    df["feature_date_utc"] = pd.to_datetime(df["date_utc"], errors="coerce").dt.strftime("%Y-%m-%d")
    df = df.dropna(subset=["feature_date_utc"]).sort_values("feature_date_utc")
    df["gold_close"] = pd.to_numeric(df["close"], errors="coerce")
    df["gold_sma20"] = df["gold_close"].rolling(20, min_periods=20).mean()
    df["gold_sma50"] = df["gold_close"].rolling(50, min_periods=50).mean()
    df["gold_sma200"] = df["gold_close"].rolling(200, min_periods=200).mean()
    df["gold_sma20_over_50"] = df["gold_sma20"] / df["gold_sma50"] - 1.0
    df["gold_sma50_over_200"] = df["gold_sma50"] / df["gold_sma200"] - 1.0
    series_info: Dict[str, Any] = {}
    exog_dir = root / config["paths"]["exogenous_dir"]
    for series in ["dxy", "real_yield", "vix", "etf_flow", "central_bank_demand"]:
        p = exog_dir / f"{series}.csv"
        if not p.exists():
            series_info[series] = {"exists": False, "path": str(p), "coverage_rows": 0, "coverage_pct": 0.0}
            continue
        s = read_csv_loose(p)
        if "date_utc" not in s.columns or series not in s.columns:
            series_info[series] = {"exists": True, "path": str(p), "error": "missing date_utc or value column", "coverage_rows": 0, "coverage_pct": 0.0}
            continue
        s = s[["date_utc", series]].copy()
        s["date_utc"] = pd.to_datetime(s["date_utc"], errors="coerce").dt.strftime("%Y-%m-%d")
        s[series] = pd.to_numeric(s[series], errors="coerce")
        s = s.dropna(subset=["date_utc"]).drop_duplicates("date_utc", keep="last").sort_values("date_utc")
        df = df.merge(s, how="left", left_on="feature_date_utc", right_on="date_utc", suffixes=("", f"_{series}"))
        if f"date_utc_{series}" in df.columns:
            df = df.drop(columns=[f"date_utc_{series}"])
        df[series] = df[series].ffill()
        cov = int(df[series].notna().sum())
        series_info[series] = {"exists": True, "path": str(p), "coverage_rows": cov, "coverage_pct": round(cov / max(1, len(df)) * 100, 3), "latest_source_date": s["date_utc"].max() if not s.empty else None}
    if "dxy" in df.columns:
        df["dxy_ret_20d"] = df["dxy"] / df["dxy"].shift(20) - 1.0
        df["dxy_sma20"] = df["dxy"].rolling(20, min_periods=20).mean()
        df["dxy_sma50"] = df["dxy"].rolling(50, min_periods=50).mean()
        df["dxy_sma20_over_50"] = df["dxy_sma20"] / df["dxy_sma50"] - 1.0
    if "real_yield" in df.columns:
        df["real_yield_change_20d"] = df["real_yield"] - df["real_yield"].shift(20)
    if "vix" in df.columns:
        df["vix_change_20d"] = df["vix"] - df["vix"].shift(20)
    if "etf_flow" in df.columns:
        df["etf_flow_tonnes_3m"] = df["etf_flow"].rolling(63, min_periods=1).sum()
    if "central_bank_demand" in df.columns:
        df["central_bank_demand_tonnes_3m"] = df["central_bank_demand"].rolling(63, min_periods=1).sum()
    df["sample_available_after_utc"] = (pd.to_datetime(df["feature_date_utc"]) + pd.Timedelta(days=1)).dt.strftime("%Y-%m-%dT00:00:00Z")
    # Preserve expected primary columns first.
    cols = ["feature_date_utc", "sample_available_after_utc", "gold_close", "gold_sma20_over_50", "gold_sma50_over_200", "dxy_ret_20d", "dxy_sma20_over_50", "real_yield_change_20d", "vix_change_20d", "etf_flow_tonnes_3m", "central_bank_demand_tonnes_3m"]
    ordered = [c for c in cols if c in df.columns] + [c for c in df.columns if c not in cols]
    df = df[ordered]
    ensure_parent(macro_path)
    df.to_csv(macro_path, index=False)
    after_hash = sha256_path(macro_path)
    result.update({
        "status": "PASS",
        "hash_after": after_hash,
        "hash_changed": before_hash != after_hash,
        "rows": int(len(df)),
        "latest_after": df["feature_date_utc"].max() if not df.empty else None,
        "series_info": series_info,
    })
    return result


def run_stage66j2(root: Path, config: Dict[str, Any], out_root: Path) -> Dict[str, Any]:
    py = sys.executable
    script = root / "app/stage66j2_multi_readiness_daily_ops.py"
    cfg = root / config["paths"]["stage66j2_config"]
    out = root / config["paths"]["stage66j2_out"]
    cmd = [py, str(script), "--root", str(root), "--config", str(cfg), "--out", str(out)]
    res = subprocess.run(cmd, cwd=str(root), text=True, capture_output=True)
    summary_path = out / "stage66j2_multi_readiness_daily_ops_summary.json"
    summary = read_json(summary_path) if summary_path.exists() else {}
    return {
        "attempted": True,
        "cmd": cmd,
        "returncode": res.returncode,
        "status": "PASS" if res.returncode == 0 and summary_path.exists() else "FAIL",
        "stdout_tail": res.stdout[-2000:],
        "stderr_tail": res.stderr[-2000:],
        "summary_found": summary_path.exists(),
        "summary_path": str(summary_path.relative_to(root)) if summary_path.exists() else str(summary_path),
        "summary_decision": summary.get("decision"),
        "summary_classification": summary.get("classification"),
        "summary_sha256": sha256_path(summary_path),
    }


def write_report(path: Path, summary: Dict[str, Any]) -> None:
    ensure_parent(path)
    dr = summary.get("data_refresh", {})
    lines = [
        "# Stage67C Manual Multi-Format Persistent Refresh + Multi-Readiness Runner",
        "",
        "## Decision",
        "",
        f"- status: `{summary.get('status')}`",
        f"- decision: `{summary.get('decision')}`",
        f"- classification: `{summary.get('classification')}`",
        "",
        "## Data refresh summary",
        "",
        "```json",
        json.dumps(dr, indent=2, sort_keys=True),
        "```",
        "",
        "## Readiness runner",
        "",
        "```json",
        json.dumps(summary.get("readiness_run"), indent=2, sort_keys=True),
        "```",
        "",
        "## Issues",
        "",
    ]
    issues = summary.get("issues") or []
    if issues:
        lines.extend([f"- `{x}`" for x in issues])
    else:
        lines.append("- none")
    lines.extend(["", "## Hard blocks", ""])
    lines.extend([f"- `{x}`" for x in HARD_BLOCKS])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--force-readiness", action="store_true")
    args = ap.parse_args()
    root = Path(args.root).expanduser().resolve()
    cfg_path = Path(args.config)
    if not cfg_path.is_absolute():
        cfg_path = root / cfg_path
    config = read_json(cfg_path)
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    download_dir = Path(config.get("download_dir", "~/Downloads")).expanduser()
    if not download_dir.is_absolute():
        download_dir = (root / download_dir).resolve()

    gold_source = find_source(download_dir, config["sources"].get("gold_m5", []))
    gold_result = refresh_gold(root, gold_source, root / config["paths"]["gold_d1"])
    exog_results, exog_any_new = refresh_exogenous(root, download_dir, config)
    macro_result = build_macro_dataset(root, config)

    issues: List[str] = []
    if gold_result.get("status") == "FAIL":
        issues.append("GOLD_IMPORT_FAILED")
    for name, res in exog_results.items():
        if res.get("status") == "FAIL":
            issues.append(f"{name.upper()}_IMPORT_FAILED")
        if "RAW_ONLY" in str(res.get("status")):
            issues.append(f"{name.upper()}_XLSX_RAW_ONLY_MAPPING_UNRESOLVED")
    if macro_result.get("status") != "PASS":
        issues.append("MACRO_BUILD_FAILED")

    imported_new_data = bool(
        gold_result.get("hash_changed")
        or exog_any_new
        or macro_result.get("hash_changed")
    )

    readiness_run: Dict[str, Any] = {"attempted": False, "status": "SKIP"}
    if macro_result.get("status") == "PASS" and (imported_new_data or args.force_readiness):
        readiness_run = run_stage66j2(root, config, out_dir)
        if readiness_run.get("status") != "PASS":
            issues.append("STAGE66J2_RUN_FAILED")

    if macro_result.get("status") != "PASS" or "GOLD_IMPORT_FAILED" in issues or any(x.endswith("_IMPORT_FAILED") for x in issues if x != "GOLD_IMPORT_FAILED"):
        decision = "STAGE67C_STOP_INPUT_OR_REFRESH_FAILURE_NO_ORDER"
        classification = "S67C_STOP"
        status = "STAGE67C_COMPLETE_WITH_ISSUES_NO_PROMOTION"
    elif not imported_new_data and not args.force_readiness:
        decision = "STAGE67C_NO_NEW_MANUAL_DATA_IMPORTED_NO_FORWARD_READINESS_RUN"
        classification = "S67C_NO_NEW_DATA"
        status = "STAGE67C_COMPLETE_NO_PROMOTION"
    else:
        j2_decision = readiness_run.get("summary_decision")
        if j2_decision == "STAGE66J2_ALL_READINESS_WAIT_SIGNALS_NO_ORDER":
            decision = "STAGE67C_REFRESH_COMPLETE_STAGE66J2_ALL_READINESS_WAIT_SIGNALS_NO_ORDER"
            classification = "S67C_REFRESH_WAIT_ALL_INACTIVE"
        elif j2_decision == "STAGE66J2_BACKUP_SIGNAL_ACTIVE_REQUIRES_STAGE66L_NO_ORDER":
            decision = "STAGE67C_REFRESH_COMPLETE_STAGE66J2_BACKUP_SIGNAL_ACTIVE_REQUIRES_STAGE66L_NO_ORDER"
            classification = "S67C_REFRESH_BACKUP_ACTIVE"
        else:
            decision = f"STAGE67C_REFRESH_COMPLETE_{j2_decision or 'STAGE66J2_UNKNOWN'}"
            classification = "S67C_REFRESH_REVIEW"
        status = "STAGE67C_COMPLETE_NO_PROMOTION" if not issues else "STAGE67C_COMPLETE_WITH_ISSUES_NO_PROMOTION"

    summary = {
        "stage": "Stage67C_MANUAL_MULTI_FORMAT_PERSISTENT_REFRESH",
        "status": status,
        "decision": decision,
        "classification": classification,
        "generated_utc": now_utc(),
        "root": str(root),
        "config": str(cfg_path.relative_to(root)) if str(cfg_path).startswith(str(root)) else str(cfg_path),
        "data_refresh": {
            "download_dir": str(download_dir),
            "gold_import": gold_result,
            "exogenous_import": exog_results,
            "macro_build": macro_result,
            "imported_new_data": imported_new_data,
            "xlsx_supported": True,
            "persistent_merge_policy": "append_or_upsert_by_date_never_truncate_existing_history",
        },
        "readiness_run": readiness_run,
        "issues": issues,
        "hard_blocks": HARD_BLOCKS,
        "outputs": {
            "summary_json": str((out_dir / "stage67c_manual_multi_format_persistent_refresh_summary.json").relative_to(root)),
            "report_md": str((out_dir / "stage67c_manual_multi_format_persistent_refresh_report.md").relative_to(root)),
            "ledger_csv": "data/forward_shadow/stage67c_manual_multi_format_persistent_refresh_ledger.csv",
        },
        "next_step": "If refreshed and Stage66J2 says WAIT, continue manual refresh cadence. If any signal/ticket appears, review only and build the next explicit no-broker authorization/dry-run package. No order is authorized by Stage67C.",
    }
    summary_path = out_dir / "stage67c_manual_multi_format_persistent_refresh_summary.json"
    report_path = out_dir / "stage67c_manual_multi_format_persistent_refresh_report.md"
    write_json(summary_path, summary)
    write_report(report_path, summary)
    ledger = root / "data/forward_shadow/stage67c_manual_multi_format_persistent_refresh_ledger.csv"
    ensure_parent(ledger)
    new_row = pd.DataFrame([{
        "generated_utc": summary["generated_utc"],
        "decision": decision,
        "classification": classification,
        "macro_latest": macro_result.get("latest_after"),
        "imported_new_data": imported_new_data,
        "issues": ";".join(issues),
        "stage66j2_decision": readiness_run.get("summary_decision"),
    }])
    if ledger.exists():
        old = pd.read_csv(ledger)
        pd.concat([old, new_row], ignore_index=True).to_csv(ledger, index=False)
    else:
        new_row.to_csv(ledger, index=False)
    print(json.dumps({
        "stage": summary["stage"],
        "status": status,
        "decision": decision,
        "classification": classification,
        "summary_json": str(summary_path),
        "report_md": str(report_path),
        "issues": issues,
    }, indent=2))
    return 2 if "STOP" in decision else 0


if __name__ == "__main__":
    raise SystemExit(main())
