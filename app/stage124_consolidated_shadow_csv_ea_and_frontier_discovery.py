#!/usr/bin/env python3
"""
Stage124 consolidated shadow CSV/EA-safe observer prep + next frontier discovery.

One-pass operator stage:
1) Fix/static-replay Stage123 return mapping by joining Stage121 dry-run events to Stage117 dataset.
2) Emit shadow-only observer CSV and an EA-safe no-trade MQL5 observer source/contract.
3) Immediately run the next frontier discovery scan using available macro/COT/dollar/SPDR/Census-event inputs.

No order, no broker, no trading. MT5/MQL5 writes are optional and limited to shadow-only files.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

STAGE = "Stage124C_CONSOLIDATED_SHADOW_CSV_EA_PATH_AND_NEXT_DISCOVERY"
STATUS_OK = "STAGE124C_COMPLETE_CONSOLIDATED_READY_NO_ORDER"
STATUS_WATCH = "STAGE124C_COMPLETE_WITH_WATCH_OR_BLOCK_NO_ORDER"
DECISION_OK = "STAGE124C_SHADOW_CSV_EA_PATH_READY_AND_DISCOVERY_REVIEW_READY_NO_ORDER"
DECISION_WATCH = "STAGE124C_REPLAY_OR_DISCOVERY_WATCH_NO_ORDER"

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_TRADE_REQUEST_FROM_STAGE124",
    "NO_ORDER_SEND",
    "NO_CTRADE_USAGE",
    "NO_PAPER_LIVE",
    "NO_LIVE",
]

MT5_FILES_DEFAULT = "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files"
MT5_EXPERTS_DEFAULT = "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Experts/Advisors/XAUUSD"

TIME_COL_CANDIDATES = [
    "_stage121_timestamp", "_stage123_timestamp", "utc_time", "time_utc", "timestamp", "datetime", "date_time", "bar_time", "time", "date"
]
RETURN_COL_CANDIDATES = [
    "fwd_ret_bps_h120", "forward_return_bps", "h120_forward_return_bps", "fwd_return_bps_h120",
    "ret_bps_h120", "fwd_ret_120h_bps", "forward_ret_bps_h120", "forward_h120_bps",
    "horizon_return_bps", "future_return_bps", "target_return_bps", "target_bps_h120",
]
RULE_ID_COLS = ["observer_rule_id", "rule_id", "source_rule_id", "stage117_rule_id", "base_rule_id"]

EA_SAFE_MQL5 = r'''//+------------------------------------------------------------------+
//| XAUUSD Stage124C Shadow Observer Only EA                         |
//| Reports-only EA. No trade library and never sends orders.        |
//+------------------------------------------------------------------+
#property strict
#property version   "1.243"
#property description "Stage124C shadow observer only; no trading actions."

input string InpShadowCsvFile = "xauusd_stage124_shadow_observer_signal.csv";
input int    InpTimerSeconds = 60;
input bool   InpPrintAllKeys = false;

string g_rule_id = "";
string g_status = "";
string g_allow_trading = "";
string g_last_signal_time = "";
string g_cost10_mean_bps = "";
string g_cost10_hit_rate = "";
string g_combo_mode = "";

int OnInit()
{
   EventSetTimer(InpTimerSeconds);
   Print("Stage124C ShadowObserverOnly initialized. File=", InpShadowCsvFile,
         " Trading disabled by design. This EA does not send orders.");
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   Print("Stage124C ShadowObserverOnly deinitialized. reason=", reason);
}

void OnTick()
{
   // Intentionally empty. Shadow observer runs on timer only and never trades.
}

void ResetState()
{
   g_rule_id = "";
   g_status = "";
   g_allow_trading = "";
   g_last_signal_time = "";
   g_cost10_mean_bps = "";
   g_cost10_hit_rate = "";
   g_combo_mode = "";
}

void CaptureKeyValue(const string key, const string value)
{
   if(key == "rule_id") g_rule_id = value;
   else if(key == "rule_status") g_status = value;
   else if(key == "allow_trading") g_allow_trading = value;
   else if(key == "last_signal_time_utc") g_last_signal_time = value;
   else if(key == "cost10_mean_bps") g_cost10_mean_bps = value;
   else if(key == "cost10_hit_rate") g_cost10_hit_rate = value;
   else if(key == "combo_integration_mode") g_combo_mode = value;
}

void OnTimer()
{
   int handle = FileOpen(InpShadowCsvFile, FILE_READ|FILE_CSV|FILE_ANSI, ',');
   if(handle == INVALID_HANDLE)
   {
      Print("Stage124C shadow key-value CSV not found in MQL5/Files: ", InpShadowCsvFile,
            " error=", GetLastError());
      return;
   }

   ResetState();
   int kv_count = 0;
   while(!FileIsEnding(handle))
   {
      string key = FileReadString(handle);
      if(FileIsEnding(handle) && key == "")
         break;
      string value = FileReadString(handle);
      if(key != "")
      {
         CaptureKeyValue(key, value);
         kv_count++;
         if(InpPrintAllKeys)
            Print("Stage124C shadow kv: ", key, "=", value);
      }
   }
   FileClose(handle);

   Print("Stage124C shadow CSV read complete. kv_count=", kv_count,
         " rule=", g_rule_id,
         " status=", g_status,
         " allow_trading=", g_allow_trading,
         " cost10_mean_bps=", g_cost10_mean_bps,
         " cost10_hit_rate=", g_cost10_hit_rate,
         " last_signal=", g_last_signal_time,
         " combo_mode=", g_combo_mode,
         ". Trading remains disabled.");
}
'''


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def normalize_col(c: object) -> str:
    s = str(c).strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return re.sub(r"_+", "_", s).strip("_")


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [normalize_col(c) for c in out.columns]
    return out


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, obj: dict) -> str:
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)


def write_csv(path: Path, rows: Sequence[dict], fieldnames: Optional[List[str]] = None) -> str:
    ensure_dir(path.parent)
    if fieldnames is None:
        fieldnames = []
        seen = set()
        for r in rows:
            for k in r.keys():
                if k not in seen:
                    seen.add(k)
                    fieldnames.append(k)
        if not fieldnames:
            fieldnames = ["empty"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return str(path)


def first_existing_col(df: pd.DataFrame, candidates: Iterable[str]) -> Optional[str]:
    if df.empty:
        return None
    lower = {normalize_col(c): c for c in df.columns}
    for c in candidates:
        nc = normalize_col(c)
        if nc in lower:
            return lower[nc]
    return None


def detect_time_col(df: pd.DataFrame) -> Optional[str]:
    direct = first_existing_col(df, TIME_COL_CANDIDATES)
    if direct:
        return direct
    for c in df.columns:
        lc = normalize_col(c)
        if "time" in lc or lc == "date":
            return c
    return None


def detect_return_col(df: pd.DataFrame, horizon_hours: int = 120) -> Optional[str]:
    direct = first_existing_col(df, RETURN_COL_CANDIDATES)
    if direct:
        return direct
    h = str(horizon_hours)
    candidates: List[Tuple[int, str]] = []
    for c in df.columns:
        lc = normalize_col(c)
        score = 0
        if "bps" in lc:
            score += 2
        if h in lc or f"h{h}" in lc or f"{h}h" in lc:
            score += 2
        if any(tok in lc for tok in ["fwd", "forward", "future", "target", "horizon"]):
            score += 2
        if any(tok in lc for tok in ["return", "ret", "pnl"]):
            score += 1
        if score >= 5:
            candidates.append((score, c))
    if candidates:
        return sorted(candidates, key=lambda x: (-x[0], len(str(x[1]))))[0][1]
    return None


def to_utc_naive(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce", utc=True).dt.tz_convert(None)


def coerce_num(s: pd.Series) -> pd.Series:
    """Coerce a Series to numeric float values safely across pandas/numpy versions.

    Pandas/NumPy on newer Python versions can fail when quantile is applied to
    boolean arrays because numpy boolean subtraction is unsupported.  This helper
    forces bool-like data to float and turns non-numeric/object values into NaN,
    so discovery thresholds skip unavailable proxy columns instead of crashing.
    """
    if not isinstance(s, pd.Series):
        s = pd.Series(s)
    if pd.api.types.is_bool_dtype(s):
        return s.astype("float64")
    if s.dtype == object or pd.api.types.is_string_dtype(s):
        s = s.astype(str).str.replace(",", "", regex=False).str.replace("%", "", regex=False).str.strip()
        s = s.replace({"": pd.NA, ".": pd.NA, "nan": pd.NA, "None": pd.NA, "NaN": pd.NA, "<NA>": pd.NA, "True": "1", "False": "0", "true": "1", "false": "0"})
    out = pd.to_numeric(s, errors="coerce")
    if pd.api.types.is_bool_dtype(out):
        out = out.astype("float64")
    return out.astype("float64")


def load_stage_paths(root: Path) -> Dict[str, Path]:
    return {
        "report_dir": root / "reports" / "stage124_consolidated_shadow_csv_ea_and_frontier_discovery",
        "stage117_dir": root / "reports" / "stage117_segmented_macro_cot_dollar_discovery",
        "stage121_dir": root / "reports" / "stage121_dry_run_observer_preflight",
        "stage122_dir": root / "reports" / "stage122_shadow_observer_package_review",
        "stage123_dir": root / "reports" / "stage123_static_replay_shadow_observer_package",
        "feature_dir": root / "data" / "fundamental_event_inbox" / "features",
        "shadow_dir": root / "data" / "shadow_observer",
        "mql5_repo_dir": root / "mql5" / "Experts",
    }


def load_stage117_dataset(root: Path, paths: Dict[str, Path]) -> pd.DataFrame:
    candidates = [
        paths["feature_dir"] / "stage117_joined_macro_cot_dollar_h1_research_dataset.csv",
        paths["stage117_dir"] / "stage117_joined_macro_cot_dollar_h1_research_dataset.csv",
    ]
    for p in candidates:
        df = read_csv(p)
        if not df.empty:
            return normalize_columns(df)
    return pd.DataFrame()


def join_events_to_returns(events: pd.DataFrame, dataset: pd.DataFrame, horizon_hours: int) -> Tuple[pd.DataFrame, Optional[str], List[str]]:
    warnings: List[str] = []
    if events.empty:
        return events.copy(), None, ["stage121_events_missing"]
    out = normalize_columns(events)
    ds = normalize_columns(dataset)
    event_time_col = detect_time_col(out)
    ds_time_col = detect_time_col(ds)
    if not event_time_col or ds.empty or not ds_time_col:
        warnings.append("time_or_dataset_missing_for_return_join")
        return out, detect_return_col(out, horizon_hours), warnings

    return_col = detect_return_col(out, horizon_hours)
    if return_col:
        out[return_col] = coerce_num(out[return_col])
        return out, return_col, warnings

    ds_return_col = detect_return_col(ds, horizon_hours)
    if not ds_return_col:
        warnings.append("forward_return_column_not_detected_in_stage117_dataset")
        return out, None, warnings

    out["_event_time_join"] = to_utc_naive(out[event_time_col])
    ds["_event_time_join"] = to_utc_naive(ds[ds_time_col])
    ds["_stage124_forward_return_bps"] = coerce_num(ds[ds_return_col])

    keep_cols = ["_event_time_join", "_stage124_forward_return_bps"]
    for c in ["stage117_split", "split", "sample_split", "segment"]:
        cc = first_existing_col(ds, [c])
        if cc and cc not in keep_cols:
            keep_cols.append(cc)
    joined = out.merge(ds[keep_cols].dropna(subset=["_event_time_join"]).drop_duplicates("_event_time_join"), on="_event_time_join", how="left")
    if joined["_stage124_forward_return_bps"].notna().sum() == 0:
        # Fallback to nearest one-hour match if exact string formatting differs.
        e = out.dropna(subset=["_event_time_join"]).sort_values("_event_time_join")
        d = ds[keep_cols].dropna(subset=["_event_time_join"]).sort_values("_event_time_join")
        if not e.empty and not d.empty:
            joined = pd.merge_asof(e, d, on="_event_time_join", direction="nearest", tolerance=pd.Timedelta("61min"))
            out2 = out.merge(joined[["_event_time_join", "_stage124_forward_return_bps"]], on="_event_time_join", how="left")
            joined = out2
    return joined, "_stage124_forward_return_bps", warnings


def event_spacing_hours(times: pd.Series) -> Tuple[Optional[float], bool]:
    t = pd.to_datetime(times, errors="coerce").dropna().sort_values()
    if len(t) < 2:
        return None, True
    diffs = t.diff().dropna().dt.total_seconds() / 3600.0
    min_spacing = float(diffs.min()) if not diffs.empty else None
    return min_spacing, bool(min_spacing is None or min_spacing >= 119.9)


def concentration_by_year(times: pd.Series) -> Tuple[float, List[dict]]:
    t = pd.to_datetime(times, errors="coerce").dropna()
    if t.empty:
        return 0.0, []
    years = t.dt.year.astype(str)
    vc = years.value_counts().sort_index()
    total = int(vc.sum())
    rows = [{"year": y, "event_count": int(n), "pct": round(float(n) / total, 4)} for y, n in vc.items()]
    return max(r["pct"] for r in rows), rows


def compute_replay_metrics(rule_id: str, events: pd.DataFrame, return_col: Optional[str], horizon_hours: int, cost_bps: float = 10.0) -> Dict[str, object]:
    time_col = detect_time_col(events)
    vals = coerce_num(events[return_col]) if return_col and return_col in events.columns else pd.Series(dtype=float)
    valid = vals.dropna()
    min_spacing, spacing_pass = event_spacing_hours(events[time_col]) if time_col else (None, False)
    max_year_conc, _ = concentration_by_year(events[time_col]) if time_col else (0.0, [])
    mean_bps = float(valid.mean()) if len(valid) else math.nan
    hit = float((valid > 0).mean()) if len(valid) else math.nan
    cost_mean = mean_bps - cost_bps if not math.isnan(mean_bps) else math.nan
    cost_hit = float(((valid - cost_bps) > 0).mean()) if len(valid) else math.nan
    pass_static = bool(
        len(valid) >= 30 and
        not math.isnan(cost_mean) and cost_mean > 0 and
        not math.isnan(cost_hit) and cost_hit >= 0.55 and
        spacing_pass and
        max_year_conc <= 0.80
    )
    reasons = []
    if len(valid) < 30:
        reasons.append("valid_forward_return_rows_lt_30")
    if return_col is None:
        reasons.append("forward_return_column_not_detected")
    if not spacing_pass:
        reasons.append("event_spacing_lt_120h")
    if max_year_conc > 0.80:
        reasons.append("year_concentration_gt_80pct")
    if math.isnan(cost_mean) or cost_mean <= 0:
        reasons.append("cost10_mean_not_positive")
    if math.isnan(cost_hit) or cost_hit < 0.55:
        reasons.append("cost10_hit_rate_lt_55pct")
    return {
        "rule_id": rule_id,
        "static_replay_status": "PASS_STATIC_REPLAY" if pass_static else "WATCH_STATIC_REPLAY",
        "event_rows": int(len(events)),
        "valid_forward_return_rows": int(len(valid)),
        "return_col": return_col or "",
        "mean_bps": round(mean_bps, 4) if not math.isnan(mean_bps) else "",
        "hit_rate": round(hit, 4) if not math.isnan(hit) else "",
        "cost10_mean_bps": round(cost_mean, 4) if not math.isnan(cost_mean) else "",
        "cost10_hit_rate": round(cost_hit, 4) if not math.isnan(cost_hit) else "",
        "min_observed_spacing_hours": round(min_spacing, 2) if min_spacing is not None else "",
        "event_spacing_pass": spacing_pass,
        "max_year_concentration": round(max_year_conc, 4),
        "horizon_hours": horizon_hours,
        "block_reasons": ";".join(reasons),
    }


def build_shadow_csv_row(summary: dict, metrics: dict, rule_meta: dict, last_signal_time: str) -> dict:
    return {
        "generated_utc": summary["generated_utc"],
        "stage": STAGE,
        "mode": "SHADOW_OBSERVER_ONLY_NO_ORDER",
        "symbol": "XAUUSD",
        "timeframe": "H1",
        "side": "LONG_OBSERVATION_ONLY",
        "rule_id": metrics.get("rule_id", "S120_01_SPDR_FLOW_SUPPORT_MACRO_RELIEF_OBSERVER_DESIGN"),
        "source_rule_id": rule_meta.get("source_rule_id", "S117_06_SPDR_FLOW_SUPPORT_MACRO_RELIEF"),
        "rule_status": metrics.get("static_replay_status", "WATCH_STATIC_REPLAY"),
        "allow_trading": "false",
        "observer_only": "true",
        "candidate_only": str(rule_meta.get("candidate_only", True)).lower(),
        "stage116_spdr_status": rule_meta.get("stage116_spdr_status", "VALIDATED_CANDIDATE"),
        "dxy_source": rule_meta.get("dxy_source", "FRED_DTWEXBGS_FALLBACK_OR_DOLLAR_PRESSURE_PROXY"),
        "horizon_hours": metrics.get("horizon_hours", 120),
        "event_rows": metrics.get("event_rows", 0),
        "cost10_mean_bps": metrics.get("cost10_mean_bps", ""),
        "cost10_hit_rate": metrics.get("cost10_hit_rate", ""),
        "last_signal_time_utc": last_signal_time,
        "block_reasons": metrics.get("block_reasons", ""),
        "combo_integration_mode": "SEPARATE_SHADOW_NOW__MERGE_TO_UNIFIED_COMBO_RECOMMENDED_AFTER_COMBO_EA_PATCH",
        "combo_active_update": "false",
        "contract_note": "CSV is for shadow observer telemetry only. EA must not place orders.",
    }




def build_mt5_shadow_kv_rows(shadow_row: dict) -> List[dict]:
    """Build a two-column key/value CSV for MT5 FILE_CSV readers.

    The repo/report CSV remains wide for pandas and audit use.  The MT5 copy is
    intentionally key/value because a generic FILE_CSV loop that reads fixed
    cell counts will otherwise print header fragments instead of signal state.
    """
    ordered_keys = [
        "generated_utc", "stage", "mode", "symbol", "timeframe", "side",
        "rule_id", "source_rule_id", "rule_status", "allow_trading",
        "observer_only", "candidate_only", "stage116_spdr_status", "dxy_source",
        "horizon_hours", "event_rows", "cost10_mean_bps", "cost10_hit_rate",
        "last_signal_time_utc", "block_reasons", "combo_integration_mode",
        "combo_active_update", "contract_note",
    ]
    rows = []
    for k in ordered_keys:
        if k in shadow_row:
            rows.append({"key": k, "value": shadow_row.get(k, "")})
    return rows


def write_kv_csv(path: Path, rows: Sequence[dict]) -> str:
    ensure_dir(path.parent)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for r in rows:
            w.writerow([r.get("key", ""), r.get("value", "")])
    return str(path)


def write_combo_overlay_preview(root: Path, report_dir: Path, shadow_row: dict) -> Dict[str, str]:
    """Create a non-active preview showing how Stage124C would attach to the 7-rule combo.

    This does not overwrite data/mt5_bridge/unified_observer_signal.csv.  It is a
    bridge design artifact for the next consolidated combo patch, so the existing
    Stage109/Stage108 combo can keep running unchanged until deliberate merge.
    """
    src = root / "data" / "mt5_bridge" / "unified_observer_signal.csv"
    out_repo = root / "data" / "shadow_observer" / "stage124c_unified_observer_signal_overlay_preview.csv"
    out_report = report_dir / "stage124c_unified_observer_signal_overlay_preview.csv"
    if not src.exists():
        empty_rows = [{
            "source_unified_csv": str(src),
            "overlay_status": "SOURCE_UNIFIED_CSV_NOT_FOUND",
            "stage124_rule_id": shadow_row.get("rule_id", ""),
            "combo_active_update": "false",
        }]
        write_csv(out_repo, empty_rows)
        write_csv(out_report, empty_rows)
        return {"combo_overlay_preview_repo": str(out_repo), "combo_overlay_preview_report": str(out_report), "combo_overlay_source_found": "false"}
    base = read_csv(src)
    if base.empty:
        empty_rows = [{
            "source_unified_csv": str(src),
            "overlay_status": "SOURCE_UNIFIED_CSV_EMPTY_OR_UNREADABLE",
            "stage124_rule_id": shadow_row.get("rule_id", ""),
            "combo_active_update": "false",
        }]
        write_csv(out_repo, empty_rows)
        write_csv(out_report, empty_rows)
        return {"combo_overlay_preview_repo": str(out_repo), "combo_overlay_preview_report": str(out_report), "combo_overlay_source_found": "false"}
    row = base.iloc[0].to_dict()
    try:
        old_count = int(float(row.get("rule_count", 7)))
    except Exception:
        old_count = 7
    row.update({
        "stage124c_overlay_status": "PREVIEW_ONLY_NOT_ACTIVE_COMBO_UPDATE",
        "stage124c_rule_id": shadow_row.get("rule_id", ""),
        "stage124c_source_rule_id": shadow_row.get("source_rule_id", ""),
        "stage124c_rule_status": shadow_row.get("rule_status", ""),
        "stage124c_signal_active": "false",
        "stage124c_allow_trading": "false",
        "stage124c_candidate_only": shadow_row.get("candidate_only", "true"),
        "stage124c_last_signal_time_utc": shadow_row.get("last_signal_time_utc", ""),
        "stage124c_cost10_mean_bps": shadow_row.get("cost10_mean_bps", ""),
        "stage124c_cost10_hit_rate": shadow_row.get("cost10_hit_rate", ""),
        "stage124c_combo_merge_recommendation": "MERGE_AS_SHADOW_FIELD_AFTER_COMBO_EA_READINESS_PATCH",
        "stage124c_preview_rule_count_if_merged": str(old_count + 1),
    })
    write_csv(out_repo, [row])
    write_csv(out_report, [row])
    return {"combo_overlay_preview_repo": str(out_repo), "combo_overlay_preview_report": str(out_report), "combo_overlay_source_found": "true"}

def write_ea_files(root: Path, paths: Dict[str, Path], mt5_experts: Path, write_mql5_ea: bool) -> Dict[str, str]:
    repo_ea = paths["mql5_repo_dir"] / "XAUUSD_Stage124_ShadowObserverOnly.mq5"
    ensure_dir(repo_ea.parent)
    repo_ea.write_text(EA_SAFE_MQL5, encoding="utf-8")
    out = {"repo_ea_source": str(repo_ea), "mt5_ea_source": ""}
    if write_mql5_ea:
        ensure_dir(mt5_experts)
        dst = mt5_experts / repo_ea.name
        shutil.copy2(repo_ea, dst)
        out["mt5_ea_source"] = str(dst)
    return out


def available_col(df: pd.DataFrame, names: Sequence[str]) -> Optional[str]:
    return first_existing_col(df, names)


def quantile_threshold(s: pd.Series, q: float) -> float:
    vals = coerce_num(s).dropna()
    if vals.empty:
        return math.nan
    return float(vals.quantile(q))


def build_next_discovery(dataset: pd.DataFrame, horizon_hours: int) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run a compact next frontier scan from currently available data.

    This is intentionally conservative: it uses only columns available in the joined Stage117 panel,
    and treats direct DXY/WGC central-bank gaps through source-mode aliases/proxies.
    """
    ds = normalize_columns(dataset)
    if ds.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    time_col = detect_time_col(ds)
    ret_col = detect_return_col(ds, horizon_hours)
    if not time_col or not ret_col:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    ds["_time"] = to_utc_naive(ds[time_col])
    ds["_ret"] = coerce_num(ds[ret_col])
    ds = ds.dropna(subset=["_time", "_ret"]).sort_values("_time")
    if ds.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # Time splits: same simple selection/validation/tail scheme.
    n = len(ds)
    sel_end = int(n * 0.60)
    val_end = int(n * 0.80)
    ds["_split"] = "tail"
    ds.iloc[:sel_end, ds.columns.get_loc("_split")] = "selection"
    ds.iloc[sel_end:val_end, ds.columns.get_loc("_split")] = "validation"

    aliases = {
        "real_yield": ["real_yield_10y", "dfii10", "real_yield", "real_yield_change_20d"],
        "dollar": ["dollar_pressure_index", "dollar_pressure", "broad_dollar_dtwexbgs", "dtwexbgs", "dtwexbgs_close", "dxy_close", "dxy"],
        "vix": ["vixcls", "vix", "vix_close"],
        "hy": ["bamlh0a0hym2", "hy_oas", "high_yield_oas"],
        "cot_z": ["cot_z", "mm_net_z", "money_manager_net_z", "cot_gold_mm_net_z"],
        "cot_decrowd": ["cot_z_change_4w", "mm_net_z_change_4w", "cot_decrowding", "cot_z_delta_4w"],
        "spdr": ["spdr_flow_20d", "spdr_gld_tonnes_change_20d", "spdr_value", "gld_tonnes", "spdr_gld"],
        "census": ["census_marts_yoy", "census_resconst_yoy", "census_activity_proxy", "retail_sales_proxy"],
        "event": ["event_proximity_score", "fred_release_event_near", "fomc_event_near", "treasury_auction_near"],
    }
    cols = {k: available_col(ds, v) for k, v in aliases.items()}

    thresholds = []
    for name, col in cols.items():
        if col:
            thresholds.append({
                "feature_group": name,
                "column": col,
                "q20": quantile_threshold(ds.loc[ds["_split"] == "selection", col], 0.20),
                "q40": quantile_threshold(ds.loc[ds["_split"] == "selection", col], 0.40),
                "q60": quantile_threshold(ds.loc[ds["_split"] == "selection", col], 0.60),
                "q80": quantile_threshold(ds.loc[ds["_split"] == "selection", col], 0.80),
            })

    def z(col: Optional[str]) -> pd.Series:
        if not col or col not in ds.columns:
            return pd.Series([math.nan] * len(ds), index=ds.index, dtype="float64")
        return coerce_num(ds[col])

    rules = []
    # Feature-driven candidate families. Each requires available cols and uses selection quantiles only.
    # Low real yield + dollar relief + SPDR support.
    ry = z(cols["real_yield"]); dol = z(cols["dollar"]); spdr = z(cols["spdr"]); cot = z(cols["cot_z"]); cotd = z(cols["cot_decrowd"]); vix = z(cols["vix"]); hy = z(cols["hy"]); census = z(cols["census"]); event = z(cols["event"])
    sel = ds["_split"] == "selection"
    def q(series: pd.Series, qq: float) -> float:
        vals = coerce_num(series[sel]).dropna()
        if vals.empty:
            return math.nan
        return float(vals.quantile(qq))
    def oknum(x: float) -> bool:
        return not math.isnan(x)
    qvals = {
        "ry40": q(ry, .40), "ry20": q(ry, .20), "dol40": q(dol, .40), "dol20": q(dol, .20), "dol60": q(dol, .60),
        "spdr60": q(spdr, .60), "spdr40": q(spdr, .40), "cot60": q(cot, .60), "cot40": q(cot, .40),
        "cotd40": q(cotd, .40), "vix60": q(vix, .60), "hy60": q(hy, .60), "census40": q(census, .40), "event60": q(event, .60),
    }

    masks: Dict[str, Tuple[pd.Series, str, List[str]]] = {}
    if cols["real_yield"] and cols["dollar"] and oknum(qvals["ry40"]) and oknum(qvals["dol40"]):
        masks["S124_01_RY_DOLLAR_RELIEF_CONTINUATION"] = ((ry <= qvals["ry40"]) & (dol <= qvals["dol40"]), "real-yield low/relief + dollar pressure relief", [cols["real_yield"], cols["dollar"]])
    if cols["spdr"] and cols["real_yield"] and oknum(qvals["spdr60"]) and oknum(qvals["ry40"]):
        masks["S124_02_SPDR_SUPPORT_RY_RELIEF"] = ((spdr >= qvals["spdr60"]) & (ry <= qvals["ry40"]), "SPDR support + real-yield relief", [cols["spdr"], cols["real_yield"]])
    if cols["cot_z"] and cols["dollar"] and oknum(qvals["cot60"]) and oknum(qvals["dol40"]):
        masks["S124_03_NOT_CROWDED_DOLLAR_RELIEF"] = ((cot <= qvals["cot60"]) & (dol <= qvals["dol40"]), "COT not crowded + dollar relief", [cols["cot_z"], cols["dollar"]])
    if cols["vix"] and cols["dollar"] and oknum(qvals["vix60"]) and oknum(qvals["dol60"]):
        masks["S124_04_SAFE_HAVEN_VIX_UP_DOLLAR_NOT_STRONG"] = ((vix >= qvals["vix60"]) & (dol <= qvals["dol60"]), "safe-haven volatility without strong dollar pressure", [cols["vix"], cols["dollar"]])
    if cols["census"] and cols["real_yield"] and oknum(qvals["census40"]) and oknum(qvals["ry40"]):
        masks["S124_05_CENSUS_SLOWDOWN_RY_RELIEF"] = ((census <= qvals["census40"]) & (ry <= qvals["ry40"]), "Census activity slowdown proxy + real-yield relief", [cols["census"], cols["real_yield"]])
    if cols["event"] and cols["real_yield"] and oknum(qvals["event60"]) and oknum(qvals["ry40"]):
        masks["S124_06_EVENT_WINDOW_RY_RELIEF"] = ((event >= qvals["event60"]) & (ry <= qvals["ry40"]), "official event-window + real-yield relief", [cols["event"], cols["real_yield"]])
    if cols["hy"] and cols["vix"] and oknum(qvals["hy60"]) and oknum(qvals["vix60"]):
        masks["S124_07_CREDIT_VOL_STRESS_SAFE_HAVEN"] = ((hy >= qvals["hy60"]) & (vix >= qvals["vix60"]), "credit/volatility stress safe-haven", [cols["hy"], cols["vix"]])

    rows = []
    selected_events = []
    for rule, (mask, thesis, req_cols) in masks.items():
        mask = mask.fillna(False)
        for split in ["selection", "validation", "tail"]:
            sub = ds[(ds["_split"] == split) & mask]
            vals = sub["_ret"].dropna()
            rows.append({
                "rule_id": rule,
                "thesis": thesis,
                "required_cols": ";".join(req_cols),
                "split": split,
                "events": int(len(sub)),
                "mean_bps": round(float(vals.mean()), 4) if len(vals) else "",
                "hit_rate": round(float((vals > 0).mean()), 4) if len(vals) else "",
                "cost10_mean_bps": round(float(vals.mean()) - 10.0, 4) if len(vals) else "",
                "available_feature_count": len(req_cols),
            })
        tail = ds[(ds["_split"] == "tail") & mask]
        val = ds[(ds["_split"] == "validation") & mask]
        sel_sub = ds[(ds["_split"] == "selection") & mask]
        tv = tail["_ret"].dropna(); vv = val["_ret"].dropna(); sv = sel_sub["_ret"].dropna()
        if len(sv) >= 30 and len(vv) >= 15 and len(tv) >= 10:
            tail_cost = float(tv.mean()) - 10.0
            val_cost = float(vv.mean()) - 10.0
            tail_hit_cost = float(((tv - 10) > 0).mean())
            if val_cost > 0 and tail_cost > 0 and tail_hit_cost >= 0.50:
                selected_events.append({
                    "rule_id": rule,
                    "thesis": thesis,
                    "selection_events": int(len(sel_sub)),
                    "validation_events": int(len(val)),
                    "tail_events": int(len(tail)),
                    "validation_cost10_mean_bps": round(val_cost, 4),
                    "tail_cost10_mean_bps": round(tail_cost, 4),
                    "tail_cost10_hit_rate": round(tail_hit_cost, 4),
                    "required_cols": ";".join(req_cols),
                    "decision": "STAGE125_REVIEW_QUEUE_NO_ORDER",
                })

    feature_plan = []
    for group, col in cols.items():
        if col:
            status = "AVAILABLE"
            alt = "use_current_stage117_joined_feature"
        elif group == "dollar":
            status = "MISSING_DIRECT_USE_PROXY"
            alt = "FRED DTWEXBGS / dollar_pressure_index / Fed H.10 broad dollar index"
        elif group == "event":
            status = "MISSING_OR_SPARSE_USE_OFFICIAL_BACKBONE"
            alt = "FRED releases/dates + FOMC calendar + Treasury auctions + BLS/BEA/Census datasets"
        elif group == "census":
            status = "MISSING_IN_JOINED_PANEL_USE_STAGE116C_RAW"
            alt = "normalize Census EITS marts/ftd/resconst/ressales yearly JSONs into daily/monthly activity proxy"
        else:
            status = "MISSING"
            alt = "not used in this scan"
        feature_plan.append({"feature_group": group, "selected_column": col or "", "status": status, "alternative_path": alt})

    return pd.DataFrame(rows), pd.DataFrame(selected_events), pd.DataFrame(feature_plan + thresholds)


def safe_copy(src: Path, dst: Path) -> str:
    ensure_dir(dst.parent)
    shutil.copy2(src, dst)
    return str(dst)


def run(root: Path, mt5_files: Path, mt5_experts: Path, write_shadow_mt5_csv: bool, write_mql5_ea: bool, horizon_hours: int) -> dict:
    paths = load_stage_paths(root)
    report_dir = paths["report_dir"]
    ensure_dir(report_dir)
    ensure_dir(paths["shadow_dir"])

    stage123_summary = read_json(paths["stage123_dir"] / "stage123_static_replay_shadow_observer_package_summary.json")
    stage121_summary = read_json(paths["stage121_dir"] / "stage121_dry_run_observer_preflight_summary.json")
    stage120_summary = read_json(root / "reports" / "stage120_observer_design_review" / "stage120_observer_design_review_summary.json")
    events = read_csv(paths["stage121_dir"] / "stage121_dry_run_signal_events.csv")
    preflight_metrics = read_csv(paths["stage121_dir"] / "stage121_preflight_metrics.csv")
    dataset = load_stage117_dataset(root, paths)

    joined_events, return_col, replay_warnings = join_events_to_returns(events, dataset, horizon_hours)
    rule_id = "S120_01_SPDR_FLOW_SUPPORT_MACRO_RELIEF_OBSERVER_DESIGN"
    if not preflight_metrics.empty:
        rid_col = first_existing_col(preflight_metrics, ["rule_id", "observer_rule_id"])
        if rid_col:
            rule_id = str(preflight_metrics.iloc[0].get(rid_col, rule_id))

    metrics = compute_replay_metrics(rule_id, joined_events, return_col, horizon_hours)
    time_col = detect_time_col(joined_events)
    last_signal_time = ""
    if time_col and not joined_events.empty:
        times = to_utc_naive(joined_events[time_col]).dropna()
        if len(times):
            last_signal_time = times.max().isoformat() + "Z"

    generated = utc_now()
    rule_meta = {
        "source_rule_id": "S117_06_SPDR_FLOW_SUPPORT_MACRO_RELIEF",
        "candidate_only": True,
        "stage116_spdr_status": stage120_summary.get("spdr_status", "VALIDATED_CANDIDATE"),
        "dxy_source": "FRED_DTWEXBGS_FALLBACK_OR_DOLLAR_PRESSURE_PROXY",
    }
    summary_stub = {"generated_utc": generated}
    shadow_row = build_shadow_csv_row(summary_stub, metrics, rule_meta, last_signal_time)

    shadow_csv_repo = paths["shadow_dir"] / "stage124_xauusd_shadow_observer_signal.csv"
    shadow_csv_report = report_dir / "stage124_xauusd_shadow_observer_signal.csv"
    write_csv(shadow_csv_repo, [shadow_row])
    write_csv(shadow_csv_report, [shadow_row])
    mt5_shadow_csv = ""
    mt5_shadow_kv_repo = paths["shadow_dir"] / "stage124c_xauusd_shadow_observer_signal_mt5_kv.csv"
    mt5_shadow_kv_report = report_dir / "stage124c_xauusd_shadow_observer_signal_mt5_kv.csv"
    kv_rows = build_mt5_shadow_kv_rows(shadow_row)
    write_kv_csv(mt5_shadow_kv_repo, kv_rows)
    write_kv_csv(mt5_shadow_kv_report, kv_rows)
    if write_shadow_mt5_csv:
        mt5_shadow_csv = write_kv_csv(mt5_files / "xauusd_stage124_shadow_observer_signal.csv", kv_rows)

    combo_overlay_paths = write_combo_overlay_preview(root, report_dir, shadow_row)

    ea_paths = write_ea_files(root, paths, mt5_experts, write_mql5_ea)

    replay_metrics_path = write_csv(report_dir / "stage124_consolidated_replay_metrics.csv", [metrics])
    replay_events_path = str(report_dir / "stage124_consolidated_replay_events.csv")
    ensure_dir(Path(replay_events_path).parent)
    joined_events.to_csv(replay_events_path, index=False)
    year_conc, year_rows = concentration_by_year(joined_events[time_col]) if time_col else (0.0, [])
    year_distribution_path = write_csv(report_dir / "stage124_year_distribution.csv", year_rows)

    discovery_metrics, discovery_selected, feature_plan = build_next_discovery(dataset, horizon_hours)
    discovery_metrics_path = str(report_dir / "stage124_next_frontier_discovery_metrics.csv")
    selected_path = str(report_dir / "stage124_selected_for_stage125.csv")
    feature_plan_path = str(report_dir / "stage124_data_alternative_and_feature_plan.csv")
    discovery_metrics.to_csv(discovery_metrics_path, index=False)
    discovery_selected.to_csv(selected_path, index=False)
    feature_plan.to_csv(feature_plan_path, index=False)

    no_write_rows = [
        {"surface": "orders", "status": "BLOCKED", "note": "No automated/paper/live order in Stage124."},
        {"surface": "EA trading", "status": "BLOCKED", "note": "MQL5 source is observer-only and contains no trade library or order function."},
        {"surface": "active observer", "status": "NOT_UPDATED", "note": "Shadow CSV only; active observer unchanged."},
        {"surface": "unified observer combo", "status": "PREVIEW_ONLY_NOT_UPDATED", "note": "Overlay preview is generated, but Stage109/Stage108 active combo CSV is not overwritten."},
        {"surface": "MT5 MQL5/Files", "status": "OPTIONAL_SHADOW_KEY_VALUE_CSV_ONLY" if write_shadow_mt5_csv else "NOT_WRITTEN", "note": "Only xauusd_stage124_shadow_observer_signal.csv if explicitly requested; key/value format for EA reader."},
    ]
    no_write_manifest = write_csv(report_dir / "stage124_governance_no_order_manifest.csv", no_write_rows)

    pass_replay = metrics.get("static_replay_status") == "PASS_STATIC_REPLAY"
    selected_count = int(len(discovery_selected)) if not discovery_selected.empty else 0
    status = STATUS_OK if pass_replay else STATUS_WATCH
    decision = DECISION_OK if pass_replay else DECISION_WATCH
    summary = {
        "stage": STAGE,
        "generated_utc": generated,
        "status": status,
        "decision": decision,
        "classification": "CONSOLIDATED_SHADOW_CSV_EA_AND_DISCOVERY_NO_ORDER",
        "hard_blocks": HARD_BLOCKS,
        "root": str(root),
        "stage123_prior_status": stage123_summary.get("status", ""),
        "stage123_prior_decision": stage123_summary.get("decision", ""),
        "stage121_signal_rows_seen": int(len(events)),
        "dataset_rows": int(len(dataset)),
        "return_col_detected": return_col or "",
        "replay_status": metrics.get("static_replay_status"),
        "replay_block_reasons": metrics.get("block_reasons", ""),
        "replay_warnings": replay_warnings,
        "shadow_csv_repo": str(shadow_csv_repo),
        "shadow_csv_report": str(shadow_csv_report),
        "mt5_shadow_csv_written": bool(write_shadow_mt5_csv),
        "mt5_shadow_csv": mt5_shadow_csv,
        "mt5_shadow_csv_format": "KEY_VALUE_TWO_COLUMN_NO_HEADER",
        "mt5_shadow_kv_repo": str(mt5_shadow_kv_repo),
        "mt5_shadow_kv_report": str(mt5_shadow_kv_report),
        "combo_integration_recommendation": "MERGE_STAGE124_AS_8TH_SHADOW_RULE_IN_UNIFIED_COMBO_AFTER_COMBO_EA_PATCH",
        **combo_overlay_paths,
        "repo_ea_source": ea_paths["repo_ea_source"],
        "mt5_ea_written": bool(write_mql5_ea),
        "mt5_ea_source": ea_paths.get("mt5_ea_source", ""),
        "next_frontier_candidate_metric_rows": int(len(discovery_metrics)),
        "selected_for_stage125_count": selected_count,
        "replay_metrics": replay_metrics_path,
        "replay_events": replay_events_path,
        "year_distribution": year_distribution_path,
        "next_frontier_discovery_metrics": discovery_metrics_path,
        "selected_for_stage125": selected_path,
        "data_alternative_and_feature_plan": feature_plan_path,
        "governance_no_order_manifest": no_write_manifest,
        "next": [
            "Review Stage124 replay_status and selected_for_stage125 in one pass.",
            "If replay_status is PASS_STATIC_REPLAY, shadow CSV/EA-safe observer artifacts are ready for observation only, not trading.",
            "Use Stage124 selected_for_stage125 to continue discovery; do not create another micro-stage before reading the consolidated outputs.",
        ],
    }
    summary_path = write_json(report_dir / "stage124_consolidated_shadow_csv_ea_and_frontier_discovery_summary.json", summary)
    report_md = report_dir / "stage124_consolidated_shadow_csv_ea_and_frontier_discovery_report.md"
    report_md.write_text(
        f"# {STAGE}\n\n"
        f"Status: {status}\n\nDecision: {decision}\n\n"
        f"Replay status: {metrics.get('static_replay_status')}\n\n"
        f"Return column: {return_col or 'NOT_DETECTED'}\n\n"
        f"Shadow CSV: {shadow_csv_repo}\n\n"
        f"EA source: {ea_paths['repo_ea_source']}\n\n"
        f"MT5 shadow CSV format: KEY_VALUE_TWO_COLUMN_NO_HEADER\n\n"
        f"Combo overlay preview: {combo_overlay_paths.get('combo_overlay_preview_repo','')}\n\n"
        f"Selected Stage125 candidates: {selected_count}\n\n"
        "This stage is consolidated by design: CSV/EA-safe shadow artifacts and next discovery are produced in one run. No order surfaces are touched.\n",
        encoding="utf-8",
    )
    summary["summary_json"] = summary_path
    summary["report_md"] = str(report_md)
    write_json(report_dir / "stage124_consolidated_shadow_csv_ea_and_frontier_discovery_summary.json", summary)
    print(f"{STAGE} | status={status} | decision={decision} | replay={metrics.get('static_replay_status')} | selected_stage125={selected_count}")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/Users/vahid/Desktop/xauusd-trader")
    ap.add_argument("--mt5-files", default=MT5_FILES_DEFAULT)
    ap.add_argument("--mt5-experts", default=MT5_EXPERTS_DEFAULT)
    ap.add_argument("--write-shadow-mt5-csv", action="store_true", help="Copy shadow-only CSV to MT5 MQL5/Files. No order signal; allow_trading=false.")
    ap.add_argument("--write-mql5-ea", action="store_true", help="Copy observer-only no-trade EA source to MT5 MQL5/Experts.")
    ap.add_argument("--horizon-hours", type=int, default=120)
    args = ap.parse_args()
    run(Path(args.root).expanduser(), Path(args.mt5_files).expanduser(), Path(args.mt5_experts).expanduser(), args.write_shadow_mt5_csv, args.write_mql5_ea, args.horizon_hours)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
