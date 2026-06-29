#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

STAGE = "Stage129_DUAL_TRACK_MARKET_OPEN_OPS_AND_FRONTIER_EXPANSION"
STATUS = "STAGE129_COMPLETE_DUAL_TRACK_READY_NO_ORDER"
CLASSIFICATION = "DUAL_TRACK_MARKET_OPEN_FORWARD_SHADOW_AND_FRONTIER_EXPANSION_NO_ORDER"

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_TRADE_REQUEST_FROM_STAGE129",
    "NO_ORDER_SEND",
    "NO_CTRADE_USAGE",
    "NO_MT5_EA_CHANGE_FROM_STAGE129",
    "NO_INDICATOR_UI_CHANGE_FROM_STAGE129",
    "NO_PAPER_LIVE",
    "NO_LIVE",
]

DEFAULT_MT5_FILES = (
    "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/"
    "drive_c/Program Files/MetaTrader 5/MQL5/Files"
)

def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path

def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def read_csv_safe(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()

def write_json(path: Path, obj: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")

def write_rows(path: Path, rows: List[Dict[str, Any]], fields: List[str] | None = None) -> None:
    ensure_dir(path.parent)
    if fields is None:
        fields = []
        for row in rows:
            for k in row:
                if k not in fields:
                    fields.append(k)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})
    tmp.replace(path)

def write_kv(path: Path, kv: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for k, v in kv.items():
            f.write(f"{k}|{'' if v is None else v}\n")
    tmp.replace(path)

def read_kv(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path.exists():
        return out
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if "|" in line:
                k, v = line.split("|", 1)
            elif "," in line:
                k, v = line.split(",", 1)
            else:
                continue
            out[k.strip()] = v.strip()
    except Exception:
        return {}
    return out

def first_existing(paths: List[Path]) -> Path | None:
    for p in paths:
        if p.exists():
            return p
    return None

def coerce_num(s: pd.Series) -> pd.Series:
    if s.dtype == bool:
        return s.astype(float)
    return pd.to_numeric(s, errors="coerce")

def find_col(df: pd.DataFrame, names: List[str]) -> str | None:
    low = {c.lower(): c for c in df.columns}
    for n in names:
        if n in df.columns:
            return n
        if n.lower() in low:
            return low[n.lower()]
    return None

def load_stage117_dataset(root: Path) -> Tuple[pd.DataFrame, str, str]:
    p = first_existing([
        root / "data/fundamental_event_inbox/features/stage117_joined_macro_cot_dollar_h1_research_dataset.csv",
        root / "reports/stage117_segmented_macro_cot_dollar_discovery/stage117_joined_macro_cot_dollar_h1_research_dataset.csv",
    ])
    if p is None:
        return pd.DataFrame(), "", "missing"
    df = pd.read_csv(p)
    tcol = find_col(df, ["utc_time", "time", "date", "datetime"])
    if tcol:
        df[tcol] = pd.to_datetime(df[tcol], errors="coerce", utc=True)
        df = df[df[tcol].notna()].sort_values(tcol).reset_index(drop=True)
    rcol = find_col(df, ["fwd_ret_bps_h120", "forward_return_bps_h120", "fwd_return_bps_h120"])
    if rcol:
        df["_stage129_forward_return_bps"] = coerce_num(df[rcol])
        return df, str(p), f"mapped_from:{rcol}"
    return df, str(p), "return_col_missing"

def quantile(df: pd.DataFrame, col: str, q: float) -> float:
    if col not in df:
        return math.nan
    vals = coerce_num(df[col]).dropna()
    if len(vals) == 0:
        return math.nan
    return float(vals.quantile(q))

def split_time(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    tcol = find_col(df, ["utc_time", "time", "date", "datetime"])
    if not tcol:
        return {}
    d = df.sort_values(tcol).reset_index(drop=True)
    a = int(len(d) * 0.60)
    b = int(len(d) * 0.80)
    return {
        "selection": d.iloc[:a].copy(),
        "validation": d.iloc[a:b].copy(),
        "tail": d.iloc[b:].copy(),
        "all": d.copy(),
    }

def year_concentration(events: pd.DataFrame) -> Tuple[float, str]:
    tcol = find_col(events, ["utc_time", "time", "date", "datetime"])
    if events.empty or not tcol:
        return math.nan, ""
    years = pd.to_datetime(events[tcol], errors="coerce", utc=True).dt.year.dropna()
    if len(years) == 0:
        return math.nan, ""
    vc = years.value_counts(normalize=True)
    return float(vc.iloc[0] * 100.0), str(int(vc.index[0]))

def nonoverlap(events: pd.DataFrame, hours: int = 120) -> pd.DataFrame:
    tcol = find_col(events, ["utc_time", "time", "date", "datetime"])
    if events.empty or not tcol:
        return events.copy()
    d = events.sort_values(tcol)
    chosen = []
    last = None
    gap = pd.Timedelta(hours=hours)
    for i, row in d.iterrows():
        t = row[tcol]
        if last is None or (t - last) >= gap:
            chosen.append(i)
            last = t
    return d.loc[chosen].copy()

def metrics(events: pd.DataFrame, split: str) -> Dict[str, Any]:
    ret = coerce_num(events["_stage129_forward_return_bps"]).dropna() if "_stage129_forward_return_bps" in events else pd.Series(dtype=float)
    cost = ret - 10.0
    yc, ty = year_concentration(events)
    return {
        "split": split,
        "events": int(len(events)),
        "valid_return_events": int(len(ret)),
        "mean_bps": float(ret.mean()) if len(ret) else math.nan,
        "hit_rate": float((ret > 0).mean()) if len(ret) else math.nan,
        "cost10_mean_bps": float(cost.mean()) if len(cost) else math.nan,
        "cost10_hit_rate": float((cost > 0).mean()) if len(cost) else math.nan,
        "worst_cost10_bps": float(cost.min()) if len(cost) else math.nan,
        "best_cost10_bps": float(cost.max()) if len(cost) else math.nan,
        "max_year_concentration_pct": yc,
        "top_year": ty,
    }

def frontier_expansion_scan(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if df.empty or "_stage129_forward_return_bps" not in df:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    splits = split_time(df)
    if not splits:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    sel = splits["selection"]

    thresholds = {
        "vix60": quantile(sel, "vix_chg_20d", 0.60),
        "vix70": quantile(sel, "vix_chg_20d", 0.70),
        "dollar40": quantile(sel, "dollar_pressure_chg_20d", 0.40),
        "dollar50": quantile(sel, "dollar_pressure_chg_20d", 0.50),
        "ry40": quantile(sel, "real_yield_10y_chg_20d", 0.40),
        "ry50": quantile(sel, "real_yield_10y_chg_20d", 0.50),
        "spdr60": quantile(sel, "spdr_value_chg_20d", 0.60),
        "cot60": quantile(sel, "cot_mm_net_z", 0.60),
    }

    def has(*cols: str) -> bool:
        return all(c in df.columns for c in cols)

    rules = []
    if has("vix_chg_20d", "dollar_pressure_chg_20d", "real_yield_10y_chg_20d"):
        rules.append(("F129_01_DECONCENTRATED_SAFE_HAVEN_VIX_DOLLAR_RY",
                      "vix>q70 dollar<q40 ry<q40",
                      ["vix_chg_20d", "dollar_pressure_chg_20d", "real_yield_10y_chg_20d"],
                      lambda d: (coerce_num(d["vix_chg_20d"]) > thresholds["vix70"]) &
                                (coerce_num(d["dollar_pressure_chg_20d"]) < thresholds["dollar40"]) &
                                (coerce_num(d["real_yield_10y_chg_20d"]) < thresholds["ry40"])))
    if has("spdr_value_chg_20d", "dollar_pressure_chg_20d", "real_yield_10y_chg_20d"):
        rules.append(("F129_02_STRICT_SPDR_MACRO_RELIEF",
                      "spdr>q60 dollar<q40 ry<q40",
                      ["spdr_value_chg_20d", "dollar_pressure_chg_20d", "real_yield_10y_chg_20d"],
                      lambda d: (coerce_num(d["spdr_value_chg_20d"]) > thresholds["spdr60"]) &
                                (coerce_num(d["dollar_pressure_chg_20d"]) < thresholds["dollar40"]) &
                                (coerce_num(d["real_yield_10y_chg_20d"]) < thresholds["ry40"])))
    if has("vix_chg_20d", "dollar_pressure_chg_20d", "cot_mm_net_z"):
        rules.append(("F129_03_VIX_DOLLAR_RELIEF_COT_NOT_CROWDED",
                      "vix>q60 dollar<q50 cot<q60",
                      ["vix_chg_20d", "dollar_pressure_chg_20d", "cot_mm_net_z"],
                      lambda d: (coerce_num(d["vix_chg_20d"]) > thresholds["vix60"]) &
                                (coerce_num(d["dollar_pressure_chg_20d"]) < thresholds["dollar50"]) &
                                (coerce_num(d["cot_mm_net_z"]) < thresholds["cot60"])))

    all_rows = []
    selected = []
    watch = []

    for rule_id, condition, features, fn in rules:
        split_m = {}
        all_events = pd.DataFrame()
        for name, dsplit in splits.items():
            ev = dsplit[fn(dsplit).fillna(False)].copy()
            if name == "all":
                all_events = ev
            m = metrics(ev, name)
            split_m[name] = m
            row = dict(m)
            row.update({"rule_id": rule_id, "condition": condition, "required_features": ",".join(features)})
            all_rows.append(row)
        no = nonoverlap(all_events, 120)
        no_m = metrics(no, "nonoverlap_h120")
        row = dict(no_m)
        row.update({"rule_id": rule_id, "condition": condition, "required_features": ",".join(features)})
        all_rows.append(row)

        reasons = []
        for split_name in ["selection", "validation", "tail"]:
            m = split_m.get(split_name, {})
            if m.get("events", 0) < 30:
                reasons.append(f"{split_name}_events_lt_30")
            if split_name in ["validation", "tail"]:
                if m.get("cost10_mean_bps", math.nan) <= 0 or math.isnan(m.get("cost10_mean_bps", math.nan)):
                    reasons.append(f"{split_name}_cost10_mean_not_positive")
                if m.get("max_year_concentration_pct", 100) > 75:
                    reasons.append(f"{split_name}_year_concentration_gt_75pct:{m.get('max_year_concentration_pct', math.nan):.2f}")
        if no_m.get("events", 0) < 10:
            reasons.append("nonoverlap_events_lt_10")
        if no_m.get("cost10_mean_bps", math.nan) <= 0 or math.isnan(no_m.get("cost10_mean_bps", math.nan)):
            reasons.append("nonoverlap_cost10_mean_not_positive")
        if no_m.get("max_year_concentration_pct", 100) > 75:
            reasons.append(f"nonoverlap_year_concentration_gt_75pct:{no_m.get('max_year_concentration_pct', math.nan):.2f}")

        carry = {
            "rule_id": rule_id,
            "condition": condition,
            "required_features": ",".join(features),
            "selection_events": split_m.get("selection", {}).get("events", 0),
            "validation_events": split_m.get("validation", {}).get("events", 0),
            "tail_events": split_m.get("tail", {}).get("events", 0),
            "nonoverlap_events": no_m.get("events", 0),
            "validation_cost10_mean_bps": split_m.get("validation", {}).get("cost10_mean_bps", math.nan),
            "tail_cost10_mean_bps": split_m.get("tail", {}).get("cost10_mean_bps", math.nan),
            "nonoverlap_cost10_mean_bps": no_m.get("cost10_mean_bps", math.nan),
            "validation_year_concentration_pct": split_m.get("validation", {}).get("max_year_concentration_pct", math.nan),
            "tail_year_concentration_pct": split_m.get("tail", {}).get("max_year_concentration_pct", math.nan),
            "nonoverlap_year_concentration_pct": no_m.get("max_year_concentration_pct", math.nan),
            "decision": "PASS_STAGE130_REVIEW_QUEUE" if not reasons else "WATCH_OR_REJECT",
            "reasons": ";".join(reasons),
        }
        if reasons:
            watch.append(carry)
        else:
            selected.append(carry)

    return pd.DataFrame(all_rows), pd.DataFrame(selected), pd.DataFrame(watch)

def shadow_runtime_snapshot(root: Path, mt5_files: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    files = [
        ("rule8", "xauusd_stage124f_rule8_overlay_kv.csv"),
        ("rule9", "xauusd_stage126_rule9_frontier_status_kv.csv"),
        ("rule9_review", "xauusd_stage127_rule9_review_status_kv.csv"),
        ("stage128", "xauusd_stage128_forward_shadow_and_megascan_status_kv.csv"),
    ]
    rows = []
    for label, fn in files:
        p = mt5_files / fn
        kv = read_kv(p)
        rows.append({
            "label": label,
            "file": fn,
            "seen": bool(kv),
            "kv_count": len(kv),
            "status": kv.get("status") or kv.get("stage127_status") or "",
            "allow_trading": kv.get("allow_trading") or "false",
            "decision": kv.get("decision", ""),
            "cost10_mean_bps": kv.get("cost10_mean_bps", ""),
        })
    health = {
        "rule8_seen": any(r["label"] == "rule8" and r["seen"] for r in rows),
        "rule9_seen": any(r["label"] in ["rule9", "rule9_review"] and r["seen"] for r in rows),
        "kv_files_seen": sum(1 for r in rows if r["seen"]),
    }
    return rows, health

def data_expansion_plan() -> List[Dict[str, Any]]:
    return [
        {
            "arm": "forward_shadow",
            "action": "Keep 7-rule Unified_ObserverOnly_EA and Rule8/Rule9 overlays running while market is open",
            "cadence": "hourly snapshot or after new macro/source update",
            "promotion_impact": "observation only",
        },
        {
            "arm": "frontier_discovery",
            "action": "Do not build Stage130 unless selected_for_stage130_count > 0",
            "cadence": "after new data/proxy or daily data refresh",
            "promotion_impact": "review only",
        },
        {
            "arm": "data_alternative",
            "action": "Use DTWEXBGS/FRED as dollar pressure fallback; keep direct DXY optional",
            "cadence": "daily",
            "promotion_impact": "feature stability",
        },
        {
            "arm": "data_alternative",
            "action": "Build surprise proxies from official releases rather than scraped commercial calendar surprises",
            "cadence": "later consolidated patch",
            "promotion_impact": "new thesis source",
        },
        {
            "arm": "ui",
            "action": "Do not spend more time now; fix overlay spacing only when an indicator file is next touched",
            "cadence": "opportunistic",
            "promotion_impact": "none",
        },
    ]

def run(root: Path, mt5_files: Path, write_mt5_status_kv: bool = False) -> Dict[str, Any]:
    root = root.expanduser()
    mt5_files = mt5_files.expanduser()

    out = ensure_dir(root / "reports/stage129_dual_track_market_open_ops_and_frontier_expansion")
    shadow = ensure_dir(root / "data/shadow_observer")

    stage128_summary = read_json(root / "reports/stage128_market_open_forward_shadow_and_frontier_megascan/stage128_market_open_forward_shadow_and_frontier_megascan_summary.json")
    stage127_summary = read_json(root / "reports/stage127_rule9_deconcentration_combo_overlap_review/stage127_rule9_deconcentration_combo_overlap_review_summary.json")
    dataset, dataset_path, return_source = load_stage117_dataset(root)

    runtime_rows, runtime_health = shadow_runtime_snapshot(root, mt5_files)
    scan_metrics, selected, watch = frontier_expansion_scan(dataset)

    runtime_path = out / "stage129_market_open_runtime_snapshot.csv"
    metrics_path = out / "stage129_frontier_expansion_metrics.csv"
    selected_path = out / "stage129_selected_for_stage130.csv"
    watch_path = out / "stage129_watch_or_reject.csv"
    plan_path = out / "stage129_dual_track_action_plan.csv"
    governance_path = out / "stage129_governance_no_order_manifest.csv"
    kv_repo = shadow / "stage129_dual_track_status_kv.csv"
    kv_report = out / "stage129_dual_track_status_kv.csv"

    write_rows(runtime_path, runtime_rows)
    scan_metrics.to_csv(metrics_path, index=False)
    selected.to_csv(selected_path, index=False)
    watch.to_csv(watch_path, index=False)
    write_rows(plan_path, data_expansion_plan())
    write_rows(governance_path, [{"block": b, "status": "ACTIVE"} for b in HARD_BLOCKS])

    selected_count = int(len(selected))
    decision = "STAGE129_STAGE130_FRONTIER_REVIEW_QUEUE_READY_NO_ORDER" if selected_count else "STAGE129_FORWARD_SHADOW_CONTINUE_NO_NEW_FRONTIER_SELECTION_NO_ORDER"
    kv = {
        "stage": STAGE,
        "status": STATUS,
        "decision": decision,
        "generated_utc": now_utc(),
        "allow_trading": "false",
        "order_send": "false",
        "selected_for_stage130_count": selected_count,
        "watch_or_reject_count": int(len(watch)),
        "rule8_seen": str(runtime_health["rule8_seen"]).lower(),
        "rule9_seen": str(runtime_health["rule9_seen"]).lower(),
        "ui_note": "indicator_layout_fix_deferred_until_next_indicator_patch",
    }
    write_kv(kv_repo, kv)
    write_kv(kv_report, kv)
    mt5_kv = ""
    if write_mt5_status_kv:
        p = mt5_files / "xauusd_stage129_dual_track_status_kv.csv"
        write_kv(p, kv)
        mt5_kv = str(p)

    summary = {
        "stage": STAGE,
        "generated_utc": now_utc(),
        "status": STATUS,
        "decision": decision,
        "classification": CLASSIFICATION,
        "hard_blocks": HARD_BLOCKS,
        "root": str(root),
        "stage127_prior_decision": stage127_summary.get("decision", ""),
        "stage128_prior_decision": stage128_summary.get("decision", ""),
        "runtime_health": runtime_health,
        "dataset_path": dataset_path,
        "dataset_rows": int(len(dataset)),
        "return_source": return_source,
        "frontier_metric_rows": int(len(scan_metrics)),
        "selected_for_stage130_count": selected_count,
        "watch_or_reject_count": int(len(watch)),
        "mt5_status_kv_written": bool(write_mt5_status_kv),
        "mt5_status_kv": mt5_kv,
        "market_open_runtime_snapshot": str(runtime_path),
        "frontier_expansion_metrics": str(metrics_path),
        "selected_for_stage130": str(selected_path),
        "watch_or_reject": str(watch_path),
        "dual_track_action_plan": str(plan_path),
        "governance_no_order_manifest": str(governance_path),
        "status_kv_repo": str(kv_repo),
        "status_kv_report": str(kv_report),
        "summary_json": str(out / "stage129_dual_track_market_open_ops_and_frontier_expansion_summary.json"),
        "report_md": str(out / "stage129_dual_track_market_open_ops_and_frontier_expansion_report.md"),
        "next": [
            "If selected_for_stage130_count is zero, continue forward shadow and do not build a new promotion/review stage.",
            "If selected_for_stage130_count is positive, review Stage130 candidates in one consolidated package only.",
            "Defer indicator UI layout fixes until the next indicator-touching patch."
        ]
    }
    write_json(out / "stage129_dual_track_market_open_ops_and_frontier_expansion_summary.json", summary)
    report = [
        f"# {STAGE}",
        "",
        f"Status: `{STATUS}`",
        f"Decision: `{decision}`",
        "",
        "## Runtime health",
        "",
        f"- Rule8 seen: {runtime_health['rule8_seen']}",
        f"- Rule9 seen: {runtime_health['rule9_seen']}",
        "",
        "## Frontier expansion",
        "",
        f"- metric rows: {len(scan_metrics)}",
        f"- selected for Stage130: {selected_count}",
        f"- watch/reject: {len(watch)}",
        "",
        "## UI note",
        "",
        "Indicator layout fix is deliberately deferred until the next indicator-touching patch.",
    ]
    (out / "stage129_dual_track_market_open_ops_and_frontier_expansion_report.md").write_text("\n".join(report), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--mt5-files", default=DEFAULT_MT5_FILES)
    parser.add_argument("--write-mt5-status-kv", action="store_true")
    args = parser.parse_args()
    run(Path(args.root), Path(args.mt5_files), args.write_mt5_status_kv)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
