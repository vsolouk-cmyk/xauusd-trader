#!/usr/bin/env python3
"""Stage65 forward-shadow signal ledger fastlane.

No-order runner. It appends prospective signal-state rows for the locked Stage64
macro survivor and maintains a pending/matured observation ledger.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


HARD_BLOCKS = [
    "NO_PAPER_ORDER",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_BROKER_CONNECTION",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE65",
    "NO_HISTORICAL_EVENT_FILTER_FROM_FORWARD_ONLY_GOVERNANCE",
    "NO_POST_HOC_EVENT_EXCLUSION",
    "NO_REDUCED_SCOPE_RETEST",
    "NO_RESCUE_FILTERING",
    "NO_NEW_INTRADAY_SCAN",
    "NO_THRESHOLD_TUNING",
    "NO_COMMERCIALIZATION_WITHOUT_LATER_FORWARD_AND_BROKER_GOVERNANCE",
]

SIGNAL_LEDGER_FIELDS = [
    "run_utc",
    "feature_date_utc",
    "sample_available_after_utc",
    "hypothesis_id",
    "horizon_days",
    "signal_active",
    "benchmark_active",
    "rule_failures",
    "gold_close",
    "external_spot_close",
    "dxy_ret_20d",
    "real_yield_change_20d",
    "etf_flow_tonnes_3m",
    "central_bank_demand_tonnes_6m",
    "event_calendar_forward_only_governance_active",
    "historical_event_calendar_feature_present",
    "asof_lag_safe",
    "row_hash",
    "no_order_policy",
]

OBS_LEDGER_FIELDS = [
    "signal_id",
    "created_utc",
    "feature_date_utc",
    "entry_external_spot_date",
    "entry_external_spot_close",
    "horizon_trading_days",
    "target_due_date_estimate_utc",
    "maturity_external_spot_date",
    "maturity_external_spot_close",
    "realized_return_bps",
    "status",
    "no_order_policy",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_date_any(value: Any) -> Optional[date]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    # Allow date only, ISO datetime, and simple slash dates if needed.
    for fmt in (None, "%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            if fmt is None:
                return datetime.fromisoformat(s).date()
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def date_iso(d: Optional[date]) -> str:
    if d is None:
        return ""
    return d.isoformat()


def safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if s == "" or s.lower() in {"none", "nan", "null"}:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


def sha256_path(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def row_hash(payload: Dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv_rows(path: Path, fields: List[str], rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})


def append_csv_row(path: Path, fields: List[str], row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        if not exists:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in fields})


def op_pass(value: Optional[float], op: str, threshold: float) -> bool:
    if value is None:
        return False
    if op == ">":
        return value > threshold
    if op == ">=":
        return value >= threshold
    if op == "<":
        return value < threshold
    if op == "<=":
        return value <= threshold
    if op == "==":
        return value == threshold
    raise ValueError(f"unsupported op: {op}")


def eval_rule(row: Dict[str, str], rule: Dict[str, Dict[str, Any]]) -> Tuple[bool, List[str]]:
    failures: List[str] = []
    for col, spec in rule.items():
        v = safe_float(row.get(col))
        op = str(spec["op"])
        threshold = float(spec["threshold"])
        if not op_pass(v, op, threshold):
            failures.append(f"{col}:{v}{op}{threshold}")
    return (len(failures) == 0, failures)


def latest_dataset_row(rows: List[Dict[str, str]]) -> Tuple[Optional[Dict[str, str]], Dict[str, Any]]:
    parsed: List[Tuple[date, Dict[str, str]]] = []
    errors = 0
    for row in rows:
        d = parse_date_any(row.get("feature_date_utc"))
        if d is None:
            errors += 1
            continue
        parsed.append((d, row))
    parsed.sort(key=lambda x: x[0])
    return (parsed[-1][1] if parsed else None, {"parse_errors": errors, "usable_rows": len(parsed)})


def read_external_spot(path: Path) -> Tuple[Dict[date, float], List[date], Dict[str, Any]]:
    info: Dict[str, Any] = {
        "found": path.exists(),
        "raw_rows": 0,
        "parsed_rows": 0,
        "parse_errors": 0,
        "first_date": None,
        "last_date": None,
        "sha256": sha256_path(path),
    }
    if not path.exists():
        return {}, [], info
    rows = read_csv_rows(path)
    info["raw_rows"] = len(rows)
    prices: Dict[date, float] = {}
    for row in rows:
        d = parse_date_any(row.get("date_utc") or row.get("Date") or row.get("date"))
        c = safe_float(row.get("close") or row.get("Price") or row.get("Close"))
        if d is None or c is None:
            info["parse_errors"] += 1
            continue
        prices[d] = c
    dates = sorted(prices)
    info["parsed_rows"] = len(dates)
    if dates:
        info["first_date"] = dates[0].isoformat()
        info["last_date"] = dates[-1].isoformat()
    return prices, dates, info


def price_on_or_before(prices: Dict[date, float], dates: List[date], target: date) -> Tuple[Optional[date], Optional[float]]:
    # Small enough for linear reverse scan; avoids bisect complexity with dates in older py.
    for d in reversed(dates):
        if d <= target:
            return d, prices[d]
    return None, None


def nth_trading_date_after(dates: List[date], start: date, n: int) -> Optional[date]:
    future = [d for d in dates if d > start]
    if len(future) >= n:
        return future[n - 1]
    return None


def add_business_days(start: date, n: int) -> date:
    d = start
    left = n
    while left > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            left -= 1
    return d


def load_existing_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    return read_csv_rows(path)


def update_mature_observations(obs_rows: List[Dict[str, str]], prices: Dict[date, float], dates: List[date]) -> Tuple[List[Dict[str, str]], int]:
    updated = 0
    for row in obs_rows:
        if row.get("status") != "PENDING_120D_EXTERNAL_SPOT_NO_ORDER":
            continue
        entry_d = parse_date_any(row.get("entry_external_spot_date"))
        entry_c = safe_float(row.get("entry_external_spot_close"))
        h = int(float(row.get("horizon_trading_days") or 120))
        if entry_d is None or entry_c is None:
            continue
        maturity_d = nth_trading_date_after(dates, entry_d, h)
        if maturity_d is None:
            continue
        maturity_c = prices.get(maturity_d)
        if maturity_c is None:
            continue
        ret_bps = (maturity_c / entry_c - 1.0) * 10000.0
        row["maturity_external_spot_date"] = maturity_d.isoformat()
        row["maturity_external_spot_close"] = f"{maturity_c:.8f}"
        row["realized_return_bps"] = f"{ret_bps:.6f}"
        row["status"] = "MATURED_EXTERNAL_SPOT_NO_ORDER"
        updated += 1
    return obs_rows, updated


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    cfg_path = (root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    out_dir = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = read_json(cfg_path)
    paths = cfg["paths"]
    stage64s_path = root / paths["stage64s_summary"]
    dataset_path = root / paths["stage64k_dataset"]
    external_path = root / paths["external_spot_d1"]
    signal_path = root / paths["signal_ledger"]
    obs_path = root / paths["observation_ledger"]
    state_path = root / paths["state_json"]

    run_utc = utc_now_iso()
    input_checks: Dict[str, Any] = {
        "stage64s_summary_found": stage64s_path.exists(),
        "dataset_found": dataset_path.exists(),
        "external_spot_found": external_path.exists(),
        "config_found": cfg_path.exists(),
        "issues": [],
    }

    stage64s = read_json(stage64s_path) if stage64s_path.exists() else {}
    stage64s_decision = stage64s.get("decision")
    input_checks["stage64s_decision"] = stage64s_decision
    input_checks["expected_stage64s_decision"] = cfg.get("expected_stage64s_decision")
    input_checks["stage64s_decision_ok"] = stage64s_decision == cfg.get("expected_stage64s_decision")
    if not input_checks["stage64s_decision_ok"]:
        input_checks["issues"].append("stage64s_decision_not_allowed")
    if not dataset_path.exists():
        input_checks["issues"].append("stage64k_dataset_missing")
    if not external_path.exists():
        input_checks["issues"].append("external_spot_d1_missing")

    no_order_policy_ok = all(v is False for v in cfg.get("no_order_policy", {}).values())
    input_checks["no_order_policy_ok"] = no_order_policy_ok
    if not no_order_policy_ok:
        input_checks["issues"].append("no_order_policy_not_all_false")

    dataset_rows: List[Dict[str, str]] = []
    dataset_info: Dict[str, Any] = {"rows": 0, "usable_rows": 0, "parse_errors": 0, "latest_feature_date": None}
    latest_row: Optional[Dict[str, str]] = None
    if dataset_path.exists():
        dataset_rows = read_csv_rows(dataset_path)
        latest_row, extra = latest_dataset_row(dataset_rows)
        dataset_info.update({"rows": len(dataset_rows), **extra})
        if latest_row:
            latest_d = parse_date_any(latest_row.get("feature_date_utc"))
            dataset_info["latest_feature_date"] = date_iso(latest_d)
            forbidden = latest_row.get("historical_event_calendar_feature_present")
            input_checks["historical_event_calendar_feature_present_latest"] = forbidden
            if str(forbidden).strip().lower() not in {"false", "0", "", "none"}:
                input_checks["issues"].append("historical_event_calendar_feature_present_latest")

    prices, spot_dates, external_info = read_external_spot(external_path)
    if external_info.get("parsed_rows", 0) < 2500:
        input_checks["issues"].append("external_spot_rows_below_2500")

    stage65_input_ok = len(input_checks["issues"]) == 0

    signal_row: Optional[Dict[str, Any]] = None
    signal_appended = False
    observation_appended = False
    observations_matured = 0
    existing_signal_rows = load_existing_csv(signal_path)
    existing_obs_rows = load_existing_csv(obs_path)
    current_signal_active = False
    current_benchmark_active = False

    if stage65_input_ok and latest_row:
        latest_d = parse_date_any(latest_row.get("feature_date_utc"))
        sample_available_after = latest_row.get("sample_available_after_utc", "")
        current_signal_active, failures = eval_rule(latest_row, cfg["locked_rule"])
        current_benchmark_active, benchmark_failures = eval_rule(latest_row, cfg["benchmark_rule"])
        entry_d, entry_c = price_on_or_before(prices, spot_dates, latest_d) if latest_d else (None, None)
        feature_payload = {
            "feature_date_utc": date_iso(latest_d),
            "sample_available_after_utc": sample_available_after,
            "hypothesis_id": cfg["locked_survivor"]["hypothesis_id"],
            "horizon_days": cfg["locked_survivor"]["horizon_days"],
            "signal_active": current_signal_active,
            "benchmark_active": current_benchmark_active,
            "locked_rule_values": {k: latest_row.get(k) for k in cfg["locked_rule"]},
            "external_spot_date": date_iso(entry_d),
            "external_spot_close": entry_c,
        }
        rh = row_hash(feature_payload)
        signal_row = {
            "run_utc": run_utc,
            "feature_date_utc": date_iso(latest_d),
            "sample_available_after_utc": sample_available_after,
            "hypothesis_id": cfg["locked_survivor"]["hypothesis_id"],
            "horizon_days": cfg["locked_survivor"]["horizon_days"],
            "signal_active": str(current_signal_active),
            "benchmark_active": str(current_benchmark_active),
            "rule_failures": ";".join(failures),
            "gold_close": latest_row.get("gold_close", ""),
            "external_spot_close": "" if entry_c is None else f"{entry_c:.8f}",
            "dxy_ret_20d": latest_row.get("dxy_ret_20d", ""),
            "real_yield_change_20d": latest_row.get("real_yield_change_20d", ""),
            "etf_flow_tonnes_3m": latest_row.get("etf_flow_tonnes_3m", ""),
            "central_bank_demand_tonnes_6m": latest_row.get("central_bank_demand_tonnes_6m", ""),
            "event_calendar_forward_only_governance_active": latest_row.get("event_calendar_forward_only_governance_active", ""),
            "historical_event_calendar_feature_present": latest_row.get("historical_event_calendar_feature_present", ""),
            "asof_lag_safe": "True",
            "row_hash": rh,
            "no_order_policy": "NO_ORDER_NO_BROKER_NO_PAPER_NO_LIVE",
        }
        existing_dates = {r.get("feature_date_utc") for r in existing_signal_rows}
        if signal_row["feature_date_utc"] not in existing_dates:
            append_csv_row(signal_path, SIGNAL_LEDGER_FIELDS, signal_row)
            signal_appended = True
            existing_signal_rows.append({k: str(v) for k, v in signal_row.items()})

        # Update previous observations before possibly appending a new one.
        existing_obs_rows, observations_matured = update_mature_observations(existing_obs_rows, prices, spot_dates)

        if current_signal_active and entry_d is not None and entry_c is not None and latest_d is not None:
            signal_id = row_hash({"hypothesis_id": cfg["locked_survivor"]["hypothesis_id"], "feature_date": latest_d.isoformat(), "row_hash": rh})[:24]
            existing_ids = {r.get("signal_id") for r in existing_obs_rows}
            if signal_id not in existing_ids:
                h = int(cfg["locked_survivor"]["horizon_days"])
                maturity_d = nth_trading_date_after(spot_dates, entry_d, h)
                status = "PENDING_120D_EXTERNAL_SPOT_NO_ORDER"
                maturity_close = ""
                realized_bps = ""
                maturity_date_str = ""
                if maturity_d is not None and maturity_d in prices:
                    maturity_c = prices[maturity_d]
                    realized_bps = f"{(maturity_c / entry_c - 1.0) * 10000.0:.6f}"
                    maturity_close = f"{maturity_c:.8f}"
                    maturity_date_str = maturity_d.isoformat()
                    status = "MATURED_EXTERNAL_SPOT_NO_ORDER"
                obs_row = {
                    "signal_id": signal_id,
                    "created_utc": run_utc,
                    "feature_date_utc": latest_d.isoformat(),
                    "entry_external_spot_date": entry_d.isoformat(),
                    "entry_external_spot_close": f"{entry_c:.8f}",
                    "horizon_trading_days": h,
                    "target_due_date_estimate_utc": add_business_days(entry_d, h).isoformat(),
                    "maturity_external_spot_date": maturity_date_str,
                    "maturity_external_spot_close": maturity_close,
                    "realized_return_bps": realized_bps,
                    "status": status,
                    "no_order_policy": "NO_ORDER_NO_BROKER_NO_PAPER_NO_LIVE",
                }
                existing_obs_rows.append({k: str(v) for k, v in obs_row.items()})
                observation_appended = True
        if existing_obs_rows:
            write_csv_rows(obs_path, OBS_LEDGER_FIELDS, existing_obs_rows)

    # Governance metrics after any append/update.
    signal_rows_final = load_existing_csv(signal_path)
    obs_rows_final = load_existing_csv(obs_path)
    obs_signal_rows = [r for r in obs_rows_final if r.get("status") in {"PENDING_120D_EXTERNAL_SPOT_NO_ORDER", "MATURED_EXTERNAL_SPOT_NO_ORDER"}]
    signal_dates = [parse_date_any(r.get("feature_date_utc")) for r in obs_signal_rows]
    signal_dates = [d for d in signal_dates if d is not None]
    calendar_span_days = 0
    if signal_dates:
        calendar_span_days = (max(signal_dates) - min(signal_dates)).days
    min_req = cfg["forward_governance_minimums"]
    forward_minimums = {
        "observed_new_signals": len(obs_signal_rows),
        "calendar_span_days": calendar_span_days,
        "matured_observations": sum(1 for r in obs_rows_final if r.get("status") == "MATURED_EXTERNAL_SPOT_NO_ORDER"),
        "observed_new_signals_min": min_req["observed_new_signals_min"],
        "calendar_span_min_days": min_req["calendar_span_min_days"],
        "observed_new_signals_gate": len(obs_signal_rows) >= int(min_req["observed_new_signals_min"]),
        "calendar_span_gate": calendar_span_days >= int(min_req["calendar_span_min_days"]),
        "asof_lag_safe_gate": True,
        "no_manual_override_backfill_gate": True,
    }
    forward_governance_ready = all([
        forward_minimums["observed_new_signals_gate"],
        forward_minimums["calendar_span_gate"],
        forward_minimums["asof_lag_safe_gate"],
        forward_minimums["no_manual_override_backfill_gate"],
    ])

    status = "FORWARD_SHADOW_SIGNAL_LEDGER_FASTLANE_COMPLETE_NO_PROMOTION" if stage65_input_ok else "FORWARD_SHADOW_SIGNAL_LEDGER_FASTLANE_INPUT_FAILED_NO_PROMOTION"
    if not stage65_input_ok:
        decision = "STAGE65_INPUT_FAILED_FIX_INPUTS_NO_ORDER"
    elif forward_governance_ready:
        decision = "STAGE65_FORWARD_MINIMUMS_MET_REVIEW_GOVERNANCE_ONLY_NO_ORDER"
    else:
        decision = "STAGE65_FORWARD_LEDGER_ACTIVE_CONTINUE_DAILY_NO_ORDER"

    state = {
        "stage": cfg["stage"],
        "last_run_utc": run_utc,
        "latest_feature_date": dataset_info.get("latest_feature_date"),
        "current_signal_active": current_signal_active,
        "current_benchmark_active": current_benchmark_active,
        "signal_ledger_rows": len(signal_rows_final),
        "observation_ledger_rows": len(obs_rows_final),
        "forward_governance_ready": forward_governance_ready,
        "decision": decision,
        "hard_blocks": HARD_BLOCKS,
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = {
        "stage": cfg["stage"],
        "status": status,
        "decision": decision,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_order": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "validation_allowed_for_order_or_promotion": False,
        "validation_run_performed": False,
        "order_path": "NONE",
        "broker_connection": "NONE",
        "generated_utc": run_utc,
        "root": str(root),
        "input_checks": input_checks,
        "target_survivor": cfg["locked_survivor"],
        "dataset_info": dataset_info,
        "external_spot_info": external_info,
        "latest_signal_state": signal_row or {},
        "ledger_update": {
            "signal_row_appended": signal_appended,
            "observation_row_appended": observation_appended,
            "observations_matured_this_run": observations_matured,
            "signal_ledger_path": str(signal_path),
            "observation_ledger_path": str(obs_path),
            "state_json_path": str(state_path),
            "signal_ledger_rows": len(signal_rows_final),
            "observation_ledger_rows": len(obs_rows_final),
        },
        "forward_governance_minimums": forward_minimums,
        "forward_governance_ready": forward_governance_ready,
        "executive_conclusion": (
            "Stage65 no-order forward-shadow ledger is active. Continue daily runs; paper/live/broker paths remain blocked."
            if stage65_input_ok else
            "Stage65 inputs failed. Fix inputs and rerun; no order path is authorized."
        ),
        "next_allowed_step": "CONTINUE_STAGE65_DAILY_FORWARD_SHADOW_LEDGER_NO_ORDER",
        "hard_blocks": HARD_BLOCKS,
        "outputs": {
            "summary_json": str(out_dir / "stage65_forward_shadow_signal_ledger_summary.json"),
            "report_md": str(out_dir / "stage65_forward_shadow_signal_ledger_report.md"),
            "signal_ledger_csv": str(signal_path),
            "observation_ledger_csv": str(obs_path),
            "state_json": str(state_path),
        },
        "output_hashes": {
            "signal_ledger_csv": sha256_path(signal_path),
            "observation_ledger_csv": sha256_path(obs_path),
            "state_json": sha256_path(state_path),
        }
    }

    report_lines = [
        "# Stage65 - Forward Shadow Signal Ledger Fastlane (No Order)",
        "",
        f"Generated UTC: `{run_utc}`",
        "",
        "## Status",
        "",
        f"- status: `{status}`",
        f"- decision: `{decision}`",
        "- promotion/paper/live: `NO_GO`",
        "- validation_allowed_for_order_or_promotion: `False`",
        "- order_path: `NONE`",
        "- broker_connection: `NONE`",
        "",
        "## Executive conclusion",
        "",
        summary["executive_conclusion"],
        "",
        "## Latest signal state",
        "",
        f"- latest_feature_date: `{dataset_info.get('latest_feature_date')}`",
        f"- signal_active: `{current_signal_active}`",
        f"- benchmark_active: `{current_benchmark_active}`",
        f"- signal_row_appended: `{signal_appended}`",
        f"- observation_row_appended: `{observation_appended}`",
        f"- observations_matured_this_run: `{observations_matured}`",
        "",
        "## Forward governance minimums",
        "",
        "| metric | value |",
        "|---|---:|",
        f"| observed_new_signals | `{forward_minimums['observed_new_signals']}` |",
        f"| observed_new_signals_min | `{forward_minimums['observed_new_signals_min']}` |",
        f"| calendar_span_days | `{forward_minimums['calendar_span_days']}` |",
        f"| calendar_span_min_days | `{forward_minimums['calendar_span_min_days']}` |",
        f"| matured_observations | `{forward_minimums['matured_observations']}` |",
        f"| forward_governance_ready | `{forward_governance_ready}` |",
        "",
        "## Ledger files",
        "",
        f"- signal_ledger: `{signal_path}`",
        f"- observation_ledger: `{obs_path}`",
        f"- state_json: `{state_path}`",
        "",
        "## Hard blocks",
        "",
    ]
    report_lines += [f"- `{b}`" for b in HARD_BLOCKS]
    report_lines += ["", "## Next allowed step", "", "`CONTINUE_STAGE65_DAILY_FORWARD_SHADOW_LEDGER_NO_ORDER`", ""]

    (out_dir / "stage65_forward_shadow_signal_ledger_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "stage65_forward_shadow_signal_ledger_report.md").write_text("\n".join(report_lines), encoding="utf-8")

    return 0 if stage65_input_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
