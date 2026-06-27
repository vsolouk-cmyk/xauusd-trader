#!/usr/bin/env python3
"""Stage95 COT Official Dataset Builder.

Builds a normalized, lag-aware COMEX Gold COT positioning dataset from official
CFTC Disaggregated COT historical text/CSV/ZIP files. No trading, broker, MT5, or
EA side effects.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import math
import os
import re
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import pandas as pd
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"pandas is required for Stage95: {exc}")

STAGE = "Stage95_COT_OFFICIAL_DATASET_BUILDER"
DEFAULT_CONFIG = "configs/stage95_cot_official_dataset_builder.json"
CFTC_HISTORICAL_COMPRESSED_INDEX = "https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm"
CFTC_DIRECT_URL_PATTERNS = {
    "disaggregated_futures_only": "https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year}.zip",
    "disaggregated_futures_options_combined": "https://www.cftc.gov/files/dea/history/com_disagg_txt_{year}.zip",
}
GOLD_CODE = "088691"


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


def normalize_col(name: Any) -> str:
    s = str(name).strip().lower()
    s = s.replace("<", "").replace(">", "")
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def find_first(columns: Iterable[str], candidates: Iterable[str]) -> Optional[str]:
    cols = list(columns)
    norm_to_orig = {normalize_col(c): c for c in cols}
    for cand in candidates:
        n = normalize_col(cand)
        if n in norm_to_orig:
            return norm_to_orig[n]
    # relaxed contains matching, useful for CFTC files with tiny spelling drift
    normalized = [(normalize_col(c), c) for c in cols]
    for cand in candidates:
        n = normalize_col(cand)
        for nc, orig in normalized:
            if n == nc or n in nc:
                return orig
    return None


def parse_date_value(value: Any) -> Optional[pd.Timestamp]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "nat"}:
        return None
    # CFTC sometimes uses YYMMDD as integer/string.
    if re.fullmatch(r"\d{6}", s):
        yy = int(s[:2])
        year = 2000 + yy if yy < 80 else 1900 + yy
        try:
            return pd.Timestamp(dt.date(year, int(s[2:4]), int(s[4:6])))
        except Exception:
            return None
    # YYYYMMDD
    if re.fullmatch(r"\d{8}", s):
        try:
            return pd.Timestamp(dt.date(int(s[:4]), int(s[4:6]), int(s[6:8])))
        except Exception:
            return None
    try:
        ts = pd.to_datetime(s, errors="coerce", utc=False)
        if pd.isna(ts):
            return None
        return pd.Timestamp(ts).tz_localize(None) if getattr(ts, "tzinfo", None) else pd.Timestamp(ts)
    except Exception:
        return None


def available_after_from_report_date(ts: pd.Timestamp, cfg: Dict[str, Any]) -> str:
    # COT positions are as of Tuesday and generally released Friday afternoon ET.
    # Use configurable conservative UTC publication timestamp. Default: +3 days 22:00 UTC.
    days = int(cfg.get("cot_release_lag_calendar_days", 3))
    hour = int(cfg.get("cot_release_utc_hour", 22))
    minute = int(cfg.get("cot_release_utc_minute", 0))
    d = ts.date() + dt.timedelta(days=days)
    out = dt.datetime(d.year, d.month, d.day, hour, minute, tzinfo=dt.timezone.utc)
    return out.isoformat().replace("+00:00", "Z")


def expand_user_path(root: Path, text: str) -> Path:
    s = os.path.expandvars(os.path.expanduser(text))
    p = Path(s)
    if not p.is_absolute():
        p = root / p
    return p


def download_cot_archives(root: Path, cfg: Dict[str, Any], out_dir: Path) -> List[Dict[str, Any]]:
    safe_mkdir(out_dir)
    report_type = cfg.get("report_type", "disaggregated_futures_options_combined")
    pattern = CFTC_DIRECT_URL_PATTERNS.get(report_type, CFTC_DIRECT_URL_PATTERNS["disaggregated_futures_options_combined"])
    start_year = int(cfg.get("start_year", 2011))
    end_year = int(cfg.get("end_year", dt.datetime.now(dt.timezone.utc).year))
    timeout = int(cfg.get("download_timeout_seconds", 45))
    results: List[Dict[str, Any]] = []
    for year in range(start_year, end_year + 1):
        url = pattern.format(year=year)
        dest = out_dir / Path(url).name
        rec: Dict[str, Any] = {"year": year, "url": url, "path": str(dest), "downloaded": False, "exists": dest.exists(), "error": None}
        if dest.exists() and dest.stat().st_size > 0 and not cfg.get("force_redownload", False):
            rec["downloaded"] = False
            rec["exists"] = True
            results.append(rec)
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Stage95-COT-Builder"})
            with urllib.request.urlopen(req, timeout=timeout) as resp, dest.open("wb") as f:
                shutil.copyfileobj(resp, f)
            rec["downloaded"] = True
            rec["exists"] = dest.exists() and dest.stat().st_size > 0
        except Exception as exc:
            rec["error"] = str(exc)
        results.append(rec)
    return results


def discover_input_files(root: Path, cfg: Dict[str, Any], downloaded_dir: Path) -> List[Path]:
    patterns = cfg.get("input_globs", [])
    files: List[Path] = []
    for pat in patterns:
        ptxt = os.path.expanduser(os.path.expandvars(str(pat)))
        base = Path(ptxt)
        if not base.is_absolute():
            globbed = list(root.glob(ptxt))
        else:
            globbed = list(base.parent.glob(base.name))
        files.extend([p for p in globbed if p.is_file()])
    if downloaded_dir.exists():
        files.extend([p for p in downloaded_dir.glob("*") if p.is_file()])
    # unique while preserving order
    seen = set()
    out = []
    for f in files:
        rp = str(f.resolve())
        if rp not in seen:
            seen.add(rp)
            out.append(f)
    return out


def read_csv_bytes(data: bytes, source_name: str) -> Optional[pd.DataFrame]:
    # CFTC text files are comma-delimited CSV. Some user files may be tab-delimited.
    for sep in [",", "\t", ";", "|"]:
        try:
            df = pd.read_csv(io.BytesIO(data), sep=sep, dtype=str, low_memory=False)
            if df.shape[1] >= 5 and len(df) > 0:
                df.attrs["source_member"] = source_name
                return df
        except Exception:
            continue
    return None


def iter_dataframes_from_file(path: Path) -> List[pd.DataFrame]:
    dfs: List[pd.DataFrame] = []
    suffix = path.suffix.lower()
    try:
        if suffix == ".zip":
            with zipfile.ZipFile(path, "r") as zf:
                for name in zf.namelist():
                    if name.endswith("/"):
                        continue
                    lname = name.lower()
                    if not (lname.endswith(".txt") or lname.endswith(".csv")):
                        continue
                    data = zf.read(name)
                    df = read_csv_bytes(data, name)
                    if df is not None:
                        df.attrs["source_member"] = name
                        dfs.append(df)
        elif suffix in {".csv", ".txt"}:
            data = path.read_bytes()
            df = read_csv_bytes(data, path.name)
            if df is not None:
                dfs.append(df)
        elif suffix in {".xlsx", ".xls"}:
            try:
                df = pd.read_excel(path, dtype=str)
                if df.shape[1] >= 5 and len(df) > 0:
                    df.attrs["source_member"] = path.name
                    dfs.append(df)
            except Exception:
                pass
    except Exception:
        return []
    return dfs


def to_numeric_series(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(",", "", regex=False).str.strip(), errors="coerce")


def normalize_cot_dataframe(df: pd.DataFrame, source_file: Path, cfg: Dict[str, Any]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    original_cols = list(df.columns)
    colmap = {c: normalize_col(c) for c in original_cols}
    df = df.copy()
    df.columns = [colmap[c] for c in original_cols]
    cols = list(df.columns)

    market_col = find_first(cols, ["market_and_exchange_names", "market_and_exchange_name", "market_name", "market"])
    code_col = find_first(cols, ["cftc_contract_market_code", "cftc_contract_market_code_quotes", "contract_market_code", "cftc_code", "cftc_commodity_code"])
    date_col = find_first(cols, ["report_date_as_yyyy_mm_dd", "report_date_yyyy_mm_dd", "report_date", "as_of_date_in_form_yymmdd", "as_of_date_in_form_yy_mm_dd"])
    oi_col = find_first(cols, ["open_interest_all", "open_interest", "open_int_all"])
    long_col = find_first(cols, ["m_money_positions_long_all", "managed_money_long", "managed_money_positions_long_all", "m_money_long_all"])
    short_col = find_first(cols, ["m_money_positions_short_all", "managed_money_short", "managed_money_positions_short_all", "m_money_short_all"])
    spread_col = find_first(cols, ["m_money_positions_spread_all", "managed_money_spread", "managed_money_positions_spread_all", "m_money_spread_all"])

    missing = [name for name, val in {
        "date": date_col,
        "open_interest": oi_col,
        "managed_money_long": long_col,
        "managed_money_short": short_col,
    }.items() if val is None]
    info: Dict[str, Any] = {
        "source_file": str(source_file),
        "source_member": df.attrs.get("source_member", ""),
        "rows_in": int(len(df)),
        "columns_in": original_cols[:80],
        "missing_required_fields": "|".join(missing),
        "rows_gold_filtered": 0,
        "rows_normalized": 0,
    }
    if missing:
        return pd.DataFrame(), info

    mask = pd.Series(False, index=df.index)
    if market_col is not None:
        m = df[market_col].astype(str).str.upper()
        mask = mask | (m.str.contains("GOLD", na=False) & (m.str.contains("COMMODITY EXCHANGE", na=False) | m.str.contains("COMEX", na=False)))
    if code_col is not None:
        code = df[code_col].astype(str).str.extract(r"(\d+)", expand=False).fillna("")
        mask = mask | code.str.zfill(6).eq(GOLD_CODE)
    gold = df[mask].copy()
    info["rows_gold_filtered"] = int(len(gold))
    if gold.empty:
        return pd.DataFrame(), info

    dates = gold[date_col].map(parse_date_value)
    out = pd.DataFrame()
    out["report_date_utc"] = dates.map(lambda x: x.date().isoformat() if x is not None and not pd.isna(x) else "")
    out["available_after_utc"] = dates.map(lambda x: available_after_from_report_date(pd.Timestamp(x), cfg) if x is not None and not pd.isna(x) else "")
    out["market"] = gold[market_col].astype(str).str.strip() if market_col else "GOLD - COMMODITY EXCHANGE INC."
    out["cftc_contract_market_code"] = gold[code_col].astype(str).str.extract(r"(\d+)", expand=False).fillna(GOLD_CODE).str.zfill(6) if code_col else GOLD_CODE
    out["open_interest"] = to_numeric_series(gold[oi_col])
    out["managed_money_long"] = to_numeric_series(gold[long_col])
    out["managed_money_short"] = to_numeric_series(gold[short_col])
    out["managed_money_spread"] = to_numeric_series(gold[spread_col]) if spread_col else pd.NA
    out["managed_money_net"] = out["managed_money_long"] - out["managed_money_short"]
    out["managed_money_net_pct_oi"] = out["managed_money_net"] / out["open_interest"].replace(0, pd.NA)
    out["managed_money_long_pct_oi"] = out["managed_money_long"] / out["open_interest"].replace(0, pd.NA)
    out["managed_money_short_pct_oi"] = out["managed_money_short"] / out["open_interest"].replace(0, pd.NA)
    out["source_file"] = str(source_file)
    out["source_member"] = str(df.attrs.get("source_member", ""))
    out["source_sha256"] = sha256_path(source_file) if source_file.exists() else ""
    out = out[out["report_date_utc"].astype(str).str.len() > 0].copy()
    out = out.dropna(subset=["open_interest", "managed_money_long", "managed_money_short"])
    info["rows_normalized"] = int(len(out))
    return out, info


def add_rolling_features(df: pd.DataFrame, cfg: Dict[str, Any]) -> pd.DataFrame:
    out = df.copy()
    out["report_date_utc"] = pd.to_datetime(out["report_date_utc"], errors="coerce")
    out = out.dropna(subset=["report_date_utc"]).sort_values("report_date_utc").drop_duplicates("report_date_utc", keep="last")
    window = int(cfg.get("rolling_z_window_reports", 156))
    minp = int(cfg.get("rolling_z_min_periods", 52))
    for col in ["managed_money_net", "managed_money_net_pct_oi", "managed_money_long_pct_oi", "managed_money_short_pct_oi"]:
        s = pd.to_numeric(out[col], errors="coerce")
        mean = s.rolling(window=window, min_periods=minp).mean()
        std = s.rolling(window=window, min_periods=minp).std(ddof=0)
        out[f"{col}_z_{window}w"] = (s - mean) / std.replace(0, pd.NA)
    out["managed_money_net_change_1w"] = pd.to_numeric(out["managed_money_net"], errors="coerce").diff(1)
    out["managed_money_net_change_4w"] = pd.to_numeric(out["managed_money_net"], errors="coerce").diff(4)
    out["managed_money_net_pct_oi_change_4w"] = pd.to_numeric(out["managed_money_net_pct_oi"], errors="coerce").diff(4)
    out["report_date_utc"] = out["report_date_utc"].dt.strftime("%Y-%m-%d")
    return out


def write_csv(path: Path, df: pd.DataFrame) -> None:
    safe_mkdir(path.parent)
    df.to_csv(path, index=False)


def build_cot_dataset(root: Path, cfg: Dict[str, Any], out_dir: Path) -> Dict[str, Any]:
    raw_dir = expand_user_path(root, cfg.get("download_dir", "data/external_frontiers/raw_cot/cftc"))
    download_results: List[Dict[str, Any]] = []
    if cfg.get("download_official_cftc", False):
        download_results = download_cot_archives(root, cfg, raw_dir)
    files = discover_input_files(root, cfg, raw_dir)
    inventory_records: List[Dict[str, Any]] = []
    normalized_parts: List[pd.DataFrame] = []
    for path in files:
        file_rec_base = {
            "path": str(path),
            "exists": path.exists(),
            "size_bytes": path.stat().st_size if path.exists() else 0,
            "sha256": sha256_path(path) if path.exists() else "",
            "dataframes_read": 0,
            "rows_normalized_total": 0,
            "error": "",
        }
        try:
            dfs = iter_dataframes_from_file(path)
            file_rec_base["dataframes_read"] = len(dfs)
            for df in dfs:
                norm, info = normalize_cot_dataframe(df, path, cfg)
                rec = dict(file_rec_base)
                rec.update(info)
                rec["rows_normalized_total"] = int(len(norm))
                inventory_records.append(rec)
                if not norm.empty:
                    normalized_parts.append(norm)
        except Exception as exc:
            rec = dict(file_rec_base)
            rec["error"] = str(exc)
            inventory_records.append(rec)
    if not inventory_records:
        for path in files:
            inventory_records.append({"path": str(path), "exists": path.exists(), "size_bytes": path.stat().st_size if path.exists() else 0, "sha256": sha256_path(path) if path.exists() else "", "dataframes_read": 0, "rows_normalized_total": 0, "error": "NO_READABLE_DATAFRAME"})

    if normalized_parts:
        cot = pd.concat(normalized_parts, ignore_index=True)
        cot = add_rolling_features(cot, cfg)
    else:
        cot = pd.DataFrame(columns=[
            "report_date_utc", "available_after_utc", "market", "cftc_contract_market_code", "open_interest",
            "managed_money_long", "managed_money_short", "managed_money_spread", "managed_money_net", "managed_money_net_pct_oi",
            "managed_money_long_pct_oi", "managed_money_short_pct_oi", "managed_money_net_z_156w",
            "managed_money_net_pct_oi_z_156w", "managed_money_net_change_1w", "managed_money_net_change_4w",
            "managed_money_net_pct_oi_change_4w", "source_file", "source_member", "source_sha256"
        ])
    output_csv = expand_user_path(root, cfg.get("output_csv", "data/external_frontiers/cot_positioning_normalized.csv"))
    write_csv(output_csv, cot)

    inventory_csv = out_dir / "stage95_cot_file_inventory.csv"
    inv_df = pd.DataFrame(inventory_records)
    write_csv(inventory_csv, inv_df)

    rows = int(len(cot))
    z_col = f"managed_money_net_pct_oi_z_{int(cfg.get('rolling_z_window_reports',156))}w"
    z_non_null = int(pd.to_numeric(cot[z_col], errors="coerce").notna().sum()) if z_col in cot.columns else 0
    min_rows = int(cfg.get("minimum_ready_rows", 300))
    min_z = int(cfg.get("minimum_zscore_non_null", 100))
    ready = rows >= min_rows and z_non_null >= min_z
    summary = {
        "cot_files_seen": len(files),
        "download_results": download_results,
        "inventory_csv": str(inventory_csv),
        "normalized_csv": str(output_csv),
        "normalized_rows": rows,
        "zscore_non_null": z_non_null,
        "minimum_ready_rows": min_rows,
        "minimum_zscore_non_null": min_z,
        "dataset_ready": ready,
        "min_report_date_utc": str(cot["report_date_utc"].min()) if rows and "report_date_utc" in cot.columns else None,
        "max_report_date_utc": str(cot["report_date_utc"].max()) if rows and "report_date_utc" in cot.columns else None,
        "sha256": sha256_path(output_csv) if output_csv.exists() else "",
    }
    return summary


def write_requirements(root: Path, out_dir: Path, cot_summary: Dict[str, Any]) -> Tuple[Path, Path]:
    req_path = out_dir / "stage95_cot_data_requirements.csv"
    rows = []
    if not cot_summary.get("dataset_ready", False):
        rows.append({
            "frontier": "COT_POSITIONING",
            "requirement": "Official CFTC Disaggregated Gold COMEX historical text/CSV/ZIP files",
            "minimum": f">={cot_summary.get('minimum_ready_rows', 300)} normalized weekly rows and >={cot_summary.get('minimum_zscore_non_null', 100)} non-null rolling zscores",
            "current": f"rows={cot_summary.get('normalized_rows',0)} zscores={cot_summary.get('zscore_non_null',0)} files_seen={cot_summary.get('cot_files_seen',0)}",
            "official_source": CFTC_HISTORICAL_COMPRESSED_INDEX,
            "notes": "Use Disaggregated Futures-and-Options Combined or Futures Only text ZIPs; filter GOLD - COMMODITY EXCHANGE INC. code 088691.",
        })
    else:
        rows.append({
            "frontier": "COT_POSITIONING",
            "requirement": "Ready for Stage96 COT positioning thesis discovery",
            "minimum": "met",
            "current": f"rows={cot_summary.get('normalized_rows',0)} zscores={cot_summary.get('zscore_non_null',0)}",
            "official_source": CFTC_HISTORICAL_COMPRESSED_INDEX,
            "notes": "Proceed to thesis-first discovery; no order authorization.",
        })
    write_csv(req_path, pd.DataFrame(rows))

    queue_path = out_dir / "stage95_thesis_queue.csv"
    queue_rows = []
    if cot_summary.get("dataset_ready", False):
        queue_rows.extend([
            {"priority": 1, "next_stage": "Stage96_COT_POSITIONING_THESIS_DISCOVERY", "thesis_family": "C01_MANAGED_MONEY_EXTREME_SHORT_MEAN_REVERSION", "stage_status": "QUEUED_NO_ORDER"},
            {"priority": 2, "next_stage": "Stage96_COT_POSITIONING_THESIS_DISCOVERY", "thesis_family": "C02_MANAGED_MONEY_CROWDING_UNWIND", "stage_status": "QUEUED_NO_ORDER"},
            {"priority": 3, "next_stage": "Stage96_COT_POSITIONING_THESIS_DISCOVERY", "thesis_family": "C03_MM_NET_ACCELERATION_CONFIRMATION", "stage_status": "QUEUED_NO_ORDER"},
        ])
    else:
        queue_rows.append({"priority": 1, "next_stage": "SUPPLY_COT_DATA_OR_ENABLE_DOWNLOAD", "thesis_family": "COT_DATA_SUPPLY", "stage_status": "BLOCKED_DATA_REQUIRED"})
    write_csv(queue_path, pd.DataFrame(queue_rows))
    return req_path, queue_path


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Stage95 official CFTC COT dataset builder")
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--out", default="reports/stage95_cot_official_dataset_builder")
    parser.add_argument("--download", action="store_true", help="Download official CFTC historical ZIPs according to config years")
    parser.add_argument("--no-download", action="store_true", help="Disable download even if config enables it")
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    cfg_path = Path(args.config).expanduser()
    if not cfg_path.is_absolute():
        cfg_path = root / cfg_path
    out_dir = Path(args.out).expanduser()
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    safe_mkdir(out_dir)

    cfg = load_json(cfg_path)
    if args.download:
        cfg["download_official_cftc"] = True
    if args.no_download:
        cfg["download_official_cftc"] = False

    cot_summary = build_cot_dataset(root, cfg, out_dir)
    req_path, queue_path = write_requirements(root, out_dir, cot_summary)

    ready = bool(cot_summary.get("dataset_ready", False))
    decision = "STAGE95_COT_DATASET_READY_FOR_STAGE96_THESIS_DISCOVERY_NO_ORDER" if ready else "STAGE95_COT_DATASET_NOT_READY_SUPPLY_DATA_NO_ORDER"
    classification = "S95_COT_DATASET_READY" if ready else "S95_COT_DATASET_NOT_READY"
    disposition = "COT_DATASET_READY_FOR_STAGE96" if ready else "SUPPLY_OR_DOWNLOAD_COT_DATA_BEFORE_STAGE96"

    summary = {
        "stage": STAGE,
        "root": str(root),
        "config": str(cfg_path),
        "generated_utc": utc_now_iso(),
        "status": "STAGE95_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
        "principle": "Build official CFTC Gold COT positioning dataset before thesis discovery. No orders, no broker connection, no MT5/EA change.",
        "official_sources": {
            "historical_compressed_index": CFTC_HISTORICAL_COMPRESSED_INDEX,
            "report_type": cfg.get("report_type", "disaggregated_futures_options_combined"),
            "direct_url_pattern": CFTC_DIRECT_URL_PATTERNS.get(cfg.get("report_type", "disaggregated_futures_options_combined")),
            "gold_contract_code": GOLD_CODE,
        },
        "cot_dataset": cot_summary,
        "selected_next_stage": "Stage96_COT_POSITIONING_THESIS_DISCOVERY" if ready else "DATA_SUPPLY_REQUIRED_BEFORE_STAGE96",
        "hard_blocks": [
            "NO_AUTOMATED_ORDER", "NO_PAPER_ORDER", "NO_BROKER_CONNECTION", "NO_EA_PROMOTION",
            "NO_PAPER_LIVE", "NO_LIVE", "NO_ORDER_AUTHORIZATION_FROM_STAGE95",
            "NO_THRESHOLD_TUNING_FROM_STAGE95_DATA_BUILDER", "NO_DIRECT_MT5_OR_EA_CHANGE_FROM_STAGE95"
        ],
        "outputs": {
            "summary_json": str(out_dir / "stage95_cot_official_dataset_builder_summary.json"),
            "report_md": str(out_dir / "stage95_cot_official_dataset_builder_report.md"),
            "cot_file_inventory_csv": cot_summary.get("inventory_csv"),
            "cot_normalized_csv": cot_summary.get("normalized_csv"),
            "data_requirements_csv": str(req_path),
            "thesis_queue_csv": str(queue_path),
        },
    }
    write_json(out_dir / "stage95_cot_official_dataset_builder_summary.json", summary)

    report_lines = [
        "# Stage95 COT Official Dataset Builder",
        "",
        "## Decision",
        f"- status: `{summary['status']}`",
        f"- decision: `{summary['decision']}`",
        f"- classification: `{summary['classification']}`",
        f"- disposition: `{summary['disposition']}`",
        "",
        "## Dataset",
        f"- normalized_rows: `{cot_summary.get('normalized_rows', 0)}`",
        f"- zscore_non_null: `{cot_summary.get('zscore_non_null', 0)}`",
        f"- ready: `{cot_summary.get('dataset_ready', False)}`",
        f"- min_report_date_utc: `{cot_summary.get('min_report_date_utc')}`",
        f"- max_report_date_utc: `{cot_summary.get('max_report_date_utc')}`",
        f"- output: `{cot_summary.get('normalized_csv')}`",
        "",
        "## Hard blocks",
    ]
    for hb in summary["hard_blocks"]:
        report_lines.append(f"- `{hb}`")
    (out_dir / "stage95_cot_official_dataset_builder_report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
