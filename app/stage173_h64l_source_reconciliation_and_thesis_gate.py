#!/usr/bin/env python3
"""Stage173 — H64L source reconciliation and prior-thesis delta gate.

This stage does not scan for alpha. It repairs the current WGC ETF semantic
mapping, inventories the original Stage64R/H64L source contracts, corrects the
Stage172 governance classification, and prevents re-running previously failed
thesis families without a documented material delta.

No order, demo, paper-order, live, threshold optimization, or ML path exists.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

STAGE = "Stage173_H64L_SOURCE_RECONCILIATION_AND_PRIOR_THESIS_DELTA_GATE"
DEFAULT_OUT = "reports/stage173_h64l_source_reconciliation_and_thesis_gate"


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def utc_iso(x: Optional[dt.datetime] = None) -> str:
    y = (x or utc_now()).astimezone(dt.timezone.utc).replace(microsecond=0)
    return y.isoformat().replace("+00:00", "Z")


def resolve(root: Path, value: str | Path) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else root / p


def detect_sep(path: Path) -> str:
    line = path.open("r", encoding="utf-8-sig", errors="replace").readline()
    return max(["\t", ",", ";", "|"], key=line.count)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def parse_num(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if not s or s.lower() in {"nan", "none", "null", "."}:
        return None
    try:
        x = float(s)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def first_existing(root: Path, values: Sequence[str]) -> Optional[Path]:
    for value in values:
        p = resolve(root, value)
        if p.exists() and p.is_file():
            return p
    return None


def is_fund_key(name: Any) -> bool:
    return "equity" in str(name).strip().lower()


def extract_wgc_json_records(path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    df = pd.read_csv(path, sep=detect_sep(path), low_memory=False)
    sheet_col = next((c for c in df.columns if "sheet" in str(c).lower()), None)
    json_cols = [c for c in df.columns if "json" in str(c).lower() or "raw" in str(c).lower()]
    records: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        if sheet_col and "holdings by month" not in str(row.get(sheet_col, "")).lower():
            continue
        for jc in json_cols:
            raw = row.get(jc)
            if not isinstance(raw, str) or not raw.strip().startswith("{"):
                continue
            try:
                obj = json.loads(raw)
            except Exception:
                continue
            if isinstance(obj, dict):
                records.append(obj)
                break
    return records, {
        "path": str(path),
        "sha256": sha256(path),
        "rows_total": int(len(df)),
        "holdings_month_records": int(len(records)),
        "sheet_column": str(sheet_col) if sheet_col else None,
        "json_columns": [str(x) for x in json_cols],
    }


def resolve_holdings_column(records: Sequence[Dict[str, Any]]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for obj in records:
        d = obj.get("ticker") or obj.get("date") or obj.get("Date") or obj.get("month")
        if d is None:
            continue
        fund_values = [parse_num(v) for k, v in obj.items() if is_fund_key(k)]
        fund_values = [v for v in fund_values if v is not None]
        if len(fund_values) < 5:
            continue
        r: Dict[str, Any] = {"date": d, "fund_sum": float(sum(fund_values))}
        for k, v in obj.items():
            if k in {"ticker", "date", "Date", "month"} or is_fund_key(k):
                continue
            x = parse_num(v)
            if x is not None:
                r[str(k)] = x
        rows.append(r)
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError("No WGC holdings-by-month rows with fund-level values")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce", utc=True).dt.floor("D")
    frame = frame.dropna(subset=["date", "fund_sum"]).sort_values("date").drop_duplicates("date", keep="last")
    candidates: List[Dict[str, Any]] = []
    for c in frame.columns:
        if c in {"date", "fund_sum"}:
            continue
        values = pd.to_numeric(frame[c], errors="coerce")
        valid = values.notna() & (frame["fund_sum"] > 0)
        if int(valid.sum()) < 12:
            continue
        rel = ((values[valid] - frame.loc[valid, "fund_sum"]).abs() / frame.loc[valid, "fund_sum"]).dropna()
        candidates.append({
            "column": str(c),
            "rows": int(valid.sum()),
            "median_relative_error_to_fund_sum": float(rel.median()),
            "p90_relative_error_to_fund_sum": float(rel.quantile(0.9)),
            "latest_value": float(values[valid].iloc[-1]),
        })
    if not candidates:
        raise ValueError("No numeric WGC total candidate has sufficient coverage")
    candidates.sort(key=lambda r: (r["median_relative_error_to_fund_sum"], r["p90_relative_error_to_fund_sum"], -r["rows"], r["column"]))
    selected = candidates[0]
    if selected["median_relative_error_to_fund_sum"] > 0.02 or selected["p90_relative_error_to_fund_sum"] > 0.05:
        raise ValueError(f"No WGC candidate reconciles to fund holdings: best={selected}")
    col = selected["column"]
    out = pd.DataFrame({
        "date_utc": frame["date"],
        "holdings_tonnes": pd.to_numeric(frame[col], errors="coerce"),
        "fund_sum_tonnes": frame["fund_sum"],
    }).dropna().sort_values("date_utc").drop_duplicates("date_utc", keep="last")
    if len(out) < 12 or not out["holdings_tonnes"].between(10, 10000).all():
        raise ValueError("Resolved WGC holdings series fails level plausibility")
    return out, {"selected_column": col, "selected_score": selected, "candidate_scores": candidates}


def validate_anchors(series: pd.DataFrame, anchors: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    checks = []
    for anchor in anchors:
        target = pd.Timestamp(anchor["date"], tz="UTC")
        tol_days = int(anchor.get("date_tolerance_days", 4))
        tol_tonnes = float(anchor.get("tonnes_tolerance", 8.0))
        subset = series[(series["date_utc"] >= target - pd.Timedelta(days=tol_days)) & (series["date_utc"] <= target + pd.Timedelta(days=tol_days))]
        if subset.empty:
            checks.append({**anchor, "pass": False, "reason": "NO_NEARBY_ROW"})
            continue
        idx = (subset["date_utc"] - target).abs().idxmin()
        row = subset.loc[idx]
        diff = float(row["holdings_tonnes"] - float(anchor["holdings_tonnes"]))
        checks.append({
            **anchor,
            "matched_date": str(row["date_utc"].date()),
            "matched_holdings_tonnes": float(row["holdings_tonnes"]),
            "difference_tonnes": diff,
            "pass": abs(diff) <= tol_tonnes,
        })
    return {"checks": checks, "all_pass": bool(checks) and all(x.get("pass") for x in checks)}


def build_canonical_etf_series(series: pd.DataFrame, source: Path, cfg: Dict[str, Any], out_path: Path) -> Dict[str, Any]:
    x = series.copy().sort_values("date_utc")
    x["etf_flow_tonnes_3m"] = x["holdings_tonnes"] - x["holdings_tonnes"].shift(3)
    x["available_after_utc"] = x["date_utc"] + pd.to_timedelta(int(cfg["historical_release_lag_days"]), unit="D")
    x["source_path"] = str(source)
    x["source_sha256"] = sha256(source)
    x["semantic_contract"] = "GLOBAL_PHYSICALLY_BACKED_GOLD_ETF_HOLDINGS_TONNES_RESOLVED_BY_FUND_SUM"
    x["availability_contract"] = f"CONSERVATIVE_MONTH_END_PLUS_{int(cfg['historical_release_lag_days'])}_CALENDAR_DAYS"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    x.to_csv(out_path, index=False)
    latest = x.iloc[-1]
    max_abs_3m = float(x["etf_flow_tonnes_3m"].abs().max(skipna=True))
    return {
        "output": str(out_path),
        "rows": int(len(x)),
        "latest_date": str(latest["date_utc"].date()),
        "latest_holdings_tonnes": float(latest["holdings_tonnes"]),
        "latest_etf_flow_tonnes_3m": float(latest["etf_flow_tonnes_3m"]) if pd.notna(latest["etf_flow_tonnes_3m"]) else None,
        "max_abs_3m_change_tonnes": max_abs_3m,
        "plausibility_pass": max_abs_3m <= float(cfg["maximum_abs_3m_change_tonnes"]),
    }


def compare_historical_etf(root: Path, canonical: pd.DataFrame, candidates: Sequence[str]) -> Dict[str, Any]:
    path = first_existing(root, candidates)
    if path is None:
        return {"status": "HISTORICAL_FEATURE_DATASET_NOT_FOUND"}
    raw = pd.read_csv(path, sep=detect_sep(path), low_memory=False)
    lower = {str(c).strip().lower(): c for c in raw.columns}
    dc = next((lower[x] for x in ["feature_date_utc", "date_utc", "date", "timestamp"] if x in lower), None)
    ec = lower.get("etf_flow_tonnes_3m")
    if dc is None or ec is None:
        return {"status": "HISTORICAL_FEATURE_DATASET_SCHEMA_INVALID", "path": str(path), "columns": [str(c) for c in raw.columns]}
    hist = pd.DataFrame({
        "date": pd.to_datetime(raw[dc], errors="coerce", utc=True).dt.floor("D"),
        "historical_etf": pd.to_numeric(raw[ec], errors="coerce"),
    }).dropna().sort_values("date")
    canon = canonical[["available_after_utc", "etf_flow_tonnes_3m"]].dropna().sort_values("available_after_utc")
    merged = pd.merge_asof(hist, canon, left_on="date", right_on="available_after_utc", direction="backward")
    valid = merged.dropna(subset=["historical_etf", "etf_flow_tonnes_3m"])
    if valid.empty:
        return {"status": "NO_COMPARABLE_ROWS", "path": str(path)}
    diff = valid["historical_etf"] - valid["etf_flow_tonnes_3m"]
    corr = valid[["historical_etf", "etf_flow_tonnes_3m"]].corr().iloc[0, 1] if len(valid) >= 3 else None
    med = float(diff.abs().median())
    return {
        "status": "COMPARED",
        "path": str(path),
        "sha256": sha256(path),
        "rows": int(len(valid)),
        "median_abs_difference_tonnes": med,
        "p90_abs_difference_tonnes": float(diff.abs().quantile(0.9)),
        "correlation": float(corr) if corr is not None and pd.notna(corr) else None,
        "historical_etf_contract": "MATCHES_STAGE173_RECONCILED_ETF" if med <= 2.0 else "DIFFERS_FROM_STAGE173_RECONCILED_ETF",
    }


def iter_text_files(root: Path, cfg: Dict[str, Any]) -> Iterable[Path]:
    extensions = set(cfg["extensions"])
    excluded = [str(x).lower() for x in cfg["excluded_path_tokens"]]
    max_size = int(cfg["maximum_file_size_bytes"])
    for base_name in cfg["roots"]:
        base = resolve(root, base_name)
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in extensions:
                continue
            low = p.as_posix().lower()
            if any(token in low for token in excluded):
                continue
            try:
                if p.stat().st_size > max_size:
                    continue
            except OSError:
                continue
            yield p


def archaeology(root: Path, cfg: Dict[str, Any]) -> Dict[str, Any]:
    evidence: List[Dict[str, Any]] = []
    dxy_terms = ["DTWEXBGS", "DX-Y.NYB", "ICE DXY", "ICE_USDX", "dxy.csv", "dxy_ret_20d"]
    etf_terms = ["etf_flow_tonnes_3m", "Holdings by month", "col_3", "All units in tonnes unless otherwise specified"]
    horizon_patterns = [r"holding[_ -]?days[^\d]{0,8}(\d+)", r"holding[_ -]?horizon[^\d]{0,8}(\d+)", r"horizon[_ -]?days[^\d]{0,8}(\d+)", r"hold[_ -]?days[^\d]{0,8}(\d+)"]
    for p in iter_text_files(root, cfg):
        try:
            text = p.read_text(encoding="utf-8-sig", errors="replace")
        except Exception:
            continue
        low = text.lower()
        if not any(x in low for x in ["h64l", "stage64r", "etf_flow_tonnes_3m", "dxy_ret_20d"]):
            continue
        dxy_hits = [x for x in dxy_terms if x.lower() in low]
        etf_hits = [x for x in etf_terms if x.lower() in low]
        horizon_hits: List[str] = []
        for pattern in horizon_patterns:
            horizon_hits.extend(m.group(0)[:80] for m in re.finditer(pattern, text, flags=re.IGNORECASE))
        evidence.append({
            "path": str(p.relative_to(root)) if p.is_relative_to(root) else str(p),
            "sha256": sha256(p),
            "size_bytes": int(p.stat().st_size),
            "h64l": "h64l" in low,
            "stage64r": "stage64r" in low,
            "dxy_hits": ";".join(dxy_hits),
            "etf_hits": ";".join(etf_hits),
            "horizon_hits": ";".join(horizon_hits[:12]),
        })
    strong = [r for r in evidence if any(token in r["path"].lower() for token in ["stage64", "stage66a", "h64l_locked_rule"])]
    joined_dxy = " ".join(r["dxy_hits"] for r in strong)
    if "DTWEXBGS" in joined_dxy and any(x in joined_dxy for x in ["DX-Y.NYB", "ICE DXY", "ICE_USDX"]):
        dxy_status = "UNRESOLVED_MULTIPLE_DXY_CONTRACTS_IN_STAGE64_EVIDENCE"
    elif "DTWEXBGS" in joined_dxy:
        dxy_status = "ORIGINAL_STAGE64_EVIDENCE_POINTS_TO_DTWEXBGS_PROXY"
    elif any(x in joined_dxy for x in ["DX-Y.NYB", "ICE DXY", "ICE_USDX"]):
        dxy_status = "ORIGINAL_STAGE64_EVIDENCE_POINTS_TO_ICE_DXY"
    else:
        dxy_status = "DXY_SOURCE_CONTRACT_UNRESOLVED"
    horizon_values: List[int] = []
    for r in strong:
        for number in re.findall(r"(?:holding[_ -]?days|holding[_ -]?horizon|horizon[_ -]?days|hold[_ -]?days)(?:[^\d]{0,8})(\d{1,3})", r["horizon_hits"], flags=re.IGNORECASE):
            try:
                horizon_values.append(int(number))
            except Exception:
                pass
    unique_horizons = sorted(set(x for x in horizon_values if 1 <= x <= 240))
    horizon_status = "HOLDING_HORIZON_UNRESOLVED" if len(unique_horizons) != 1 else "HOLDING_HORIZON_SINGLE_CANDIDATE_FOUND"
    return {
        "evidence": evidence,
        "dxy_source_contract_status": dxy_status,
        "holding_horizon_status": horizon_status,
        "holding_horizon_candidates": unique_horizons,
        "stage64_evidence_count": int(len(strong)),
    }


def correct_stage172(root: Path, cfg: Dict[str, Any], out: Path) -> Dict[str, Any]:
    source = first_existing(root, cfg["summary_candidates"])
    if source is None:
        return {"status": "STAGE172_SUMMARY_NOT_FOUND"}
    summary = json.loads(source.read_text(encoding="utf-8"))
    original_a = dict(summary.get("track_a") or {})
    original_b = dict(summary.get("track_b") or {})
    corrected_a = dict(original_a)
    if original_a.get("status") == "BLOCKED":
        corrected_a["decision"] = "INCONCLUSIVE_BLOCKED"
        corrected_a["governance_correction"] = "MISSING_OR_INVALID_INPUT_IS_NOT_A_NEGATIVE_PERFORMANCE_RESULT"
    exact_kills = []
    for row in original_b.get("results") or []:
        if row.get("survives") is False and int((row.get("holdout_metrics") or {}).get("trades") or 0) > 0:
            exact_kills.append({"strategy": row.get("strategy"), "direction": row.get("direction")})
    corrected = {
        "source": str(source),
        "source_sha256": sha256(source),
        "track_a_original": original_a,
        "track_a_corrected": corrected_a,
        "track_b_decision": original_b.get("decision"),
        "track_b_exact_tested_formulations_killed": exact_kills,
        "ml_allowed": False,
        "program_state": "H64L_SUSPENDED_PENDING_SOURCE_RECONCILIATION_STAGE172_EXACT_BASELINES_KILLED_NO_ML",
    }
    write_json(out / "stage172_governance_correction.json", corrected)
    md = [
        "# Stage172 Governance Correction",
        "",
        f"Source: `{source}`",
        "",
        "- Track A was blocked by missing/invalid historical-as-of input; it was not statistically killed.",
        "- Correct Track A state: `INCONCLUSIVE_BLOCKED`.",
        "- Track B kills only the exact tested formulations with actual holdout trades.",
        "- ML remains forbidden.",
        "- H64L remains suspended as an interpretable signal until ETF/DXY contracts are reconciled.",
    ]
    (out / "stage172_governance_correction.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return corrected


def thesis_delta_matrix(root: Path, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for family in cfg["families"]:
        hits: List[str] = []
        for pattern in family["artifact_patterns"]:
            for p in root.glob(pattern):
                if p.is_file():
                    hits.append(str(p.relative_to(root)))
        hits = sorted(set(hits))
        rows.append({
            "family": family["family"],
            "prior_result": family["prior_result"],
            "artifact_hits": len(hits),
            "sample_artifacts": ";".join(hits[:8]),
            "rerun_policy": family["rerun_policy"],
            "required_material_delta": family["required_material_delta"],
        })
    return rows


def decision_md(summary: Dict[str, Any]) -> str:
    etf = summary["etf_reconciliation"]
    arch = summary["archaeology"]
    lines = [
        "# Stage173 Decision",
        "",
        f"Generated: {summary['generated_utc']}",
        "",
        "## Hard controls",
        "",
        "- Orders/demo/live: forbidden.",
        "- ML: forbidden.",
        "- Broad scan: forbidden.",
        "- Previously failed families cannot be rerun without a pre-written material delta.",
        "",
        "## ETF reconciliation",
        "",
        f"Status: `{etf.get('status')}`",
        f"Selected WGC holdings column: `{etf.get('selected_column')}`",
        f"Latest 3-month holdings change: `{etf.get('canonical', {}).get('latest_etf_flow_tonnes_3m')}` tonnes",
        "",
        "## Stage64R archaeology",
        "",
        f"DXY source contract: `{arch.get('dxy_source_contract_status')}`",
        f"Holding horizon: `{arch.get('holding_horizon_status')}`",
        f"Candidates: `{arch.get('holding_horizon_candidates')}`",
        "",
        "## Corrected program decision",
        "",
        f"**`{summary['program_decision']}`**",
        "",
        "Stage172's tested technical formulations stay killed. H64L may be rerun only after source and horizon contracts are validated. No new COT scan or generic technical rescan is authorized.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="~/Desktop/xauusd-trader")
    ap.add_argument("--config", default="configs/stage173_h64l_source_reconciliation_and_thesis_gate.json")
    ap.add_argument("--out-dir", default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    cfg = json.loads(resolve(root, args.config).read_text(encoding="utf-8"))
    out = resolve(root, args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    issues: List[str] = []

    source = first_existing(root, cfg["etf"]["normalized_wgc_candidates"])
    etf_summary: Dict[str, Any]
    canonical_df: Optional[pd.DataFrame] = None
    if source is None:
        etf_summary = {"status": "BLOCKED_WGC_NORMALIZED_ROWS_NOT_FOUND"}
        issues.append("WGC_NORMALIZED_ROWS_NOT_FOUND")
    else:
        try:
            records, source_meta = extract_wgc_json_records(source)
            series, resolution = resolve_holdings_column(records)
            anchors = validate_anchors(series, cfg["etf"]["official_anchors"])
            canonical_path = resolve(root, cfg["etf"]["canonical_output"])
            canonical = build_canonical_etf_series(series, source, cfg["etf"], canonical_path)
            canonical_df = pd.read_csv(canonical_path, parse_dates=["date_utc", "available_after_utc"])
            comparison = compare_historical_etf(root, canonical_df, cfg["historical"]["feature_dataset_candidates"])
            pass_all = anchors["all_pass"] and canonical["plausibility_pass"]
            etf_summary = {
                "status": "PASS_RECONCILED" if pass_all else "BLOCKED_RECONCILIATION_CHECK_FAILED",
                **source_meta,
                **resolution,
                "anchor_validation": anchors,
                "canonical": canonical,
                "historical_comparison": comparison,
            }
            if not pass_all:
                issues.append("ETF_RECONCILIATION_CHECK_FAILED")
        except Exception as exc:
            etf_summary = {"status": "BLOCKED_RECONCILIATION_EXCEPTION", "path": str(source), "error": f"{type(exc).__name__}:{exc}"}
            issues.append(f"ETF_RECONCILIATION_EXCEPTION:{type(exc).__name__}:{exc}")

    arch = archaeology(root, cfg["archaeology"])
    pd.DataFrame(arch.pop("evidence")).to_csv(out / "stage173_h64l_archaeology_evidence.csv", index=False)
    correction = correct_stage172(root, cfg["stage172_correction"], out)
    thesis_rows = thesis_delta_matrix(root, cfg["prior_thesis_gate"])
    pd.DataFrame(thesis_rows).to_csv(out / "stage173_prior_thesis_delta_matrix.csv", index=False)

    if etf_summary.get("status") != "PASS_RECONCILED":
        program_decision = "BLOCK_H64L_ETF_RECONCILIATION_FAILED_KEEP_ALL_EXECUTION_FORBIDDEN"
    elif arch["dxy_source_contract_status"] == "DXY_SOURCE_CONTRACT_UNRESOLVED" or arch["dxy_source_contract_status"].startswith("UNRESOLVED"):
        program_decision = "H64L_ETF_FIXED_BLOCK_TRACK_A_PENDING_DXY_ARCHAEOLOGY_NO_NEW_SCAN"
    elif arch["holding_horizon_status"] != "HOLDING_HORIZON_SINGLE_CANDIDATE_FOUND":
        program_decision = "H64L_SOURCES_PARTLY_RESOLVED_BLOCK_TRACK_A_PENDING_HORIZON_CONTRACT_NO_NEW_SCAN"
    else:
        program_decision = "READY_TO_BUILD_VALIDATED_H64L_HISTORICAL_ASOF_TABLE_AND_RERUN_TRACK_A_ONLY"

    summary = {
        "stage": STAGE,
        "generated_utc": utc_iso(),
        "root": str(root),
        "hard_controls": {
            "orders_allowed": False,
            "demo_allowed": False,
            "live_allowed": False,
            "paper_order_allowed": False,
            "ml_allowed": False,
            "broad_scan_allowed": False,
        },
        "issues": issues,
        "etf_reconciliation": etf_summary,
        "archaeology": arch,
        "stage172_correction": correction,
        "prior_thesis_delta_matrix": thesis_rows,
        "program_decision": program_decision,
    }
    write_json(out / "stage173_summary.json", summary)
    (out / "stage173_decision.md").write_text(decision_md(summary), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
