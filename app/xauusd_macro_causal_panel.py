#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import shutil
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
import pandas as pd

PROGRAM = "XAUUSD_MACRO_CAUSAL_PANEL_V1_1_GOLD_ASOF_EXECUTION_REPAIR"
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
REPORT_DIR = Path("reports/xauusd_macro_causal_panel")
CORE_SERIES = ("usd_broad", "real_yield_10y", "nominal_yield_10y", "breakeven_10y", "vix", "gvz")

class PanelError(RuntimeError):
    pass


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def atomic_write_json(path: Path, obj: Any) -> None:
    atomic_write_text(path, json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n")


def load_config(root: Path, config_path: Path | None = None) -> dict[str, Any]:
    path = config_path or root / "config/xauusd_macro_causal_panel_v1.json"
    if not path.is_file():
        raise PanelError(f"config missing: {path}")
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if cfg.get("program") != PROGRAM:
        raise PanelError(f"unexpected config program: {cfg.get('program')}")
    return cfg


def reject_masquerade(data: bytes, path: Path) -> None:
    prefix = data[:500].lstrip().lower()
    if prefix.startswith(b"<!doctype html") or prefix.startswith(b"<html"):
        raise PanelError(f"HTML masquerading as data: {path}")
    if path.suffix.lower() == ".xlsx" and not data.startswith(b"PK"):
        raise PanelError(f"invalid XLSX container: {path}")


def read_csv_checked(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise PanelError(f"file missing: {path}")
    data = path.read_bytes()
    reject_masquerade(data, path)
    try:
        return pd.read_csv(io.BytesIO(data), low_memory=False)
    except Exception as exc:
        raise PanelError(f"cannot parse CSV {path}: {exc}") from exc


def to_utc(values: Iterable[Any]) -> pd.Series:
    return pd.to_datetime(values, utc=True, errors="coerce")


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.replace({".": np.nan, "": np.nan}), errors="coerce")


def safe_rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def candidate_fred_paths(root: Path, series: str) -> list[Path]:
    candidates: list[Path] = []
    downloads = Path.home() / "Downloads/xauusd_fundamental_event_inbox/fred_macro" / f"{series}.csv"
    candidates.append(downloads)
    raw = root / "data/fundamental_event_inbox/raw/fred_macro"
    if raw.is_dir():
        candidates.extend(sorted(raw.glob(f"*__{series}.csv")))
    return [p for p in candidates if p.is_file()]


def validate_fred(path: Path, series: str) -> dict[str, Any]:
    df = read_csv_checked(path)
    expected = ["observation_date", series]
    if list(df.columns[:2]) != expected:
        raise PanelError(f"unexpected {series} headers in {path}: {list(df.columns)}")
    dates = to_utc(df["observation_date"])
    vals = numeric(df[series])
    valid = dates.notna() & vals.notna()
    if int(valid.sum()) < 500:
        raise PanelError(f"insufficient valid {series} rows in {path}: {int(valid.sum())}")
    return {
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "rows": int(valid.sum()),
        "first_date": dates[valid].min().isoformat(),
        "last_date": dates[valid].max().isoformat(),
        "size": path.stat().st_size,
    }


def select_fred(root: Path, series: str) -> dict[str, Any]:
    valid: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for path in candidate_fred_paths(root, series):
        try:
            meta = validate_fred(path, series)
            valid.append(meta)
        except Exception as exc:
            failures.append({"path": str(path), "error": f"{type(exc).__name__}: {exc}"})
    if not valid:
        raise PanelError(f"no valid canonical source for {series}; failures={failures}")
    valid.sort(key=lambda x: (x["last_date"], x["rows"], x["size"]), reverse=True)
    selected = valid[0]
    selected["alternatives"] = valid[1:]
    selected["rejected"] = failures
    return selected


def load_fred(path: Path, series: str, value_name: str, lag_days: int) -> pd.DataFrame:
    df = read_csv_checked(path)[["observation_date", series]].copy()
    df["observation_time"] = to_utc(df["observation_date"]).dt.normalize()
    df[value_name] = numeric(df[series])
    df = df.dropna(subset=["observation_time", value_name]).sort_values("observation_time")
    df = df.drop_duplicates("observation_time", keep="last")
    df[f"{value_name}_available_after_utc"] = df["observation_time"] + pd.Timedelta(days=lag_days)
    return df[["observation_time", f"{value_name}_available_after_utc", value_name]].rename(
        columns={"observation_time": f"{value_name}_observation_date_utc"}
    )


def exact_path(root: Path, rel: str) -> Path:
    p = root / rel
    if not p.is_file():
        raise PanelError(f"required canonical file missing: {p}")
    return p


def load_gold(root: Path) -> tuple[pd.DataFrame, Path]:
    preferences = [
        "data/macro_regime/raw/broker_or_spot_gold_d1_ohlc_2011_present.csv",
        "data/macro_regime/raw/gold_d1_ohlc_2011_present.csv",
    ]
    for rel in preferences:
        path = root / rel
        if not path.is_file():
            continue
        df = read_csv_checked(path)
        required = {"date_utc", "open", "high", "low", "close"}
        if not required.issubset(df.columns):
            continue
        out = pd.DataFrame({
            "gold_bar_date_utc": to_utc(df["date_utc"]).dt.normalize(),
            "gold_bar_open": numeric(df["open"]),
            "gold_bar_high": numeric(df["high"]),
            "gold_bar_low": numeric(df["low"]),
            "gold_bar_close": numeric(df["close"]),
        })
        out = out.dropna(subset=["gold_bar_date_utc", "gold_bar_open", "gold_bar_close"])
        out = out.sort_values("gold_bar_date_utc").drop_duplicates("gold_bar_date_utc", keep="last")
        return out.reset_index(drop=True), path
    raise PanelError("no valid canonical gold daily file")


def build_decision_panel(gold_bars: pd.DataFrame) -> pd.DataFrame:
    """Build an executable daily decision panel.

    A row dated D is a decision made at D 00:00 UTC, using only the completed
    gold bar from the previous trading row. Entry is the open of D and future
    targets are kept in a separate file.
    """
    out = pd.DataFrame({
        "decision_date_utc": gold_bars["gold_bar_date_utc"],
        "decision_time_utc": gold_bars["gold_bar_date_utc"],
        "gold_feature_observation_date_utc": gold_bars["gold_bar_date_utc"].shift(1),
        "gold_feature_available_after_utc": gold_bars["gold_bar_date_utc"],
        "gold_prev_open": gold_bars["gold_bar_open"].shift(1),
        "gold_prev_high": gold_bars["gold_bar_high"].shift(1),
        "gold_prev_low": gold_bars["gold_bar_low"].shift(1),
        "gold_prev_close": gold_bars["gold_bar_close"].shift(1),
    })
    out = out.dropna(subset=[
        "decision_date_utc",
        "gold_feature_observation_date_utc",
        "gold_prev_open",
        "gold_prev_close",
    ]).reset_index(drop=True)
    return out


def asof_merge(panel: pd.DataFrame, source: pd.DataFrame, available_col: str) -> pd.DataFrame:
    left = panel.sort_values("decision_time_utc")
    right = source.sort_values(available_col)
    return pd.merge_asof(
        left,
        right,
        left_on="decision_time_utc",
        right_on=available_col,
        direction="backward",
        allow_exact_matches=True,
    )


def load_cftc(root: Path) -> tuple[pd.DataFrame, Path]:
    path = exact_path(root, "data/external_frontiers/cot_positioning_normalized.csv")
    df = read_csv_checked(path)
    required = {"report_date_utc", "available_after_utc", "managed_money_net_z_156w", "managed_money_net_pct_oi", "managed_money_net_change_4w"}
    if not required.issubset(df.columns):
        raise PanelError(f"CFTC schema mismatch: missing {sorted(required - set(df.columns))}")
    out = pd.DataFrame({
        "cftc_report_date_utc": to_utc(df["report_date_utc"]),
        "cftc_available_after_utc": to_utc(df["available_after_utc"]),
        "cftc_mm_net_z_156w": numeric(df["managed_money_net_z_156w"]),
        "cftc_mm_net_pct_oi": numeric(df["managed_money_net_pct_oi"]),
        "cftc_mm_net_change_4w": numeric(df["managed_money_net_change_4w"]),
    }).dropna(subset=["cftc_available_after_utc"])
    out = out.sort_values("cftc_available_after_utc").drop_duplicates("cftc_available_after_utc", keep="last")
    return out, path


def load_etf_optional(root: Path) -> tuple[pd.DataFrame | None, Path | None]:
    path = root / "data/macro_regime/normalized/wgc_global_etf_holdings_monthly_stage173.csv"
    if not path.is_file():
        return None, None
    df = read_csv_checked(path)
    required = {"date_utc", "available_after_utc", "holdings_tonnes", "etf_flow_tonnes_3m"}
    if not required.issubset(df.columns):
        return None, None
    out = pd.DataFrame({
        "etf_period_date_utc": to_utc(df["date_utc"]),
        "etf_available_after_utc": to_utc(df["available_after_utc"]),
        "etf_holdings_tonnes": numeric(df["holdings_tonnes"]),
        "etf_flow_tonnes_3m": numeric(df["etf_flow_tonnes_3m"]),
    }).dropna(subset=["etf_available_after_utc"])
    out = out.sort_values("etf_available_after_utc").drop_duplicates("etf_available_after_utc", keep="last")
    return out, path


def load_wgc_optional(root: Path) -> tuple[pd.DataFrame | None, Path | None]:
    path = root / "data/macro_regime/vintages/wgc_official_sector_quarterly_vintages.csv"
    if not path.is_file():
        return None, None
    df = read_csv_checked(path)
    required = {"quarter_end_utc", "release_timestamp_utc", "official_sector_purchases_tonnes"}
    if not required.issubset(df.columns):
        return None, None
    if "is_original_publication" in df.columns:
        flag = df["is_original_publication"].astype(str).str.lower().isin({"true", "1", "yes"})
        if flag.any():
            df = df[flag].copy()
    out = pd.DataFrame({
        "wgc_quarter_end_utc": to_utc(df["quarter_end_utc"]),
        "wgc_available_after_utc": to_utc(df["release_timestamp_utc"]),
        "wgc_official_sector_purchases_tonnes": numeric(df["official_sector_purchases_tonnes"]),
    }).dropna(subset=["wgc_available_after_utc"])
    out = out.sort_values("wgc_available_after_utc").drop_duplicates("wgc_available_after_utc", keep="last")
    return out, path


def load_events(root: Path, cfg: dict[str, Any]) -> tuple[pd.DataFrame, Path]:
    path = exact_path(root, "data/fundamental_event_inbox/features/stage115_official_core_event_timestamps.csv")
    df = read_csv_checked(path)
    required = {"event_time_utc", "source", "category", "title"}
    if not required.issubset(df.columns):
        raise PanelError(f"event schema mismatch: missing {sorted(required - set(df.columns))}")
    events = pd.DataFrame({
        "event_time_utc": to_utc(df["event_time_utc"]),
        "event_source": df["source"].astype(str),
        "event_category": df["category"].astype(str),
        "event_title": df["title"].astype(str),
    }).dropna(subset=["event_time_utc"]).sort_values("event_time_utc")
    return events, path


def add_event_flags(panel: pd.DataFrame, events: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    before = pd.Timedelta(minutes=int(cfg["event_blackout_before_minutes"]))
    after = pd.Timedelta(minutes=int(cfg["event_blackout_after_minutes"]))
    times = events["event_time_utc"].sort_values().to_numpy(dtype="datetime64[ns]")
    counts: list[int] = []
    flags: list[bool] = []
    next24: list[int] = []
    for t in panel["decision_time_utc"]:
        t64 = np.datetime64(t.to_datetime64(), "ns")
        lo = np.searchsorted(times, t64 - np.timedelta64(int(after.total_seconds()), "s"), side="left")
        hi = np.searchsorted(times, t64 + np.timedelta64(int(before.total_seconds()), "s"), side="right")
        n = int(max(0, hi - lo))
        counts.append(n)
        flags.append(n > 0)
        hi24 = np.searchsorted(times, t64 + np.timedelta64(24, "h"), side="right")
        next24.append(int(max(0, hi24 - np.searchsorted(times, t64, side="left"))))
    out = panel.copy()
    out["official_event_blackout_active"] = flags
    out["official_event_blackout_count"] = counts
    out["official_events_next_24h_count"] = next24
    return out


def add_derived_features(panel: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    values = ["usd_broad", "real_yield_10y", "nominal_yield_10y", "breakeven_10y", "vix", "gvz"]
    for col in values:
        if col not in out:
            continue
        for lag in (5, 20, 60):
            out[f"{col}_chg_{lag}d"] = out[col] - out[col].shift(lag)
            if col in {"usd_broad", "vix", "gvz"}:
                out[f"{col}_ret_{lag}d"] = out[col].pct_change(lag, fill_method=None)
        rolling = out[col].rolling(252, min_periods=126)
        out[f"{col}_z252"] = (out[col] - rolling.mean()) / rolling.std(ddof=0).replace(0, np.nan)
    out["gvz_vix_ratio"] = out["gvz"] / out["vix"].replace(0, np.nan)
    return out


def build_targets(gold_bars: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
    """Targets for a decision at the current trading-day open.

    The signal uses the previous completed D1 bar. Entry is the current row's
    open. A horizon h exits at the close h trading rows after the entry row.
    """
    out = pd.DataFrame({
        "decision_date_utc": gold_bars["gold_bar_date_utc"],
        "decision_time_utc": gold_bars["gold_bar_date_utc"],
        "entry_date_utc": gold_bars["gold_bar_date_utc"],
        "entry_open": gold_bars["gold_bar_open"],
    })
    for h in horizons:
        exit_close = gold_bars["gold_bar_close"].shift(-h)
        out[f"exit_close_{h}td"] = exit_close
        out[f"gross_return_{h}td_bps"] = (exit_close / out["entry_open"] - 1.0) * 10000.0
        out[f"target_exit_date_{h}td_utc"] = gold_bars["gold_bar_date_utc"].shift(-h)
    out["future_target_only"] = True
    # The first raw gold row has no previous completed bar and therefore no
    # corresponding feature row. Keep target rows exactly aligned to features.
    return out.iloc[1:].reset_index(drop=True)


def source_meta(path: Path, root: Path) -> dict[str, Any]:
    return {"path": safe_rel(path, root), "absolute_path": str(path.resolve()), "sha256": sha256_file(path), "size": path.stat().st_size}


def select_sources(root: Path, cfg: dict[str, Any], allow_missing_gvz: bool) -> dict[str, Any]:
    selected: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for name, series in cfg["fred_series"].items():
        try:
            selected[name] = select_fred(root, series)
        except Exception as exc:
            if name == "gvz" and allow_missing_gvz:
                errors[name] = f"{type(exc).__name__}: {exc}"
            else:
                raise
    gold_bars, gold_path = load_gold(root)
    selected["gold"] = source_meta(gold_path, root) | {
        "rows": len(gold_bars),
        "first_date": gold_bars["gold_bar_date_utc"].min().isoformat(),
        "last_date": gold_bars["gold_bar_date_utc"].max().isoformat(),
    }
    cftc, cftc_path = load_cftc(root)
    selected["cftc"] = source_meta(cftc_path, root) | {"rows": len(cftc)}
    events, events_path = load_events(root, cfg)
    selected["events"] = source_meta(events_path, root) | {"rows": len(events)}
    etf, etf_path = load_etf_optional(root)
    selected["etf_optional"] = None if etf_path is None else source_meta(etf_path, root) | {"rows": len(etf)}
    wgc, wgc_path = load_wgc_optional(root)
    selected["wgc_optional"] = None if wgc_path is None else source_meta(wgc_path, root) | {"rows": len(wgc)}
    return {"selected": selected, "errors": errors}


def preflight(root: Path, config_path: Path | None = None) -> dict[str, Any]:
    cfg = load_config(root, config_path)
    selection = select_sources(root, cfg, allow_missing_gvz=True)
    gvz_missing = "gvz" not in selection["selected"]
    result = {
        "program": PROGRAM,
        "generated_utc": now_utc(),
        "decision": "PASS_MACRO_PANEL_PREFLIGHT_GVZ_DOWNLOAD_REQUIRED" if gvz_missing else "PASS_MACRO_PANEL_PREFLIGHT_READY",
        "pass": True,
        "network_required": gvz_missing,
        "paper_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
        "selection": selection,
        "required_next_action": "FETCH_GVZ_THEN_BUILD" if gvz_missing else "BUILD_CAUSAL_PANEL",
    }
    out = root / REPORT_DIR / "macro_panel_preflight.json"
    atomic_write_json(out, result)
    return result


def validate_gvz_bytes(data: bytes) -> pd.DataFrame:
    reject_masquerade(data, Path("GVZCLS.csv"))
    df = pd.read_csv(io.BytesIO(data), low_memory=False)
    if list(df.columns[:2]) != ["observation_date", "GVZCLS"]:
        raise PanelError(f"unexpected GVZCLS headers: {list(df.columns)}")
    dates = to_utc(df["observation_date"])
    vals = numeric(df["GVZCLS"])
    valid = dates.notna() & vals.notna()
    if int(valid.sum()) < 1000:
        raise PanelError(f"insufficient GVZCLS rows: {int(valid.sum())}")
    if dates[valid].min() > pd.Timestamp("2012-01-01", tz="UTC"):
        raise PanelError("GVZ history starts too late")
    return df


def fetch_gvz(root: Path, source_file: Path | None = None) -> dict[str, Any]:
    if source_file is not None:
        data = source_file.read_bytes()
        source = str(source_file.resolve())
    else:
        url = FRED_CSV_URL.format(series="GVZCLS")
        req = urllib.request.Request(url, headers={"User-Agent": "xauusd-research/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                data = response.read()
        except Exception as exc:
            raise PanelError(f"GVZ download failed: {type(exc).__name__}: {exc}") from exc
        source = url
    df = validate_gvz_bytes(data)
    digest = sha256_bytes(data)
    repo_path = root / "data/fundamental_event_inbox/raw/fred_macro" / f"{digest[:12]}__GVZCLS.csv"
    downloads_path = Path.home() / "Downloads/xauusd_fundamental_event_inbox/fred_macro/GVZCLS.csv"
    repo_path.parent.mkdir(parents=True, exist_ok=True)
    downloads_path.parent.mkdir(parents=True, exist_ok=True)
    repo_path.write_bytes(data)
    downloads_path.write_bytes(data)
    dates = to_utc(df["observation_date"])
    vals = numeric(df["GVZCLS"])
    valid = dates.notna() & vals.notna()
    result = {
        "program": PROGRAM,
        "generated_utc": now_utc(),
        "decision": "PASS_GVZCLS_FETCH_AND_CANONICALIZE",
        "pass": True,
        "source": source,
        "sha256": digest,
        "repo_path": str(repo_path.resolve()),
        "downloads_path": str(downloads_path.resolve()),
        "rows": int(valid.sum()),
        "first_date": dates[valid].min().isoformat(),
        "last_date": dates[valid].max().isoformat(),
        "paper_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
    }
    atomic_write_json(root / REPORT_DIR / "gvz_fetch_summary.json", result)
    return result


def build(root: Path, config_path: Path | None = None) -> dict[str, Any]:
    cfg = load_config(root, config_path)
    selection = select_sources(root, cfg, allow_missing_gvz=False)
    selected = selection["selected"]
    gold_bars, gold_path = load_gold(root)
    panel = build_decision_panel(gold_bars)
    lag = int(cfg["daily_availability_lag_days"])
    for name in CORE_SERIES:
        series = cfg["fred_series"][name]
        path = Path(selected[name]["path"])
        src = load_fred(path, series, name, lag)
        panel = asof_merge(panel, src, f"{name}_available_after_utc")
    cftc, cftc_path = load_cftc(root)
    panel = asof_merge(panel, cftc, "cftc_available_after_utc")
    etf, etf_path = load_etf_optional(root)
    if etf is not None:
        panel = asof_merge(panel, etf, "etf_available_after_utc")
    wgc, wgc_path = load_wgc_optional(root)
    if wgc is not None:
        panel = asof_merge(panel, wgc, "wgc_available_after_utc")
    events, events_path = load_events(root, cfg)
    panel = add_event_flags(panel, events, cfg)
    panel = add_derived_features(panel)
    targets = build_targets(gold_bars, list(map(int, cfg["target_horizons_trading_days"])))
    if len(targets) != len(panel) or not targets["decision_date_utc"].equals(panel["decision_date_utc"]):
        raise PanelError("feature/target decision-row alignment failed")

    # Hard causality checks.
    leakage: dict[str, int] = {}
    leakage["gold"] = int((
        panel["gold_feature_available_after_utc"].notna()
        & (panel["gold_feature_available_after_utc"] > panel["decision_time_utc"])
    ).sum())
    gold_nonprior = int((
        panel["gold_feature_observation_date_utc"] >= panel["decision_date_utc"]
    ).sum())
    for name in CORE_SERIES:
        avail = f"{name}_available_after_utc"
        leakage[name] = int((panel[avail].notna() & (panel[avail] > panel["decision_time_utc"])).sum())
    leakage["cftc"] = int((panel["cftc_available_after_utc"].notna() & (panel["cftc_available_after_utc"] > panel["decision_time_utc"])).sum())
    if etf is not None:
        leakage["etf"] = int((panel["etf_available_after_utc"].notna() & (panel["etf_available_after_utc"] > panel["decision_time_utc"])).sum())
    if wgc is not None:
        leakage["wgc"] = int((panel["wgc_available_after_utc"].notna() & (panel["wgc_available_after_utc"] > panel["decision_time_utc"])).sum())
    if any(leakage.values()):
        raise PanelError(f"causality leakage detected: {leakage}")
    if gold_nonprior:
        raise PanelError(f"gold feature bar is not strictly prior on {gold_nonprior} rows")

    start = pd.Timestamp(cfg["minimum_core_start"], tz="UTC")
    end = pd.Timestamp(cfg["minimum_core_end"], tz="UTC")
    eval_mask = (panel["decision_date_utc"] >= start) & (panel["decision_date_utc"] <= end)
    completeness = {name: float(panel.loc[eval_mask, name].notna().mean()) for name in CORE_SERIES}
    min_complete = float(cfg["minimum_core_completeness"])
    failing = {k: v for k, v in completeness.items() if v < min_complete}
    if failing:
        raise PanelError(f"core completeness below {min_complete}: {failing}")

    report_dir = root / REPORT_DIR
    report_dir.mkdir(parents=True, exist_ok=True)
    panel_path = report_dir / "macro_causal_features.csv"
    target_path = report_dir / "macro_causal_targets.csv"
    panel.to_csv(panel_path, index=False)
    targets.to_csv(target_path, index=False)

    source_selection = {
        "program": PROGRAM,
        "generated_utc": now_utc(),
        "selected": selected,
        "gold": source_meta(gold_path, root) | {
            "rows": len(gold_bars),
            "first_date": gold_bars["gold_bar_date_utc"].min().isoformat(),
            "last_date": gold_bars["gold_bar_date_utc"].max().isoformat(),
        },
        "cftc": source_meta(cftc_path, root),
        "events": source_meta(events_path, root),
        "etf_optional": None if etf_path is None else source_meta(etf_path, root),
        "wgc_optional": None if wgc_path is None else source_meta(wgc_path, root),
    }
    atomic_write_json(report_dir / "macro_source_selection.json", source_selection)

    quality = {
        "program": PROGRAM,
        "generated_utc": now_utc(),
        "rows": len(panel),
        "first_date": panel["decision_date_utc"].min().isoformat(),
        "last_date": panel["decision_date_utc"].max().isoformat(),
        "core_completeness_2012_2024": completeness,
        "causality_leakage_counts": leakage,
        "gold_feature_nonprior_rows": gold_nonprior,
        "feature_target_alignment_rows": len(panel),
        "decision_semantics": "D 00:00 UTC decision using previous completed gold D1 bar; entry at D open; exit at close h trading rows later.",
        "event_rows": len(events),
        "optional_etf_present": etf is not None,
        "optional_wgc_present": wgc is not None,
        "reference_rows": int((panel["decision_date_utc"] <= pd.Timestamp(cfg["reference_end"], tz="UTC")).sum()),
        "diagnostic_2025_plus_rows": int((panel["decision_date_utc"] >= pd.Timestamp(cfg["diagnostic_start"], tz="UTC")).sum()),
    }
    atomic_write_json(report_dir / "macro_panel_quality.json", quality)

    contract = {
        "program": PROGRAM,
        "generated_utc": now_utc(),
        "feature_availability": "Decision at D 00:00 UTC uses the previous completed gold D1 bar; FRED daily closes are usable from next UTC day; CFTC/ETF/WGC use explicit available_after timestamps; official events are blackout flags only.",
        "execution_semantics": "Enter at D open and exit at close h trading rows after entry; no same-day gold OHLC is present in features.",
        "reference_selection_window": [cfg["reference_start"], cfg["reference_end"]],
        "post_2025_role": "SEEN_DIAGNOSTIC_NOT_PRISTINE_HOLDOUT",
        "target_columns_are_future_only": True,
        "paper_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
    }
    atomic_write_json(report_dir / "macro_panel_contract.json", contract)

    result = {
        "program": PROGRAM,
        "generated_utc": now_utc(),
        "decision": "PASS_CAUSAL_MACRO_PANEL_GOLD_ASOF_REPAIRED_READY_FOR_REFERENCE_THESIS_SCAN",
        "pass": True,
        "paper_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
        "features_csv": str(panel_path.resolve()),
        "targets_csv": str(target_path.resolve()),
        "rows": len(panel),
        "quality": quality,
        "required_next_action": "RUN_FIXED_REFERENCE_ONLY_MACRO_THESIS_SCAN",
    }
    atomic_write_json(report_dir / "macro_panel_summary.json", result)
    failure = report_dir / "macro_panel_failure.json"
    if failure.exists():
        failure.unlink()
    return result


def collect(root: Path) -> dict[str, Any]:
    report_dir = root / REPORT_DIR
    summary_path = report_dir / "macro_panel_summary.json"
    if not summary_path.is_file():
        raise PanelError(f"macro panel summary missing: {summary_path}")
    names = [
        "macro_panel_preflight.json",
        "gvz_fetch_summary.json",
        "macro_source_selection.json",
        "macro_panel_quality.json",
        "macro_panel_contract.json",
        "macro_panel_summary.json",
        "macro_causal_features.csv",
        "macro_causal_targets.csv",
    ]
    files = [report_dir / name for name in names if (report_dir / name).is_file()]
    console = root / "xauusd_macro_panel_console.txt"
    if console.is_file():
        files.append(console)
    output = Path.home() / "Downloads/XAUUSD_MACRO_CAUSAL_PANEL_V1_1_RESULTS.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {"program": PROGRAM, "generated_utc": now_utc(), "files": []}
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path in files:
            arc = f"reports/{path.name}" if path.parent == report_dir else path.name
            archive.write(path, arc)
            manifest["files"].append({"archive_path": arc, "sha256": sha256_file(path), "size": path.stat().st_size})
        archive.writestr("RESULTS_MANIFEST.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return {
        "program": PROGRAM,
        "generated_utc": now_utc(),
        "decision": "PASS_MACRO_CAUSAL_PANEL_RESULTS_PACK_CREATED",
        "pass": True,
        "output": str(output.resolve()),
        "files": len(files),
        "paper_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
    }


def fail(root: Path, exc: Exception) -> dict[str, Any]:
    result = {
        "program": PROGRAM,
        "generated_utc": now_utc(),
        "decision": "MACRO_CAUSAL_PANEL_FAIL_CLOSED",
        "pass": False,
        "error": f"{type(exc).__name__}: {exc}",
        "paper_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
    }
    atomic_write_json(root / REPORT_DIR / "macro_panel_failure.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("preflight", "build", "collect"):
        p = sub.add_parser(name)
        p.add_argument("--root", default=".")
        p.add_argument("--config")
    p = sub.add_parser("fetch-gvz")
    p.add_argument("--root", default=".")
    p.add_argument("--source-file")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        if args.command == "preflight":
            result = preflight(root, Path(args.config).resolve() if args.config else None)
        elif args.command == "fetch-gvz":
            result = fetch_gvz(root, Path(args.source_file).resolve() if args.source_file else None)
        elif args.command == "build":
            result = build(root, Path(args.config).resolve() if args.config else None)
        elif args.command == "collect":
            result = collect(root)
        else:
            raise AssertionError(args.command)
        print(json.dumps(result, indent=2, default=str))
        return 0
    except Exception as exc:
        result = fail(root, exc)
        print(json.dumps(result, indent=2, default=str))
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
