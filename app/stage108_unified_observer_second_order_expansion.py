#!/usr/bin/env python3
"""Stage108 unified observer expansion with Stage107-selected second-order COT/macro rule.

Observer-only bridge generator. No orders, no broker connection, no EA promotion.
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

STAGE = "Stage108_UNIFIED_OBSERVER_SECOND_ORDER_EXPANSION"
SCHEMA_VERSION = "stage108_unified_observer_second_order_v1"

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_ORDER_SEND_IN_EA",
    "OBSERVER_ONLY_EA",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE108",
    "NO_THRESHOLD_TUNING_FROM_UNIFIED_SECOND_ORDER_OBSERVER_EXPANSION",
]

DATE_CANDIDATES = [
    "date", "date_utc", "utc_date", "asof_date_utc", "as_of_date", "trading_date",
    "timestamp", "utc_time", "time", "datetime",
]
PRICE_CANDIDATES = ["gold_close", "close", "xauusd_close", "price", "settle", "settlement"]
COT_REPORT_DATE_CANDIDATES = ["report_date_utc", "report_date", "date", "date_utc"]
COT_AVAILABLE_CANDIDATES = ["available_after_utc", "available_date_utc", "available_after", "asof_date_utc"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(root: Path, p: str | Path) -> Path:
    q = Path(p)
    return q if q.is_absolute() else root / q


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def find_col(df: pd.DataFrame, candidates: Iterable[str]) -> Optional[str]:
    lower = {str(c).strip().lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    return None


def parse_date_series(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce", utc=True).dt.tz_convert(None)


def safe_to_numeric_inplace(df: pd.DataFrame, skip_cols: Iterable[str] = ()) -> None:
    skip = set(skip_cols)
    for col in list(df.columns):
        if col in skip:
            continue
        if df[col].dtype == object:
            cleaned = df[col].astype(str).str.replace("%", "", regex=False).str.replace(",", "", regex=False)
            numeric = pd.to_numeric(cleaned, errors="coerce")
            # Convert when at least one numeric exists and not every original non-empty string becomes NaN.
            non_empty = cleaned.str.strip().ne("") & cleaned.str.lower().ne("nan")
            if numeric.notna().sum() > 0 and (numeric.notna().sum() >= max(1, int(non_empty.sum() * 0.5))):
                df[col] = numeric
        else:
            try:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            except Exception:
                pass


def alias_macro_columns(df: pd.DataFrame) -> pd.DataFrame:
    aliases = {
        "gold_sma20_over_50": ["gold_sma20_over_50", "xau_sma20_over_50"],
        "dxy_ret_20d": ["dxy_ret_20d", "dxy_return_20d"],
        "dxy_ret_120d": ["dxy_ret_120d", "dxy_return_120d"],
        "dxy_sma20_over_50": ["dxy_sma20_over_50"],
        "real_yield_change_20d": ["real_yield_change_20d", "real_yield_20d_change"],
        "real_yield_change_120d": ["real_yield_change_120d", "real_yield_120d_change"],
        "vix_change_20d": ["vix_change_20d", "vix_20d_change"],
        "central_bank_demand_tonnes_3m": ["central_bank_demand_tonnes_3m", "cb_demand_tonnes_3m"],
        "gold_ret_20d": ["gold_ret_20d", "xau_ret_20d", "gold_return_20d"],
    }
    lower = {c.lower(): c for c in df.columns}
    for canonical, cands in aliases.items():
        if canonical not in df.columns:
            for cand in cands:
                src = lower.get(cand.lower())
                if src is not None:
                    df[canonical] = df[src]
                    break
    return df


def alias_cot_columns(df: pd.DataFrame) -> pd.DataFrame:
    aliases = {
        "cot_mm_net_z": [
            "cot_mm_net_z", "managed_money_net_pct_oi_z_156w", "managed_money_net_z_156w",
            "mm_net_pct_oi_z_156w", "managed_money_net_pct_oi_z",
        ],
        "cot_mm_net_z_change_4w": [
            "cot_mm_net_z_change_4w", "managed_money_net_pct_oi_change_4w",
            "managed_money_net_change_4w", "mm_net_pct_oi_change_4w",
            "managed_money_net_pct_oi_z_change_4w",
        ],
    }
    lower = {c.lower(): c for c in df.columns}
    for canonical, cands in aliases.items():
        if canonical not in df.columns:
            for cand in cands:
                src = lower.get(cand.lower())
                if src is not None:
                    df[canonical] = df[src]
                    break
    return df



def first_existing_col(df: pd.DataFrame, candidates: Iterable[str]) -> Optional[str]:
    lower = {str(c).strip().lower(): c for c in df.columns}
    for cand in candidates:
        src = lower.get(cand.lower())
        if src is not None:
            return src
    return None


def derive_macro_features(df: pd.DataFrame) -> pd.DataFrame:
    """Rebuild common rolling macro features when Stage64K exports only base columns.

    Stage99/100 already exposed these fields in the bridge. Stage108 must preserve
    feature parity when a merge/alias path drops the derived columns or when the
    macro CSV carries only base series such as gold_close, dxy_close and real_yield.
    Derivations are causal rolling/pct-change transforms over sorted daily rows.
    """
    df = df.sort_values("date_utc").copy()

    def num_col(candidates: Iterable[str]) -> Optional[str]:
        col = first_existing_col(df, candidates)
        if col is not None:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return col

    gold_col = num_col(["gold_close", "xauusd_close", "xau_close", "close", "price", "settle", "settlement"])
    dxy_col = num_col(["dxy_close", "dxy", "dxy_index", "dxy_price", "usd_index_close"])
    real_yield_col = num_col(["real_yield", "real_yield_close", "us10y_real_yield", "us10y_real", "tips_10y", "dfii10"])
    vix_col = num_col(["vix_close", "vix", "vix_index"])

    if gold_col is not None:
        if "gold_ret_20d" not in df.columns:
            df["gold_ret_20d"] = df[gold_col].pct_change(20)
        if "gold_sma20_over_50" not in df.columns:
            sma20 = df[gold_col].rolling(20, min_periods=20).mean()
            sma50 = df[gold_col].rolling(50, min_periods=50).mean()
            df["gold_sma20_over_50"] = (sma20 / sma50) - 1.0

    if dxy_col is not None:
        if "dxy_ret_20d" not in df.columns:
            df["dxy_ret_20d"] = df[dxy_col].pct_change(20)
        if "dxy_ret_120d" not in df.columns:
            df["dxy_ret_120d"] = df[dxy_col].pct_change(120)
        if "dxy_sma20_over_50" not in df.columns:
            sma20 = df[dxy_col].rolling(20, min_periods=20).mean()
            sma50 = df[dxy_col].rolling(50, min_periods=50).mean()
            df["dxy_sma20_over_50"] = (sma20 / sma50) - 1.0

    if real_yield_col is not None:
        if "real_yield_change_20d" not in df.columns:
            df["real_yield_change_20d"] = df[real_yield_col] - df[real_yield_col].shift(20)
        if "real_yield_change_120d" not in df.columns:
            df["real_yield_change_120d"] = df[real_yield_col] - df[real_yield_col].shift(120)

    if vix_col is not None and "vix_change_20d" not in df.columns:
        df["vix_change_20d"] = df[vix_col] - df[vix_col].shift(20)

    return df

def load_macro(root: Path, cfg: Dict[str, Any]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    path = rel(root, cfg["macro_dataset_path"])
    if not path.exists():
        raise FileNotFoundError(f"Macro dataset not found: {path}")
    df = pd.read_csv(path)
    date_col = find_col(df, DATE_CANDIDATES)
    if not date_col:
        raise ValueError("No macro date column found. First columns=" + ",".join(map(str, list(df.columns)[:20])))
    price_col = find_col(df, PRICE_CANDIDATES)
    df = alias_macro_columns(df)
    skip = [date_col]
    safe_to_numeric_inplace(df, skip_cols=skip)
    df["date_utc"] = parse_date_series(df[date_col])
    df = df.dropna(subset=["date_utc"]).sort_values("date_utc").drop_duplicates("date_utc", keep="last")
    df = derive_macro_features(df)
    meta = {
        "path": str(path), "rows": int(len(df)), "date_col": str(date_col), "price_col": price_col,
        "min_date": df["date_utc"].min().date().isoformat() if len(df) else None,
        "max_date": df["date_utc"].max().date().isoformat() if len(df) else None,
        "sha256": sha256_file(path),
    }
    return df, meta


def load_cot(root: Path, cfg: Dict[str, Any]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    path = rel(root, cfg["cot_dataset_path"])
    if not path.exists():
        raise FileNotFoundError(f"COT dataset not found: {path}")
    df = pd.read_csv(path)
    report_col = find_col(df, COT_REPORT_DATE_CANDIDATES)
    available_col = find_col(df, COT_AVAILABLE_CANDIDATES)
    if not report_col:
        raise ValueError("No COT report date column found. First columns=" + ",".join(map(str, list(df.columns)[:20])))
    if not available_col:
        # Conservative Friday availability after Tuesday report; dataset should normally contain this.
        available_col = report_col
    df = alias_cot_columns(df)
    safe_to_numeric_inplace(df, skip_cols=[report_col, available_col])
    df["report_date_utc"] = parse_date_series(df[report_col])
    df["available_after_utc"] = parse_date_series(df[available_col])
    df = df.dropna(subset=["report_date_utc", "available_after_utc"]).sort_values("available_after_utc")
    meta = {
        "path": str(path), "rows": int(len(df)), "report_date_col": str(report_col), "available_col": str(available_col),
        "min_report_date_utc": df["report_date_utc"].min().date().isoformat() if len(df) else None,
        "max_report_date_utc": df["report_date_utc"].max().date().isoformat() if len(df) else None,
        "zscore_non_null": int(df.get("cot_mm_net_z", pd.Series(dtype=float)).notna().sum()) if "cot_mm_net_z" in df else 0,
        "change_non_null": int(df.get("cot_mm_net_z_change_4w", pd.Series(dtype=float)).notna().sum()) if "cot_mm_net_z_change_4w" in df else 0,
        "sha256": sha256_file(path),
    }
    return df, meta


def build_joined(root: Path, cfg: Dict[str, Any]) -> Tuple[pd.DataFrame, Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    macro, macro_meta = load_macro(root, cfg)
    cot, cot_meta = load_cot(root, cfg)

    # Stage108B fix: avoid macro/COT column collisions around available_after_utc.
    # The stage64 macro dataset can contain its own availability fields. If a left-side
    # numeric/NaN availability column survives the asof merge under the same name, pandas
    # may compare datetimes against Float64 arrays in the lookahead check. Keep the COT
    # availability under an explicit key and normalize both comparison columns.
    macro = macro.copy()
    cot = cot.copy()
    if "available_after_utc" in macro.columns:
        macro = macro.rename(columns={"available_after_utc": "macro_available_after_utc"})
    if "available_after_utc" not in cot.columns:
        raise ValueError("COT dataset missing normalized available_after_utc after load_cot")

    macro["date_utc"] = parse_date_series(macro["date_utc"])
    cot["cot_available_after_utc"] = parse_date_series(cot["available_after_utc"])
    macro = macro.dropna(subset=["date_utc"]).sort_values("date_utc")
    cot = cot.dropna(subset=["cot_available_after_utc"]).sort_values("cot_available_after_utc")

    joined = pd.merge_asof(
        macro,
        cot,
        left_on="date_utc", right_on="cot_available_after_utc", direction="backward",
        suffixes=("", "_cot"),
    )

    # Canonical COT availability column for downstream summaries and lookahead checks.
    if "cot_available_after_utc" in joined.columns:
        joined["available_after_utc"] = parse_date_series(joined["cot_available_after_utc"])
    else:
        joined["available_after_utc"] = pd.NaT
    joined["date_utc"] = parse_date_series(joined["date_utc"])

    valid_dates = joined["available_after_utc"].notna() & joined["date_utc"].notna()
    lookahead = int((joined.loc[valid_dates, "available_after_utc"] > joined.loc[valid_dates, "date_utc"]).sum())
    join_meta = {
        "joined_rows": int(len(joined)),
        "joined_cot_available_rows": int(valid_dates.sum()),
        "lookahead_violations": lookahead,
    }
    return joined, macro_meta, cot_meta, join_meta


@dataclass
class Condition:
    column: str
    operator: str
    threshold: float

    def eval(self, row: pd.Series) -> Dict[str, Any]:
        if self.column not in row.index:
            return {"column": self.column, "operator": self.operator, "threshold": self.threshold, "value": None, "passed": False, "reason": "missing_column"}
        value = row[self.column]
        try:
            fv = float(value)
        except Exception:
            return {"column": self.column, "operator": self.operator, "threshold": self.threshold, "value": None, "passed": False, "reason": "non_numeric_or_missing"}
        if math.isnan(fv):
            return {"column": self.column, "operator": self.operator, "threshold": self.threshold, "value": None, "passed": False, "reason": "nan"}
        if self.operator == ">":
            passed = fv > self.threshold
        elif self.operator == "<":
            passed = fv < self.threshold
        elif self.operator == ">=":
            passed = fv >= self.threshold
        elif self.operator == "<=":
            passed = fv <= self.threshold
        else:
            raise ValueError(f"Unsupported operator: {self.operator}")
        return {"column": self.column, "operator": self.operator, "threshold": self.threshold, "value": fv, "passed": bool(passed), "reason": "ok" if passed else f"{fv}{self.operator}{self.threshold}"}


@dataclass
class Rule:
    rule_id: str
    short_id: str
    label: str
    priority: int
    horizon_trading_days: int
    conditions: List[Condition]

    def eval(self, row: pd.Series) -> Dict[str, Any]:
        conds = [c.eval(row) for c in self.conditions]
        failures = [f"{c['column']}:{c['reason']}" for c in conds if not c["passed"]]
        missing = [c["column"] for c in conds if c["reason"] == "missing_column"]
        return {
            "rule_id": self.rule_id,
            "short_id": self.short_id,
            "label": self.label,
            "priority": self.priority,
            "horizon_trading_days": self.horizon_trading_days,
            "signal_active": len(failures) == 0,
            "condition_results": conds,
            "rule_failures": failures,
            "missing_columns": missing,
        }


def default_rules() -> List[Rule]:
    return [
        Rule("K06_RESILIENT_GOLD_VS_DXY_H120", "K06", "K06_RESILIENT_GOLD_VS_DXY", 1, 120, [
            Condition("gold_sma20_over_50", ">", 0.0), Condition("dxy_ret_20d", ">", 0.0), Condition("real_yield_change_20d", "<", 0.0)]),
        Rule("K03_SAFE_HAVEN_REALYIELD_H120", "K03", "K03_WGC_RISK_UNCERTAINTY_SAFE_HAVEN", 2, 120, [
            Condition("vix_change_20d", ">", 0.0), Condition("real_yield_change_20d", "<", 0.0)]),
        Rule("K07_DXY_TREND_RELIEF_GOLD_TREND_H120", "K07", "K07_DXY_TREND_RELIEF_GOLD_TREND", 3, 120, [
            Condition("gold_sma20_over_50", ">", 0.0), Condition("dxy_sma20_over_50", "<", 0.0)]),
        Rule("S83_14_REALYIELD_120D_DOWN_GOLD_NOT_TRENDING_H120", "S83_14", "REALYIELD_120D_DOWN_GOLD_NOT_TRENDING", 4, 120, [
            Condition("real_yield_change_120d", "<", 0.0), Condition("gold_sma20_over_50", "<", 0.0)]),
        Rule("S83_13_DXY_120D_DOWN_GOLD_NOT_TRENDING_H120", "S83_13", "DXY_120D_DOWN_GOLD_NOT_TRENDING", 5, 120, [
            Condition("dxy_ret_120d", "<", 0.0), Condition("gold_sma20_over_50", "<", 0.0)]),
        Rule("C96_07_CB_SUPPORT_NOT_CROWDED_H120", "C96_07", "CB_SUPPORT_NOT_CROWDED", 6, 120, [
            Condition("cot_mm_net_z", "<", 1.0), Condition("central_bank_demand_tonnes_3m", ">", 0.0), Condition("gold_ret_20d", "<", 0.0)]),
        Rule("S105_03_COT_DECROWDING_CB_SUPPORT_RY_RELIEF_H120", "S105_03", "COT_DECROWDING_CB_SUPPORT_RY_RELIEF", 7, 120, [
            Condition("cot_mm_net_z_change_4w", "<", 0.0), Condition("central_bank_demand_tonnes_3m", ">", 0.0), Condition("real_yield_change_20d", "<", 0.0)]),
    ]


def bool_str(v: bool) -> str:
    return "true" if bool(v) else "false"


def build_bridge_row(rule_results: List[Dict[str, Any]], latest_date: str, generated_utc: str) -> Dict[str, str]:
    active = [r for r in rule_results if r["signal_active"]]
    selected = sorted(active, key=lambda r: r["priority"])[0] if active else None
    primary = rule_results[0]
    row: Dict[str, str] = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "generated_utc": generated_utc,
        "feature_date": latest_date,
        "portfolio_mode": "OBSERVER_ONLY_NO_TRADE",
        "mode": "OBSERVER_ONLY_NO_TRADE",
        "execution_allowed": "false",
        "order_authorized": "false",
        "broker_connection_allowed": "false",
        "rule_count": str(len(rule_results)),
        "active_rule_count": str(len(active)),
        "any_signal_active": bool_str(len(active) > 0),
        "active_rule_ids": "|".join(r["rule_id"] for r in active),
        "selected_rule_id": selected["rule_id"] if selected else "",
        "selected_label": selected["label"] if selected else "",
        "selected_horizon_trading_days": str(selected["horizon_trading_days"]) if selected else "",
        "primary_rule_id": primary["rule_id"],
        "primary_label": primary["label"],
        "primary_signal_active": bool_str(primary["signal_active"]),
        "primary_failures": "|".join(primary["rule_failures"]),
        "k06_signal_active": bool_str(primary["signal_active"]),
        "k06_failures": "|".join(primary["rule_failures"]),
    }
    for r in rule_results:
        rid = r["rule_id"]
        sid = r["short_id"]
        failures = "|".join(r["rule_failures"])
        row[f"{rid}_label"] = str(r["label"])
        row[f"{rid}_signal_active"] = bool_str(r["signal_active"])
        row[f"{rid}_failures"] = failures
        row[f"{sid}_rule_id"] = str(rid)
        row[f"{sid}_label"] = str(r["label"])
        row[f"{sid}_active"] = bool_str(r["signal_active"])
        row[f"{sid}_failures"] = failures
    return row


def write_bridge_csv(path: Path, row: Dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = list(row.keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerow(row)


def write_report(path: Path, summary: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Stage108 Unified Observer Second-Order Expansion",
        "",
        "## Decision",
        f"- status: `{summary['status']}`",
        f"- decision: `{summary['decision']}`",
        f"- classification: `{summary['classification']}`",
        f"- disposition: `{summary['disposition']}`",
        "",
        "## Latest unified+second-order observer signal",
        f"- latest_feature_date_utc: `{summary['latest_feature_date_utc']}`",
        f"- active_rule_ids: `{', '.join(summary['active_rule_ids'])}`",
        f"- selected_rule_id: `{summary['selected_rule_id']}`",
        "",
        "## Rule snapshot",
    ]
    for r in summary["rule_results"]:
        lines.append(f"- `{r['rule_id']}` active=`{r['signal_active']}` failures=`{'|'.join(r['rule_failures'])}`")
    lines += ["", "## Bridge CSV", f"- path: `{summary['bridge_csv']['path']}`", f"- written: `{summary['bridge_csv']['written']}`", "", "## Issues"]
    if summary["issues"]:
        lines += [f"- `{i}`" for i in summary["issues"]]
    else:
        lines.append("- none")
    lines += ["", "## Hard blocks"] + [f"- `{x}`" for x in summary["hard_blocks"]]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--copy-to-mt5-files", action="store_true")
    ns = ap.parse_args(argv)
    root = Path(ns.root).resolve()
    cfg = read_json(rel(root, ns.config))
    out = rel(root, ns.out)
    generated_utc = utc_now_iso()

    stage107_summary_path = rel(root, cfg.get("stage107_summary_path", "reports/stage107_second_order_portfolio_increment_review/stage107_second_order_portfolio_increment_review_summary.json"))
    stage107_ref: Dict[str, Any] = {"path": str(stage107_summary_path), "exists": stage107_summary_path.exists(), "read_ok": False}
    if stage107_summary_path.exists():
        try:
            ref = read_json(stage107_summary_path)
            stage107_ref.update({
                "read_ok": True,
                "decision": ref.get("decision"),
                "disposition": ref.get("disposition"),
                "selected_rule_ids": ref.get("selected_rule_ids", []),
            })
        except Exception as e:
            stage107_ref["error"] = str(e)

    joined, macro_meta, cot_meta, join_meta = build_joined(root, cfg)
    if join_meta["lookahead_violations"] != 0:
        raise ValueError(f"Lookahead violations detected: {join_meta['lookahead_violations']}")
    latest = joined.sort_values("date_utc").iloc[-1]
    latest_date = pd.Timestamp(latest["date_utc"]).date().isoformat()
    rules = default_rules()
    rule_results = [r.eval(latest) for r in rules]
    active_rule_ids = [r["rule_id"] for r in rule_results if r["signal_active"]]
    selected = sorted([r for r in rule_results if r["signal_active"]], key=lambda r: r["priority"])
    selected_rule_id = selected[0]["rule_id"] if selected else None
    selected_label = selected[0]["label"] if selected else None

    bridge_path = rel(root, cfg.get("bridge_csv_path", "data/mt5_bridge/unified_observer_signal.csv"))
    row = build_bridge_row(rule_results, latest_date, generated_utc)
    write_bridge_csv(bridge_path, row)

    csv_copy: Dict[str, Any] = {"source": str(bridge_path), "destination": None, "copied": False, "status": "SKIPPED", "sha256": sha256_file(bridge_path), "error": None}
    mt5_dest_dir = cfg.get("mt5_files_dir", "")
    if ns.copy_to_mt5_files:
        if not mt5_dest_dir:
            csv_copy.update({"status": "NO_DESTINATION", "error": "mt5_files_dir missing in config"})
        else:
            dest_dir = Path(mt5_dest_dir).expanduser()
            dest = dest_dir / bridge_path.name
            csv_copy["destination"] = str(dest)
            try:
                dest_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(bridge_path, dest)
                csv_copy.update({"copied": True, "status": "COPIED", "sha256": sha256_file(dest), "error": None})
            except Exception as e:
                csv_copy.update({"copied": False, "status": "COPY_FAILED", "error": str(e)})

    summary = {
        "stage": STAGE,
        "root": str(root),
        "config": str(rel(root, ns.config)),
        "generated_utc": generated_utc,
        "status": "STAGE108_COMPLETE_NO_PROMOTION",
        "decision": "STAGE108_UNIFIED_SECOND_ORDER_OBSERVER_READY_WAIT_SIGNAL_NO_ORDER",
        "classification": "S108_UNIFIED_SECOND_ORDER_OBSERVER_READY",
        "disposition": "UNIFIED_SECOND_ORDER_OBSERVER_READY_NO_ORDER",
        "bridge_role": "MT5 unified observer-only bridge expanded with Stage107-selected second-order COT/macro rule. The EA may read/display signals but cannot trade.",
        "stage107_reference": stage107_ref,
        "macro_dataset": macro_meta,
        "cot_dataset": cot_meta,
        "data_join": join_meta,
        "latest_feature_date_utc": latest_date,
        "expanded_unified_rule_ids": [r.rule_id for r in rules],
        "new_second_order_rule_ids": ["S105_03_COT_DECROWDING_CB_SUPPORT_RY_RELIEF_H120"],
        "rule_results": rule_results,
        "active_rule_ids": active_rule_ids,
        "selected_rule_id": selected_rule_id,
        "selected_label": selected_label,
        "bridge_csv": {
            "path": str(bridge_path),
            "written": bridge_path.exists(),
            "schema_version": SCHEMA_VERSION,
            "mode": "OBSERVER_ONLY_NO_TRADE",
            "any_signal_active_exported": bool(len(active_rule_ids) > 0),
            "order_authorized": False,
            "broker_connection_allowed": False,
            "sha256": sha256_file(bridge_path),
        },
        "csv_copy": csv_copy,
        "issues": [],
        "hard_blocks": HARD_BLOCKS,
        "outputs": {
            "summary_json": str(out / "stage108_unified_observer_second_order_expansion_summary.json"),
            "report_md": str(out / "stage108_unified_observer_second_order_expansion_report.md"),
            "bridge_csv": str(bridge_path),
        },
    }
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "stage108_unified_observer_second_order_expansion_summary.json", summary)
    write_report(out / "stage108_unified_observer_second_order_expansion_report.md", summary)
    print(json.dumps({"status": summary["status"], "decision": summary["decision"], "bridge_csv": str(bridge_path), "active_rule_ids": active_rule_ids, "issues": []}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
