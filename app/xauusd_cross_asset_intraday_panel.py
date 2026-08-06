#!/usr/bin/env python3
from __future__ import annotations

import argparse
import calendar
import csv
import datetime as dt
import hashlib
import json
import math
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROGRAM = "XAUUSD_CROSS_ASSET_INTRADAY_PANEL_V1_2_SESSION_ELIGIBILITY_CONTRACT_REPAIR"
EXPORT_PROGRAMS = {"XAUUSD_CROSS_ASSET_INTRADAY_PANEL_V1", PROGRAM}
REPORT_REL = Path("reports/xauusd_cross_asset_intraday_panel")
MT5_EXPORT_REL = Path("XAUUSD_CROSS_ASSET_HISTORY")
REQUIRED_SYMBOLS = ["XAUUSD", "XAGUSD", "EURUSD", "USDJPY"]
OPTIONAL_SYMBOLS = ["S&P500", "WTI", "BRENT", "DXY"]
ALL_SYMBOLS = REQUIRED_SYMBOLS + OPTIONAL_SYMBOLS
TF_SECONDS = {"M15": 900, "H1": 3600}
H1_HORIZONS = [4, 12, 24]
FORBIDDEN_EXECUTION_TOKENS = (
    "ordersend", "positionopen", "positionclose", "ctrade", "trade.buy",
    "trade.sell", "ordercalc", "broker_order_allowed=true",
    "demo_order_allowed=true", "live_order_allowed=true",
)

class PanelError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def last_sunday(year: int, month: int) -> dt.date:
    weeks = calendar.monthcalendar(year, month)
    return dt.date(year, month, [w[calendar.SUNDAY] for w in weeks if w[calendar.SUNDAY]][-1])


def amarkets_shift_minutes(server_times: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(server_times, unit="s", errors="coerce")
    if parsed.isna().any():
        raise PanelError("invalid server timestamps")
    dates = parsed.dt.date
    out = np.full(len(parsed), -120, dtype="int64")
    for year in sorted({x.year for x in dates}):
        start = last_sunday(year, 3)
        end = last_sunday(year, 10)
        mask = np.array([(x >= start and x < end) for x in dates])
        out[mask] = -180
    return pd.Series(out, index=server_times.index, dtype="int64")


def server_epoch_to_utc(server_epoch: pd.Series) -> pd.Series:
    values = pd.to_numeric(server_epoch, errors="coerce")
    if values.isna().any():
        raise PanelError("non-numeric server epoch")
    naive = pd.to_datetime(values.astype("int64"), unit="s", errors="coerce")
    shifts = amarkets_shift_minutes(values.astype("int64"))
    utc = naive + pd.to_timedelta(shifts, unit="m")
    return pd.to_datetime(utc, utc=True)


def safe_symbol_name(symbol: str) -> str:
    symbol = symbol.replace("&", "AND")
    return re.sub(r"[^A-Za-z0-9]+", "_", symbol).strip("_").lower()


def expected_export_path(export_dir: Path, symbol: str, timeframe: str) -> Path:
    return export_dir / f"{safe_symbol_name(symbol)}__{timeframe.lower()}.csv"


def read_export(path: Path, symbol: str, timeframe: str) -> pd.DataFrame:
    if not path.is_file():
        raise PanelError(f"missing MT5 export: {path}")
    required = {
        "program", "symbol", "timeframe", "time_server_epoch", "open", "high",
        "low", "close", "tick_volume", "spread", "real_volume", "source",
    }
    frame = pd.read_csv(path)
    missing = sorted(required - set(frame.columns))
    if missing:
        raise PanelError(f"export schema missing {missing}: {path}")
    frame = frame[frame["program"].astype(str).isin(EXPORT_PROGRAMS)].copy()
    frame = frame[frame["symbol"].astype(str) == symbol].copy()
    frame = frame[frame["timeframe"].astype(str).str.upper() == timeframe].copy()
    if frame.empty:
        raise PanelError(f"export has no matching rows: {path}")
    for col in ["open", "high", "low", "close", "tick_volume", "spread", "real_volume"]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    if frame[["open", "high", "low", "close"]].isna().any().any():
        raise PanelError(f"invalid OHLC values: {path}")
    if (frame[["open", "high", "low", "close"]] <= 0).any().any():
        raise PanelError(f"non-positive OHLC values: {path}")
    frame["timestamp_utc"] = server_epoch_to_utc(frame["time_server_epoch"])
    frame = frame.sort_values(["timestamp_utc", "time_server_epoch"]).drop_duplicates(
        "timestamp_utc", keep="last"
    )
    interval = TF_SECONDS[timeframe]
    frame["available_time_utc"] = frame["timestamp_utc"] + pd.to_timedelta(interval, unit="s")
    frame["symbol"] = symbol
    frame["timeframe"] = timeframe
    return frame.reset_index(drop=True)


def exact_log_return(close: pd.Series, times: pd.Series, lag_rows: int, interval_seconds: int) -> pd.Series:
    values = pd.to_numeric(close, errors="coerce").to_numpy(dtype="float64")
    t = pd.to_datetime(times, utc=True).to_numpy(dtype="datetime64[s]").astype("int64")
    out = np.full(len(values), np.nan, dtype="float64")
    if len(values) <= lag_rows:
        return pd.Series(out, index=close.index)
    current = values[lag_rows:]
    prior = values[:-lag_rows]
    gaps = t[lag_rows:] - t[:-lag_rows]
    valid = (
        np.isfinite(current) & np.isfinite(prior) & (current > 0) & (prior > 0)
        & (gaps == lag_rows * interval_seconds)
    )
    result = np.full(len(current), np.nan, dtype="float64")
    result[valid] = np.log(current[valid] / prior[valid])
    out[lag_rows:] = result
    return pd.Series(out, index=close.index)


def make_symbol_features(frame: pd.DataFrame, symbol: str, timeframe: str) -> pd.DataFrame:
    interval = TF_SECONDS[timeframe]
    prefix = safe_symbol_name(symbol)
    out = pd.DataFrame({"decision_time_utc": frame["available_time_utc"]})
    if timeframe == "H1":
        lags = [1, 4, 12, 24]
        vol_window = 24
    else:
        lags = [1, 4, 16]
        vol_window = 16
    ret1 = exact_log_return(frame["close"], frame["timestamp_utc"], 1, interval)
    for lag in lags:
        out[f"{prefix}_{timeframe.lower()}_ret_{lag}"] = exact_log_return(
            frame["close"], frame["timestamp_utc"], lag, interval
        ).to_numpy()
    out[f"{prefix}_{timeframe.lower()}_range_bps"] = (
        (frame["high"] - frame["low"]) / frame["close"] * 10000.0
    ).to_numpy()
    out[f"{prefix}_{timeframe.lower()}_body_bps"] = (
        (frame["close"] - frame["open"]) / frame["open"] * 10000.0
    ).to_numpy()
    out[f"{prefix}_{timeframe.lower()}_rv_{vol_window}"] = (
        ret1.rolling(vol_window, min_periods=vol_window).std(ddof=0) * math.sqrt(vol_window) * 10000.0
    ).to_numpy()
    out[f"{prefix}_{timeframe.lower()}_spread_points"] = frame["spread"].to_numpy()
    out[f"{prefix}_{timeframe.lower()}_source_bar_open_utc"] = frame["timestamp_utc"].astype(str).to_numpy()
    out[f"{prefix}_{timeframe.lower()}_available_time_utc"] = frame["available_time_utc"].astype(str).to_numpy()
    return out.drop_duplicates("decision_time_utc", keep="last").sort_values("decision_time_utc")


def make_targets(xau_h1: pd.DataFrame) -> pd.DataFrame:
    times = pd.to_datetime(xau_h1["timestamp_utc"], utc=True)
    ts_sec = times.to_numpy(dtype="datetime64[s]").astype("int64")
    opens = xau_h1["open"].to_numpy(dtype="float64")
    closes = xau_h1["close"].to_numpy(dtype="float64")
    index_by_sec = {int(v): i for i, v in enumerate(ts_sec)}
    rows: list[dict[str, Any]] = []
    for i, t in enumerate(ts_sec):
        row: dict[str, Any] = {
            "decision_time_utc": pd.Timestamp(times.iloc[i]).isoformat(),
            "entry_time_utc": pd.Timestamp(times.iloc[i]).isoformat(),
            "entry_open": float(opens[i]),
        }
        for horizon in H1_HORIZONS:
            exit_open_sec = int(t + (horizon - 1) * 3600)
            j = index_by_sec.get(exit_open_sec)
            if j is None:
                row[f"exit_time_{horizon}h_utc"] = None
                row[f"exit_close_{horizon}h"] = np.nan
                row[f"forward_return_{horizon}h_bps"] = np.nan
            else:
                exit_time = pd.Timestamp(times.iloc[j]) + pd.Timedelta(hours=1)
                exit_close = float(closes[j])
                row[f"exit_time_{horizon}h_utc"] = exit_time.isoformat()
                row[f"exit_close_{horizon}h"] = exit_close
                row[f"forward_return_{horizon}h_bps"] = (exit_close / opens[i] - 1.0) * 10000.0
        rows.append(row)
    return pd.DataFrame(rows)



def evaluate_session_eligibility(
    features: pd.DataFrame,
    targets: pd.DataFrame,
    ref_mask: pd.Series,
) -> dict[str, Any]:
    def ret4(symbol: str) -> str:
        return f"{safe_symbol_name(symbol)}_h1_ret_4"

    reference_rows = int(ref_mask.sum())
    unconditional_coverage = {
        symbol: float(features.loc[ref_mask, ret4(symbol)].notna().mean()) if reference_rows else 0.0
        for symbol in ALL_SYMBOLS
    }
    xau_anchor = ref_mask & features[ret4("XAUUSD")].notna()
    xau_anchor_rows = int(xau_anchor.sum())
    xau_anchor_share = float(xau_anchor_rows / reference_rows) if reference_rows else 0.0

    peer_symbols = [s for s in REQUIRED_SYMBOLS if s != "XAUUSD"]
    peer_coverage = {
        symbol: float(features.loc[xau_anchor, ret4(symbol)].notna().mean()) if xau_anchor_rows else 0.0
        for symbol in peer_symbols
    }
    core_columns = [ret4(s) for s in REQUIRED_SYMBOLS]
    core_history_ready = ref_mask & features[core_columns].notna().all(axis=1)
    core_history_rows = int(core_history_ready.sum())
    core_share_reference = float(core_history_rows / reference_rows) if reference_rows else 0.0
    core_share_anchor = float(core_history_rows / xau_anchor_rows) if xau_anchor_rows else 0.0

    target4 = targets["forward_return_4h_bps"].notna()
    target4_on_core = float(target4[core_history_ready].mean()) if core_history_rows else 0.0
    trade_ready = core_history_ready & target4
    trade_ready_rows = int(trade_ready.sum())
    trade_ready_share = float(trade_ready_rows / reference_rows) if reference_rows else 0.0

    target_horizon_coverage = {
        f"{h}h": float(targets.loc[ref_mask, f"forward_return_{h}h_bps"].notna().mean())
        if reference_rows else 0.0
        for h in H1_HORIZONS
    }
    return {
        "reference_rows": reference_rows,
        "unconditional_coverage": unconditional_coverage,
        "xau_anchor_mask": xau_anchor,
        "xau_anchor_rows": xau_anchor_rows,
        "xau_anchor_share": xau_anchor_share,
        "peer_coverage": peer_coverage,
        "core_history_mask": core_history_ready,
        "core_history_rows": core_history_rows,
        "core_history_share_of_reference": core_share_reference,
        "core_history_share_of_xau_anchor": core_share_anchor,
        "target_4h_coverage_on_core": target4_on_core,
        "trade_ready_mask": trade_ready,
        "trade_ready_rows": trade_ready_rows,
        "trade_ready_share_of_reference": trade_ready_share,
        "target_horizon_coverage": target_horizon_coverage,
    }

def load_macro_features(root: Path) -> pd.DataFrame:
    candidates = [
        root / "reports/xauusd_macro_causal_panel/macro_causal_features.csv",
        root / "reports/_archive",
    ]
    direct = candidates[0]
    if direct.is_file():
        path = direct
    else:
        archive = candidates[1]
        found = sorted(archive.glob("xauusd_macro_causal_panel_v1_1*/macro_causal_features.csv")) if archive.is_dir() else []
        if not found:
            found = sorted(archive.glob("xauusd_macro_causal_panel*/macro_causal_features.csv")) if archive.is_dir() else []
        if not found:
            raise PanelError("causal macro feature file not found")
        path = found[-1]
    frame = pd.read_csv(path)
    if "decision_date_utc" not in frame.columns:
        raise PanelError("macro feature file missing decision_date_utc")
    keep = [
        "decision_date_utc", "usd_broad_chg_5d", "usd_broad_chg_20d",
        "real_yield_10y", "real_yield_10y_chg_5d", "real_yield_10y_chg_20d",
        "nominal_yield_10y_chg_5d", "breakeven_10y_chg_5d",
        "vix_z252", "gvz_z252", "gvz_vix_ratio",
        "cftc_mm_net_z_156w", "etf_flow_tonnes_3m",
        "wgc_official_sector_purchases_tonnes", "official_event_blackout_active",
        "official_event_blackout_count", "official_events_next_24h_count",
    ]
    missing = [c for c in keep if c not in frame.columns]
    if missing:
        raise PanelError(f"macro feature file missing columns: {missing}")
    frame = frame[keep].copy()
    frame["decision_date_utc"] = pd.to_datetime(frame["decision_date_utc"], utc=True).dt.strftime("%Y-%m-%d")
    return frame.drop_duplicates("decision_date_utc", keep="last")


def static_execution_violations(root: Path) -> list[str]:
    violations: list[str] = []
    for rel in [Path("mt5/XAUUSD_CrossAssetHistoryExport.mq5")]:
        path = root / rel
        if not path.is_file():
            violations.append(f"missing:{rel}")
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        for token in FORBIDDEN_EXECUTION_TOKENS:
            if token in text:
                violations.append(f"{rel}:{token}")
    return violations


def resolve_mt5_export_dir() -> Path:
    return Path.home() / (
        "Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/"
        "Program Files/MetaTrader 5/MQL5/Files"
    ) / MT5_EXPORT_REL


def preflight(root: Path) -> dict[str, Any]:
    violations = static_execution_violations(root)
    macro_ready = (root / "reports/xauusd_macro_causal_panel/macro_causal_features.csv").is_file()
    if not macro_ready:
        archive = root / "reports/_archive"
        macro_ready = bool(list(archive.glob("xauusd_macro_causal_panel*/macro_causal_features.csv"))) if archive.is_dir() else False
    result = {
        "program": PROGRAM,
        "generated_utc": utc_now(),
        "decision": "PASS_CROSS_ASSET_PANEL_PREFLIGHT_EXPORT_REQUIRED",
        "pass": not violations and macro_ready,
        "paper_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
        "mt5_export_directory": str(resolve_mt5_export_dir()),
        "macro_causal_features_ready": macro_ready,
        "static_execution_violations": violations,
        "required_next_action": "RUN_MT5_EXPORT_SCRIPT_ONCE_THEN_BUILD",
    }
    if not result["pass"]:
        result["decision"] = "CROSS_ASSET_PANEL_PREFLIGHT_FAIL_CLOSED"
    return result


def build(root: Path, export_dir: Path | None = None, report_dir: Path | None = None) -> dict[str, Any]:
    export_dir = export_dir or resolve_mt5_export_dir()
    report_dir = report_dir or (root / REPORT_REL)
    if report_dir.exists() and any(report_dir.iterdir()):
        raise PanelError(f"output directory already exists and is non-empty: {report_dir}")
    report_dir.mkdir(parents=True, exist_ok=True)

    loaded: dict[tuple[str, str], pd.DataFrame] = {}
    source_rows: list[dict[str, Any]] = []
    for symbol in ALL_SYMBOLS:
        for tf in ["M15", "H1"]:
            path = expected_export_path(export_dir, symbol, tf)
            frame = read_export(path, symbol, tf)
            loaded[(symbol, tf)] = frame
            source_rows.append({
                "symbol": symbol, "timeframe": tf, "path": str(path),
                "rows": int(len(frame)), "first_utc": frame["timestamp_utc"].min().isoformat(),
                "last_utc": frame["timestamp_utc"].max().isoformat(),
                "sha256": sha256_file(path),
            })

    xau_h1 = loaded[("XAUUSD", "H1")]
    anchor = pd.DataFrame({"decision_time_utc": pd.to_datetime(xau_h1["timestamp_utc"], utc=True)})
    anchor = anchor.drop_duplicates().sort_values("decision_time_utc")
    features = anchor.copy()

    for symbol in ALL_SYMBOLS:
        for tf in ["H1", "M15"]:
            sf = make_symbol_features(loaded[(symbol, tf)], symbol, tf)
            features = features.merge(sf, on="decision_time_utc", how="left", validate="one_to_one")

    features["decision_date_utc"] = features["decision_time_utc"].dt.strftime("%Y-%m-%d")
    macro = load_macro_features(root)
    features = features.merge(macro, on="decision_date_utc", how="left", validate="many_to_one")
    # Defragment after repeated merges before adding derived columns.
    features = features.copy()

    # Derived cross-asset signals, all from completed prior bars.
    def col(sym: str, tf: str, suffix: str) -> str:
        return f"{safe_symbol_name(sym)}_{tf.lower()}_{suffix}"

    features["usd_fx_composite_h1"] = (
        -features[col("EURUSD", "H1", "ret_4")]
        + features[col("USDJPY", "H1", "ret_4")]
    ) / 2.0
    features["gold_silver_relative_h1"] = (
        features[col("XAUUSD", "H1", "ret_4")]
        - features[col("XAGUSD", "H1", "ret_4")]
    )
    risk_energy_columns = [
        col("S&P500", "H1", "ret_4"),
        col("WTI", "H1", "ret_4"),
        col("BRENT", "H1", "ret_4"),
    ]
    risk_energy_count = features[risk_energy_columns].notna().sum(axis=1)
    features["risk_energy_component_count_h1"] = risk_energy_count.astype("int64")
    features["risk_energy_composite_h1"] = features[risk_energy_columns].mean(axis=1, skipna=True)
    features.loc[risk_energy_count < 2, "risk_energy_composite_h1"] = np.nan

    for symbol in OPTIONAL_SYMBOLS:
        features[f"{safe_symbol_name(symbol)}_h1_ret4_available"] = (
            features[col(symbol, "H1", "ret_4")].notna().astype("int8")
        )

    targets = make_targets(xau_h1)
    targets["decision_time_utc"] = pd.to_datetime(targets["decision_time_utc"], utc=True)
    features = features.sort_values("decision_time_utc").reset_index(drop=True)
    targets = targets.sort_values("decision_time_utc").reset_index(drop=True)
    common = features[["decision_time_utc"]].merge(targets[["decision_time_utc"]], on="decision_time_utc")
    features = common.merge(features, on="decision_time_utc", how="left")
    targets = common.merge(targets, on="decision_time_utc", how="left")

    # Safe eligibility uses only completed historical features. Future target availability
    # is reported separately and never written into the feature matrix.
    core_history_columns = [col(s, "H1", "ret_4") for s in REQUIRED_SYMBOLS]
    features["core_h1_4h_history_ready"] = features[core_history_columns].notna().all(axis=1).astype("int8")
    targets["target_4h_available"] = targets["forward_return_4h_bps"].notna().astype("int8")

    for frame in (features, targets):
        frame["decision_time_utc"] = pd.to_datetime(frame["decision_time_utc"], utc=True).astype(str)
        frame["sample_role"] = np.where(
            pd.to_datetime(frame["decision_time_utc"], utc=True) < pd.Timestamp("2025-01-01", tz="UTC"),
            "REFERENCE_2016_2024",
            "SEEN_DIAGNOSTIC_NOT_PRISTINE_HOLDOUT",
        )

    ref_mask = pd.to_datetime(features["decision_time_utc"], utc=True).between(
        pd.Timestamp("2016-01-01", tz="UTC"), pd.Timestamp("2025-01-01", tz="UTC"), inclusive="left"
    )
    reference_rows = int(ref_mask.sum())

    eligibility = evaluate_session_eligibility(features, targets, ref_mask)
    unconditional_coverage = eligibility["unconditional_coverage"]
    xau_anchor_rows = eligibility["xau_anchor_rows"]
    xau_anchor_share = eligibility["xau_anchor_share"]
    peer_coverage_on_xau_anchor = eligibility["peer_coverage"]
    core_history_ready = eligibility["core_history_mask"]
    core_history_rows = eligibility["core_history_rows"]
    core_history_share_of_reference = eligibility["core_history_share_of_reference"]
    core_history_share_of_xau_anchor = eligibility["core_history_share_of_xau_anchor"]
    target_4h_coverage_on_core = eligibility["target_4h_coverage_on_core"]
    trade_ready_4h = eligibility["trade_ready_mask"]
    trade_ready_4h_rows = eligibility["trade_ready_rows"]
    trade_ready_4h_share_of_reference = eligibility["trade_ready_share_of_reference"]
    target_horizon_coverage = eligibility["target_horizon_coverage"]

    availability_columns = [c for c in features.columns if c.endswith("_available_time_utc")]
    leakage_counts: dict[str, int] = {}
    decisions = pd.to_datetime(features["decision_time_utc"], utc=True)
    for c in availability_columns:
        available = pd.to_datetime(features[c], utc=True, errors="coerce")
        leakage_counts[c] = int((available > decisions).fillna(False).sum())

    target_columns_in_features = [
        c for c in features.columns
        if c.startswith("forward_return_") or c.startswith("exit_") or c == "entry_open"
    ]
    rate_coverage = float(features.loc[trade_ready_4h, "real_yield_10y"].notna().mean()) if trade_ready_4h_rows else 0.0
    feature_target_time_match = bool(features["decision_time_utc"].equals(targets["decision_time_utc"]))

    gates = {
        "reference_rows_at_least_30000": reference_rows >= 30000,
        "xau_exact_4h_history_share_at_least_0_70": xau_anchor_share >= 0.70,
        "peer_core_coverage_on_xau_anchor_at_least_0_97": (
            min(peer_coverage_on_xau_anchor.values(), default=0.0) >= 0.97
        ),
        "core_history_rows_at_least_30000": core_history_rows >= 30000,
        "core_history_share_of_xau_anchor_at_least_0_97": core_history_share_of_xau_anchor >= 0.97,
        "target_4h_coverage_on_core_at_least_0_90": target_4h_coverage_on_core >= 0.90,
        "trade_ready_4h_rows_at_least_30000": trade_ready_4h_rows >= 30000,
        "daily_real_yield_coverage_at_least_0_90": rate_coverage >= 0.90,
        "availability_leakage_zero": sum(leakage_counts.values()) == 0,
        "target_columns_absent_from_features": not target_columns_in_features,
        "feature_target_time_match": feature_target_time_match,
    }
    passed = all(gates.values())
    decision = (
        "PASS_CROSS_ASSET_INTRADAY_CAUSAL_PANEL_READY_FOR_FIXED_SCAN"
        if passed else "CROSS_ASSET_INTRADAY_PANEL_FAIL_CLOSED"
    )

    features_path = report_dir / "cross_asset_intraday_features.csv"
    targets_path = report_dir / "cross_asset_intraday_targets.csv"
    sources_path = report_dir / "cross_asset_source_manifest.csv"
    features.to_csv(features_path, index=False)
    targets.to_csv(targets_path, index=False)
    pd.DataFrame(source_rows).to_csv(sources_path, index=False)

    def coverage_table(frame: pd.DataFrame) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for name in frame.columns:
            nonempty = int(frame[name].notna().sum())
            rows.append({
                "column": name,
                "nonempty_rows": nonempty,
                "missing_rows": int(len(frame) - nonempty),
                "coverage": float(nonempty / len(frame)) if len(frame) else 0.0,
                "reference_coverage": float(frame.loc[ref_mask, name].notna().mean()) if reference_rows else 0.0,
            })
        return pd.DataFrame(rows)

    feature_coverage = coverage_table(features)
    target_coverage = coverage_table(targets)
    feature_coverage.to_csv(report_dir / "cross_asset_feature_column_coverage.csv", index=False)
    target_coverage.to_csv(report_dir / "cross_asset_target_column_coverage.csv", index=False)

    feature_policy = feature_coverage[["column", "reference_coverage"]].copy()
    feature_policy["fixed_scan_policy"] = np.select(
        [
            feature_policy["column"].isin(core_history_columns + [
                "usd_fx_composite_h1", "gold_silver_relative_h1",
                "risk_energy_composite_h1", "core_h1_4h_history_ready",
            ]),
            feature_policy["reference_coverage"] < 0.05,
            feature_policy["reference_coverage"] < 0.50,
        ],
        ["CORE_OR_DERIVED", "EXCLUDE_NEAR_EMPTY", "SPARSE_OPTIONAL_WITH_INDICATOR"],
        default="AVAILABLE_WITH_MISSINGNESS_CONTROL",
    )
    feature_policy.to_csv(report_dir / "cross_asset_feature_policy.csv", index=False)

    def sample_rows(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame
        indices = sorted(set(
            list(range(min(5, len(frame))))
            + list(range(max(0, len(frame) - 5), len(frame)))
            + [int(i) for i in np.linspace(0, len(frame) - 1, num=min(20, len(frame)))]
        ))
        return frame.iloc[indices].copy()

    sample_rows(features).to_csv(report_dir / "cross_asset_feature_samples.csv", index=False)
    sample_rows(targets).to_csv(report_dir / "cross_asset_target_samples.csv", index=False)

    large_file_manifest = {
        "program": PROGRAM,
        "generated_utc": utc_now(),
        "files": [
            {"path": features_path.name, "size": features_path.stat().st_size, "sha256": sha256_file(features_path), "rows": int(len(features)), "columns": int(len(features.columns))},
            {"path": targets_path.name, "size": targets_path.stat().st_size, "sha256": sha256_file(targets_path), "rows": int(len(targets)), "columns": int(len(targets.columns))},
        ],
        "included_in_results_zip": False,
        "reason": "large local model inputs retained in repo report directory; compact evidence only is uploaded",
    }
    (report_dir / "cross_asset_large_file_manifest.json").write_text(
        json.dumps(large_file_manifest, indent=2), encoding="utf-8"
    )

    quality = {
        "program": PROGRAM,
        "generated_utc": utc_now(),
        "reference_rows_2016_2024": reference_rows,
        "diagnostic_rows_2025_plus": int((~ref_mask).sum()),
        "unconditional_symbol_h1_ret4_coverage": unconditional_coverage,
        "session_eligibility": {
            "xau_exact_4h_history_rows": xau_anchor_rows,
            "xau_exact_4h_history_share_of_reference": xau_anchor_share,
            "peer_coverage_on_xau_anchor": peer_coverage_on_xau_anchor,
            "core_history_ready_rows": core_history_rows,
            "core_history_share_of_reference": core_history_share_of_reference,
            "core_history_share_of_xau_anchor": core_history_share_of_xau_anchor,
            "target_4h_coverage_on_core_history": target_4h_coverage_on_core,
            "trade_ready_4h_rows": trade_ready_4h_rows,
            "trade_ready_4h_share_of_reference": trade_ready_4h_share_of_reference,
        },
        "target_horizon_coverage": target_horizon_coverage,
        "daily_real_yield_coverage_on_trade_ready_4h": rate_coverage,
        "availability_leakage_counts": leakage_counts,
        "target_columns_in_features": target_columns_in_features,
        "feature_rows": int(len(features)),
        "target_rows": int(len(targets)),
        "feature_target_time_match": feature_target_time_match,
        "gates": gates,
    }
    (report_dir / "cross_asset_panel_quality.json").write_text(json.dumps(quality, indent=2), encoding="utf-8")

    contract = {
        "program": PROGRAM,
        "accepted_export_programs": sorted(EXPORT_PROGRAMS),
        "generated_utc": utc_now(),
        "decision_time": "XAUUSD H1 bar open UTC",
        "intraday_feature_contract": "only completed H1/M15 bars with availability <= decision_time",
        "exact_gap_contract": {
            "meaning": "ret_4 requires four uninterrupted wall-clock hours; daily maintenance breaks intentionally create missing values",
            "quality_denominator": "eligible XAU exact-4h rows, not all XAU H1 anchor rows",
            "missingness_policy": "retain explicit availability flags; do not forward-fill exact returns",
        },
        "amarkets_time_contract": {
            "standard_shift_minutes": -120,
            "dst_shift_minutes": -180,
            "dst_calendar": "EU",
            "semantics": "timestamp_utc = timestamp_server_naive + shift_minutes",
        },
        "target_contract": {
            "entry": "XAUUSD open at decision_time",
            "horizons_hours": H1_HORIZONS,
            "exit": "close of the exact final H1 bar in the horizon",
        },
        "slow_rate_contract": "daily causal macro-panel features, including real and nominal US yields",
        "sample_policy": {
            "reference": "2016-01-01 through 2024-12-31",
            "2025_plus": "SEEN_DIAGNOSTIC_NOT_PRISTINE_HOLDOUT",
        },
        "paper_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
    }
    (report_dir / "cross_asset_panel_contract.json").write_text(json.dumps(contract, indent=2), encoding="utf-8")

    summary = {
        "program": PROGRAM,
        "generated_utc": utc_now(),
        "decision": decision,
        "pass": passed,
        "paper_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
        "feature_rows": int(len(features)),
        "target_rows": int(len(targets)),
        "reference_rows_2016_2024": reference_rows,
        "diagnostic_rows_2025_plus": int((~ref_mask).sum()),
        "xau_exact_4h_history_share_of_reference": xau_anchor_share,
        "core_history_ready_rows": core_history_rows,
        "trade_ready_4h_rows": trade_ready_4h_rows,
        "peer_coverage_on_xau_anchor": peer_coverage_on_xau_anchor,
        "optional_symbol_unconditional_coverage": {s: unconditional_coverage[s] for s in OPTIONAL_SYMBOLS},
        "daily_real_yield_coverage_on_trade_ready_4h": rate_coverage,
        "failed_gates": [name for name, ok in gates.items() if not ok],
        "required_next_action": "FIXED_CROSS_ASSET_INTRADAY_THESIS_SCAN" if passed else "REPAIR_PANEL_CONTRACT",
    }
    (report_dir / "cross_asset_panel_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    md = [
        "# XAUUSD Cross-Asset Intraday Causal Panel",
        "",
        f"Decision: `{decision}`",
        "",
        f"Feature rows: {len(features)}",
        f"Reference rows 2016-2024: {reference_rows}",
        f"XAU exact-4h eligible share: {xau_anchor_share:.4%}",
        f"Core history-ready rows: {core_history_rows}",
        f"Trade-ready 4h rows: {trade_ready_4h_rows}",
        f"Diagnostic rows 2025+: {int((~ref_mask).sum())}",
        "",
        "Quality is session-eligible: daily maintenance gaps are missing by contract, not data loss.",
        "Large feature and target CSVs remain local and are excluded from the compact evidence ZIP.",
        "No paper, demo, or live orders are authorized.",
    ]
    (report_dir / "cross_asset_panel_decision.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    failure_path = report_dir / "cross_asset_panel_failure.json"
    if passed and failure_path.exists():
        failure_path.unlink()
    return summary


def collect(root: Path, report_dir: Path | None = None, output: Path | None = None) -> dict[str, Any]:
    report_dir = report_dir or (root / REPORT_REL)
    summary_path = report_dir / "cross_asset_panel_summary.json"
    if not summary_path.is_file():
        raise PanelError(f"panel summary missing: {summary_path}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if not summary.get("pass"):
        raise PanelError("panel summary is not passing; compact results pack not created")
    output = output or (Path.home() / "Downloads/XAUUSD_CROSS_ASSET_INTRADAY_PANEL_RESULTS.zip")
    names = [
        "cross_asset_panel_summary.json", "cross_asset_panel_quality.json",
        "cross_asset_panel_contract.json", "cross_asset_panel_decision.md",
        "cross_asset_source_manifest.csv", "cross_asset_feature_column_coverage.csv",
        "cross_asset_target_column_coverage.csv", "cross_asset_feature_policy.csv",
        "cross_asset_feature_samples.csv", "cross_asset_target_samples.csv",
        "cross_asset_large_file_manifest.json",
    ]
    files = [report_dir / n for n in names]
    missing = [str(p) for p in files if not p.is_file()]
    if missing:
        raise PanelError(f"missing compact panel outputs: {missing}")
    manifest = {
        "program": PROGRAM,
        "generated_utc": utc_now(),
        "artifact_scope": "COMPACT_EVIDENCE_NO_LARGE_FEATURE_TARGET_CSV",
        "files": [
            {"path": p.name, "size": p.stat().st_size, "sha256": sha256_file(p)} for p in files
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, p.name)
        z.writestr("RESULTS_MANIFEST.json", json.dumps(manifest, indent=2))
    return {
        "program": PROGRAM,
        "generated_utc": utc_now(),
        "decision": "PASS_CROSS_ASSET_INTRADAY_PANEL_COMPACT_RESULTS_PACK_CREATED",
        "pass": True,
        "paper_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
        "output": str(output),
        "large_feature_target_files_included": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ["preflight", "build", "collect"]:
        p = sub.add_parser(name)
        p.add_argument("--root", type=Path, default=Path.cwd())
        if name == "build":
            p.add_argument("--export-dir", type=Path)
        if name == "collect":
            p.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.cmd == "preflight":
            result = preflight(root)
        elif args.cmd == "build":
            result = build(root, export_dir=args.export_dir)
        else:
            result = collect(root, output=args.output)
        print(json.dumps(result, indent=2))
        return 0 if result.get("pass") else 2
    except Exception as exc:
        failure = {
            "program": PROGRAM,
            "generated_utc": utc_now(),
            "decision": "CROSS_ASSET_INTRADAY_PANEL_FAIL_CLOSED",
            "pass": False,
            "paper_order_allowed": False,
            "demo_order_allowed": False,
            "live_order_allowed": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
        report = root / REPORT_REL
        report.mkdir(parents=True, exist_ok=True)
        (report / "cross_asset_panel_failure.json").write_text(json.dumps(failure, indent=2), encoding="utf-8")
        print(json.dumps(failure, indent=2))
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
