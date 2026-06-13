"""Stage31B: forward-safe exogenous/macro gate validation.

Research/shadow only. This module consumes the Stage31A enriched ML dataset and
validates exogenous gates with expanding, year-by-year calibration. It does not
change EA behavior, does not authorize paper/live/order execution, and does not
fetch data from the internet.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


DEFAULT_DATASET_PATH = Path(
    "data/reports/stage31a_exogenous_feature_ingestion/stage31a_exogenous_ml_dataset.csv"
)
DEFAULT_OUT_DIR = Path("data/reports/stage31b_exogenous_gate_validation")
EXOG_PREFIXES = ("dxy_", "us10y_", "real_yield_", "vix_", "spx_", "oil_")
DEFAULT_QUANTILES = (0.20, 0.30, 0.70, 0.80)
MIN_SCOPE_ROWS = 120
MIN_TRAIN_ROWS = 250
MIN_TEST_ROWS = 25
MIN_GATE_EVENTS = 30
BOOT_N = 400
RNG_SEED = 3131


@dataclass
class MetricBundle:
    events: int
    pf_x4: float
    pf_x6: float
    total_x4: float
    total_x6: float
    win_rate_x4: float
    median_x4: float
    avg_x4: float
    years_tested: int
    years_positive_x4: int
    min_year_events: int


@dataclass
class GateResult:
    scope_type: str
    scope_value: str
    feature: str
    gate: str
    direction: str
    quantile: float
    wf_events: int
    wf_retained_ratio: float
    threshold_avg: float
    threshold_min: float
    threshold_max: float
    base_events: int
    base_pf_x4: float
    base_total_x4: float
    wf_pf_x4: float
    wf_pf_x6: float
    wf_total_x4: float
    wf_total_x6: float
    wf_win_rate_x4: float
    wf_median_x4: float
    wf_avg_x4: float
    years_tested: int
    years_positive_x4: int
    min_year_events: int
    lift_pf_x4: float
    lift_total_x4: float
    boot_p05_total_x4: float
    decision: str
    rank_score: float


def now_iso() -> str:
    return pd.Timestamp.now(tz="UTC").isoformat()


def safe_float(x: object, default: float = 0.0) -> float:
    try:
        if pd.isna(x):
            return default
        return float(x)
    except Exception:
        return default


def profit_factor(values: pd.Series) -> float:
    vals = pd.to_numeric(values, errors="coerce").dropna()
    if vals.empty:
        return 0.0
    gains = vals[vals > 0].sum()
    losses = -vals[vals < 0].sum()
    if losses <= 0:
        return float("inf") if gains > 0 else 0.0
    return float(gains / losses)


def metrics(df: pd.DataFrame) -> MetricBundle:
    if df.empty or "net_x4" not in df.columns:
        return MetricBundle(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0, 0)
    net4 = pd.to_numeric(df["net_x4"], errors="coerce").fillna(0.0)
    net6 = pd.to_numeric(df.get("net_x6", pd.Series(index=df.index, dtype=float)), errors="coerce").fillna(0.0)
    if "year" in df.columns:
        years = pd.to_numeric(df["year"], errors="coerce")
    else:
        years = pd.Series(np.nan, index=df.index)
    year_stats = pd.DataFrame({"year": years, "net_x4": net4}).dropna(subset=["year"])
    years_tested = int(year_stats["year"].nunique()) if not year_stats.empty else 0
    if not year_stats.empty:
        by_year = year_stats.groupby("year")["net_x4"].agg(["sum", "count"])
        years_positive = int((by_year["sum"] > 0).sum())
        min_year_events = int(by_year["count"].min())
    else:
        years_positive = 0
        min_year_events = 0
    return MetricBundle(
        events=int(len(df)),
        pf_x4=profit_factor(net4),
        pf_x6=profit_factor(net6),
        total_x4=float(net4.sum()),
        total_x6=float(net6.sum()),
        win_rate_x4=float((net4 > 0).mean()) if len(net4) else 0.0,
        median_x4=float(net4.median()) if len(net4) else 0.0,
        avg_x4=float(net4.mean()) if len(net4) else 0.0,
        years_tested=years_tested,
        years_positive_x4=years_positive,
        min_year_events=min_year_events,
    )


def load_dataset(path: Path) -> Tuple[pd.DataFrame, Dict[str, object]]:
    info: Dict[str, object] = {"dataset_path": str(path), "loaded": False}
    if not path.exists():
        info["error"] = "missing_dataset"
        return pd.DataFrame(), info
    try:
        df = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        info["error"] = "empty_dataset"
        return pd.DataFrame(), info
    except Exception as exc:  # pragma: no cover - diagnostic branch
        info["error"] = f"read_error:{type(exc).__name__}:{exc}"
        return pd.DataFrame(), info
    info.update({"loaded": True, "rows_raw": int(len(df)), "columns": list(df.columns)})
    for col in ("net_x4", "net_x6", "year"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "year" not in df.columns:
        if "entry_ts_norm" in df.columns:
            ts = pd.to_datetime(df["entry_ts_norm"], errors="coerce", utc=True)
            df["year"] = ts.dt.year
        else:
            df["year"] = np.nan
    df = df.dropna(subset=["net_x4", "year"]).copy()
    df["year"] = df["year"].astype(int)
    info["rows_after_required_parse"] = int(len(df))
    return df, info


def exogenous_features(df: pd.DataFrame) -> List[str]:
    cols: List[str] = []
    for c in df.columns:
        if not c.startswith(EXOG_PREFIXES):
            continue
        if c.endswith("_age_hours"):
            # Age is a data-freshness diagnostic; not a macro state edge by itself.
            continue
        s = pd.to_numeric(df[c], errors="coerce")
        coverage = float(s.notna().mean()) if len(s) else 0.0
        nunique = int(s.nunique(dropna=True))
        if coverage >= 0.50 and nunique >= 8:
            cols.append(c)
    return cols


def scope_frames(df: pd.DataFrame) -> List[Tuple[str, str, pd.DataFrame]]:
    scopes: List[Tuple[str, str, pd.DataFrame]] = [("ALL", "ALL", df)]
    for col, scope_type, max_groups in [
        ("source_stage", "source_stage", 20),
        ("family", "family", 25),
        ("candidate_name", "candidate_name", 40),
    ]:
        if col not in df.columns:
            continue
        counts = df[col].fillna("NA").astype(str).value_counts()
        for value in counts.head(max_groups).index:
            sub = df[df[col].fillna("NA").astype(str) == value].copy()
            if len(sub) >= MIN_SCOPE_ROWS:
                scopes.append((scope_type, str(value), sub))
    return scopes


def apply_gate(series: pd.Series, direction: str, threshold: float) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    if direction == "ge":
        return values >= threshold
    return values <= threshold


def bootstrap_p05_total(values: Sequence[float], n: int = BOOT_N) -> float:
    arr = np.asarray([v for v in values if not pd.isna(v)], dtype=float)
    if arr.size < 10:
        return float(np.nansum(arr)) if arr.size else 0.0
    rng = np.random.default_rng(RNG_SEED)
    totals = np.empty(n, dtype=float)
    for i in range(n):
        sample = rng.choice(arr, size=arr.size, replace=True)
        totals[i] = sample.sum()
    return float(np.quantile(totals, 0.05))


def expanding_validate(
    df: pd.DataFrame,
    feature: str,
    q: float,
    direction: str,
) -> Tuple[pd.DataFrame, Dict[str, float]]:
    rows: List[pd.DataFrame] = []
    thresholds: List[float] = []
    years = sorted(int(y) for y in pd.Series(df["year"]).dropna().unique())
    for test_year in years:
        train = df[df["year"] < test_year].copy()
        test = df[df["year"] == test_year].copy()
        if len(train) < MIN_TRAIN_ROWS or len(test) < MIN_TEST_ROWS:
            continue
        train_feature = pd.to_numeric(train[feature], errors="coerce").dropna()
        if len(train_feature) < MIN_TRAIN_ROWS or train_feature.nunique() < 8:
            continue
        threshold = float(train_feature.quantile(q))
        mask = apply_gate(test[feature], direction, threshold)
        kept = test[mask].copy()
        if kept.empty:
            continue
        kept["stage31b_test_year"] = test_year
        kept["stage31b_threshold"] = threshold
        kept["stage31b_feature"] = feature
        kept["stage31b_gate_direction"] = direction
        kept["stage31b_gate_quantile"] = q
        rows.append(kept)
        thresholds.append(threshold)
    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    threshold_info = {
        "threshold_avg": float(np.mean(thresholds)) if thresholds else 0.0,
        "threshold_min": float(np.min(thresholds)) if thresholds else 0.0,
        "threshold_max": float(np.max(thresholds)) if thresholds else 0.0,
    }
    return out, threshold_info


def decide(result: MetricBundle, base: MetricBundle, boot_p05: float) -> str:
    if result.events < MIN_GATE_EVENTS:
        return "REJECT_TOO_FEW_EVENTS"
    if result.years_tested < 3:
        return "REJECT_TOO_FEW_YEARS"
    if result.pf_x4 >= 1.20 and result.pf_x6 >= 1.00 and result.total_x4 > 0 and boot_p05 > 0 and result.years_positive_x4 >= 3:
        return "REVIEW_STRONG_FORWARD_SAFE_CANDIDATE"
    if result.pf_x4 > base.pf_x4 and result.total_x4 > base.total_x4 and result.pf_x4 >= 0.80 and result.years_positive_x4 >= 2:
        return "REVIEW_WEAK_IMPROVEMENT_ONLY"
    return "REJECT_NO_FORWARD_EDGE"


def rank_score(result: MetricBundle, base: MetricBundle, boot_p05: float) -> float:
    pf = 10.0 if math.isinf(result.pf_x4) else result.pf_x4
    base_pf = 10.0 if math.isinf(base.pf_x4) else base.pf_x4
    return float(
        (pf - base_pf) * 25.0
        + result.total_x4 / 100.0
        + boot_p05 / 250.0
        + result.years_positive_x4 * 4.0
        + min(result.events, 500) / 100.0
    )


def validate_scope(scope_type: str, scope_value: str, df: pd.DataFrame, features: Sequence[str]) -> List[GateResult]:
    if len(df) < MIN_SCOPE_ROWS:
        return []
    base = metrics(df)
    out: List[GateResult] = []
    for feature in features:
        if feature not in df.columns:
            continue
        s = pd.to_numeric(df[feature], errors="coerce")
        if s.notna().sum() < MIN_TRAIN_ROWS or s.nunique(dropna=True) < 8:
            continue
        for q in DEFAULT_QUANTILES:
            direction = "le" if q < 0.5 else "ge"
            wf, th = expanding_validate(df, feature, q, direction)
            m = metrics(wf)
            if m.events <= 0:
                continue
            retained = float(m.events / base.events) if base.events else 0.0
            boot = bootstrap_p05_total(pd.to_numeric(wf.get("net_x4", pd.Series(dtype=float)), errors="coerce"))
            dec = decide(m, base, boot)
            score = rank_score(m, base, boot)
            out.append(
                GateResult(
                    scope_type=scope_type,
                    scope_value=scope_value,
                    feature=feature,
                    gate=f"{feature}_{direction}_q{int(q * 100)}",
                    direction=direction,
                    quantile=float(q),
                    wf_events=m.events,
                    wf_retained_ratio=retained,
                    threshold_avg=th["threshold_avg"],
                    threshold_min=th["threshold_min"],
                    threshold_max=th["threshold_max"],
                    base_events=base.events,
                    base_pf_x4=base.pf_x4,
                    base_total_x4=base.total_x4,
                    wf_pf_x4=m.pf_x4,
                    wf_pf_x6=m.pf_x6,
                    wf_total_x4=m.total_x4,
                    wf_total_x6=m.total_x6,
                    wf_win_rate_x4=m.win_rate_x4,
                    wf_median_x4=m.median_x4,
                    wf_avg_x4=m.avg_x4,
                    years_tested=m.years_tested,
                    years_positive_x4=m.years_positive_x4,
                    min_year_events=m.min_year_events,
                    lift_pf_x4=(m.pf_x4 - base.pf_x4) if not math.isinf(m.pf_x4) and not math.isinf(base.pf_x4) else 0.0,
                    lift_total_x4=m.total_x4 - base.total_x4,
                    boot_p05_total_x4=boot,
                    decision=dec,
                    rank_score=score,
                )
            )
    return out


def df_to_markdown(df: pd.DataFrame, limit: int = 30) -> str:
    if df.empty:
        return "_No rows._"
    view = df.head(limit).copy()
    try:
        return view.to_markdown(index=False)
    except Exception:
        # Avoid optional dependency failures on minimal runners.
        cols = list(view.columns)
        lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
        for _, row in view.iterrows():
            vals = [str(row.get(c, "")) for c in cols]
            lines.append("| " + " | ".join(vals) + " |")
        return "\n".join(lines)


def write_outputs(
    out_dir: Path,
    report: Dict[str, object],
    results_df: pd.DataFrame,
    selected_df: pd.DataFrame,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "stage31b_exogenous_gate_validation.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    results_df.to_csv(out_dir / "stage31b_gate_results.csv", index=False)
    selected_df.to_csv(out_dir / "stage31b_candidate_review.csv", index=False)
    lines: List[str] = []
    lines.append("# Stage31B Exogenous/Macro Gate Validation")
    lines.append("")
    lines.append(f"Generated UTC: `{report['generated_utc']}`")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append("```text")
    lines.append(str(report["decision"]))
    lines.append("```")
    lines.append("")
    lines.append("## Scope guardrails")
    lines.append("")
    lines.extend([
        "- Research/shadow validation only.",
        "- No EA change, no automatic trading, no paper/live/order authorization.",
        "- Consumes the Stage31A enriched dataset only; no internet fetch is performed.",
        "- Gate thresholds are calibrated with expanding prior-year data only.",
        "- Results are review-only even if a candidate is strong.",
    ])
    lines.append("")
    lines.append("## Dataset")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(report["dataset"], indent=2, ensure_ascii=False))
    lines.append("```")
    lines.append("")
    lines.append("## Counts")
    lines.append("")
    for key in [
        "feature_count",
        "scope_count",
        "gate_result_count",
        "candidate_review_count",
        "strong_candidate_count",
        "weak_improvement_count",
    ]:
        lines.append(f"- {key}: `{report.get(key)}`")
    lines.append("")
    lines.append("## Candidate review sample")
    lines.append("")
    if selected_df.empty:
        lines.append("No forward-safe exogenous gate passed review thresholds.")
    else:
        sample_cols = [
            "decision", "scope_type", "scope_value", "feature", "gate", "wf_events", "wf_pf_x4",
            "wf_pf_x6", "wf_total_x4", "boot_p05_total_x4", "years_positive_x4", "years_tested", "rank_score",
        ]
        lines.append(df_to_markdown(selected_df[[c for c in sample_cols if c in selected_df.columns]], 30))
    lines.append("")
    lines.append("## Top rejected / diagnostic gates")
    lines.append("")
    top_cols = [
        "decision", "scope_type", "scope_value", "feature", "gate", "wf_events", "wf_pf_x4",
        "wf_total_x4", "base_pf_x4", "base_total_x4", "rank_score",
    ]
    lines.append(df_to_markdown(results_df[[c for c in top_cols if c in results_df.columns]], 40))
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.extend([
        "- A rejected result does not mean macro data is useless; it means these simple forward-safe quantile gates did not validate on the current candidate pool/scope.",
        "- Candidate-pool quality still matters: Stage30A included weak families, so lineage-specific results should be read before global results.",
        "- Promotion requires a separate forward-shadow tracker; this stage cannot authorize execution.",
    ])
    lines.append("")
    lines.append("## Output files")
    lines.append("")
    lines.extend([
        f"- `{out_dir / 'stage31b_exogenous_gate_validation.json'}`",
        f"- `{out_dir / 'stage31b_exogenous_gate_validation.md'}`",
        f"- `{out_dir / 'stage31b_gate_results.csv'}`",
        f"- `{out_dir / 'stage31b_candidate_review.csv'}`",
    ])
    (out_dir / "stage31b_exogenous_gate_validation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    dataset_path = Path(os.environ.get("STAGE31B_DATASET_PATH", str(DEFAULT_DATASET_PATH)))
    out_dir = Path(os.environ.get("STAGE31B_OUT_DIR", str(DEFAULT_OUT_DIR)))
    df, dataset_info = load_dataset(dataset_path)
    report: Dict[str, object] = {
        "stage": "31B",
        "generated_utc": now_iso(),
        "dataset": dataset_info,
        "decision": "STAGE31B_NOT_RUN_DATASET_MISSING_REVIEW_ONLY",
        "feature_count": 0,
        "scope_count": 0,
        "gate_result_count": 0,
        "candidate_review_count": 0,
        "strong_candidate_count": 0,
        "weak_improvement_count": 0,
    }
    if df.empty:
        write_outputs(out_dir, report, pd.DataFrame(), pd.DataFrame())
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    features = exogenous_features(df)
    scopes = scope_frames(df)
    report["feature_count"] = int(len(features))
    report["features"] = features
    report["scope_count"] = int(len(scopes))
    if not features:
        report["decision"] = "STAGE31B_NO_EXOGENOUS_FEATURES_REVIEW_ONLY"
        write_outputs(out_dir, report, pd.DataFrame(), pd.DataFrame())
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    all_results: List[GateResult] = []
    for scope_type, scope_value, sub in scopes:
        all_results.extend(validate_scope(scope_type, scope_value, sub, features))
    results_df = pd.DataFrame([asdict(r) for r in all_results])
    if results_df.empty:
        report["decision"] = "STAGE31B_NO_VALID_GATE_RESULTS_REVIEW_ONLY"
        write_outputs(out_dir, report, results_df, results_df)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    results_df = results_df.sort_values(["decision", "rank_score", "wf_total_x4"], ascending=[True, False, False]).reset_index(drop=True)
    selected_df = results_df[results_df["decision"].isin([
        "REVIEW_STRONG_FORWARD_SAFE_CANDIDATE",
        "REVIEW_WEAK_IMPROVEMENT_ONLY",
    ])].sort_values(["decision", "rank_score"], ascending=[True, False]).reset_index(drop=True)
    strong_count = int((selected_df["decision"] == "REVIEW_STRONG_FORWARD_SAFE_CANDIDATE").sum()) if not selected_df.empty else 0
    weak_count = int((selected_df["decision"] == "REVIEW_WEAK_IMPROVEMENT_ONLY").sum()) if not selected_df.empty else 0
    report.update({
        "gate_result_count": int(len(results_df)),
        "candidate_review_count": int(len(selected_df)),
        "strong_candidate_count": strong_count,
        "weak_improvement_count": weak_count,
    })
    if strong_count > 0:
        report["decision"] = "STAGE31B_HAS_STRONG_EXOGENOUS_GATE_CANDIDATE_REVIEW_ONLY"
    elif weak_count > 0:
        report["decision"] = "STAGE31B_HAS_WEAK_EXOGENOUS_GATE_IMPROVEMENT_REVIEW_ONLY"
    else:
        report["decision"] = "STAGE31B_NO_EXOGENOUS_GATE_PROMOTION_KEEP_RESEARCH_OPEN"
    write_outputs(out_dir, report, results_df, selected_df)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
