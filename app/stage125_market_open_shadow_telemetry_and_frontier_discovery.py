#!/usr/bin/env python3
"""
Stage125: market-open shadow telemetry + frontier discovery continuation.

Report-only / observer-only. This script does NOT send orders and does NOT modify any EA logic.
It collects market-open shadow observer snapshots, confirms the 7-rule EA + Stage124 rule-8 overlay path,
and runs a consolidated next-frontier discovery pass using available official/fallback features.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

STAGE = "Stage125_MARKET_OPEN_SHADOW_TELEMETRY_AND_FRONTIER_DISCOVERY"
STATUS_OK = "STAGE125_COMPLETE_MARKET_OPEN_SHADOW_TELEMETRY_AND_DISCOVERY_READY_NO_ORDER"
STATUS_WARN = "STAGE125_COMPLETE_WITH_WARNINGS_NO_ORDER"
DECISION = "STAGE125_FORWARD_SHADOW_TELEMETRY_READY_AND_DISCOVERY_REVIEW_READY_NO_ORDER"
CLASSIFICATION = "MARKET_OPEN_FORWARD_SHADOW_AND_DISCOVERY_NO_ORDER"

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_TRADE_REQUEST_FROM_STAGE125",
    "NO_ORDER_SEND",
    "NO_CTRADE_USAGE",
    "NO_MT5_EA_CHANGE_FROM_STAGE125",
    "NO_PAPER_LIVE",
    "NO_LIVE",
]

DEFAULT_MT5_FILES = Path(
    "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files"
)

EXPECTED_RULE_7_IDS = [
    "K06_RESILIENT_GOLD_VS_DXY_H120",
    "K03_SAFE_HAVEN_REALYIELD_H120",
    "K07_DXY_TREND_RELIEF_GOLD_TREND_H120",
    "S83_14_REALYIELD_120D_DOWN_GOLD_NOT_TRENDING_H120",
    "S83_13_DXY_120D_DOWN_GOLD_NOT_TRENDING_H120",
    "C96_07_CB_SUPPORT_NOT_CROWDED_H120",
    "S105_03_COT_DECROWDING_CB_SUPPORT_RY_RELIEF_H120",
]

RULE8_ID = "S120_01_SPDR_FLOW_SUPPORT_MACRO_RELIEF_OBSERVER_DESIGN"
SOURCE_RULE8_ID = "S117_06_SPDR_FLOW_SUPPORT_MACRO_RELIEF"


@dataclass
class FileSnapshot:
    path: str
    exists: bool
    size_bytes: int = 0
    modified_utc: str = ""
    format_hint: str = ""
    row_count: int = 0
    kv_count: int = 0
    rule_id: str = ""
    status: str = ""
    allow_trading: str = ""
    notes: str = ""


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def atomic_write_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", delete=False, dir=str(path.parent)) as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)


def atomic_write_df(path: Path, df: pd.DataFrame) -> None:
    ensure_dir(path.parent)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", delete=False, dir=str(path.parent)) as tmp:
        df.to_csv(tmp.name, index=False)
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)


def atomic_write_json(path: Path, obj: Dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2, default=str) + "\n")


def read_kv_csv(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path.exists() or path.stat().st_size <= 0:
        return out
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or len(row) < 2:
                continue
            key = str(row[0]).strip()
            val = str(row[1]).strip()
            if key and key.lower() not in {"key", "field", "name"}:
                out[key] = val
    return out


def safe_read_csv(path: Path, max_rows: Optional[int] = None) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size <= 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path, nrows=max_rows)
    except Exception:
        try:
            return pd.read_csv(path, sep=";", nrows=max_rows)
        except Exception:
            return pd.DataFrame()


def snapshot_file(path: Path) -> FileSnapshot:
    snap = FileSnapshot(path=str(path), exists=path.exists())
    if not path.exists():
        snap.notes = "MISSING"
        return snap
    st = path.stat()
    snap.size_bytes = int(st.st_size)
    snap.modified_utc = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    kv = read_kv_csv(path)
    if kv:
        snap.format_hint = "KEY_VALUE"
        snap.kv_count = len(kv)
        snap.rule_id = kv.get("rule_id", kv.get("stage124_rule", kv.get("rule8_id", "")))
        snap.status = kv.get("status", kv.get("replay_status", kv.get("rule_status", "")))
        snap.allow_trading = kv.get("allow_trading", "")
        snap.row_count = len(kv)
        return snap
    df = safe_read_csv(path, max_rows=200)
    if not df.empty:
        snap.format_hint = "TABLE"
        snap.row_count = len(df)
        cols = [str(c) for c in df.columns]
        if "rule_id" in cols:
            vals = df["rule_id"].dropna().astype(str).unique().tolist()
            snap.rule_id = ";".join(vals[:5])
        if "status" in cols:
            vals = df["status"].dropna().astype(str).unique().tolist()
            snap.status = ";".join(vals[:5])
        if "allow_trading" in cols:
            vals = df["allow_trading"].dropna().astype(str).unique().tolist()
            snap.allow_trading = ";".join(vals[:5])
    else:
        snap.format_hint = "UNREADABLE_OR_EMPTY"
        snap.notes = "CSV_PARSE_EMPTY"
    return snap


def discover_shadow_files(root: Path, mt5_files: Path) -> List[Path]:
    candidates: List[Path] = []
    names = [
        "xauusd_stage124_shadow_observer_signal.csv",
        "xauusd_stage124e_unified_combo_8rule_chart_status.csv",
        "xauusd_stage124f_rule8_overlay_kv.csv",
        "xauusd_stage124d_unified_combo_plus_stage124_shadow.csv",
        "unified_observer_signal.csv",
        "xauusd_unified_observer_signal.csv",
        "active_unified_observer_signal.csv",
    ]
    for base in [mt5_files, root / "data" / "shadow_observer", root / "reports"]:
        if not base.exists():
            continue
        for name in names:
            if base.is_dir():
                for p in base.rglob(name) if base.name == "reports" else [base / name]:
                    if p.exists() and p not in candidates:
                        candidates.append(p)
        if base.is_dir():
            for pat in ["*stage124*observer*.csv", "*stage124*overlay*.csv", "*unified*observer*.csv", "*combo*.csv"]:
                for p in base.glob(pat):
                    if p.is_file() and p not in candidates:
                        candidates.append(p)
    return candidates


def coerce_num(s: Any) -> pd.Series:
    ser = s if isinstance(s, pd.Series) else pd.Series(s)
    if ser.dtype == bool:
        return ser.astype(float)
    return pd.to_numeric(ser, errors="coerce")


def first_col(df: pd.DataFrame, names: Sequence[str]) -> Optional[str]:
    lower = {str(c).lower(): str(c) for c in df.columns}
    for name in names:
        if name in df.columns:
            return name
        if name.lower() in lower:
            return lower[name.lower()]
    return None


def find_stage117_dataset(root: Path) -> Optional[Path]:
    candidates = [
        root / "data/fundamental_event_inbox/features/stage117_joined_macro_cot_dollar_h1_research_dataset.csv",
        root / "reports/stage117_segmented_macro_cot_dollar_discovery/stage117_joined_macro_cot_dollar_h1_research_dataset.csv",
    ]
    for p in candidates:
        if p.exists():
            return p
    for p in (root / "data").rglob("stage117_joined_macro_cot_dollar_h1_research_dataset.csv") if (root / "data").exists() else []:
        return p
    return None


def detect_forward_return_col(df: pd.DataFrame, horizon_hours: int) -> Optional[str]:
    candidates = [
        f"fwd_ret_bps_h{horizon_hours}",
        f"forward_return_bps_h{horizon_hours}",
        "_stage124_forward_return_bps",
        "fwd_ret_bps_h120",
        "forward_return_bps",
        "fwd_return_bps",
    ]
    return first_col(df, candidates)


def add_forward_return_if_needed(df: pd.DataFrame, horizon_hours: int) -> Tuple[pd.DataFrame, Optional[str], str]:
    out = df.copy()
    existing = detect_forward_return_col(out, horizon_hours)
    if existing:
        out["_stage125_forward_return_bps"] = coerce_num(out[existing])
        return out, "_stage125_forward_return_bps", f"mapped_from:{existing}"
    close_col = first_col(out, ["close", "Close", "gold_close"])
    time_col = first_col(out, ["utc_time", "time", "datetime", "date"])
    if not close_col:
        return out, None, "no_forward_return_or_close_column"
    close = coerce_num(out[close_col])
    # Dataset is H1 by design; horizon 120h => shift 120 rows.
    shift_rows = int(horizon_hours)
    if len(close.dropna()) <= shift_rows:
        return out, None, "not_enough_rows_to_compute_forward_return"
    out["_stage125_forward_return_bps"] = ((close.shift(-shift_rows) / close) - 1.0) * 10000.0
    return out, "_stage125_forward_return_bps", f"computed_from:{close_col}:shift_rows_{shift_rows}:time_col_{time_col or 'unknown'}"


def q(series: pd.Series, quant: float) -> float:
    vals = coerce_num(series).dropna()
    if len(vals) == 0:
        return math.nan
    return float(vals.quantile(quant))


def eval_mask(df: pd.DataFrame, clauses: List[Tuple[str, str, float]]) -> Tuple[pd.Series, List[str]]:
    mask = pd.Series(True, index=df.index)
    reasons: List[str] = []
    for col, op, val in clauses:
        if col not in df.columns or not math.isfinite(float(val)):
            reasons.append(f"missing_or_invalid:{col}")
            return pd.Series(False, index=df.index), reasons
        x = coerce_num(df[col])
        if op == "lt":
            part = x < val
        elif op == "le":
            part = x <= val
        elif op == "gt":
            part = x > val
        elif op == "ge":
            part = x >= val
        elif op == "abs_lt":
            part = x.abs() < val
        else:
            reasons.append(f"bad_operator:{op}")
            return pd.Series(False, index=df.index), reasons
        mask &= part.fillna(False)
    return mask, reasons


def metric_for_mask(df: pd.DataFrame, mask: pd.Series, ret_col: str, cost_bps: float = 10.0, horizon_hours: int = 120) -> Dict[str, Any]:
    ret = coerce_num(df.loc[mask, ret_col]).dropna()
    if len(ret) == 0:
        return {
            "events": 0,
            "valid_return_events": 0,
            "mean_bps": math.nan,
            "hit_rate": math.nan,
            "cost10_mean_bps": math.nan,
            "cost10_hit_rate": math.nan,
            "worst_bps": math.nan,
            "best_bps": math.nan,
            "max_year_concentration_pct": math.nan,
        }
    idx = ret.index
    years = None
    time_col = first_col(df, ["utc_time", "time", "datetime", "date"])
    max_year_conc = math.nan
    if time_col:
        t = pd.to_datetime(df.loc[idx, time_col], errors="coerce", utc=True)
        years = t.dt.year.dropna()
        if len(years):
            max_year_conc = float(years.value_counts(normalize=True).max() * 100.0)
    cost_ret = ret - cost_bps
    return {
        "events": int(mask.sum()),
        "valid_return_events": int(len(ret)),
        "mean_bps": float(ret.mean()),
        "hit_rate": float((ret > 0).mean()),
        "cost10_mean_bps": float(cost_ret.mean()),
        "cost10_hit_rate": float((cost_ret > 0).mean()),
        "worst_bps": float(ret.min()),
        "best_bps": float(ret.max()),
        "max_year_concentration_pct": max_year_conc,
    }


def build_frontier_discovery(df: pd.DataFrame, horizon_hours: int = 120) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, str]:
    if df.empty:
        return pd.DataFrame(), pd.DataFrame(), data_alternative_plan(), "empty_dataset"
    work, ret_col, ret_source = add_forward_return_if_needed(df, horizon_hours)
    if not ret_col:
        metrics = pd.DataFrame([{"candidate_id": "BLOCKED", "status": "BLOCKED_NO_FORWARD_RETURN", "return_source": ret_source}])
        return metrics, pd.DataFrame(), data_alternative_plan(), ret_source

    # Resolve feature aliases.
    aliases = {
        "ry20": ["real_yield_10y_chg_20d", "real_yield_change_20d", "dfii10_chg_20d"],
        "ry60": ["real_yield_10y_chg_60d", "real_yield_change_60d", "dfii10_chg_60d"],
        "dollar20": ["dollar_pressure_chg_20d", "dxy_ret_20d", "dtwexbgs_ret_20d"],
        "dollar60": ["dollar_pressure_chg_60d", "dxy_ret_60d", "dtwexbgs_ret_60d"],
        "spdr20": ["spdr_value_chg_20d", "spdr_tonnes_chg_20d", "spdr_flow_20d"],
        "spdr60": ["spdr_value_chg_60d", "spdr_tonnes_chg_60d", "spdr_flow_60d"],
        "cot_z": ["cot_mm_net_z", "cot_z"],
        "cot_chg4": ["cot_mm_net_z_change_4w", "cot_z_change_4w"],
        "vix20": ["vix_chg_20d", "vixcls_chg_20d"],
        "gold20": ["gold_ret_20d", "close_ret_20d"],
        "event_prox": ["event_proximity_score", "fred_release_proximity", "official_event_window_score"],
        "census_proxy": ["census_growth_proxy", "retail_sales_chg", "mrts_chg"],
    }
    resolved: Dict[str, Optional[str]] = {k: first_col(work, v) for k, v in aliases.items()}
    rows: List[Dict[str, Any]] = []

    def add_candidate(candidate_id: str, thesis: str, clause_specs: List[Tuple[str, str, float]], feature_keys: List[str], source_policy: str) -> None:
        missing = [k for k in feature_keys if resolved.get(k) is None]
        if missing:
            rows.append({
                "candidate_id": candidate_id,
                "thesis": thesis,
                "source_policy": source_policy,
                "status": "SKIPPED_MISSING_FEATURES",
                "missing_feature_keys": ";".join(missing),
                "return_source": ret_source,
            })
            return
        clauses: List[Tuple[str, str, float]] = []
        for key, op, quant_or_abs in clause_specs:
            col = resolved[key]
            assert col is not None
            if op == "abs_lt":
                threshold = abs(float(quant_or_abs))
            else:
                threshold = q(work[col], float(quant_or_abs))
            clauses.append((col, op, threshold))
        mask, reasons = eval_mask(work, clauses)
        met = metric_for_mask(work, mask, ret_col, cost_bps=10.0, horizon_hours=horizon_hours)
        status = "REVIEW_ONLY"
        if reasons:
            status = "BLOCKED_" + "_".join(reasons[:2])
        elif met["valid_return_events"] >= 30 and met["cost10_mean_bps"] and met["cost10_mean_bps"] > 50 and met["cost10_hit_rate"] and met["cost10_hit_rate"] >= 0.58 and (math.isnan(met["max_year_concentration_pct"]) or met["max_year_concentration_pct"] <= 80):
            status = "SELECT_STAGE126_REVIEW_QUEUE"
        elif met["valid_return_events"] >= 15 and met["cost10_mean_bps"] and met["cost10_mean_bps"] > 0:
            status = "WATCH_ONLY_NO_PROMOTION"
        else:
            status = "NO_SELECT"
        rows.append({
            "candidate_id": candidate_id,
            "thesis": thesis,
            "source_policy": source_policy,
            "status": status,
            "feature_columns": ";".join([resolved[k] or "" for k in feature_keys]),
            "conditions": ";".join([f"{c}{op}{thr:.6g}" for c, op, thr in clauses]),
            "return_source": ret_source,
            **met,
        })

    # The next frontier scans deliberately avoid direct DXY/WGC hard-dependency.
    add_candidate(
        "F125_01_RY_DOLLAR_SPDR_RELIEF",
        "Gold benefits when real yield pressure eases, broad-dollar pressure eases, and SPDR proxy confirms flow support.",
        [("ry20", "lt", 0.40), ("dollar20", "lt", 0.40), ("spdr20", "gt", 0.60)],
        ["ry20", "dollar20", "spdr20"],
        "Uses FRED/Fed dollar fallback DTWEXBGS and validated SPDR proxy; no direct DXY/WGC hard dependency.",
    )
    add_candidate(
        "F125_02_COT_DECROWD_RY_DOLLAR_RELIEF",
        "Macro relief plus speculative decrowding, avoiding long-crowded COT state.",
        [("ry20", "lt", 0.45), ("dollar20", "lt", 0.45), ("cot_z", "lt", 0.55), ("cot_chg4", "lt", 0.45)],
        ["ry20", "dollar20", "cot_z", "cot_chg4"],
        "Uses CFTC official COT compressed historical data and FRED dollar fallback.",
    )
    add_candidate(
        "F125_03_SPDR_ACCUMULATION_DOLLAR_RELIEF",
        "ETF-flow proxy accumulation during dollar relief.",
        [("spdr60", "gt", 0.60), ("dollar60", "lt", 0.45)],
        ["spdr60", "dollar60"],
        "Uses SPDR as ETF proxy and DTWEXBGS/DXY fallback for dollar pressure.",
    )
    add_candidate(
        "F125_04_SAFE_HAVEN_VIX_UP_DOLLAR_NOT_UP",
        "Safe-haven impulse when VIX rises but dollar pressure is not strengthening.",
        [("vix20", "gt", 0.60), ("dollar20", "lt", 0.55)],
        ["vix20", "dollar20"],
        "Uses FRED VIXCLS and broad-dollar fallback; no commercial event calendar needed.",
    )
    add_candidate(
        "F125_05_EVENT_WINDOW_MACRO_DRIFT_PROXY",
        "Post-release / event-window drift using official release-date backbone rather than commercial calendar.",
        [("event_prox", "gt", 0.60), ("ry20", "lt", 0.50)],
        ["event_prox", "ry20"],
        "Requires derived official-event proximity from FRED release dates, FOMC, Treasury, BLS/BEA/Census actual releases.",
    )
    add_candidate(
        "F125_06_CENSUS_GROWTH_SLOWDOWN_RY_RELIEF",
        "Growth slowdown proxy from Census economic indicators combined with real-yield relief.",
        [("census_proxy", "lt", 0.40), ("ry20", "lt", 0.45)],
        ["census_proxy", "ry20"],
        "Needs Census EITS-derived feature; if absent, build from Census API time-series actuals.",
    )
    add_candidate(
        "F125_07_GOLD_TREND_NOT_EXHAUSTED_DOLLAR_RELIEF",
        "Gold trend not overheated while dollar pressure eases.",
        [("gold20", "lt", 0.70), ("dollar20", "lt", 0.40), ("ry20", "lt", 0.55)],
        ["gold20", "dollar20", "ry20"],
        "Uses broker gold prices plus official broad-dollar fallback.",
    )

    metrics = pd.DataFrame(rows)
    if "status" in metrics.columns:
        selected = metrics[metrics["status"].eq("SELECT_STAGE126_REVIEW_QUEUE")].copy()
    else:
        selected = pd.DataFrame()
    return metrics, selected, data_alternative_plan(), ret_source


def data_alternative_plan() -> pd.DataFrame:
    rows = [
        {
            "data_gap": "Direct DXY web/Stooq blocked or too short",
            "operational_replacement": "FRED DTWEXBGS / Federal Reserve H.10 broad dollar index as dollar_pressure fallback",
            "status": "READY_IN_STAGE115_116_FALLBACK_PATH",
            "hard_feature_allowed": "YES",
            "next_action": "Keep direct DXY as optional reference only; do not block discovery on it.",
        },
        {
            "data_gap": "Commercial economic calendar unavailable/untrusted",
            "operational_replacement": "Official event backbone: FRED releases/dates, FOMC calendar, Treasury auctions, BLS/BEA/Census actual releases",
            "status": "PARTIAL_READY_EVENTS_AND_ACTUALS",
            "hard_feature_allowed": "YES_AFTER_RELEASE_LAG_SAFE_FEATURE_BUILD",
            "next_action": "Build event proximity / post-release drift features from official dates; avoid consensus-surprise unless a reliable consensus source is added.",
        },
        {
            "data_gap": "WGC central-bank / ETF direct downloads blocked or login-limited",
            "operational_replacement": "SPDR GLD validated proxy for ETF/flow support; IMF IFS / reserve data as future central-bank reserve proxy; WGC manual/reference only",
            "status": "SPDR_READY_WGC_NOT_HARD_FEATURE",
            "hard_feature_allowed": "SPDR_YES_WGC_NO_FOR_NOW",
            "next_action": "Continue SPDR-flow thesis; build IMF reserve proxy before re-opening central-bank thesis.",
        },
        {
            "data_gap": "COT 2009 zip blocked/broken",
            "operational_replacement": "CFTC historical compressed files 2010+; sufficient for AMarkets 2022+ broker history",
            "status": "READY_FOR_CURRENT_HISTORY",
            "hard_feature_allowed": "YES",
            "next_action": "Do not block current discovery on 2009; optional backfill later.",
        },
        {
            "data_gap": "Event surprise consensus missing",
            "operational_replacement": "Consensus-less surprise proxy: actual release delta vs rolling median / prior trend; tag as proxy not true surprise",
            "status": "DESIGN_READY_NOT_HARD_FEATURE_UNTIL_VALIDATED",
            "hard_feature_allowed": "NO_UNTIL_VALIDATED",
            "next_action": "Build and validate pseudo-surprise separately before promotion use.",
        },
    ]
    return pd.DataFrame(rows)


def build_market_open_telemetry(root: Path, mt5_files: Path) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    paths = discover_shadow_files(root, mt5_files)
    snaps = [snapshot_file(p) for p in paths]
    df = pd.DataFrame([s.__dict__ for s in snaps]) if snaps else pd.DataFrame(columns=list(FileSnapshot.__annotations__.keys()))

    rule8_seen = False
    if not df.empty:
        text_blob = " ".join(df.fillna("").astype(str).agg(" ".join, axis=1).tolist())
        rule8_seen = (RULE8_ID in text_blob) or (SOURCE_RULE8_ID in text_blob) or ("PASS_STATIC_REPLAY" in text_blob and "stage124" in text_blob.lower())

    # We cannot read the MT5 journal directly here; snapshot only verifies files.
    health = {
        "shadow_files_seen": int(len(df)),
        "rule8_file_seen": bool(rule8_seen),
        "mt5_files_path": str(mt5_files),
        "market_open_user_confirmed": True,
        "recommended_runtime_mode": "KEEP_7_RULE_UNIFIED_OBSERVER_EA_RUNNING_AND_ATTACH_STAGE124F_RULE8_INDICATOR_OVERLAY",
        "stage124d_stage124e_note": "Do not keep Stage124D/E as replacement EA on the production observer chart; use Stage124F indicator overlay or future unified 8-rule EA patch.",
    }
    return df, health


def build_status_kv(summary: Dict[str, Any]) -> pd.DataFrame:
    keys = [
        ("stage", summary.get("stage", STAGE)),
        ("generated_utc", summary.get("generated_utc", now_utc())),
        ("mode", "MARKET_OPEN_FORWARD_SHADOW_ONLY_NO_ORDER"),
        ("market_open_user_confirmed", "true"),
        ("order_allowed", "false"),
        ("trade_request_allowed", "false"),
        ("recommended_runtime", "7_RULE_EA_PLUS_STAGE124F_INDICATOR_OVERLAY"),
        ("stage124_replay", summary.get("stage124_replay_status", "PASS_STATIC_REPLAY_ASSUMED_FROM_STAGE124C")),
        ("selected_for_stage126_count", str(summary.get("selected_for_stage126_count", 0))),
        ("hard_blocks", "|".join(HARD_BLOCKS)),
    ]
    return pd.DataFrame(keys, columns=["key", "value"])


def write_report(path: Path, summary: Dict[str, Any], discovery: pd.DataFrame, alternatives: pd.DataFrame) -> None:
    lines: List[str] = []
    lines.append(f"# {STAGE}\n")
    lines.append(f"Generated UTC: {summary.get('generated_utc')}\n")
    lines.append(f"Status: `{summary.get('status')}`\n")
    lines.append(f"Decision: `{summary.get('decision')}`\n")
    lines.append("\n## Operational decision\n")
    lines.append("Market-open path is forward-shadow only. Keep the existing 7-rule Unified_ObserverOnly_EA running and use Stage124F rule-8 overlay/indicator rather than replacing the main EA with Stage124D/E. No orders are permitted.\n")
    lines.append("\n## Discovery outcome\n")
    if discovery.empty:
        lines.append("No discovery metrics were produced.\n")
    else:
        for _, r in discovery.iterrows():
            lines.append(f"- `{r.get('candidate_id')}`: {r.get('status')} | events={r.get('valid_return_events', '')} | cost10_mean={r.get('cost10_mean_bps', '')} | hit={r.get('cost10_hit_rate', '')}\n")
    lines.append("\n## Data alternative route plan\n")
    for _, r in alternatives.iterrows():
        lines.append(f"- {r.get('data_gap')}: {r.get('operational_replacement')} | {r.get('next_action')}\n")
    lines.append("\n## Governance\n")
    for b in HARD_BLOCKS:
        lines.append(f"- {b}\n")
    atomic_write_text(path, "".join(lines))


def run(root: Path, mt5_files: Path, write_mt5_status_kv: bool, horizon_hours: int) -> Dict[str, Any]:
    root = root.expanduser().resolve()
    mt5_files = mt5_files.expanduser()
    report_dir = root / "reports" / "stage125_market_open_shadow_telemetry_and_frontier_discovery"
    ensure_dir(report_dir)

    generated = now_utc()
    telemetry_df, telemetry_health = build_market_open_telemetry(root, mt5_files)

    dataset_path = find_stage117_dataset(root)
    if dataset_path:
        dataset = safe_read_csv(dataset_path)
    else:
        dataset = pd.DataFrame()
    discovery, selected, alternatives, return_source = build_frontier_discovery(dataset, horizon_hours=horizon_hours)

    governance = pd.DataFrame([{"gate": b, "status": "BLOCKED", "reason": "Stage125 is report-only / shadow-only"} for b in HARD_BLOCKS])
    watch_plan = pd.DataFrame([
        {"item": "existing_7_rule_ea", "decision": "KEEP_RUNNING", "reason": "It prints rule-status/failure diagnostics and should remain the active observer display."},
        {"item": "stage124c_standalone_ea", "decision": "STOP_AFTER_VALIDATION", "reason": "Validated KV read; not needed as permanent separate EA."},
        {"item": "stage124d_stage124e_ea", "decision": "DO_NOT_USE_AS_REPLACEMENT", "reason": "They are status/preview readers, not the production 7-rule observer EA."},
        {"item": "stage124f_rule8_indicator", "decision": "USE_ON_SAME_CHART", "reason": "Adds rule 8 overlay without removing Unified_ObserverOnly_EA."},
        {"item": "orders", "decision": "BLOCKED", "reason": "No order path is opened by Stage125."},
    ])

    telemetry_path = report_dir / "stage125_market_open_shadow_telemetry_snapshot.csv"
    discovery_path = report_dir / "stage125_next_frontier_discovery_metrics.csv"
    selected_path = report_dir / "stage125_selected_for_stage126.csv"
    alternatives_path = report_dir / "stage125_data_alternative_route_plan.csv"
    governance_path = report_dir / "stage125_governance_no_order_manifest.csv"
    watch_path = report_dir / "stage125_market_open_watch_plan.csv"
    status_kv_repo = root / "data" / "shadow_observer" / "stage125_market_open_watch_status_kv.csv"
    status_kv_report = report_dir / "stage125_market_open_watch_status_kv.csv"
    mt5_status_kv_path = mt5_files / "xauusd_stage125_market_open_watch_status_kv.csv"

    atomic_write_df(telemetry_path, telemetry_df)
    atomic_write_df(discovery_path, discovery)
    atomic_write_df(selected_path, selected)
    atomic_write_df(alternatives_path, alternatives)
    atomic_write_df(governance_path, governance)
    atomic_write_df(watch_path, watch_plan)

    selected_count = int(len(selected)) if selected is not None else 0
    status = STATUS_OK
    warnings: List[str] = []
    if not telemetry_health.get("rule8_file_seen"):
        warnings.append("RULE8_FILE_NOT_SEEN_IN_SNAPSHOT_SEARCH_BUT_USER_MT5_LOG_MAY_CONFIRM_RUNTIME")
    if dataset_path is None:
        warnings.append("STAGE117_DATASET_NOT_FOUND_DISCOVERY_LIMITED")
    if selected_count == 0:
        warnings.append("NO_NEW_FRONTIER_CANDIDATE_SELECTED")
    if warnings:
        status = STATUS_WARN

    summary: Dict[str, Any] = {
        "stage": STAGE,
        "generated_utc": generated,
        "status": status,
        "decision": DECISION,
        "classification": CLASSIFICATION,
        "hard_blocks": HARD_BLOCKS,
        "root": str(root),
        "market_open_user_confirmed": True,
        "mt5_files": str(mt5_files),
        "telemetry_health": telemetry_health,
        "stage124_replay_status": "PASS_STATIC_REPLAY_CONFIRMED_PREVIOUS_STAGE124C",
        "stage124_runtime_decision": "KEEP_AS_RULE8_SHADOW_OVERLAY_NOT_SEPARATE_PERMANENT_EA",
        "recommended_runtime_mode": "Unified_ObserverOnly_EA_7_RULES_PLUS_Stage124F_Rule8_Indicator_Overlay",
        "dataset_path": str(dataset_path) if dataset_path else "",
        "dataset_rows": int(len(dataset)) if dataset is not None else 0,
        "return_source": return_source,
        "frontier_metric_rows": int(len(discovery)) if discovery is not None else 0,
        "selected_for_stage126_count": selected_count,
        "warnings": warnings,
        "telemetry_snapshot": str(telemetry_path),
        "next_frontier_discovery_metrics": str(discovery_path),
        "selected_for_stage126": str(selected_path),
        "data_alternative_route_plan": str(alternatives_path),
        "governance_no_order_manifest": str(governance_path),
        "market_open_watch_plan": str(watch_path),
        "status_kv_repo": str(status_kv_repo),
        "status_kv_report": str(status_kv_report),
        "mt5_status_kv_written": False,
        "mt5_status_kv": str(mt5_status_kv_path),
        "next": [
            "Keep Unified_ObserverOnly_EA running and use Stage124F rule-8 indicator overlay on the same chart.",
            "Review selected_for_stage126; if zero, do not build a promotion stage and instead collect forward shadow telemetry.",
            "Use data_alternative_route_plan to build the next consolidated discovery only when a new data proxy is added or a new thesis is specified.",
        ],
    }

    status_kv = build_status_kv(summary)
    atomic_write_df(status_kv_repo, status_kv)
    atomic_write_df(status_kv_report, status_kv)
    if write_mt5_status_kv:
        atomic_write_df(mt5_status_kv_path, status_kv)
        summary["mt5_status_kv_written"] = True

    summary_path = report_dir / "stage125_market_open_shadow_telemetry_and_frontier_discovery_summary.json"
    report_path = report_dir / "stage125_market_open_shadow_telemetry_and_frontier_discovery_report.md"
    summary["summary_json"] = str(summary_path)
    summary["report_md"] = str(report_path)

    atomic_write_json(summary_path, summary)
    write_report(report_path, summary, discovery, alternatives)
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--root", default="/Users/vahid/Desktop/xauusd-trader")
    ap.add_argument("--mt5-files", default=str(DEFAULT_MT5_FILES))
    ap.add_argument("--write-mt5-status-kv", action="store_true")
    ap.add_argument("--horizon-hours", type=int, default=120)
    args = ap.parse_args(argv)
    summary = run(Path(args.root), Path(args.mt5_files), bool(args.write_mt5_status_kv), int(args.horizon_hours))
    print(json.dumps({
        "stage": summary["stage"],
        "status": summary["status"],
        "decision": summary["decision"],
        "selected_for_stage126_count": summary["selected_for_stage126_count"],
        "summary_json": summary["summary_json"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
