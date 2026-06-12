#!/usr/bin/env python3
"""
Stage28C forward-safe meta-gate validation for the XAUUSD research project.

Purpose:
- Do NOT create orders or modify active trackers.
- Validate Stage28B Hotfix2 strict forward-safe meta-gate candidates around the
  Stage23/25 canonical lineage.
- Detect and reduce selection/quantile leakage by comparing:
    1) static full-sample threshold reproduction (diagnostic only),
    2) expanding event-by-event historical-threshold validation,
    3) yearly walk-forward threshold validation,
    4) leave-one-year-out robustness diagnostics.
- DB market candles are used only for metadata sanity via the validated Stage25C
  loader. Trade artifacts are research artifacts, not market-data fallback.
"""
from __future__ import annotations

import json
import math
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

DEFAULT_DB_PATH = Path(os.getenv("XAUUSD_DB_PATH", "data/local/xauusd_local_store.sqlite"))
DEFAULT_TRADES = Path(
    os.getenv(
        "STAGE28C_TRADES_ARTIFACT",
        "data/reports/stage28b_ml_meta_feature_screen/stage28b_normalized_lineage_trades.csv",
    )
)
FALLBACK_TRADES = Path(
    os.getenv(
        "STAGE28C_FALLBACK_TRADES_ARTIFACT",
        "data/reports/stage25c_deduped_filter_validation/stage25c_enriched_canonical_trades.csv",
    )
)
REPORT_DIR = Path("data/reports/stage28c_forward_safe_meta_gate_validation")
MIN_EVENTS = int(os.getenv("STAGE28C_MIN_EVENTS", "25"))
MIN_CALIB_EVENTS = int(os.getenv("STAGE28C_MIN_CALIB_EVENTS", "25"))
BOOT_N = int(os.getenv("STAGE28C_BOOT_N", "250"))
RANDOM_SEED = int(os.getenv("STAGE28C_RANDOM_SEED", "2803"))
ROUNDTRIP_COST_X1 = float(os.getenv("STAGE28C_ROUNDTRIP_COST_X1", "0.35"))

FORWARD_SAFE_FEATURES = {
    "year", "month", "dow", "entry_hour", "direction", "dir_mult",
    "prior_day_range", "asia_range", "asia_eff", "london_range", "london_eff", "prior_day_aligned",
}
REQUIRED_NET_COLS = ["net_x1", "net_x4", "net_x6"]
TIME_COL_CANDIDATES = ["entry_ts_norm", "entry_time", "timestamp", "time", "date"]

# Gate definitions are intentionally focused on the Stage28B Hotfix2 winning cluster:
# strong London range and prior-day/Asia context, all knowable at canonical entry.
GATE_DEFS: List[Dict[str, Any]] = [
    {"name": "s28b_top_london_q40_prior_q25", "kind": "pairwise", "rules": [("london_range", "ge", 0.40), ("prior_day_range", "ge", 0.25)]},
    {"name": "london_q40_prior_q30", "kind": "pairwise", "rules": [("london_range", "ge", 0.40), ("prior_day_range", "ge", 0.30)]},
    {"name": "london_q40_prior_q35", "kind": "pairwise", "rules": [("london_range", "ge", 0.40), ("prior_day_range", "ge", 0.35)]},
    {"name": "london_q40_prior_q40", "kind": "pairwise", "rules": [("london_range", "ge", 0.40), ("prior_day_range", "ge", 0.40)]},
    {"name": "london_q35_prior_q25", "kind": "pairwise", "rules": [("london_range", "ge", 0.35), ("prior_day_range", "ge", 0.25)]},
    {"name": "london_q35_prior_q30", "kind": "pairwise", "rules": [("london_range", "ge", 0.35), ("prior_day_range", "ge", 0.30)]},
    {"name": "london_q60_prior_q25", "kind": "pairwise", "rules": [("london_range", "ge", 0.60), ("prior_day_range", "ge", 0.25)]},
    {"name": "london_q60_prior_q30", "kind": "pairwise", "rules": [("london_range", "ge", 0.60), ("prior_day_range", "ge", 0.30)]},
    {"name": "london_q40_asia_q25", "kind": "pairwise", "rules": [("london_range", "ge", 0.40), ("asia_range", "ge", 0.25)]},
    {"name": "london_q40_asia_q30", "kind": "pairwise", "rules": [("london_range", "ge", 0.40), ("asia_range", "ge", 0.30)]},
    {"name": "asia_q30_prior_q25", "kind": "pairwise", "rules": [("asia_range", "ge", 0.30), ("prior_day_range", "ge", 0.25)]},
    {"name": "asia_q35_prior_q25", "kind": "pairwise", "rules": [("asia_range", "ge", 0.35), ("prior_day_range", "ge", 0.25)]},
    {"name": "london_range_q40", "kind": "single", "rules": [("london_range", "ge", 0.40)]},
    {"name": "london_range_q60", "kind": "single", "rules": [("london_range", "ge", 0.60)]},
    {"name": "london_range_q65", "kind": "single", "rules": [("london_range", "ge", 0.65)]},
    {"name": "london_range_q70", "kind": "single", "rules": [("london_range", "ge", 0.70)]},
]

@dataclass
class Metrics:
    events: int
    pf_x1: float
    pf_x4: float
    pf_x6: float
    boot_pf_p05_x4: float
    median_x4: float
    total_x4: float
    win_rate_x4: float
    years_positive_x4: int
    year_count: int


def _safe_float(x: Any) -> float:
    try:
        f = float(x)
        if math.isnan(f):
            return 0.0
        if math.isinf(f):
            return float("inf") if f > 0 else float("-inf")
        return round(f, 6)
    except Exception:
        return 0.0


def _profit_factor(values: pd.Series) -> float:
    v = pd.to_numeric(values, errors="coerce").dropna()
    gains = float(v[v > 0].sum())
    losses = float((-v[v < 0]).sum())
    if losses <= 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


def _bootstrap_pf_p05(values: pd.Series, n: int = BOOT_N, seed: int = RANDOM_SEED) -> float:
    v = pd.to_numeric(values, errors="coerce").dropna().to_numpy(dtype=float)
    if len(v) < 5:
        return 0.0
    rng = np.random.default_rng(seed)
    pfs: List[float] = []
    for _ in range(max(1, n)):
        sample = rng.choice(v, size=len(v), replace=True)
        gains = float(sample[sample > 0].sum())
        losses = float((-sample[sample < 0]).sum())
        if losses <= 0:
            pfs.append(float("inf") if gains > 0 else 0.0)
        else:
            pfs.append(gains / losses)
    finite = np.array([x for x in pfs if np.isfinite(x)], dtype=float)
    if len(finite) == 0:
        return float("inf")
    return float(np.percentile(finite, 5))


def _metrics(df: pd.DataFrame, boot_n: int = BOOT_N) -> Metrics:
    if df.empty:
        return Metrics(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0)
    x1 = pd.to_numeric(df.get("net_x1", pd.Series(dtype=float)), errors="coerce")
    x4 = pd.to_numeric(df.get("net_x4", pd.Series(dtype=float)), errors="coerce")
    x6 = pd.to_numeric(df.get("net_x6", pd.Series(dtype=float)), errors="coerce")
    years_positive = 0
    year_count = 0
    if "year" in df.columns:
        yearly = df.groupby("year")["net_x4"].sum(numeric_only=True)
        year_count = int(len(yearly))
        years_positive = int((yearly > 0).sum())
    return Metrics(
        events=int(len(df)),
        pf_x1=_safe_float(_profit_factor(x1)),
        pf_x4=_safe_float(_profit_factor(x4)),
        pf_x6=_safe_float(_profit_factor(x6)),
        boot_pf_p05_x4=_safe_float(_bootstrap_pf_p05(x4, boot_n)),
        median_x4=_safe_float(float(x4.median()) if len(x4.dropna()) else 0.0),
        total_x4=_safe_float(float(x4.sum()) if len(x4.dropna()) else 0.0),
        win_rate_x4=_safe_float(float((x4 > 0).mean()) if len(x4.dropna()) else 0.0),
        years_positive_x4=years_positive,
        year_count=year_count,
    )


def _detect_time_col(df: pd.DataFrame) -> Optional[str]:
    for c in TIME_COL_CANDIDATES:
        if c in df.columns:
            return c
    return None


def _load_trades() -> Tuple[pd.DataFrame, Dict[str, Any]]:
    path = DEFAULT_TRADES if DEFAULT_TRADES.exists() else FALLBACK_TRADES
    manifest: Dict[str, Any] = {"selected_artifact": str(path), "exists": path.exists(), "rows": 0, "status": "missing"}
    if not path.exists():
        raise FileNotFoundError(f"No Stage28B/Stage25C trade artifact found: {DEFAULT_TRADES} or {FALLBACK_TRADES}")
    df = pd.read_csv(path)
    manifest.update({"rows": int(len(df)), "status": "loaded"})

    # Standardize net columns.
    for c in REQUIRED_NET_COLS:
        if c not in df.columns:
            raise ValueError(f"Required column missing from trade artifact: {c}")
        df[c] = pd.to_numeric(df[c], errors="coerce")

    time_col = _detect_time_col(df)
    manifest["time_column_used"] = time_col or "none"
    if time_col:
        ts = pd.to_datetime(df[time_col], errors="coerce", utc=True)
        df["entry_ts_norm"] = ts
        df["year"] = ts.dt.year
        df["month"] = ts.dt.month
        df["dow"] = ts.dt.dayofweek
        df["entry_hour"] = ts.dt.hour
    else:
        for c in ["year", "month", "dow", "entry_hour"]:
            if c not in df.columns:
                df[c] = -1

    # Numeric conversion for forward-safe features.
    for c in sorted(FORWARD_SAFE_FEATURES):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    before = len(df)
    dedup_cols = [c for c in ["entry_ts_norm", "direction", "net_x1", "net_x4", "net_x6"] if c in df.columns]
    if dedup_cols:
        df = df.drop_duplicates(subset=dedup_cols).copy()
    manifest["rows_after_event_dedup"] = int(len(df))
    manifest["dedup_removed"] = int(before - len(df))

    if "entry_ts_norm" in df.columns:
        df = df.sort_values("entry_ts_norm").reset_index(drop=True)
    else:
        df = df.reset_index(drop=True)
    return df, manifest


def _load_db_meta() -> Dict[str, Any]:
    meta: Dict[str, Any] = {
        "loader_mode": "reused:app.stage25c_deduped_filter_validation.load_bars_from_db",
        "db_path": str(DEFAULT_DB_PATH),
        "db_first": True,
        "csv_fallback_enabled": False,
    }
    try:
        from app.stage25c_deduped_filter_validation import load_bars_from_db  # type: ignore
        loaded = load_bars_from_db(DEFAULT_DB_PATH)
        if isinstance(loaded, tuple) and len(loaded) >= 2:
            m1, h1 = loaded[0], loaded[1]
            if len(loaded) >= 3 and isinstance(loaded[2], dict):
                meta.update(loaded[2])
            meta.update({
                "m1_rows": int(len(m1)) if hasattr(m1, "__len__") else "unavailable",
                "h1_rows": int(len(h1)) if hasattr(h1, "__len__") else "unavailable",
                "db_meta_status": "ok",
            })
        else:
            meta.update({"db_meta_status": "warning", "db_meta_error": "Unexpected loader return shape"})
    except Exception as exc:
        meta.update({"db_meta_status": "warning", "db_meta_error": f"{type(exc).__name__}: {exc}"})
    return meta


def _available_gate_defs(df: pd.DataFrame) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for gd in GATE_DEFS:
        missing = [f for f, _op, _q in gd["rules"] if f not in df.columns or f not in FORWARD_SAFE_FEATURES]
        if not missing:
            out.append(gd)
    return out


def _thresholds_from_reference(ref: pd.DataFrame, gd: Dict[str, Any]) -> Optional[Dict[str, float]]:
    thresholds: Dict[str, float] = {}
    for feature, op, q in gd["rules"]:
        s = pd.to_numeric(ref[feature], errors="coerce").dropna()
        if len(s) < MIN_CALIB_EVENTS or s.nunique() < 2:
            return None
        thresholds[feature] = float(s.quantile(float(q)))
    return thresholds


def _mask_with_thresholds(df: pd.DataFrame, gd: Dict[str, Any], thresholds: Dict[str, float]) -> pd.Series:
    mask = pd.Series([True] * len(df), index=df.index)
    for feature, op, _q in gd["rules"]:
        s = pd.to_numeric(df[feature], errors="coerce")
        thr = thresholds[feature]
        if op == "ge":
            mask = mask & (s >= thr)
        elif op == "gt":
            mask = mask & (s > thr)
        elif op == "le":
            mask = mask & (s <= thr)
        elif op == "lt":
            mask = mask & (s < thr)
        else:
            raise ValueError(f"Unsupported operator: {op}")
    return mask.fillna(False)


def _static_validation(df: pd.DataFrame, gd: Dict[str, Any], base: Metrics) -> Dict[str, Any]:
    thr = _thresholds_from_reference(df, gd)
    if thr is None:
        m = _metrics(df.iloc[0:0])
        mask = pd.Series([False] * len(df), index=df.index)
    else:
        mask = _mask_with_thresholds(df, gd, thr)
        m = _metrics(df[mask])
    return {
        "gate_name": gd["name"], "mode": "static_full_sample_diagnostic", "thresholds": thr or {},
        **asdict(m),
        "retained_ratio": _safe_float(m.events / max(base.events, 1)),
        "improvement_pf_x4": _safe_float(m.pf_x4 - base.pf_x4),
        "improvement_pf_x6": _safe_float(m.pf_x6 - base.pf_x6),
        "improvement_total_x4": _safe_float(m.total_x4 - base.total_x4),
        "mask": mask,
    }


def _expanding_event_validation(df: pd.DataFrame, gd: Dict[str, Any], base: Metrics) -> Dict[str, Any]:
    kept = []
    threshold_records: List[Dict[str, Any]] = []
    for idx in range(len(df)):
        ref = df.iloc[:idx]
        cur = df.iloc[[idx]]
        thr = _thresholds_from_reference(ref, gd)
        if thr is None:
            kept.append(False)
            continue
        mask = _mask_with_thresholds(cur, gd, thr)
        keep = bool(mask.iloc[0])
        kept.append(keep)
        if keep:
            rec = {"idx": idx, "entry_ts_norm": str(cur.iloc[0].get("entry_ts_norm", ""))}
            rec.update({f"thr_{k}": v for k, v in thr.items()})
            threshold_records.append(rec)
    mask = pd.Series(kept, index=df.index)
    m = _metrics(df[mask])
    return {
        "gate_name": gd["name"], "mode": "expanding_event_oos", "thresholds": {},
        **asdict(m),
        "retained_ratio": _safe_float(m.events / max(base.events, 1)),
        "improvement_pf_x4": _safe_float(m.pf_x4 - base.pf_x4),
        "improvement_pf_x6": _safe_float(m.pf_x6 - base.pf_x6),
        "improvement_total_x4": _safe_float(m.total_x4 - base.total_x4),
        "threshold_record_count": len(threshold_records),
        "mask": mask,
    }


def _yearly_walk_forward_validation(df: pd.DataFrame, gd: Dict[str, Any], base: Metrics) -> Tuple[Dict[str, Any], pd.DataFrame]:
    masks = pd.Series([False] * len(df), index=df.index)
    rows: List[Dict[str, Any]] = []
    years = sorted([int(y) for y in pd.to_numeric(df["year"], errors="coerce").dropna().unique()]) if "year" in df.columns else []
    for y in years:
        ref = df[pd.to_numeric(df["year"], errors="coerce") < y]
        test = df[pd.to_numeric(df["year"], errors="coerce") == y]
        if test.empty:
            continue
        thr = _thresholds_from_reference(ref, gd)
        if thr is None:
            part = test.iloc[0:0]
            kept_mask = pd.Series([False] * len(test), index=test.index)
            status = "skipped_insufficient_prior_calibration"
        else:
            kept_mask = _mask_with_thresholds(test, gd, thr)
            part = test[kept_mask]
            masks.loc[test.index] = kept_mask
            status = "tested"
        m = _metrics(part, boot_n=50)
        rows.append({
            "gate_name": gd["name"], "year": y, "status": status,
            "train_events": int(len(ref)), "test_events": int(len(test)),
            "kept_events": int(len(part)), "pf_x4": m.pf_x4, "pf_x6": m.pf_x6,
            "total_x4": m.total_x4, "win_rate_x4": m.win_rate_x4,
            "thresholds": json.dumps(thr or {}, default=str),
        })
    m_all = _metrics(df[masks])
    return {
        "gate_name": gd["name"], "mode": "yearly_walk_forward_oos", "thresholds": {},
        **asdict(m_all),
        "retained_ratio": _safe_float(m_all.events / max(base.events, 1)),
        "improvement_pf_x4": _safe_float(m_all.pf_x4 - base.pf_x4),
        "improvement_pf_x6": _safe_float(m_all.pf_x6 - base.pf_x6),
        "improvement_total_x4": _safe_float(m_all.total_x4 - base.total_x4),
        "mask": masks,
    }, pd.DataFrame(rows)


def _leave_one_year_out(df: pd.DataFrame, gd: Dict[str, Any]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    if "year" not in df.columns:
        return pd.DataFrame(rows)
    years = sorted([int(y) for y in pd.to_numeric(df["year"], errors="coerce").dropna().unique()])
    for y in years:
        train = df[pd.to_numeric(df["year"], errors="coerce") != y]
        hold = df[pd.to_numeric(df["year"], errors="coerce") == y]
        thr = _thresholds_from_reference(train, gd)
        if thr is None or hold.empty:
            part = hold.iloc[0:0]
            status = "skipped"
        else:
            part = hold[_mask_with_thresholds(hold, gd, thr)]
            status = "tested"
        m = _metrics(part, boot_n=50)
        rows.append({
            "gate_name": gd["name"], "holdout_year": y, "status": status,
            "holdout_events": int(len(hold)), "kept_events": m.events,
            "pf_x4": m.pf_x4, "pf_x6": m.pf_x6, "total_x4": m.total_x4,
            "win_rate_x4": m.win_rate_x4, "thresholds": json.dumps(thr or {}, default=str),
        })
    return pd.DataFrame(rows)


def _classify(oos: Dict[str, Any], ywf: Dict[str, Any], static: Dict[str, Any]) -> str:
    # OOS is the main standard; static is diagnostic only.
    if (
        int(oos["events"]) >= MIN_EVENTS
        and float(oos["pf_x4"]) >= 1.75
        and float(oos["pf_x6"]) >= 1.05
        and float(oos["total_x4"]) > 0
        and float(oos["boot_pf_p05_x4"]) >= 1.05
        and int(ywf["events"]) >= max(12, MIN_EVENTS // 2)
        and float(ywf["total_x4"]) > 0
    ):
        return "STAGE28C_META_GATE_VALIDATED_REVIEW_ONLY"
    if int(oos["events"]) >= max(12, MIN_EVENTS // 2) and float(oos["total_x4"]) > 0 and float(oos["pf_x4"]) >= 1.20:
        return "STAGE28C_META_GATE_WATCHLIST_ONLY"
    return "STAGE28C_REJECT"


def _rank(rec: Dict[str, Any]) -> float:
    pf4 = float(rec.get("expanding_pf_x4", 0.0) or 0.0)
    pf6 = float(rec.get("expanding_pf_x6", 0.0) or 0.0)
    boot = float(rec.get("expanding_boot_pf_p05_x4", 0.0) or 0.0)
    total = float(rec.get("expanding_total_x4", 0.0) or 0.0)
    events = float(rec.get("expanding_events", 0.0) or 0.0)
    ywf_total = float(rec.get("ywf_total_x4", 0.0) or 0.0)
    return _safe_float(min(pf4, 10.0) * 0.35 + min(pf6, 8.0) * 0.25 + min(boot, 5.0) * 0.20 + np.sign(total) * 0.10 + min(events / 50.0, 1.0) * 0.05 + np.sign(ywf_total) * 0.05)


def _split_diag(df: pd.DataFrame, gate_name: str, mode: str, mask: pd.Series) -> pd.DataFrame:
    g = df[mask.fillna(False)].copy()
    rows: List[Dict[str, Any]] = []
    for split in ["year", "direction", "entry_hour", "dow", "month"]:
        if split not in g.columns:
            continue
        for bucket, part in g.groupby(split):
            m = _metrics(part, boot_n=50)
            rows.append({
                "gate_name": gate_name, "mode": mode, "split": split, "bucket": bucket,
                "events": m.events, "pf_x4": m.pf_x4, "pf_x6": m.pf_x6,
                "total_x4": m.total_x4, "win_rate_x4": m.win_rate_x4,
            })
    return pd.DataFrame(rows)


def _format_table(df: pd.DataFrame, max_rows: int = 40) -> str:
    if df.empty:
        return "No rows."
    return df.head(max_rows).to_markdown(index=False)


def run() -> Dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    db_meta = _load_db_meta()
    df, manifest = _load_trades()
    base = _metrics(df)
    available = _available_gate_defs(df)

    results: List[Dict[str, Any]] = []
    all_yearly_rows: List[pd.DataFrame] = []
    all_loyo_rows: List[pd.DataFrame] = []
    split_frames: List[pd.DataFrame] = []

    for gd in available:
        static = _static_validation(df, gd, base)
        expanding = _expanding_event_validation(df, gd, base)
        ywf, ywf_rows = _yearly_walk_forward_validation(df, gd, base)
        loyo = _leave_one_year_out(df, gd)
        decision = _classify(expanding, ywf, static)
        rec: Dict[str, Any] = {
            "decision": decision,
            "gate_name": gd["name"],
            "gate_kind": gd["kind"],
            "rules": json.dumps(gd["rules"]),
            "static_events": static["events"], "static_pf_x4": static["pf_x4"], "static_pf_x6": static["pf_x6"], "static_total_x4": static["total_x4"], "static_win_rate_x4": static["win_rate_x4"],
            "expanding_events": expanding["events"], "expanding_pf_x4": expanding["pf_x4"], "expanding_pf_x6": expanding["pf_x6"], "expanding_boot_pf_p05_x4": expanding["boot_pf_p05_x4"], "expanding_total_x4": expanding["total_x4"], "expanding_win_rate_x4": expanding["win_rate_x4"], "expanding_years_positive_x4": expanding["years_positive_x4"], "expanding_year_count": expanding["year_count"],
            "ywf_events": ywf["events"], "ywf_pf_x4": ywf["pf_x4"], "ywf_pf_x6": ywf["pf_x6"], "ywf_total_x4": ywf["total_x4"], "ywf_win_rate_x4": ywf["win_rate_x4"], "ywf_years_positive_x4": ywf["years_positive_x4"], "ywf_year_count": ywf["year_count"],
        }
        rec["rank_score"] = _rank(rec)
        results.append(rec)
        if not ywf_rows.empty:
            all_yearly_rows.append(ywf_rows)
        if not loyo.empty:
            all_loyo_rows.append(loyo)
        # Record splits for static and expanding for top candidate candidates later; cheap enough for all.
        split_frames.append(_split_diag(df, gd["name"], "static_full_sample_diagnostic", static["mask"]))
        split_frames.append(_split_diag(df, gd["name"], "expanding_event_oos", expanding["mask"]))

    res_df = pd.DataFrame(results)
    if not res_df.empty:
        order = {"STAGE28C_META_GATE_VALIDATED_REVIEW_ONLY": 0, "STAGE28C_META_GATE_WATCHLIST_ONLY": 1, "STAGE28C_REJECT": 2}
        res_df["_decision_order"] = res_df["decision"].map(order).fillna(9)
        res_df = res_df.sort_values(["_decision_order", "rank_score", "expanding_total_x4"], ascending=[True, False, False]).drop(columns=["_decision_order"])
    yearly_df = pd.concat(all_yearly_rows, ignore_index=True) if all_yearly_rows else pd.DataFrame()
    loyo_df = pd.concat(all_loyo_rows, ignore_index=True) if all_loyo_rows else pd.DataFrame()
    split_df = pd.concat(split_frames, ignore_index=True) if split_frames else pd.DataFrame()

    validated_count = int((res_df.get("decision", pd.Series(dtype=str)) == "STAGE28C_META_GATE_VALIDATED_REVIEW_ONLY").sum()) if not res_df.empty else 0
    watch_count = int((res_df.get("decision", pd.Series(dtype=str)) == "STAGE28C_META_GATE_WATCHLIST_ONLY").sum()) if not res_df.empty else 0
    decision = "STAGE28C_HAS_FORWARD_SAFE_META_GATE_VALIDATION_CANDIDATE_REVIEW_ONLY" if validated_count else ("STAGE28C_HAS_META_GATE_WATCHLIST_ONLY" if watch_count else "STAGE28C_NO_META_GATE_VALIDATION_KEEP_DISCOVERY_OPEN")

    outputs = {
        "md": str(REPORT_DIR / "stage28c_forward_safe_meta_gate_validation.md"),
        "json": str(REPORT_DIR / "stage28c_forward_safe_meta_gate_validation.json"),
        "gate_validation": str(REPORT_DIR / "stage28c_gate_validation.csv"),
        "yearly_walk_forward": str(REPORT_DIR / "stage28c_yearly_walk_forward.csv"),
        "leave_one_year_out": str(REPORT_DIR / "stage28c_leave_one_year_out.csv"),
        "gate_splits": str(REPORT_DIR / "stage28c_gate_splits.csv"),
        "db_schema_diagnostic": str(REPORT_DIR / "stage28c_db_schema_diagnostic.json"),
    }

    res_df.to_csv(outputs["gate_validation"], index=False)
    yearly_df.to_csv(outputs["yearly_walk_forward"], index=False)
    loyo_df.to_csv(outputs["leave_one_year_out"], index=False)
    split_df.to_csv(outputs["gate_splits"], index=False)
    Path(outputs["db_schema_diagnostic"]).write_text(json.dumps(db_meta, indent=2, default=str), encoding="utf-8")

    summary = {
        "decision": decision,
        "db_meta": db_meta,
        "artifact_manifest": manifest,
        "base_metrics": asdict(base),
        "gate_defs_total": len(GATE_DEFS),
        "gate_defs_available": len(available),
        "min_calib_events": MIN_CALIB_EVENTS,
        "min_events": MIN_EVENTS,
        "validated_count": validated_count,
        "watchlist_only_count": watch_count,
        "outputs": outputs,
    }
    md = _render_markdown(summary, res_df, yearly_df, loyo_df, split_df)
    Path(outputs["md"]).write_text(md, encoding="utf-8")
    Path(outputs["json"]).write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return summary


def _render_markdown(summary: Dict[str, Any], res_df: pd.DataFrame, yearly_df: pd.DataFrame, loyo_df: pd.DataFrame, split_df: pd.DataFrame) -> str:
    db = summary["db_meta"]
    manifest = summary["artifact_manifest"]
    base = summary["base_metrics"]
    lines: List[str] = []
    lines.append("# Stage28C Forward-Safe Meta-Gate Validation")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append("```text")
    lines.append(str(summary["decision"]))
    lines.append("```")
    lines.append("")
    lines.append("## Scope guardrails")
    lines.append("")
    lines.append("- Research/shadow validation only.")
    lines.append("- No EA change, no automatic trading, no paper/live/order authorization.")
    lines.append("- Stage18A/Stage23D/Stage25D/Stage27D remain unchanged.")
    lines.append("- Validates Stage28B Hotfix2 strict forward-safe meta-gates; it does not invent a new raw entry.")
    lines.append("- Full-sample static thresholds are diagnostic only; expanding and yearly walk-forward validation are the main anti-selection checks.")
    lines.append("- DB candle access is sanity-only via Stage25C loader; trade artifacts remain research artifacts, not market-data fallback.")
    lines.append("")
    lines.append("## DB source of truth")
    lines.append("")
    lines.append(f"- loader_mode: `{db.get('loader_mode')}`")
    lines.append(f"- db_path: `{db.get('db_path')}`")
    lines.append(f"- db_first: `{db.get('db_first')}`")
    lines.append(f"- csv_fallback_enabled: `{db.get('csv_fallback_enabled')}`")
    lines.append(f"- m1_rows: `{db.get('m1_rows', 'unavailable')}`")
    lines.append(f"- h1_rows: `{db.get('h1_rows', 'unavailable')}`")
    if db.get("db_meta_status") == "warning":
        lines.append(f"- db_meta_warning: `{db.get('db_meta_error')}`")
    lines.append("")
    lines.append("## Trade artifact")
    lines.append("")
    lines.append(f"- selected_artifact: `{manifest.get('selected_artifact')}`")
    lines.append(f"- rows: `{manifest.get('rows')}`")
    lines.append(f"- rows_after_event_dedup: `{manifest.get('rows_after_event_dedup')}`")
    lines.append(f"- time_column_used: `{manifest.get('time_column_used')}`")
    lines.append("")
    lines.append("## Base metrics")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(base, indent=2, default=str))
    lines.append("```")
    lines.append("")
    lines.append("## Counts")
    lines.append("")
    lines.append(f"- gate_defs_total: `{summary['gate_defs_total']}`")
    lines.append(f"- gate_defs_available: `{summary['gate_defs_available']}`")
    lines.append(f"- min_calib_events: `{summary['min_calib_events']}`")
    lines.append(f"- min_events: `{summary['min_events']}`")
    lines.append(f"- validated_count: `{summary['validated_count']}`")
    lines.append(f"- watchlist_only_count: `{summary['watchlist_only_count']}`")
    lines.append("")
    lines.append("## Gate validation diagnostics")
    lines.append("")
    cols = [
        "decision", "gate_name", "gate_kind", "static_events", "static_pf_x4", "static_pf_x6", "static_total_x4",
        "expanding_events", "expanding_pf_x4", "expanding_pf_x6", "expanding_boot_pf_p05_x4", "expanding_total_x4", "expanding_win_rate_x4",
        "ywf_events", "ywf_pf_x4", "ywf_pf_x6", "ywf_total_x4", "ywf_win_rate_x4", "rank_score",
    ]
    lines.append(_format_table(res_df[[c for c in cols if c in res_df.columns]], 40))
    lines.append("")
    lines.append("## Yearly walk-forward diagnostics")
    lines.append("")
    lines.append(_format_table(yearly_df, 80))
    lines.append("")
    lines.append("## Leave-one-year-out diagnostics")
    lines.append("")
    lines.append(_format_table(loyo_df, 80))
    lines.append("")
    lines.append("## Gate split diagnostics")
    lines.append("")
    lines.append(_format_table(split_df, 80))
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("- Stage28C is stricter than Stage28B: global quantile thresholds are no longer enough for validation.")
    lines.append("- A validated result here is still review-only; it requires a separate forward-shadow tracker before operational consideration.")
    lines.append("- If expanding validation survives but yearly walk-forward weakens, keep the gate as research watchlist only.")
    lines.append("- If no meta-gate survives, the next useful step is exogenous/macro/news feature integration rather than more OHLC-only gate mining.")
    lines.append("")
    lines.append("## Operational reminder")
    lines.append("")
    lines.append("```bash")
    lines.append("cd ~/Desktop/xauusd-trader")
    lines.append("python3 -m app.run_active_shadow_suite")
    lines.append("python3 -m app.stage28b_ml_meta_feature_screen")
    lines.append("python3 -m app.stage28c_forward_safe_meta_gate_validation")
    lines.append("```")
    lines.append("")
    lines.append("## Output files")
    lines.append("")
    for _k, v in summary["outputs"].items():
        lines.append(f"- `{v}`")
    return "\n".join(lines) + "\n"


def main() -> None:
    try:
        run()
    except Exception as exc:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        md = "\n".join([
            "# Stage28C Forward-Safe Meta-Gate Validation",
            "",
            "## Decision",
            "",
            "```text",
            "STAGE28C_ERROR_DIAGNOSTIC_ONLY",
            "```",
            "",
            "## Error",
            "",
            "```text",
            f"{type(exc).__name__}: {exc}",
            "```",
            "",
            "- Active forward trackers remain unchanged.",
            "- No CSV market fallback is enabled.",
            "",
        ])
        (REPORT_DIR / "stage28c_forward_safe_meta_gate_validation.md").write_text(md, encoding="utf-8")
        (REPORT_DIR / "stage28c_forward_safe_meta_gate_validation.json").write_text(
            json.dumps({"decision": "STAGE28C_ERROR_DIAGNOSTIC_ONLY", "error": f"{type(exc).__name__}: {exc}"}, indent=2),
            encoding="utf-8",
        )
        raise


if __name__ == "__main__":
    main()
