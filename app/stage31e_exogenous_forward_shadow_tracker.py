"""Stage31E Exogenous Forward-Shadow Tracker.

Research/shadow only. This module consumes Stage31A enriched candidate rows and
Stage31D confirmed exogenous gate definitions, then applies the confirmed gates
with expanding prior-year thresholds to identify recent forward-shadow signals.

It does NOT place orders, modify EA files, authorize paper/live execution, or
fetch internet data.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

REPORT_DIR = Path("data/reports/stage31e_exogenous_forward_shadow_tracker")
STAGE31A_DATASET = Path("data/reports/stage31a_exogenous_feature_ingestion/stage31a_exogenous_ml_dataset.csv")
STAGE31D_REVIEW = Path("data/reports/stage31d_exogenous_candidate_confirmation/stage31d_candidate_review.csv")

DEFAULT_LOOKBACK_HOURS = int(os.environ.get("STAGE31E_LOOKBACK_HOURS", "336"))
DEFAULT_TOP_N = int(os.environ.get("STAGE31E_TOP_N", "8"))
MIN_PRIOR_ROWS = int(os.environ.get("STAGE31E_MIN_PRIOR_ROWS", "20"))
MIN_RECENT_SIGNAL_ROWS = int(os.environ.get("STAGE31E_MIN_RECENT_SIGNAL_ROWS", "1"))

CONFIRMED_DECISION = "STAGE31D_HAS_CONFIRMED_EXOGENOUS_CANDIDATE_REVIEW_ONLY"
FRAGILE_DECISION = "STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY"


@dataclass
class GateDef:
    scope_type: str
    scope_value: str
    macro_feature: str
    macro_gate: str
    macro_side: str
    macro_q: float
    overlay_name: str
    source_decision: str
    rank_score: float
    confirmed_events: int
    confirmed_pf_x4: float
    confirmed_total_x4: float
    boot_p05_total_x4: float
    years_positive_x4: int
    years_tested: int


def _now_utc() -> str:
    return pd.Timestamp.now(tz="UTC").isoformat()


def _ensure_report_dir() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)


def _to_float(value: Any, default: float = np.nan) -> float:
    try:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return default
        return float(value)
    except Exception:
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return default
        return int(float(value))
    except Exception:
        return default


def _parse_macro_gate(row: pd.Series) -> Tuple[str, str, float]:
    side = str(row.get("macro_side", "") or "").strip().lower()
    q_raw = row.get("macro_q", np.nan)
    q = _to_float(q_raw, np.nan)

    gate = str(row.get("macro_gate", "") or "")
    match = re.search(r"_(le|ge)_q(\d+(?:\.\d+)?)$", gate)
    if match:
        parsed_side = match.group(1)
        parsed_q = float(match.group(2)) / 100.0
        if side not in {"le", "ge"}:
            side = parsed_side
        if np.isnan(q):
            q = parsed_q

    if side not in {"le", "ge"}:
        # Conservative default; most confirmed Stage31D gates are low-rate/low-yield filters.
        side = "le"
    if np.isnan(q):
        q = 0.20
    if q > 1.0:
        q = q / 100.0
    q = min(max(q, 0.01), 0.99)
    return side, side, q


def _load_dataset(path: Path) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    info: Dict[str, Any] = {"path": str(path), "exists": path.exists(), "loaded": False}
    if not path.exists():
        return pd.DataFrame(), info
    try:
        df = pd.read_csv(path)
    except Exception as exc:
        info["error"] = f"{type(exc).__name__}: {exc}"
        return pd.DataFrame(), info

    info["loaded"] = True
    info["rows_raw"] = int(len(df))
    info["columns"] = list(df.columns)
    if "entry_ts_norm" not in df.columns:
        info["error"] = "missing entry_ts_norm"
        return pd.DataFrame(), info
    df = df.copy()
    df["entry_ts_norm"] = pd.to_datetime(df["entry_ts_norm"], utc=True, errors="coerce")
    before = len(df)
    df = df[df["entry_ts_norm"].notna()].copy()
    df["year"] = df["entry_ts_norm"].dt.year
    info["rows_after_time_parse"] = int(len(df))
    info["rows_dropped_bad_time"] = int(before - len(df))
    return df, info


def _load_gate_defs(path: Path, top_n: int = DEFAULT_TOP_N) -> Tuple[List[GateDef], Dict[str, Any]]:
    info: Dict[str, Any] = {"path": str(path), "exists": path.exists(), "loaded": False}
    if not path.exists():
        return [], info
    try:
        raw = pd.read_csv(path)
    except Exception as exc:
        info["error"] = f"{type(exc).__name__}: {exc}"
        return [], info

    info["loaded"] = True
    info["rows_raw"] = int(len(raw))
    info["columns"] = list(raw.columns)
    if "decision" not in raw.columns:
        info["error"] = "missing decision column"
        return [], info

    # Stage31E should track confirmed candidates first. Fragile confirmations remain diagnostic.
    confirmed = raw[raw["decision"].astype(str).eq(CONFIRMED_DECISION)].copy()
    if confirmed.empty:
        confirmed = raw[raw["decision"].astype(str).str.contains("CONFIRMED", na=False)].copy()

    # Prefer concrete candidate-level rows over family duplicates when both exist.
    confirmed["scope_priority"] = np.where(confirmed.get("scope_type", "").astype(str).eq("candidate_name"), 0, 1)
    sort_cols = ["scope_priority"]
    ascending = [True]
    if "rank_score" in confirmed.columns:
        sort_cols.append("rank_score")
        ascending.append(False)
    if "confirmed_total_x4" in confirmed.columns:
        sort_cols.append("confirmed_total_x4")
        ascending.append(False)

    confirmed = confirmed.sort_values(sort_cols, ascending=ascending).head(top_n)
    info["rows_confirmed"] = int(len(confirmed))

    defs: List[GateDef] = []
    for _, row in confirmed.iterrows():
        _, side, q = _parse_macro_gate(row)
        defs.append(
            GateDef(
                scope_type=str(row.get("scope_type", "")),
                scope_value=str(row.get("scope_value", "")),
                macro_feature=str(row.get("macro_feature", "")),
                macro_gate=str(row.get("macro_gate", "")),
                macro_side=side,
                macro_q=q,
                overlay_name=str(row.get("overlay_name", "macro_only")),
                source_decision=str(row.get("decision", "")),
                rank_score=_to_float(row.get("rank_score"), 0.0),
                confirmed_events=_to_int(row.get("confirmed_events"), 0),
                confirmed_pf_x4=_to_float(row.get("confirmed_pf_x4"), np.nan),
                confirmed_total_x4=_to_float(row.get("confirmed_total_x4"), np.nan),
                boot_p05_total_x4=_to_float(row.get("boot_p05_total_x4"), np.nan),
                years_positive_x4=_to_int(row.get("years_positive_x4"), 0),
                years_tested=_to_int(row.get("years_tested"), 0),
            )
        )
    return defs, info


def _scope_mask(df: pd.DataFrame, gd: GateDef) -> pd.Series:
    if gd.scope_type and gd.scope_type in df.columns:
        return df[gd.scope_type].astype(str).eq(str(gd.scope_value))
    if gd.scope_type == "candidate_name" and "candidate_name" in df.columns:
        return df["candidate_name"].astype(str).eq(str(gd.scope_value))
    if gd.scope_type == "family" and "family" in df.columns:
        return df["family"].astype(str).eq(str(gd.scope_value))
    return pd.Series(False, index=df.index)


def _threshold(prior: pd.Series, q: float) -> Optional[float]:
    prior = pd.to_numeric(prior, errors="coerce").dropna()
    if len(prior) < MIN_PRIOR_ROWS:
        return None
    try:
        return float(prior.quantile(q))
    except Exception:
        return None


def _apply_single_expanding_gate(
    scope_df: pd.DataFrame,
    feature: str,
    side: str,
    q: float,
    years: Iterable[int],
) -> Tuple[pd.Series, Dict[int, Optional[float]]]:
    out = pd.Series(False, index=scope_df.index)
    thresholds: Dict[int, Optional[float]] = {}
    if feature not in scope_df.columns:
        return out, thresholds
    vals = pd.to_numeric(scope_df[feature], errors="coerce")
    for year in years:
        prior_mask = scope_df["year"] < year
        current_mask = scope_df["year"].eq(year)
        thr = _threshold(vals[prior_mask], q)
        thresholds[int(year)] = thr
        if thr is None:
            continue
        if side == "le":
            out.loc[current_mask] = vals[current_mask] <= thr
        else:
            out.loc[current_mask] = vals[current_mask] >= thr
    return out, thresholds


def _overlay_specs(name: str) -> List[Tuple[str, str, float]]:
    name = str(name or "macro_only")
    if name == "macro_only":
        return []
    if name == "h1_atr_rank_le_q30":
        return [("h1_atr20_pct_rank_250", "le", 0.30)]
    if name == "london_q40_prior_q30":
        return [("london_range", "ge", 0.40), ("prior_day_range", "ge", 0.30)]
    if name == "london_q60_prior_q25":
        return [("london_range", "ge", 0.60), ("prior_day_range", "ge", 0.25)]
    if name == "h1_atr_q30_and_london_q60_prior_q25":
        return [
            ("h1_atr20_pct_rank_250", "le", 0.30),
            ("london_range", "ge", 0.60),
            ("prior_day_range", "ge", 0.25),
        ]
    return []


def _event_dedup(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    if "event_key" in df.columns:
        return df.sort_values("entry_ts_norm").drop_duplicates("event_key", keep="last")
    subset = [c for c in ["entry_ts_norm", "candidate_name", "family", "macro_gate"] if c in df.columns]
    if subset:
        return df.sort_values("entry_ts_norm").drop_duplicates(subset, keep="last")
    return df


def _summarise_returns(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {
            "events": 0,
            "total_x4": 0.0,
            "total_x6": 0.0,
            "pf_x4": np.nan,
            "pf_x6": np.nan,
            "win_rate_x4": np.nan,
            "median_x4": np.nan,
        }
    x4 = pd.to_numeric(df.get("net_x4"), errors="coerce").dropna()
    x6 = pd.to_numeric(df.get("net_x6"), errors="coerce").dropna()

    def pf(s: pd.Series) -> float:
        gains = s[s > 0].sum()
        losses = -s[s < 0].sum()
        if losses <= 0:
            return float("inf") if gains > 0 else np.nan
        return float(gains / losses)

    return {
        "events": int(len(df)),
        "total_x4": float(x4.sum()) if len(x4) else 0.0,
        "total_x6": float(x6.sum()) if len(x6) else 0.0,
        "pf_x4": pf(x4),
        "pf_x6": pf(x6),
        "win_rate_x4": float((x4 > 0).mean()) if len(x4) else np.nan,
        "median_x4": float(x4.median()) if len(x4) else np.nan,
    }


def evaluate_gate(df: pd.DataFrame, gd: GateDef) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    scope = df[_scope_mask(df, gd)].copy()
    result: Dict[str, Any] = asdict(gd)
    result["scope_rows"] = int(len(scope))
    if scope.empty or gd.macro_feature not in scope.columns:
        result["status"] = "missing_scope_or_feature"
        return pd.DataFrame(), result

    years = sorted(y for y in scope["year"].dropna().unique().tolist() if pd.notna(y))
    macro_mask, macro_thresholds = _apply_single_expanding_gate(scope, gd.macro_feature, gd.macro_side, gd.macro_q, years)
    combined = macro_mask.copy()
    overlay_thresholds: Dict[str, Dict[int, Optional[float]]] = {}
    for feature, side, q in _overlay_specs(gd.overlay_name):
        omask, othr = _apply_single_expanding_gate(scope, feature, side, q, years)
        combined = combined & omask
        overlay_thresholds[f"{feature}_{side}_q{int(round(q*100))}"] = othr

    kept = scope[combined].copy()
    kept = _event_dedup(kept)
    result.update({f"confirmed_recalc_{k}": v for k, v in _summarise_returns(kept).items()})
    result["macro_thresholds_by_year"] = json.dumps(macro_thresholds, sort_keys=True, default=str)
    result["overlay_thresholds_by_year"] = json.dumps(overlay_thresholds, sort_keys=True, default=str)
    result["status"] = "evaluated"
    kept["stage31e_gate_key"] = f"{gd.scope_type}:{gd.scope_value}|{gd.macro_gate}|{gd.overlay_name}"
    kept["stage31e_source_decision"] = gd.source_decision
    return kept, result


def _format_num(x: Any, nd: int = 4) -> str:
    try:
        if x is None or pd.isna(x):
            return "nan"
        if x == float("inf"):
            return "inf"
        return f"{float(x):.{nd}f}"
    except Exception:
        return str(x)


def _simple_markdown_table(df: pd.DataFrame, max_rows: int = 30) -> str:
    if df.empty:
        return "_No rows._"
    view = df.head(max_rows).copy()
    cols = list(view.columns)
    lines = []
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("| " + " | ".join([":---" for _ in cols]) + " |")
    for _, row in view.iterrows():
        vals = []
        for c in cols:
            v = row[c]
            if isinstance(v, float):
                vals.append(_format_num(v))
            else:
                vals.append(str(v).replace("|", "\\|"))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def write_report(report: Dict[str, Any], summary_df: pd.DataFrame, recent_df: pd.DataFrame) -> None:
    _ensure_report_dir()
    md_path = REPORT_DIR / "stage31e_exogenous_forward_shadow_tracker.md"
    json_path = REPORT_DIR / "stage31e_exogenous_forward_shadow_tracker.json"
    summary_path = REPORT_DIR / "stage31e_tracker_summary.csv"
    recent_path = REPORT_DIR / "stage31e_recent_signals.csv"

    summary_df.to_csv(summary_path, index=False)
    recent_df.to_csv(recent_path, index=False)
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    md: List[str] = []
    md.append("# Stage31E Exogenous Forward-Shadow Tracker")
    md.append("")
    md.append(f"Generated UTC: `{report.get('generated_utc')}`")
    md.append("")
    md.append("## Decision")
    md.append("")
    md.append("```text")
    md.append(str(report.get("decision")))
    md.append("```")
    md.append("")
    md.append("## Scope guardrails")
    md.append("")
    md.append("- Research/shadow tracker only.")
    md.append("- No EA change, no automatic trading, no paper/live/order authorization.")
    md.append("- Consumes Stage31A enriched dataset and Stage31D confirmed candidates only.")
    md.append("- Gate thresholds are applied with expanding prior-year calibration only.")
    md.append("- Recent signals are review-only observations, not executable instructions.")
    md.append("")
    md.append("## Counts")
    md.append("")
    for key in [
        "dataset_rows", "gate_defs_loaded", "gate_defs_tracked", "tracker_results", "recent_signal_rows", "recent_signal_gate_count", "lookback_hours",
    ]:
        md.append(f"- {key}: `{report.get(key)}`")
    md.append("")
    md.append("## Tracker summary")
    md.append("")
    md.append(_simple_markdown_table(summary_df[[
        "tracker_decision", "scope_type", "scope_value", "macro_gate", "overlay_name",
        "confirmed_recalc_events", "confirmed_recalc_pf_x4", "confirmed_recalc_total_x4",
        "recent_events", "recent_last_entry_ts", "rank_score"
    ]] if not summary_df.empty else summary_df))
    md.append("")
    md.append("## Recent signal sample")
    md.append("")
    cols = [c for c in [
        "entry_ts_norm", "event_key", "candidate_name", "family", "net_x4", "net_x6",
        "stage31e_gate_key", "real_yield_rank250", "real_yield_z60", "us10y_rank250", "dxy_ret_5",
        "london_range", "prior_day_range", "h1_atr20_pct_rank_250"
    ] if c in recent_df.columns]
    md.append(_simple_markdown_table(recent_df[cols].sort_values("entry_ts_norm", ascending=False) if cols else recent_df))
    md.append("")
    md.append("## Interpretation")
    md.append("")
    md.append("- A recent signal only means a historically confirmed research gate matched a recent candidate-pool row.")
    md.append("- This stage cannot authorize EA, paper/live, or orders.")
    md.append("- The next promotion step, if warranted, is sustained forward-shadow observation and active-suite integration, not live execution.")
    md.append("")
    md.append("## Output files")
    md.append("")
    for p in [json_path, md_path, summary_path, recent_path]:
        md.append(f"- `{p}`")
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")


def main() -> None:
    _ensure_report_dir()
    lookback_hours = DEFAULT_LOOKBACK_HOURS
    top_n = DEFAULT_TOP_N

    df, dataset_info = _load_dataset(STAGE31A_DATASET)
    gate_defs, gate_info = _load_gate_defs(STAGE31D_REVIEW, top_n=top_n)

    report: Dict[str, Any] = {
        "generated_utc": _now_utc(),
        "stage31a_dataset": dataset_info,
        "stage31d_gate_defs": gate_info,
        "lookback_hours": lookback_hours,
        "top_n": top_n,
        "dataset_rows": int(len(df)),
        "gate_defs_loaded": int(len(gate_defs)),
    }

    if df.empty:
        report.update({
            "decision": "STAGE31E_DATASET_MISSING_RESEARCH_ONLY",
            "gate_defs_tracked": 0,
            "tracker_results": 0,
            "recent_signal_rows": 0,
            "recent_signal_gate_count": 0,
        })
        write_report(report, pd.DataFrame(), pd.DataFrame())
        return

    if not gate_defs:
        report.update({
            "decision": "STAGE31E_NO_CONFIRMED_CANDIDATE_RESEARCH_ONLY",
            "gate_defs_tracked": 0,
            "tracker_results": 0,
            "recent_signal_rows": 0,
            "recent_signal_gate_count": 0,
        })
        write_report(report, pd.DataFrame(), pd.DataFrame())
        return

    max_ts = df["entry_ts_norm"].max()
    cutoff = max_ts - pd.Timedelta(hours=lookback_hours)

    rows: List[Dict[str, Any]] = []
    recent_parts: List[pd.DataFrame] = []
    for gd in gate_defs:
        kept, res = evaluate_gate(df, gd)
        recent = kept[kept["entry_ts_norm"] >= cutoff].copy() if not kept.empty else kept
        recent_events = int(len(recent))
        res["recent_events"] = recent_events
        res["recent_last_entry_ts"] = recent["entry_ts_norm"].max().isoformat() if recent_events else ""
        if recent_events >= MIN_RECENT_SIGNAL_ROWS:
            res["tracker_decision"] = "STAGE31E_FORWARD_SHADOW_ACTIVE_SIGNAL_REVIEW_ONLY"
            recent_parts.append(recent)
        else:
            res["tracker_decision"] = "STAGE31E_NO_RECENT_FORWARD_SHADOW_SIGNAL_RESEARCH_ONLY"
        rows.append(res)

    summary = pd.DataFrame(rows)
    recent_df = pd.concat(recent_parts, ignore_index=True) if recent_parts else pd.DataFrame()
    if not recent_df.empty:
        recent_df = _event_dedup(recent_df)

    active = summary[summary.get("tracker_decision", pd.Series([], dtype=str)).astype(str).eq("STAGE31E_FORWARD_SHADOW_ACTIVE_SIGNAL_REVIEW_ONLY")]
    report.update({
        "gate_defs_tracked": int(len(gate_defs)),
        "tracker_results": int(len(summary)),
        "recent_signal_rows": int(len(recent_df)),
        "recent_signal_gate_count": int(len(active)),
        "latest_dataset_ts": max_ts.isoformat() if pd.notna(max_ts) else "",
        "recent_cutoff_ts": cutoff.isoformat() if pd.notna(cutoff) else "",
    })

    if len(active) > 0:
        report["decision"] = "STAGE31E_FORWARD_SHADOW_ACTIVE_SIGNAL_REVIEW_ONLY"
    else:
        report["decision"] = "STAGE31E_NO_RECENT_FORWARD_SHADOW_SIGNAL_RESEARCH_ONLY"

    write_report(report, summary, recent_df)


if __name__ == "__main__":
    main()
