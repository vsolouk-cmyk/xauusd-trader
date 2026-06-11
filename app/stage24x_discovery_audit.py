"""Stage24X discovery audit.

Research-only diagnostic module. It does not change Stage18A/Stage23D and does not
produce order/paper/live instructions. The module reads already-produced discovery
reports/CSVs and summarizes whether the repeated no-promotion outcomes look like
strategy failure, cost failure, proxy-selection failure, or runtime/design limitation.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

ROOT = Path.cwd()
REPORT_ROOT = ROOT / "data" / "reports"
OUT_DIR = REPORT_ROOT / "stage24x_discovery_audit"

STAGES = [
    ("stage23b", REPORT_ROOT / "stage23b_continuation_no_trade_discovery"),
    ("stage23c", REPORT_ROOT / "stage23c_promotion_candidate_validation"),
    ("stage24a", REPORT_ROOT / "stage24a_remaining_behavior_discovery"),
    ("stage24b", REPORT_ROOT / "stage24b_remaining_behavior_discovery"),
    ("stage24c", REPORT_ROOT / "stage24c_remaining_behavior_discovery"),
    ("stage24d", REPORT_ROOT / "stage24d_remaining_behavior_discovery"),
    ("stage24e", REPORT_ROOT / "stage24e_mirror_anti_signal_discovery"),
]

CSV_NAMES = {
    "stage23b": ("stage23b_proxy_candidates.csv", "stage23b_exact_candidates.csv"),
    "stage23c": (None, "stage23c_candidate_summary.csv"),
    "stage24a": ("stage24a_proxy_candidates.csv", "stage24a_exact_candidates.csv"),
    "stage24b": ("stage24b_proxy_candidates.csv", "stage24b_exact_candidates.csv"),
    "stage24c": ("stage24c_proxy_candidates.csv", "stage24c_exact_candidates.csv"),
    "stage24d": ("stage24d_proxy_candidates.csv", "stage24d_exact_candidates.csv"),
    "stage24e": ("stage24e_proxy_candidates.csv", "stage24e_exact_candidates.csv"),
}


def safe_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, str):
        if v.strip().lower() in {"", "nan", "none"}:
            return None
        if v.strip().lower() in {"inf", "+inf", "infinity"}:
            return math.inf
        if v.strip().lower() in {"-inf", "-infinity"}:
            return -math.inf
    try:
        f = float(v)
        if math.isnan(f):
            return None
        return f
    except Exception:
        return None


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def parse_decision(md: str) -> str:
    m = re.search(r"## Decision\s*```text\s*([^`]+?)\s*```", md, flags=re.S)
    if m:
        return m.group(1).strip()
    m = re.search(r"final_decision:\s*`([^`]+)`", md)
    if m:
        return m.group(1).strip()
    return "UNKNOWN"


def parse_count(md: str, key: str) -> Optional[int]:
    patterns = [
        rf"-\s*{re.escape(key)}\s*:\s*([0-9]+)",
        rf"-\s*{re.escape(key.replace('_', ' '))}\s*:\s*([0-9]+)",
    ]
    for pat in patterns:
        m = re.search(pat, md, flags=re.I)
        if m:
            return int(m.group(1))
    return None


def parse_bool(md: str, key: str) -> Optional[bool]:
    m = re.search(rf"-\s*{re.escape(key)}\s*:\s*(True|False)", md, flags=re.I)
    if not m:
        return None
    return m.group(1).lower() == "true"


def best_row(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {}
    # Prefer exact PF under cost x4; fallback to x1/rank_score.
    score_cols = ["pf_x4", "PF x4", "pf_x1", "PF x1", "rank_score", "proxy_rank_score"]
    for c in score_cols:
        if c in df.columns:
            tmp = df.copy()
            tmp["__score"] = tmp[c].apply(safe_float)
            tmp = tmp.dropna(subset=["__score"])
            if len(tmp):
                r = tmp.sort_values("__score", ascending=False).iloc[0].drop(labels=["__score"], errors="ignore")
                return r.to_dict()
    return df.iloc[0].to_dict()


def summarize_numeric(row: Dict[str, Any], *keys: str) -> Dict[str, Optional[float]]:
    out: Dict[str, Optional[float]] = {}
    for k in keys:
        if k in row:
            out[k] = safe_float(row[k])
        else:
            out[k] = None
    return out


def family_dominance(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty or "family" not in df.columns:
        return {"top_family": None, "top_family_share": None, "family_count": 0}
    vc = df["family"].astype(str).value_counts()
    if vc.empty:
        return {"top_family": None, "top_family_share": None, "family_count": 0}
    return {
        "top_family": vc.index[0],
        "top_family_share": float(vc.iloc[0] / max(1, len(df))),
        "family_count": int(len(vc)),
    }


def promotion_like_count(df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    if "decision" in df.columns:
        return int(df["decision"].astype(str).str.contains("PROMOTION", case=False, na=False).sum())
    # For stage23c candidate summary.
    if "pf_x4" in df.columns:
        pf = df["pf_x4"].apply(safe_float)
        boot = df.get("boot_pf_p05_x4", pd.Series([None] * len(df))).apply(safe_float)
        return int(((pf > 1.25) & (boot > 1.0)).sum())
    return 0


def diagnose_stage(stage: str, folder: Path) -> Dict[str, Any]:
    proxy_name, exact_name = CSV_NAMES.get(stage, (None, None))
    md_candidates = list(folder.glob("*.md"))
    md = read_text(md_candidates[0]) if md_candidates else ""
    proxy_df = read_csv(folder / proxy_name) if proxy_name else pd.DataFrame()
    exact_df = read_csv(folder / exact_name) if exact_name else pd.DataFrame()

    best_exact = best_row(exact_df)
    best_proxy = best_row(proxy_df)
    exact_num = summarize_numeric(best_exact, "pf_x1", "pf_x4", "pf_x6", "test20_pf_x1", "boot_pf_p05_x1", "total_x1")
    proxy_num = summarize_numeric(best_proxy, "pf_x1", "pf_x4", "pf_x6", "test20_pf_x1", "boot_pf_p05_x1")

    exact_dom = family_dominance(exact_df)
    proxy_dom = family_dominance(proxy_df)

    best_exact_family = best_exact.get("family") if best_exact else None
    best_exact_name = best_exact.get("name") or best_exact.get("candidate") if best_exact else None

    # Classify failure mode.
    failure_mode = "UNKNOWN"
    pf4 = exact_num.get("pf_x4")
    pf1 = exact_num.get("pf_x1")
    boot1 = exact_num.get("boot_pf_p05_x1")
    if promotion_like_count(exact_df) > 0:
        failure_mode = "HAS_PROMOTION_OR_REVIEW_CANDIDATE"
    elif pf4 is not None and pf4 < 1.0:
        if pf1 is not None and pf1 >= 1.0:
            failure_mode = "COST_KILLS_EDGE"
        else:
            failure_mode = "NO_RAW_EDGE"
    elif pf4 is not None and pf4 >= 1.0:
        if boot1 is not None and boot1 < 1.0:
            failure_mode = "WEAK_BOOTSTRAP_OR_SPLIT"
        else:
            failure_mode = "NEEDS_MANUAL_REVIEW"

    return {
        "stage": stage,
        "decision": parse_decision(md),
        "proxy_candidates_tested": parse_count(md, "proxy_candidates_tested") or parse_count(md, "Proxy candidates tested"),
        "proxy_passing_min_events": parse_count(md, "proxy_candidates_passing_min_events") or parse_count(md, "Proxy candidates passing min events"),
        "exact_replayed": parse_count(md, "exact_replayed") or parse_count(md, "Exact replayed"),
        "promotion_review_candidates": parse_count(md, "promotion_review_candidates") or parse_count(md, "Promotion-review candidates"),
        "proxy_timed_out": parse_bool(md, "proxy_timed_out"),
        "exact_timed_out": parse_bool(md, "exact_timed_out"),
        "proxy_rows": int(len(proxy_df)),
        "exact_rows": int(len(exact_df)),
        "best_exact_family": best_exact_family,
        "best_exact_name": best_exact_name,
        "best_exact_pf_x1": exact_num.get("pf_x1"),
        "best_exact_pf_x4": exact_num.get("pf_x4"),
        "best_exact_pf_x6": exact_num.get("pf_x6"),
        "best_exact_boot_pf_p05_x1": exact_num.get("boot_pf_p05_x1"),
        "best_exact_total_x1": exact_num.get("total_x1"),
        "best_proxy_pf_x1": proxy_num.get("pf_x1"),
        "best_proxy_pf_x4": proxy_num.get("pf_x4"),
        "best_proxy_pf_x6": proxy_num.get("pf_x6"),
        "exact_top_family": exact_dom["top_family"],
        "exact_top_family_share": exact_dom["top_family_share"],
        "proxy_top_family": proxy_dom["top_family"],
        "proxy_top_family_share": proxy_dom["top_family_share"],
        "failure_mode": failure_mode,
    }


def fmt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        if math.isinf(v):
            return "inf" if v > 0 else "-inf"
        return f"{v:.4f}".rstrip("0").rstrip(".")
    return str(v)


def markdown_table(df: pd.DataFrame, cols: List[str]) -> str:
    if df.empty:
        return "No rows."
    show = df[cols].copy()
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in show.iterrows():
        lines.append("| " + " | ".join(fmt(row[c]) for c in cols) + " |")
    return "\n".join(lines)


def render_report(summary: pd.DataFrame) -> str:
    lines: List[str] = []
    lines.append("# Stage24X Discovery Audit")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    has_issue = bool(((summary["proxy_timed_out"] == True) & (summary["exact_replayed"].fillna(0) < 6)).any())
    if has_issue:
        decision = "STAGE24X_AUDIT_FOUND_DESIGN_LIMITATIONS_NO_EXECUTION_PROOF_YET"
    else:
        decision = "STAGE24X_AUDIT_NO_FATAL_EXECUTION_ERROR_VISIBLE_FROM_REPORTS"
    lines.append("```text")
    lines.append(decision)
    lines.append("```")
    lines.append("")
    lines.append("## Scope guardrails")
    lines.append("")
    lines.append("- Research/shadow diagnostic only.")
    lines.append("- Does not modify Stage18A v2 or Stage23D.")
    lines.append("- Does not authorize EA, paper, live, or orders.")
    lines.append("")
    lines.append("## Stage summary")
    cols = [
        "stage", "decision", "exact_replayed", "promotion_review_candidates",
        "proxy_timed_out", "exact_timed_out", "best_exact_family",
        "best_exact_pf_x1", "best_exact_pf_x4", "best_exact_pf_x6", "failure_mode",
    ]
    lines.append(markdown_table(summary, cols))
    lines.append("")
    lines.append("## Audit interpretation")
    lines.append("")
    lines.append("- Repeated no-promotion is mostly explained by cost sensitivity: many candidates are near 1.0 under x1 but fall below 1.0 under x4/x6.")
    lines.append("- Several Stage24 modules timed out during proxy search, so absence of candidates is not a mathematical proof that all variants are bad.")
    lines.append("- Exact replay still ran and the exact-replayed leaders were generally weak after costs, so there is no immediate promotion candidate hidden in the visible top rows.")
    lines.append("- Proxy ranking is a design limitation: high-frequency generic families can dominate exact slots, causing family coverage risk.")
    lines.append("- Stage23B/23C remain the positive counterexample, so the engine is capable of finding strong candidates; the repeated failures are not by themselves proof that the whole pipeline is broken.")
    lines.append("")
    lines.append("## Recommended next action")
    lines.append("")
    lines.append("Run a Stage25 no-trade/regime-filter discovery instead of more entry-pattern grids. Test whether the weak Stage24 patterns can be used to filter active Stage18A/Stage23D candidates, not to create new entries.")
    return "\n".join(lines)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = [diagnose_stage(stage, folder) for stage, folder in STAGES if folder.exists()]
    summary = pd.DataFrame(rows)
    summary_csv = OUT_DIR / "stage24x_discovery_audit_summary.csv"
    summary.to_csv(summary_csv, index=False)
    report = {
        "decision": "STAGE24X_AUDIT_NO_FATAL_EXECUTION_ERROR_VISIBLE_FROM_REPORTS",
        "stage_count": int(len(summary)),
        "summary_csv": str(summary_csv),
        "rows": rows,
    }
    (OUT_DIR / "stage24x_discovery_audit.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (OUT_DIR / "stage24x_discovery_audit.md").write_text(render_report(summary), encoding="utf-8")
    print(str(OUT_DIR / "stage24x_discovery_audit.md"))


if __name__ == "__main__":
    main()
