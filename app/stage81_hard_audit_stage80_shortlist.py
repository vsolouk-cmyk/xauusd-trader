#!/usr/bin/env python3
"""
Stage81 Hard Audit for Stage80 structured thesis discovery shortlist.

No orders. No broker connection. No EA changes.
This stage recomputes Stage80 shortlist rules from the macro dataset and applies
a stricter hard-audit layer before any candidate can be considered for a future
observer-only portfolio expansion.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd


@dataclass(frozen=True)
class Condition:
    column: str
    operator: str
    threshold: float


@dataclass(frozen=True)
class Rule:
    rule_id: str
    label: str
    bucket: str
    horizon_trading_days: int
    cooldown_trading_days: int
    conditions: Tuple[Condition, ...]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(root: Path, p: str | Path) -> Path:
    p = Path(p)
    if p.is_absolute():
        return p
    return root / p


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def parse_condition_text(text: str) -> Tuple[Condition, ...]:
    parts = [p.strip() for p in str(text).split(" AND ") if p.strip()]
    out: List[Condition] = []
    for part in parts:
        matched = False
        for op in (">=", "<=", ">", "<", "=="):
            if op in part:
                lhs, rhs = part.split(op, 1)
                out.append(Condition(lhs.strip(), op, float(rhs.strip())))
                matched = True
                break
        if not matched:
            raise ValueError(f"Cannot parse condition: {part!r}")
    if not out:
        raise ValueError("Empty rule condition text")
    return tuple(out)


def compare(value: float, operator: str, threshold: float) -> bool:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return False
    if operator == ">":
        return value > threshold
    if operator == "<":
        return value < threshold
    if operator == ">=":
        return value >= threshold
    if operator == "<=":
        return value <= threshold
    if operator == "==":
        return value == threshold
    raise ValueError(f"Unsupported operator: {operator}")


def load_config(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_macro(path: Path, date_col: str, price_col: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"macro dataset not found: {path}")
    df = pd.read_csv(path)
    if date_col not in df.columns:
        raise ValueError(f"missing date column {date_col!r} in macro dataset")
    if price_col not in df.columns:
        raise ValueError(f"missing price column {price_col!r} in macro dataset")
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce", utc=True)
    df = df[df[date_col].notna()].sort_values(date_col).reset_index(drop=True)
    for c in df.columns:
        if c == date_col:
            continue
        converted = pd.to_numeric(df[c], errors="coerce")
        # Preserve clearly textual metadata columns when conversion yields no numeric values.
        if converted.notna().sum() > 0:
            df[c] = converted
    return df


def add_derived_features(df: pd.DataFrame) -> List[str]:
    added: List[str] = []

    def add_return(name: str, base: str, period: int) -> None:
        nonlocal added
        if name not in df.columns and base in df.columns:
            df[name] = df[base] / df[base].shift(period) - 1.0
            added.append(name)

    def add_change(name: str, base: str, period: int) -> None:
        nonlocal added
        if name not in df.columns and base in df.columns:
            df[name] = df[base] - df[base].shift(period)
            added.append(name)

    def add_sma_diff(name: str, base: str, fast: int = 20, slow: int = 50) -> None:
        nonlocal added
        if name not in df.columns and base in df.columns:
            df[name] = df[base].rolling(fast, min_periods=fast).mean() / df[base].rolling(slow, min_periods=slow).mean() - 1.0
            added.append(name)

    add_return("gold_ret_20d", "gold_close", 20)
    add_return("gold_ret_60d", "gold_close", 60)
    add_return("dxy_ret_20d", "dxy", 20)
    add_return("dxy_ret_60d", "dxy", 60)
    add_change("real_yield_change_20d", "real_yield", 20)
    add_change("real_yield_change_60d", "real_yield", 60)
    add_change("vix_change_20d", "vix", 20)
    add_sma_diff("gold_sma20_over_50", "gold_close", 20, 50)
    add_sma_diff("dxy_sma20_over_50", "dxy", 20, 50)
    return added


def load_stage80_shortlist(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Stage80 shortlist CSV not found: {path}")
    df = pd.read_csv(path)
    required = {"rule_id", "label", "bucket", "horizon_trading_days", "cooldown_trading_days", "condition_text"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Stage80 shortlist CSV missing columns: {missing}")
    return df


def rules_from_shortlist(df: pd.DataFrame) -> List[Rule]:
    rules: List[Rule] = []
    seen: set[str] = set()
    for _, row in df.iterrows():
        rid = str(row["rule_id"])
        if rid in seen:
            continue
        seen.add(rid)
        rules.append(
            Rule(
                rule_id=rid,
                label=str(row["label"]),
                bucket=str(row.get("bucket", "")),
                horizon_trading_days=int(row["horizon_trading_days"]),
                cooldown_trading_days=int(row["cooldown_trading_days"]),
                conditions=parse_condition_text(str(row["condition_text"])),
            )
        )
    return rules


def evaluate_rule(df: pd.DataFrame, rule: Rule, date_col: str, price_col: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    missing_columns = [c.column for c in rule.conditions if c.column not in df.columns]
    required_cols = [date_col, price_col] + [c.column for c in rule.conditions if c.column in df.columns]
    missing_required_feature_rows = int(df[required_cols].isna().any(axis=1).sum()) if required_cols else len(df)

    if missing_columns:
        return [], {
            "missing_columns": "|".join(sorted(missing_columns)),
            "missing_required_feature_rows": missing_required_feature_rows,
            "lookahead_violations": 0,
            "active_days": 0,
            "replay_active_days": 0,
        }

    condition_pass = []
    for _, row in df.iterrows():
        ok = True
        for cond in rule.conditions:
            val = row.get(cond.column)
            if not compare(float(val) if pd.notna(val) else math.nan, cond.operator, cond.threshold):
                ok = False
                break
        condition_pass.append(ok)

    active_days = int(sum(condition_pass))
    entries: List[Dict[str, Any]] = []
    last_entry_i = -10**9
    n = len(df)
    lookahead_violations = 0

    for i, active in enumerate(condition_pass):
        if not active:
            continue
        if i - last_entry_i < rule.cooldown_trading_days:
            continue
        exit_i = i + rule.horizon_trading_days
        if exit_i >= n:
            continue
        entry_date = df.at[i, date_col]
        exit_date = df.at[exit_i, date_col]
        if exit_date <= entry_date:
            lookahead_violations += 1
            continue
        entry_price = float(df.at[i, price_col])
        exit_price = float(df.at[exit_i, price_col])
        if not math.isfinite(entry_price) or not math.isfinite(exit_price) or entry_price <= 0:
            continue
        gross_bps = (exit_price / entry_price - 1.0) * 10000.0
        entries.append(
            {
                "rule_id": rule.rule_id,
                "label": rule.label,
                "entry_index": i,
                "exit_index": exit_i,
                "entry_date_utc": entry_date.date().isoformat(),
                "exit_date_utc": exit_date.date().isoformat(),
                "entry_price": entry_price,
                "exit_price": exit_price,
                "gross_return_bps": round(gross_bps, 4),
            }
        )
        last_entry_i = i

    replay_active_days = int(sum(condition_pass[min(rule.horizon_trading_days, n):])) if n else 0
    diagnostics = {
        "missing_columns": "",
        "missing_required_feature_rows": missing_required_feature_rows,
        "lookahead_violations": lookahead_violations,
        "active_days": active_days,
        "replay_active_days": replay_active_days,
    }
    return entries, diagnostics


def mean(xs: List[float]) -> Optional[float]:
    return float(sum(xs) / len(xs)) if xs else None


def median(xs: List[float]) -> Optional[float]:
    return float(statistics.median(xs)) if xs else None


def pct(x: Optional[float]) -> Optional[float]:
    if x is None:
        return None
    return round(float(x), 4)


def metrics_for_entries(entries: List[Dict[str, Any]], cost_bps_total: float) -> Dict[str, Any]:
    if not entries:
        return {
            "entry_count": 0,
            "matured_count": 0,
            "mean_net_return_bps": None,
            "median_net_return_bps": None,
            "win_rate": None,
            "min_net_return_bps": None,
            "max_net_return_bps": None,
            "total_net_return_bps": 0.0,
        }
    rets = [float(e["gross_return_bps"]) - cost_bps_total for e in entries]
    return {
        "entry_count": len(entries),
        "matured_count": len(entries),
        "mean_net_return_bps": round(mean(rets), 4),
        "median_net_return_bps": round(median(rets), 4),
        "win_rate": round(sum(1 for r in rets if r > 0) / len(rets), 4),
        "min_net_return_bps": round(min(rets), 4),
        "max_net_return_bps": round(max(rets), 4),
        "total_net_return_bps": round(sum(rets), 4),
    }


def filter_entries(entries: List[Dict[str, Any]], start: Optional[str], end: Optional[str]) -> List[Dict[str, Any]]:
    out = []
    for e in entries:
        d = e["entry_date_utc"]
        if start and d < start:
            continue
        if end and d > end:
            continue
        out.append(e)
    return out


def year_concentration(entries: List[Dict[str, Any]]) -> Tuple[Optional[int], float]:
    if not entries:
        return None, 0.0
    counts: Dict[int, int] = {}
    for e in entries:
        y = int(str(e["entry_date_utc"])[:4])
        counts[y] = counts.get(y, 0) + 1
    year, cnt = max(counts.items(), key=lambda kv: kv[1])
    return year, round(cnt / len(entries), 4)


def entry_rate_per_252(entries: List[Dict[str, Any]], start: str, end: str) -> Optional[float]:
    s = pd.Timestamp(start, tz="UTC")
    e = pd.Timestamp(end, tz="UTC")
    days = max((e - s).days, 1)
    years = days / 365.25
    if years <= 0:
        return None
    return round(len(entries) / years, 4)


def fail_reasons(row: Dict[str, Any], constraints: Dict[str, Any]) -> List[str]:
    reasons: List[str] = []

    def below(key: str, limit_key: str, reason: str) -> None:
        v = row.get(key)
        if v is None or float(v) < float(constraints[limit_key]):
            reasons.append(reason)

    def above_abs(key: str, limit_key: str, reason: str) -> None:
        v = row.get(key)
        if v is not None and abs(float(v)) > float(constraints[limit_key]):
            reasons.append(reason)

    if row.get("missing_columns"):
        reasons.append("MISSING_COLUMNS")
    if int(row.get("missing_required_feature_rows", 0)) > int(constraints["max_missing_required_feature_rows"]):
        reasons.append("MISSING_REQUIRED_FEATURE_ROWS")
    if int(row.get("lookahead_violations", 0)) > int(constraints["max_lookahead_violations"]):
        reasons.append("LOOKAHEAD_VIOLATIONS")

    if int(row.get("total_entry_count", 0)) < int(constraints["min_total_entries"]):
        reasons.append("TOTAL_ENTRIES_TOO_LOW")
    below("total_mean_net_return_bps", "min_total_mean_net_bps", "TOTAL_MEAN_TOO_LOW")
    below("total_median_net_return_bps", "min_total_median_net_bps", "TOTAL_MEDIAN_TOO_LOW")
    below("total_win_rate", "min_total_win_rate", "TOTAL_WIN_RATE_TOO_LOW")
    above_abs("total_min_net_return_bps", "max_abs_worst_loss_bps", "WORST_LOSS_TOO_LARGE")

    if int(row.get("validation_entries", 0)) < int(constraints["min_validation_entries"]):
        reasons.append("VALIDATION_ENTRIES_TOO_LOW")
    below("validation_mean_net_bps", "min_validation_mean_bps", "VALIDATION_MEAN_TOO_LOW")

    if int(row.get("locked_forward_entries", 0)) < int(constraints["min_locked_forward_entries"]):
        reasons.append("LOCKED_FORWARD_ENTRIES_TOO_LOW")
    below("locked_forward_mean_net_bps", "min_locked_forward_mean_bps", "LOCKED_FORWARD_MEAN_TOO_LOW")

    if int(row.get("final_holdout_entries", 0)) < int(constraints["min_final_holdout_entries"]):
        reasons.append("FINAL_HOLDOUT_ENTRIES_TOO_LOW")
    below("final_holdout_mean_net_bps", "min_final_holdout_mean_bps", "FINAL_HOLDOUT_MEAN_TOO_LOW")

    if int(row.get("post_plus_final_entries", 0)) < int(constraints["min_post_plus_final_entries"]):
        reasons.append("POST_PLUS_FINAL_ENTRIES_TOO_LOW")
    below("post_plus_final_mean_net_bps", "min_post_plus_final_mean_bps", "POST_PLUS_FINAL_MEAN_TOO_LOW")

    max_y = row.get("max_year_entry_share")
    if max_y is not None and float(max_y) > float(constraints["max_year_entry_share"]):
        reasons.append("YEAR_CONCENTRATION_TOO_HIGH")

    overlap = row.get("max_overlap_with_stage77b_selected_pct")
    if overlap is not None and overlap != "" and float(overlap) > float(constraints["max_overlap_with_stage77b_selected_pct"]):
        reasons.append("OVERLAP_WITH_STAGE77B_TOO_HIGH")

    return reasons


def score(row: Dict[str, Any]) -> float:
    # Conservative hard-audit score: downside, split stability, and overlap matter.
    vals = [
        row.get("total_mean_net_return_bps") or 0,
        row.get("total_median_net_return_bps") or 0,
        row.get("locked_forward_mean_net_bps") or 0,
        row.get("final_holdout_mean_net_bps") or 0,
        row.get("post_plus_final_mean_net_bps") or 0,
    ]
    downside_penalty = abs(min(0.0, float(row.get("total_min_net_return_bps") or 0))) * 0.35
    overlap_penalty = float(row.get("max_overlap_with_stage77b_selected_pct") or 0) * 8.0
    concentration_penalty = float(row.get("max_year_entry_share") or 0) * 250.0
    return round(sum(vals) - downside_penalty - overlap_penalty - concentration_penalty, 4)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    cfg = load_config(rel(root, args.config))
    out_dir = rel(root, args.out)
    ensure_dir(out_dir)

    date_col = cfg.get("date_col", "feature_date_utc")
    price_col = cfg.get("price_col", "gold_close")
    cost_bps = float(cfg.get("cost_bps_total_reference", 50.0))
    asof_date = cfg.get("asof_date", "2024-01-01")
    splits = cfg["splits"]
    constraints = cfg["constraints"]

    macro_path = rel(root, cfg["macro_dataset_path"])
    shortlist_path = rel(root, cfg["stage80_shortlist_csv"])
    summary80_path = rel(root, cfg["stage80_summary_json"])

    df = load_macro(macro_path, date_col, price_col)
    derived_added = add_derived_features(df)
    shortlist_df = load_stage80_shortlist(shortlist_path)
    rules = rules_from_shortlist(shortlist_df)

    # Keep Stage80 overlap column as a hard-audit input, but recompute the rest.
    overlap_map: Dict[str, Any] = {}
    if "max_overlap_with_stage77b_selected_pct" in shortlist_df.columns:
        for _, r in shortlist_df.iterrows():
            overlap_map[str(r["rule_id"])] = r.get("max_overlap_with_stage77b_selected_pct")

    metrics_rows: List[Dict[str, Any]] = []
    entry_rows: List[Dict[str, Any]] = []

    for rule in rules:
        entries, diag = evaluate_rule(df, rule, date_col, price_col)
        for e in entries:
            e2 = dict(e)
            e2["net_return_bps"] = round(float(e2["gross_return_bps"]) - cost_bps, 4)
            entry_rows.append(e2)

        total = metrics_for_entries(entries, cost_bps)
        row: Dict[str, Any] = {
            "rule_id": rule.rule_id,
            "label": rule.label,
            "bucket": rule.bucket,
            "horizon_trading_days": rule.horizon_trading_days,
            "cooldown_trading_days": rule.cooldown_trading_days,
            "condition_text": " AND ".join(f"{c.column}{c.operator}{c.threshold}" for c in rule.conditions),
            **diag,
            "total_entry_count": total["entry_count"],
            "total_matured_count": total["matured_count"],
            "total_mean_net_return_bps": total["mean_net_return_bps"],
            "total_median_net_return_bps": total["median_net_return_bps"],
            "total_win_rate": total["win_rate"],
            "total_min_net_return_bps": total["min_net_return_bps"],
            "total_max_net_return_bps": total["max_net_return_bps"],
            "total_total_net_return_bps": total["total_net_return_bps"],
            "entry_rate_per_year": entry_rate_per_252(entries, df[date_col].min().date().isoformat(), df[date_col].max().date().isoformat()),
            "max_overlap_with_stage77b_selected_pct": overlap_map.get(rule.rule_id, ""),
        }

        for split_name, bounds in splits.items():
            ents = filter_entries(entries, bounds.get("start"), bounds.get("end"))
            m = metrics_for_entries(ents, cost_bps)
            prefix = split_name.lower()
            row[f"{prefix}_entries"] = m["entry_count"]
            row[f"{prefix}_mean_net_bps"] = m["mean_net_return_bps"]
            row[f"{prefix}_median_net_bps"] = m["median_net_return_bps"]
            row[f"{prefix}_win_rate"] = m["win_rate"]

        pre = [e for e in entries if e["exit_date_utc"] < asof_date]
        post = [e for e in entries if e["entry_date_utc"] >= asof_date]
        final_bounds = splits.get("FINAL_HOLDOUT", {})
        final = filter_entries(entries, final_bounds.get("start"), final_bounds.get("end"))
        post_plus_final_ids = {(e["entry_date_utc"], e["rule_id"]) for e in post}
        post_plus_final = list(post)
        for e in final:
            if (e["entry_date_utc"], e["rule_id"]) not in post_plus_final_ids:
                post_plus_final.append(e)

        for name, ents in [
            ("pre_asof", pre),
            ("post_asof", post),
            ("post_plus_final", post_plus_final),
        ]:
            m = metrics_for_entries(ents, cost_bps)
            row[f"{name}_entries"] = m["entry_count"]
            row[f"{name}_mean_net_bps"] = m["mean_net_return_bps"]
            row[f"{name}_median_net_bps"] = m["median_net_return_bps"]
            row[f"{name}_win_rate"] = m["win_rate"]

        y, yshare = year_concentration(entries)
        row["max_entry_year"] = y
        row["max_year_entry_share"] = yshare

        reasons = fail_reasons(row, constraints)
        row["pass_hard_audit_candidate"] = len(reasons) == 0
        row["hard_fail_reasons"] = "|".join(reasons)
        row["hard_audit_score"] = score(row)
        metrics_rows.append(row)

    metrics_rows.sort(key=lambda r: (not bool(r["pass_hard_audit_candidate"]), -float(r["hard_audit_score"])))

    pass_rows = [r for r in metrics_rows if r["pass_hard_audit_candidate"]]
    max_selected = int(cfg.get("max_selected_for_stage82", 4))
    selected_rows = pass_rows[:max_selected]

    if selected_rows:
        decision = "STAGE81_HARD_AUDIT_SHORTLIST_READY_FOR_PORTFOLIO_REVIEW_NO_ORDER"
        classification = "S81_HARD_AUDIT_SHORTLIST_READY"
        disposition = "HARD_AUDIT_SHORTLIST_READY_FOR_PORTFOLIO_REVIEW"
    else:
        decision = "STAGE81_NO_DISCOVERY_CANDIDATE_SURVIVES_HARD_AUDIT_NO_ORDER"
        classification = "S81_NO_HARD_AUDIT_SURVIVOR"
        disposition = "NO_DISCOVERY_CANDIDATE_SURVIVES_HARD_AUDIT"

    metrics_csv = out_dir / "stage81_hard_audit_metrics.csv"
    selected_csv = out_dir / "stage81_selected_for_stage82.csv"
    failures_csv = out_dir / "stage81_hard_audit_failures.csv"
    entries_csv = out_dir / "stage81_hard_audit_entry_returns.csv"
    summary_json = out_dir / "stage81_hard_audit_stage80_shortlist_summary.json"
    report_md = out_dir / "stage81_hard_audit_stage80_shortlist_report.md"

    fieldnames = list(metrics_rows[0].keys()) if metrics_rows else []
    with metrics_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(metrics_rows)

    with selected_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(selected_rows)

    with failures_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows([r for r in metrics_rows if not r["pass_hard_audit_candidate"]])

    if entry_rows:
        entry_fields = list(entry_rows[0].keys())
        with entries_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=entry_fields)
            w.writeheader()
            w.writerows(entry_rows)
    else:
        entries_csv.write_text("rule_id,label,entry_date_utc,exit_date_utc,net_return_bps\n", encoding="utf-8")

    stage80_decision = None
    if summary80_path.exists():
        try:
            with summary80_path.open("r", encoding="utf-8") as f:
                stage80_decision = json.load(f).get("decision")
        except Exception:
            stage80_decision = "UNREADABLE"

    summary = {
        "stage": "Stage81_HARD_AUDIT_STAGE80_SHORTLIST",
        "root": str(root),
        "config": str(rel(root, args.config)),
        "generated_utc": utc_now(),
        "status": "STAGE81_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
        "principle": "Hard-audit Stage80 discovery shortlist before any observer-portfolio expansion. No orders, no broker connection, no EA change.",
        "stage80_decision_reference": stage80_decision,
        "macro_dataset": {
            "path": str(macro_path),
            "rows": int(len(df)),
            "date_col": date_col,
            "price_col": price_col,
            "min_date": df[date_col].min().date().isoformat() if len(df) else None,
            "max_date": df[date_col].max().date().isoformat() if len(df) else None,
            "sha256": sha256_file(macro_path),
            "derived_features_added": derived_added,
        },
        "candidate_count": len(metrics_rows),
        "pass_hard_audit_count": len(pass_rows),
        "selected_count": len(selected_rows),
        "selected_rule_ids": [r["rule_id"] for r in selected_rows],
        "selected_for_stage82": selected_rows,
        "constraints": constraints,
        "hard_blocks": [
            "NO_AUTOMATED_ORDER",
            "NO_PAPER_ORDER",
            "NO_BROKER_CONNECTION",
            "NO_EA_PROMOTION",
            "NO_PAPER_LIVE",
            "NO_LIVE",
            "NO_ORDER_AUTHORIZATION_FROM_STAGE81",
            "NO_THRESHOLD_TUNING_FROM_STAGE81_HARD_AUDIT",
            "NO_DIRECT_MT5_OR_EA_CHANGE_FROM_STAGE81",
        ],
        "outputs": {
            "summary_json": str(summary_json),
            "report_md": str(report_md),
            "metrics_csv": str(metrics_csv),
            "selected_csv": str(selected_csv),
            "failures_csv": str(failures_csv),
            "entry_returns_csv": str(entries_csv),
        },
    }
    with summary_json.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    lines = [
        "# Stage81 Hard Audit - Stage80 Shortlist",
        "",
        "## Decision",
        f"- status: `STAGE81_COMPLETE_NO_PROMOTION`",
        f"- decision: `{decision}`",
        f"- classification: `{classification}`",
        f"- disposition: `{disposition}`",
        "",
        "## Principle",
        "Hard-audit Stage80 discovery candidates before any observer-only portfolio expansion. No order authorization.",
        "",
        "## Selected for Stage82",
    ]
    if selected_rows:
        for r in selected_rows:
            lines.append(
                f"- `{r['rule_id']}`: {r['label']} score=`{r['hard_audit_score']}` mean=`{r['total_mean_net_return_bps']}` "
                f"locked=`{r.get('locked_forward_mean_net_bps')}` final=`{r.get('final_holdout_mean_net_bps')}` "
                f"post_plus_final=`{r.get('post_plus_final_mean_net_bps')}`"
            )
    else:
        lines.append("- none")
    lines += [
        "",
        "## Candidate snapshot",
    ]
    for r in metrics_rows:
        lines.append(
            f"- `{r['rule_id']}` pass=`{r['pass_hard_audit_candidate']}` score=`{r['hard_audit_score']}` "
            f"mean=`{r['total_mean_net_return_bps']}` median=`{r['total_median_net_return_bps']}` "
            f"win=`{r['total_win_rate']}` worst=`{r['total_min_net_return_bps']}` "
            f"fail=`{r['hard_fail_reasons']}`"
        )
    lines += [
        "",
        "## Hard blocks",
    ]
    for hb in summary["hard_blocks"]:
        lines.append(f"- `{hb}`")
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({
        "stage": summary["stage"],
        "status": summary["status"],
        "decision": summary["decision"],
        "selected_count": summary["selected_count"],
        "summary_json": str(summary_json),
        "report_md": str(report_md),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
