#!/usr/bin/env python3
"""
Stage 18D — Promotion Consolidation and Overlap Audit

Purpose:
- Stage18C exhaustive refinement can be slow and should not be rerun routinely.
- Stage18C produced multiple promoted variants, many of which are minor parameter
  variations of the same behavior.
- This stage reads Stage18C output CSVs, de-duplicates promoted candidates by
  overlap/family, and recommends a small forward-shadow shortlist.

Inputs:
- data/reports/stage18c_near_miss_refinement_lab/stage18c_refinement_summary.csv
- data/reports/stage18c_near_miss_refinement_lab/stage18c_refinement_trades.csv

Hard rules:
- Research consolidation only.
- No EA change.
- No automatic trading.
- No paper/live/order authorization.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd


TOOL_VERSION = "v1"
DEFAULT_REPORT_DIR = Path("data/reports/stage18c_near_miss_refinement_lab")
DEFAULT_OUT_DIR = Path("data/reports/stage18d_promotion_consolidation")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing required CSV: {path}")
    return pd.read_csv(path)


def safe_float(x, default=0.0) -> float:
    try:
        if pd.isna(x):
            return default
        return float(x)
    except Exception:
        return default


def normalize_trades(trades: pd.DataFrame) -> pd.DataFrame:
    x = trades.copy()
    for c in ["signal_dt", "entry_dt", "exit_dt"]:
        if c in x.columns:
            x[c] = pd.to_datetime(x[c], utc=True, errors="coerce")
    if "entry_dt" in x.columns:
        x["entry_key"] = x["entry_dt"].dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    else:
        x["entry_key"] = ""
    return x


def overlap_stats(trades: pd.DataFrame, variants: List[str]) -> pd.DataFrame:
    rows = []
    sets = {}
    for v in variants:
        s = set(trades.loc[trades["variant"].eq(v), "entry_key"].dropna().astype(str))
        sets[v] = s

    for i, a in enumerate(variants):
        for b in variants[i + 1:]:
            sa, sb = sets.get(a, set()), sets.get(b, set())
            inter = len(sa & sb)
            union = len(sa | sb)
            min_base = min(len(sa), len(sb)) if min(len(sa), len(sb)) else 0
            rows.append({
                "variant_a": a,
                "variant_b": b,
                "events_a": len(sa),
                "events_b": len(sb),
                "overlap_count": inter,
                "jaccard": round(inter / union, 6) if union else 0.0,
                "overlap_min_share": round(inter / min_base, 6) if min_base else 0.0,
            })
    return pd.DataFrame(rows).sort_values(["overlap_min_share", "jaccard"], ascending=[False, False]) if rows else pd.DataFrame()


def decision_score(row: pd.Series) -> float:
    """
    Conservative consolidation score:
    - prefer robust PF x4 and bootstrap p05
    - prefer enough events/frequency
    - penalize extremely low median or excessive dependence on 2026-only
    """
    pf4 = safe_float(row.get("pf_x4"))
    pf1 = safe_float(row.get("pf_x1"))
    boot = safe_float(row.get("boot_pf_p05"))
    test = safe_float(row.get("test20_pf"))
    median = safe_float(row.get("median_x1"))
    events = safe_float(row.get("events"))
    freq = safe_float(row.get("freq_per_month"))
    score = 0.0
    score += min(8.0, pf4 * 5.0)
    score += min(5.0, boot * 3.5)
    score += min(5.0, test * 1.2)
    score += min(4.0, pf1 * 1.5)
    score += min(3.0, max(0.0, median) * 1.5)
    score += min(2.0, events / 150.0)
    score += min(2.0, freq / 5.0)
    return round(score, 6)


def choose_representatives(promoted: pd.DataFrame, trades: pd.DataFrame, max_per_family: int, overlap_threshold: float) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    p = promoted.copy()
    if p.empty:
        return p, pd.DataFrame(), pd.DataFrame()

    p["consolidation_score"] = p.apply(decision_score, axis=1)
    p = p.sort_values(["family", "consolidation_score", "score"], ascending=[True, False, False]).reset_index(drop=True)

    selected_rows = []
    rejected_rows = []
    for family, g in p.groupby("family", sort=False):
        selected_for_family: List[str] = []
        for _, row in g.sort_values(["consolidation_score", "score"], ascending=[False, False]).iterrows():
            v = str(row["variant"])
            if len(selected_for_family) >= max_per_family:
                r = row.to_dict()
                r["consolidation_decision"] = "DUPLICATE_FAMILY_CAP"
                r["consolidation_reason"] = f"Family already has {max_per_family} selected representative(s)."
                rejected_rows.append(r)
                continue

            # Reject if too much overlap with a selected representative in the same family.
            v_entries = set(trades.loc[trades["variant"].eq(v), "entry_key"].dropna().astype(str))
            duplicate = False
            duplicate_of = ""
            duplicate_share = 0.0
            for sv in selected_for_family:
                s_entries = set(trades.loc[trades["variant"].eq(sv), "entry_key"].dropna().astype(str))
                if not v_entries or not s_entries:
                    continue
                overlap = len(v_entries & s_entries) / max(1, min(len(v_entries), len(s_entries)))
                if overlap >= overlap_threshold:
                    duplicate = True
                    duplicate_of = sv
                    duplicate_share = overlap
                    break

            if duplicate:
                r = row.to_dict()
                r["consolidation_decision"] = "DUPLICATE_HIGH_OVERLAP"
                r["consolidation_reason"] = f"High overlap with {duplicate_of}: {duplicate_share:.3f}"
                rejected_rows.append(r)
                continue

            r = row.to_dict()
            r["consolidation_decision"] = "SELECT_FORWARD_SHADOW_DESIGN_SHORTLIST"
            r["consolidation_reason"] = "Best non-duplicate representative for this family."
            selected_rows.append(r)
            selected_for_family.append(v)

    selected = pd.DataFrame(selected_rows)
    rejected = pd.DataFrame(rejected_rows)

    variants = p["variant"].astype(str).tolist()
    overlaps = overlap_stats(trades, variants)
    return selected, rejected, overlaps


def final_decision(selected: pd.DataFrame) -> Tuple[str, List[str]]:
    if selected.empty:
        return "NO_SHORTLIST_SELECTED", ["No promoted candidate survived consolidation."]
    families = selected["family"].nunique()
    if len(selected) >= 2 and families >= 2:
        return "MULTI_FAMILY_FORWARD_SHADOW_SHORTLIST_READY", ["At least two independent behavior families have representatives."]
    return "SINGLE_FAMILY_FORWARD_SHADOW_SHORTLIST_READY", ["Only one behavior family is ready after de-duplication."]


def run(report_dir: Path, out_dir: Path, max_per_family: int, overlap_threshold: float) -> int:
    generated = now_iso()
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_path = report_dir / "stage18c_refinement_summary.csv"
    trades_path = report_dir / "stage18c_refinement_trades.csv"

    summary = read_csv(summary_path)
    trades = normalize_trades(read_csv(trades_path))

    promoted = summary[summary["decision"].eq("PROMOTE_FORWARD_SHADOW_DESIGN_CANDIDATE")].copy()
    selected, rejected, overlaps = choose_representatives(
        promoted=promoted,
        trades=trades,
        max_per_family=max_per_family,
        overlap_threshold=overlap_threshold,
    )

    decision, reasons = final_decision(selected)

    selected_csv = out_dir / "stage18d_selected_forward_shadow_shortlist.csv"
    rejected_csv = out_dir / "stage18d_duplicate_or_rejected_promotions.csv"
    overlap_csv = out_dir / "stage18d_promoted_overlap_matrix.csv"
    json_path = out_dir / "stage18d_promotion_consolidation.json"
    md_path = out_dir / "stage18d_promotion_consolidation.md"

    selected.to_csv(selected_csv, index=False)
    rejected.to_csv(rejected_csv, index=False)
    overlaps.to_csv(overlap_csv, index=False)

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "inputs": {
            "summary_csv": str(summary_path),
            "trades_csv": str(trades_path),
            "max_per_family": int(max_per_family),
            "overlap_threshold": float(overlap_threshold),
        },
        "counts": {
            "summary_rows": int(len(summary)),
            "promoted_rows": int(len(promoted)),
            "selected_rows": int(len(selected)),
            "rejected_duplicate_rows": int(len(rejected)),
            "families_selected": int(selected["family"].nunique()) if not selected.empty else 0,
        },
        "final_decision": decision,
        "reasons": reasons,
        "selected": selected.to_dict(orient="records"),
        "authorization_flags": {
            "trade_authorization": False,
            "ea_change_authorization": False,
            "paper_order_authorization": False,
            "live_order_authorization": False,
            "automatic_trading": False,
        },
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    lines = [
        "# Stage 18D Promotion Consolidation and Overlap Audit",
        "",
        f"Generated UTC: `{generated}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: research consolidation only. No EA change, no automatic trading, no paper/live authorization.",
        "",
        "## Purpose",
        "- Avoid rerunning slow Stage18C exhaustive refinement for routine work.",
        "- De-duplicate promoted variants that are only small parameter variations.",
        "- Select a small forward-shadow design shortlist.",
        "",
        "## Inputs",
        f"- summary_csv: `{summary_path}`",
        f"- trades_csv: `{trades_path}`",
        f"- promoted_rows: `{len(promoted)}`",
        f"- max_per_family: `{max_per_family}`",
        f"- overlap_threshold: `{overlap_threshold}`",
        "",
        "## Final decision",
        f"- final_decision: `{decision}`",
        "",
        "## Reasons",
    ]
    for r in reasons:
        lines.append(f"- {r}")

    lines += [
        "",
        "## Selected forward-shadow design shortlist",
        "| Rank | Variant | Family | Events | Freq/mo | PF x1 | PF x4 | Test20 PF | 2026 PF | Boot PF p05 | Consolidation score | Reason |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    if not selected.empty:
        for i, r in enumerate(selected.sort_values("consolidation_score", ascending=False).to_dict(orient="records"), 1):
            lines.append(
                f"| {i} | `{r['variant']}` | `{r['family']}` | {r['events']} | {r['freq_per_month']} | {r['pf_x1']} | {r['pf_x4']} | {r['test20_pf']} | {r['pf_2026']} | {r['boot_pf_p05']} | {r['consolidation_score']} | {r['consolidation_reason']} |"
            )
    else:
        lines.append("| 0 | none | none | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | none |")

    lines += [
        "",
        "## Top promoted overlap pairs",
        "| Rank | Variant A | Variant B | Events A | Events B | Overlap | Jaccard |",
        "|---:|---|---|---:|---:|---:|---:|",
    ]
    if not overlaps.empty:
        for i, r in enumerate(overlaps.head(20).to_dict(orient="records"), 1):
            lines.append(
                f"| {i} | `{r['variant_a']}` | `{r['variant_b']}` | {r['events_a']} | {r['events_b']} | {r['overlap_min_share']} | {r['jaccard']} |"
            )
    else:
        lines.append("| 0 | none | none | 0 | 0 | 0 | 0 |")

    lines += [
        "",
        "## Interpretation",
        "- Selected rows are not trade signals; they are only candidates for a later forward-shadow collector patch.",
        "- Highly overlapping variants should not all enter Stage18A; doing so would double-count the same behavior.",
        "- A future Stage18E/19 patch should add only the selected shortlist to unified shadow operations.",
        "- No paper/live/order escalation is authorized.",
        "",
        "## Output files",
        f"- selected_csv: `{selected_csv}`",
        f"- rejected_csv: `{rejected_csv}`",
        f"- overlap_csv: `{overlap_csv}`",
        f"- json: `{json_path}`",
        f"- md: `{md_path}`",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 18D promotion consolidation: DONE")
    print(f"final_decision={decision}")
    print(f"selected={len(selected)} promoted_input={len(promoted)}")
    print(f"Report: {md_path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--max-per-family", type=int, default=1)
    p.add_argument("--overlap-threshold", type=float, default=0.80)
    args = p.parse_args()

    return run(
        report_dir=Path(args.report_dir),
        out_dir=Path(args.out_dir),
        max_per_family=int(args.max_per_family),
        overlap_threshold=float(args.overlap_threshold),
    )


if __name__ == "__main__":
    raise SystemExit(main())
