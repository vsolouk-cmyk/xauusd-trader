#!/usr/bin/env python3
"""
Stage 11C — Recent Short-Regime Diagnostic

Why:
- Stage 11A and Stage 11B found no robust all-history short candidate.
- Stage 11B top candidates show large positive test-period PnL but weak all-history PF/median/drawdown.
- This may be a recent-regime effect, not a stable short edge.

Purpose:
- Diagnose whether Stage 11B short_rally_rejection is only recent-regime watchlist.
- Do not promote it to robustness/execution replay unless distribution quality is acceptable.
- No EA change, no order logic.

Inputs:
- data/reports/stage11b_alternative_short_thesis_lab/stage11b_short_candidate_summary.csv
- data/reports/stage11b_alternative_short_thesis_lab/stage11b_short_candidate_trades.csv

Outputs:
- data/reports/stage11c_recent_short_regime_diagnostic/stage11c_recent_short_regime_diagnostic.md
- data/reports/stage11c_recent_short_regime_diagnostic/stage11c_recent_candidate_summary.csv
- data/reports/stage11c_recent_short_regime_diagnostic/stage11c_recent_candidate_period_breakdown.csv
- data/reports/stage11c_recent_short_regime_diagnostic/stage11c_recent_short_regime_diagnostic.json

Hard rules:
- Research/diagnostic only.
- No EA change.
- No automatic trading.
- No demo/paper/live/order authorization.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Sequence

import pandas as pd


TOOL_VERSION = "v1"
DEFAULT_SUMMARY = Path("data/reports/stage11b_alternative_short_thesis_lab/stage11b_short_candidate_summary.csv")
DEFAULT_TRADES = Path("data/reports/stage11b_alternative_short_thesis_lab/stage11b_short_candidate_trades.csv")
DEFAULT_OUT_DIR = Path("data/reports/stage11c_recent_short_regime_diagnostic")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def dd(vals: Sequence[float]) -> float:
    eq = 0.0
    peak = 0.0
    maxdd = 0.0
    for v in vals:
        eq += float(v)
        peak = max(peak, eq)
        maxdd = min(maxdd, eq - peak)
    return round(maxdd, 6)


def pf(vals: Sequence[float]) -> float:
    vals = [float(v) for v in vals]
    wins = sum(v for v in vals if v > 0)
    losses = abs(sum(v for v in vals if v < 0))
    if losses == 0:
        return 999.0 if wins > 0 else 0.0
    return round(wins / losses, 6)


def summarize(vals: Sequence[float]) -> dict:
    vals = [float(v) for v in vals]
    if not vals:
        return {"trades": 0, "total_x4": 0.0, "pf_x4": 0.0, "median_x4": 0.0, "wr": 0.0, "dd_x4": 0.0}
    wins = [v for v in vals if v > 0]
    return {
        "trades": len(vals),
        "total_x4": round(sum(vals), 6),
        "pf_x4": pf(vals),
        "median_x4": round(float(pd.Series(vals).median()), 6),
        "wr": round(len(wins) / len(vals), 6),
        "dd_x4": dd(vals),
    }


def load_inputs(summary_path: Path, trades_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not summary_path.exists():
        raise FileNotFoundError(f"Missing Stage 11B summary CSV: {summary_path}")
    if not trades_path.exists():
        raise FileNotFoundError(f"Missing Stage 11B trades CSV: {trades_path}")
    s = pd.read_csv(summary_path)
    t = pd.read_csv(trades_path)
    if "entry_utc" not in t.columns or "net_x4" not in t.columns or "variant" not in t.columns:
        raise RuntimeError("Stage 11B trades CSV must contain entry_utc, net_x4, variant.")
    t["entry_dt"] = pd.to_datetime(t["entry_utc"], utc=True, errors="coerce")
    t["net_x4"] = pd.to_numeric(t["net_x4"], errors="coerce")
    t = t.dropna(subset=["entry_dt", "net_x4", "variant"])
    return s, t


def candidate_pool(summary: pd.DataFrame, top_n: int) -> pd.DataFrame:
    # Prioritize what looked tempting in Stage 11B: high test_total_x4 with adequate sample.
    s = summary.copy()
    for c in ["trades", "test_total_x4", "total_x4", "pf_x4", "median_x4", "dd_x4"]:
        if c in s.columns:
            s[c] = pd.to_numeric(s[c], errors="coerce")
    s = s[s["trades"] >= 40].copy()
    s = s.sort_values(["test_total_x4", "pf_x4", "total_x4"], ascending=[False, False, False])
    return s.head(top_n)


def period_breakdown(trades: pd.DataFrame, variant: str) -> pd.DataFrame:
    x = trades[trades["variant"] == variant].copy()
    if x.empty:
        return pd.DataFrame()
    x["year"] = x["entry_dt"].dt.year.astype(int)
    x["quarter"] = x["entry_dt"].dt.year.astype(str) + "Q" + x["entry_dt"].dt.quarter.astype(str)
    x["month"] = x["entry_dt"].dt.strftime("%Y-%m")

    rows = []
    for period_type, col in [("year", "year"), ("quarter", "quarter"), ("month", "month")]:
        for k, g in x.groupby(col):
            st = summarize(g.sort_values("entry_dt")["net_x4"].tolist())
            st.update({
                "variant": variant,
                "period_type": period_type,
                "period": str(k),
                "start_utc": g["entry_dt"].min().isoformat(),
                "end_utc": g["entry_dt"].max().isoformat(),
            })
            rows.append(st)
    return pd.DataFrame(rows)


def analyze_candidate(trades: pd.DataFrame, row: pd.Series) -> dict:
    variant = row["variant"]
    x = trades[trades["variant"] == variant].sort_values("entry_dt").copy()
    vals_all = x["net_x4"].tolist()
    all_s = summarize(vals_all)

    max_dt = x["entry_dt"].max()
    recent_12_start = max_dt - pd.Timedelta(days=365)
    recent_24_start = max_dt - pd.Timedelta(days=730)

    r12 = x[x["entry_dt"] >= recent_12_start]
    r24 = x[x["entry_dt"] >= recent_24_start]
    prior = x[x["entry_dt"] < recent_24_start]

    s12 = summarize(r12["net_x4"].tolist())
    s24 = summarize(r24["net_x4"].tolist())
    sprior = summarize(prior["net_x4"].tolist())

    # Diagnostic labels.
    if all_s["pf_x4"] >= 1.18 and all_s["median_x4"] >= -2.0 and all_s["dd_x4"] > -550 and all_s["trades"] >= 80:
        verdict = "ALL_HISTORY_RESEARCH_CANDIDATE"
    elif s24["trades"] >= 40 and s24["total_x4"] > 0 and s24["pf_x4"] >= 1.15 and all_s["pf_x4"] < 1.15:
        verdict = "RECENT_REGIME_WATCHLIST_ONLY"
    elif s12["trades"] >= 20 and s12["total_x4"] > 0 and s12["pf_x4"] >= 1.15 and all_s["pf_x4"] < 1.15:
        verdict = "SHORT_TERM_WATCHLIST_ONLY"
    else:
        verdict = "REJECT"

    return {
        "variant": variant,
        "definition": row.get("definition", ""),
        "stage11b_trades": int(row.get("trades", 0)),
        "stage11b_total_x4": float(row.get("total_x4", 0)),
        "stage11b_test_total_x4": float(row.get("test_total_x4", 0)),
        "stage11b_pf_x4": float(row.get("pf_x4", 0)),
        "stage11b_median_x4": float(row.get("median_x4", 0)),
        "stage11b_dd_x4": float(row.get("dd_x4", 0)),
        "all_trades": all_s["trades"],
        "all_total_x4": all_s["total_x4"],
        "all_pf_x4": all_s["pf_x4"],
        "all_median_x4": all_s["median_x4"],
        "all_wr": all_s["wr"],
        "all_dd_x4": all_s["dd_x4"],
        "recent_24m_trades": s24["trades"],
        "recent_24m_total_x4": s24["total_x4"],
        "recent_24m_pf_x4": s24["pf_x4"],
        "recent_24m_median_x4": s24["median_x4"],
        "recent_24m_dd_x4": s24["dd_x4"],
        "recent_12m_trades": s12["trades"],
        "recent_12m_total_x4": s12["total_x4"],
        "recent_12m_pf_x4": s12["pf_x4"],
        "recent_12m_median_x4": s12["median_x4"],
        "recent_12m_dd_x4": s12["dd_x4"],
        "prior_to_24m_trades": sprior["trades"],
        "prior_to_24m_total_x4": sprior["total_x4"],
        "prior_to_24m_pf_x4": sprior["pf_x4"],
        "verdict": verdict,
    }


def run(summary_path: Path, trades_path: Path, out_dir: Path, top_n: int) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = now_iso()

    summary, trades = load_inputs(summary_path, trades_path)
    pool = candidate_pool(summary, top_n)
    rows = []
    breakdowns = []

    for _, r in pool.iterrows():
        rows.append(analyze_candidate(trades, r))
        pb = period_breakdown(trades, r["variant"])
        if not pb.empty:
            breakdowns.append(pb)

    out = pd.DataFrame(rows)
    breakdown = pd.concat(breakdowns, ignore_index=True) if breakdowns else pd.DataFrame()

    if not out.empty:
        verdict_order = {
            "ALL_HISTORY_RESEARCH_CANDIDATE": 0,
            "RECENT_REGIME_WATCHLIST_ONLY": 1,
            "SHORT_TERM_WATCHLIST_ONLY": 2,
            "REJECT": 3,
        }
        out["_ord"] = out["verdict"].map(verdict_order).fillna(99)
        out = out.sort_values(["_ord", "recent_24m_total_x4", "all_pf_x4"], ascending=[True, False, False]).drop(columns=["_ord"])

    out_csv = out_dir / "stage11c_recent_candidate_summary.csv"
    breakdown_csv = out_dir / "stage11c_recent_candidate_period_breakdown.csv"
    out.to_csv(out_csv, index=False)
    breakdown.to_csv(breakdown_csv, index=False)

    verdict_counts = out["verdict"].value_counts().to_dict() if not out.empty else {}
    if verdict_counts.get("ALL_HISTORY_RESEARCH_CANDIDATE", 0) > 0:
        decision = "stage11d_research_candidate_found"
    elif verdict_counts.get("RECENT_REGIME_WATCHLIST_ONLY", 0) > 0 or verdict_counts.get("SHORT_TERM_WATCHLIST_ONLY", 0) > 0:
        decision = "recent_short_watchlist_only"
    else:
        decision = "kill_short_price_only_for_now"

    top = out.head(8).to_dict(orient="records") if not out.empty else []
    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "summary_path": str(summary_path),
        "trades_path": str(trades_path),
        "candidates_checked": int(len(out)),
        "decision": decision,
        "verdict_counts": verdict_counts,
        "top": top[:5],
    }
    (out_dir / "stage11c_recent_short_regime_diagnostic.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    lines = [
        "# Stage 11C Recent Short-Regime Diagnostic",
        "",
        f"Generated UTC: `{generated}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: diagnostic only. No EA change, no automatic trading, no paper/live authorization.",
        "",
        "## Inputs",
        f"- summary_csv: `{summary_path}`",
        f"- trades_csv: `{trades_path}`",
        f"- candidates_checked: `{len(out)}`",
        "",
        "## Decision",
        f"- decision: `{decision}`",
        "",
        "## Verdict counts",
        "| Verdict | Candidates |",
        "|---|---:|",
    ]
    if verdict_counts:
        for k, v in verdict_counts.items():
            lines.append(f"| {k} | {v} |")
    else:
        lines.append("| none | 0 |")

    lines += [
        "",
        "## Top diagnostic candidates",
        "| Rank | Verdict | Definition | Trades | All total | All PF | All median | All DD | Recent24m trades | Recent24m total | Recent24m PF | Prior total |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    if top:
        for i, r in enumerate(top, start=1):
            lines.append(
                f"| {i} | {r['verdict']} | {r['definition']} | {r['all_trades']} | "
                f"{r['all_total_x4']} | {r['all_pf_x4']} | {r['all_median_x4']} | {r['all_dd_x4']} | "
                f"{r['recent_24m_trades']} | {r['recent_24m_total_x4']} | {r['recent_24m_pf_x4']} | {r['prior_to_24m_total_x4']} |"
            )
    else:
        lines.append("| 0 | none | none | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |")

    lines += [
        "",
        "## Interpretation",
        "- `ALL_HISTORY_RESEARCH_CANDIDATE` may move to strict robustness research only.",
        "- `RECENT_REGIME_WATCHLIST_ONLY` must not become an EA rule; it can be monitored in forward-shadow reports.",
        "- `REJECT` means no short-side mechanical candidate from this thesis family.",
        "- If only recent-watchlist appears, do not run full-grid on MacBook; collect forward evidence instead.",
        "",
        "## Outputs",
        f"- candidate_summary_csv: `{out_csv}`",
        f"- period_breakdown_csv: `{breakdown_csv}`",
        f"- json: `{out_dir / 'stage11c_recent_short_regime_diagnostic.json'}`",
    ]
    (out_dir / "stage11c_recent_short_regime_diagnostic.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 11C recent short-regime diagnostic: DONE")
    print(f"decision={decision} candidates_checked={len(out)} verdict_counts={verdict_counts}")
    print(f"Report: {out_dir / 'stage11c_recent_short_regime_diagnostic.md'}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    p.add_argument("--trades", default=str(DEFAULT_TRADES))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--top-n", type=int, default=20)
    args = p.parse_args()
    return run(Path(args.summary), Path(args.trades), Path(args.out_dir), args.top_n)


if __name__ == "__main__":
    raise SystemExit(main())
