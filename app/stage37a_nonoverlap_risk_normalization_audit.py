from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

ROOT = Path.cwd()
REPORT_ROOT = ROOT / "data" / "reports"
OUT_DIR = REPORT_ROOT / "stage37a_nonoverlap_risk_normalization_audit"
OUT_DIR.mkdir(parents=True, exist_ok=True)

STAGE_SUMMARY_PATHS = {
    "stage36b": REPORT_ROOT / "stage36b_session_regime_baseline_scout" / "stage36b_summary.json",
    "stage36c": REPORT_ROOT / "stage36c_event_risk_guard_scout" / "stage36c_summary.json",
    "stage36d": REPORT_ROOT / "stage36d_volatility_compression_breakout_scout" / "stage36d_summary.json",
    "stage36e": REPORT_ROOT / "stage36e_market_structure_sweep_reclaim_scout" / "stage36e_summary.json",
    "stage36f": REPORT_ROOT / "stage36f_broker_cost_window_guard_scout" / "stage36f_summary.json",
}

CANDIDATE_FILES = [
    REPORT_ROOT / "stage36f_broker_cost_window_guard_scout" / "stage36f_background_queue.csv",
    REPORT_ROOT / "stage36f_broker_cost_window_guard_scout" / "stage36f_cost_window_candidate_summary.csv",
    REPORT_ROOT / "stage36e_market_structure_sweep_reclaim_scout" / "stage36e_background_queue.csv",
    REPORT_ROOT / "stage36e_market_structure_sweep_reclaim_scout" / "stage36e_candidate_summary.csv",
]

LEDGER_FILES = [
    REPORT_ROOT / "stage36e_market_structure_sweep_reclaim_scout" / "stage36e_signal_ledger.csv",
]

THRESHOLDS = {
    "min_events_review": 40,
    "min_pf_review": 1.25,
    "min_avg_review": 0.15,
    "min_wr_review": 0.52,
    "min_tail_pf_review": 1.00,
    "min_cost1_pf_review": 1.05,
    "max_drawdown_review": -45.0,
    "max_drawdown_per_100_review": -12.0,
    "min_recent_pf_review": 1.00,
    "cost_penalty_x4": 1.0,
}


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"missing": True, "path": str(path)}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": str(exc), "path": str(path)}


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return default
        return float(x)
    except Exception:
        return default


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return default
        return int(float(x))
    except Exception:
        return default


def _pf(series: pd.Series) -> float:
    wins = series[series > 0].sum()
    losses = -series[series < 0].sum()
    if losses <= 0:
        return float("inf") if wins > 0 else 0.0
    return float(wins / losses)


def _max_drawdown(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    eq = series.cumsum()
    peak = eq.cummax()
    dd = eq - peak
    return float(dd.min())


def _find_col(cols: List[str], candidates: List[str]) -> Optional[str]:
    lower = {c.lower(): c for c in cols}
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    for c in cols:
        lc = c.lower()
        if any(cand.lower() in lc for cand in candidates):
            return c
    return None


def _load_candidates() -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    frames = []
    audit = []
    for p in CANDIDATE_FILES:
        row = {"path": str(p), "exists": p.exists(), "rows": 0, "error": ""}
        if not p.exists():
            audit.append(row)
            continue
        try:
            df = pd.read_csv(p)
            row["rows"] = len(df)
            df["source_file"] = str(p)
            frames.append(df)
        except Exception as exc:
            row["error"] = str(exc)
        audit.append(row)
    if not frames:
        return pd.DataFrame(), audit
    out = pd.concat(frames, ignore_index=True, sort=False)
    # Deduplicate by variant and guard when available, keeping the strongest PF rows first.
    pf_col = _find_col(list(out.columns), ["pf_x4"])
    if pf_col:
        out["_pf_sort"] = out[pf_col].map(_safe_float)
        out = out.sort_values("_pf_sort", ascending=False)
    key_cols = [c for c in ["variant_id", "guard_filter"] if c in out.columns]
    if key_cols:
        out = out.drop_duplicates(subset=key_cols, keep="first")
    return out.reset_index(drop=True), audit


def _rank_background_candidates(df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    if df.empty:
        return df
    for col in ["signal_count", "pf_x4", "avg_net_x4", "win_rate_x4", "tail_pf_x4", "recent_pf_x4", "cost1_pf_x4", "max_drawdown_x4"]:
        if col in df.columns:
            df[col] = df[col].map(_safe_float)
    if "stage36f_decision" in df.columns:
        decision_col = "stage36f_decision"
    elif "stage36e_decision" in df.columns:
        decision_col = "stage36e_decision"
    else:
        decision_col = None
    if decision_col:
        bg = df[df[decision_col].astype(str).str.contains("BACKGROUND", na=False)].copy()
    else:
        bg = df.copy()
    if bg.empty:
        return bg
    # Score intentionally rewards robust raw edge but penalizes absolute drawdown and weak tail/recent.
    bg["risk_norm_dd_per_100"] = bg.apply(
        lambda r: (_safe_float(r.get("max_drawdown_x4")) / max(_safe_float(r.get("signal_count")), 1.0)) * 100.0,
        axis=1,
    )
    bg["branch_priority_score"] = (
        bg.get("pf_x4", 0).map(_safe_float) * 2.0
        + bg.get("cost1_pf_x4", 0).map(_safe_float) * 2.0
        + bg.get("tail_pf_x4", 0).map(_safe_float)
        + bg.get("recent_pf_x4", 0).map(_safe_float)
        + bg.get("avg_net_x4", 0).map(_safe_float) / 3.0
        - bg["risk_norm_dd_per_100"].abs() / 20.0
    )
    sort_cols = ["branch_priority_score", "pf_x4", "cost1_pf_x4", "tail_pf_x4"]
    bg = bg.sort_values(sort_cols, ascending=[False, False, False, False])
    return bg.head(top_n).reset_index(drop=True)


def _load_ledger() -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    audit = []
    for p in LEDGER_FILES:
        row = {"path": str(p), "exists": p.exists(), "rows": 0, "error": ""}
        if not p.exists():
            audit.append(row)
            continue
        try:
            df = pd.read_csv(p)
            row["rows"] = len(df)
            audit.append(row)
            return df, audit
        except Exception as exc:
            row["error"] = str(exc)
            audit.append(row)
    return pd.DataFrame(), audit


def _normalize_ledger(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    ts_col = _find_col(list(out.columns), ["entry_ts", "entry_utc", "signal_ts", "signal_time", "ts", "utc_time"])
    exit_col = _find_col(list(out.columns), ["exit_ts", "exit_utc"])
    net_col = _find_col(list(out.columns), ["net_x4", "net_usd_x4", "net", "pnl_x4", "net_R", "net_r"])
    if ts_col:
        out["entry_ts_norm"] = pd.to_datetime(out[ts_col], errors="coerce", utc=True)
    else:
        out["entry_ts_norm"] = pd.NaT
    if exit_col:
        out["exit_ts_norm"] = pd.to_datetime(out[exit_col], errors="coerce", utc=True)
    else:
        # Conservative fixed proxy: one H1 step if no exit column exists.
        out["exit_ts_norm"] = out["entry_ts_norm"] + pd.Timedelta(hours=1)
    if net_col:
        out["net_x4_norm"] = pd.to_numeric(out[net_col], errors="coerce")
    elif "avg_net_x4" in out.columns:
        out["net_x4_norm"] = pd.to_numeric(out["avg_net_x4"], errors="coerce")
    else:
        out["net_x4_norm"] = 0.0
    out = out.dropna(subset=["entry_ts_norm", "net_x4_norm"]).copy()
    if "variant_id" not in out.columns:
        setup_col = _find_col(list(out.columns), ["setup", "strategy_id", "candidate_id"])
        out["variant_id"] = out[setup_col].astype(str) if setup_col else "unknown_variant"
    return out


def _cooldown_nonoverlap_metrics(ledger: pd.DataFrame, candidates: pd.DataFrame) -> pd.DataFrame:
    if ledger.empty or candidates.empty:
        return pd.DataFrame()
    norm = _normalize_ledger(ledger)
    if norm.empty:
        return pd.DataFrame()

    # Evaluate top candidates only; if exact variant ids don't match ledger variants, fall back to setup substring.
    rows = []
    top_ids = candidates.get("variant_id", pd.Series(dtype=str)).dropna().astype(str).unique().tolist()[:12]
    for vid in top_ids:
        sub = norm[norm["variant_id"].astype(str) == vid].copy()
        if sub.empty:
            # Many ledgers store setup instead of full variant id. Try suffix matching.
            tokens = [t for t in vid.split("_") if t in {"roll12", "roll24", "roll48", "prevday", "high", "low", "continuation", "reclaim", "reversal", "long", "short"}]
            if tokens:
                mask = norm["variant_id"].astype(str).str.lower()
                for t in tokens[:4]:
                    mask = mask & norm["variant_id"].astype(str).str.lower().str.contains(t.lower(), na=False)
                sub = norm[mask].copy()
        if sub.empty:
            continue
        sub = sub.sort_values("entry_ts_norm")
        for cooldown_h in [1, 2, 4, 8, 12, 24]:
            selected = []
            next_allowed = pd.Timestamp.min.tz_localize("UTC")
            for _, r in sub.iterrows():
                ts = r["entry_ts_norm"]
                if ts >= next_allowed:
                    selected.append(r)
                    next_allowed = ts + pd.Timedelta(hours=cooldown_h)
            if not selected:
                continue
            sel = pd.DataFrame(selected)
            s = sel["net_x4_norm"].astype(float)
            n = len(sel)
            pf = _pf(s)
            avg = float(s.mean())
            wr = float((s > 0).mean())
            dd = _max_drawdown(s)
            dd100 = dd / max(n, 1) * 100.0
            tail = s.tail(20)
            rows.append({
                "variant_id": vid,
                "cooldown_hours": cooldown_h,
                "signal_count": n,
                "pf_x4": pf,
                "avg_net_x4": avg,
                "win_rate_x4": wr,
                "max_drawdown_x4": dd,
                "max_drawdown_per_100_x4": dd100,
                "tail_pf_x4": _pf(tail) if not tail.empty else 0.0,
                "recent_pf_x4": _pf(tail) if not tail.empty else 0.0,
            })
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    out["passes_risk_normalized_research"] = (
        (out["signal_count"] >= THRESHOLDS["min_events_review"]) &
        (out["pf_x4"] >= THRESHOLDS["min_pf_review"]) &
        (out["avg_net_x4"] >= THRESHOLDS["min_avg_review"]) &
        (out["win_rate_x4"] >= THRESHOLDS["min_wr_review"]) &
        (out["tail_pf_x4"] >= THRESHOLDS["min_tail_pf_review"]) &
        (out["max_drawdown_per_100_x4"] >= THRESHOLDS["max_drawdown_per_100_review"])
    )
    out = out.sort_values(["passes_risk_normalized_research", "pf_x4", "max_drawdown_per_100_x4"], ascending=[False, False, False])
    return out


def main() -> None:
    summaries = {k: _read_json(v) for k, v in STAGE_SUMMARY_PATHS.items()}
    branch_rows = []
    for stage, s in summaries.items():
        branch_rows.append({
            "stage": stage,
            "decision": s.get("decision", "MISSING_OR_ERROR"),
            "strict_review_ready_rows": _safe_int(s.get("strict_review_ready_rows")),
            "background_rows": _safe_int(s.get("background_rows")),
            "kill_or_repair_rows": _safe_int(s.get("kill_or_repair_rows")),
            "recommended_next_stage": s.get("recommended_next_stage", ""),
            "missing": bool(s.get("missing", False)),
            "error": s.get("error", ""),
        })
    branch_df = pd.DataFrame(branch_rows)
    total_strict = int(branch_df["strict_review_ready_rows"].sum()) if not branch_df.empty else 0
    total_background = int(branch_df["background_rows"].sum()) if not branch_df.empty else 0

    candidates, cand_audit = _load_candidates()
    ranked_bg = _rank_background_candidates(candidates)
    ledger, ledger_audit = _load_ledger()
    nonoverlap = _cooldown_nonoverlap_metrics(ledger, ranked_bg)
    nonoverlap_pass_rows = int(nonoverlap.get("passes_risk_normalized_research", pd.Series(dtype=bool)).sum()) if not nonoverlap.empty else 0

    if total_strict > 0:
        decision = "STAGE37A_HAS_STRICT_STAGE36_CANDIDATE_REVIEW_REQUIRED_RESEARCH_ONLY"
        recommended = "BUILD_STRICT_REVIEW_FOR_STAGE36_STRICT_CANDIDATE"
    elif nonoverlap_pass_rows > 0:
        decision = "STAGE37A_RISK_NORMALIZED_STRUCTURE_REVIEW_CANDIDATE_RESEARCH_ONLY"
        recommended = "BUILD_STAGE37B_NONOVERLAP_STRUCTURE_RISK_REVIEW"
    elif total_background > 0:
        decision = "STAGE37A_NO_STRICT_BACKGROUND_ONLY_RISK_NORMALIZATION_NEEDED_RESEARCH_ONLY"
        recommended = "KEEP_STAGE35C_AND_STAGE36_BACKGROUND_WATCHLIST_BUILD_STAGE37B_ONLY_IF_NONOVERLAP_OR_NEW_DATA_IMPROVES"
    else:
        decision = "STAGE37A_NO_STAGE36_EDGE_RESEARCH_ONLY"
        recommended = "STOP_STAGE36_BRANCHES_AND_RETURN_TO_THESIS_SELECTION"

    branch_df.to_csv(OUT_DIR / "stage37a_branch_decision_matrix.csv", index=False)
    pd.DataFrame(cand_audit).to_csv(OUT_DIR / "stage37a_candidate_source_audit.csv", index=False)
    pd.DataFrame(ledger_audit).to_csv(OUT_DIR / "stage37a_ledger_source_audit.csv", index=False)
    if not ranked_bg.empty:
        ranked_bg.to_csv(OUT_DIR / "stage37a_background_watchlist.csv", index=False)
    else:
        pd.DataFrame().to_csv(OUT_DIR / "stage37a_background_watchlist.csv", index=False)
    if not nonoverlap.empty:
        nonoverlap.to_csv(OUT_DIR / "stage37a_nonoverlap_risk_metrics.csv", index=False)
    else:
        pd.DataFrame().to_csv(OUT_DIR / "stage37a_nonoverlap_risk_metrics.csv", index=False)

    top_watch = [] if ranked_bg.empty else ranked_bg.head(8).to_dict(orient="records")
    summary = {
        "generated_utc": pd.Timestamp.utcnow().isoformat(),
        "decision": decision,
        "execution_status": "RESEARCH_ONLY",
        "commercial_transition_authorized": False,
        "no_ea_change": True,
        "no_paper_live": True,
        "no_order_authorization": True,
        "primary_objective": "BRANCH_LEVEL_DECISION_AFTER_STAGE36_THESIS_SWEEP",
        "recommended_next_stage": recommended,
        "total_strict_review_ready_rows": total_strict,
        "total_background_rows": total_background,
        "nonoverlap_pass_rows": nonoverlap_pass_rows,
        "branch_count": len(branch_df),
        "background_watchlist_rows": len(ranked_bg),
        "top_background_variant": top_watch[0].get("variant_id", "") if top_watch else "",
    }
    (OUT_DIR / "stage37a_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    md = []
    md.append("# XAUUSD Stage37A — Branch-Level Decision / Non-Overlap Risk Normalization Audit")
    md.append(f"Generated UTC: {summary['generated_utc']}")
    md.append("")
    md.append("## Decision")
    for k in ["decision", "execution_status", "commercial_transition_authorized", "no_ea_change", "no_paper_live", "no_order_authorization", "primary_objective", "recommended_next_stage"]:
        md.append(f"{k.upper()} = {summary[k]}")
    md.append("")
    md.append("## Why this stage exists")
    md.append("Stage36B through Stage36F tested the new thesis branches opened by Stage36A. None produced a strict review-ready row. Several market-structure and cost-window rows remained background-only, mainly because absolute drawdown failed. Stage37A prevents two mistakes: promoting a non-strict row too early, or killing a raw edge before checking whether overlapping signal evaluation inflated drawdown.")
    md.append("")
    md.append("## Branch decision matrix")
    md.append(branch_df.to_markdown(index=False))
    md.append("")
    md.append("## Summary")
    for k in ["total_strict_review_ready_rows", "total_background_rows", "nonoverlap_pass_rows", "background_watchlist_rows", "top_background_variant"]:
        md.append(f"{k} = {summary[k]}")
    md.append("")
    md.append("## Background watchlist")
    if ranked_bg.empty:
        md.append("No background rows found.")
    else:
        show_cols = [c for c in ["variant_id", "guard_filter", "signal_count", "pf_x4", "avg_net_x4", "win_rate_x4", "tail_pf_x4", "recent_pf_x4", "cost1_pf_x4", "max_drawdown_x4", "risk_norm_dd_per_100", "branch_priority_score"] if c in ranked_bg.columns]
        md.append(ranked_bg[show_cols].head(12).to_markdown(index=False))
    md.append("")
    md.append("## Non-overlap risk-normalization probe")
    if nonoverlap.empty:
        md.append("No non-overlap metrics were produced. This usually means the ledger schema did not include enough timestamp/net columns for reconstruction, or candidate IDs did not match ledger IDs.")
    else:
        md.append(nonoverlap.head(20).to_markdown(index=False))
    md.append("")
    md.append("## Operational interpretation")
    md.append("1. No EA, paper-live, or order path is authorized.")
    md.append("2. If non-overlap normalization produces a pass row, the next stage is a strict non-overlap structure review, not live trading.")
    md.append("3. If non-overlap normalization does not produce a pass row, keep Stage35C and the Stage36 background watchlist only as monitors and do not mine the same branches indefinitely.")
    md.append("4. The practical bottleneck is no longer entry discovery alone; it is whether raw structure edge can be converted into acceptable executable risk.")
    md.append("")
    md.append("## Output files")
    for name in ["stage37a_summary.json", "stage37a_branch_decision_matrix.csv", "stage37a_background_watchlist.csv", "stage37a_nonoverlap_risk_metrics.csv", "stage37a_candidate_source_audit.csv", "stage37a_ledger_source_audit.csv"]:
        md.append(f"- `data/reports/stage37a_nonoverlap_risk_normalization_audit/{name}`")
    (OUT_DIR / "stage37a_nonoverlap_risk_normalization_audit.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"DECISION={decision}")
    print(f"RECOMMENDED_NEXT_STAGE={recommended}")
    print(f"OUT_DIR={OUT_DIR}")


if __name__ == "__main__":
    main()
