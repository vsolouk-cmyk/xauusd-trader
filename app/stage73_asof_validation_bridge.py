#!/usr/bin/env python3
"""Stage73 As-Of Validation Bridge for K06.

Runs an as-of historical validation: treat the configured as_of_date as if it were
"today", derive expectations from earlier matured K06 events, then compare against
later locked outcomes without retuning thresholds.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd


@dataclass
class Condition:
    column: str
    operator: str
    threshold: float

    def eval(self, row: pd.Series) -> Tuple[bool, Any, str]:
        if self.column not in row.index:
            return False, None, f"missing:{self.column}"
        value = row[self.column]
        if pd.isna(value):
            return False, None, f"nan:{self.column}"
        value_f = float(value)
        if self.operator == ">":
            passed = value_f > self.threshold
        elif self.operator == "<":
            passed = value_f < self.threshold
        elif self.operator == ">=":
            passed = value_f >= self.threshold
        elif self.operator == "<=":
            passed = value_f <= self.threshold
        elif self.operator == "==":
            passed = value_f == self.threshold
        else:
            raise ValueError(f"Unsupported operator: {self.operator}")
        return passed, value_f, "ok" if passed else f"{value_f}{self.operator}{self.threshold}"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_config(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def ensure_out(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)


def evaluate_conditions(row: pd.Series, conditions: List[Condition]) -> Tuple[bool, List[Dict[str, Any]], List[str]]:
    results: List[Dict[str, Any]] = []
    failures: List[str] = []
    ok_all = True
    for cond in conditions:
        passed, value, reason = cond.eval(row)
        results.append({
            "column": cond.column,
            "operator": cond.operator,
            "threshold": cond.threshold,
            "value": value,
            "passed": passed,
            "reason": reason,
        })
        if not passed:
            ok_all = False
            failures.append(f"{cond.column}:{reason}")
    return ok_all, results, failures


def safe_mean(xs: List[float]) -> Optional[float]:
    return round(float(pd.Series(xs).mean()), 4) if xs else None


def safe_median(xs: List[float]) -> Optional[float]:
    return round(float(pd.Series(xs).median()), 4) if xs else None


def metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    vals = [float(r["net_return_bps"]) for r in rows if r.get("matured")]
    wins = [v for v in vals if v > 0]
    return {
        "entry_count": len(rows),
        "matured_count": len(vals),
        "mean_net_return_bps": safe_mean(vals),
        "median_net_return_bps": safe_median(vals),
        "win_rate": round(len(wins) / len(vals), 4) if vals else None,
        "min_net_return_bps": round(min(vals), 4) if vals else None,
        "max_net_return_bps": round(max(vals), 4) if vals else None,
        "total_net_return_bps": round(sum(vals), 4) if vals else None,
    }


def build_events(
    df: pd.DataFrame,
    date_col: str,
    price_col: str,
    conditions: List[Condition],
    horizon: int,
    cooldown: int,
    cost_bps_total: float,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], int, int]:
    rows = df.reset_index(drop=True)
    events: List[Dict[str, Any]] = []
    daily_ledger: List[Dict[str, Any]] = []
    last_entry_idx = -10**9
    lookahead_violations = 0
    missing_feature_rows = 0

    for i, row in rows.iterrows():
        date = row[date_col]
        active, cond_results, failures = evaluate_conditions(row, conditions)
        missing_or_nan = any((r["reason"] or "").startswith(("missing", "nan")) for r in cond_results)
        if missing_or_nan:
            missing_feature_rows += 1
        cooldown_ready = (i - last_entry_idx) >= cooldown
        trigger = bool(active and cooldown_ready)

        ledger_row = {
            "date_utc": str(pd.Timestamp(date).date()),
            "signal_active": active,
            "cooldown_ready": cooldown_ready,
            "entry_trigger": trigger,
            "rule_failures": "; ".join(failures),
        }
        for result in cond_results:
            ledger_row[f"{result['column']}_value"] = result["value"]
            ledger_row[f"{result['column']}_passed"] = result["passed"]
        daily_ledger.append(ledger_row)

        if trigger:
            last_entry_idx = i
            entry_price = float(row[price_col])
            exit_idx = i + horizon
            matured = exit_idx < len(rows)
            exit_date = None
            exit_price = None
            gross_bps = None
            net_bps = None
            if matured:
                exit_row = rows.iloc[exit_idx]
                if exit_idx <= i:
                    lookahead_violations += 1
                exit_date = str(pd.Timestamp(exit_row[date_col]).date())
                exit_price = float(exit_row[price_col])
                gross_bps = (exit_price / entry_price - 1.0) * 10000.0
                net_bps = gross_bps - cost_bps_total
            events.append({
                "entry_index": int(i),
                "entry_date_utc": str(pd.Timestamp(date).date()),
                "entry_price": round(entry_price, 6),
                "exit_index": int(exit_idx) if matured else None,
                "exit_date_utc": exit_date,
                "exit_price": round(exit_price, 6) if exit_price is not None else None,
                "horizon_trading_days": horizon,
                "matured": matured,
                "gross_return_bps": round(gross_bps, 4) if gross_bps is not None else None,
                "net_return_bps": round(net_bps, 4) if net_bps is not None else None,
                "cost_bps_total": cost_bps_total,
            })
    return events, daily_ledger, lookahead_violations, missing_feature_rows


def assign_asof_bucket(events: List[Dict[str, Any]], as_of_date: pd.Timestamp, final_holdout_start: pd.Timestamp) -> None:
    for e in events:
        d = pd.Timestamp(e["entry_date_utc"])
        if d < as_of_date:
            e["asof_bucket"] = "PRE_ASOF_CALIBRATION"
        elif d < final_holdout_start:
            e["asof_bucket"] = "POST_ASOF_VALIDATION"
        else:
            e["asof_bucket"] = "FINAL_HOLDOUT_COMPARISON"


def metric_error(expected: Dict[str, Any], actual: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k in ["mean_net_return_bps", "median_net_return_bps", "win_rate", "entry_count", "matured_count"]:
        ev = expected.get(k)
        av = actual.get(k)
        out[f"expected_{k}"] = ev
        out[f"actual_{k}"] = av
        if ev is None or av is None:
            out[f"abs_error_{k}"] = None
        else:
            out[f"abs_error_{k}"] = round(abs(float(av) - float(ev)), 4)
    return out


def monthly_metrics(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not events:
        return []
    df = pd.DataFrame(events)
    df = df[df["matured"] == True].copy()
    if df.empty:
        return []
    df["entry_month"] = pd.to_datetime(df["entry_date_utc"]).dt.to_period("M").astype(str)
    out = []
    for m, g in df.groupby("entry_month"):
        vals = g["net_return_bps"].astype(float).tolist()
        out.append({
            "entry_month": m,
            "entry_count": len(g),
            "mean_net_return_bps": round(sum(vals) / len(vals), 4),
            "win_rate": round(sum(1 for v in vals if v > 0) / len(vals), 4),
        })
    return out


def temporal_compatibility(df: pd.DataFrame, date_col: str, columns: List[str], start: str, end: Optional[str]) -> List[Dict[str, Any]]:
    d = df.copy()
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end) if end else d[date_col].max()
    d = d[(d[date_col] >= start_ts) & (d[date_col] <= end_ts)].copy()
    out = []
    for col in columns:
        exists = col in d.columns
        non_null = int(d[col].notna().sum()) if exists else 0
        rows = len(d)
        dates = d.loc[d[col].notna(), date_col] if exists else pd.Series([], dtype="datetime64[ns]")
        coverage = round(non_null / rows * 100.0, 4) if rows else 0.0
        out.append({
            "column": col,
            "exists": exists,
            "rows_in_window": rows,
            "non_null_rows": non_null,
            "coverage_pct": coverage,
            "first_non_null_date": str(dates.min().date()) if len(dates) else None,
            "last_non_null_date": str(dates.max().date()) if len(dates) else None,
            "status": "PASS_ASOF_TEMPORAL_COMPATIBILITY" if exists and coverage >= 95.0 else "LOW_COVERAGE_OR_MISSING_ASOF_COMPATIBILITY",
        })
    return out


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def run(root: Path, config_path: Path, out_dir: Path) -> Dict[str, Any]:
    cfg = load_config(config_path)
    root = root.resolve()
    out_dir = out_dir.resolve()
    ensure_out(out_dir)

    macro_path = root / cfg["macro_dataset_path"]
    if not macro_path.exists():
        raise FileNotFoundError(f"Macro dataset not found: {macro_path}")

    date_col = cfg.get("date_col", "feature_date_utc")
    price_col = cfg.get("price_col", "gold_close")
    as_of_date = pd.Timestamp(cfg["as_of_date"])
    final_holdout_start = pd.Timestamp(cfg["final_holdout_start"])
    replay_start = pd.Timestamp(cfg.get("replay_start", cfg["as_of_date"]))
    replay_end = pd.Timestamp(cfg["replay_end"]) if cfg.get("replay_end") else None

    df = pd.read_csv(macro_path)
    if date_col not in df.columns:
        raise ValueError(f"Missing date_col {date_col}")
    if price_col not in df.columns:
        raise ValueError(f"Missing price_col {price_col}")
    df[date_col] = pd.to_datetime(df[date_col], utc=False).dt.tz_localize(None)
    df = df.sort_values(date_col).reset_index(drop=True)

    conditions = [Condition(**x) for x in cfg["conditions"]]
    required_cols = [price_col] + [c.column for c in conditions] + cfg.get("compatibility_columns", [])
    required_cols = list(dict.fromkeys(required_cols))

    events_all, daily_all, lookahead_violations, missing_feature_rows = build_events(
        df, date_col, price_col, conditions,
        int(cfg["horizon_trading_days"]), int(cfg["entry_cooldown_trading_days"]), float(cfg["cost_bps_total"])
    )
    assign_asof_bucket(events_all, as_of_date, final_holdout_start)

    # Daily replay window represents the operational validation horizon.
    def in_window(d: str) -> bool:
        ts = pd.Timestamp(d)
        if ts < replay_start:
            return False
        if replay_end is not None and ts > replay_end:
            return False
        return True

    events_replay = [e for e in events_all if in_window(e["entry_date_utc"])]
    daily_replay = [r for r in daily_all if in_window(r["date_utc"])]

    pre = [e for e in events_all if e["asof_bucket"] == "PRE_ASOF_CALIBRATION" and e.get("matured")]
    post = [e for e in events_all if e["asof_bucket"] == "POST_ASOF_VALIDATION" and e.get("matured")]
    final = [e for e in events_all if e["asof_bucket"] == "FINAL_HOLDOUT_COMPARISON" and e.get("matured")]
    post_plus_final = [e for e in events_all if e["asof_bucket"] in ("POST_ASOF_VALIDATION", "FINAL_HOLDOUT_COMPARISON") and e.get("matured")]

    pre_metrics = metrics(pre)
    post_metrics = metrics(post)
    final_metrics = metrics(final)
    post_final_metrics = metrics(post_plus_final)
    replay_metrics = metrics([e for e in events_replay if e.get("matured")])

    validation_error_rows = []
    validation_error_rows.append({"comparison": "PRE_ASOF_EXPECTED_VS_POST_ASOF_ACTUAL", **metric_error(pre_metrics, post_metrics)})
    validation_error_rows.append({"comparison": "PRE_ASOF_EXPECTED_VS_FINAL_HOLDOUT_ACTUAL", **metric_error(pre_metrics, final_metrics)})
    validation_error_rows.append({"comparison": "PRE_ASOF_EXPECTED_VS_POST_PLUS_FINAL_ACTUAL", **metric_error(pre_metrics, post_final_metrics)})

    compat = temporal_compatibility(df, date_col, required_cols, cfg["as_of_date"], cfg.get("replay_end"))

    # Constraints focus on actual out-of-sample/post-as-of performance and replay integrity.
    constraints = cfg.get("decision_constraints", {})
    hard_failures = []
    cautions = []

    def fail_if(cond: bool, msg: str) -> None:
        if cond:
            hard_failures.append(msg)

    def caution_if(cond: bool, msg: str) -> None:
        if cond:
            cautions.append(msg)

    fail_if(lookahead_violations > constraints.get("max_lookahead_violations", 0), "LOOKAHEAD_VIOLATION")
    fail_if(missing_feature_rows > constraints.get("max_missing_feature_rows", 0), "MISSING_FEATURE_ROWS_PRESENT")
    fail_if(len(daily_replay) < constraints.get("min_replay_rows", 500), "INSUFFICIENT_REPLAY_ROWS")
    fail_if(post_final_metrics["matured_count"] < constraints.get("min_post_asof_matured_events", 4), "INSUFFICIENT_POST_ASOF_MATURED_EVENTS")
    if post_final_metrics["mean_net_return_bps"] is not None:
        fail_if(post_final_metrics["mean_net_return_bps"] < constraints.get("min_post_asof_mean_net_bps", 0.0), "POST_ASOF_MEAN_NET_BELOW_MIN")
    if post_final_metrics["win_rate"] is not None:
        fail_if(post_final_metrics["win_rate"] < constraints.get("min_post_asof_win_rate", 0.50), "POST_ASOF_WIN_RATE_BELOW_MIN")
    worst = post_final_metrics.get("min_net_return_bps")
    if worst is not None:
        fail_if(abs(float(worst)) > constraints.get("max_abs_post_asof_worst_loss_bps", 1500.0), "POST_ASOF_WORST_LOSS_EXCEEDS_LIMIT")

    # Error/caution thresholds: pre-as-of does not need perfect prediction but should not invert sign or miss coverage badly.
    err_final = validation_error_rows[1]
    if err_final.get("actual_mean_net_return_bps") is not None:
        caution_if(abs(float(err_final["actual_mean_net_return_bps"]) - float(err_final.get("expected_mean_net_return_bps") or 0.0)) > constraints.get("max_mean_error_bps_for_no_caution", 1000.0), "LARGE_MEAN_ERROR_VS_FINAL_HOLDOUT")

    low_cov = [c for c in compat if c["status"] != "PASS_ASOF_TEMPORAL_COMPATIBILITY"]
    fail_if(bool(low_cov), "ASOF_TEMPORAL_COMPATIBILITY_FAIL")

    if hard_failures:
        decision = "K06_ASOF_VALIDATION_FAIL_NO_ORDER"
        classification = "S73_K06_ASOF_VALIDATION_FAIL"
        disposition = "K06_FAILS_ASOF_VALIDATION"
    elif cautions:
        decision = "K06_ASOF_VALIDATION_PASS_WITH_CAUTION_NO_ORDER"
        classification = "S73_K06_ASOF_VALIDATION_PASS_WITH_CAUTION"
        disposition = "K06_PASSES_ASOF_VALIDATION_WITH_CAUTION"
    else:
        decision = "K06_ASOF_VALIDATION_PASS_NO_ORDER"
        classification = "S73_K06_ASOF_VALIDATION_PASS"
        disposition = "K06_PASSES_ASOF_VALIDATION"

    summary = {
        "stage": "Stage73_ASOF_VALIDATION_BRIDGE",
        "root": str(root),
        "config": str(config_path.resolve()),
        "status": "STAGE73_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
        "as_of_policy": {
            "as_of_date": cfg["as_of_date"],
            "principle": "Behave as if standing at the as-of date. Pre-as-of events define expectations; post-as-of and final holdout are compared to actual realized outcomes without retuning.",
            "final_holdout_start": cfg["final_holdout_start"],
            "replay_start": cfg.get("replay_start"),
            "replay_end": cfg.get("replay_end"),
        },
        "champion": {
            "thesis_id": "K06_RESILIENT_GOLD_VS_DXY",
            "family": "GOLD_RESILIENCE_AGAINST_DXY",
            "direction": "long",
            "horizon_trading_days": cfg["horizon_trading_days"],
            "entry_cooldown_trading_days": cfg["entry_cooldown_trading_days"],
            "conditions_text": ";".join([f"{c.column}{c.operator}{c.threshold}" for c in conditions]),
            "cost_bps_total": cfg["cost_bps_total"],
        },
        "macro_dataset": {
            "path": str(macro_path),
            "rows_raw": int(len(df)),
            "rows_replayed": int(len(daily_replay)),
            "date_col": date_col,
            "price_col": price_col,
            "min_date": str(df[date_col].min().date()),
            "max_date": str(df[date_col].max().date()),
            "sha256": sha256_file(macro_path),
        },
        "asof_metrics": {
            "pre_asof_calibration": pre_metrics,
            "post_asof_validation": post_metrics,
            "final_holdout_comparison": final_metrics,
            "post_plus_final_actual": post_final_metrics,
            "replay_window": replay_metrics,
        },
        "historical_daily_replay": {
            "replay_rows": int(len(daily_replay)),
            "entry_triggers_in_replay": int(len(events_replay)),
            "matured_outcomes_in_replay": int(sum(1 for e in events_replay if e.get("matured"))),
            "lookahead_violations": int(lookahead_violations),
            "missing_feature_rows": int(missing_feature_rows),
        },
        "validation_error_summary": validation_error_rows,
        "temporal_compatibility_summary": compat,
        "decision_constraints": constraints,
        "hard_failures": hard_failures,
        "cautions": cautions,
        "hard_blocks": [
            "NO_AUTOMATED_ORDER",
            "NO_PAPER_ORDER",
            "NO_BROKER_CONNECTION",
            "NO_EA_PROMOTION",
            "NO_PAPER_LIVE",
            "NO_LIVE",
            "NO_ORDER_AUTHORIZATION_FROM_STAGE73",
            "NO_THRESHOLD_TUNING_FROM_ASOF_VALIDATION",
            "NO_PROMOTION_FROM_STAGE73_WITHOUT_SEPARATE_GOVERNANCE",
        ],
        "operator_instructions": [
            "Stage73 is an as-of validation bridge and cannot authorize orders.",
            "Do not use real future data as the primary validation mechanism when historical as-of replay is available.",
            "Do not retune K06 thresholds after reading post-as-of or final holdout outcomes.",
            "Broker, EA, paper-live, and live paths remain blocked without separate governance.",
        ],
        "outputs": {
            "summary_json": str(out_dir / "stage73_asof_validation_bridge_summary.json"),
            "report_md": str(out_dir / "stage73_asof_validation_bridge_report.md"),
            "entry_returns_csv": str(out_dir / "stage73_k06_asof_entry_returns.csv"),
            "daily_ledger_csv": str(out_dir / "stage73_k06_asof_daily_ledger.csv"),
            "validation_errors_csv": str(out_dir / "stage73_k06_asof_validation_errors.csv"),
            "monthly_metrics_csv": str(out_dir / "stage73_k06_asof_monthly_metrics.csv"),
            "temporal_compatibility_csv": str(out_dir / "stage73_asof_temporal_compatibility.csv"),
        },
    }

    write_csv(out_dir / "stage73_k06_asof_entry_returns.csv", events_all)
    write_csv(out_dir / "stage73_k06_asof_daily_ledger.csv", daily_replay)
    write_csv(out_dir / "stage73_k06_asof_validation_errors.csv", validation_error_rows)
    write_csv(out_dir / "stage73_k06_asof_monthly_metrics.csv", monthly_metrics(events_all))
    write_csv(out_dir / "stage73_asof_temporal_compatibility.csv", compat)

    (out_dir / "stage73_asof_validation_bridge_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    report = render_report(summary)
    (out_dir / "stage73_asof_validation_bridge_report.md").write_text(report, encoding="utf-8")
    return summary


def render_report(s: Dict[str, Any]) -> str:
    m = s["asof_metrics"]
    err = s["validation_error_summary"]
    comp = s["temporal_compatibility_summary"]
    lines = [
        "# Stage73 As-Of Validation Bridge",
        "",
        "## Decision",
        f"- status: `{s['status']}`",
        f"- decision: `{s['decision']}`",
        f"- classification: `{s['classification']}`",
        f"- disposition: `{s['disposition']}`",
        "",
        "## As-of principle",
        f"- as_of_date: `{s['as_of_policy']['as_of_date']}`",
        f"- final_holdout_start: `{s['as_of_policy']['final_holdout_start']}`",
        "- Behave as if standing at the as-of date; compare estimates/expectations against later realized locked data without retuning.",
        "",
        "## Champion",
        f"- thesis_id: `{s['champion']['thesis_id']}`",
        f"- horizon_trading_days: `{s['champion']['horizon_trading_days']}`",
        f"- conditions: `{s['champion']['conditions_text']}`",
        "",
        "## Metrics",
    ]
    for bucket, vals in m.items():
        lines.extend([
            f"### `{bucket}`",
            f"- matured_count: `{vals.get('matured_count')}`",
            f"- mean_net_return_bps: `{vals.get('mean_net_return_bps')}`",
            f"- median_net_return_bps: `{vals.get('median_net_return_bps')}`",
            f"- win_rate: `{vals.get('win_rate')}`",
            f"- min_net_return_bps: `{vals.get('min_net_return_bps')}`",
            f"- max_net_return_bps: `{vals.get('max_net_return_bps')}`",
            "",
        ])
    lines.extend(["## Validation error summary"])
    for row in err:
        lines.extend([
            f"### `{row['comparison']}`",
            f"- expected_mean_net_return_bps: `{row.get('expected_mean_net_return_bps')}`",
            f"- actual_mean_net_return_bps: `{row.get('actual_mean_net_return_bps')}`",
            f"- abs_error_mean_net_return_bps: `{row.get('abs_error_mean_net_return_bps')}`",
            f"- expected_win_rate: `{row.get('expected_win_rate')}`",
            f"- actual_win_rate: `{row.get('actual_win_rate')}`",
            f"- abs_error_win_rate: `{row.get('abs_error_win_rate')}`",
            "",
        ])
    lines.extend(["## Replay integrity", ""])
    r = s["historical_daily_replay"]
    for k, v in r.items():
        lines.append(f"- {k}: `{v}`")
    lines.extend(["", "## Temporal compatibility"])
    for c in comp:
        lines.append(f"- `{c['column']}`: status=`{c['status']}`, coverage_pct=`{c['coverage_pct']}`, first=`{c['first_non_null_date']}`, last=`{c['last_non_null_date']}`")
    lines.extend(["", "## Hard failures", "- " + ("none" if not s["hard_failures"] else "; ".join(s["hard_failures"]))])
    lines.extend(["", "## Cautions", "- " + ("none" if not s["cautions"] else "; ".join(s["cautions"]))])
    lines.extend(["", "## Hard blocks"])
    for hb in s["hard_blocks"]:
        lines.append(f"- `{hb}`")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    summary = run(Path(args.root), Path(args.config), Path(args.out))
    print(json.dumps({
        "stage": summary["stage"],
        "status": summary["status"],
        "decision": summary["decision"],
        "classification": summary["classification"],
        "disposition": summary["disposition"],
        "summary_json": summary["outputs"]["summary_json"],
        "report_md": summary["outputs"]["report_md"],
    }, indent=2))


if __name__ == "__main__":
    main()
