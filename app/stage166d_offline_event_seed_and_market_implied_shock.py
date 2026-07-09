#!/usr/bin/env python3
"""
Stage166D Offline Event Seed + Market-Implied Shock Panel

Purpose
-------
Rebuild a trainable current-event/shock panel when online feeds such as GDELT
are inaccessible or too slow. This stage is read-only for execution: it writes
research panels and never authorizes demo/live orders.

Key design
----------
1) Ingest a manual current-event history CSV when available.
2) Build a non-web market-implied post-shock proxy from AMarkets XAUUSD bars.
3) Write a Stage166-compatible intraday panel so Stage167 can be rerun.
4) Report whether the panel is trainable and whether it is external-event-backed
   or only market-implied proxy-backed.

Important caution
-----------------
The market-implied proxy is NOT a substitute for external news history. It uses
lagged post-shock information only, so it is usable for discovering post-shock
behavior, but not for claiming exogenous predictive news edge.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

STAGE = "Stage166D_OFFLINE_EVENT_SEED_AND_MARKET_IMPLIED_SHOCK"

MANUAL_COLUMNS = [
    "event_time_utc",
    "event_end_utc",
    "event_title",
    "event_category",
    "direction",
    "severity_1_5",
    "confidence_0_1",
    "decay_hours",
    "source",
    "notes",
]

CATEGORY_ALIASES = {
    "geopolitical_escalation": "geopolitical_escalation_score",
    "military_conflict": "geopolitical_escalation_score",
    "war": "geopolitical_escalation_score",
    "sanctions": "geopolitical_escalation_score",
    "systemic_risk": "geopolitical_escalation_score",
    "risk_off": "geopolitical_escalation_score",
    "deescalation": "deescalation_score",
    "ceasefire": "deescalation_score",
    "peace_talk": "deescalation_score",
    "risk_on": "deescalation_score",
    "macro_policy_hawkish": "macro_policy_hawkish_score",
    "hawkish_fed": "macro_policy_hawkish_score",
    "rate_hike": "macro_policy_hawkish_score",
    "real_yield_up": "macro_policy_hawkish_score",
    "usd_strength": "macro_policy_hawkish_score",
    "macro_policy_dovish": "macro_policy_dovish_score",
    "dovish_fed": "macro_policy_dovish_score",
    "rate_cut": "macro_policy_dovish_score",
    "real_yield_down": "macro_policy_dovish_score",
    "usd_weakness": "macro_policy_dovish_score",
    "inflation_energy_shock": "inflation_energy_shock_score",
    "energy_shock": "inflation_energy_shock_score",
    "inflation_shock": "inflation_energy_shock_score",
    "oil_shock": "inflation_energy_shock_score",
}

SCORE_COLUMNS = [
    "geopolitical_escalation_score",
    "deescalation_score",
    "macro_policy_hawkish_score",
    "macro_policy_dovish_score",
    "inflation_energy_shock_score",
]


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def normalize_col(c: Any) -> str:
    s = str(c).strip().strip("\ufeff")
    s = s.replace("<", "").replace(">", "")
    return s.lower().replace(" ", "_").replace("-", "_")


def read_csv_auto(path: Path, nrows: Optional[int] = None) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(str(path))
    # MT5 exports are often tab-delimited; event CSVs may be comma/semicolon.
    seps = ["\t", ",", ";"]
    best_sep = ","
    best_cols = -1
    for sep in seps:
        try:
            probe = pd.read_csv(path, sep=sep, nrows=5)
            if len(probe.columns) > best_cols:
                best_cols = len(probe.columns)
                best_sep = sep
        except Exception:
            continue
    return pd.read_csv(path, sep=best_sep, nrows=nrows)


def load_bars(path: Path, timestamp_shift_hours: float) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    df = read_csv_auto(path)
    raw_columns = list(df.columns)
    df.columns = [normalize_col(c) for c in df.columns]
    meta: Dict[str, Any] = {
        "source_path": str(path),
        "raw_columns": raw_columns,
        "raw_row_count": int(len(df)),
        "timestamp_shift_hours": timestamp_shift_hours,
    }

    if "date" in df.columns and "time" in df.columns:
        ts = pd.to_datetime(
            df["date"].astype(str).str.strip() + " " + df["time"].astype(str).str.strip(),
            format="%Y.%m.%d %H:%M:%S",
            errors="coerce",
            utc=False,
        )
        ts = ts + pd.to_timedelta(timestamp_shift_hours, unit="h")
        ts = pd.to_datetime(ts, utc=True, errors="coerce")
        meta["parse_mode"] = "mt5_split_date_time"
    else:
        time_col = None
        for c in ["time_utc", "utc_time", "datetime", "timestamp", "server_time", "time"]:
            if c in df.columns:
                time_col = c
                break
        if not time_col:
            for c in df.columns:
                if any(x in c for x in ["date", "time", "utc"]):
                    time_col = c
                    break
        if not time_col:
            raise ValueError(f"No timestamp column in {path}; columns={list(df.columns)}")
        ts = pd.to_datetime(df[time_col], errors="coerce", utc=True)
        if timestamp_shift_hours and time_col not in {"time_utc", "utc_time"}:
            ts = ts + pd.to_timedelta(timestamp_shift_hours, unit="h")
        meta["parse_mode"] = f"single_timestamp:{time_col}"

    out = pd.DataFrame({"time_utc": ts})
    for c in ["open", "high", "low", "close"]:
        if c not in df.columns:
            raise ValueError(f"Missing OHLC column {c}; columns={list(df.columns)}")
        out[c] = pd.to_numeric(df[c], errors="coerce")
    out["volume"] = pd.to_numeric(df["tickvol"] if "tickvol" in df.columns else df.get("volume", 0.0), errors="coerce").fillna(0.0)
    out["spread"] = pd.to_numeric(df["spread"] if "spread" in df.columns else df.get("spread_points", float("nan")), errors="coerce")
    out = out.dropna(subset=["time_utc", "open", "high", "low", "close"]).sort_values("time_utc").drop_duplicates("time_utc", keep="last").reset_index(drop=True)
    meta.update({
        "bar_count": int(len(out)),
        "min_time_utc": str(out["time_utc"].min()) if len(out) else None,
        "max_time_utc": str(out["time_utc"].max()) if len(out) else None,
        "spread_nonnull_pct": round(float(out["spread"].notna().mean() * 100.0), 4) if len(out) else 0.0,
    })
    return out, meta


def build_hourly_index(bars: pd.DataFrame) -> pd.DataFrame:
    start = pd.to_datetime(bars["time_utc"].min(), utc=True).floor("1D")
    end = pd.to_datetime(bars["time_utc"].max(), utc=True).ceil("1h")
    idx = pd.date_range(start=start, end=end, freq="1h", tz="UTC")
    panel = pd.DataFrame({"time_bucket_utc": idx})
    for c in SCORE_COLUMNS:
        panel[c] = 0.0
    panel["event_count"] = 0.0
    panel["manual_event_count"] = 0.0
    panel["market_implied_event_count"] = 0.0
    panel["manual_gold_long_pressure"] = 0.0
    panel["manual_gold_short_pressure"] = 0.0
    panel["market_implied_long_pressure"] = 0.0
    panel["market_implied_short_pressure"] = 0.0
    return panel


def write_manual_template(path: Path) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MANUAL_COLUMNS)
        writer.writeheader()


def find_manual_event_files(event_inbox: Path, manual_events_csv: Optional[Path]) -> List[Path]:
    candidates: List[Path] = []
    if manual_events_csv:
        candidates.append(manual_events_csv.expanduser())
    default_paths = [
        event_inbox / "manual_current_events.csv",
        event_inbox / "manual_event_history.csv",
        event_inbox / "current_event_history.csv",
        event_inbox / "events" / "manual_current_events.csv",
        event_inbox / "events" / "manual_event_history.csv",
    ]
    for p in default_paths:
        if p not in candidates:
            candidates.append(p)
    return [p for p in candidates if p.exists()]


def load_manual_events(paths: Sequence[Path]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    frames = []
    loaded = []
    errors = []
    for p in paths:
        try:
            df = read_csv_auto(p)
            df.columns = [normalize_col(c) for c in df.columns]
            df["source_file"] = str(p)
            frames.append(df)
            loaded.append(str(p))
        except Exception as e:
            errors.append({"path": str(p), "error": f"{type(e).__name__}:{e}"})
    if not frames:
        return pd.DataFrame(), {"loaded_files": loaded, "errors": errors, "row_count": 0}
    raw = pd.concat(frames, ignore_index=True)
    # Schema aliases
    aliases = {
        "time_utc": "event_time_utc",
        "utc_time": "event_time_utc",
        "timestamp": "event_time_utc",
        "date": "event_time_utc",
        "title": "event_title",
        "category": "event_category",
        "side": "direction",
        "gold_side": "direction",
        "severity": "severity_1_5",
        "confidence": "confidence_0_1",
    }
    for old, new in aliases.items():
        if old in raw.columns and new not in raw.columns:
            raw[new] = raw[old]
    if "event_time_utc" not in raw.columns:
        return pd.DataFrame(), {"loaded_files": loaded, "errors": errors + [{"error": "missing_event_time_utc"}], "row_count": int(len(raw))}
    out = pd.DataFrame()
    out["event_time_utc"] = pd.to_datetime(raw["event_time_utc"], utc=True, errors="coerce")
    out["event_end_utc"] = pd.to_datetime(raw.get("event_end_utc", pd.NaT), utc=True, errors="coerce")
    out["event_title"] = raw.get("event_title", "").astype(str) if "event_title" in raw else ""
    out["event_category"] = raw.get("event_category", "manual_event").astype(str).str.strip().str.lower().str.replace(" ", "_", regex=False) if "event_category" in raw else "manual_event"
    out["direction"] = raw.get("direction", "NONE").astype(str).str.strip().str.upper() if "direction" in raw else "NONE"
    out["severity_1_5"] = pd.to_numeric(raw.get("severity_1_5", 3), errors="coerce").fillna(3).clip(0, 5)
    out["confidence_0_1"] = pd.to_numeric(raw.get("confidence_0_1", 0.7), errors="coerce").fillna(0.7).clip(0, 1)
    out["decay_hours"] = pd.to_numeric(raw.get("decay_hours", 72), errors="coerce").fillna(72).clip(1, 720)
    out["source"] = raw.get("source", "manual").astype(str) if "source" in raw else "manual"
    out["notes"] = raw.get("notes", "").astype(str) if "notes" in raw else ""
    out["source_file"] = raw.get("source_file", "").astype(str) if "source_file" in raw else ""
    out = out.dropna(subset=["event_time_utc"]).sort_values("event_time_utc").reset_index(drop=True)
    return out, {"loaded_files": loaded, "errors": errors, "row_count": int(len(out))}


def add_event_to_panel(panel: pd.DataFrame, event_time: pd.Timestamp, decay_hours: float, score: float, score_col: str, direction: str, manual: bool = True) -> None:
    if panel.empty:
        return
    start = event_time.floor("1h")
    end = start + pd.Timedelta(hours=float(decay_hours))
    mask = (panel["time_bucket_utc"] >= start) & (panel["time_bucket_utc"] <= end)
    if not mask.any():
        return
    age_hours = (panel.loc[mask, "time_bucket_utc"] - start).dt.total_seconds() / 3600.0
    # Half-life is one third of the event decay window, with lower bound 3h.
    half_life = max(float(decay_hours) / 3.0, 3.0)
    decay = 0.5 ** (age_hours / half_life)
    vals = float(score) * decay
    panel.loc[mask, score_col] += vals.to_numpy()
    panel.loc[mask, "event_count"] += decay.to_numpy()
    if manual:
        panel.loc[mask, "manual_event_count"] += decay.to_numpy()
    else:
        panel.loc[mask, "market_implied_event_count"] += decay.to_numpy()
    direction = str(direction).upper()
    if direction == "LONG":
        if manual:
            panel.loc[mask, "manual_gold_long_pressure"] += vals.to_numpy()
        else:
            panel.loc[mask, "market_implied_long_pressure"] += vals.to_numpy()
    elif direction == "SHORT":
        if manual:
            panel.loc[mask, "manual_gold_short_pressure"] += vals.to_numpy()
        else:
            panel.loc[mask, "market_implied_short_pressure"] += vals.to_numpy()


def apply_manual_events(panel: pd.DataFrame, events: pd.DataFrame) -> Dict[str, Any]:
    if events.empty:
        return {"manual_events_applied": 0}
    applied = 0
    category_counts: Dict[str, int] = {}
    for _, row in events.iterrows():
        category = str(row.get("event_category", "manual_event")).strip().lower().replace(" ", "_")
        score_col = CATEGORY_ALIASES.get(category, "geopolitical_escalation_score" if str(row.get("direction", "")).upper() == "LONG" else "macro_policy_hawkish_score" if str(row.get("direction", "")).upper() == "SHORT" else "geopolitical_escalation_score")
        severity = float(row.get("severity_1_5", 3.0))
        confidence = float(row.get("confidence_0_1", 0.7))
        score = severity * confidence
        decay_hours = float(row.get("decay_hours", 72.0))
        direction = str(row.get("direction", "NONE")).upper()
        # Infer direction from category if not specified.
        if direction not in {"LONG", "SHORT", "NONE"}:
            direction = "NONE"
        if direction == "NONE":
            if score_col in {"geopolitical_escalation_score", "macro_policy_dovish_score", "inflation_energy_shock_score"}:
                direction = "LONG"
            elif score_col in {"deescalation_score", "macro_policy_hawkish_score"}:
                direction = "SHORT"
        add_event_to_panel(panel, pd.to_datetime(row["event_time_utc"], utc=True), decay_hours, score, score_col, direction, manual=True)
        applied += 1
        category_counts[category] = category_counts.get(category, 0) + 1
    return {"manual_events_applied": applied, "manual_category_counts": category_counts}


def hourly_bars(bars: pd.DataFrame) -> pd.DataFrame:
    x = bars.set_index("time_utc").sort_index()
    h = x.resample("1h").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
        "spread": "mean",
    }).dropna(subset=["open", "high", "low", "close"]).reset_index()
    h["time_bucket_utc"] = h["time_utc"].dt.floor("1h")
    h["ret_bps"] = (h["close"] / h["open"] - 1.0) * 10000.0
    h["range_bps"] = (h["high"] / h["low"] - 1.0) * 10000.0
    h["body_bps"] = (h["close"] / h["open"] - 1.0).abs() * 10000.0
    return h


def train_mask_for_hourly(h: pd.DataFrame, bars: pd.DataFrame, holdout_pct: float) -> pd.Series:
    if h.empty:
        return pd.Series([], dtype=bool)
    split_i = int(len(bars) * (1.0 - holdout_pct))
    split_i = max(1, min(split_i, len(bars) - 1))
    split_time = bars.iloc[split_i]["time_utc"]
    return h["time_bucket_utc"] < split_time.floor("1h")


def apply_market_implied_post_shocks(panel: pd.DataFrame, bars: pd.DataFrame, holdout_pct: float, q: float, decay_hours: int, max_events: int) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    h = hourly_bars(bars)
    if h.empty:
        return pd.DataFrame(), {"market_implied_events": 0, "reason": "no_hourly_bars"}
    train_mask = train_mask_for_hourly(h, bars, holdout_pct)
    train = h[train_mask].copy()
    if train.empty:
        return pd.DataFrame(), {"market_implied_events": 0, "reason": "no_train_hourly_bars"}
    abs_ret_thr = float(train["ret_bps"].abs().quantile(q))
    range_thr = float(train["range_bps"].quantile(q))
    # Candidate shock hour if return or range is extreme under train thresholds.
    shock = h[(h["ret_bps"].abs() >= abs_ret_thr) | (h["range_bps"] >= range_thr)].copy()
    shock["shock_strength"] = (shock["ret_bps"].abs() / max(abs_ret_thr, 1e-9)).clip(1, 6)
    shock["direction"] = shock["ret_bps"].apply(lambda v: "LONG" if v > 0 else "SHORT" if v < 0 else "NONE")
    # Limit pathological over-density while keeping chronology.
    if max_events > 0 and len(shock) > max_events:
        shock = shock.sort_values("shock_strength", ascending=False).head(max_events).sort_values("time_bucket_utc")
    applied = 0
    for _, row in shock.iterrows():
        # Shift by one hour to avoid same-bar lookahead. This represents a post-shock regime.
        event_time = pd.to_datetime(row["time_bucket_utc"], utc=True) + pd.Timedelta(hours=1)
        strength = float(row["shock_strength"])
        direction = str(row["direction"])
        score_col = "geopolitical_escalation_score" if direction == "LONG" else "macro_policy_hawkish_score" if direction == "SHORT" else "inflation_energy_shock_score"
        add_event_to_panel(panel, event_time, decay_hours, strength, score_col, direction, manual=False)
        applied += 1
    meta = {
        "market_implied_events": int(applied),
        "hourly_bar_count": int(len(h)),
        "train_hourly_bar_count": int(len(train)),
        "abs_ret_threshold_bps": round(abs_ret_thr, 6),
        "range_threshold_bps": round(range_thr, 6),
        "quantile": q,
        "decay_hours": decay_hours,
        "max_events": max_events,
        "note": "Market-implied shocks are shifted forward one hour to avoid same-hour lookahead; use as post-shock regime proxy only.",
    }
    return shock[["time_bucket_utc", "ret_bps", "range_bps", "shock_strength", "direction"]].copy(), meta


def finalize_panel(panel: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    out["gold_long_pressure"] = out["manual_gold_long_pressure"] + out["market_implied_long_pressure"] + out["geopolitical_escalation_score"] + out["macro_policy_dovish_score"] + out["inflation_energy_shock_score"]
    out["gold_short_pressure"] = out["manual_gold_short_pressure"] + out["market_implied_short_pressure"] + out["deescalation_score"] + out["macro_policy_hawkish_score"]
    out["net_gold_event_pressure"] = out["gold_long_pressure"] - out["gold_short_pressure"]
    out["shock_abs"] = out["net_gold_event_pressure"].abs()

    def regime(row: pd.Series) -> str:
        if row["shock_abs"] <= 0:
            return "NO_CURRENT_EVENT_SHOCK"
        if row["net_gold_event_pressure"] > 0:
            return "GOLD_LONG_EVENT_SHOCK"
        if row["net_gold_event_pressure"] < 0:
            return "GOLD_SHORT_EVENT_SHOCK"
        return "BALANCED_EVENT_SHOCK"

    out["event_shock_regime"] = out.apply(regime, axis=1)
    # Keep Stage166-compatible columns first, preserve diagnostic extras after.
    compat = [
        "time_bucket_utc",
        "event_count",
        "gold_long_pressure",
        "gold_short_pressure",
        "shock_abs",
        "geopolitical_escalation_score",
        "deescalation_score",
        "macro_policy_hawkish_score",
        "macro_policy_dovish_score",
        "inflation_energy_shock_score",
        "net_gold_event_pressure",
        "event_shock_regime",
    ]
    extras = [c for c in out.columns if c not in compat]
    return out[compat + extras]


def evaluate_health(panel: pd.DataFrame, bars: pd.DataFrame, holdout_pct: float, min_train_active_event_bars: int, min_panel_nonzero_rows: int) -> Dict[str, Any]:
    split_i = int(len(bars) * (1.0 - holdout_pct))
    split_i = max(1, min(split_i, len(bars) - 1))
    split_time = bars.iloc[split_i]["time_utc"]
    # As-of hourly panel against M5 bars to count active bars.
    p = panel[["time_bucket_utc", "shock_abs", "gold_long_pressure", "gold_short_pressure", "manual_event_count", "market_implied_event_count"]].copy()
    p["time_bucket_utc"] = pd.to_datetime(p["time_bucket_utc"], utc=True)
    b = bars[["time_utc"]].copy()
    b["time_bucket_utc"] = b["time_utc"].dt.floor("1h")
    joined = b.merge(p, on="time_bucket_utc", how="left").fillna(0.0)
    train = joined[joined["time_utc"] < split_time]
    holdout = joined[joined["time_utc"] >= split_time]
    panel_nonzero = int((panel["shock_abs"] > 0).sum())
    train_active = int((train["shock_abs"] > 0).sum())
    holdout_active = int((holdout["shock_abs"] > 0).sum())
    train_manual_active = int((train["manual_event_count"] > 0).sum())
    train_market_active = int((train["market_implied_event_count"] > 0).sum())
    shock_thresholds_zero = bool(panel.loc[panel["time_bucket_utc"] < split_time.floor("1h"), "shock_abs"].quantile(0.75) <= 0) if len(panel) else True
    trainable = train_active >= min_train_active_event_bars and panel_nonzero >= min_panel_nonzero_rows
    external_backed = train_manual_active >= min_train_active_event_bars
    proxy_backed = train_market_active >= min_train_active_event_bars
    reasons = []
    if panel_nonzero < min_panel_nonzero_rows:
        reasons.append("PANEL_NONZERO_SHOCK_ROWS_LT_MIN")
    if train_active < min_train_active_event_bars:
        reasons.append("TRAIN_ACTIVE_EVENT_BARS_LT_MIN")
    if shock_thresholds_zero:
        reasons.append("TRAIN_SHOCK_Q75_ZERO_OR_LOW")
    if trainable and not external_backed and proxy_backed:
        reasons.append("TRAINABLE_ONLY_AS_MARKET_IMPLIED_PROXY_NOT_EXTERNAL_NEWS")
    return {
        "panel_rows": int(len(panel)),
        "panel_nonzero_shock_rows": panel_nonzero,
        "bar_rows": int(len(bars)),
        "holdout_pct": holdout_pct,
        "split_time_utc": str(split_time),
        "train_rows": int(len(train)),
        "holdout_rows": int(len(holdout)),
        "train_active_event_bars": train_active,
        "holdout_active_event_bars": holdout_active,
        "train_manual_active_event_bars": train_manual_active,
        "train_market_implied_active_event_bars": train_market_active,
        "min_panel_nonzero_rows": min_panel_nonzero_rows,
        "min_train_active_event_bars": min_train_active_event_bars,
        "shock_thresholds_zero_or_low": shock_thresholds_zero,
        "event_overlay_trainable": bool(trainable),
        "external_event_backed": bool(external_backed),
        "market_implied_proxy_backed": bool(proxy_backed),
        "reasons": reasons,
    }


def backup_and_write_compatible(root: Path, panel: pd.DataFrame, backup_existing: bool) -> Tuple[bool, Optional[str], str]:
    target = root / "reports" / "stage166_current_event_shock_overlay" / "stage166_current_event_intraday_panel.csv"
    ensure_dir(target.parent)
    backup = None
    if target.exists() and backup_existing:
        backup = str(target.with_suffix(".pre_stage166d_backup.csv"))
        target.replace(backup)
    panel.to_csv(target, index=False)
    return True, backup, str(target)


def run(args: argparse.Namespace) -> Dict[str, Any]:
    root = Path(args.root).expanduser().resolve()
    event_inbox = Path(args.event_inbox).expanduser().resolve()
    report_dir = root / "reports" / "stage166d_offline_event_seed_and_market_implied_shock"
    ensure_dir(report_dir)
    outputs = {
        "summary_json": str(report_dir / "stage166d_offline_event_seed_summary.json"),
        "manual_event_template_csv": str(report_dir / "stage166d_manual_event_template.csv"),
        "manual_events_normalized_csv": str(report_dir / "stage166d_manual_events_normalized.csv"),
        "market_implied_shocks_csv": str(report_dir / "stage166d_market_implied_shocks.csv"),
        "current_event_intraday_panel_csv": str(report_dir / "stage166d_current_event_intraday_panel.csv"),
        "health_json": str(report_dir / "stage166d_event_panel_health.json"),
    }

    if args.build_template:
        template_path = Path(args.template_path).expanduser() if args.template_path else Path(outputs["manual_event_template_csv"])
        write_manual_template(template_path)

    try:
        bars, bars_meta = load_bars(Path(args.bars_m5).expanduser(), args.timestamp_shift_hours)
        panel = build_hourly_index(bars)
        manual_paths = find_manual_event_files(event_inbox, Path(args.manual_events_csv).expanduser() if args.manual_events_csv else None)
        manual_events, manual_meta = load_manual_events(manual_paths)
        if not manual_events.empty:
            ensure_dir(Path(outputs["manual_events_normalized_csv"]).parent)
            manual_events.to_csv(outputs["manual_events_normalized_csv"], index=False)
        else:
            pd.DataFrame(columns=MANUAL_COLUMNS).to_csv(outputs["manual_events_normalized_csv"], index=False)
        manual_apply_meta = apply_manual_events(panel, manual_events)
        if args.use_market_implied_proxy:
            shock_df, market_meta = apply_market_implied_post_shocks(
                panel=panel,
                bars=bars,
                holdout_pct=args.holdout_pct,
                q=args.market_implied_quantile,
                decay_hours=args.market_implied_decay_hours,
                max_events=args.market_implied_max_events,
            )
        else:
            shock_df = pd.DataFrame(columns=["time_bucket_utc", "ret_bps", "range_bps", "shock_strength", "direction"])
            market_meta = {"market_implied_events": 0, "disabled": True}
        shock_df.to_csv(outputs["market_implied_shocks_csv"], index=False)
        final_panel = finalize_panel(panel)
        final_panel.to_csv(outputs["current_event_intraday_panel_csv"], index=False)
        health = evaluate_health(
            final_panel,
            bars,
            holdout_pct=args.holdout_pct,
            min_train_active_event_bars=args.min_train_active_event_bars,
            min_panel_nonzero_rows=args.min_panel_nonzero_rows,
        )
        write_json(Path(outputs["health_json"]), health)
        compatible_written = False
        compatible_backup = None
        compatible_path = ""
        if args.write_stage166_compatible_panel:
            compatible_written, compatible_backup, compatible_path = backup_and_write_compatible(root, final_panel, args.backup_existing_compatible_panel)

        if health["event_overlay_trainable"] and health["external_event_backed"]:
            decision = "STAGE166D_EXTERNAL_EVENT_PANEL_TRAINABLE_RERUN_STAGE167"
            severity = "MEDIUM"
            recommended_action = "RERUN_STAGE167_WITH_STAGE166D_PANEL_THEN_GATE_HOLDOUT"
        elif health["event_overlay_trainable"] and health["market_implied_proxy_backed"]:
            decision = "STAGE166D_MARKET_IMPLIED_PROXY_TRAINABLE_RERUN_STAGE167_WITH_CAUTION"
            severity = "WARN"
            recommended_action = "RERUN_STAGE167_AS_POST_SHOCK_PROXY_DISCOVERY_NOT_EXTERNAL_NEWS_EDGE"
        else:
            decision = "STAGE166D_EVENT_PANEL_STILL_NOT_TRAINABLE_ADD_MANUAL_EVENT_HISTORY"
            severity = "HIGH"
            recommended_action = "ADD_MANUAL_CURRENT_EVENT_HISTORY_CSV_OR_ALTERNATE_SOURCE_BEFORE_STAGE167"

        summary = {
            "stage": STAGE,
            "generated_utc": now_utc_iso(),
            "root": str(root),
            "order_routing_allowed": False,
            "demo_release_allowed": False,
            "status": "STAGE166D_COMPLETE_OFFLINE_EVENT_PANEL_READY",
            "decision": decision,
            "severity": severity,
            "recommended_action": recommended_action,
            "bars_m5": str(Path(args.bars_m5).expanduser()),
            "event_inbox": str(event_inbox),
            "manual_events_csv": str(Path(args.manual_events_csv).expanduser()) if args.manual_events_csv else None,
            "bars_meta": bars_meta,
            "manual_event_meta": manual_meta,
            "manual_apply_meta": manual_apply_meta,
            "market_implied_meta": market_meta,
            "event_panel_health": health,
            "write_stage166_compatible_panel": bool(args.write_stage166_compatible_panel),
            "compatible_stage166_panel_written": bool(compatible_written),
            "compatible_stage166_panel_backup": compatible_backup,
            "compatible_stage166_panel_csv": compatible_path,
            "outputs": outputs,
            "next": [
                "If decision is EXTERNAL_EVENT_PANEL_TRAINABLE, rerun Stage167 normally.",
                "If decision is MARKET_IMPLIED_PROXY_TRAINABLE, rerun Stage167 only as post-shock proxy discovery and do not claim external news edge.",
                "If decision is STILL_NOT_TRAINABLE, fill the manual event CSV template and rerun Stage166D.",
                "Do not release demo/live orders from Stage166D output alone.",
            ],
        }
        write_json(Path(outputs["summary_json"]), summary)
        return summary
    except Exception as e:
        summary = {
            "stage": STAGE,
            "generated_utc": now_utc_iso(),
            "root": str(root),
            "order_routing_allowed": False,
            "demo_release_allowed": False,
            "status": "STAGE166D_FAILURE_ARTIFACTS_WRITTEN",
            "decision": "STAGE166D_RUN_FAILED_DO_NOT_RUN_STAGE167",
            "severity": "HIGH",
            "recommended_action": "INSPECT_ERROR_AND_FIX_INPUTS",
            "error_type": type(e).__name__,
            "error_message": str(e),
            "outputs": outputs,
        }
        write_json(Path(outputs["summary_json"]), summary)
        return summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Stage166D offline current-event seed and market-implied shock panel")
    p.add_argument("--root", required=True)
    p.add_argument("--bars-m5", required=True)
    p.add_argument("--event-inbox", required=True)
    p.add_argument("--manual-events-csv", default="")
    p.add_argument("--timestamp-shift-hours", type=float, default=-3.0)
    p.add_argument("--holdout-pct", type=float, default=0.20)
    p.add_argument("--build-template", action="store_true")
    p.add_argument("--template-path", default="")
    p.add_argument("--use-market-implied-proxy", action="store_true", default=True)
    p.add_argument("--no-market-implied-proxy", action="store_false", dest="use_market_implied_proxy")
    p.add_argument("--market-implied-quantile", type=float, default=0.985)
    p.add_argument("--market-implied-decay-hours", type=int, default=48)
    p.add_argument("--market-implied-max-events", type=int, default=2500)
    p.add_argument("--min-train-active-event-bars", type=int, default=500)
    p.add_argument("--min-panel-nonzero-rows", type=int, default=1000)
    p.add_argument("--write-stage166-compatible-panel", action="store_true")
    p.add_argument("--backup-existing-compatible-panel", action="store_true")
    return p


if __name__ == "__main__":
    summary = run(build_parser().parse_args())
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
