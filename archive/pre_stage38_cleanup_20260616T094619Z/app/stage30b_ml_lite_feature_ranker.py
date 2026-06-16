#!/usr/bin/env python3
"""
Stage30B — ML-lite feature ranker / scorecard for the XAUUSD candidate pool.

Purpose
-------
Use the Stage30A ML-ready candidate pool to evaluate simple, auditable meta-gates
under time-aware out-of-sample checks. This is not a black-box model and does not
create orders, EA changes, paper/live authorization, or operational signals.

Core safeguards
---------------
- Consumes only Stage30A ML-ready dataset artifacts.
- Uses a strict feature whitelist and blocks known source-leak columns such as
  direction_num by default.
- Selects gates only on training data and applies them to future test years.
- Reports family/source holdout diagnostics to expose source-specific overfit.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

ROOT = Path.cwd()
REPORT_DIR = ROOT / "data" / "reports" / "stage30b_ml_lite_feature_ranker"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_DATASET = Path(os.getenv(
    "STAGE30B_DATASET",
    "data/reports/stage30a_candidate_pool_builder_ml_dataset/stage30a_ml_meta_dataset.csv",
))
MIN_TRAIN_EVENTS = int(os.getenv("STAGE30B_MIN_TRAIN_EVENTS", "250"))
MIN_TEST_EVENTS = int(os.getenv("STAGE30B_MIN_TEST_EVENTS", "25"))
MIN_GATE_TRAIN_EVENTS = int(os.getenv("STAGE30B_MIN_GATE_TRAIN_EVENTS", "60"))
MIN_GATE_TEST_EVENTS = int(os.getenv("STAGE30B_MIN_GATE_TEST_EVENTS", "20"))
TOP_K_GATES = int(os.getenv("STAGE30B_TOP_K_GATES", "12"))
VOTE_MIN = int(os.getenv("STAGE30B_VOTE_MIN", "2"))
ROUND_DIGITS = 6

# Direction is blocked by default because Stage30A showed direction_num==0 mostly
# identified the sparse successful lineage rather than true market direction.
ALLOW_DIRECTION = os.getenv("STAGE30B_ALLOW_DIRECTION", "0").strip() == "1"

NUMERIC_FEATURES = [
    "prior_day_range",
    "asia_range",
    "asia_eff",
    "london_range",
    "london_eff",
    "h1_range",
    "h1_atr20",
    "h1_atr20_pct_rank_250",
]
CATEGORICAL_FEATURES = ["entry_hour", "dow", "month"]
OPTIONAL_SAFE_CATEGORICAL = ["prior_day_aligned", "london_aligned"]
BLOCKED_FEATURES_DEFAULT = ["direction_num", "year", "source_stage", "source_file", "family", "candidate_name"]
QUANTILES = [0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60, 0.65, 0.70, 0.75, 0.80]


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        f = float(x)
        if math.isnan(f):
            return default
        if math.isinf(f):
            return float("inf") if f > 0 else float("-inf")
        return round(f, ROUND_DIGITS)
    except Exception:
        return default


def _fmt(x: Any) -> str:
    if x is None:
        return ""
    try:
        if pd.isna(x):
            return ""
    except Exception:
        pass
    if isinstance(x, float):
        if math.isinf(x):
            return "inf" if x > 0 else "-inf"
        if math.isnan(x):
            return ""
        return str(round(x, 4))
    if isinstance(x, (dict, list, tuple)):
        return json.dumps(x, ensure_ascii=False, default=str)
    return str(x)


def markdown_table(df: pd.DataFrame, columns: Sequence[str], max_rows: int = 30) -> str:
    if df is None or df.empty:
        return "No rows."
    cols = [c for c in columns if c in df.columns]
    if not cols:
        return "No rows."
    show = df.loc[:, cols].head(max_rows).copy()
    header = "| " + " | ".join(show.columns) + " |"
    sep = "| " + " | ".join(["---"] * len(show.columns)) + " |"
    rows = ["| " + " | ".join(_fmt(row[c]) for c in show.columns) + " |" for _, row in show.iterrows()]
    return "\n".join([header, sep] + rows)


def profit_factor(values: Iterable[float]) -> float:
    arr = pd.to_numeric(pd.Series(list(values)), errors="coerce").dropna().to_numpy(dtype=float)
    if arr.size == 0:
        return 0.0
    gains = float(arr[arr > 0].sum())
    losses = float((-arr[arr < 0]).sum())
    if losses <= 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


@dataclass
class Metrics:
    events: int
    pf_x1: float
    pf_x4: float
    pf_x6: float
    total_x4: float
    win_rate_x4: float
    median_x4: float
    years_positive_x4: int
    year_count: int


def metrics(df: pd.DataFrame) -> Metrics:
    if df is None or df.empty:
        return Metrics(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0)
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
        pf_x1=_safe_float(profit_factor(x1)),
        pf_x4=_safe_float(profit_factor(x4)),
        pf_x6=_safe_float(profit_factor(x6)),
        total_x4=_safe_float(float(x4.sum()) if x4.notna().any() else 0.0),
        win_rate_x4=_safe_float(float((x4 > 0).mean()) if x4.notna().any() else 0.0),
        median_x4=_safe_float(float(x4.median()) if x4.notna().any() else 0.0),
        years_positive_x4=years_positive,
        year_count=year_count,
    )


@dataclass
class GateDef:
    gate_name: str
    gate_kind: str
    feature: str
    side: str
    threshold: Optional[float] = None
    value: Optional[float] = None
    train_score: float = 0.0
    train_events: int = 0
    train_pf_x4: float = 0.0
    train_pf_x6: float = 0.0
    train_total_x4: float = 0.0

    def apply(self, df: pd.DataFrame) -> pd.Series:
        if self.feature not in df.columns:
            return pd.Series([False] * len(df), index=df.index)
        x = pd.to_numeric(df[self.feature], errors="coerce")
        if self.gate_kind == "numeric_quantile":
            if self.side == "ge":
                return (x >= float(self.threshold)).fillna(False)
            if self.side == "le":
                return (x <= float(self.threshold)).fillna(False)
        if self.gate_kind == "categorical_bucket":
            return (x == float(self.value)).fillna(False)
        return pd.Series([False] * len(df), index=df.index)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def load_dataset(path: Path) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    meta = {"dataset_path": str(path), "loaded": False}
    if not path.exists():
        meta["error"] = "dataset_not_found"
        return pd.DataFrame(), meta
    df = pd.read_csv(path)
    meta.update({"loaded": True, "rows_raw": int(len(df)), "columns": list(df.columns)})
    if df.empty:
        return df, meta
    for c in ["entry_ts_norm"]:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], utc=True, errors="coerce")
    for c in ["net_x1", "net_x4", "net_x6"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "year" not in df.columns or df["year"].isna().all():
        if "entry_ts_norm" in df.columns:
            df["year"] = df["entry_ts_norm"].dt.year
    df["year"] = pd.to_numeric(df.get("year"), errors="coerce")
    before = len(df)
    df = df.dropna(subset=["net_x4", "year"]).copy()
    # Event-level dedup: remove duplicate artifacts for the same timestamp/direction/outcome.
    if "entry_ts_norm" in df.columns:
        ts = df["entry_ts_norm"].astype(str)
    else:
        ts = pd.Series(range(len(df)), index=df.index).astype(str)
    dir_series = pd.to_numeric(df.get("direction_num", pd.Series([0.0] * len(df), index=df.index)), errors="coerce").fillna(0.0).round(3).astype(str)
    x4 = pd.to_numeric(df["net_x4"], errors="coerce").round(4).astype(str)
    x6 = pd.to_numeric(df.get("net_x6", pd.Series([np.nan] * len(df), index=df.index)), errors="coerce").round(4).astype(str)
    df["stage30b_event_uid"] = ts + "|" + dir_series + "|" + x4 + "|" + x6
    before_dedup = len(df)
    df = df.drop_duplicates(subset=["stage30b_event_uid"], keep="first").reset_index(drop=True)
    meta.update({
        "rows_after_required_dropna": int(before),
        "rows_after_dedup": int(len(df)),
        "dedup_removed": int(before_dedup - len(df)),
    })
    return df, meta


def usable_features(df: pd.DataFrame) -> Tuple[List[str], List[str], Dict[str, float]]:
    features: List[str] = []
    blocked = list(BLOCKED_FEATURES_DEFAULT)
    if ALLOW_DIRECTION and "direction_num" in df.columns:
        features.append("direction_num")
        blocked = [b for b in blocked if b != "direction_num"]
    for c in NUMERIC_FEATURES + CATEGORICAL_FEATURES + OPTIONAL_SAFE_CATEGORICAL:
        if c in df.columns and c not in features:
            non_null = float(pd.to_numeric(df[c], errors="coerce").notna().mean())
            if non_null >= 0.20:
                features.append(c)
    coverage = {c: round(float(pd.to_numeric(df[c], errors="coerce").notna().mean()), 4) for c in features if c in df.columns}
    return features, blocked, coverage


def generate_candidate_gates(train: pd.DataFrame, features: Sequence[str]) -> List[GateDef]:
    gates: List[GateDef] = []
    for feat in features:
        x = pd.to_numeric(train[feat], errors="coerce")
        if x.notna().sum() < MIN_GATE_TRAIN_EVENTS:
            continue
        if feat in CATEGORICAL_FEATURES + OPTIONAL_SAFE_CATEGORICAL or (feat == "direction_num" and ALLOW_DIRECTION):
            values = sorted([v for v in x.dropna().unique().tolist() if math.isfinite(float(v))])
            for v in values:
                mask = (x == float(v)).fillna(False)
                sub = train.loc[mask]
                if len(sub) < MIN_GATE_TRAIN_EVENTS:
                    continue
                m = metrics(sub)
                score = gate_score(m, len(train))
                gates.append(GateDef(
                    gate_name=f"{feat}_eq_{_safe_float(v)}",
                    gate_kind="categorical_bucket",
                    feature=feat,
                    side="eq",
                    value=float(v),
                    train_score=score,
                    train_events=m.events,
                    train_pf_x4=m.pf_x4,
                    train_pf_x6=m.pf_x6,
                    train_total_x4=m.total_x4,
                ))
        else:
            for q in QUANTILES:
                threshold = x.quantile(q)
                if pd.isna(threshold):
                    continue
                for side in ["ge", "le"]:
                    mask = (x >= threshold) if side == "ge" else (x <= threshold)
                    sub = train.loc[mask.fillna(False)]
                    if len(sub) < MIN_GATE_TRAIN_EVENTS:
                        continue
                    m = metrics(sub)
                    score = gate_score(m, len(train))
                    gates.append(GateDef(
                        gate_name=f"{feat}_{side}_q{int(q*100)}",
                        gate_kind="numeric_quantile",
                        feature=feat,
                        side=side,
                        threshold=float(threshold),
                        train_score=score,
                        train_events=m.events,
                        train_pf_x4=m.pf_x4,
                        train_pf_x6=m.pf_x6,
                        train_total_x4=m.total_x4,
                    ))
    gates.sort(key=lambda g: (g.train_score, g.train_total_x4, g.train_events), reverse=True)
    return gates


def gate_score(m: Metrics, universe_events: int) -> float:
    pf4 = min(m.pf_x4 if math.isfinite(m.pf_x4) else 25.0, 25.0)
    pf6 = min(m.pf_x6 if math.isfinite(m.pf_x6) else 25.0, 25.0)
    # Penalize tiny retained sets, but allow sparse genuinely high-PF filters.
    event_term = min(m.events / max(1.0, universe_events), 0.6)
    total_term = 0.002 * m.total_x4
    return _safe_float(1.0 * pf4 + 0.35 * pf6 + 1.5 * event_term + total_term)


def evaluate_gate(gate: GateDef, df: pd.DataFrame) -> Dict[str, Any]:
    mask = gate.apply(df)
    sub = df.loc[mask]
    m = metrics(sub)
    return {
        "gate_name": gate.gate_name,
        "gate_kind": gate.gate_kind,
        "feature": gate.feature,
        "side": gate.side,
        "threshold": _safe_float(gate.threshold) if gate.threshold is not None else None,
        "value": _safe_float(gate.value) if gate.value is not None else None,
        **{f"test_{k}": v for k, v in asdict(m).items()},
        "retained_ratio": _safe_float(len(sub) / max(1, len(df))),
    }


def yearly_walk_forward(df: pd.DataFrame, features: Sequence[str]) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rows: List[Dict[str, Any]] = []
    selected_rows: List[Dict[str, Any]] = []
    ensemble_rows: List[Dict[str, Any]] = []
    predictions: List[pd.DataFrame] = []
    years = sorted([int(y) for y in pd.to_numeric(df["year"], errors="coerce").dropna().unique().tolist()])
    for year in years:
        train = df.loc[df["year"] < year].copy()
        test = df.loc[df["year"] == year].copy()
        if len(train) < MIN_TRAIN_EVENTS or len(test) < MIN_TEST_EVENTS:
            rows.append({
                "year": year,
                "status": "skipped_insufficient_train_or_test",
                "train_events": int(len(train)),
                "test_events": int(len(test)),
            })
            continue
        gates = generate_candidate_gates(train, features)
        gates = gates[:TOP_K_GATES]
        for rank, gate in enumerate(gates, start=1):
            selected_rows.append({"year": year, "rank": rank, **gate.to_dict()})
            ev = evaluate_gate(gate, test)
            rows.append({
                "year": year,
                "status": "tested",
                "train_events": int(len(train)),
                "test_events": int(len(test)),
                "rank": rank,
                "train_score": gate.train_score,
                **ev,
            })
        if gates:
            votes = pd.Series(0, index=test.index, dtype=int)
            vote_names: List[str] = []
            for gate in gates:
                vote_mask = gate.apply(test)
                votes += vote_mask.astype(int)
                vote_names.append(gate.gate_name)
            for vote_min in sorted(set([1, 2, 3, max(1, VOTE_MIN)])):
                sub = test.loc[votes >= vote_min]
                m = metrics(sub)
                ensemble_rows.append({
                    "year": year,
                    "status": "tested",
                    "train_events": int(len(train)),
                    "test_events": int(len(test)),
                    "vote_min": int(vote_min),
                    "kept_events": int(len(sub)),
                    **asdict(m),
                    "top_gates": ";".join(vote_names[:TOP_K_GATES]),
                })
            pred = test[[c for c in ["stage30b_event_uid", "entry_ts_norm", "source_stage", "family", "candidate_name", "net_x4", "net_x6", "year"] if c in test.columns]].copy()
            pred["gate_vote_count"] = votes.values
            pred["selected_vote_min"] = VOTE_MIN
            pred["selected_by_scorecard"] = pred["gate_vote_count"] >= VOTE_MIN
            predictions.append(pred)
    return pd.DataFrame(rows), pd.DataFrame(selected_rows), pd.DataFrame(ensemble_rows), (pd.concat(predictions, ignore_index=True) if predictions else pd.DataFrame())


def family_holdout(df: pd.DataFrame, features: Sequence[str]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    if "source_stage" not in df.columns or "family" not in df.columns:
        return pd.DataFrame(rows)
    groups = df.groupby(["source_stage", "family"], dropna=False)
    for (stage, family), holdout in groups:
        if len(holdout) < MIN_GATE_TEST_EVENTS:
            continue
        train = df.drop(index=holdout.index)
        if len(train) < MIN_TRAIN_EVENTS:
            continue
        gates = generate_candidate_gates(train, features)[:TOP_K_GATES]
        if not gates:
            continue
        votes = pd.Series(0, index=holdout.index, dtype=int)
        for gate in gates:
            votes += gate.apply(holdout).astype(int)
        for vote_min in [1, max(1, VOTE_MIN)]:
            sub = holdout.loc[votes >= vote_min]
            m = metrics(sub)
            rows.append({
                "holdout_source_stage": stage,
                "holdout_family": family,
                "holdout_events": int(len(holdout)),
                "train_events": int(len(train)),
                "vote_min": int(vote_min),
                "kept_events": int(len(sub)),
                **asdict(m),
            })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["vote_min", "events", "pf_x4"], ascending=[True, False, False]).reset_index(drop=True)
    return out


def summarize_oos(oos: pd.DataFrame, ensemble: pd.DataFrame) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    valid = oos.loc[oos.get("status") == "tested"].copy() if not oos.empty else pd.DataFrame()
    if not valid.empty:
        top1 = valid.loc[valid["rank"] == 1].copy()
        summary["top1_years_tested"] = int(top1["year"].nunique())
        summary["top1_kept_events"] = int(pd.to_numeric(top1.get("test_events", pd.Series(dtype=float)), errors="coerce").sum()) if "test_events" in top1.columns else 0
        # Aggregate by reconstructing from already evaluated metrics is not exact for PF, so expose weighted totals and median PFs.
        summary["top1_pf_x4_median"] = _safe_float(pd.to_numeric(top1["test_pf_x4"], errors="coerce").replace([np.inf, -np.inf], np.nan).median())
        summary["top1_pf_x6_median"] = _safe_float(pd.to_numeric(top1["test_pf_x6"], errors="coerce").replace([np.inf, -np.inf], np.nan).median())
        summary["top1_total_x4_sum"] = _safe_float(pd.to_numeric(top1["test_total_x4"], errors="coerce").sum())
    ens = ensemble.loc[ensemble.get("status") == "tested"].copy() if not ensemble.empty else pd.DataFrame()
    if not ens.empty:
        for vote_min in sorted(ens["vote_min"].dropna().unique().tolist()):
            sub = ens.loc[ens["vote_min"] == vote_min]
            summary[f"ensemble_vote{int(vote_min)}_years"] = int(sub["year"].nunique())
            summary[f"ensemble_vote{int(vote_min)}_kept_events"] = int(pd.to_numeric(sub["kept_events"], errors="coerce").sum())
            summary[f"ensemble_vote{int(vote_min)}_total_x4_sum"] = _safe_float(pd.to_numeric(sub["total_x4"], errors="coerce").sum())
            summary[f"ensemble_vote{int(vote_min)}_pf_x4_median"] = _safe_float(pd.to_numeric(sub["pf_x4"], errors="coerce").replace([np.inf, -np.inf], np.nan).median())
            summary[f"ensemble_vote{int(vote_min)}_pf_x6_median"] = _safe_float(pd.to_numeric(sub["pf_x6"], errors="coerce").replace([np.inf, -np.inf], np.nan).median())
    return summary


def decide(base: Metrics, oos_summary: Dict[str, Any], features: Sequence[str]) -> str:
    kept = int(oos_summary.get(f"ensemble_vote{VOTE_MIN}_kept_events", 0))
    total = float(oos_summary.get(f"ensemble_vote{VOTE_MIN}_total_x4_sum", 0.0))
    pf4 = float(oos_summary.get(f"ensemble_vote{VOTE_MIN}_pf_x4_median", 0.0))
    pf6 = float(oos_summary.get(f"ensemble_vote{VOTE_MIN}_pf_x6_median", 0.0))
    years = int(oos_summary.get(f"ensemble_vote{VOTE_MIN}_years", 0))
    if kept >= 80 and years >= 3 and total > 0 and pf4 >= 1.25 and pf6 >= 0.75:
        return "STAGE30B_HAS_ML_LITE_SCORECARD_CANDIDATE_REVIEW_ONLY"
    if kept >= 40 and total > 0 and pf4 >= 1.0:
        return "STAGE30B_WATCHLIST_ONLY_NEEDS_STRONGER_VALIDATION"
    return "STAGE30B_NO_ML_LITE_PROMOTION_KEEP_RESEARCH_OPEN"


def write_outputs(
    df: pd.DataFrame,
    dataset_meta: Dict[str, Any],
    features: List[str],
    blocked: List[str],
    coverage: Dict[str, float],
    oos: pd.DataFrame,
    selected: pd.DataFrame,
    ensemble: pd.DataFrame,
    preds: pd.DataFrame,
    holdout: pd.DataFrame,
) -> Dict[str, Any]:
    base = metrics(df)
    oos_summary = summarize_oos(oos, ensemble)
    decision = decide(base, oos_summary, features)

    json_path = REPORT_DIR / "stage30b_ml_lite_feature_ranker.json"
    md_path = REPORT_DIR / "stage30b_ml_lite_feature_ranker.md"
    oos_path = REPORT_DIR / "stage30b_yearly_oos_gate_results.csv"
    selected_path = REPORT_DIR / "stage30b_selected_train_gates.csv"
    ensemble_path = REPORT_DIR / "stage30b_scorecard_ensemble_oos.csv"
    preds_path = REPORT_DIR / "stage30b_scorecard_predictions.csv"
    holdout_path = REPORT_DIR / "stage30b_family_holdout.csv"

    oos.to_csv(oos_path, index=False)
    selected.to_csv(selected_path, index=False)
    ensemble.to_csv(ensemble_path, index=False)
    preds.to_csv(preds_path, index=False)
    holdout.to_csv(holdout_path, index=False)

    result = {
        "decision": decision,
        "scope_guardrails": [
            "Research/shadow ML-lite screening only.",
            "No EA change, no automatic trading, no paper/live/order authorization.",
            "Consumes Stage30A ML-ready dataset; existing trade artifacts remain research evidence only.",
            "Uses strict forward-safe feature whitelist and blocks source/stage/candidate fields from modeling.",
            "direction_num is blocked by default unless STAGE30B_ALLOW_DIRECTION=1.",
            "Gates are selected on prior training years and evaluated on future test years.",
        ],
        "dataset_meta": dataset_meta,
        "base_metrics": asdict(base),
        "features_used": features,
        "blocked_features": blocked,
        "feature_coverage": coverage,
        "counts": {
            "rows_used_after_dedup": int(len(df)),
            "years": sorted([int(y) for y in df["year"].dropna().unique().tolist()]) if "year" in df.columns else [],
            "feature_count": int(len(features)),
            "selected_gate_rows": int(len(selected)),
            "oos_gate_rows": int(len(oos)),
            "ensemble_rows": int(len(ensemble)),
            "family_holdout_rows": int(len(holdout)),
        },
        "oos_summary": oos_summary,
        "output_files": {
            "json": str(json_path),
            "md": str(md_path),
            "yearly_oos_gate_results": str(oos_path),
            "selected_train_gates": str(selected_path),
            "scorecard_ensemble_oos": str(ensemble_path),
            "scorecard_predictions": str(preds_path),
            "family_holdout": str(holdout_path),
        },
    }
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    lines: List[str] = []
    lines.append("# Stage30B ML-lite Feature Ranker / Scorecard")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append("```text")
    lines.append(decision)
    lines.append("```")
    lines.append("")
    lines.append("## Scope guardrails")
    lines.append("")
    for item in result["scope_guardrails"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Dataset")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(dataset_meta, indent=2, ensure_ascii=False, default=str))
    lines.append("```")
    lines.append("")
    lines.append("## Base dataset metrics after Stage30B dedup")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(asdict(base), indent=2, ensure_ascii=False, default=str))
    lines.append("```")
    lines.append("")
    lines.append("## Features")
    lines.append("")
    lines.append(f"- features_used: `{', '.join(features) if features else 'none'}`")
    lines.append(f"- blocked_features: `{', '.join(blocked)}`")
    lines.append("- feature_coverage:")
    lines.append("```json")
    lines.append(json.dumps(coverage, indent=2, ensure_ascii=False, default=str))
    lines.append("```")
    lines.append("")
    lines.append("## Counts")
    lines.append("")
    for k, v in result["counts"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")
    lines.append("## OOS summary")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(oos_summary, indent=2, ensure_ascii=False, default=str))
    lines.append("```")
    lines.append("")
    lines.append("## Top selected train gates")
    lines.append("")
    lines.append(markdown_table(selected, ["year", "rank", "gate_name", "feature", "side", "threshold", "value", "train_events", "train_pf_x4", "train_pf_x6", "train_total_x4", "train_score"], 30))
    lines.append("")
    lines.append("## Yearly OOS gate diagnostics")
    lines.append("")
    lines.append(markdown_table(oos, ["year", "status", "rank", "gate_name", "test_events", "test_pf_x4", "test_pf_x6", "test_total_x4", "test_win_rate_x4", "retained_ratio"], 40))
    lines.append("")
    lines.append("## Scorecard ensemble OOS")
    lines.append("")
    lines.append(markdown_table(ensemble, ["year", "vote_min", "kept_events", "pf_x4", "pf_x6", "total_x4", "win_rate_x4", "train_events", "test_events"], 40))
    lines.append("")
    lines.append("## Family/source holdout diagnostics")
    lines.append("")
    lines.append(markdown_table(holdout, ["holdout_source_stage", "holdout_family", "holdout_events", "vote_min", "kept_events", "pf_x4", "pf_x6", "total_x4", "win_rate_x4"], 40))
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("- Stage30B is a ML-lite scorecard/gate ranker, not a tradable strategy.")
    lines.append("- Because the candidate pool contains many weak raw-entry artifacts, family/source holdout is critical.")
    lines.append("- If a scorecard candidate appears here, the next stage must validate it on a stricter deduped pool and then create a separate forward-shadow tracker.")
    lines.append("- If no scorecard survives, the next useful step is adding exogenous/macro/news features, not adding higher-capacity ML to the same OHLC-only features.")
    lines.append("")
    lines.append("## Operational reminder")
    lines.append("")
    lines.append("```bash")
    lines.append("cd ~/Desktop/xauusd-trader")
    lines.append("python3 -m app.stage30a_candidate_pool_builder_ml_dataset")
    lines.append("python3 -m app.stage30b_ml_lite_feature_ranker")
    lines.append("```")
    lines.append("")
    lines.append("## Output files")
    lines.append("")
    for path in result["output_files"].values():
        lines.append(f"- `{path}`")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return result


def main() -> None:
    df, dataset_meta = load_dataset(DEFAULT_DATASET)
    if df.empty:
        result = {
            "decision": "STAGE30B_DATASET_NOT_READY",
            "dataset_meta": dataset_meta,
            "output_files": {},
        }
        (REPORT_DIR / "stage30b_ml_lite_feature_ranker.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        (REPORT_DIR / "stage30b_ml_lite_feature_ranker.md").write_text("# Stage30B ML-lite Feature Ranker\n\nDataset not ready. Run Stage30A first.\n", encoding="utf-8")
        return
    features, blocked, coverage = usable_features(df)
    oos, selected, ensemble, preds = yearly_walk_forward(df, features)
    holdout = family_holdout(df, features)
    write_outputs(df, dataset_meta, features, blocked, coverage, oos, selected, ensemble, preds, holdout)


if __name__ == "__main__":
    main()
