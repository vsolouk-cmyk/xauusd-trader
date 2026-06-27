#!/usr/bin/env python3
"""
Stage94 COT/Event Frontier Dataset Builder.

Builds normalized external frontier datasets only when local raw files provide
sufficient schema. It does not run thesis discovery, change MT5/EA files, or
authorize orders.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd


STAGE = "Stage94_COT_EVENT_FRONTIER_DATASET_BUILDER"
HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE94",
    "NO_THRESHOLD_TUNING_FROM_STAGE94_DATA_BUILDER",
    "NO_DIRECT_MT5_OR_EA_CHANGE_FROM_STAGE94",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def expand_path(root: Path, value: str) -> Path:
    value = os.path.expanduser(os.path.expandvars(value))
    p = Path(value)
    if not p.is_absolute():
        p = root / p
    return p


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_col(c: Any) -> str:
    s = str(c).strip().lower()
    s = s.replace("<", "").replace(">", "")
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s


def sniff_sep(path: Path) -> str:
    sample = path.read_bytes()[:8192].decode("utf-8", errors="ignore")
    if sample.count("\t") > sample.count(",") and sample.count("\t") > sample.count(";"):
        return "\t"
    if sample.count(";") > sample.count(","):
        return ";"
    return ","


def read_table(path: Path, max_rows: Optional[int] = None) -> pd.DataFrame:
    sep = sniff_sep(path)
    try:
        df = pd.read_csv(path, sep=sep, nrows=max_rows, engine="python")
    except Exception:
        df = pd.read_csv(path, sep=None, nrows=max_rows, engine="python")
    df.columns = [normalize_col(c) for c in df.columns]
    return df


def find_files(root: Path, search_paths: List[str], patterns: List[str], max_files: int = 1000) -> List[Path]:
    out: List[Path] = []
    seen = set()
    for base_raw in search_paths:
        base = expand_path(root, base_raw)
        if not base.exists():
            continue
        for pat in patterns:
            for p in base.glob(pat):
                if p.is_file() and p.suffix.lower() in {".csv", ".txt", ".tsv"}:
                    key = str(p.resolve())
                    if key not in seen:
                        seen.add(key)
                        out.append(p)
                        if len(out) >= max_files:
                            return out
    return sorted(out, key=lambda p: str(p).lower())


def first_present(cols: Iterable[str], candidates: Iterable[str]) -> Optional[str]:
    colset = set(cols)
    for c in candidates:
        nc = normalize_col(c)
        if nc in colset:
            return nc
    return None


def parse_numeric_series(s: pd.Series) -> pd.Series:
    def conv(x: Any) -> float:
        if pd.isna(x):
            return math.nan
        text = str(x).strip()
        if not text or text.lower() in {"nan", "none", "null", "-"}:
            return math.nan
        neg = False
        if text.startswith("(") and text.endswith(")"):
            neg = True
            text = text[1:-1]
        text = text.replace(",", "").replace("%", "")
        mult = 1.0
        if re.search(r"[kK]$", text):
            mult = 1_000.0
            text = text[:-1]
        elif re.search(r"[mM]$", text):
            mult = 1_000_000.0
            text = text[:-1]
        elif re.search(r"[bB]$", text):
            mult = 1_000_000_000.0
            text = text[:-1]
        try:
            val = float(text) * mult
            return -val if neg else val
        except Exception:
            m = re.search(r"-?\d+(?:\.\d+)?", text)
            if not m:
                return math.nan
            val = float(m.group(0)) * mult
            return -val if neg else val
    return s.map(conv).astype(float)


def parse_datetime_cols(df: pd.DataFrame, preferred: List[str]) -> pd.Series:
    for c in preferred:
        nc = normalize_col(c)
        if nc in df.columns:
            dt = pd.to_datetime(df[nc], errors="coerce", utc=True)
            if dt.notna().sum() > 0:
                return dt
    date_col = first_present(df.columns, ["date", "report_date", "event_date", "date_utc"])
    time_col = first_present(df.columns, ["time", "event_time", "time_utc"])
    if date_col and time_col:
        dt = pd.to_datetime(df[date_col].astype(str) + " " + df[time_col].astype(str), errors="coerce", utc=True)
        if dt.notna().sum() > 0:
            return dt
    if date_col:
        dt = pd.to_datetime(df[date_col], errors="coerce", utc=True)
        if dt.notna().sum() > 0:
            return dt
    return pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns, UTC]")


def rolling_z_asof(series: pd.Series, window: int, min_periods: int) -> pd.Series:
    prior_mean = series.shift(1).rolling(window=window, min_periods=min_periods).mean()
    prior_std = series.shift(1).rolling(window=window, min_periods=min_periods).std(ddof=0)
    z = (series - prior_mean) / prior_std.replace(0, math.nan)
    return z


COT_COLS = {
    "report_date": [
        "report_date_utc", "report_date", "as_of_date", "date", "report_date_as_yyyy_mm_dd",
        "report_date_as_yyyy_mm_dd", "as_of_date_in_form_yyyy_mm_dd"
    ],
    "managed_money_long": [
        "managed_money_long", "mm_long", "m_money_positions_long_all",
        "managed_money_positions_long_all", "money_manager_long", "noncommercial_long_all"
    ],
    "managed_money_short": [
        "managed_money_short", "mm_short", "m_money_positions_short_all",
        "managed_money_positions_short_all", "money_manager_short", "noncommercial_short_all"
    ],
    "open_interest": [
        "open_interest", "open_interest_all", "open_int", "open_interest_total"
    ],
    "commercial_long": [
        "commercial_long", "producer_merchant_processor_user_longs_all", "comm_positions_long_all"
    ],
    "commercial_short": [
        "commercial_short", "producer_merchant_processor_user_shorts_all", "comm_positions_short_all"
    ],
}


def normalize_cot_file(path: Path, cfg: Dict[str, Any]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    meta: Dict[str, Any] = {"path": str(path), "read_ok": False, "ready_schema": False, "rows": 0, "issue": None}
    try:
        df = read_table(path)
        meta["read_ok"] = True
        meta["rows"] = int(len(df))
        meta["columns"] = list(df.columns)
    except Exception as e:
        meta["issue"] = f"read_error:{e}"
        return pd.DataFrame(), meta

    date_col = first_present(df.columns, COT_COLS["report_date"])
    long_col = first_present(df.columns, COT_COLS["managed_money_long"])
    short_col = first_present(df.columns, COT_COLS["managed_money_short"])
    oi_col = first_present(df.columns, COT_COLS["open_interest"])
    if not (date_col and long_col and short_col and oi_col):
        meta["issue"] = f"missing_required_columns date={date_col} long={long_col} short={short_col} oi={oi_col}"
        return pd.DataFrame(), meta

    out = pd.DataFrame()
    out["report_date_utc"] = pd.to_datetime(df[date_col], errors="coerce", utc=True).dt.normalize()
    out["available_after_utc"] = out["report_date_utc"] + pd.to_timedelta(int(cfg.get("cot_release_lag_days", 3)), unit="D")
    hour = int(cfg.get("cot_available_after_utc_hour", 22))
    out["available_after_utc"] = out["available_after_utc"].dt.normalize() + pd.to_timedelta(hour, unit="h")
    out["managed_money_long"] = parse_numeric_series(df[long_col])
    out["managed_money_short"] = parse_numeric_series(df[short_col])
    out["open_interest"] = parse_numeric_series(df[oi_col])
    comm_long_col = first_present(df.columns, COT_COLS["commercial_long"])
    comm_short_col = first_present(df.columns, COT_COLS["commercial_short"])
    out["commercial_long"] = parse_numeric_series(df[comm_long_col]) if comm_long_col else math.nan
    out["commercial_short"] = parse_numeric_series(df[comm_short_col]) if comm_short_col else math.nan
    out["managed_money_net"] = out["managed_money_long"] - out["managed_money_short"]
    out["managed_money_long_pct_oi"] = out["managed_money_long"] / out["open_interest"].replace(0, math.nan)
    out["managed_money_short_pct_oi"] = out["managed_money_short"] / out["open_interest"].replace(0, math.nan)
    out["managed_money_net_pct_oi"] = out["managed_money_net"] / out["open_interest"].replace(0, math.nan)
    out = out.dropna(subset=["report_date_utc", "managed_money_long", "managed_money_short", "open_interest"])
    out = out.sort_values("report_date_utc").drop_duplicates(subset=["report_date_utc"], keep="last").reset_index(drop=True)
    window = int(cfg.get("cot_z_window_weeks", 156))
    minp = int(cfg.get("cot_z_min_periods", 52))
    out["managed_money_net_z_asof"] = rolling_z_asof(out["managed_money_net_pct_oi"], window, minp)
    out["managed_money_long_z_asof"] = rolling_z_asof(out["managed_money_long_pct_oi"], window, minp)
    out["managed_money_short_z_asof"] = rolling_z_asof(out["managed_money_short_pct_oi"], window, minp)
    out["source_file"] = str(path)
    meta["normalized_rows"] = int(len(out))
    meta["ready_schema"] = len(out) > 0
    meta["min_date"] = str(out["report_date_utc"].min()) if len(out) else None
    meta["max_date"] = str(out["report_date_utc"].max()) if len(out) else None
    return out, meta


EVENT_DATE_CANDIDATES = [
    "event_time_utc", "release_time_utc", "datetime_utc", "timestamp_utc", "timestamp",
    "date_utc", "event_date", "date"
]
EVENT_TYPE_CANDIDATES = ["event_type", "event", "event_name", "name", "title", "indicator", "calendar_event"]
ACTUAL_CANDIDATES = ["actual", "actual_value", "release_actual", "value"]
CONSENSUS_CANDIDATES = ["consensus", "forecast", "estimate", "expected", "survey", "consensus_value"]
PREVIOUS_CANDIDATES = ["previous", "prior", "prev", "previous_value"]
COUNTRY_CANDIDATES = ["country", "currency", "region"]


def standardize_event_type(x: Any) -> str:
    text = str(x).lower()
    if "fomc" in text or "fed interest" in text or "federal funds" in text or "rate decision" in text:
        return "FOMC"
    if "nonfarm" in text or "non-farm" in text or "nfp" in text or "payroll" in text:
        return "NFP"
    if "cpi" in text or "consumer price" in text or "inflation rate" in text:
        return "CPI"
    if "pce" in text or "personal consumption" in text:
        return "PCE"
    if "ism" in text or "pmi" in text:
        return "ISM"
    if "retail sales" in text:
        return "RetailSales"
    if "jobless" in text:
        return "JoblessClaims"
    if "gdp" in text:
        return "GDP"
    if "ppi" in text or "producer price" in text:
        return "PPI"
    return str(x).strip()[:64] if str(x).strip() else "UNKNOWN"


def normalize_event_file(path: Path, cfg: Dict[str, Any]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    meta: Dict[str, Any] = {"path": str(path), "read_ok": False, "ready_schema": False, "rows": 0, "issue": None}
    try:
        df = read_table(path)
        meta["read_ok"] = True
        meta["rows"] = int(len(df))
        meta["columns"] = list(df.columns)
    except Exception as e:
        meta["issue"] = f"read_error:{e}"
        return pd.DataFrame(), meta

    event_col = first_present(df.columns, EVENT_TYPE_CANDIDATES)
    actual_col = first_present(df.columns, ACTUAL_CANDIDATES)
    consensus_col = first_present(df.columns, CONSENSUS_CANDIDATES)
    previous_col = first_present(df.columns, PREVIOUS_CANDIDATES)
    country_col = first_present(df.columns, COUNTRY_CANDIDATES)

    event_time = parse_datetime_cols(df, EVENT_DATE_CANDIDATES)
    if not (event_col and actual_col and consensus_col) or event_time.notna().sum() == 0:
        meta["issue"] = f"missing_required_columns event={event_col} actual={actual_col} consensus={consensus_col} datetime_ok={event_time.notna().sum()}"
        return pd.DataFrame(), meta

    out = pd.DataFrame()
    out["event_time_utc"] = event_time
    out["available_after_utc"] = event_time
    out["event_type"] = df[event_col].map(standardize_event_type)
    out["event_name_raw"] = df[event_col].astype(str)
    out["country"] = df[country_col].astype(str) if country_col else "US"
    out["actual"] = parse_numeric_series(df[actual_col])
    out["consensus"] = parse_numeric_series(df[consensus_col])
    out["previous"] = parse_numeric_series(df[previous_col]) if previous_col else math.nan
    out["surprise"] = out["actual"] - out["consensus"]
    out["surprise_pct_consensus"] = out["surprise"] / out["consensus"].replace(0, math.nan).abs()
    out = out.dropna(subset=["event_time_utc", "event_type", "actual", "consensus", "surprise"])
    out = out.sort_values("event_time_utc").reset_index(drop=True)
    window = int(cfg.get("event_z_window", 60))
    minp = int(cfg.get("event_z_min_periods", 12))
    out["surprise_z_asof"] = math.nan
    for _, idx in out.groupby("event_type").groups.items():
        idx_list = list(idx)
        z = rolling_z_asof(out.loc[idx_list, "surprise"].reset_index(drop=True), window, minp)
        out.loc[idx_list, "surprise_z_asof"] = z.values
    out["event_date_utc"] = out["event_time_utc"].dt.normalize()
    out["source_file"] = str(path)
    meta["normalized_rows"] = int(len(out))
    meta["ready_schema"] = len(out) > 0
    meta["min_date"] = str(out["event_time_utc"].min()) if len(out) else None
    meta["max_date"] = str(out["event_time_utc"].max()) if len(out) else None
    return out, meta


def write_templates(root: Path, cfg: Dict[str, Any]) -> Dict[str, str]:
    base = expand_path(root, cfg.get("template_dir", "data/frontier_templates"))
    base.mkdir(parents=True, exist_ok=True)
    cot_template = base / "stage94_cot_positioning_normalized_template.csv"
    event_template = base / "stage94_event_surprise_normalized_template.csv"
    if not cot_template.exists():
        pd.DataFrame(columns=[
            "report_date_utc", "available_after_utc", "managed_money_long", "managed_money_short",
            "open_interest", "managed_money_net", "managed_money_long_pct_oi",
            "managed_money_short_pct_oi", "managed_money_net_pct_oi", "managed_money_net_z_asof",
            "managed_money_long_z_asof", "managed_money_short_z_asof", "source_file"
        ]).to_csv(cot_template, index=False)
    if not event_template.exists():
        pd.DataFrame(columns=[
            "event_time_utc", "available_after_utc", "event_date_utc", "event_type", "event_name_raw",
            "country", "actual", "consensus", "previous", "surprise", "surprise_pct_consensus",
            "surprise_z_asof", "source_file"
        ]).to_csv(event_template, index=False)
    return {"cot_template": str(cot_template), "event_surprise_template": str(event_template)}


def build_report(summary: Dict[str, Any]) -> str:
    lines = [
        "# Stage94 COT/Event Frontier Dataset Builder",
        "",
        "## Decision",
        f"- status: `{summary['status']}`",
        f"- decision: `{summary['decision']}`",
        f"- classification: `{summary['classification']}`",
        f"- disposition: `{summary['disposition']}`",
        "",
        "## Dataset build status",
        f"- COT files: `{summary['cot_file_count']}`, ready files: `{summary['cot_ready_file_count']}`, normalized rows: `{summary['cot_normalized_rows']}`",
        f"- Event files: `{summary['event_file_count']}`, ready files: `{summary['event_ready_file_count']}`, normalized rows: `{summary['event_normalized_rows']}`",
        "",
        "## Selected next stage",
        f"- `{summary['selected_next_stage']}`",
        "",
        "## Outputs",
    ]
    for k, v in summary["outputs"].items():
        lines.append(f"- `{k}`: `{v}`")
    lines += ["", "## Hard blocks"]
    lines.extend([f"- `{b}`" for b in summary["hard_blocks"]])
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    cfg_path = expand_path(root, args.config)
    cfg = read_json(cfg_path)
    out_dir = expand_path(root, args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    template_paths = write_templates(root, cfg)

    cot_files = find_files(root, cfg.get("cot_search_paths", []), cfg.get("cot_patterns", []))
    event_files = find_files(root, cfg.get("event_search_paths", []), cfg.get("event_patterns", []))

    cot_frames: List[pd.DataFrame] = []
    cot_inventory: List[Dict[str, Any]] = []
    for p in cot_files:
        norm, meta = normalize_cot_file(p, cfg)
        meta["sha256"] = sha256_file(p) if p.exists() else None
        cot_inventory.append(meta)
        if meta.get("ready_schema") and len(norm):
            cot_frames.append(norm)

    event_frames: List[pd.DataFrame] = []
    event_inventory: List[Dict[str, Any]] = []
    for p in event_files:
        norm, meta = normalize_event_file(p, cfg)
        meta["sha256"] = sha256_file(p) if p.exists() else None
        event_inventory.append(meta)
        if meta.get("ready_schema") and len(norm):
            event_frames.append(norm)

    output_data_dir = expand_path(root, cfg.get("output_data_dir", "data/external_frontiers"))
    output_data_dir.mkdir(parents=True, exist_ok=True)
    cot_output = output_data_dir / "cot_positioning_normalized.csv"
    event_output = output_data_dir / "event_surprise_normalized.csv"

    if cot_frames:
        cot_all = pd.concat(cot_frames, ignore_index=True).sort_values("report_date_utc")
        cot_all = cot_all.drop_duplicates(subset=["report_date_utc"], keep="last")
    else:
        cot_all = pd.DataFrame()
    if event_frames:
        event_all = pd.concat(event_frames, ignore_index=True).sort_values("event_time_utc")
        event_all = event_all.drop_duplicates(subset=["event_time_utc", "event_type", "actual", "consensus"], keep="last")
    else:
        event_all = pd.DataFrame()

    cot_all.to_csv(cot_output, index=False)
    event_all.to_csv(event_output, index=False)

    cot_min_rows = int(cfg.get("min_cot_rows", 300))
    event_min_rows = int(cfg.get("min_event_rows", 500))
    cot_ready = len(cot_all) >= cot_min_rows and "managed_money_net_z_asof" in cot_all.columns and cot_all["managed_money_net_z_asof"].notna().sum() > 0
    event_ready = len(event_all) >= event_min_rows and "surprise_z_asof" in event_all.columns and event_all["surprise_z_asof"].notna().sum() > 0

    if cot_ready and event_ready:
        decision = "STAGE94_COT_AND_EVENT_DATASETS_READY_FOR_STAGE95_DISCOVERY_NO_ORDER"
        classification = "S94_EXTERNAL_FRONTIERS_READY"
        disposition = "COT_AND_EVENT_DATASETS_READY_FOR_STAGE95"
        selected_next_stage = "Stage95_COT_EVENT_THESIS_DISCOVERY"
    elif cot_ready:
        decision = "STAGE94_COT_DATASET_READY_FOR_STAGE95_DISCOVERY_NO_ORDER"
        classification = "S94_COT_FRONTIER_READY"
        disposition = "COT_DATASET_READY_FOR_STAGE95"
        selected_next_stage = "Stage95_COT_POSITIONING_THESIS_DISCOVERY"
    elif event_ready:
        decision = "STAGE94_EVENT_SURPRISE_DATASET_READY_FOR_STAGE95_DISCOVERY_NO_ORDER"
        classification = "S94_EVENT_FRONTIER_READY"
        disposition = "EVENT_SURPRISE_DATASET_READY_FOR_STAGE95"
        selected_next_stage = "Stage95_EVENT_SURPRISE_THESIS_DISCOVERY"
    else:
        decision = "STAGE94_EXTERNAL_FRONTIER_DATA_STILL_NOT_READY_NO_ORDER"
        classification = "S94_DATA_FRONTIER_STILL_NOT_READY"
        disposition = "SUPPLY_RAW_COT_OR_EVENT_SURPRISE_DATA_BEFORE_STAGE95"
        selected_next_stage = "DATA_SUPPLY_REQUIRED_BEFORE_DISCOVERY"

    frontier_status = [
        {
            "frontier": "COT_POSITIONING",
            "normalized_rows": int(len(cot_all)),
            "ready": bool(cot_ready),
            "output_path": str(cot_output),
            "minimum_rows": cot_min_rows,
            "zscore_non_null": int(cot_all["managed_money_net_z_asof"].notna().sum()) if "managed_money_net_z_asof" in cot_all.columns else 0,
            "next_action": "Stage95_COT_POSITIONING_THESIS_DISCOVERY" if cot_ready else "Supply normalized or raw COT gold/COMEX managed-money rows",
        },
        {
            "frontier": "EVENT_SURPRISE",
            "normalized_rows": int(len(event_all)),
            "ready": bool(event_ready),
            "output_path": str(event_output),
            "minimum_rows": event_min_rows,
            "zscore_non_null": int(event_all["surprise_z_asof"].notna().sum()) if "surprise_z_asof" in event_all.columns else 0,
            "next_action": "Stage95_EVENT_SURPRISE_THESIS_DISCOVERY" if event_ready else "Supply event-time/actual/consensus high-impact US event rows",
        },
    ]

    pd.DataFrame(cot_inventory).to_csv(out_dir / "stage94_cot_file_inventory.csv", index=False)
    pd.DataFrame(event_inventory).to_csv(out_dir / "stage94_event_file_inventory.csv", index=False)
    pd.DataFrame(frontier_status).to_csv(out_dir / "stage94_frontier_dataset_status.csv", index=False)

    requirements = [
        {
            "frontier": "COT_POSITIONING",
            "required_columns": "report_date_utc/as_of_date, managed_money_long, managed_money_short, open_interest",
            "minimum": cot_min_rows,
            "accepted_raw_schema_examples": "CFTC disaggregated m_money_positions_long_all, m_money_positions_short_all, open_interest_all",
            "normalized_output": str(cot_output),
            "lookahead_rule": "available_after_utc must be after COT public release; z-scores use prior rows only",
        },
        {
            "frontier": "EVENT_SURPRISE",
            "required_columns": "event_time_utc/date+time, event_type/name, actual, consensus/forecast",
            "minimum": event_min_rows,
            "accepted_event_types": "CPI,NFP,FOMC,PCE,ISM,RetailSales,JoblessClaims,GDP,PPI",
            "normalized_output": str(event_output),
            "lookahead_rule": "available_after_utc equals release time or later; surprise_z uses prior same-event rows only",
        },
    ]
    pd.DataFrame(requirements).to_csv(out_dir / "stage94_data_requirements.csv", index=False)

    thesis_queue = []
    if cot_ready:
        thesis_queue.append({
            "priority": 1,
            "stage": "Stage95_COT_POSITIONING_THESIS_DISCOVERY",
            "frontier": "COT_POSITIONING",
            "status": "READY_NO_ORDER",
            "thesis_family": "COT managed-money exhaustion / short-covering / crowded-long risk",
        })
    else:
        thesis_queue.append({
            "priority": 1,
            "stage": "Stage95_COT_POSITIONING_THESIS_DISCOVERY",
            "frontier": "COT_POSITIONING",
            "status": "BLOCKED_DATA_REQUIRED",
            "thesis_family": "COT managed-money exhaustion / short-covering / crowded-long risk",
        })
    if event_ready:
        thesis_queue.append({
            "priority": 2,
            "stage": "Stage95_EVENT_SURPRISE_THESIS_DISCOVERY",
            "frontier": "EVENT_SURPRISE",
            "status": "READY_NO_ORDER",
            "thesis_family": "post-event gold repricing after CPI/NFP/FOMC surprise",
        })
    else:
        thesis_queue.append({
            "priority": 2,
            "stage": "Stage95_EVENT_SURPRISE_THESIS_DISCOVERY",
            "frontier": "EVENT_SURPRISE",
            "status": "BLOCKED_DATA_REQUIRED",
            "thesis_family": "post-event gold repricing after CPI/NFP/FOMC surprise",
        })
    pd.DataFrame(thesis_queue).to_csv(out_dir / "stage94_thesis_queue.csv", index=False)

    refs = []
    for name, default_path in [
        ("stage88", "reports/stage88_daily_unified_observer_combo/stage88_daily_unified_observer_combo_summary.json"),
        ("stage89", "reports/stage89_residual_regime_thesis_discovery/stage89_residual_regime_thesis_discovery_summary.json"),
        ("stage92", "reports/stage92_intraday_session_residual_thesis_discovery/stage92_intraday_session_residual_thesis_discovery_summary.json"),
        ("stage93", "reports/stage93_cot_event_frontier_readiness_builder/stage93_cot_event_frontier_readiness_builder_summary.json"),
    ]:
        rp = expand_path(root, default_path)
        entry = {"name": name, "path": str(rp), "exists": rp.exists(), "read_ok": False, "decision": None, "disposition": None}
        if rp.exists():
            try:
                rj = read_json(rp)
                entry["read_ok"] = True
                entry["decision"] = rj.get("decision")
                entry["disposition"] = rj.get("disposition")
            except Exception as e:
                entry["error"] = str(e)
        refs.append(entry)

    summary = {
        "stage": STAGE,
        "root": str(root),
        "config": str(cfg_path),
        "generated_utc": utc_now_iso(),
        "status": "STAGE94_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
        "principle": "Build normalized COT/event-surprise external frontier datasets before thesis discovery. No orders, no broker connection, no MT5/EA change.",
        "references": refs,
        "cot_file_count": len(cot_files),
        "cot_ready_file_count": sum(1 for m in cot_inventory if m.get("ready_schema")),
        "cot_normalized_rows": int(len(cot_all)),
        "cot_dataset_ready": bool(cot_ready),
        "event_file_count": len(event_files),
        "event_ready_file_count": sum(1 for m in event_inventory if m.get("ready_schema")),
        "event_normalized_rows": int(len(event_all)),
        "event_dataset_ready": bool(event_ready),
        "frontier_status": frontier_status,
        "selected_next_stage": selected_next_stage,
        "template_paths": template_paths,
        "hard_blocks": HARD_BLOCKS,
        "outputs": {
            "summary_json": str(out_dir / "stage94_cot_event_frontier_dataset_builder_summary.json"),
            "report_md": str(out_dir / "stage94_cot_event_frontier_dataset_builder_report.md"),
            "frontier_dataset_status_csv": str(out_dir / "stage94_frontier_dataset_status.csv"),
            "cot_file_inventory_csv": str(out_dir / "stage94_cot_file_inventory.csv"),
            "event_file_inventory_csv": str(out_dir / "stage94_event_file_inventory.csv"),
            "data_requirements_csv": str(out_dir / "stage94_data_requirements.csv"),
            "thesis_queue_csv": str(out_dir / "stage94_thesis_queue.csv"),
            "cot_normalized_csv": str(cot_output),
            "event_surprise_normalized_csv": str(event_output),
        },
    }
    write_json(out_dir / "stage94_cot_event_frontier_dataset_builder_summary.json", summary)
    (out_dir / "stage94_cot_event_frontier_dataset_builder_report.md").write_text(build_report(summary), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
