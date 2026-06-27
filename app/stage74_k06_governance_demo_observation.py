#!/usr/bin/env python3
"""Stage74 K06 Governance Demo Observation Protocol.

No broker, no EA, no paper-live, no live, no automated order.
This stage converts a historically validated K06 candidate into an operational
review-only observation protocol. It checks validation locks, data freshness,
latest signal state, and emits a review-only activation packet if the signal is
active.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

STAGE = "Stage74_K06_GOVERNANCE_DEMO_OBSERVATION"

REQUIRED_COLUMNS = [
    "feature_date_utc",
    "gold_close",
    "gold_sma20_over_50",
    "dxy_ret_20d",
    "real_yield_change_20d",
]

K06_CONDITIONS = [
    {"column": "gold_sma20_over_50", "operator": ">", "threshold": 0.0},
    {"column": "dxy_ret_20d", "operator": ">", "threshold": 0.0},
    {"column": "real_yield_change_20d", "operator": "<", "threshold": 0.0},
]

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE74",
    "NO_THRESHOLD_TUNING_FROM_GOVERNANCE_BRIDGE",
    "NO_PROMOTION_FROM_STAGE74_WITHOUT_SEPARATE_MANUAL_AUTHORIZATION",
]

DEFAULT_CONFIG: Dict[str, Any] = {
    "macro_path": "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv",
    "date_col": "feature_date_utc",
    "price_col": "gold_close",
    "thesis_id": "K06_RESILIENT_GOLD_VS_DXY",
    "family": "GOLD_RESILIENCE_AGAINST_DXY",
    "direction": "long",
    "horizon_trading_days": 120,
    "entry_cooldown_trading_days": 120,
    "cost_bps_total_reference": 50.0,
    "max_stale_calendar_days": 7,
    "current_date_utc": None,
    "lock_files": [
        {
            "stage": "Stage70B",
            "path": "reports/stage70b_champion_hard_audit/stage70b_champion_hard_audit_summary.json",
            "required_disposition": "PROMOTE_TO_NO_ORDER_SHADOW_CANDIDATE",
        },
        {
            "stage": "Stage71",
            "path": "reports/stage71_locked_historical_forward_test/stage71_locked_historical_forward_test_summary.json",
            "required_disposition": "K06_PASSES_LOCKED_HISTORICAL_FORWARD",
        },
        {
            "stage": "Stage72",
            "path": "reports/stage72_historical_daily_replay/stage72_historical_daily_replay_summary.json",
            "required_disposition": "K06_PASSES_HISTORICAL_DAILY_REPLAY",
        },
        {
            "stage": "Stage73B",
            "path": "reports/stage73b_corrected_asof_validation_bridge/stage73b_corrected_asof_validation_bridge_summary.json",
            "required_disposition": "K06_PASSES_CORRECTED_ASOF_VALIDATION",
        },
    ],
    "reference_metric_sources": {
        "stage71_overall_mean_bps": "reports/stage71_locked_historical_forward_test/stage71_locked_historical_forward_test_summary.json",
        "stage72_replay_mean_bps": "reports/stage72_historical_daily_replay/stage72_historical_daily_replay_summary.json",
        "stage73b_pre_asof_known_mean_bps": "reports/stage73b_corrected_asof_validation_bridge/stage73b_corrected_asof_validation_bridge_summary.json",
    },
    "output_ledger_path": "data/forward_shadow/stage74_k06_governance_demo_observation_ledger.csv",
    "activation_packet_prefix": "stage74_k06_review_only_activation_packet",
}


@dataclass
class LockCheck:
    stage: str
    path: str
    exists: bool
    read_ok: bool
    required_disposition: str
    actual_disposition: Optional[str]
    matches_required: bool
    issue: Optional[str] = None


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=False)
        f.write("\n")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=STAGE)
    p.add_argument("--root", default=".", help="Repository root")
    p.add_argument("--config", default="configs/stage74_k06_governance_demo_observation.json")
    p.add_argument("--out", default="reports/stage74_k06_governance_demo_observation")
    return p.parse_args()


def load_config(root: Path, config_arg: str) -> Dict[str, Any]:
    cfg = dict(DEFAULT_CONFIG)
    config_path = Path(config_arg)
    if not config_path.is_absolute():
        config_path = root / config_path
    if config_path.exists():
        user_cfg = load_json(config_path)
        cfg.update(user_cfg)
    return cfg


def parse_date_value(value: Any) -> date:
    ts = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(ts):
        raise ValueError(f"Could not parse date: {value!r}")
    return ts.date()


def now_date_utc(cfg: Dict[str, Any]) -> date:
    override = cfg.get("current_date_utc")
    if override:
        return parse_date_value(override)
    return datetime.now(timezone.utc).date()


def check_locks(root: Path, cfg: Dict[str, Any]) -> List[LockCheck]:
    checks: List[LockCheck] = []
    for item in cfg.get("lock_files", []):
        rel = item["path"]
        path = Path(rel)
        if not path.is_absolute():
            path = root / path
        exists = path.exists()
        read_ok = False
        actual = None
        issue = None
        if exists:
            try:
                payload = load_json(path)
                read_ok = True
                actual = payload.get("disposition") or payload.get("decision")
            except Exception as exc:  # pragma: no cover - defensive
                issue = f"READ_FAIL:{exc.__class__.__name__}:{exc}"
        else:
            issue = "MISSING_LOCK_FILE"
        required = item.get("required_disposition", "")
        matches = bool(read_ok and actual == required)
        if read_ok and not matches:
            issue = f"LOCK_DISPOSITION_MISMATCH:{actual}!={required}"
        checks.append(
            LockCheck(
                stage=item.get("stage", rel),
                path=str(path),
                exists=exists,
                read_ok=read_ok,
                required_disposition=required,
                actual_disposition=actual,
                matches_required=matches,
                issue=issue,
            )
        )
    return checks


def load_macro(root: Path, cfg: Dict[str, Any]) -> Tuple[pd.DataFrame, Path]:
    macro_path = Path(cfg["macro_path"])
    if not macro_path.is_absolute():
        macro_path = root / macro_path
    if not macro_path.exists():
        raise FileNotFoundError(f"Macro dataset not found: {macro_path}")
    df = pd.read_csv(macro_path)
    if cfg["date_col"] not in df.columns:
        raise ValueError(f"Missing date_col {cfg['date_col']} in macro dataset")
    df[cfg["date_col"]] = pd.to_datetime(df[cfg["date_col"]], utc=True, errors="coerce")
    df = df.dropna(subset=[cfg["date_col"]]).sort_values(cfg["date_col"]).reset_index(drop=True)
    return df, macro_path


def eval_condition(value: Any, op: str, threshold: float) -> bool:
    if pd.isna(value):
        return False
    v = float(value)
    if op == ">":
        return v > threshold
    if op == "<":
        return v < threshold
    if op == ">=":
        return v >= threshold
    if op == "<=":
        return v <= threshold
    if op == "==":
        return v == threshold
    raise ValueError(f"Unsupported operator: {op}")


def latest_signal(df: pd.DataFrame, cfg: Dict[str, Any]) -> Dict[str, Any]:
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    latest = df.iloc[-1] if len(df) else None
    missing_values: List[str] = []
    condition_results: List[Dict[str, Any]] = []
    failures: List[str] = []
    if latest is not None:
        for col in REQUIRED_COLUMNS:
            if col in df.columns and pd.isna(latest[col]):
                missing_values.append(col)
        for cond in K06_CONDITIONS:
            col = cond["column"]
            value = latest[col] if col in df.columns else None
            passed = False if col not in df.columns else eval_condition(value, cond["operator"], cond["threshold"])
            if not passed:
                failures.append(f"{col}:{value}{cond['operator']}{cond['threshold']}")
            condition_results.append(
                {
                    "column": col,
                    "operator": cond["operator"],
                    "threshold": cond["threshold"],
                    "value": None if col not in df.columns or pd.isna(value) else float(value),
                    "passed": bool(passed),
                }
            )
    signal_active = bool((not missing_cols) and (not missing_values) and all(r["passed"] for r in condition_results))
    latest_date = latest[cfg["date_col"]].date().isoformat() if latest is not None else None
    return {
        "latest_feature_date_utc": latest_date,
        "signal_active": signal_active,
        "condition_results": condition_results,
        "rule_failures": failures,
        "missing_columns": missing_cols,
        "missing_values": missing_values,
    }


def freshness_status(latest_date_iso: Optional[str], cfg: Dict[str, Any]) -> Dict[str, Any]:
    if not latest_date_iso:
        return {"current_date_utc": now_date_utc(cfg).isoformat(), "age_calendar_days": None, "fresh": False}
    current = now_date_utc(cfg)
    latest = parse_date_value(latest_date_iso)
    age = (current - latest).days
    return {
        "current_date_utc": current.isoformat(),
        "latest_feature_date_utc": latest.isoformat(),
        "age_calendar_days": age,
        "max_stale_calendar_days": int(cfg.get("max_stale_calendar_days", 7)),
        "fresh": bool(age >= 0 and age <= int(cfg.get("max_stale_calendar_days", 7))),
    }


def extract_reference_metrics(root: Path, cfg: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    # Stage71 overall
    try:
        p = root / cfg["reference_metric_sources"]["stage71_overall_mean_bps"]
        j = load_json(p)
        out["stage71_overall_mean_net_return_bps"] = j.get("overall_metrics", {}).get("mean_net_return_bps")
        out["stage71_overall_win_rate"] = j.get("overall_metrics", {}).get("win_rate")
    except Exception:
        out["stage71_overall_mean_net_return_bps"] = None
        out["stage71_overall_win_rate"] = None
    # Stage72 replay
    try:
        p = root / cfg["reference_metric_sources"]["stage72_replay_mean_bps"]
        j = load_json(p)
        out["stage72_replay_mean_net_return_bps"] = j.get("matured_outcome_metrics", {}).get("mean_net_return_bps")
        out["stage72_replay_win_rate"] = j.get("matured_outcome_metrics", {}).get("win_rate")
        out["stage72_final_holdout_mean_net_return_bps"] = j.get("final_holdout_matured_outcome_metrics", {}).get("mean_net_return_bps")
    except Exception:
        out["stage72_replay_mean_net_return_bps"] = None
        out["stage72_replay_win_rate"] = None
        out["stage72_final_holdout_mean_net_return_bps"] = None
    # Stage73B pre-asof conservative expectation
    try:
        p = root / cfg["reference_metric_sources"]["stage73b_pre_asof_known_mean_bps"]
        j = load_json(p)
        pre = j.get("asof_metrics", {}).get("pre_asof_known_matured_calibration", {})
        out["stage73b_pre_asof_known_mean_net_return_bps"] = pre.get("mean_net_return_bps")
        out["stage73b_pre_asof_known_win_rate"] = pre.get("win_rate")
        out["stage73b_pre_asof_known_entry_rate_per_252d"] = pre.get("entry_rate_per_252d")
    except Exception:
        out["stage73b_pre_asof_known_mean_net_return_bps"] = None
        out["stage73b_pre_asof_known_win_rate"] = None
        out["stage73b_pre_asof_known_entry_rate_per_252d"] = None
    return out


def append_ledger(ledger_path: Path, row: Dict[str, Any]) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "generated_utc",
        "stage",
        "decision",
        "disposition",
        "latest_feature_date_utc",
        "signal_active",
        "data_fresh",
        "lock_pass_count",
        "lock_total_count",
        "rule_failures",
        "activation_packet_json",
        "activation_packet_md",
    ]
    exists = ledger_path.exists()
    with ledger_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in fieldnames})


def build_activation_packet(
    out_dir: Path,
    cfg: Dict[str, Any],
    latest: Dict[str, Any],
    reference_metrics: Dict[str, Any],
    generated_utc: str,
) -> Dict[str, str]:
    prefix = cfg.get("activation_packet_prefix", "stage74_k06_review_only_activation_packet")
    packet = {
        "stage": STAGE,
        "generated_utc": generated_utc,
        "packet_type": "REVIEW_ONLY_ACTIVATION_PACKET_NO_ORDER",
        "thesis_id": cfg["thesis_id"],
        "family": cfg["family"],
        "direction": cfg["direction"],
        "horizon_trading_days": cfg["horizon_trading_days"],
        "entry_cooldown_trading_days": cfg["entry_cooldown_trading_days"],
        "cost_bps_total_reference": cfg["cost_bps_total_reference"],
        "latest_signal_snapshot": latest,
        "reference_metrics": reference_metrics,
        "operator_required_action": "Manual review only. Do not place order, do not route to broker, do not trigger EA.",
        "hard_blocks": HARD_BLOCKS,
    }
    json_path = out_dir / f"{prefix}.json"
    md_path = out_dir / f"{prefix}.md"
    write_json(json_path, packet)
    md = [
        "# Stage74 K06 Review-Only Activation Packet",
        "",
        "## Status",
        "- packet_type: `REVIEW_ONLY_ACTIVATION_PACKET_NO_ORDER`",
        f"- generated_utc: `{generated_utc}`",
        f"- thesis_id: `{cfg['thesis_id']}`",
        f"- latest_feature_date_utc: `{latest.get('latest_feature_date_utc')}`",
        "",
        "## Rule",
        f"- conditions: `gold_sma20_over_50>0; dxy_ret_20d>0; real_yield_change_20d<0`",
        f"- horizon_trading_days: `{cfg['horizon_trading_days']}`",
        "",
        "## Latest condition results",
    ]
    for item in latest.get("condition_results", []):
        md.append(
            f"- `{item['column']}` {item['operator']} `{item['threshold']}`: value=`{item['value']}`, passed=`{item['passed']}`"
        )
    md += [
        "",
        "## Reference metrics",
    ]
    for k, v in reference_metrics.items():
        md.append(f"- {k}: `{v}`")
    md += [
        "",
        "## Hard blocks",
    ]
    for b in HARD_BLOCKS:
        md.append(f"- `{b}`")
    md += [
        "",
        "## Operator instruction",
        "Manual review only. This packet cannot authorize paper, demo, EA, broker, paper-live, or live orders.",
    ]
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return {"activation_packet_json": str(json_path), "activation_packet_md": str(md_path)}


def make_report(summary: Dict[str, Any]) -> str:
    lines = [
        "# Stage74 K06 Governance Demo Observation",
        "",
        "## Decision",
        f"- status: `{summary['status']}`",
        f"- decision: `{summary['decision']}`",
        f"- classification: `{summary['classification']}`",
        f"- disposition: `{summary['disposition']}`",
        "",
        "## Governance role",
        "This stage converts a historically validated K06 thesis into a no-order operational observation protocol. It cannot authorize orders.",
        "",
        "## Lock checks",
    ]
    for lock in summary.get("lock_checks", []):
        lines.append(
            f"- `{lock['stage']}`: exists=`{lock['exists']}`, read_ok=`{lock['read_ok']}`, matches_required=`{lock['matches_required']}`, actual=`{lock['actual_disposition']}`"
        )
    lines += [
        "",
        "## Freshness",
        f"- latest_feature_date_utc: `{summary['latest_signal_snapshot'].get('latest_feature_date_utc')}`",
        f"- current_date_utc: `{summary['freshness'].get('current_date_utc')}`",
        f"- age_calendar_days: `{summary['freshness'].get('age_calendar_days')}`",
        f"- fresh: `{summary['freshness'].get('fresh')}`",
        "",
        "## Latest K06 signal",
        f"- signal_active: `{summary['latest_signal_snapshot'].get('signal_active')}`",
        f"- rule_failures: `{'; '.join(summary['latest_signal_snapshot'].get('rule_failures', []))}`",
        "",
        "## Reference metrics",
    ]
    for k, v in summary.get("reference_metrics", {}).items():
        lines.append(f"- {k}: `{v}`")
    lines += [
        "",
        "## Issues",
    ]
    if summary.get("issues"):
        for i in summary["issues"]:
            lines.append(f"- {i}")
    else:
        lines.append("- none")
    lines += [
        "",
        "## Cautions",
    ]
    if summary.get("cautions"):
        for c in summary["cautions"]:
            lines.append(f"- {c}")
    else:
        lines.append("- none")
    lines += [
        "",
        "## Hard blocks",
    ]
    for b in HARD_BLOCKS:
        lines.append(f"- `{b}`")
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    root = Path(args.root).resolve()
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = load_config(root, args.config)

    generated_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    issues: List[str] = []
    cautions: List[str] = []

    lock_checks = check_locks(root, cfg)
    lock_pass_count = sum(1 for x in lock_checks if x.matches_required)
    lock_total_count = len(lock_checks)
    for lock in lock_checks:
        if not lock.matches_required:
            issues.append(f"LOCK_NOT_READY:{lock.stage}:{lock.issue}")

    df, macro_path = load_macro(root, cfg)
    missing_dataset_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_dataset_cols:
        issues.append("MISSING_REQUIRED_COLUMNS:" + ",".join(missing_dataset_cols))

    latest = latest_signal(df, cfg)
    if latest["missing_columns"]:
        issues.append("MISSING_SIGNAL_COLUMNS:" + ",".join(latest["missing_columns"]))
    if latest["missing_values"]:
        issues.append("MISSING_LATEST_VALUES:" + ",".join(latest["missing_values"]))

    freshness = freshness_status(latest.get("latest_feature_date_utc"), cfg)
    if not freshness.get("fresh"):
        issues.append("STALE_OR_INVALID_MACRO_DATA")

    reference_metrics = extract_reference_metrics(root, cfg)

    activation_paths = {"activation_packet_json": None, "activation_packet_md": None}
    all_locks_ready = lock_total_count > 0 and lock_pass_count == lock_total_count
    if issues:
        status = "STAGE74_COMPLETE_NO_PROMOTION"
        decision = "STAGE74_K06_GOVERNANCE_BLOCKED_NO_ORDER"
        classification = "S74_K06_GOVERNANCE_BLOCKED"
        disposition = "GOVERNANCE_BLOCKED_NO_ORDER"
    elif all_locks_ready and latest["signal_active"]:
        status = "STAGE74_COMPLETE_NO_PROMOTION"
        decision = "STAGE74_K06_REVIEW_ONLY_ACTIVATION_PACKET_READY_NO_ORDER"
        classification = "S74_K06_REVIEW_ONLY_PACKET_READY"
        disposition = "REVIEW_ONLY_ACTIVATION_PACKET_READY_NO_ORDER"
        activation_paths = build_activation_packet(out_dir, cfg, latest, reference_metrics, generated_utc)
    elif all_locks_ready and not latest["signal_active"]:
        status = "STAGE74_COMPLETE_NO_PROMOTION"
        decision = "STAGE74_K06_GOVERNANCE_READY_WAIT_SIGNAL_NO_ORDER"
        classification = "S74_K06_GOVERNANCE_READY_WAIT_SIGNAL"
        disposition = "GOVERNANCE_READY_WAIT_SIGNAL_NO_ORDER"
    else:
        status = "STAGE74_COMPLETE_NO_PROMOTION"
        decision = "STAGE74_K06_GOVERNANCE_BLOCKED_NO_ORDER"
        classification = "S74_K06_GOVERNANCE_BLOCKED"
        disposition = "GOVERNANCE_BLOCKED_NO_ORDER"

    summary: Dict[str, Any] = {
        "stage": STAGE,
        "root": str(root),
        "config": str((root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)),
        "generated_utc": generated_utc,
        "status": status,
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
        "governance_role": "No-order operational observation protocol for historically validated K06.",
        "champion": {
            "thesis_id": cfg["thesis_id"],
            "family": cfg["family"],
            "direction": cfg["direction"],
            "horizon_trading_days": cfg["horizon_trading_days"],
            "entry_cooldown_trading_days": cfg["entry_cooldown_trading_days"],
            "conditions_text": "gold_sma20_over_50>0.0;dxy_ret_20d>0.0;real_yield_change_20d<0.0",
            "cost_bps_total_reference": cfg["cost_bps_total_reference"],
        },
        "macro_dataset": {
            "path": str(macro_path),
            "rows": int(len(df)),
            "date_col": cfg["date_col"],
            "price_col": cfg["price_col"],
            "min_date": df[cfg["date_col"]].min().date().isoformat() if len(df) else None,
            "max_date": df[cfg["date_col"]].max().date().isoformat() if len(df) else None,
            "sha256": sha256_file(macro_path),
        },
        "lock_checks": [x.__dict__ for x in lock_checks],
        "lock_pass_count": lock_pass_count,
        "lock_total_count": lock_total_count,
        "freshness": freshness,
        "latest_signal_snapshot": latest,
        "reference_metrics": reference_metrics,
        "activation_packet": activation_paths,
        "issues": issues,
        "cautions": cautions,
        "hard_blocks": HARD_BLOCKS,
        "operator_instructions": [
            "Stage74 cannot authorize orders.",
            "If K06 is active, use the activation packet for review only; do not route to broker, EA, paper-live, or live.",
            "Do not retune K06 thresholds here.",
            "Future data is used for operational freshness only, not as the primary statistical proof mechanism.",
        ],
        "outputs": {},
    }

    summary_path = out_dir / "stage74_k06_governance_demo_observation_summary.json"
    report_path = out_dir / "stage74_k06_governance_demo_observation_report.md"
    ledger_path = Path(cfg["output_ledger_path"])
    if not ledger_path.is_absolute():
        ledger_path = root / ledger_path

    append_ledger(
        ledger_path,
        {
            "generated_utc": generated_utc,
            "stage": STAGE,
            "decision": decision,
            "disposition": disposition,
            "latest_feature_date_utc": latest.get("latest_feature_date_utc"),
            "signal_active": latest.get("signal_active"),
            "data_fresh": freshness.get("fresh"),
            "lock_pass_count": lock_pass_count,
            "lock_total_count": lock_total_count,
            "rule_failures": ";".join(latest.get("rule_failures", [])),
            "activation_packet_json": activation_paths.get("activation_packet_json"),
            "activation_packet_md": activation_paths.get("activation_packet_md"),
        },
    )

    summary["outputs"] = {
        "summary_json": str(summary_path),
        "report_md": str(report_path),
        "ledger_csv": str(ledger_path),
        "activation_packet_json": activation_paths.get("activation_packet_json"),
        "activation_packet_md": activation_paths.get("activation_packet_md"),
    }

    write_json(summary_path, summary)
    report_path.write_text(make_report(summary), encoding="utf-8")
    print(json.dumps({"status": status, "decision": decision, "classification": classification, "summary_json": str(summary_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
