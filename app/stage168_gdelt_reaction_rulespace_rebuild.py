#!/usr/bin/env python3
"""
Stage168 GDELT Reaction Rulespace Rebuild

Commercial-purpose, read-only rulespace rebuild after Stage167C showed that the
hard-coded medium-frequency event rules produced no commercial holdout candidate.

This stage uses the Stage166-compatible historical event panel, preferably built
from Stage166F/GDELT, and scans a broader post-event reaction surface:
- event score family / directional prior
- positive-train event thresholds
- entry lags after the event hour
- price confirmation modes
- exit horizons
- train/newest-holdout validation with cost/slippage proxy

It does NOT write MT5 execution files and does NOT authorize demo/live orders.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

STAGE = "Stage168_GDELT_REACTION_RULESPACE_REBUILD"


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def normalize_col(c: Any) -> str:
    s = str(c).strip().strip("\ufeff")
    s = re.sub(r"[<>]", "", s)
    return s.lower().replace(" ", "_").replace("-", "_")


def read_csv_auto(path: Path, nrows: Optional[int] = None) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(str(path))
    seps = ["\t", ",", ";", "|"]
    best_sep = ","
    best_score = -1
    for sep in seps:
        try:
            sample = pd.read_csv(path, sep=sep, nrows=5)
            score = len(sample.columns)
            if score > best_score:
                best_sep = sep
                best_score = score
        except Exception:
            continue
    return pd.read_csv(path, sep=best_sep, nrows=nrows)


def load_bars(path: Path, timestamp_shift_hours: float = -3.0) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    raw = read_csv_auto(path)
    raw_columns = list(raw.columns)
    raw.columns = [normalize_col(c) for c in raw.columns]
    meta: Dict[str, Any] = {
        "source_path": str(path),
        "raw_columns": raw_columns,
        "raw_row_count": int(len(raw)),
        "timestamp_shift_hours": timestamp_shift_hours,
    }

    if "date" in raw.columns and "time" in raw.columns:
        ts = pd.to_datetime(
            raw["date"].astype(str).str.strip() + " " + raw["time"].astype(str).str.strip(),
            format="%Y.%m.%d %H:%M:%S",
            errors="coerce",
            utc=False,
        )
        ts = ts + pd.to_timedelta(timestamp_shift_hours, unit="h")
        ts = pd.to_datetime(ts, utc=True, errors="coerce")
        meta["parse_mode"] = "mt5_split_date_time"
    else:
        time_col = None
        for c in ["time_utc", "utc_time", "datetime", "timestamp", "server_time", "time", "date"]:
            if c in raw.columns:
                time_col = c
                break
        if time_col is None:
            for c in raw.columns:
                if any(x in c for x in ["date", "time", "utc"]):
                    time_col = c
                    break
        if time_col is None:
            raise ValueError(f"No timestamp column found in {path}; columns={list(raw.columns)}")
        ts = pd.to_datetime(raw[time_col], errors="coerce", utc=True)
        if timestamp_shift_hours and time_col not in {"time_utc", "utc_time"}:
            ts = ts + pd.to_timedelta(timestamp_shift_hours, unit="h")
        meta["parse_mode"] = f"single_timestamp:{time_col}"

    out = pd.DataFrame({"time_utc": ts})
    colmap = {
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "tickvol": "volume",
        "tick_volume": "volume",
        "vol": "real_volume",
        "volume": "volume",
        "spread": "spread",
        "spread_points": "spread",
    }
    for src, dst in colmap.items():
        if src in raw.columns:
            out[dst] = pd.to_numeric(raw[src], errors="coerce")
    for c in ["open", "high", "low", "close"]:
        if c not in out.columns:
            raise ValueError(f"Missing OHLC column {c}; columns={list(raw.columns)}")
    if "spread" not in out.columns:
        out["spread"] = float("nan")
    if "volume" not in out.columns:
        out["volume"] = 0.0
    out = out.dropna(subset=["time_utc", "open", "high", "low", "close"]).copy()
    out = out.sort_values("time_utc").drop_duplicates("time_utc", keep="last").reset_index(drop=True)
    meta.update({
        "bar_count": int(len(out)),
        "min_time_utc": str(out["time_utc"].min()) if len(out) else None,
        "max_time_utc": str(out["time_utc"].max()) if len(out) else None,
        "spread_nonnull_pct": float(out["spread"].notna().mean() * 100.0) if len(out) else 0.0,
    })
    return out, meta


def load_event_panel(path: Path) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    raw = read_csv_auto(path)
    raw_columns = list(raw.columns)
    raw.columns = [normalize_col(c) for c in raw.columns]
    time_col = None
    for c in ["time_bucket_utc", "time_utc", "utc_time", "datetime", "timestamp"]:
        if c in raw.columns:
            time_col = c
            break
    if time_col is None:
        raise ValueError(f"No event time column found in {path}; columns={list(raw.columns)}")
    raw["time_utc"] = pd.to_datetime(raw[time_col], errors="coerce", utc=True)
    raw = raw.dropna(subset=["time_utc"]).copy()
    numeric_defaults = [
        "event_count", "gold_long_pressure", "gold_short_pressure", "shock_abs",
        "geopolitical_escalation_score", "deescalation_score", "macro_policy_hawkish_score",
        "macro_policy_dovish_score", "inflation_energy_shock_score", "market_stress_score",
        "central_bank_gold_score", "net_gold_event_pressure", "gold_direct_score", "event_count_weighted",
    ]
    for c in numeric_defaults:
        if c not in raw.columns:
            raw[c] = 0.0
        raw[c] = pd.to_numeric(raw[c], errors="coerce").fillna(0.0)
    if "event_side_bias" not in raw.columns:
        raw["event_side_bias"] = raw["net_gold_event_pressure"].apply(lambda x: "LONG" if x > 0 else ("SHORT" if x < 0 else "NEUTRAL"))
    if "event_shock_regime" not in raw.columns:
        raw["event_shock_regime"] = raw["shock_abs"].apply(lambda x: "SHOCK" if x > 0 else "NO_EVENT")
    raw = raw.sort_values("time_utc").drop_duplicates("time_utc", keep="last").reset_index(drop=True)
    meta = {
        "event_panel_path": str(path),
        "raw_columns": raw_columns,
        "row_count": int(len(raw)),
        "min_time_utc": str(raw["time_utc"].min()) if len(raw) else None,
        "max_time_utc": str(raw["time_utc"].max()) if len(raw) else None,
        "columns": list(raw.columns),
    }
    return raw, meta


def timeframe_minutes(bars: pd.DataFrame) -> int:
    if len(bars) < 3:
        return 5
    d = bars["time_utc"].sort_values().diff().dropna().dt.total_seconds() / 60.0
    med = float(d.median()) if len(d) else 5.0
    if not math.isfinite(med) or med <= 0:
        return 5
    return max(1, int(round(med)))


def as_bars_with_events(bars: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    event_cols = [c for c in events.columns if c != "time_utc"]
    merged = pd.merge_asof(
        bars.sort_values("time_utc"),
        events[["time_utc"] + event_cols].sort_values("time_utc"),
        on="time_utc",
        direction="backward",
        tolerance=pd.Timedelta("65min"),
    )
    score_cols = [
        "event_count", "gold_long_pressure", "gold_short_pressure", "shock_abs",
        "geopolitical_escalation_score", "deescalation_score", "macro_policy_hawkish_score",
        "macro_policy_dovish_score", "inflation_energy_shock_score", "market_stress_score",
        "central_bank_gold_score", "net_gold_event_pressure", "gold_direct_score", "event_count_weighted",
    ]
    for c in score_cols:
        if c not in merged.columns:
            merged[c] = 0.0
        merged[c] = pd.to_numeric(merged[c], errors="coerce").fillna(0.0)
    if "event_side_bias" not in merged.columns:
        merged["event_side_bias"] = "NEUTRAL"
    merged["event_side_bias"] = merged["event_side_bias"].fillna("NEUTRAL")
    merged["event_any"] = merged["shock_abs"].fillna(0.0) > 0
    return merged.reset_index(drop=True)


def add_price_features(df: pd.DataFrame, tfm: int) -> pd.DataFrame:
    out = df.copy()
    for minutes in [30, 60, 120, 240, 480, 1440]:
        n = max(1, int(round(minutes / tfm)))
        out[f"mom_{minutes}m_bps"] = (out["close"] / out["close"].shift(n) - 1.0) * 10000.0
        out[f"range_{minutes}m_bps"] = ((out["high"].rolling(n, min_periods=max(2, min(n, 12))).max() - out["low"].rolling(n, min_periods=max(2, min(n, 12))).min()) / out["close"]) * 10000.0
    prev_close = out["close"].shift(1)
    tr = pd.concat([
        (out["high"] - out["low"]).abs(),
        (out["high"] - prev_close).abs(),
        (out["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    out["atr_240m_bps"] = (tr.rolling(max(2, int(round(240 / tfm))), min_periods=2).mean() / out["close"]) * 10000.0
    out["hour_utc"] = out["time_utc"].dt.hour
    out["session"] = out["hour_utc"].apply(lambda h: "ASIA" if h < 7 else ("LONDON" if h < 13 else ("NY" if h < 21 else "LATE")))
    return out


def positive_quantile(series: pd.Series, q: float, fallback: float = 0.0) -> float:
    s = pd.to_numeric(series, errors="coerce").dropna()
    s = s[s > 0]
    if len(s) == 0:
        return fallback
    return float(s.quantile(q))


def compute_thresholds(train: pd.DataFrame) -> Dict[str, float]:
    thresholds: Dict[str, float] = {}
    for c in [
        "shock_abs", "gold_long_pressure", "gold_short_pressure",
        "geopolitical_escalation_score", "deescalation_score", "macro_policy_hawkish_score",
        "macro_policy_dovish_score", "inflation_energy_shock_score", "market_stress_score", "central_bank_gold_score",
    ]:
        for qname, q in [("q40", 0.40), ("q50", 0.50), ("q60", 0.60), ("q70", 0.70), ("q80", 0.80), ("q90", 0.90)]:
            thresholds[f"{c}_{qname}"] = positive_quantile(train.get(c, pd.Series(dtype=float)), q)
        thresholds[f"{c}_positive_count"] = float((pd.to_numeric(train.get(c, pd.Series(dtype=float)), errors="coerce").fillna(0) > 0).sum())
    for c in ["mom_60m_bps", "mom_240m_bps", "atr_240m_bps"]:
        s = pd.to_numeric(train.get(c, pd.Series(dtype=float)), errors="coerce").dropna()
        if len(s):
            thresholds[f"{c}_abs_q55"] = float(s.abs().quantile(0.55))
            thresholds[f"{c}_abs_q70"] = float(s.abs().quantile(0.70))
        else:
            thresholds[f"{c}_abs_q55"] = 0.0
            thresholds[f"{c}_abs_q70"] = 0.0
    return thresholds


@dataclass(frozen=True)
class RuleSpec:
    rule_id: str
    event_column: str
    side: str
    threshold_key: str
    threshold_value: float
    horizon_minutes: int
    entry_lag_minutes: int
    confirmation: str
    session_filter: str
    description: str


def build_rules(th: Dict[str, float]) -> List[RuleSpec]:
    event_families = [
        ("shock_abs", "LONG", "GENERAL_SHOCK_LONG"),
        ("shock_abs", "SHORT", "GENERAL_SHOCK_SHORT"),
        ("gold_long_pressure", "LONG", "NET_LONG_PRESSURE"),
        ("gold_short_pressure", "SHORT", "NET_SHORT_PRESSURE"),
        ("geopolitical_escalation_score", "LONG", "GEOPOL_ESCALATION_LONG"),
        ("inflation_energy_shock_score", "LONG", "INFLATION_ENERGY_LONG"),
        ("market_stress_score", "LONG", "MARKET_STRESS_LONG"),
        ("central_bank_gold_score", "LONG", "CB_GOLD_LONG"),
        ("macro_policy_dovish_score", "LONG", "DOVISH_MACRO_LONG"),
        ("deescalation_score", "SHORT", "DEESCALATION_SHORT"),
        ("macro_policy_hawkish_score", "SHORT", "HAWKISH_MACRO_SHORT"),
    ]
    q_levels = ["q40", "q60", "q80"]
    horizons = [60, 120, 240, 480, 1440]
    lags = [0, 60, 180, 360, 720]
    confirmations = ["NONE", "MOM60_ALIGN", "MOM240_ALIGN", "MOM60_FADE", "HIGH_VOL"]
    sessions = ["ALL", "LONDON_NY"]
    out: List[RuleSpec] = []
    for event_col, side, family in event_families:
        for ql in q_levels:
            tk = f"{event_col}_{ql}"
            tv = float(th.get(tk, 0.0))
            if not math.isfinite(tv) or tv <= 0:
                continue
            for h in horizons:
                for lag in lags:
                    for conf in confirmations:
                        for sess in sessions:
                            rid = f"D168_{family}_{ql}_{conf}_{sess}_{lag}L_{h}H"
                            out.append(RuleSpec(
                                rule_id=rid,
                                event_column=event_col,
                                side=side,
                                threshold_key=tk,
                                threshold_value=tv,
                                horizon_minutes=h,
                                entry_lag_minutes=lag,
                                confirmation=conf,
                                session_filter=sess,
                                description=f"{side} after {event_col}>={ql} with {conf}, lag={lag}m, horizon={h}m, session={sess}",
                            ))
    return out


def condition_for_rule(df: pd.DataFrame, spec: RuleSpec, th: Dict[str, float]) -> pd.Series:
    cond = pd.to_numeric(df.get(spec.event_column, pd.Series(index=df.index, data=0.0)), errors="coerce").fillna(0.0) >= spec.threshold_value
    if spec.event_column == "shock_abs":
        if spec.side == "LONG":
            cond = cond & (pd.to_numeric(df.get("net_gold_event_pressure", 0.0), errors="coerce").fillna(0.0) >= 0)
        else:
            cond = cond & (pd.to_numeric(df.get("net_gold_event_pressure", 0.0), errors="coerce").fillna(0.0) < 0)
    elif spec.side == "LONG":
        cond = cond & (pd.to_numeric(df.get("gold_long_pressure", 0.0), errors="coerce").fillna(0.0) >= pd.to_numeric(df.get("gold_short_pressure", 0.0), errors="coerce").fillna(0.0) * 0.5)
    elif spec.side == "SHORT":
        # For category-specific short rules, do not require short_pressure to dominate; GDELT category itself is the prior.
        cond = cond

    if spec.session_filter == "LONDON_NY":
        cond = cond & df["session"].isin(["LONDON", "NY"])

    mom60 = pd.to_numeric(df.get("mom_60m_bps", 0.0), errors="coerce").fillna(0.0)
    mom240 = pd.to_numeric(df.get("mom_240m_bps", 0.0), errors="coerce").fillna(0.0)
    atr = pd.to_numeric(df.get("atr_240m_bps", 0.0), errors="coerce").fillna(0.0)
    mom60_floor = float(th.get("mom_60m_bps_abs_q55", 0.0))
    mom240_floor = float(th.get("mom_240m_bps_abs_q55", 0.0))
    atr_floor = float(pd.to_numeric(atr, errors="coerce").quantile(0.55)) if len(atr.dropna()) else 0.0
    if spec.confirmation == "MOM60_ALIGN":
        cond = cond & ((mom60 > mom60_floor) if spec.side == "LONG" else (mom60 < -mom60_floor))
    elif spec.confirmation == "MOM240_ALIGN":
        cond = cond & ((mom240 > mom240_floor) if spec.side == "LONG" else (mom240 < -mom240_floor))
    elif spec.confirmation == "MOM60_FADE":
        cond = cond & ((mom60 < -mom60_floor) if spec.side == "LONG" else (mom60 > mom60_floor))
    elif spec.confirmation == "HIGH_VOL":
        cond = cond & (atr >= atr_floor)
    return cond.fillna(False)


def effective_cost_bps(close: float, spread_points: Any, fixed_cost_bps: float, spread_point_size: float) -> float:
    try:
        sp = float(spread_points)
        px = float(close)
        if math.isfinite(sp) and sp >= 0 and math.isfinite(px) and px > 0:
            return fixed_cost_bps + (sp * spread_point_size / px * 10000.0)
    except Exception:
        pass
    return fixed_cost_bps


def select_entries(cond: pd.Series, lag_bars: int, horizon_bars: int, cooldown_bars: int, n: int) -> List[int]:
    raw_idx = list(cond[cond].index.astype(int))
    entries: List[int] = []
    next_allowed = 0
    max_entry = n - horizon_bars - 1
    for i in raw_idx:
        e = int(i) + lag_bars
        if e < 0 or e > max_entry:
            continue
        if e < next_allowed:
            continue
        entries.append(e)
        next_allowed = e + max(cooldown_bars, max(1, horizon_bars // 2))
    return entries


def evaluate_rule(
    df: pd.DataFrame,
    spec: RuleSpec,
    th: Dict[str, float],
    tfm: int,
    fixed_cost_bps: float,
    spread_point_size: float,
    split_index: int,
    min_event_dependency_ratio_window_hours: int = 24,
) -> Tuple[Dict[str, Any], pd.DataFrame]:
    horizon_bars = max(1, int(round(spec.horizon_minutes / tfm)))
    lag_bars = max(0, int(round(spec.entry_lag_minutes / tfm)))
    cooldown_bars = max(1, int(round(max(spec.horizon_minutes, 240) / tfm)))
    cond = condition_for_rule(df, spec, th)
    entries = select_entries(cond, lag_bars, horizon_bars, cooldown_bars, len(df))
    rows: List[Dict[str, Any]] = []
    side_mult = 1.0 if spec.side == "LONG" else -1.0
    for e in entries:
        x = e + horizon_bars
        if x >= len(df):
            continue
        entry = float(df.at[e, "close"])
        exit_px = float(df.at[x, "close"])
        gross_bps = side_mult * (exit_px / entry - 1.0) * 10000.0
        cost = effective_cost_bps(entry, df.at[e, "spread"] if "spread" in df.columns else float("nan"), fixed_cost_bps, spread_point_size)
        rows.append({
            "rule_id": spec.rule_id,
            "entry_index": int(e),
            "exit_index": int(x),
            "entry_time_utc": df.at[e, "time_utc"],
            "exit_time_utc": df.at[x, "time_utc"],
            "side": spec.side,
            "entry_close": entry,
            "exit_close": exit_px,
            "gross_bps": gross_bps,
            "cost_bps": cost,
            "net_bps": gross_bps - cost,
            "split": "TRAIN" if e < split_index else "HOLDOUT",
            "event_column": spec.event_column,
            "event_value": float(pd.to_numeric(pd.Series([df.at[e, spec.event_column] if spec.event_column in df.columns else 0.0]), errors="coerce").fillna(0).iloc[0]),
            "confirmation": spec.confirmation,
            "session": df.at[e, "session"],
            "horizon_minutes": spec.horizon_minutes,
            "entry_lag_minutes": spec.entry_lag_minutes,
        })
    tr = pd.DataFrame(rows)

    def metrics(part: pd.DataFrame, prefix: str) -> Dict[str, Any]:
        if len(part) == 0:
            return {
                f"{prefix}_events": 0,
                f"{prefix}_mean_net_bps": float("nan"),
                f"{prefix}_median_net_bps": float("nan"),
                f"{prefix}_hit_rate": float("nan"),
                f"{prefix}_p10_net_bps": float("nan"),
                f"{prefix}_p90_net_bps": float("nan"),
                f"{prefix}_profit_factor": float("nan"),
                f"{prefix}_max_drawdown_proxy_bps": float("nan"),
            }
        r = pd.to_numeric(part["net_bps"], errors="coerce").dropna()
        pos = r[r > 0].sum()
        neg = -r[r < 0].sum()
        equity = r.cumsum()
        dd = (equity - equity.cummax()).min() if len(equity) else float("nan")
        return {
            f"{prefix}_events": int(len(r)),
            f"{prefix}_mean_net_bps": float(r.mean()) if len(r) else float("nan"),
            f"{prefix}_median_net_bps": float(r.median()) if len(r) else float("nan"),
            f"{prefix}_hit_rate": float((r > 0).mean()) if len(r) else float("nan"),
            f"{prefix}_p10_net_bps": float(r.quantile(0.10)) if len(r) else float("nan"),
            f"{prefix}_p90_net_bps": float(r.quantile(0.90)) if len(r) else float("nan"),
            f"{prefix}_profit_factor": float(pos / neg) if neg > 0 else (float("inf") if pos > 0 else float("nan")),
            f"{prefix}_max_drawdown_proxy_bps": float(dd) if math.isfinite(float(dd)) else float("nan"),
        }

    score: Dict[str, Any] = asdict(spec)
    train_tr = tr[tr["split"] == "TRAIN"] if len(tr) else tr
    hold_tr = tr[tr["split"] == "HOLDOUT"] if len(tr) else tr
    score.update(metrics(train_tr, "train"))
    score.update(metrics(hold_tr, "holdout"))
    # Proxy for dependency on very few clustered event spikes: share of trades in most common calendar day.
    if len(tr):
        day_counts = pd.to_datetime(tr["entry_time_utc"], utc=True).dt.date.value_counts()
        score["max_single_day_trade_share"] = float(day_counts.max() / len(tr)) if len(day_counts) else 0.0
    else:
        score["max_single_day_trade_share"] = float("nan")
    return score, tr


def apply_gates(score: Dict[str, Any], args: argparse.Namespace) -> List[str]:
    reasons: List[str] = []
    def val(k: str, default: float = float("nan")) -> float:
        try:
            return float(score.get(k, default))
        except Exception:
            return default
    if val("train_events", 0) < args.min_train_events:
        reasons.append("TRAIN_EVENTS_LT_MIN")
    if val("holdout_events", 0) < args.min_holdout_events:
        reasons.append("HOLDOUT_EVENTS_LT_MIN")
    if val("train_mean_net_bps") < args.min_train_mean_bps:
        reasons.append("TRAIN_MEAN_LT_MIN")
    if val("holdout_mean_net_bps") < args.min_holdout_mean_bps:
        reasons.append("HOLDOUT_MEAN_LT_MIN")
    if val("train_hit_rate") < args.min_train_hit_rate:
        reasons.append("TRAIN_HIT_LT_MIN")
    if val("holdout_hit_rate") < args.min_holdout_hit_rate:
        reasons.append("HOLDOUT_HIT_LT_MIN")
    if val("holdout_p10_net_bps") < args.min_holdout_p10_bps:
        reasons.append("HOLDOUT_LEFT_TAIL_TOO_WEAK")
    if val("max_single_day_trade_share", 1.0) > args.max_single_day_trade_share:
        reasons.append("TOO_CLUSTERED_IN_SINGLE_DAY")
    return reasons


def sort_scores(df: pd.DataFrame) -> pd.DataFrame:
    if len(df) == 0:
        return df
    for c in ["holdout_mean_net_bps", "train_mean_net_bps", "holdout_hit_rate", "train_hit_rate"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values(
        ["is_commercial_candidate", "holdout_mean_net_bps", "holdout_hit_rate", "train_mean_net_bps", "train_events"],
        ascending=[False, False, False, False, False],
    ).reset_index(drop=True)


def write_decision(out_path: Path, summary: Dict[str, Any], top_failed: pd.DataFrame) -> None:
    lines: List[str] = []
    lines.append("# Stage168 GDELT Reaction Rulespace Rebuild")
    lines.append("")
    lines.append(f"Generated UTC: `{summary['generated_utc']}`")
    lines.append("")
    lines.append(f"Decision: `{summary['decision']}`")
    lines.append(f"Recommended action: `{summary['recommended_action']}`")
    lines.append("")
    lines.append("## Core rule")
    lines.append("")
    lines.append("Do not wait for more low-frequency samples. If the broadened event-reaction surface cannot pass newest holdout after costs, kill or redesign the event thesis.")
    lines.append("")
    lines.append("## Counts")
    lines.append("")
    ec = summary["evaluation_context"]
    lines.append(f"Rules scanned: `{ec['rule_spec_count']}`")
    lines.append(f"Scores: `{ec['score_count']}`")
    lines.append(f"Commercial shortlist: `{ec['shortlist_count']}`")
    lines.append("")
    lines.append("## Event panel health")
    lines.append("")
    eh = summary["event_panel_health"]
    lines.append(f"Panel rows: `{eh['panel_rows']}`")
    lines.append(f"Train active event bars: `{eh['train_active_event_bars']}`")
    lines.append(f"Holdout active event bars: `{eh['holdout_active_event_bars']}`")
    lines.append(f"Trainable: `{eh['event_overlay_trainable']}`")
    lines.append("")
    if len(top_failed):
        lines.append("## Top failed candidates for diagnosis")
        lines.append("")
        cols = [
            "rule_id", "event_column", "side", "entry_lag_minutes", "horizon_minutes", "confirmation",
            "train_events", "train_mean_net_bps", "train_hit_rate", "holdout_events", "holdout_mean_net_bps", "holdout_hit_rate", "kill_reasons",
        ]
        lines.append(top_failed[[c for c in cols if c in top_failed.columns]].head(20).to_markdown(index=False))
        lines.append("")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> Dict[str, Any]:
    root = Path(args.root).expanduser().resolve()
    out_dir = root / "reports" / "stage168_gdelt_reaction_rulespace_rebuild"
    ensure_dir(out_dir)

    bars, bars_meta = load_bars(Path(args.bars_m5).expanduser(), args.timestamp_shift_hours)
    event_panel, event_meta = load_event_panel(Path(args.event_panel).expanduser())
    tfm = timeframe_minutes(bars)
    df = as_bars_with_events(bars, event_panel)
    df = add_price_features(df, tfm)
    df = df.dropna(subset=["close"]).reset_index(drop=True)

    split_index = int(len(df) * (1.0 - args.holdout_pct))
    split_index = max(1, min(split_index, len(df) - 1))
    train = df.iloc[:split_index].copy()
    holdout = df.iloc[split_index:].copy()
    thresholds = compute_thresholds(train)
    health = {
        "panel_rows": int(len(event_panel)),
        "feature_rows": int(len(df)),
        "train_rows": int(len(train)),
        "holdout_rows": int(len(holdout)),
        "train_active_event_bars": int((train["shock_abs"] > 0).sum()),
        "holdout_active_event_bars": int((holdout["shock_abs"] > 0).sum()),
        "min_train_active_event_bars": int(args.min_train_active_event_bars),
        "event_overlay_trainable": bool((train["shock_abs"] > 0).sum() >= args.min_train_active_event_bars),
    }

    rules = build_rules(thresholds)
    all_scores: List[Dict[str, Any]] = []
    top_trades: List[pd.DataFrame] = []
    full_trades: List[pd.DataFrame] = []
    if health["event_overlay_trainable"]:
        for spec in rules:
            score, trades = evaluate_rule(df, spec, thresholds, tfm, args.cost_bps, args.spread_point_size, split_index)
            reasons = apply_gates(score, args)
            score["kill_reasons"] = ";".join(reasons)
            score["is_commercial_candidate"] = len(reasons) == 0
            all_scores.append(score)
            if len(trades) and (len(top_trades) < args.top_trade_rule_limit or score["is_commercial_candidate"]):
                full_trades.append(trades if args.export_all_rule_trades else pd.DataFrame())
        # After scoring, select top rule trades only for output.
        scores_df_tmp = sort_scores(pd.DataFrame(all_scores))
        top_rule_ids = set(scores_df_tmp.head(args.top_trade_rule_limit)["rule_id"].astype(str).tolist()) if len(scores_df_tmp) else set()
        if top_rule_ids:
            for spec in rules:
                if spec.rule_id in top_rule_ids:
                    _, trades = evaluate_rule(df, spec, thresholds, tfm, args.cost_bps, args.spread_point_size, split_index)
                    if len(trades):
                        top_trades.append(trades)
    scores = sort_scores(pd.DataFrame(all_scores))
    if len(scores):
        shortlist = scores[scores["is_commercial_candidate"] == True].copy()
    else:
        shortlist = pd.DataFrame()

    all_scores_path = out_dir / "stage168_all_reaction_rule_scores.csv"
    shortlist_path = out_dir / "stage168_commercial_shortlist.csv"
    top_trades_path = out_dir / "stage168_top_rule_trades.csv"
    all_trades_path = out_dir / "stage168_all_rule_trades.csv"
    thresholds_path = out_dir / "stage168_train_thresholds.json"
    summary_path = out_dir / "stage168_gdelt_reaction_rulespace_summary.json"
    decision_path = out_dir / "stage168_decision.md"

    scores.to_csv(all_scores_path, index=False)
    shortlist.to_csv(shortlist_path, index=False)
    if top_trades:
        pd.concat(top_trades, ignore_index=True).to_csv(top_trades_path, index=False)
    else:
        pd.DataFrame().to_csv(top_trades_path, index=False)
    if args.export_all_rule_trades and full_trades:
        pd.concat([x for x in full_trades if len(x)], ignore_index=True).to_csv(all_trades_path, index=False)
    else:
        pd.DataFrame().to_csv(all_trades_path, index=False)
    write_json(thresholds_path, thresholds)

    if not health["event_overlay_trainable"]:
        decision = "STAGE168_EVENT_PANEL_NOT_TRAINABLE_STOP"
        recommended = "REBUILD_EVENT_PANEL_BEFORE_RULESPACE_SCAN"
        severity = "HIGH"
    elif len(shortlist) > 0:
        decision = "STAGE168_GDELT_REACTION_CANDIDATES_FOUND_REQUIRES_STAGE169_EXECUTION_REPLAY"
        recommended = "RUN_COSTED_EXECUTION_REPLAY_NO_DEMO_RELEASE"
        severity = "MEDIUM"
    else:
        decision = "STAGE168_NO_COMMERCIAL_GDELT_REACTION_CANDIDATE_KILL_OR_REDESIGN_EVENT_THESIS"
        recommended = "DO_NOT_WAIT; KILL_CURRENT_EVENT_RULESPACE_OR_ADD_STRONGER_LABELED_EVENT_FEATURES"
        severity = "HIGH"

    summary: Dict[str, Any] = {
        "stage": STAGE,
        "generated_utc": now_utc_iso(),
        "root": str(root),
        "order_routing_allowed": False,
        "demo_release_allowed": False,
        "status": "STAGE168_COMPLETE_REACTION_RULESPACE_READY",
        "decision": decision,
        "severity": severity,
        "recommended_action": recommended,
        "bars_m5": str(Path(args.bars_m5).expanduser()),
        "event_panel": str(Path(args.event_panel).expanduser()),
        "bars_meta": bars_meta,
        "event_meta": event_meta,
        "feature_meta": {"timeframe_minutes": int(tfm), "feature_row_count": int(len(df))},
        "split_meta": {
            "row_count": int(len(df)),
            "holdout_pct": float(args.holdout_pct),
            "split_index": int(split_index),
            "train_rows": int(len(train)),
            "holdout_rows": int(len(holdout)),
            "train_start_utc": str(train["time_utc"].min()) if len(train) else None,
            "train_end_utc": str(train["time_utc"].max()) if len(train) else None,
            "holdout_start_utc": str(holdout["time_utc"].min()) if len(holdout) else None,
            "holdout_end_utc": str(holdout["time_utc"].max()) if len(holdout) else None,
        },
        "event_panel_health": health,
        "gate_thresholds": {
            "min_train_events": int(args.min_train_events),
            "min_holdout_events": int(args.min_holdout_events),
            "min_train_mean_bps": float(args.min_train_mean_bps),
            "min_holdout_mean_bps": float(args.min_holdout_mean_bps),
            "min_train_hit_rate": float(args.min_train_hit_rate),
            "min_holdout_hit_rate": float(args.min_holdout_hit_rate),
            "min_holdout_p10_bps": float(args.min_holdout_p10_bps),
            "max_single_day_trade_share": float(args.max_single_day_trade_share),
        },
        "evaluation_context": {
            "rule_spec_count": int(len(rules)),
            "score_count": int(len(scores)),
            "shortlist_count": int(len(shortlist)),
            "candidate_event_columns": sorted(scores["event_column"].dropna().unique().tolist()) if len(scores) and "event_column" in scores.columns else [],
            "pass_event_columns": sorted(shortlist["event_column"].dropna().unique().tolist()) if len(shortlist) and "event_column" in shortlist.columns else [],
            "export_all_rule_trades": bool(args.export_all_rule_trades),
        },
        "top_shortlist_rule_ids": shortlist.head(20)["rule_id"].astype(str).tolist() if len(shortlist) and "rule_id" in shortlist.columns else [],
        "top_score_rule_ids": scores.head(20)["rule_id"].astype(str).tolist() if len(scores) and "rule_id" in scores.columns else [],
        "outputs": {
            "summary_json": str(summary_path),
            "all_rule_scores_csv": str(all_scores_path),
            "commercial_shortlist_csv": str(shortlist_path),
            "top_rule_trades_csv": str(top_trades_path),
            "all_rule_trades_csv": str(all_trades_path),
            "thresholds_json": str(thresholds_path),
            "decision_md": str(decision_path),
        },
        "next": [
            "If shortlist_count is positive, run Stage169 costed execution replay before any demo release.",
            "If shortlist_count is zero, do not wait for more samples; kill or redesign the event thesis with stronger labeled event features.",
            "Do not release demo/live orders from Stage168 output alone.",
        ],
    }
    write_json(summary_path, summary)
    top_failed = scores[scores["is_commercial_candidate"] == False].head(30).copy() if len(scores) else pd.DataFrame()
    write_decision(decision_path, summary, top_failed)
    return summary


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--root", default=".")
    ap.add_argument("--bars-m5", required=True)
    ap.add_argument("--event-panel", required=True)
    ap.add_argument("--timestamp-shift-hours", type=float, default=-3.0)
    ap.add_argument("--holdout-pct", type=float, default=0.20)
    ap.add_argument("--cost-bps", type=float, default=4.0)
    ap.add_argument("--spread-point-size", type=float, default=0.01)
    ap.add_argument("--min-train-active-event-bars", type=int, default=500)
    ap.add_argument("--min-train-events", type=int, default=80)
    ap.add_argument("--min-holdout-events", type=int, default=20)
    ap.add_argument("--min-train-mean-bps", type=float, default=1.0)
    ap.add_argument("--min-holdout-mean-bps", type=float, default=0.25)
    ap.add_argument("--min-train-hit-rate", type=float, default=0.505)
    ap.add_argument("--min-holdout-hit-rate", type=float, default=0.500)
    ap.add_argument("--min-holdout-p10-bps", type=float, default=-50.0)
    ap.add_argument("--max-single-day-trade-share", type=float, default=0.20)
    ap.add_argument("--top-trade-rule-limit", type=int, default=25)
    ap.add_argument("--export-all-rule-trades", action="store_true")
    return ap.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    summary = run(args)
    print(json.dumps({
        "stage": summary["stage"],
        "decision": summary["decision"],
        "severity": summary["severity"],
        "shortlist_count": summary["evaluation_context"]["shortlist_count"],
        "score_count": summary["evaluation_context"]["score_count"],
        "summary_json": summary["outputs"]["summary_json"],
        "decision_md": summary["outputs"]["decision_md"],
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
