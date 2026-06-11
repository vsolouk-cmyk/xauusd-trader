"""
Stage 23C — locked validation for Stage23B promotion-review candidates.

Research-only module. It does NOT modify Stage18A, does NOT authorize paper/live,
and does NOT create orders.

Purpose:
- Validate the strong Stage23B london_oneway_continuation candidates without running a broad grid.
- Detect duplicate/near-duplicate parameter variants.
- Stress-test exact M1 replay by cost, year, direction, exit reason, and chronological splits.
- Produce a promotion-review validation report only; no operational promotion is performed.

Run:
    cd ~/Desktop/xauusd-trader
    python3 -m app.stage23c_promotion_candidate_validation
    cat data/reports/stage23c_promotion_candidate_validation/stage23c_promotion_candidate_validation.md
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd

try:
    from app.stage23b_continuation_no_trade_discovery import (
        Candidate,
        ROUNDTRIP_COST_USD,
        add_atr,
        events_london_oneway_continuation,
        load_market_data,
        merge_atr,
        replay_events,
        profit_factor,
    )
except Exception as exc:  # pragma: no cover - user-facing guard
    raise RuntimeError(
        "Stage23C depends on app.stage23b_continuation_no_trade_discovery. "
        "Apply/run the Stage23B patch first. Original import error: " + str(exc)
    )


STAGE_NAME = "stage23c_promotion_candidate_validation"
REPORT_DIR = Path("data/reports") / STAGE_NAME
RANDOM_SEED = 2303
BOOTSTRAP_ITERS = 300

# Locked candidates from Stage23B report. No broad search and no new family discovery here.
LOCKED_CANDIDATES: List[Candidate] = [
    Candidate(
        "london_oneway_continuation",
        "S23B_A_pb0.1_eff0.72_h180_tp0.6_sl0.65",
        {
            "london_move_atr_min": 0.9,
            "eff_min": 0.72,
            "pullback_atr_max": 0.10,
            "ny_confirm_atr_min": 0.15,
            "entry_hour": 13,
            "horizon_min": 180,
            "tp_atr": 0.60,
            "sl_atr": 0.65,
        },
    ),
    Candidate(
        "london_oneway_continuation",
        "S23B_A_dup_pb0.3_eff0.72_h180_tp0.6_sl0.65",
        {
            "london_move_atr_min": 0.9,
            "eff_min": 0.72,
            "pullback_atr_max": 0.30,
            "ny_confirm_atr_min": 0.15,
            "entry_hour": 13,
            "horizon_min": 180,
            "tp_atr": 0.60,
            "sl_atr": 0.65,
        },
    ),
    Candidate(
        "london_oneway_continuation",
        "S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65",
        {
            "london_move_atr_min": 0.9,
            "eff_min": 0.60,
            "pullback_atr_max": 0.10,
            "ny_confirm_atr_min": 0.15,
            "entry_hour": 13,
            "horizon_min": 180,
            "tp_atr": 0.60,
            "sl_atr": 0.65,
        },
    ),
    Candidate(
        "london_oneway_continuation",
        "S23B_B_dup_pb0.3_eff0.60_h180_tp0.6_sl0.65",
        {
            "london_move_atr_min": 0.9,
            "eff_min": 0.60,
            "pullback_atr_max": 0.30,
            "ny_confirm_atr_min": 0.15,
            "entry_hour": 13,
            "horizon_min": 180,
            "tp_atr": 0.60,
            "sl_atr": 0.65,
        },
    ),
    # Horizon sensitivity checks. These were strong in M15 proxy but not part of the Stage23B exact top four.
    Candidate(
        "london_oneway_continuation",
        "S23B_A_h90_sensitivity_eff0.72_tp0.6_sl0.65",
        {
            "london_move_atr_min": 0.9,
            "eff_min": 0.72,
            "pullback_atr_max": 0.10,
            "ny_confirm_atr_min": 0.15,
            "entry_hour": 13,
            "horizon_min": 90,
            "tp_atr": 0.60,
            "sl_atr": 0.65,
        },
    ),
    Candidate(
        "london_oneway_continuation",
        "S23B_B_h90_sensitivity_eff0.60_tp0.6_sl0.65",
        {
            "london_move_atr_min": 0.9,
            "eff_min": 0.60,
            "pullback_atr_max": 0.10,
            "ny_confirm_atr_min": 0.15,
            "entry_hour": 13,
            "horizon_min": 90,
            "tp_atr": 0.60,
            "sl_atr": 0.65,
        },
    ),
]


COST_MULTIPLIERS = [1, 2, 4, 6, 8]


def _finite_for_json(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _finite_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_finite_for_json(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        if math.isinf(float(obj)):
            return "inf"
        if math.isnan(float(obj)):
            return None
        return float(obj)
    if isinstance(obj, pd.Timestamp):
        return str(obj)
    return obj


def _bootstrap_pf_p05(values: Sequence[float], n_iter: int = BOOTSTRAP_ITERS) -> float:
    vals = np.asarray(list(values), dtype=float)
    if vals.size < 20:
        return 0.0
    rng = np.random.default_rng(RANDOM_SEED)
    pfs = []
    for _ in range(n_iter):
        sample = rng.choice(vals, size=vals.size, replace=True)
        pfs.append(profit_factor(sample))
    finite = np.asarray([x for x in pfs if np.isfinite(x)], dtype=float)
    if finite.size == 0:
        return float("inf")
    return float(np.percentile(finite, 5))


def _trade_dataframe(trades: list[Any], candidate_name: str) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame()
    df = pd.DataFrame([asdict(t) for t in trades])
    df["candidate"] = candidate_name
    df["entry_time_dt"] = pd.to_datetime(df["entry_time"], errors="coerce")
    df["year"] = df["entry_time_dt"].dt.year
    df["month"] = df["entry_time_dt"].dt.to_period("M").astype(str)
    # Reconstruct gross from the replay output and compute additional stress costs.
    for mult in COST_MULTIPLIERS:
        df[f"net_x{mult}"] = df["gross"].astype(float) - float(mult) * ROUNDTRIP_COST_USD
    return df.sort_values("entry_time_dt").reset_index(drop=True)


def _summary_for_values(values: Sequence[float]) -> Dict[str, Any]:
    vals = np.asarray(list(values), dtype=float)
    if vals.size == 0:
        return {"events": 0, "pf": 0.0, "total": 0.0, "median": 0.0, "win_rate": 0.0, "loss_count": 0}
    return {
        "events": int(vals.size),
        "pf": round(profit_factor(vals), 4),
        "total": round(float(vals.sum()), 4),
        "median": round(float(np.median(vals)), 4),
        "win_rate": round(float((vals > 0).mean()), 4),
        "loss_count": int((vals < 0).sum()),
    }


def summarize_candidate(df: pd.DataFrame, cand: Candidate) -> Dict[str, Any]:
    if df.empty:
        return {"candidate": cand.name, "events": 0, "decision": "STAGE23C_REJECT_EMPTY"}

    n = len(df)
    split80 = max(1, int(math.floor(n * 0.8)))
    test20 = df.iloc[split80:] if split80 < n else df.iloc[-max(1, n // 5) :]
    first_half = df.iloc[: max(1, n // 2)]
    second_half = df.iloc[max(1, n // 2) :]
    by_year = df.groupby("year", dropna=True)["net_x4"].agg(lambda s: profit_factor(s)).to_dict()
    years_with_trades = sorted(int(y) for y in df["year"].dropna().unique())
    years_pf_positive = sum(1 for y, pf in by_year.items() if pf >= 1.0)
    y2026 = df[df["year"] == 2026]
    y2026_s = _summary_for_values(y2026["net_x4"])
    long_s = _summary_for_values(df[df["direction"] == "long"]["net_x4"])
    short_s = _summary_for_values(df[df["direction"] == "short"]["net_x4"])

    row: Dict[str, Any] = {
        "candidate": cand.name,
        "family": cand.family,
        "events": int(n),
        "first_entry": str(df["entry_time_dt"].min()),
        "last_entry": str(df["entry_time_dt"].max()),
        "years_with_trades": ",".join(map(str, years_with_trades)),
        "years_pf_positive_x4": int(years_pf_positive),
        "valid_year_count": int(len(years_with_trades)),
        "pf_x1": round(profit_factor(df["net_x1"]), 4),
        "pf_x2": round(profit_factor(df["net_x2"]), 4),
        "pf_x4": round(profit_factor(df["net_x4"]), 4),
        "pf_x6": round(profit_factor(df["net_x6"]), 4),
        "pf_x8": round(profit_factor(df["net_x8"]), 4),
        "total_x1": round(float(df["net_x1"].sum()), 4),
        "total_x4": round(float(df["net_x4"].sum()), 4),
        "median_x1": round(float(df["net_x1"].median()), 4),
        "median_x4": round(float(df["net_x4"].median()), 4),
        "win_rate_x4": round(float((df["net_x4"] > 0).mean()), 4),
        "boot_pf_p05_x1": round(_bootstrap_pf_p05(df["net_x1"]), 4),
        "boot_pf_p05_x4": round(_bootstrap_pf_p05(df["net_x4"]), 4),
        "test20_pf_x1": round(profit_factor(test20["net_x1"]), 4),
        "test20_pf_x4": round(profit_factor(test20["net_x4"]), 4),
        "first_half_pf_x4": round(profit_factor(first_half["net_x4"]), 4),
        "second_half_pf_x4": round(profit_factor(second_half["net_x4"]), 4),
        "pf_2026_x4": y2026_s["pf"] if int(y2026_s["events"]) > 0 else None,
        "events_2026": int(y2026_s["events"]),
        "loss_count_2026_x4": int(y2026_s["loss_count"]),
        "long_events": int(long_s["events"]),
        "long_pf_x4": long_s["pf"],
        "short_events": int(short_s["events"]),
        "short_pf_x4": short_s["pf"],
        "exit_tp_count": int((df["exit_reason"] == "tp").sum()),
        "exit_sl_count": int(df["exit_reason"].astype(str).str.contains("sl", case=False, na=False).sum()),
        "exit_horizon_count": int((df["exit_reason"] == "horizon_close").sum()),
        "is_inf_2026_warning": bool(int(y2026_s["events"]) > 0 and int(y2026_s["loss_count"]) == 0),
    }

    # Conservative decision. This is still research-only and is not a Stage18A promotion.
    core_ok = (
        row["events"] >= 50
        and row["pf_x4"] >= 1.35
        and row["pf_x6"] >= 1.05
        and row["boot_pf_p05_x4"] >= 1.0
        and row["test20_pf_x4"] >= 1.0
        and row["median_x4"] > 0
    )
    year_ok = row["valid_year_count"] >= 4 and row["years_pf_positive_x4"] >= max(3, row["valid_year_count"] - 1)
    direction_ok = not (
        (row["long_events"] >= 20 and row["long_pf_x4"] < 0.9)
        or (row["short_events"] >= 20 and row["short_pf_x4"] < 0.9)
    )
    if core_ok and year_ok and direction_ok:
        row["decision"] = "STAGE23C_VALIDATED_PROMOTION_REVIEW_ONLY"
    elif row["events"] >= 35 and row["pf_x4"] >= 1.05 and row["boot_pf_p05_x4"] >= 0.85:
        row["decision"] = "STAGE23C_KEEP_WATCHLIST_ONLY"
    else:
        row["decision"] = "STAGE23C_REJECT"
    return row


def make_split_rows(df: pd.DataFrame, cand_name: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if df.empty:
        return rows
    for key, g in df.groupby("year", dropna=True):
        s = _summary_for_values(g["net_x4"])
        rows.append({"candidate": cand_name, "split_type": "year", "split": str(int(key)), **s})
    for key, g in df.groupby("direction", dropna=True):
        s = _summary_for_values(g["net_x4"])
        rows.append({"candidate": cand_name, "split_type": "direction", "split": str(key), **s})
    for key, g in df.groupby("exit_reason", dropna=True):
        s = _summary_for_values(g["net_x4"])
        rows.append({"candidate": cand_name, "split_type": "exit_reason", "split": str(key), **s})
    return rows


def _event_signature(events: pd.DataFrame) -> str:
    if events.empty:
        return "EMPTY"
    cols = ["signal_time", "direction"]
    x = events[cols].copy().sort_values(cols).reset_index(drop=True)
    return str(pd.util.hash_pandas_object(x, index=False).sum()) + f":{len(x)}"


def detect_duplicates(event_signatures: Dict[str, str]) -> List[Dict[str, Any]]:
    inv: Dict[str, List[str]] = {}
    for name, sig in event_signatures.items():
        inv.setdefault(sig, []).append(name)
    return [
        {"event_signature": sig, "candidate_count": len(names), "candidates": names}
        for sig, names in inv.items()
        if len(names) > 1
    ]


def markdown_table(df: pd.DataFrame, cols: List[str], n: int = 20) -> str:
    if df.empty:
        return ""
    show = df[cols].head(n).copy()

    def fmt(v: Any) -> str:
        # Some diagnostic columns intentionally contain lists, e.g. duplicate candidate names.
        # pandas.isna(list/array) returns an array of booleans and raises
        # "truth value of an array is ambiguous" when used in an if.
        if isinstance(v, (list, tuple, set)):
            text = ", ".join(str(x) for x in v)
            return text.replace("|", "/")
        if hasattr(v, "tolist") and not isinstance(v, (str, bytes)):
            try:
                converted = v.tolist()
                if isinstance(converted, list):
                    text = ", ".join(str(x) for x in converted)
                    return text.replace("|", "/")
            except Exception:
                pass
        if isinstance(v, dict):
            text = json.dumps(v, ensure_ascii=False, sort_keys=True)
            return text.replace("|", "/")
        try:
            if pd.isna(v):
                return ""
        except (TypeError, ValueError):
            pass
        if isinstance(v, float):
            if math.isinf(v):
                return "inf"
            return f"{v:.4f}".rstrip("0").rstrip(".")
        text = str(v)
        return text.replace("|", "/")

    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    rows = ["| " + " | ".join(fmt(row[c]) for c in cols) + " |" for _, row in show.iterrows()]
    return "\n".join([header, sep] + rows)


def render_markdown(report: Dict[str, Any], summary_df: pd.DataFrame, split_df: pd.DataFrame, dup_df: pd.DataFrame) -> str:
    lines: List[str] = []
    lines.append("# Stage23C Promotion-Candidate Validation")
    lines.append("")
    lines.append(f"Generated UTC: {report['generated_utc']}")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append(f"```text\n{report['decision']}\n```")
    lines.append("")
    lines.append("## Scope guardrails")
    lines.append("")
    lines.append("- Research/shadow only.")
    lines.append("- Stage18A v2 remains the active operational forward-shadow runner.")
    lines.append("- No EA change, no automatic trading, no paper/live/order authorization.")
    lines.append("- This module validates Stage23B candidates only; it does not promote them operationally.")
    lines.append("")
    lines.append("## Data")
    lines.append("")
    d = report["data"]
    lines.append(f"- M1 rows: {d['m1_rows']} | span: {d['m1_start']} → {d['m1_end']}")
    lines.append(f"- H1 rows: {d['h1_rows']} | span: {d['h1_start']} → {d['h1_end']}")
    lines.append(f"- M15 rows: {d['m15_rows']} | span: {d['m15_start']} → {d['m15_end']}")
    lines.append(f"- Roundtrip cost x1: {ROUNDTRIP_COST_USD}")
    lines.append("")
    lines.append("## Duplicate / redundancy check")
    lines.append("")
    if dup_df.empty:
        lines.append("No exact duplicate event signatures detected among locked candidates.")
    else:
        lines.append(markdown_table(dup_df, ["candidate_count", "candidates"], 10))
    lines.append("")
    lines.append("## Candidate validation summary")
    lines.append("")
    cols = [
        "decision", "candidate", "events", "pf_x1", "pf_x4", "pf_x6", "test20_pf_x4",
        "boot_pf_p05_x4", "years_pf_positive_x4", "valid_year_count", "pf_2026_x4",
        "events_2026", "loss_count_2026_x4", "median_x4", "total_x4",
    ]
    lines.append(markdown_table(summary_df, cols, 20))
    lines.append("")
    lines.append("## Split diagnostics")
    lines.append("")
    if split_df.empty:
        lines.append("No split diagnostics generated.")
    else:
        lines.append(markdown_table(split_df, ["candidate", "split_type", "split", "events", "pf", "total", "median", "win_rate", "loss_count"], 80))
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("- `pf_2026 = inf` is treated as a warning if it comes from zero losing trades, not as proof of robustness.")
    lines.append("- Duplicate pb0.1/pb0.3 variants are not independent evidence if their event signatures match.")
    lines.append("- A validated result here is still research-only. The next step would be a narrow Stage23D forward-shadow candidate module, not EA/paper/live execution.")
    lines.append("")
    lines.append("## Operational reminder")
    lines.append("")
    lines.append("Continue Stage18A v2 separately after AMarkets CSV refresh:")
    lines.append("")
    lines.append("```bash")
    lines.append("cd ~/Desktop/xauusd-trader")
    lines.append("python3 -m app.stage18a_unified_shadow_ops_cycle")
    lines.append("cat data/reports/stage18a_unified_shadow_ops_cycle/stage18a_unified_shadow_ops_cycle.md")
    lines.append("```")
    lines.append("")
    lines.append("## Output files")
    lines.append("")
    lines.append(f"- `{REPORT_DIR / 'stage23c_promotion_candidate_validation.json'}`")
    lines.append(f"- `{REPORT_DIR / 'stage23c_promotion_candidate_validation.md'}`")
    lines.append(f"- `{REPORT_DIR / 'stage23c_candidate_summary.csv'}`")
    lines.append(f"- `{REPORT_DIR / 'stage23c_split_diagnostics.csv'}`")
    lines.append(f"- `{REPORT_DIR / 'stage23c_exact_trades.csv'}`")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")

    m1, h1, m15, load_meta = load_market_data()
    h1 = add_atr(h1)
    m15 = merge_atr(m15, h1)
    m1 = merge_atr(m1, h1)

    all_trades: List[pd.DataFrame] = []
    summary_rows: List[Dict[str, Any]] = []
    split_rows: List[Dict[str, Any]] = []
    event_signatures: Dict[str, str] = {}

    for cand in LOCKED_CANDIDATES:
        events = events_london_oneway_continuation(m15, cand.params)
        event_signatures[cand.name] = _event_signature(events)
        trades = replay_events(m1, events, cand, ROUNDTRIP_COST_USD)
        df = _trade_dataframe(trades, cand.name)
        if not df.empty:
            all_trades.append(df)
        summary_rows.append(summarize_candidate(df, cand))
        split_rows.extend(make_split_rows(df, cand.name))

    summary_df = pd.DataFrame(summary_rows).sort_values(
        ["decision", "pf_x4", "boot_pf_p05_x4", "events"], ascending=[True, False, False, False]
    )
    split_df = pd.DataFrame(split_rows)
    trades_df = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
    dup_df = pd.DataFrame(detect_duplicates(event_signatures))

    validated_count = int((summary_df["decision"] == "STAGE23C_VALIDATED_PROMOTION_REVIEW_ONLY").sum()) if not summary_df.empty else 0
    watchlist_count = int((summary_df["decision"] == "STAGE23C_KEEP_WATCHLIST_ONLY").sum()) if not summary_df.empty else 0
    if validated_count > 0:
        decision = "STAGE23C_VALIDATED_PROMOTION_REVIEW_ONLY_RESEARCH_ONLY"
    elif watchlist_count > 0:
        decision = "STAGE23C_KEEP_WATCHLIST_ONLY"
    else:
        decision = "STAGE23C_REJECT_STAGE23B_PROMOTION_REVIEW"

    report = {
        "stage": STAGE_NAME,
        "generated_utc": generated,
        "decision": decision,
        "scope": {
            "research_only": True,
            "stage18a_active_runner_unchanged": True,
            "automatic_trading_authorized": False,
            "paper_live_authorized": False,
            "orders_authorized": False,
            "operational_promotion_done": False,
        },
        "data": {
            "m1_rows": int(len(m1)),
            "m1_start": str(m1["time"].min()),
            "m1_end": str(m1["time"].max()),
            "h1_rows": int(len(h1)),
            "h1_start": str(h1["time"].min()),
            "h1_end": str(h1["time"].max()),
            "m15_rows": int(len(m15)),
            "m15_start": str(m15["time"].min()),
            "m15_end": str(m15["time"].max()),
            "load_meta": load_meta,
        },
        "config": {
            "locked_candidate_count": len(LOCKED_CANDIDATES),
            "cost_multipliers": COST_MULTIPLIERS,
            "bootstrap_iters": BOOTSTRAP_ITERS,
            "roundtrip_cost_usd": ROUNDTRIP_COST_USD,
        },
        "counts": {
            "validated_count": validated_count,
            "watchlist_count": watchlist_count,
            "duplicate_groups": int(len(dup_df)),
            "total_replayed_trades_rows": int(len(trades_df)),
        },
        "duplicates": [] if dup_df.empty else _finite_for_json(dup_df.to_dict(orient="records")),
        "candidate_summary": _finite_for_json(summary_df.to_dict(orient="records")),
    }

    summary_path = REPORT_DIR / "stage23c_candidate_summary.csv"
    split_path = REPORT_DIR / "stage23c_split_diagnostics.csv"
    trades_path = REPORT_DIR / "stage23c_exact_trades.csv"
    json_path = REPORT_DIR / "stage23c_promotion_candidate_validation.json"
    md_path = REPORT_DIR / "stage23c_promotion_candidate_validation.md"

    summary_df.to_csv(summary_path, index=False)
    split_df.to_csv(split_path, index=False)
    trades_df.to_csv(trades_path, index=False)
    json_path.write_text(json.dumps(_finite_for_json(report), indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(report, summary_df, split_df, dup_df), encoding="utf-8")

    print(json.dumps(_finite_for_json({"stage": STAGE_NAME, "decision": decision, "report_md": str(md_path), "report_json": str(json_path)}), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
