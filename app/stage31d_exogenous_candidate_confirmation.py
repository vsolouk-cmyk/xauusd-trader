#!/usr/bin/env python3
"""Stage31D - Exogenous candidate confirmation audit.

Research/shadow validation only. This module consumes Stage31A enriched dataset and
Stage31C candidate diagnostics. It performs a stricter confirmation pass on the
best Stage31C exogenous gates using expanding prior-year thresholds, event
deduplication, year diagnostics, bootstrap stress, and simple cost stress tests.

It does not change any EA, paper/live, order, or execution configuration.
"""
from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = Path(os.environ.get("XAUUSD_ROOT", ".")).resolve()
DATASET_PATH = Path(os.environ.get(
    "STAGE31A_DATASET",
    "data/reports/stage31a_exogenous_feature_ingestion/stage31a_exogenous_ml_dataset.csv",
))
STAGE31C_CANDIDATE_PATH = Path(os.environ.get(
    "STAGE31C_CANDIDATES",
    "data/reports/stage31c_exogenous_edge_audit/stage31c_candidate_review.csv",
))
STAGE31C_AUDIT_PATH = Path(os.environ.get(
    "STAGE31C_AUDIT",
    "data/reports/stage31c_exogenous_edge_audit/stage31c_exogenous_edge_audit.csv",
))
REPORT_DIR = Path(os.environ.get(
    "STAGE31D_REPORT_DIR",
    "data/reports/stage31d_exogenous_candidate_confirmation",
))
TOP_N = int(os.environ.get("STAGE31D_TOP_N", "40"))
BOOT_N = int(os.environ.get("STAGE31D_BOOT_N", "500"))
RANDOM_SEED = int(os.environ.get("STAGE31D_RANDOM_SEED", "31031"))
MIN_EVENTS = int(os.environ.get("STAGE31D_MIN_EVENTS", "50"))
MIN_YEARS = int(os.environ.get("STAGE31D_MIN_YEARS", "3"))

STRONG_PF_X4 = float(os.environ.get("STAGE31D_STRONG_PF_X4", "2.0"))
STRONG_TOTAL_X4 = float(os.environ.get("STAGE31D_STRONG_TOTAL_X4", "100.0"))
STRONG_BOOT_P05 = float(os.environ.get("STAGE31D_STRONG_BOOT_P05", "0.0"))
STRONG_YEARS_POS_RATIO = float(os.environ.get("STAGE31D_STRONG_YEARS_POS_RATIO", "0.75"))
STRESS_R = [0.05, 0.10, 0.20]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def safe_float(x, default=np.nan) -> float:
    try:
        if pd.isna(x):
            return default
        return float(x)
    except Exception:
        return default


def ensure_year(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "entry_ts_norm" in out.columns:
        ts = pd.to_datetime(out["entry_ts_norm"], errors="coerce", utc=True)
        out["_entry_ts"] = ts
        if "year" not in out.columns:
            out["year"] = ts.dt.year
    else:
        if "year" not in out.columns:
            out["year"] = np.nan
        out["_entry_ts"] = pd.NaT
    out["year"] = pd.to_numeric(out["year"], errors="coerce").astype("Int64")
    return out.dropna(subset=["year"]).copy()


def load_dataset(path: Path) -> Tuple[pd.DataFrame, Dict]:
    info = {"path": str(path), "exists": path.exists(), "loaded": False}
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(), info
    try:
        df = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        info["error"] = "EmptyDataError"
        return pd.DataFrame(), info
    info.update({"loaded": True, "rows_raw": int(len(df)), "columns": list(df.columns)})
    df = ensure_year(df)
    info["rows_after_parse"] = int(len(df))
    return df, info


def load_stage31c_candidates() -> Tuple[pd.DataFrame, Dict]:
    candidates_path = resolve(STAGE31C_CANDIDATE_PATH)
    audit_path = resolve(STAGE31C_AUDIT_PATH)
    info = {
        "candidate_path": str(candidates_path),
        "candidate_exists": candidates_path.exists(),
        "audit_path": str(audit_path),
        "audit_exists": audit_path.exists(),
        "loaded": False,
    }
    path = candidates_path if candidates_path.exists() and candidates_path.stat().st_size > 0 else audit_path
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(), info
    try:
        df = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        info["error"] = "EmptyDataError"
        return pd.DataFrame(), info
    info.update({"loaded": True, "used_path": str(path), "rows_raw": int(len(df)), "columns": list(df.columns)})

    # Normalize expected Stage31C names.
    rename = {}
    if "feature" in df.columns and "macro_feature" not in df.columns:
        rename["feature"] = "macro_feature"
    if "gate" in df.columns and "macro_gate" not in df.columns:
        rename["gate"] = "macro_gate"
    df = df.rename(columns=rename)

    required = {"scope_type", "scope_value", "macro_feature", "macro_gate", "overlay_name"}
    missing = sorted(required - set(df.columns))
    if missing:
        info["missing_required"] = missing
        return pd.DataFrame(), info

    if "rank_score" in df.columns:
        df["rank_score"] = pd.to_numeric(df["rank_score"], errors="coerce").fillna(-1e9)
        df = df.sort_values("rank_score", ascending=False)
    else:
        df["rank_score"] = 0.0

    # Prefer review/audit positives; keep rejected rows out unless explicitly requested.
    if "decision" in df.columns:
        mask = df["decision"].astype(str).str.contains("AUDIT_CANDIDATE|FRAGILE_POSITIVE|WEAK", regex=True, na=False)
        if mask.any():
            df = df[mask].copy()

    # Top unique definitions to avoid repeated family/candidate duplicates overwhelming runtime.
    key_cols = ["scope_type", "scope_value", "macro_feature", "macro_gate", "overlay_name"]
    df = df.drop_duplicates(subset=key_cols, keep="first").head(TOP_N).copy()
    info["rows_after_filter"] = int(len(df))
    return df, info


_GATE_RE = re.compile(r"_(le|ge)_q(\d{1,2})$")


def parse_gate(gate: str) -> Optional[Tuple[str, float]]:
    m = _GATE_RE.search(str(gate))
    if not m:
        return None
    direction = m.group(1)
    q = float(m.group(2)) / 100.0
    return direction, q


def apply_threshold(series: pd.Series, direction: str, threshold: float) -> pd.Series:
    vals = pd.to_numeric(series, errors="coerce")
    if direction == "le":
        return vals <= threshold
    if direction == "ge":
        return vals >= threshold
    return pd.Series(False, index=series.index)


@dataclass(frozen=True)
class OverlayCondition:
    col: str
    direction: str
    q: float


OVERLAYS: Dict[str, List[OverlayCondition]] = {
    "macro_only": [],
    "h1_atr_rank_le_q30": [OverlayCondition("h1_atr20_pct_rank_250", "le", 0.30)],
    "london_q60_prior_q25": [
        OverlayCondition("london_range", "ge", 0.60),
        OverlayCondition("prior_day_range", "ge", 0.25),
    ],
    "london_q40_prior_q30": [
        OverlayCondition("london_range", "ge", 0.40),
        OverlayCondition("prior_day_range", "ge", 0.30),
    ],
    "h1_atr_q30_and_london_q60_prior_q25": [
        OverlayCondition("h1_atr20_pct_rank_250", "le", 0.30),
        OverlayCondition("london_range", "ge", 0.60),
        OverlayCondition("prior_day_range", "ge", 0.25),
    ],
}


def scope_subset(df: pd.DataFrame, scope_type: str, scope_value: str) -> pd.DataFrame:
    if scope_type not in df.columns:
        return pd.DataFrame(columns=df.columns)
    return df[df[scope_type].astype(str) == str(scope_value)].copy()


def pf(values: Iterable[float]) -> float:
    arr = pd.to_numeric(pd.Series(values), errors="coerce").dropna().to_numpy(dtype=float)
    if arr.size == 0:
        return float("nan")
    gains = arr[arr > 0].sum()
    losses = -arr[arr < 0].sum()
    if losses <= 0:
        return float("inf") if gains > 0 else float("nan")
    return float(gains / losses)


def metrics(rows: pd.DataFrame, prefix: str = "") -> Dict[str, float]:
    if rows.empty:
        return {
            f"{prefix}events": 0,
            f"{prefix}pf_x4": float("nan"),
            f"{prefix}pf_x6": float("nan"),
            f"{prefix}total_x4": 0.0,
            f"{prefix}total_x6": 0.0,
            f"{prefix}win_rate_x4": float("nan"),
            f"{prefix}median_x4": float("nan"),
            f"{prefix}avg_x4": float("nan"),
        }
    x4 = pd.to_numeric(rows.get("net_x4", pd.Series([], dtype=float)), errors="coerce")
    x6 = pd.to_numeric(rows.get("net_x6", pd.Series([], dtype=float)), errors="coerce")
    return {
        f"{prefix}events": int(len(rows)),
        f"{prefix}pf_x4": pf(x4),
        f"{prefix}pf_x6": pf(x6),
        f"{prefix}total_x4": float(x4.sum(skipna=True)),
        f"{prefix}total_x6": float(x6.sum(skipna=True)),
        f"{prefix}win_rate_x4": float((x4 > 0).mean()) if len(x4) else float("nan"),
        f"{prefix}median_x4": float(x4.median(skipna=True)) if len(x4) else float("nan"),
        f"{prefix}avg_x4": float(x4.mean(skipna=True)) if len(x4) else float("nan"),
    }


def bootstrap_p05(rows: pd.DataFrame, col: str = "net_x4", n: int = BOOT_N, seed: int = RANDOM_SEED) -> float:
    vals = pd.to_numeric(rows.get(col, pd.Series([], dtype=float)), errors="coerce").dropna().to_numpy(dtype=float)
    if vals.size == 0:
        return float("nan")
    if vals.size == 1:
        return float(vals[0])
    rng = np.random.default_rng(seed)
    totals = np.empty(n, dtype=float)
    for i in range(n):
        totals[i] = rng.choice(vals, size=vals.size, replace=True).sum()
    return float(np.quantile(totals, 0.05))


def stress_metrics(rows: pd.DataFrame, stress_r: float) -> Dict[str, float]:
    if rows.empty or "net_x4" not in rows.columns:
        return {f"stress_{stress_r:.2f}_total_x4": float("nan"), f"stress_{stress_r:.2f}_pf_x4": float("nan")}
    stressed = rows.copy()
    stressed["net_x4"] = pd.to_numeric(stressed["net_x4"], errors="coerce") - stress_r
    return {
        f"stress_{stress_r:.2f}_total_x4": float(stressed["net_x4"].sum(skipna=True)),
        f"stress_{stress_r:.2f}_pf_x4": pf(stressed["net_x4"]),
    }


def year_stats(rows: pd.DataFrame) -> Dict[str, float]:
    if rows.empty:
        return {"years_tested": 0, "years_positive_x4": 0, "min_year_events": 0, "year_total_min": float("nan")}
    totals = rows.groupby("year")["net_x4"].agg(["count", "sum"]).reset_index()
    return {
        "years_tested": int(len(totals)),
        "years_positive_x4": int((totals["sum"] > 0).sum()),
        "min_year_events": int(totals["count"].min()) if len(totals) else 0,
        "year_total_min": float(totals["sum"].min()) if len(totals) else float("nan"),
    }


def dedupe_events(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return rows
    # Keep one row per event within a candidate definition. This reduces artifact duplication risk.
    if "event_key" in rows.columns:
        sort_cols = [c for c in ["_entry_ts", "event_key"] if c in rows.columns]
        rows = rows.sort_values(sort_cols).drop_duplicates(subset=["event_key"], keep="first")
    else:
        subset_cols = [c for c in ["entry_ts_norm", "candidate_name", "family", "net_x4", "net_x6"] if c in rows.columns]
        if subset_cols:
            rows = rows.drop_duplicates(subset=subset_cols, keep="first")
    return rows.copy()


def confirm_gate(base_scope: pd.DataFrame, macro_feature: str, macro_gate: str, overlay_name: str) -> Tuple[pd.DataFrame, List[Dict]]:
    parsed = parse_gate(macro_gate)
    if parsed is None or macro_feature not in base_scope.columns:
        return pd.DataFrame(columns=base_scope.columns), []
    macro_direction, macro_q = parsed
    overlay_conditions = OVERLAYS.get(str(overlay_name), OVERLAYS.get("macro_only", []))

    accepted_parts: List[pd.DataFrame] = []
    year_diag: List[Dict] = []
    years = sorted(int(y) for y in base_scope["year"].dropna().unique())
    for y in years:
        prior = base_scope[base_scope["year"] < y].copy()
        test = base_scope[base_scope["year"] == y].copy()
        if len(prior) < 30 or test.empty:
            continue
        prior_macro = pd.to_numeric(prior[macro_feature], errors="coerce").dropna()
        if prior_macro.empty:
            continue
        macro_threshold = float(prior_macro.quantile(macro_q))
        mask = apply_threshold(test[macro_feature], macro_direction, macro_threshold)
        thresholds = {f"{macro_feature}_{macro_direction}_q{int(macro_q*100)}": macro_threshold}

        for cond in overlay_conditions:
            if cond.col not in prior.columns or cond.col not in test.columns:
                mask &= False
                thresholds[f"missing_{cond.col}"] = float("nan")
                continue
            prior_vals = pd.to_numeric(prior[cond.col], errors="coerce").dropna()
            if prior_vals.empty:
                mask &= False
                thresholds[f"empty_{cond.col}"] = float("nan")
                continue
            thr = float(prior_vals.quantile(cond.q))
            thresholds[f"{cond.col}_{cond.direction}_q{int(cond.q*100)}"] = thr
            mask &= apply_threshold(test[cond.col], cond.direction, thr)

        accepted = test[mask].copy()
        accepted_parts.append(accepted)
        yd = {"year": int(y), "test_rows": int(len(test)), "kept_rows": int(len(accepted))}
        yd.update(thresholds)
        if not accepted.empty:
            yd.update(metrics(accepted))
        year_diag.append(yd)

    if not accepted_parts:
        return pd.DataFrame(columns=base_scope.columns), year_diag
    kept = pd.concat(accepted_parts, ignore_index=True)
    kept = dedupe_events(kept)
    return kept, year_diag


def decision_for(row: Dict) -> str:
    events = row.get("confirmed_events", 0) or 0
    years_tested = row.get("years_tested", 0) or 0
    years_pos = row.get("years_positive_x4", 0) or 0
    ratio = years_pos / years_tested if years_tested else 0.0
    if (
        events >= MIN_EVENTS
        and years_tested >= MIN_YEARS
        and safe_float(row.get("confirmed_pf_x4")) >= STRONG_PF_X4
        and safe_float(row.get("confirmed_total_x4")) >= STRONG_TOTAL_X4
        and safe_float(row.get("boot_p05_total_x4")) > STRONG_BOOT_P05
        and ratio >= STRONG_YEARS_POS_RATIO
        and safe_float(row.get("stress_0.20_total_x4")) > 0
    ):
        return "STAGE31D_HAS_CONFIRMED_EXOGENOUS_CANDIDATE_REVIEW_ONLY"
    if events >= 30 and safe_float(row.get("confirmed_total_x4")) > 0 and safe_float(row.get("boot_p05_total_x4")) > 0:
        return "STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY"
    return "STAGE31D_REJECT_CONFIRMATION"


def rank_score(row: Dict) -> float:
    total = safe_float(row.get("confirmed_total_x4"), 0.0)
    boot = safe_float(row.get("boot_p05_total_x4"), 0.0)
    pfv = safe_float(row.get("confirmed_pf_x4"), 0.0)
    events = safe_float(row.get("confirmed_events"), 0.0)
    years = safe_float(row.get("years_positive_x4"), 0.0)
    stress = safe_float(row.get("stress_0.20_total_x4"), 0.0)
    return float(total * 0.20 + boot * 0.25 + min(pfv, 25.0) * 5.0 + years * 8.0 + min(events, 150.0) * 0.10 + max(stress, -100.0) * 0.10)


def markdown_table(df: pd.DataFrame, max_rows: int = 30) -> str:
    if df.empty:
        return "_No rows._"
    small = df.head(max_rows).copy()
    try:
        return small.to_markdown(index=False)
    except Exception:
        cols = list(small.columns)
        lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
        for _, r in small.iterrows():
            vals = []
            for c in cols:
                v = r[c]
                if isinstance(v, float):
                    vals.append(f"{v:.6g}")
                else:
                    vals.append(str(v))
            lines.append("| " + " | ".join(vals) + " |")
        return "\n".join(lines)


def write_reports(report: Dict, results: pd.DataFrame, year_diag: pd.DataFrame) -> None:
    out_dir = resolve(REPORT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "stage31d_exogenous_candidate_confirmation.json"
    md_path = out_dir / "stage31d_exogenous_candidate_confirmation.md"
    csv_path = out_dir / "stage31d_confirmation_results.csv"
    review_path = out_dir / "stage31d_candidate_review.csv"
    yd_path = out_dir / "stage31d_year_diagnostics.csv"

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    results.to_csv(csv_path, index=False)
    review = results[results["decision"].astype(str).str.contains("CONFIRMED|FRAGILE", regex=True, na=False)].copy()
    review.to_csv(review_path, index=False)
    year_diag.to_csv(yd_path, index=False)

    md = []
    md.append("# Stage31D Exogenous Candidate Confirmation")
    md.append("")
    md.append(f"Generated UTC: `{report['generated_utc']}`")
    md.append("")
    md.append("## Decision")
    md.append("")
    md.append("```text")
    md.append(report["decision"])
    md.append("```")
    md.append("")
    md.append("## Scope guardrails")
    md.append("")
    md.append("- Research/shadow confirmation only.")
    md.append("- No EA change, no automatic trading, no paper/live/order authorization.")
    md.append("- Consumes Stage31A enriched dataset and Stage31C audit outputs only.")
    md.append("- Gate thresholds are recalibrated with expanding prior-year data only.")
    md.append("- Event-level deduplication is applied to reduce artifact duplication risk.")
    md.append("")
    md.append("## Inputs")
    md.append("")
    md.append("```json")
    md.append(json.dumps(report["inputs"], indent=2, default=str))
    md.append("```")
    md.append("")
    md.append("## Counts")
    md.append("")
    for k, v in report["counts"].items():
        md.append(f"- {k}: `{v}`")
    md.append("")
    md.append("## Candidate review")
    md.append("")
    review_cols = [
        "decision", "scope_type", "scope_value", "macro_feature", "macro_gate", "overlay_name",
        "confirmed_events", "confirmed_pf_x4", "confirmed_pf_x6", "confirmed_total_x4",
        "boot_p05_total_x4", "stress_0.20_total_x4", "years_positive_x4", "years_tested", "rank_score",
    ]
    existing = [c for c in review_cols if c in review.columns]
    md.append(markdown_table(review[existing] if existing else review, max_rows=40))
    md.append("")
    md.append("## Top diagnostics")
    md.append("")
    diag_cols = [c for c in review_cols if c in results.columns]
    md.append(markdown_table(results[diag_cols].head(40) if diag_cols else results.head(40), max_rows=40))
    md.append("")
    md.append("## Interpretation")
    md.append("")
    md.append("- A confirmed candidate is still review-only; it is not an execution authorization.")
    md.append("- The next step after a confirmed candidate is a dedicated forward-shadow tracker, not EA/paper/live promotion.")
    md.append("- If confirmation fails, the Stage31C positives should be treated as selection artifacts or overfit intersections.")
    md.append("")
    md.append("## Output files")
    md.append("")
    for p in [json_path, md_path, csv_path, review_path, yd_path]:
        md.append(f"- `{p.relative_to(ROOT) if p.is_relative_to(ROOT) else p}`")

    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")


def main() -> None:
    dataset_path = resolve(DATASET_PATH)
    data, data_info = load_dataset(dataset_path)
    cand, cand_info = load_stage31c_candidates()

    rows: List[Dict] = []
    yd_rows: List[Dict] = []

    if not data.empty and not cand.empty:
        for i, c in cand.iterrows():
            scope_type = str(c["scope_type"])
            scope_value = str(c["scope_value"])
            macro_feature = str(c["macro_feature"])
            macro_gate = str(c["macro_gate"])
            overlay_name = str(c.get("overlay_name", "macro_only"))
            base_scope = scope_subset(data, scope_type, scope_value)
            base_scope = dedupe_events(base_scope)
            kept, yd = confirm_gate(base_scope, macro_feature, macro_gate, overlay_name)
            row = {
                "scope_type": scope_type,
                "scope_value": scope_value,
                "macro_feature": macro_feature,
                "macro_gate": macro_gate,
                "overlay_name": overlay_name,
                "source_stage31c_rank_score": safe_float(c.get("rank_score"), 0.0),
                "source_stage31c_decision": str(c.get("decision", "")),
                "base_scope_events": int(len(base_scope)),
            }
            row.update(metrics(base_scope, prefix="base_"))
            confirmed_metrics = metrics(kept, prefix="confirmed_")
            row.update(confirmed_metrics)
            row.update(year_stats(kept))
            row["boot_p05_total_x4"] = bootstrap_p05(kept, "net_x4", seed=RANDOM_SEED + int(i)) if not kept.empty else float("nan")
            row["boot_p05_total_x6"] = bootstrap_p05(kept, "net_x6", seed=RANDOM_SEED + int(i) + 1000) if not kept.empty else float("nan")
            for s in STRESS_R:
                row.update(stress_metrics(kept, s))
            row["lift_pf_x4"] = safe_float(row.get("confirmed_pf_x4")) - safe_float(row.get("base_pf_x4"))
            row["lift_total_x4"] = safe_float(row.get("confirmed_total_x4"), 0.0) - safe_float(row.get("base_total_x4"), 0.0)
            row["decision"] = decision_for(row)
            row["rank_score"] = rank_score(row)
            rows.append(row)
            for ydr in yd:
                ydr.update({
                    "scope_type": scope_type,
                    "scope_value": scope_value,
                    "macro_feature": macro_feature,
                    "macro_gate": macro_gate,
                    "overlay_name": overlay_name,
                })
                yd_rows.append(ydr)

    results = pd.DataFrame(rows)
    if not results.empty:
        results = results.sort_values(["rank_score", "confirmed_total_x4"], ascending=False)
    year_diag = pd.DataFrame(yd_rows)

    confirmed_count = int(results["decision"].astype(str).str.contains("HAS_CONFIRMED", regex=False).sum()) if not results.empty else 0
    fragile_count = int(results["decision"].astype(str).str.contains("FRAGILE", regex=False).sum()) if not results.empty else 0
    if confirmed_count > 0:
        decision = "STAGE31D_HAS_CONFIRMED_EXOGENOUS_CANDIDATE_REVIEW_ONLY"
    elif fragile_count > 0:
        decision = "STAGE31D_HAS_FRAGILE_CONFIRMATION_DIAGNOSTIC_ONLY"
    else:
        decision = "STAGE31D_NO_CONFIRMED_EXOGENOUS_CANDIDATE"

    report = {
        "generated_utc": now_utc(),
        "decision": decision,
        "inputs": {"stage31a_dataset": data_info, "stage31c_candidates": cand_info},
        "params": {
            "top_n": TOP_N,
            "boot_n": BOOT_N,
            "min_events": MIN_EVENTS,
            "min_years": MIN_YEARS,
            "strong_pf_x4": STRONG_PF_X4,
            "strong_total_x4": STRONG_TOTAL_X4,
            "strong_boot_p05": STRONG_BOOT_P05,
            "strong_years_pos_ratio": STRONG_YEARS_POS_RATIO,
            "stress_r": STRESS_R,
        },
        "counts": {
            "dataset_rows": int(len(data)),
            "stage31c_gate_defs_loaded": int(len(cand)),
            "confirmation_results": int(len(results)),
            "confirmed_candidate_count": confirmed_count,
            "fragile_confirmation_count": fragile_count,
            "rejected_count": int((results["decision"] == "STAGE31D_REJECT_CONFIRMATION").sum()) if not results.empty else 0,
            "year_diagnostic_rows": int(len(year_diag)),
        },
    }
    write_reports(report, results, year_diag)
    print(f"decision={decision}")
    print(f"confirmed_candidate_count={confirmed_count}")
    print(f"fragile_confirmation_count={fragile_count}")
    print(f"report_dir={resolve(REPORT_DIR)}")


if __name__ == "__main__":
    main()
