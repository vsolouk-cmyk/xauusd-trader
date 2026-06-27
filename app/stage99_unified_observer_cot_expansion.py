#!/usr/bin/env python3
"""
Stage99 unified observer COT expansion.

Observer-only bridge writer. It expands the unified observer from the five-rule
Stage88/Stage87 portfolio to six rules by adding the Stage98-selected COT rule:
C96_07_CB_SUPPORT_NOT_CROWDED_H120.

No orders, no broker connection, no MT5 execution action.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_ORDER_SEND_IN_EA",
    "OBSERVER_ONLY_EA",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE99",
    "NO_THRESHOLD_TUNING_FROM_UNIFIED_COT_OBSERVER_EXPANSION",
]

RULES = [
    {
        "rule_id": "K06_RESILIENT_GOLD_VS_DXY_H120",
        "short_id": "K06",
        "label": "K06_RESILIENT_GOLD_VS_DXY",
        "priority": 1,
        "horizon_trading_days": 120,
        "conditions": [
            ("gold_sma20_over_50", ">", 0.0),
            ("dxy_ret_20d", ">", 0.0),
            ("real_yield_change_20d", "<", 0.0),
        ],
    },
    {
        "rule_id": "K03_SAFE_HAVEN_REALYIELD_H120",
        "short_id": "K03",
        "label": "K03_WGC_RISK_UNCERTAINTY_SAFE_HAVEN",
        "priority": 2,
        "horizon_trading_days": 120,
        "conditions": [
            ("vix_change_20d", ">", 0.0),
            ("real_yield_change_20d", "<", 0.0),
        ],
    },
    {
        "rule_id": "K07_DXY_TREND_RELIEF_GOLD_TREND_H120",
        "short_id": "K07",
        "label": "K07_DXY_TREND_RELIEF_GOLD_TREND",
        "priority": 3,
        "horizon_trading_days": 120,
        "conditions": [
            ("gold_sma20_over_50", ">", 0.0),
            ("dxy_sma20_over_50", "<", 0.0),
        ],
    },
    {
        "rule_id": "S83_14_REALYIELD_120D_DOWN_GOLD_NOT_TRENDING_H120",
        "short_id": "S83_14",
        "label": "REALYIELD_120D_DOWN_GOLD_NOT_TRENDING",
        "priority": 4,
        "horizon_trading_days": 120,
        "conditions": [
            ("real_yield_change_120d", "<", 0.0),
            ("gold_sma20_over_50", "<", 0.0),
        ],
    },
    {
        "rule_id": "S83_13_DXY_120D_DOWN_GOLD_NOT_TRENDING_H120",
        "short_id": "S83_13",
        "label": "DXY_120D_DOWN_GOLD_NOT_TRENDING",
        "priority": 5,
        "horizon_trading_days": 120,
        "conditions": [
            ("dxy_ret_120d", "<", 0.0),
            ("gold_sma20_over_50", "<", 0.0),
        ],
    },
    {
        "rule_id": "C96_07_CB_SUPPORT_NOT_CROWDED_H120",
        "short_id": "C96_07",
        "label": "CB_SUPPORT_NOT_CROWDED",
        "priority": 6,
        "horizon_trading_days": 120,
        "conditions": [
            ("cot_mm_net_z", "<", 1.0),
            ("central_bank_demand_tonnes_3m", ">", 0.0),
            ("gold_ret_20d", "<", 0.0),
        ],
    },
]

COT_ALIAS_CANDIDATES = {
    "cot_mm_net_z": [
        "cot_mm_net_z",
        "managed_money_net_pct_oi_z_156w",
        "managed_money_net_z_156w",
        "managed_money_net_pct_oi_z",
        "managed_money_net_z",
    ],
    "cot_mm_net_z_change_4w": [
        "cot_mm_net_z_change_4w",
        "managed_money_net_pct_oi_change_4w",
        "managed_money_net_change_4w",
        "managed_money_net_pct_oi_z_change_4w",
        "managed_money_net_z_change_4w",
    ],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def relpath(root: Path, value: str) -> Path:
    p = Path(value).expanduser()
    if p.is_absolute():
        return p
    return root / p


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def safe_numeric(s: pd.Series) -> pd.Series:
    converted = pd.to_numeric(s, errors="coerce")
    if converted.notna().sum() == 0 and s.notna().sum() > 0:
        return s
    return converted


def parse_dt(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, errors="coerce")


def normalize_date_column(df: pd.DataFrame, candidates: Iterable[str], out: str) -> pd.DataFrame:
    for c in candidates:
        if c in df.columns:
            df[out] = parse_dt(df[c])
            return df
    raise ValueError(f"No date column found from candidates: {list(candidates)}")


def add_macro_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "feature_date_utc" not in df.columns:
        if "date_utc" in df.columns:
            df["feature_date_utc"] = df["date_utc"]
        else:
            raise ValueError("macro dataset missing feature_date_utc/date_utc")
    df["feature_date_utc"] = parse_dt(df["feature_date_utc"])
    df = df.sort_values("feature_date_utc").reset_index(drop=True)

    for c in df.columns:
        if c not in {"feature_date_utc", "date_utc", "source", "available_after_utc", "sample_available_after_utc"}:
            df[c] = safe_numeric(df[c])

    if "gold_close" not in df.columns:
        if "close" in df.columns:
            df["gold_close"] = safe_numeric(df["close"])
        else:
            raise ValueError("macro dataset missing gold_close/close")

    if "gold_ret_20d" not in df.columns:
        df["gold_ret_20d"] = df["gold_close"].pct_change(20)
    if "gold_sma20" not in df.columns:
        df["gold_sma20"] = df["gold_close"].rolling(20, min_periods=20).mean()
    if "gold_sma50" not in df.columns:
        df["gold_sma50"] = df["gold_close"].rolling(50, min_periods=50).mean()
    if "gold_sma20_over_50" not in df.columns:
        df["gold_sma20_over_50"] = (df["gold_sma20"] / df["gold_sma50"]) - 1.0

    if "dxy" in df.columns:
        if "dxy_ret_20d" not in df.columns:
            df["dxy_ret_20d"] = df["dxy"].pct_change(20)
        if "dxy_ret_120d" not in df.columns:
            df["dxy_ret_120d"] = df["dxy"].pct_change(120)
        if "dxy_sma20" not in df.columns:
            df["dxy_sma20"] = df["dxy"].rolling(20, min_periods=20).mean()
        if "dxy_sma50" not in df.columns:
            df["dxy_sma50"] = df["dxy"].rolling(50, min_periods=50).mean()
        if "dxy_sma20_over_50" not in df.columns:
            df["dxy_sma20_over_50"] = (df["dxy_sma20"] / df["dxy_sma50"]) - 1.0

    if "real_yield" in df.columns:
        if "real_yield_change_20d" not in df.columns:
            df["real_yield_change_20d"] = df["real_yield"].diff(20)
        if "real_yield_change_120d" not in df.columns:
            df["real_yield_change_120d"] = df["real_yield"].diff(120)

    if "vix" in df.columns and "vix_change_20d" not in df.columns:
        df["vix_change_20d"] = df["vix"].diff(20)

    return df


def load_cot(root: Path, cfg: Dict[str, Any]) -> pd.DataFrame:
    p = relpath(root, cfg["cot_dataset"])
    if not p.exists():
        raise FileNotFoundError(f"COT dataset not found: {p}")
    df = pd.read_csv(p)
    df.columns = [str(c).strip() for c in df.columns]
    df = normalize_date_column(df, ["report_date_utc", "report_date", "date_utc"], "report_date_utc")
    if "available_after_utc" in df.columns:
        df["cot_available_after_utc"] = parse_dt(df["available_after_utc"])
    elif "cot_available_after_utc" in df.columns:
        df["cot_available_after_utc"] = parse_dt(df["cot_available_after_utc"])
    else:
        lag_days = int(cfg.get("cot_available_lag_days_if_missing", 3))
        df["cot_available_after_utc"] = df["report_date_utc"] + pd.Timedelta(days=lag_days)

    for out_col, candidates in COT_ALIAS_CANDIDATES.items():
        if out_col in df.columns:
            df[out_col] = safe_numeric(df[out_col])
            continue
        for src in candidates:
            if src in df.columns:
                df[out_col] = safe_numeric(df[src])
                break

    for c in df.columns:
        if c not in {"report_date_utc", "available_after_utc", "cot_available_after_utc", "market_and_exchange_names", "contract_market_name"}:
            df[c] = safe_numeric(df[c])

    df = df.dropna(subset=["report_date_utc", "cot_available_after_utc"]).sort_values("cot_available_after_utc")
    return df.reset_index(drop=True)


def build_joined(root: Path, cfg: Dict[str, Any]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    macro_path = relpath(root, cfg["macro_dataset"])
    if not macro_path.exists():
        raise FileNotFoundError(f"macro dataset not found: {macro_path}")
    macro = pd.read_csv(macro_path)
    macro = add_macro_features(macro)
    cot = load_cot(root, cfg)

    macro_sorted = macro.sort_values("feature_date_utc").reset_index(drop=True)
    cot_sorted = cot.sort_values("cot_available_after_utc").reset_index(drop=True)
    joined = pd.merge_asof(
        macro_sorted,
        cot_sorted,
        left_on="feature_date_utc",
        right_on="cot_available_after_utc",
        direction="backward",
    )

    lookahead = int((joined["cot_available_after_utc"].notna() & (joined["cot_available_after_utc"] > joined["feature_date_utc"])).sum())
    meta = {
        "macro_rows": int(len(macro)),
        "macro_min_date": str(macro["feature_date_utc"].min().date()) if len(macro) else None,
        "macro_max_date": str(macro["feature_date_utc"].max().date()) if len(macro) else None,
        "cot_rows": int(len(cot)),
        "cot_min_report_date": str(cot["report_date_utc"].min().date()) if len(cot) else None,
        "cot_max_report_date": str(cot["report_date_utc"].max().date()) if len(cot) else None,
        "joined_rows": int(len(joined)),
        "joined_cot_available_rows": int(joined["cot_available_after_utc"].notna().sum()),
        "lookahead_violations": lookahead,
        "macro_sha256": sha256_file(macro_path),
        "cot_sha256": sha256_file(relpath(root, cfg["cot_dataset"])),
    }
    return joined, meta


def eval_condition(value: Any, op: str, threshold: float) -> Tuple[bool, str, Optional[float]]:
    try:
        v = float(value)
    except Exception:
        return False, "missing", None
    if math.isnan(v):
        return False, "missing", None
    if op == ">":
        return v > threshold, "ok" if v > threshold else f"{v}>{threshold}", v
    if op == "<":
        return v < threshold, "ok" if v < threshold else f"{v}<{threshold}", v
    raise ValueError(f"Unsupported operator: {op}")


def evaluate_rule(row: pd.Series, rule: Dict[str, Any]) -> Dict[str, Any]:
    condition_results = []
    failures = []
    missing_cols = []
    passed_all = True
    for col, op, threshold in rule["conditions"]:
        if col not in row.index:
            passed, reason, value = False, "missing_column", None
            missing_cols.append(col)
        else:
            passed, reason, value = eval_condition(row[col], op, threshold)
        if not passed:
            passed_all = False
            if reason == "missing_column":
                failures.append(f"{col}:missing_column")
            elif reason == "missing":
                failures.append(f"{col}:missing")
            else:
                failures.append(f"{col}:{reason}")
        condition_results.append({
            "column": col,
            "operator": op,
            "threshold": threshold,
            "value": value,
            "passed": bool(passed),
            "reason": reason,
        })
    return {
        "rule_id": rule["rule_id"],
        "short_id": rule["short_id"],
        "label": rule["label"],
        "priority": rule["priority"],
        "horizon_trading_days": rule["horizon_trading_days"],
        "signal_active": bool(passed_all),
        "condition_results": condition_results,
        "rule_failures": failures,
        "missing_columns": missing_cols,
    }


def write_key_value_csv(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["key", "value"])
        for k, v in data.items():
            if isinstance(v, bool):
                vv = "true" if v else "false"
            elif v is None:
                vv = ""
            else:
                vv = str(v)
            w.writerow([k, vv])


def copy_to_mt5(csv_path: Path, cfg: Dict[str, Any]) -> Dict[str, Any]:
    mt5_dir = str(cfg.get("mt5_files_dir", "")).strip()
    if not mt5_dir:
        return {"source": str(csv_path), "destination": None, "copied": False, "status": "SKIPPED_NO_MT5_FILES_DIR", "sha256": sha256_file(csv_path), "error": None}
    dest_dir = Path(mt5_dir).expanduser()
    dest = dest_dir / csv_path.name
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(csv_path, dest)
        return {"source": str(csv_path), "destination": str(dest), "copied": True, "status": "COPIED", "sha256": sha256_file(dest), "error": None}
    except Exception as exc:
        return {"source": str(csv_path), "destination": str(dest), "copied": False, "status": "COPY_FAILED", "sha256": sha256_file(csv_path), "error": str(exc)}


def build_bridge_data(stage: str, generated: str, latest_date: str, mode: str, rule_results: List[Dict[str, Any]], selected: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    active = [r for r in rule_results if r["signal_active"]]
    bridge: Dict[str, Any] = {
        "schema_version": "stage99_unified_observer_cot_v1",
        "stage": stage,
        "generated_utc": generated,
        "feature_date": latest_date,
        "portfolio_mode": mode,
        "mode": mode,
        "execution_allowed": False,
        "order_authorized": False,
        "broker_connection_allowed": False,
        "rule_count": len(rule_results),
        "active_rule_count": len(active),
        "any_signal_active": len(active) > 0,
        "selected_rule_id": selected["rule_id"] if selected else "",
        "selected_label": selected["label"] if selected else "",
        "selected_horizon_trading_days": selected["horizon_trading_days"] if selected else "",
        "primary_rule_id": RULES[0]["rule_id"],
        "primary_label": RULES[0]["label"],
        "primary_signal_active": rule_results[0]["signal_active"],
        "primary_failures": "|".join(rule_results[0]["rule_failures"]),
        "k06_signal_active": rule_results[0]["signal_active"],
        "k06_failures": "|".join(rule_results[0]["rule_failures"]),
    }
    for result in rule_results:
        rid = result["rule_id"]
        sid = result["short_id"]
        failures = "|".join(result["rule_failures"])
        bridge[f"{rid}_label"] = result["label"]
        bridge[f"{rid}_signal_active"] = result["signal_active"]
        bridge[f"{rid}_failures"] = failures
        bridge[f"{sid}_rule_id"] = rid
        bridge[f"{sid}_label"] = result["label"]
        bridge[f"{sid}_active"] = result["signal_active"]
        bridge[f"{sid}_failures"] = failures
    return bridge


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--copy-to-mt5-files", action="store_true")
    args = ap.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    cfg = load_json(relpath(root, args.config))
    out = relpath(root, args.out)
    out.mkdir(parents=True, exist_ok=True)

    generated = utc_now()
    issues: List[str] = []

    stage98_path = relpath(root, cfg["stage98_summary"])
    stage98_ref: Dict[str, Any] = {"path": str(stage98_path), "exists": stage98_path.exists(), "read_ok": False}
    if stage98_path.exists():
        try:
            s98 = load_json(stage98_path)
            stage98_ref.update({
                "read_ok": True,
                "decision": s98.get("decision"),
                "disposition": s98.get("disposition"),
                "selected_rule_ids": s98.get("selected_rule_ids", []),
            })
            if s98.get("disposition") != cfg.get("required_stage98_disposition"):
                issues.append("STAGE98_DISPOSITION_MISMATCH")
            if "C96_07_CB_SUPPORT_NOT_CROWDED_H120" not in s98.get("selected_rule_ids", []):
                issues.append("C96_07_NOT_SELECTED_BY_STAGE98")
        except Exception as exc:
            stage98_ref["error"] = str(exc)
            issues.append("STAGE98_SUMMARY_READ_FAILED")
    else:
        issues.append("STAGE98_SUMMARY_MISSING")

    joined, join_meta = build_joined(root, cfg)
    if join_meta["lookahead_violations"] != 0:
        issues.append("LOOKAHEAD_VIOLATION")

    latest = joined.dropna(subset=["feature_date_utc"]).sort_values("feature_date_utc").iloc[-1]
    latest_date = latest["feature_date_utc"].date().isoformat()
    rule_results = [evaluate_rule(latest, r) for r in RULES]
    active_results = [r for r in rule_results if r["signal_active"]]
    selected = sorted(active_results, key=lambda x: x["priority"])[0] if active_results else None

    mode = str(cfg.get("mode", "OBSERVER_ONLY_NO_TRADE"))
    bridge_data = build_bridge_data("Stage99_UNIFIED_OBSERVER_COT_EXPANSION", generated, latest_date, mode, rule_results, selected)
    bridge_path = relpath(root, cfg["bridge_csv"])
    write_key_value_csv(bridge_path, bridge_data)

    csv_copy = None
    if args.copy_to_mt5_files:
        csv_copy = copy_to_mt5(bridge_path, cfg)

    status = "STAGE99_COMPLETE_NO_PROMOTION" if not issues else "STAGE99_COMPLETE_WITH_ISSUES_NO_PROMOTION"
    decision = "STAGE99_UNIFIED_COT_OBSERVER_READY_WAIT_SIGNAL_NO_ORDER" if not issues else "STAGE99_UNIFIED_COT_OBSERVER_BUILT_WITH_ISSUES_NO_ORDER"
    classification = "S99_UNIFIED_COT_OBSERVER_READY" if not issues else "S99_UNIFIED_COT_OBSERVER_ISSUES"
    disposition = "UNIFIED_COT_OBSERVER_READY_NO_ORDER" if not issues else "UNIFIED_COT_OBSERVER_REVIEW_REQUIRED_NO_ORDER"

    summary = {
        "stage": "Stage99_UNIFIED_OBSERVER_COT_EXPANSION",
        "root": str(root),
        "config": str(relpath(root, args.config)),
        "generated_utc": generated,
        "status": status,
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
        "bridge_role": "MT5 unified observer-only bridge expanded with Stage98-selected COT rule. The EA may read/display signals but cannot trade.",
        "stage98_reference": stage98_ref,
        "data_join": join_meta,
        "latest_feature_date_utc": latest_date,
        "expanded_unified_rule_ids": [r["rule_id"] for r in RULES],
        "new_cot_rule_ids": ["C96_07_CB_SUPPORT_NOT_CROWDED_H120"],
        "rule_results": rule_results,
        "active_rule_ids": [r["rule_id"] for r in active_results],
        "selected_rule_id": selected["rule_id"] if selected else None,
        "selected_label": selected["label"] if selected else None,
        "bridge_csv": {
            "path": str(bridge_path),
            "written": bridge_path.exists(),
            "schema_version": "stage99_unified_observer_cot_v1",
            "mode": mode,
            "any_signal_active_exported": len(active_results) > 0,
            "order_authorized": False,
            "broker_connection_allowed": False,
            "sha256": sha256_file(bridge_path),
        },
        "csv_copy": csv_copy,
        "issues": issues,
        "hard_blocks": HARD_BLOCKS,
        "outputs": {
            "summary_json": str(out / "stage99_unified_observer_cot_expansion_summary.json"),
            "report_md": str(out / "stage99_unified_observer_cot_expansion_report.md"),
            "bridge_csv": str(bridge_path),
        },
    }

    with (out / "stage99_unified_observer_cot_expansion_summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    with (out / "stage99_unified_observer_cot_expansion_report.md").open("w", encoding="utf-8") as f:
        f.write("# Stage99 Unified Observer COT Expansion\n\n")
        f.write("## Decision\n")
        f.write(f"- status: `{status}`\n")
        f.write(f"- decision: `{decision}`\n")
        f.write(f"- classification: `{classification}`\n")
        f.write(f"- disposition: `{disposition}`\n\n")
        f.write("## Latest unified+COT observer signal\n")
        f.write(f"- latest_feature_date_utc: `{latest_date}`\n")
        f.write(f"- active_rule_ids: `{','.join([r['rule_id'] for r in active_results])}`\n")
        f.write(f"- selected_rule_id: `{selected['rule_id'] if selected else 'None'}`\n\n")
        f.write("## Rule snapshot\n")
        for r in rule_results:
            f.write(f"- `{r['rule_id']}` active=`{r['signal_active']}` failures=`{'|'.join(r['rule_failures'])}`\n")
        f.write("\n## Bridge CSV\n")
        f.write(f"- path: `{bridge_path}`\n")
        f.write(f"- written: `{bridge_path.exists()}`\n\n")
        f.write("## Issues\n")
        if issues:
            for issue in issues:
                f.write(f"- `{issue}`\n")
        else:
            f.write("- none\n")
        f.write("\n## Hard blocks\n")
        for b in HARD_BLOCKS:
            f.write(f"- `{b}`\n")

    print(json.dumps({"status": status, "decision": decision, "bridge_csv": str(bridge_path), "active_rule_ids": [r["rule_id"] for r in active_results], "issues": issues}, ensure_ascii=False))
    return 0 if status == "STAGE99_COMPLETE_NO_PROMOTION" else 2


if __name__ == "__main__":
    raise SystemExit(main())
