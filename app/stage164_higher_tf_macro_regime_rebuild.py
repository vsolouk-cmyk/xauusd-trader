#!/usr/bin/env python3
"""
Stage164 Higher-Timeframe Macro-Regime Rebuild Discovery

Read-only discovery after Stage161/163 rejected the current M5 shortlist.
It scans H1/H4/D1-style technical regimes under the current macro pressure
reported by Stage161, with explicit macro-side alignment. It writes reports
only and never writes MT5 KV/order files.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

STAGE = "Stage164B_HIGHER_TF_MACRO_REGIME_REBUILD_PANDAS_FREQ_FIX"
OUT_DIR = Path("reports/stage164_higher_tf_macro_regime_rebuild")

TIME_COL_CANDIDATES = ["time_utc", "utc_time", "datetime", "timestamp", "time", "date"]
RAW_MT5_COLS = {"<DATE>", "<TIME>", "<OPEN>", "<HIGH>", "<LOW>", "<CLOSE>"}


@dataclass(frozen=True)
class CandidateSpec:
    rule_id: str
    timeframe: str
    side: str
    conds: Tuple[Tuple[str, str, float], ...]


def utc_now_iso() -> str:
    return pd.Timestamp.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_out(root: Path) -> Path:
    p = root / OUT_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_csv_auto(path: Path) -> Tuple[pd.DataFrame, str]:
    # Try tab first because AMarkets MT5 exports are TSV with <DATE>/<TIME>.
    best: Optional[Tuple[pd.DataFrame, str, int]] = None
    for sep in ["\t", ",", ";"]:
        try:
            df = pd.read_csv(path, sep=sep)
        except Exception:
            continue
        score = len(df.columns)
        if best is None or score > best[2]:
            best = (df, sep, score)
    if best is None:
        raise ValueError(f"Could not read CSV file: {path}")
    return best[0], best[1]


def load_bars(path: Path, timestamp_shift_hours: float = 0.0) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    df_raw, sep = _read_csv_auto(path)
    meta: Dict[str, Any] = {
        "source_path": str(path),
        "loader_selected_sep": sep,
        "loader_raw_row_count": int(len(df_raw)),
        "loader_raw_columns": list(map(str, df_raw.columns)),
        "loader_parse_mode": "unknown",
    }

    cols = {str(c).strip(): c for c in df_raw.columns}
    df = df_raw.copy()

    if RAW_MT5_COLS.issubset(set(cols.keys())):
        meta["loader_parse_mode"] = "split_date_time_mt5_tsv"
        date_col = cols["<DATE>"]
        time_col = cols["<TIME>"]
        ts = pd.to_datetime(
            df[date_col].astype(str).str.strip() + " " + df[time_col].astype(str).str.strip(),
            format="%Y.%m.%d %H:%M:%S",
            errors="coerce",
            utc=False,
        )
        ts = ts - pd.to_timedelta(timestamp_shift_hours * -1, unit="h") if False else ts + pd.to_timedelta(timestamp_shift_hours, unit="h")
        # timestamp_shift_hours=-3 converts AMarkets server time to UTC.
        ts = ts.dt.tz_localize("UTC")
        mapped = pd.DataFrame(
            {
                "time_utc": ts,
                "open": pd.to_numeric(df[cols["<OPEN>"]], errors="coerce"),
                "high": pd.to_numeric(df[cols["<HIGH>"]], errors="coerce"),
                "low": pd.to_numeric(df[cols["<LOW>"]], errors="coerce"),
                "close": pd.to_numeric(df[cols["<CLOSE>"]], errors="coerce"),
                "volume": pd.to_numeric(df[cols.get("<TICKVOL>", cols["<CLOSE>"])], errors="coerce"),
                "spread": pd.to_numeric(df[cols.get("<SPREAD>", cols["<CLOSE>"])], errors="coerce"),
            }
        )
    else:
        lower = {str(c).lower().strip(): c for c in df.columns}
        tcol = None
        for name in TIME_COL_CANDIDATES:
            if name in lower:
                tcol = lower[name]
                break
        if tcol is None and "server_time" in lower:
            tcol = lower["server_time"]
        if tcol is None:
            raise ValueError(f"No timestamp column found in {path}; columns={list(df.columns)}")
        meta["loader_parse_mode"] = f"single_timestamp_column:{tcol}"
        ts = pd.to_datetime(df[tcol], errors="coerce", utc=True)
        if str(tcol).lower() == "server_time" and timestamp_shift_hours:
            ts = ts + pd.to_timedelta(timestamp_shift_hours, unit="h")
        mapped = pd.DataFrame(
            {
                "time_utc": ts,
                "open": pd.to_numeric(df[lower.get("open")], errors="coerce") if "open" in lower else np.nan,
                "high": pd.to_numeric(df[lower.get("high")], errors="coerce") if "high" in lower else np.nan,
                "low": pd.to_numeric(df[lower.get("low")], errors="coerce") if "low" in lower else np.nan,
                "close": pd.to_numeric(df[lower.get("close")], errors="coerce") if "close" in lower else np.nan,
                "volume": pd.to_numeric(df[lower.get("tick_volume", lower.get("volume", lower.get("real_volume", lower.get("close"))))], errors="coerce") if ("tick_volume" in lower or "volume" in lower or "real_volume" in lower or "close" in lower) else np.nan,
                "spread": pd.to_numeric(df[lower.get("spread_points", lower.get("spread", lower.get("close")))], errors="coerce") if ("spread_points" in lower or "spread" in lower or "close" in lower) else np.nan,
            }
        )

    mapped = mapped.dropna(subset=["time_utc", "open", "high", "low", "close"])
    mapped = mapped.sort_values("time_utc").drop_duplicates("time_utc", keep="last").reset_index(drop=True)
    meta["loader_parseable_row_count"] = int(len(mapped))
    if len(mapped):
        meta["loader_min_time_utc"] = str(mapped["time_utc"].min())
        meta["loader_max_time_utc"] = str(mapped["time_utc"].max())
    return mapped, meta


def resample_ohlc(bars: pd.DataFrame, rule: str) -> pd.DataFrame:
    if bars.empty:
        return bars.copy()
    x = bars.set_index("time_utc").sort_index()
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
        "spread": "mean",
    }
    out = x.resample(rule).agg(agg).dropna(subset=["open", "high", "low", "close"]).reset_index()
    return out


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy().sort_values("time_utc").reset_index(drop=True)
    close = x["close"]
    high = x["high"]
    low = x["low"]
    for n in [1, 2, 3, 6, 12, 24, 48, 96]:
        x[f"ret_{n}_bps"] = (close / close.shift(n) - 1.0) * 10000.0
        x[f"trend_{n}_ema_bps"] = (close / close.ewm(span=max(2, n), adjust=False).mean() - 1.0) * 10000.0
    for n in [12, 24, 48, 96]:
        hh = high.rolling(n, min_periods=max(3, n // 3)).max()
        ll = low.rolling(n, min_periods=max(3, n // 3)).min()
        x[f"range_pos_{n}"] = ((close - ll) / (hh - ll).replace(0, np.nan)) * 100.0
        tr = pd.concat([(high - low), (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(n, min_periods=max(3, n // 3)).mean()
        x[f"atr_{n}_bps"] = atr / close * 10000.0
    return x


def build_candidate_specs(timeframe: str) -> List[CandidateSpec]:
    features = [
        "ret_3_bps", "ret_6_bps", "ret_12_bps", "ret_24_bps", "ret_48_bps",
        "trend_6_ema_bps", "trend_12_ema_bps", "trend_24_ema_bps", "trend_48_ema_bps",
        "range_pos_24", "range_pos_48", "atr_24_bps",
    ]
    specs: List[CandidateSpec] = []
    thresholds: Dict[str, Sequence[Tuple[str, float]]] = {}
    for f in features:
        if f.startswith("range_pos"):
            thresholds[f] = [("<=", 35.0), (">=", 65.0)]
        elif f.startswith("atr"):
            thresholds[f] = [("<=", 12.0), (">=", 25.0), (">=", 40.0)]
        else:
            thresholds[f] = [("<=", -25.0), ("<=", -10.0), (">=", 10.0), (">=", 25.0)]

    for side in ["LONG", "SHORT"]:
        for f, ths in thresholds.items():
            for op, val in ths:
                rid = f"S164_{timeframe}_{side}_{f}_{op.replace('>=','GEQ').replace('<=','LEQ')}{int(abs(val))}"
                specs.append(CandidateSpec(rid, timeframe, side, ((f, op, val),)))

        pair_sets = [
            ("ret_12_bps", "trend_24_ema_bps"),
            ("ret_24_bps", "trend_48_ema_bps"),
            ("range_pos_24", "trend_24_ema_bps"),
            ("ret_6_bps", "range_pos_24"),
            ("trend_12_ema_bps", "atr_24_bps"),
        ]
        for a, b in pair_sets:
            for opa, va in thresholds[a][:2]:
                for opb, vb in thresholds[b][:2]:
                    rid = (
                        f"S164_{timeframe}_{side}_{a}_{opa.replace('>=','GEQ').replace('<=','LEQ')}{int(abs(va))}__"
                        f"{b}_{opb.replace('>=','GEQ').replace('<=','LEQ')}{int(abs(vb))}"
                    )
                    specs.append(CandidateSpec(rid, timeframe, side, ((a, opa, va), (b, opb, vb))))
    return specs


def eval_mask(df: pd.DataFrame, conds: Tuple[Tuple[str, str, float], ...]) -> pd.Series:
    mask = pd.Series(True, index=df.index)
    for col, op, val in conds:
        if col not in df.columns:
            return pd.Series(False, index=df.index)
        if op == ">=":
            mask &= df[col] >= val
        elif op == "<=":
            mask &= df[col] <= val
        else:
            raise ValueError(op)
    return mask.fillna(False)


def fold_label(n: int) -> np.ndarray:
    if n <= 0:
        return np.array([], dtype=object)
    idx = np.arange(n)
    qs = idx / max(1, n - 1)
    labels = np.where(qs < 0.25, "F1_OLD", np.where(qs < 0.50, "F2_MID", np.where(qs < 0.75, "F3_RECENT", "F4_TAIL")))
    return labels.astype(object)


def score_candidates(feat: pd.DataFrame, timeframe: str, horizon_bars: int, macro_supported_sides: Sequence[str]) -> pd.DataFrame:
    x = feat.copy().reset_index(drop=True)
    x["future_ret_bps"] = (x["close"].shift(-horizon_bars) / x["close"] - 1.0) * 10000.0
    x["fold"] = fold_label(len(x))
    usable = x.dropna(subset=["future_ret_bps"]).copy()
    specs = build_candidate_specs(timeframe)
    rows: List[Dict[str, Any]] = []
    supported = set(macro_supported_sides)
    for spec in specs:
        mask = eval_mask(usable, spec.conds)
        sub = usable[mask]
        if sub.empty:
            continue
        pnl = sub["future_ret_bps"] if spec.side == "LONG" else -sub["future_ret_bps"]
        recent = sub[sub["fold"].isin(["F4_TAIL"])]
        recent_pnl = recent["future_ret_bps"] if spec.side == "LONG" else -recent["future_ret_bps"]
        fold_means = {}
        positive_folds = 0
        for fl in ["F1_OLD", "F2_MID", "F3_RECENT", "F4_TAIL"]:
            ss = sub[sub["fold"] == fl]
            if len(ss) == 0:
                fold_means[fl] = np.nan
            else:
                pp = ss["future_ret_bps"] if spec.side == "LONG" else -ss["future_ret_bps"]
                m = float(pp.mean())
                fold_means[fl] = m
                if m > 0:
                    positive_folds += 1
        rows.append(
            {
                "rule_id": spec.rule_id,
                "timeframe": spec.timeframe,
                "side": spec.side,
                "macro_aligned": spec.side in supported,
                "conditions_json": json.dumps(spec.conds),
                "event_count": int(len(sub)),
                "mean_bps": float(pnl.mean()),
                "median_bps": float(pnl.median()),
                "hit_rate": float((pnl > 0).mean()),
                "recent_event_count": int(len(recent)),
                "recent_mean_bps": float(recent_pnl.mean()) if len(recent_pnl) else np.nan,
                "recent_hit_rate": float((recent_pnl > 0).mean()) if len(recent_pnl) else np.nan,
                "positive_folds": int(positive_folds),
                "fold_F1_mean_bps": fold_means["F1_OLD"],
                "fold_F2_mean_bps": fold_means["F2_MID"],
                "fold_F3_mean_bps": fold_means["F3_RECENT"],
                "fold_F4_mean_bps": fold_means["F4_TAIL"],
            }
        )
    return pd.DataFrame(rows)


def classify_macro(stage161: Dict[str, Any]) -> Tuple[str, List[str], str]:
    ctx = stage161.get("macro_context") or {}
    pressure = str(ctx.get("gold_macro_pressure") or "UNKNOWN")
    if "HEADWIND" in pressure:
        return pressure, ["SHORT"], "Headwind for gold: long continuation is conflicted; only short/reversal thesis may be explored."
    if "TAILWIND" in pressure:
        return pressure, ["LONG"], "Tailwind for gold: long-side thesis may be explored."
    return pressure, ["LONG", "SHORT"], "Neutral/unknown macro pressure: both sides are research-only candidates."


def determine_decision(shortlist: pd.DataFrame, current_active: pd.DataFrame) -> Tuple[str, str, str]:
    if shortlist.empty:
        return (
            "STAGE164_NO_HIGHER_TF_MACRO_SUPPORTED_CANDIDATE_KEEP_FREEZE",
            "HIGH",
            "KEEP_STAGE157_FREEZE_AND_WAIT_FOR_REGIME_CHANGE_OR_REBUILD_THESIS",
        )
    if not current_active.empty:
        return (
            "STAGE164_HIGHER_TF_MACRO_SUPPORTED_CANDIDATES_REVIEW_ONLY_NO_DEMO_RELEASE",
            "WARN",
            "MANUALLY_REVIEW_HIGHER_TF_SHORTLIST_AND_BUILD_SEPARATE_EXECUTION_GOVERNANCE_IF_NEEDED",
        )
    return (
        "STAGE164_HIGHER_TF_SHORTLIST_EXISTS_BUT_NOT_CURRENTLY_ACTIVE_NO_DEMO_RELEASE",
        "WARN",
        "KEEP_FREEZE_AND_MONITOR_FOR_CURRENT_ACTIVE_MACRO_ALIGNED_SETUP",
    )


def run(args: argparse.Namespace) -> Dict[str, Any]:
    root = Path(args.root).expanduser().resolve()
    out = ensure_out(root)
    stage161 = read_json(Path(args.stage161_summary).expanduser() if Path(args.stage161_summary).is_absolute() else root / args.stage161_summary)
    macro_pressure, macro_sides, macro_note = classify_macro(stage161)

    loaded_sources: Dict[str, Any] = {}
    base_bars: Optional[pd.DataFrame] = None
    if args.bars_h1:
        h1, meta = load_bars(Path(args.bars_h1).expanduser(), args.timestamp_shift_hours)
        loaded_sources["bars_h1"] = meta
        base_bars = h1
    elif args.bars_m5:
        m5, meta = load_bars(Path(args.bars_m5).expanduser(), args.timestamp_shift_hours)
        loaded_sources["bars_m5"] = meta
        base_bars = m5
    else:
        raise ValueError("Provide --bars-h1 or --bars-m5")

    if base_bars is None or base_bars.empty:
        raise ValueError("No bars loaded")

    tf_rules = []
    if args.scan_h1:
        tf_rules.append(("H1", "1h", max(1, int(round(args.horizon_hours / 1.0)))))
    if args.scan_h4:
        tf_rules.append(("H4", "4h", max(1, int(round(args.horizon_hours / 4.0)))))
    if args.scan_d1:
        tf_rules.append(("D1", "1d", max(1, int(round(args.horizon_hours / 24.0)))))
    if not tf_rules:
        tf_rules = [("H1", "1h", max(1, int(round(args.horizon_hours / 1.0))))]

    all_scores: List[pd.DataFrame] = []
    tf_context: Dict[str, Any] = {}
    for tf, rule, horizon_bars in tf_rules:
        bars_tf = base_bars if (tf == "H1" and args.bars_h1) else resample_ohlc(base_bars, rule)
        feat = add_features(bars_tf)
        scores = score_candidates(feat, tf, horizon_bars, macro_sides)
        if not scores.empty:
            all_scores.append(scores)
        tf_context[tf] = {
            "bar_count": int(len(bars_tf)),
            "feature_row_count": int(len(feat)),
            "horizon_bars": int(horizon_bars),
            "min_time_utc": str(bars_tf["time_utc"].min()) if len(bars_tf) else None,
            "max_time_utc": str(bars_tf["time_utc"].max()) if len(bars_tf) else None,
        }

    candidate_scores = pd.concat(all_scores, ignore_index=True) if all_scores else pd.DataFrame()
    if not candidate_scores.empty:
        shortlist = candidate_scores[
            (candidate_scores["macro_aligned"] == True)
            & (candidate_scores["event_count"] >= args.min_events)
            & (candidate_scores["mean_bps"] >= args.min_mean_bps)
            & (candidate_scores["hit_rate"] >= args.min_hit_rate)
            & (candidate_scores["recent_event_count"] >= max(5, args.min_events // 5))
            & (candidate_scores["recent_mean_bps"] >= args.min_recent_mean_bps)
            & (candidate_scores["positive_folds"] >= args.min_positive_folds)
        ].copy()
        shortlist = shortlist.sort_values(["recent_mean_bps", "mean_bps", "hit_rate"], ascending=[False, False, False])
    else:
        shortlist = pd.DataFrame()

    # Current active means latest feature row satisfies shortlisted conditions.
    current_rows: List[Dict[str, Any]] = []
    if not shortlist.empty:
        # Build latest features per tf once.
        latest_feat: Dict[str, pd.DataFrame] = {}
        for tf, rule, horizon_bars in tf_rules:
            bars_tf = base_bars if (tf == "H1" and args.bars_h1) else resample_ohlc(base_bars, rule)
            latest_feat[tf] = add_features(bars_tf).tail(1).copy()
        for _, row in shortlist.iterrows():
            lf = latest_feat.get(row["timeframe"])
            if lf is None or lf.empty:
                continue
            conds = tuple(tuple(x) for x in json.loads(row["conditions_json"]))
            if bool(eval_mask(lf, conds).iloc[0]):
                current_rows.append(row.to_dict())
    current_active = pd.DataFrame(current_rows)

    decision, severity, action = determine_decision(shortlist, current_active)

    scores_path = out / "stage164_higher_tf_macro_regime_candidate_scores.csv"
    shortlist_path = out / "stage164_higher_tf_macro_regime_shortlist.csv"
    current_path = out / "stage164_higher_tf_macro_regime_current_active.csv"
    context_path = out / "stage164_higher_tf_macro_regime_context.json"
    summary_path = out / "stage164_higher_tf_macro_regime_rebuild_summary.json"

    candidate_scores.to_csv(scores_path, index=False)
    shortlist.to_csv(shortlist_path, index=False)
    current_active.to_csv(current_path, index=False)

    context = {
        "stage": STAGE,
        "generated_utc": utc_now_iso(),
        "macro_pressure": macro_pressure,
        "macro_supported_sides": macro_sides,
        "macro_note": macro_note,
        "loaded_sources": loaded_sources,
        "timeframe_context": tf_context,
        "thresholds": {
            "min_events": args.min_events,
            "min_mean_bps": args.min_mean_bps,
            "min_hit_rate": args.min_hit_rate,
            "min_recent_mean_bps": args.min_recent_mean_bps,
            "min_positive_folds": args.min_positive_folds,
        },
    }
    write_json(context_path, context)

    summary = {
        "stage": STAGE,
        "generated_utc": context["generated_utc"],
        "root": str(root),
        "order_routing_allowed": False,
        "demo_release_allowed": False,
        "status": "STAGE164_COMPLETE_HIGHER_TF_MACRO_REGIME_REBUILD_READY",
        "decision": decision,
        "severity": severity,
        "recommended_action": action,
        "macro_pressure": macro_pressure,
        "macro_supported_sides": macro_sides,
        "candidate_score_count": int(len(candidate_scores)),
        "macro_aligned_candidate_count": int(candidate_scores["macro_aligned"].sum()) if not candidate_scores.empty else 0,
        "shortlist_count": int(len(shortlist)),
        "current_active_count": int(len(current_active)),
        "shortlist_side_counts": shortlist["side"].value_counts().to_dict() if not shortlist.empty else {},
        "shortlist_timeframe_counts": shortlist["timeframe"].value_counts().to_dict() if not shortlist.empty else {},
        "top_shortlist_rule_ids": shortlist["rule_id"].head(10).tolist() if not shortlist.empty else [],
        "timeframe_context": tf_context,
        "outputs": {
            "summary_json": str(summary_path),
            "candidate_scores_csv": str(scores_path),
            "shortlist_csv": str(shortlist_path),
            "current_active_csv": str(current_path),
            "context_json": str(context_path),
        },
        "next": [
            "Keep Stage157 freeze active.",
            "Do not release demo orders from this read-only rebuild stage.",
            "If a small higher-timeframe macro-aligned shortlist exists, manually review before any execution patch.",
            "If no shortlist exists, wait for regime change or rebuild with explicit macro/fundamental thesis features.",
        ],
    }
    write_json(summary_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=STAGE)
    p.add_argument("--root", required=True)
    p.add_argument("--bars-m5", default=None)
    p.add_argument("--bars-h1", default=None)
    p.add_argument("--stage161-summary", required=True)
    p.add_argument("--timestamp-shift-hours", type=float, default=-3.0)
    p.add_argument("--horizon-hours", type=float, default=24.0)
    p.add_argument("--scan-h1", action="store_true", default=True)
    p.add_argument("--scan-h4", action="store_true", default=True)
    p.add_argument("--scan-d1", action="store_true", default=True)
    p.add_argument("--no-scan-h1", dest="scan_h1", action="store_false")
    p.add_argument("--no-scan-h4", dest="scan_h4", action="store_false")
    p.add_argument("--no-scan-d1", dest="scan_d1", action="store_false")
    p.add_argument("--min-events", type=int, default=80)
    p.add_argument("--min-mean-bps", type=float, default=3.0)
    p.add_argument("--min-hit-rate", type=float, default=0.525)
    p.add_argument("--min-recent-mean-bps", type=float, default=2.0)
    p.add_argument("--min-positive-folds", type=int, default=3)
    return p


if __name__ == "__main__":
    run(build_arg_parser().parse_args())
