#!/usr/bin/env python3
"""
Stage 15D — Macro Context Robustness for Stage 15C Top Context

Top Stage 15C context:
- macro_daily_regime_real_yield_10y_chg5_up

Purpose:
- Validate whether the top macro/fundamental context is robust or merely a
  retrospective attribution artifact.
- Compare the selected direction with the opposite direction.
- Check split/year/2022/2026/sample fragility.
- Clarify the economic interpretation: real-yield-up is counterintuitive as a
  gold-supportive filter, so it may be a pressure/reversal context rather than
  a bullish macro regime.

Hard rules:
- Research validation only.
- No EA change.
- No automatic trading.
- No paper/live/order authorization.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import pandas as pd


TOOL_VERSION = "v1"
DEFAULT_ENRICHED = Path("data/reports/stage15c_macro_conditioned_replay_attribution/stage15c_trades_with_macro_context.csv")
DEFAULT_CONTEXT = Path("data/reports/stage15c_macro_conditioned_replay_attribution/stage15c_context_summary.csv")
DEFAULT_OUT_DIR = Path("data/reports/stage15d_macro_context_robustness")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_col(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).strip().lower()).strip("_")


def profit_factor(vals: Sequence[float]) -> float:
    vals = [float(v) for v in vals]
    wins = sum(v for v in vals if v > 0)
    losses = abs(sum(v for v in vals if v < 0))
    if losses == 0:
        return 999.0 if wins > 0 else 0.0
    return round(wins / losses, 6)


def max_dd(vals: Sequence[float]) -> float:
    eq = peak = 0.0
    dd = 0.0
    for v in vals:
        eq += float(v)
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return round(dd, 6)


def metrics(df: pd.DataFrame, ret_col: str = "net_ret") -> Dict:
    if df.empty or ret_col not in df.columns:
        return {
            "events": 0, "total": 0.0, "avg": 0.0, "median": 0.0,
            "win_rate": 0.0, "pf": 0.0, "max_dd": 0.0,
            "pos_years": 0, "years": 0, "pos_quarters": 0, "quarters": 0,
        }
    x = df.sort_values("entry_dt").copy()
    vals = pd.to_numeric(x[ret_col], errors="coerce").dropna().astype(float).tolist()
    if not vals:
        return {
            "events": 0, "total": 0.0, "avg": 0.0, "median": 0.0,
            "win_rate": 0.0, "pf": 0.0, "max_dd": 0.0,
            "pos_years": 0, "years": 0, "pos_quarters": 0, "quarters": 0,
        }
    s = pd.Series(vals)
    by_year = x.groupby(x["entry_dt"].dt.year)[ret_col].sum()
    by_quarter = x.groupby(x["entry_dt"].dt.to_period("Q").astype(str))[ret_col].sum()
    return {
        "events": int(len(vals)),
        "total": round(float(s.sum()), 6),
        "avg": round(float(s.mean()), 6),
        "median": round(float(s.median()), 6),
        "win_rate": round(float((s > 0).mean()), 6),
        "pf": profit_factor(vals),
        "max_dd": max_dd(vals),
        "pos_years": int((by_year > 0).sum()),
        "years": int(len(by_year)),
        "pos_quarters": int((by_quarter > 0).sum()),
        "quarters": int(len(by_quarter)),
    }


def period_metrics(df: pd.DataFrame, ret_col: str, period: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    x = df.copy()
    if period == "year":
        x["period"] = x["entry_dt"].dt.year.astype(str)
    elif period == "quarter":
        x["period"] = x["entry_dt"].dt.to_period("Q").astype(str)
    elif period == "month":
        x["period"] = x["entry_dt"].dt.to_period("M").astype(str)
    else:
        raise ValueError(period)
    rows = []
    for p, g in x.groupby("period"):
        row = {"period": p}
        row.update(metrics(g, ret_col))
        rows.append(row)
    return pd.DataFrame(rows).sort_values("period") if rows else pd.DataFrame()


def split_metrics(df: pd.DataFrame, ret_col: str, frac: float) -> Dict:
    x = df.sort_values("entry_dt").reset_index(drop=True)
    cut = int(len(x) * frac)
    return {
        "train_frac": float(frac),
        "train": metrics(x.iloc[:cut], ret_col),
        "test": metrics(x.iloc[cut:], ret_col),
    }


def bootstrap(df: pd.DataFrame, ret_col: str, n: int = 500, seed: int = 150) -> Dict:
    if df.empty:
        return {}
    x = df.sort_values("entry_dt").reset_index(drop=True)
    totals, pfs, meds = [], [], []
    for i in range(n):
        s = x.sample(n=len(x), replace=True, random_state=seed + i)
        vals = pd.to_numeric(s[ret_col], errors="coerce").dropna().astype(float).tolist()
        totals.append(sum(vals))
        pfs.append(profit_factor(vals))
        meds.append(float(pd.Series(vals).median()) if vals else 0.0)
    ts, ps, ms = pd.Series(totals), pd.Series(pfs), pd.Series(meds)
    return {
        "n": int(n),
        "total_p05": round(float(ts.quantile(0.05)), 6),
        "total_p50": round(float(ts.quantile(0.50)), 6),
        "total_p95": round(float(ts.quantile(0.95)), 6),
        "pf_p05": round(float(ps.quantile(0.05)), 6),
        "pf_p50": round(float(ps.quantile(0.50)), 6),
        "median_p05": round(float(ms.quantile(0.05)), 6),
        "median_p50": round(float(ms.quantile(0.50)), 6),
        "prob_total_gt_0": round(float((ts > 0).mean()), 6),
        "prob_pf_gt_1": round(float((ps > 1).mean()), 6),
        "prob_median_gt_0": round(float((ms > 0).mean()), 6),
    }


def load_trades(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Stage15C enriched CSV not found: {path}")
    x = pd.read_csv(path)
    if "entry_utc" not in x.columns:
        raise RuntimeError("Enriched CSV must include entry_utc.")
    x["entry_dt"] = pd.to_datetime(x["entry_utc"], utc=True, errors="coerce")
    if "net_ret" not in x.columns:
        if "time_exit_net_x1" in x.columns:
            x["net_ret"] = pd.to_numeric(x["time_exit_net_x1"], errors="coerce")
        else:
            raise RuntimeError("Enriched CSV must include net_ret or time_exit_net_x1.")
    else:
        x["net_ret"] = pd.to_numeric(x["net_ret"], errors="coerce")
    x = x.dropna(subset=["entry_dt", "net_ret"]).sort_values("entry_dt").reset_index(drop=True)
    return x


def load_top_context(context_path: Path, default_context: str) -> str:
    if not context_path.exists():
        return default_context
    try:
        x = pd.read_csv(context_path)
    except Exception:
        return default_context
    if x.empty or "context" not in x.columns:
        return default_context
    if "candidate_flag" in x.columns:
        c = x[x["candidate_flag"].astype(str).str.lower().isin(["true", "1"])]
        if not c.empty:
            return str(c.iloc[0]["context"])
    return str(x.iloc[0]["context"])


def context_to_column_and_direction(context: str, trades: pd.DataFrame) -> Tuple[str, str]:
    """
    Converts e.g. macro_daily_regime_real_yield_10y_chg5_up
    to column macro_daily_regime_real_yield_10y__chg5, direction up.
    """
    ctx = str(context)
    direction = None
    if ctx.endswith("_up"):
        direction = "up"
        base = ctx[:-3]
    elif ctx.endswith("_down"):
        direction = "down"
        base = ctx[:-5]
    else:
        raise RuntimeError(f"Cannot infer direction from context: {context}")

    if base.endswith("_chg5"):
        prefix = base[:-5]
        possible = [
            f"{prefix}__chg5",
            f"{prefix}_chg5",
            f"{prefix}__chg_5",
            f"{prefix}_chg_5",
        ]
    elif "_chg5" in base:
        prefix = base.replace("_chg5", "")
        possible = [f"{prefix}__chg5", f"{prefix}_chg5"]
    else:
        possible = [base]

    cols_norm = {normalize_col(c): c for c in trades.columns}
    for p in possible:
        if normalize_col(p) in cols_norm:
            return cols_norm[normalize_col(p)], direction

    # fallback: contains all pieces
    pieces = [p for p in normalize_col(base).split("_") if p]
    for c in trades.columns:
        nc = normalize_col(c)
        if all(p in nc for p in pieces) and ("chg5" in nc or "chg_5" in nc):
            return c, direction

    raise RuntimeError(f"Could not find a data column for context={context}. Tried: {possible}")


def make_masks(trades: pd.DataFrame, column: str, direction: str) -> Dict[str, pd.Series]:
    v = pd.to_numeric(trades[column], errors="coerce")
    q25 = v.dropna().quantile(0.25) if v.notna().any() else 0.0
    q50 = v.dropna().quantile(0.50) if v.notna().any() else 0.0
    q75 = v.dropna().quantile(0.75) if v.notna().any() else 0.0

    if direction == "up":
        selected = v > 0
        opposite = v < 0
        stronger = v >= q75
        moderate = (v > 0) & (v < q75)
    else:
        selected = v < 0
        opposite = v > 0
        stronger = v <= q25
        moderate = (v < 0) & (v > q25)

    return {
        "selected_direction": selected.fillna(False),
        "opposite_direction": opposite.fillna(False),
        "non_missing": v.notna(),
        "stronger_direction_tail": stronger.fillna(False),
        "moderate_direction": moderate.fillna(False),
        "missing": v.isna(),
    }


def compare_masks(trades: pd.DataFrame, masks: Dict[str, pd.Series]) -> pd.DataFrame:
    rows = []
    base = metrics(trades, "net_ret")
    for name, mask in masks.items():
        sub = trades[mask].copy()
        comp = trades[~mask].copy()
        m = metrics(sub, "net_ret")
        c = metrics(comp, "net_ret")
        sp70 = split_metrics(sub, "net_ret", 0.70) if len(sub) else {"test": metrics(pd.DataFrame(), "net_ret")}
        rows.append({
            "bucket": name,
            "events": m["events"],
            "coverage": round(m["events"] / max(1, len(trades)), 6),
            "total": m["total"],
            "avg": m["avg"],
            "median": m["median"],
            "wr": m["win_rate"],
            "pf": m["pf"],
            "dd": m["max_dd"],
            "pos_years": m["pos_years"],
            "years": m["years"],
            "pos_quarters": m["pos_quarters"],
            "quarters": m["quarters"],
            "test_events": sp70["test"]["events"],
            "test_total": sp70["test"]["total"],
            "test_pf": sp70["test"]["pf"],
            "complement_total": c["total"],
            "complement_pf": c["pf"],
            "delta_pf_vs_base": round(m["pf"] - base["pf"], 6),
            "delta_median_vs_base": round(m["median"] - base["median"], 6),
        })
    return pd.DataFrame(rows).sort_values(["pf", "median", "events"], ascending=[False, False, False])


def decide(base: Dict, selected: Dict, opposite: Dict, splits: List[Dict], year: pd.DataFrame, boot: Dict, context: str, direction: str) -> Tuple[str, List[str]]:
    reasons: List[str] = []
    if selected["events"] < 40:
        return "MACRO_CONTEXT_SAMPLE_TOO_SMALL", ["Selected macro context has fewer than 40 events."]

    if not (selected["total"] > 0 and selected["pf"] >= max(1.35, base["pf"] * 1.05) and selected["median"] >= base["median"] and selected["win_rate"] >= 0.58):
        return "MACRO_CONTEXT_NOT_ROBUST", ["Selected macro context does not improve enough over the Stage15B baseline."]

    if opposite["events"] >= 20 and opposite["pf"] >= selected["pf"]:
        return "MACRO_CONTEXT_DIRECTION_NOT_DISTINCT", ["Opposite macro direction is not worse than selected direction."]

    for sp in splits:
        test = sp["test"]
        if not (test["events"] >= 8 and test["total"] > 0 and test["pf"] >= 1.05):
            return "MACRO_CONTEXT_SPLIT_FRAGILE", [f"Split {sp['train_frac']} test segment fails."]

    if not year.empty:
        pos_years = int((year["total"] > 0).sum())
        years = int(len(year))
        if years >= 4 and pos_years < max(3, round(years * 0.60)):
            return "MACRO_CONTEXT_YEAR_FRAGILE", ["Year distribution remains too concentrated."]

    if boot and (boot.get("prob_total_gt_0", 0) < 0.90 or boot.get("pf_p05", 0) < 1.0):
        return "MACRO_CONTEXT_BOOTSTRAP_FRAGILE", ["Bootstrap lower tail is not strong enough."]

    counterintuitive = ("real_yield" in context or "yield" in context) and direction == "up"
    if counterintuitive:
        reasons.append("Selected macro direction is counterintuitive for gold-supportive macro logic; interpret as pressure/reversal context, not bullish macro support.")
        reasons.append("Allowed next step is forward-shadow research with this context logged, not automatic trading.")
        return "MACRO_CONTEXT_ROBUST_BUT_COUNTERINTUITIVE", reasons

    reasons.append("Selected macro context is robust enough for one forward-shadow research design step. Still no order authorization.")
    return "MACRO_CONTEXT_ROBUST_FOR_FORWARD_SHADOW_RESEARCH", reasons


def run(enriched_path: Path, context_path: Path, out_dir: Path, top_context: str, bootstrap_n: int) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = now_iso()

    trades = load_trades(enriched_path)
    if top_context.lower() == "auto":
        top_context = load_top_context(context_path, "macro_daily_regime_real_yield_10y_chg5_up")

    col, direction = context_to_column_and_direction(top_context, trades)
    masks = make_masks(trades, col, direction)
    bucket_summary = compare_masks(trades, masks)

    selected_df = trades[masks["selected_direction"]].copy()
    opposite_df = trades[masks["opposite_direction"]].copy()
    base_m = metrics(trades, "net_ret")
    selected_m = metrics(selected_df, "net_ret")
    opposite_m = metrics(opposite_df, "net_ret")

    splits = [
        split_metrics(selected_df, "net_ret", 0.60),
        split_metrics(selected_df, "net_ret", 0.70),
        split_metrics(selected_df, "net_ret", 0.80),
    ]
    year = period_metrics(selected_df, "net_ret", "year")
    quarter = period_metrics(selected_df, "net_ret", "quarter")
    month = period_metrics(selected_df, "net_ret", "month")
    boot = bootstrap(selected_df, "net_ret", bootstrap_n)

    final_decision, reasons = decide(base_m, selected_m, opposite_m, splits, year, boot, top_context, direction)

    selected_csv = out_dir / "stage15d_selected_context_trades.csv"
    opposite_csv = out_dir / "stage15d_opposite_context_trades.csv"
    bucket_csv = out_dir / "stage15d_context_bucket_summary.csv"
    year_csv = out_dir / "stage15d_selected_by_year.csv"
    quarter_csv = out_dir / "stage15d_selected_by_quarter.csv"
    month_csv = out_dir / "stage15d_selected_by_month.csv"
    split_csv = out_dir / "stage15d_selected_splits.csv"
    json_path = out_dir / "stage15d_macro_context_robustness.json"
    md_path = out_dir / "stage15d_macro_context_robustness.md"

    selected_df.to_csv(selected_csv, index=False)
    opposite_df.to_csv(opposite_csv, index=False)
    bucket_summary.to_csv(bucket_csv, index=False)
    year.to_csv(year_csv, index=False)
    quarter.to_csv(quarter_csv, index=False)
    month.to_csv(month_csv, index=False)

    split_rows = []
    for sp in splits:
        for seg in ["train", "test"]:
            row = {"train_frac": sp["train_frac"], "segment": seg}
            row.update(sp[seg])
            split_rows.append(row)
    split_df = pd.DataFrame(split_rows)
    split_df.to_csv(split_csv, index=False)

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "inputs": {
            "enriched_path": str(enriched_path),
            "context_path": str(context_path),
            "top_context": top_context,
            "context_column": col,
            "direction": direction,
            "bootstrap_n": int(bootstrap_n),
        },
        "final_decision": final_decision,
        "reasons": reasons,
        "baseline": base_m,
        "selected_direction": selected_m,
        "opposite_direction": opposite_m,
        "splits": splits,
        "bootstrap": boot,
        "bucket_summary": bucket_summary.to_dict(orient="records"),
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
        "# Stage 15D Macro Context Robustness",
        "",
        f"Generated UTC: `{generated}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: macro context robustness only. No EA change, no automatic trading, no paper/live authorization.",
        "",
        "## Context under validation",
        f"- top_context: `{top_context}`",
        f"- context_column: `{col}`",
        f"- selected_direction: `{direction}`",
        "",
        "## Final decision",
        f"- final_decision: `{final_decision}`",
        "",
        "## Reasons",
    ]
    for r in reasons:
        lines.append(f"- {r}")

    lines += [
        "",
        "## Baseline vs selected/opposite direction",
        "| Set | Events | Total | Avg | Median | WR | PF | DD | Pos years | Pos quarters |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        f"| baseline_all_stage15b | {base_m['events']} | {base_m['total']} | {base_m['avg']} | {base_m['median']} | {base_m['win_rate']} | {base_m['pf']} | {base_m['max_dd']} | {base_m['pos_years']}/{base_m['years']} | {base_m['pos_quarters']}/{base_m['quarters']} |",
        f"| selected_direction | {selected_m['events']} | {selected_m['total']} | {selected_m['avg']} | {selected_m['median']} | {selected_m['win_rate']} | {selected_m['pf']} | {selected_m['max_dd']} | {selected_m['pos_years']}/{selected_m['years']} | {selected_m['pos_quarters']}/{selected_m['quarters']} |",
        f"| opposite_direction | {opposite_m['events']} | {opposite_m['total']} | {opposite_m['avg']} | {opposite_m['median']} | {opposite_m['win_rate']} | {opposite_m['pf']} | {opposite_m['max_dd']} | {opposite_m['pos_years']}/{opposite_m['years']} | {opposite_m['pos_quarters']}/{opposite_m['quarters']} |",
        "",
        "## Context buckets",
        "| Bucket | Events | Coverage | Total | Median | WR | PF | DD | Test total | Test PF |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in bucket_summary.to_dict(orient="records"):
        lines.append(
            f"| {r['bucket']} | {r['events']} | {r['coverage']} | {r['total']} | {r['median']} | {r['wr']} | {r['pf']} | {r['dd']} | {r['test_total']} | {r['test_pf']} |"
        )

    lines += [
        "",
        "## Chronological splits - selected direction",
        "| Train frac | Segment | Events | Total | Avg | Median | WR | PF | DD |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in split_df.to_dict(orient="records"):
        lines.append(
            f"| {r['train_frac']} | {r['segment']} | {r['events']} | {r['total']} | {r['avg']} | {r['median']} | {r['win_rate']} | {r['pf']} | {r['max_dd']} |"
        )

    lines += [
        "",
        "## Year distribution - selected direction",
        "| Year | Events | Total | Avg | Median | WR | PF | DD |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in year.to_dict(orient="records"):
        lines.append(
            f"| {r['period']} | {r['events']} | {r['total']} | {r['avg']} | {r['median']} | {r['win_rate']} | {r['pf']} | {r['max_dd']} |"
        )

    lines += [
        "",
        "## Bootstrap - selected direction",
        "```json",
        json.dumps(boot, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Interpretation",
        "- `MACRO_CONTEXT_ROBUST_BUT_COUNTERINTUITIVE` means the context is statistically useful but should be interpreted as pressure/reversal, not bullish macro support.",
        "- `MACRO_CONTEXT_ROBUST_FOR_FORWARD_SHADOW_RESEARCH` permits only research-forward-shadow design.",
        "- Any failure rejects this macro context; it does not reject XAUUSD as a market.",
        "- No EA/paper/live/order authorization is granted.",
        "",
        "## Output files",
        f"- selected_csv: `{selected_csv}`",
        f"- opposite_csv: `{opposite_csv}`",
        f"- bucket_csv: `{bucket_csv}`",
        f"- year_csv: `{year_csv}`",
        f"- quarter_csv: `{quarter_csv}`",
        f"- month_csv: `{month_csv}`",
        f"- split_csv: `{split_csv}`",
        f"- json: `{json_path}`",
        f"- md: `{md_path}`",
    ]

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 15D macro context robustness: DONE")
    print(f"final_decision={final_decision}")
    print(f"context={top_context} column={col} direction={direction}")
    print(f"selected_events={selected_m['events']} selected_pf={selected_m['pf']} selected_median={selected_m['median']}")
    print(f"opposite_events={opposite_m['events']} opposite_pf={opposite_m['pf']} opposite_median={opposite_m['median']}")
    print(f"Report: {md_path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--enriched", default=str(DEFAULT_ENRICHED))
    p.add_argument("--context", default=str(DEFAULT_CONTEXT))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--top-context", default="auto")
    p.add_argument("--bootstrap-n", type=int, default=500)
    args = p.parse_args()
    return run(
        enriched_path=Path(args.enriched),
        context_path=Path(args.context),
        out_dir=Path(args.out_dir),
        top_context=str(args.top_context),
        bootstrap_n=int(args.bootstrap_n),
    )


if __name__ == "__main__":
    raise SystemExit(main())
