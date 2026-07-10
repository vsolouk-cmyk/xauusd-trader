#!/usr/bin/env python3
"""
Stage171C — H64L Evidence Recovery + Manual Shadow Checklist

Read-only support stage. It does not create trading candidates, write MT5 signals,
or authorize demo/live orders. It narrows the H64L rescue path by trying to recover
exact Stage64/Stage64R evidence and by producing a current manual shadow checklist.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

STAGE = "Stage171C_H64L_EVIDENCE_RECOVERY_AND_SHADOW_CHECKLIST"
DEFAULT_OUTPUT = "reports/stage171c_h64l_evidence_shadow_checklist"
H64L_CONDITIONS = [
    ("gold_trend_sma20_over_50", "gold_sma20_over_50", ">", 0.0),
    ("dxy_ret_20d", "dxy_ret_20d", "<", 0.0),
    ("real_yield_change_20d", "real_yield_change_20d", "<", 0.0),
    ("etf_flow_tonnes_3m", "etf_flow_tonnes_3m", ">", 0.0),
]
LIKELY_DATASETS = [
    "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv",
    "data/macro_regime/normalized/stage64f_reduced_scope_lag_safe_feature_dataset.csv",
    "data/forward_shadow/stage65_macro_signal_ledger.csv",
]
SCAN_DIRS = ["reports", "data/macro_regime", "data/forward_shadow", "docs", "app"]
MAX_SCAN_FILE_BYTES = 5_000_000


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Optional[Path]) -> Dict[str, Any]:
    if not path:
        return {}
    path = path.expanduser()
    if not path.exists():
        return {"_missing": str(path)}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_error": f"{type(exc).__name__}: {exc}", "_path": str(path)}


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def write_csv(path: Path, rows: List[Dict[str, Any]], fields: Optional[List[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not fields:
        keys = []
        for r in rows:
            for k in r.keys():
                if k not in keys:
                    keys.append(k)
        fields = keys or ["empty"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})


def detect_sep(path: Path) -> str:
    sample = path.read_text(encoding="utf-8", errors="replace")[:4096]
    candidates = {"\t": sample.count("\t"), ",": sample.count(","), ";": sample.count(";"), "|": sample.count("|")}
    return max(candidates, key=candidates.get) if sample else ","


def read_csv_any(path: Path, nrows: Optional[int] = None) -> pd.DataFrame:
    path = path.expanduser()
    sep = detect_sep(path)
    return pd.read_csv(path, sep=sep, nrows=nrows, low_memory=False)


def norm_col(c: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(c).strip().lower()).strip("_")


def find_time_col(columns: Iterable[str]) -> Optional[str]:
    normed = {norm_col(c): c for c in columns}
    for key in ["time_utc", "utc_time", "timestamp_utc", "datetime_utc", "date_utc", "date", "time", "ds"]:
        if key in normed:
            return normed[key]
    for c in columns:
        n = norm_col(c)
        if "time" in n or "date" in n:
            return c
    return None


def fuzzy_col_map(columns: Iterable[str]) -> Dict[str, Optional[str]]:
    cols = list(columns)
    norm_to_orig = {norm_col(c): c for c in cols}

    def choose(candidates: List[str], contains_all: Optional[List[str]] = None, contains_any: Optional[List[str]] = None) -> Optional[str]:
        for cand in candidates:
            if cand in norm_to_orig:
                return norm_to_orig[cand]
        contains_all = contains_all or []
        contains_any = contains_any or []
        for n, orig in norm_to_orig.items():
            if contains_all and not all(x in n for x in contains_all):
                continue
            if contains_any and not any(x in n for x in contains_any):
                continue
            return orig
        return None

    return {
        "gold_sma20_over_50": choose(
            ["gold_sma20_over_50", "xauusd_sma20_over_50", "sma20_over_50", "gold_trend_sma20_over_50"],
            contains_all=["sma20", "50"],
            contains_any=["gold", "xau", "trend"],
        ),
        "dxy_ret_20d": choose(
            ["dxy_ret_20d", "dxy_return_20d", "dxy_20d_ret", "dtwexbgs_ret_20d", "dxy_change_20d"],
            contains_all=["dxy"],
            contains_any=["20d", "ret", "change"],
        ),
        "real_yield_change_20d": choose(
            ["real_yield_change_20d", "real_yield_ret_20d", "dfii10_change_20d", "tips_yield_change_20d"],
            contains_all=["yield"],
            contains_any=["real", "dfii", "tips", "20d", "change"],
        ),
        "etf_flow_tonnes_3m": choose(
            ["etf_flow_tonnes_3m", "gld_flow_tonnes_3m", "etf_tonnes_3m", "gold_etf_flow_tonnes_3m"],
            contains_all=["flow"],
            contains_any=["etf", "gld", "tonnes", "3m"],
        ),
    }


def safe_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None


def eval_condition(value: Optional[float], op: str, threshold: float) -> str:
    if value is None:
        return "UNKNOWN"
    if op == ">":
        return "PASS" if value > threshold else "FAIL"
    if op == "<":
        return "PASS" if value < threshold else "FAIL"
    return "UNKNOWN"


def scan_h64l_artifacts(root: Path) -> List[Dict[str, Any]]:
    hits: List[Dict[str, Any]] = []
    terms = ["H64L", "macro_tailwind", "tailwind", "stage64r", "stage64", "real_yield", "dxy", "etf_flow"]
    for rel in SCAN_DIRS:
        d = root / rel
        if not d.exists():
            continue
        for p in d.rglob("*"):
            if not p.is_file():
                continue
            try:
                size = p.stat().st_size
            except Exception:
                continue
            name_text = str(p).lower()
            name_score = sum(1 for t in terms if t.lower() in name_text)
            if size > MAX_SCAN_FILE_BYTES and name_score == 0:
                continue
            content_score = 0
            snippet = ""
            if p.suffix.lower() in [".md", ".txt", ".json", ".csv", ".py", ".yml", ".yaml"] and size <= MAX_SCAN_FILE_BYTES:
                try:
                    s = p.read_text(encoding="utf-8", errors="replace")
                    for t in terms:
                        content_score += len(re.findall(re.escape(t), s, flags=re.I))
                    idxs = [s.lower().find(t.lower()) for t in terms if s.lower().find(t.lower()) >= 0]
                    if idxs:
                        idx = min(idxs)
                        snippet = s[max(0, idx-100): idx+250].replace("\n", " ")[:500]
                except Exception:
                    pass
            score = name_score * 10 + min(content_score, 50)
            if score > 0:
                hits.append({
                    "path": str(p),
                    "size_bytes": size,
                    "name_score": name_score,
                    "content_score_capped": min(content_score, 50),
                    "score": score,
                    "snippet": snippet,
                })
    hits.sort(key=lambda r: (-int(r["score"]), r["path"]))
    return hits[:200]


def inspect_dataset(path: Path) -> Dict[str, Any]:
    meta: Dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        return meta
    try:
        df_head = read_csv_any(path, nrows=5)
        meta.update({"columns": list(df_head.columns), "separator": "tab" if detect_sep(path) == "\t" else detect_sep(path)})
        # Full read only for likely small macro datasets; this is stage-specific and acceptable.
        df = read_csv_any(path)
        meta["row_count"] = int(len(df))
        tcol = find_time_col(df.columns)
        meta["time_column"] = tcol
        if tcol:
            ts = pd.to_datetime(df[tcol], utc=True, errors="coerce")
            if ts.notna().any():
                meta["min_time_utc"] = str(ts.min())
                meta["max_time_utc"] = str(ts.max())
        fmap = fuzzy_col_map(df.columns)
        meta["column_map"] = fmap
        missing = [k for k, v in fmap.items() if not v]
        meta["missing_h64l_columns"] = missing
        if len(df) > 0:
            # choose latest by time if possible else final row
            if tcol:
                df2 = df.assign(_ts=pd.to_datetime(df[tcol], utc=True, errors="coerce")).sort_values("_ts")
                row = df2.dropna(subset=["_ts"]).iloc[-1] if df2["_ts"].notna().any() else df.iloc[-1]
                meta["latest_time_utc"] = str(row.get("_ts", ""))
            else:
                row = df.iloc[-1]
            checks = []
            for feature, canonical, op, threshold in H64L_CONDITIONS:
                col = fmap.get(canonical)
                value = safe_float(row[col]) if col else None
                checks.append({
                    "feature": feature,
                    "canonical_column": canonical,
                    "mapped_column": col or "",
                    "condition": f"{canonical} {op} {threshold:g}",
                    "latest_value": value if value is not None else "",
                    "condition_status": eval_condition(value, op, threshold),
                })
            meta["latest_checklist"] = checks
            statuses = [c["condition_status"] for c in checks]
            meta["latest_h64l_all_known"] = all(s != "UNKNOWN" for s in statuses)
            meta["latest_h64l_all_pass"] = all(s == "PASS" for s in statuses)
    except Exception as exc:
        meta["error"] = f"{type(exc).__name__}: {exc}"
    return meta


def inspect_signal_ledger(path: Path) -> Dict[str, Any]:
    meta: Dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        return meta
    try:
        df = read_csv_any(path)
        meta["row_count"] = int(len(df))
        text_cols = [c for c in df.columns if df[c].dtype == object]
        mask = pd.Series(False, index=df.index)
        for c in text_cols:
            mask = mask | df[c].astype(str).str.contains("H64L|macro_tailwind|tailwind", case=False, na=False)
        h = df[mask].copy()
        meta["h64l_like_rows"] = int(len(h))
        tcol = find_time_col(df.columns)
        meta["time_column"] = tcol
        if len(h) and tcol:
            ts = pd.to_datetime(h[tcol], utc=True, errors="coerce")
            meta["h64l_min_time_utc"] = str(ts.min()) if ts.notna().any() else ""
            meta["h64l_max_time_utc"] = str(ts.max()) if ts.notna().any() else ""
        meta["columns"] = list(df.columns)
    except Exception as exc:
        meta["error"] = f"{type(exc).__name__}: {exc}"
    return meta


def make_markdown(summary: Dict[str, Any], out_paths: Dict[str, str]) -> str:
    return f"""# Stage171C H64L Evidence Recovery + Shadow Checklist

Generated UTC: `{summary['generated_utc']}`

Decision: `{summary['decision']}`  
Recommended action: `{summary['recommended_action']}`

## Scope

Read-only. No MT5 signal, no demo/live authorization, no threshold re-optimization.

## Why this stage exists

Stage171B still had `exact_rule_locked=false`, so the next productive action is not a broad audit or a scan. It is targeted evidence recovery plus immediate manual shadow logging.

## Findings

- Artifact hits scanned: `{summary['artifact_recovery']['hit_count']}`
- Supporting high-score artifacts: `{summary['artifact_recovery']['top_hit_count']}`
- Macro dataset used: `{summary['macro_dataset']['path']}`
- H64L columns missing from dataset: `{summary['macro_dataset'].get('missing_h64l_columns', [])}`
- Latest checklist all known: `{summary['current_shadow_checklist'].get('all_known')}`
- Latest checklist all pass: `{summary['current_shadow_checklist'].get('all_pass')}`
- Signal ledger H64L-like rows: `{summary['signal_ledger'].get('h64l_like_rows')}`

## Current checklist

| feature | mapped column | condition | latest value | status |
|---|---|---:|---:|---:|
""" + "\n".join(
        f"| {r['feature']} | {r.get('mapped_column','')} | {r['condition']} | {r.get('latest_value','')} | {r['condition_status']} |"
        for r in summary['current_shadow_checklist'].get('rows', [])
    ) + f"""

## Decision logic

- If exact Stage64R evidence is recovered and all H64L columns are available, continue targeted as-of fixes and shadow logging.
- If exact evidence remains missing, keep the rule as reconstructed/inconclusive and request specialist confirmation before any demo bridge.
- If latest checklist passes, log a shadow hit only; do not route orders.

## Outputs

```text
{chr(10).join(out_paths.values())}
```
"""


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--root", required=True)
    ap.add_argument("--stage171b-summary", required=False)
    ap.add_argument("--locked-rule-candidate", required=False)
    ap.add_argument("--targeted-asof-plan", required=False)
    ap.add_argument("--macro-feature-dataset", required=False, default="data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv")
    ap.add_argument("--macro-signal-ledger", required=False, default="data/forward_shadow/stage65_macro_signal_ledger.csv")
    ap.add_argument("--output-dir", required=False, default=DEFAULT_OUTPUT)
    args = ap.parse_args(argv)

    root = Path(args.root).expanduser()
    outdir = root / args.output_dir
    outdir.mkdir(parents=True, exist_ok=True)

    stage171b = read_json(Path(args.stage171b_summary).expanduser() if args.stage171b_summary else None)
    rule_candidate = read_json(Path(args.locked_rule_candidate).expanduser() if args.locked_rule_candidate else None)

    asof_plan_rows: List[Dict[str, Any]] = []
    if args.targeted_asof_plan:
        p = Path(args.targeted_asof_plan).expanduser()
        if p.exists():
            try:
                asof_plan_rows = read_csv_any(p).to_dict("records")
            except Exception:
                asof_plan_rows = []

    artifact_hits = scan_h64l_artifacts(root)

    dataset_path = Path(args.macro_feature_dataset)
    if not dataset_path.is_absolute():
        dataset_path = root / dataset_path
    dataset_meta = inspect_dataset(dataset_path)

    # If default dataset does not exist or lacks all features, inspect likely alternatives and prefer better one.
    alternatives = []
    for rel in LIKELY_DATASETS:
        p = root / rel
        if p == dataset_path:
            continue
        alternatives.append(inspect_dataset(p) if "feature_dataset" in rel else {"path": str(p), "exists": p.exists()})
    best = dataset_meta
    for alt in alternatives:
        if not alt.get("exists") or "column_map" not in alt:
            continue
        cur_missing = len(best.get("missing_h64l_columns", [1, 2, 3, 4])) if best.get("exists") else 99
        alt_missing = len(alt.get("missing_h64l_columns", [1, 2, 3, 4]))
        if alt_missing < cur_missing:
            best = alt
    dataset_meta = best

    ledger_path = Path(args.macro_signal_ledger)
    if not ledger_path.is_absolute():
        ledger_path = root / ledger_path
    ledger_meta = inspect_signal_ledger(ledger_path)

    checklist_rows = dataset_meta.get("latest_checklist", []) if isinstance(dataset_meta, dict) else []
    all_known = bool(dataset_meta.get("latest_h64l_all_known"))
    all_pass = bool(dataset_meta.get("latest_h64l_all_pass"))

    exact_locked_prior = bool(rule_candidate.get("exact_rule_locked", False))
    recovered_evidence = bool(ledger_meta.get("h64l_like_rows", 0)) or any("stage64" in h.get("path", "").lower() and h.get("score", 0) >= 10 for h in artifact_hits[:20])
    all_cols_available = all_known

    if exact_locked_prior and all_cols_available:
        decision = "STAGE171C_H64L_EXACT_RULE_ALREADY_LOCKED_SHADOW_CHECKLIST_READY"
    elif recovered_evidence and all_cols_available:
        decision = "STAGE171C_H64L_EVIDENCE_FOUND_SHADOW_CHECKLIST_READY_PENDING_SPECIALIST_CONFIRMATION"
    elif all_cols_available:
        decision = "STAGE171C_H64L_RECONSTRUCTED_CHECKLIST_READY_BUT_RULE_EVIDENCE_INCONCLUSIVE"
    else:
        decision = "STAGE171C_H64L_INCONCLUSIVE_MISSING_RULE_OR_FEATURE_COLUMNS"

    recommended_action = (
        "CONTINUE_MANUAL_SHADOW_LOGGING; RECOVER_STAGE64R_RAW_EPISODES; APPLY_ONLY_MECHANICAL_ASOF_FIXES; NO_ORDERS"
    )

    top_hits = artifact_hits[:30]
    artifact_csv = outdir / "stage171c_h64l_artifact_deep_inventory.csv"
    write_csv(artifact_csv, artifact_hits)

    checklist_csv = outdir / "stage171c_h64l_current_shadow_checklist.csv"
    write_csv(checklist_csv, checklist_rows)

    column_map_csv = outdir / "stage171c_h64l_column_map.csv"
    cmap_rows = [{"canonical_column": k, "mapped_column": v or ""} for k, v in dataset_meta.get("column_map", {}).items()]
    write_csv(column_map_csv, cmap_rows)

    asof_csv = outdir / "stage171c_h64l_targeted_asof_fix_plan_review.csv"
    write_csv(asof_csv, asof_plan_rows)

    ledger_json = outdir / "stage171c_h64l_signal_ledger_inspection.json"
    write_json(ledger_json, ledger_meta)

    locked_rule_v1 = dict(rule_candidate or {})
    locked_rule_v1.update({
        "stage171c_decision": decision,
        "stage171c_exact_rule_locked": bool(rule_candidate.get("exact_rule_locked", False)),
        "stage171c_current_checklist_all_known": all_known,
        "stage171c_current_checklist_all_pass": all_pass,
        "stage171c_no_threshold_reoptimization": True,
        "stage171c_shadow_only_no_orders": True,
    })
    rule_out = outdir / "stage171c_h64l_locked_rule_candidate_v1.json"
    write_json(rule_out, locked_rule_v1)

    summary = {
        "stage": STAGE,
        "generated_utc": utc_now(),
        "root": str(root),
        "order_routing_allowed": False,
        "demo_release_allowed": False,
        "status": "STAGE171C_COMPLETE_H64L_EVIDENCE_AND_SHADOW_READY",
        "decision": decision,
        "severity": "HIGH",
        "recommended_action": recommended_action,
        "stage171b_prior": {
            "decision": stage171b.get("decision"),
            "exact_rule_locked": stage171b.get("exact_rule_locked"),
            "rule_confidence": stage171b.get("rule_confidence"),
            "artifact_hits": stage171b.get("artifact_hits"),
            "hard_constraints": stage171b.get("hard_constraints", {}),
        },
        "rule_candidate_prior": {
            "rule_id": rule_candidate.get("rule_id"),
            "exact_rule_locked": rule_candidate.get("exact_rule_locked"),
            "confidence": rule_candidate.get("confidence"),
            "conditions": rule_candidate.get("conditions", []),
        },
        "artifact_recovery": {
            "hit_count": len(artifact_hits),
            "top_hit_count": len(top_hits),
            "top_hits": top_hits[:10],
        },
        "macro_dataset": dataset_meta,
        "alternative_dataset_inspections": alternatives,
        "signal_ledger": ledger_meta,
        "current_shadow_checklist": {
            "all_known": all_known,
            "all_pass": all_pass,
            "rows": checklist_rows,
        },
        "asof_fix_plan_rows": len(asof_plan_rows),
        "hard_constraints": {
            "manual_shadow_allowed_now": True,
            "orders_allowed": False,
            "threshold_reoptimization_allowed": False,
            "only_mechanical_asof_fixes": True,
            "incomplete_after_timebox": "INCONCLUSIVE_NOT_OPEN_ENDED_AUDIT",
        },
        "outputs": {
            "summary_json": str(outdir / "stage171c_h64l_evidence_shadow_summary.json"),
            "decision_md": str(outdir / "stage171c_decision.md"),
            "artifact_inventory_csv": str(artifact_csv),
            "current_shadow_checklist_csv": str(checklist_csv),
            "column_map_csv": str(column_map_csv),
            "asof_fix_plan_review_csv": str(asof_csv),
            "signal_ledger_inspection_json": str(ledger_json),
            "locked_rule_candidate_v1_json": str(rule_out),
        },
        "next": [
            "If current checklist has a hit, log it manually; do not route orders.",
            "If Stage64R raw episode evidence remains missing, send artifact inventory or recover Stage64R reports before specialist demo decision.",
            "Apply only mechanical as-of fixes for H64L features; no threshold changes.",
            "After the 3-business-day timebox, mark PASS/FAIL/INCONCLUSIVE and do not extend audit indefinitely.",
        ],
    }

    summary_path = outdir / "stage171c_h64l_evidence_shadow_summary.json"
    decision_path = outdir / "stage171c_decision.md"
    write_json(summary_path, summary)
    decision_path.write_text(make_markdown(summary, summary["outputs"]), encoding="utf-8")

    print(json.dumps({"stage": STAGE, "decision": decision, "summary": str(summary_path), "decision_md": str(decision_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
