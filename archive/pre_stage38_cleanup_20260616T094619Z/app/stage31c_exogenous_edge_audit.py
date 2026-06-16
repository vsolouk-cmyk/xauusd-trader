"""Stage31C Exogenous Fragile-Edge Audit.

Research/shadow only. No execution, no EA, no orders.

Purpose:
- Consume Stage31A enriched candidate-pool dataset.
- Consume Stage31B exogenous gate results when available.
- Re-audit weak/fragile exogenous gates using expanding prior-year thresholds.
- Test a small, pre-defined set of forward-safe combo overlays with prior/london/H1 ATR gates.

This stage deliberately avoids direct ML/model fitting. It is a robustness audit for
candidate exogenous gates, not a strategy builder.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd

ROOT = Path(".")
STAGE31A_DATASET = ROOT / "data/reports/stage31a_exogenous_feature_ingestion/stage31a_exogenous_ml_dataset.csv"
STAGE31B_RESULTS = ROOT / "data/reports/stage31b_exogenous_gate_validation/stage31b_gate_results.csv"
OUT_DIR = ROOT / "data/reports/stage31c_exogenous_edge_audit"

EXOG_PREFIXES = ("dxy", "us10y", "real_yield", "vix", "spx", "oil")
NET_COLS = ("net_x1", "net_x4", "net_x6")
SCOPE_COLS = ("candidate_name", "family", "source_stage")

# Known non-exogenous forward-safe overlays from earlier validated research.
# These are not execution rules here; they are diagnostic intersections only.
OVERLAY_DEFS = [
    {"overlay_name": "macro_only", "features": []},
    {"overlay_name": "h1_atr_rank_le_q30", "features": [("h1_atr20_pct_rank_250", "le", 0.30)]},
    {"overlay_name": "london_q60_prior_q25", "features": [("london_range", "ge", 0.60), ("prior_day_range", "ge", 0.25)]},
    {"overlay_name": "london_q40_prior_q30", "features": [("london_range", "ge", 0.40), ("prior_day_range", "ge", 0.30)]},
    {"overlay_name": "h1_atr_q30_and_london_q60_prior_q25", "features": [("h1_atr20_pct_rank_250", "le", 0.30), ("london_range", "ge", 0.60), ("prior_day_range", "ge", 0.25)]},
]


@dataclass
class AuditConfig:
    min_scope_rows: int = 80
    min_calib_events: int = 25
    min_year_test_rows: int = 5
    min_wf_events: int = 30
    top_stage31b_rows: int = 80
    bootstrap_iters: int = 400
    random_seed: int = 311031


def utc_now_iso() -> str:
    return pd.Timestamp.now(tz="UTC").isoformat()


def ensure_out_dir() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)


def safe_read_csv(path: Path) -> tuple[pd.DataFrame, dict]:
    info = {"path": str(path), "exists": path.exists(), "loaded": False, "rows": 0, "columns": []}
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(), info
    try:
        df = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(), info | {"error": "EmptyDataError"}
    except Exception as exc:  # noqa: BLE001
        return pd.DataFrame(), info | {"error": repr(exc)}
    info.update({"loaded": True, "rows": int(len(df)), "columns": list(map(str, df.columns))})
    return df, info


def normalize_dataset(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    if "entry_ts_norm" not in out.columns:
        for col in ("entry_time", "entry_ts", "timestamp", "datetime", "time", "date"):
            if col in out.columns:
                out["entry_ts_norm"] = out[col]
                break
    out["entry_ts_norm"] = pd.to_datetime(out.get("entry_ts_norm"), utc=True, errors="coerce")
    out = out.dropna(subset=["entry_ts_norm"]).copy()
    out["year"] = pd.to_numeric(out.get("year", out["entry_ts_norm"].dt.year), errors="coerce").fillna(out["entry_ts_norm"].dt.year).astype(int)
    for col in NET_COLS:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    for col in out.columns:
        if col.endswith(("_value", "_ret_1", "_ret_5", "_chg_1", "_chg_5", "_z60", "_rank250", "_age_hours")) or col in {
            "prior_day_range",
            "asia_range",
            "asia_eff",
            "london_range",
            "london_eff",
            "h1_range",
            "h1_atr20",
            "h1_atr20_pct_rank_250",
        }:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def parse_gate(gate: str, feature: str | None = None) -> Optional[tuple[str, str, float]]:
    """Parse gate names like dxy_chg_1_ge_q80 into (feature, side, quantile)."""
    if not isinstance(gate, str):
        return None
    m = re.match(r"^(?P<feature>.+)_(?P<side>ge|le)_q(?P<q>\d{1,2})$", gate.strip())
    if not m:
        return None
    parsed_feature = m.group("feature")
    side = m.group("side")
    q = int(m.group("q")) / 100.0
    if feature and parsed_feature != feature:
        # Prefer the explicit feature column if the gate can be matched by suffix.
        parsed_feature = feature
    if not (0.0 < q < 1.0):
        return None
    return parsed_feature, side, q


def exog_feature_columns(df: pd.DataFrame) -> list[str]:
    cols: list[str] = []
    for col in df.columns:
        if any(col.startswith(f"{p}_") for p in EXOG_PREFIXES):
            if col.endswith("_asof_ts"):
                continue
            if pd.api.types.is_numeric_dtype(df[col]):
                cols.append(col)
    return sorted(cols)


def make_default_gate_defs(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for feat in exog_feature_columns(df):
        for side, qs in (("le", (0.20, 0.30)), ("ge", (0.70, 0.80))):
            for q in qs:
                rows.append(
                    {
                        "source": "default_grid",
                        "scope_type": "ALL",
                        "scope_value": "ALL",
                        "feature": feat,
                        "gate": f"{feat}_{side}_q{int(q * 100)}",
                        "side": side,
                        "q": q,
                        "stage31b_rank_score": np.nan,
                    }
                )
    return pd.DataFrame(rows)


def build_gate_defs(df: pd.DataFrame, stage31b: pd.DataFrame, cfg: AuditConfig) -> pd.DataFrame:
    default_defs = make_default_gate_defs(df)
    if stage31b.empty:
        return default_defs

    b = stage31b.copy()
    for col in ("wf_events", "wf_pf_x4", "wf_total_x4", "rank_score"):
        if col in b.columns:
            b[col] = pd.to_numeric(b[col], errors="coerce")
    if "feature" not in b.columns or "gate" not in b.columns:
        return default_defs

    masks = []
    if "decision" in b.columns:
        masks.append(b["decision"].astype(str).str.contains("WEAK|REJECT", case=False, na=False))
    if "wf_total_x4" in b.columns:
        masks.append(b["wf_total_x4"].fillna(-np.inf) > -25)
    if "wf_pf_x4" in b.columns:
        masks.append(b["wf_pf_x4"].fillna(-np.inf) >= 0.75)
    if "rank_score" in b.columns:
        masks.append(b["rank_score"].fillna(-np.inf) >= b["rank_score"].quantile(0.80))
    if masks:
        mask = masks[0]
        for m in masks[1:]:
            mask = mask | m
        b = b.loc[mask].copy()

    if "rank_score" in b.columns:
        b = b.sort_values("rank_score", ascending=False)
    b = b.head(cfg.top_stage31b_rows).copy()

    rows = []
    for _, r in b.iterrows():
        feat = str(r.get("feature", ""))
        gate = str(r.get("gate", ""))
        parsed = parse_gate(gate, feat)
        if parsed is None:
            continue
        f, side, q = parsed
        if f not in df.columns:
            continue
        if not any(f.startswith(p + "_") for p in EXOG_PREFIXES):
            continue
        st = str(r.get("scope_type", "ALL")) if pd.notna(r.get("scope_type", "ALL")) else "ALL"
        sv = str(r.get("scope_value", "ALL")) if pd.notna(r.get("scope_value", "ALL")) else "ALL"
        if st not in {"ALL", "candidate_name", "family", "source_stage"}:
            st, sv = "ALL", "ALL"
        rows.append(
            {
                "source": "stage31b_top_diagnostic",
                "scope_type": st,
                "scope_value": sv,
                "feature": f,
                "gate": gate,
                "side": side,
                "q": q,
                "stage31b_decision": r.get("decision", ""),
                "stage31b_wf_events": r.get("wf_events", np.nan),
                "stage31b_wf_pf_x4": r.get("wf_pf_x4", np.nan),
                "stage31b_wf_total_x4": r.get("wf_total_x4", np.nan),
                "stage31b_rank_score": r.get("rank_score", np.nan),
            }
        )
    if not rows:
        return default_defs
    combined = pd.concat([pd.DataFrame(rows), default_defs], ignore_index=True)
    combined = combined.drop_duplicates(subset=["scope_type", "scope_value", "feature", "side", "q"], keep="first")
    return combined.reset_index(drop=True)


def apply_scope(df: pd.DataFrame, scope_type: str, scope_value: str) -> pd.DataFrame:
    if scope_type == "ALL" or scope_value == "ALL" or scope_type not in df.columns:
        return df.copy()
    return df.loc[df[scope_type].astype(str) == str(scope_value)].copy()


def apply_threshold(df: pd.DataFrame, feature: str, side: str, threshold: float) -> pd.Series:
    values = pd.to_numeric(df[feature], errors="coerce")
    if side == "le":
        return values <= threshold
    return values >= threshold


def pf(series: pd.Series) -> float:
    vals = pd.to_numeric(series, errors="coerce").dropna().to_numpy(dtype=float)
    if vals.size == 0:
        return float("nan")
    pos = vals[vals > 0].sum()
    neg = -vals[vals < 0].sum()
    if neg <= 1e-12:
        return float("inf") if pos > 0 else float("nan")
    return float(pos / neg)


def metrics(rows: pd.DataFrame, rng: np.random.Generator, cfg: AuditConfig) -> dict:
    out = {"events": int(len(rows))}
    if rows.empty:
        for col in NET_COLS:
            out[f"pf_{col[-2:]}"] = float("nan")
            out[f"total_{col[-2:]}"] = 0.0
        out.update({"win_rate_x4": float("nan"), "median_x4": float("nan"), "boot_p05_total_x4": float("nan"), "years_positive_x4": 0, "years_tested": 0})
        return out
    for col in NET_COLS:
        label = col.replace("net_", "")
        if col in rows.columns:
            out[f"pf_{label}"] = pf(rows[col])
            out[f"total_{label}"] = float(pd.to_numeric(rows[col], errors="coerce").fillna(0.0).sum())
        else:
            out[f"pf_{label}"] = float("nan")
            out[f"total_{label}"] = float("nan")
    x4 = pd.to_numeric(rows.get("net_x4", pd.Series(dtype=float)), errors="coerce").dropna().to_numpy(dtype=float)
    out["win_rate_x4"] = float((x4 > 0).mean()) if x4.size else float("nan")
    out["median_x4"] = float(np.median(x4)) if x4.size else float("nan")
    if x4.size >= 10:
        boot = np.array([rng.choice(x4, size=x4.size, replace=True).sum() for _ in range(cfg.bootstrap_iters)], dtype=float)
        out["boot_p05_total_x4"] = float(np.quantile(boot, 0.05))
    else:
        out["boot_p05_total_x4"] = float("nan")
    by_year = rows.assign(_net_x4=pd.to_numeric(rows.get("net_x4"), errors="coerce")).groupby("year")['_net_x4'].sum()
    out["years_positive_x4"] = int((by_year > 0).sum())
    out["years_tested"] = int(by_year.shape[0])
    return out


def expanding_oos_filter(
    scoped: pd.DataFrame,
    gate_feature: str,
    side: str,
    q: float,
    overlay_features: list[tuple[str, str, float]],
    cfg: AuditConfig,
) -> tuple[pd.DataFrame, list[dict]]:
    kept_parts = []
    year_rows = []
    scoped = scoped.dropna(subset=[gate_feature, "year", "net_x4"]).copy()
    years = sorted(int(y) for y in scoped["year"].dropna().unique())
    for y in years:
        train = scoped.loc[scoped["year"] < y].copy()
        test = scoped.loc[scoped["year"] == y].copy()
        if len(train) < cfg.min_calib_events or len(test) < cfg.min_year_test_rows:
            year_rows.append({"year": y, "train_rows": int(len(train)), "test_rows": int(len(test)), "kept_rows": 0, "status": "insufficient_calibration_or_test"})
            continue
        try:
            threshold = float(pd.to_numeric(train[gate_feature], errors="coerce").quantile(q))
        except Exception:  # noqa: BLE001
            year_rows.append({"year": y, "train_rows": int(len(train)), "test_rows": int(len(test)), "kept_rows": 0, "status": "bad_macro_threshold"})
            continue
        mask = apply_threshold(test, gate_feature, side, threshold)
        overlay_thresholds = []
        for feat, oside, oq in overlay_features:
            if feat not in train.columns or feat not in test.columns:
                mask = mask & False
                overlay_thresholds.append({"feature": feat, "status": "missing"})
                continue
            thr = float(pd.to_numeric(train[feat], errors="coerce").quantile(oq))
            mask = mask & apply_threshold(test, feat, oside, thr)
            overlay_thresholds.append({"feature": feat, "side": oside, "q": oq, "threshold": thr})
        kept = test.loc[mask].copy()
        if not kept.empty:
            kept_parts.append(kept)
        year_rows.append(
            {
                "year": y,
                "train_rows": int(len(train)),
                "test_rows": int(len(test)),
                "kept_rows": int(len(kept)),
                "macro_threshold": threshold,
                "overlay_thresholds_json": json.dumps(overlay_thresholds, ensure_ascii=False),
                "status": "ok",
            }
        )
    if kept_parts:
        return pd.concat(kept_parts, ignore_index=True), year_rows
    return pd.DataFrame(columns=scoped.columns), year_rows


def classify(row: dict, cfg: AuditConfig) -> str:
    events = row.get("wf_events", 0)
    pf_x4 = row.get("wf_pf_x4", float("nan"))
    pf_x6 = row.get("wf_pf_x6", float("nan"))
    total = row.get("wf_total_x4", 0.0)
    boot = row.get("boot_p05_total_x4", float("nan"))
    years_pos = row.get("years_positive_x4", 0)
    years_tested = row.get("years_tested", 0)
    if events >= cfg.min_wf_events and pf_x4 >= 1.25 and pf_x6 >= 0.80 and total > 0 and boot > 0 and years_pos >= max(2, min(3, years_tested)):
        return "STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY"
    if events >= cfg.min_wf_events and pf_x4 >= 1.0 and total > 0:
        return "STAGE31C_FRAGILE_POSITIVE_DIAGNOSTIC_ONLY"
    if events >= cfg.min_wf_events and pf_x4 >= 0.85 and total > -25:
        return "STAGE31C_WEAK_WATCHLIST_ONLY"
    return "STAGE31C_REJECT_NO_ROBUST_EDGE"


def audit(df: pd.DataFrame, gate_defs: pd.DataFrame, cfg: AuditConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(cfg.random_seed)
    result_rows = []
    year_diag_rows = []
    for _, gd in gate_defs.iterrows():
        scope_type = str(gd.get("scope_type", "ALL"))
        scope_value = str(gd.get("scope_value", "ALL"))
        feature = str(gd.get("feature"))
        side = str(gd.get("side"))
        q = float(gd.get("q"))
        if feature not in df.columns or side not in {"ge", "le"}:
            continue
        scoped = apply_scope(df, scope_type, scope_value)
        if len(scoped) < cfg.min_scope_rows:
            continue
        for overlay in OVERLAY_DEFS:
            missing = [feat for feat, _, _ in overlay["features"] if feat not in scoped.columns]
            if missing:
                continue
            kept, year_diag = expanding_oos_filter(scoped, feature, side, q, overlay["features"], cfg)
            m = metrics(kept, rng, cfg)
            row = {
                "source": gd.get("source", "unknown"),
                "scope_type": scope_type,
                "scope_value": scope_value,
                "macro_feature": feature,
                "macro_gate": gd.get("gate", f"{feature}_{side}_q{int(q*100)}"),
                "macro_side": side,
                "macro_q": q,
                "overlay_name": overlay["overlay_name"],
                "overlay_features_json": json.dumps(overlay["features"], ensure_ascii=False),
                "scope_rows": int(len(scoped)),
                "stage31b_decision": gd.get("stage31b_decision", ""),
                "stage31b_wf_pf_x4": gd.get("stage31b_wf_pf_x4", np.nan),
                "stage31b_wf_total_x4": gd.get("stage31b_wf_total_x4", np.nan),
            }
            row.update(
                {
                    "wf_events": m["events"],
                    "wf_pf_x1": m.get("pf_x1"),
                    "wf_pf_x4": m.get("pf_x4"),
                    "wf_pf_x6": m.get("pf_x6"),
                    "wf_total_x1": m.get("total_x1"),
                    "wf_total_x4": m.get("total_x4"),
                    "wf_total_x6": m.get("total_x6"),
                    "win_rate_x4": m.get("win_rate_x4"),
                    "median_x4": m.get("median_x4"),
                    "boot_p05_total_x4": m.get("boot_p05_total_x4"),
                    "years_positive_x4": m.get("years_positive_x4"),
                    "years_tested": m.get("years_tested"),
                }
            )
            row["decision"] = classify(row, cfg)
            row["rank_score"] = score_row(row)
            result_rows.append(row)
            for yd in year_diag:
                yr = {
                    "scope_type": scope_type,
                    "scope_value": scope_value,
                    "macro_feature": feature,
                    "macro_gate": row["macro_gate"],
                    "overlay_name": overlay["overlay_name"],
                }
                yr.update(yd)
                year_diag_rows.append(yr)
    results = pd.DataFrame(result_rows)
    if not results.empty:
        results = results.sort_values(["decision", "rank_score"], ascending=[True, False]).reset_index(drop=True)
    return results, pd.DataFrame(year_diag_rows)


def finite(v: object, default: float = 0.0) -> float:
    try:
        x = float(v)
        if math.isfinite(x):
            return x
    except Exception:  # noqa: BLE001
        pass
    return default


def score_row(row: dict) -> float:
    pf4 = min(finite(row.get("wf_pf_x4")), 5.0)
    pf6 = min(finite(row.get("wf_pf_x6")), 5.0)
    total = finite(row.get("wf_total_x4"))
    boot = finite(row.get("boot_p05_total_x4"))
    events = finite(row.get("wf_events"))
    years_pos = finite(row.get("years_positive_x4"))
    return float((pf4 * 10.0) + (pf6 * 4.0) + (total / 10.0) + (boot / 20.0) + min(events, 100.0) / 10.0 + years_pos * 2.0)


def md_table(df: pd.DataFrame, max_rows: int = 30) -> str:
    if df.empty:
        return "No rows."
    d = df.head(max_rows).copy()
    try:
        return d.to_markdown(index=False)
    except Exception:  # noqa: BLE001
        # Fallback without tabulate.
        cols = list(d.columns)
        rows = [[str(x) for x in row] for row in d.astype(object).values.tolist()]
        widths = [max(len(str(c)), *(len(r[i]) for r in rows)) for i, c in enumerate(cols)]
        header = "| " + " | ".join(str(c).ljust(widths[i]) for i, c in enumerate(cols)) + " |"
        sep = "| " + " | ".join("-" * widths[i] for i in range(len(cols))) + " |"
        body = ["| " + " | ".join(r[i].ljust(widths[i]) for i in range(len(cols))) + " |" for r in rows]
        return "\n".join([header, sep, *body])


def write_outputs(report: dict, results: pd.DataFrame, years: pd.DataFrame) -> None:
    ensure_out_dir()
    results.to_csv(OUT_DIR / "stage31c_exogenous_edge_audit.csv", index=False)
    years.to_csv(OUT_DIR / "stage31c_year_diagnostics.csv", index=False)
    review = results.loc[results["decision"].astype(str).str.contains("CANDIDATE|FRAGILE|WEAK", na=False)].copy() if not results.empty else pd.DataFrame()
    review.to_csv(OUT_DIR / "stage31c_candidate_review.csv", index=False)
    with open(OUT_DIR / "stage31c_exogenous_edge_audit.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)

    md = []
    md.append("# Stage31C Exogenous Fragile-Edge Audit")
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
    md.append("- Research/shadow audit only.")
    md.append("- No EA change, no automatic trading, no paper/live/order authorization.")
    md.append("- Consumes Stage31A enriched dataset and Stage31B gate diagnostics only.")
    md.append("- All gates use expanding prior-year thresholds; no future thresholds are used.")
    md.append("- Combo overlays are diagnostic intersections, not executable strategy rules.")
    md.append("")
    md.append("## Inputs")
    md.append("")
    md.append("```json")
    md.append(json.dumps(report["inputs"], indent=2, ensure_ascii=False, default=str))
    md.append("```")
    md.append("")
    md.append("## Counts")
    md.append("")
    for k, v in report["counts"].items():
        md.append(f"- {k}: `{v}`")
    md.append("")
    md.append("## Candidate / watchlist rows")
    md.append("")
    cols = [
        "decision", "scope_type", "scope_value", "macro_feature", "macro_gate", "overlay_name",
        "wf_events", "wf_pf_x4", "wf_pf_x6", "wf_total_x4", "boot_p05_total_x4", "years_positive_x4", "years_tested", "rank_score",
    ]
    md.append(md_table(review[[c for c in cols if c in review.columns]] if not review.empty else pd.DataFrame(), 30))
    md.append("")
    md.append("## Top diagnostics")
    md.append("")
    top = results.sort_values("rank_score", ascending=False).head(40) if not results.empty and "rank_score" in results.columns else results.head(40)
    md.append(md_table(top[[c for c in cols if c in top.columns]] if not top.empty else pd.DataFrame(), 40))
    md.append("")
    md.append("## Interpretation")
    md.append("")
    md.append("- A fragile positive means the filter improved a weak lineage but still lacks robust bootstrap/year evidence.")
    md.append("- Promotion requires a later forward-shadow tracker; this stage cannot authorize execution.")
    md.append("- If no robust candidate survives, the next useful route is calendar-event enrichment or returning to the validated Stage28C/Stage27C lineage, not broader ML.")
    md.append("")
    md.append("## Output files")
    md.append("")
    md.append("- `data/reports/stage31c_exogenous_edge_audit/stage31c_exogenous_edge_audit.md`")
    md.append("- `data/reports/stage31c_exogenous_edge_audit/stage31c_exogenous_edge_audit.json`")
    md.append("- `data/reports/stage31c_exogenous_edge_audit/stage31c_exogenous_edge_audit.csv`")
    md.append("- `data/reports/stage31c_exogenous_edge_audit/stage31c_candidate_review.csv`")
    md.append("- `data/reports/stage31c_exogenous_edge_audit/stage31c_year_diagnostics.csv`")
    (OUT_DIR / "stage31c_exogenous_edge_audit.md").write_text("\n".join(md), encoding="utf-8")


def main() -> None:
    cfg = AuditConfig()
    ensure_out_dir()
    raw, dataset_info = safe_read_csv(STAGE31A_DATASET)
    stage31b, stage31b_info = safe_read_csv(STAGE31B_RESULTS)
    df = normalize_dataset(raw)

    if df.empty or not all(col in df.columns for col in ("entry_ts_norm", "year", "net_x4")):
        report = {
            "generated_utc": utc_now_iso(),
            "decision": "STAGE31C_INPUT_DATASET_MISSING_REVIEW_ONLY",
            "inputs": {"stage31a_dataset": dataset_info, "stage31b_results": stage31b_info},
            "counts": {"rows_after_parse": int(len(df)), "gate_defs": 0, "audit_results": 0, "candidate_review_count": 0},
            "config": asdict(cfg),
        }
        write_outputs(report, pd.DataFrame(), pd.DataFrame())
        return

    gate_defs = build_gate_defs(df, stage31b, cfg)
    results, year_diag = audit(df, gate_defs, cfg)

    if results.empty:
        decision = "STAGE31C_NO_AUDIT_RESULTS_REVIEW_ONLY"
    elif (results["decision"] == "STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY").any():
        decision = "STAGE31C_HAS_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY"
    elif (results["decision"] == "STAGE31C_FRAGILE_POSITIVE_DIAGNOSTIC_ONLY").any():
        decision = "STAGE31C_HAS_FRAGILE_EXOGENOUS_POSITIVE_DIAGNOSTIC_ONLY"
    elif (results["decision"] == "STAGE31C_WEAK_WATCHLIST_ONLY").any():
        decision = "STAGE31C_HAS_WEAK_EXOGENOUS_WATCHLIST_REVIEW_ONLY"
    else:
        decision = "STAGE31C_NO_ROBUST_EXOGENOUS_EDGE_REVIEW_ONLY"

    review_count = int(results["decision"].astype(str).str.contains("CANDIDATE|FRAGILE|WEAK", na=False).sum()) if not results.empty else 0
    strong_count = int((results["decision"] == "STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY").sum()) if not results.empty else 0
    fragile_count = int((results["decision"] == "STAGE31C_FRAGILE_POSITIVE_DIAGNOSTIC_ONLY").sum()) if not results.empty else 0
    weak_count = int((results["decision"] == "STAGE31C_WEAK_WATCHLIST_ONLY").sum()) if not results.empty else 0

    report = {
        "generated_utc": utc_now_iso(),
        "decision": decision,
        "inputs": {"stage31a_dataset": dataset_info, "stage31b_results": stage31b_info},
        "counts": {
            "rows_after_parse": int(len(df)),
            "gate_defs": int(len(gate_defs)),
            "overlay_defs": int(len(OVERLAY_DEFS)),
            "audit_results": int(len(results)),
            "candidate_review_count": review_count,
            "strong_candidate_count": strong_count,
            "fragile_positive_count": fragile_count,
            "weak_watchlist_count": weak_count,
        },
        "config": asdict(cfg),
    }
    write_outputs(report, results, year_diag)


if __name__ == "__main__":
    main()
