#!/usr/bin/env python3
"""Stage64R external broker/spot D1 intake + transfer fastlane.

No order path. No broker connection. No hypothesis scan/tuning.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Dict, Iterable, List, Optional, Tuple

STAGE = "Stage64R_EXTERNAL_SPOT_D1_INTAKE_TRANSFER_FASTLANE_NO_ORDER"


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=False)


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = []
        for r in rows:
            for k in r.keys():
                if k not in fieldnames:
                    fieldnames.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_date(value: Any) -> Optional[dt.date]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    # strip time if simple common case
    candidates = [s]
    if "T" in s:
        candidates.append(s.split("T", 1)[0])
    if " " in s:
        candidates.append(s.split(" ", 1)[0])
    for c in candidates:
        try:
            return dt.datetime.fromisoformat(c).date()
        except Exception:
            pass
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y", "%Y.%m.%d"):
            try:
                return dt.datetime.strptime(c, fmt).date()
            except Exception:
                pass
    return None


def parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if s == "" or s.lower() in {"nan", "none", "null"}:
        return None
    try:
        x = float(s)
    except Exception:
        return None
    if not math.isfinite(x):
        return None
    return x


def normalize_header(h: str) -> str:
    return str(h).strip().lower().replace(" ", "_").replace("-", "_").replace(".", "_")


def pick_column(headers: List[str], candidates: Iterable[str]) -> Optional[str]:
    norm_map = {normalize_header(h): h for h in headers}
    for c in candidates:
        if c in norm_map:
            return norm_map[c]
    return None


def read_dataset(path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    info = {"path": str(path), "found": path.exists(), "rows": 0, "parse_errors": 0, "columns": []}
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows, info
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        info["columns"] = reader.fieldnames or []
        for raw in reader:
            d = parse_date(raw.get("feature_date_utc"))
            close = parse_float(raw.get("gold_close"))
            if d is None or close is None:
                info["parse_errors"] += 1
                continue
            r = dict(raw)
            r["_date"] = d
            r["_gold_close"] = close
            rows.append(r)
    rows.sort(key=lambda x: x["_date"])
    info["rows"] = len(rows)
    return rows, info


def read_external_d1(path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    info: Dict[str, Any] = {"path": str(path), "found": path.exists(), "raw_rows": 0, "parsed_rows": 0, "parse_errors": 0, "columns": [], "issue": None}
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        info["issue"] = "external_d1_file_missing"
        return rows, info
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        info["columns"] = headers
        date_col = pick_column(headers, ["date_utc", "time_utc", "utc_time", "date", "datetime", "time", "timestamp"])
        open_col = pick_column(headers, ["open", "o"])
        high_col = pick_column(headers, ["high", "h"])
        low_col = pick_column(headers, ["low", "l"])
        close_col = pick_column(headers, ["close", "c", "last", "price"])
        volume_col = pick_column(headers, ["volume", "vol", "tick_volume", "real_volume"])
        info.update({"date_col": date_col, "open_col": open_col, "high_col": high_col, "low_col": low_col, "close_col": close_col, "volume_col": volume_col})
        if not date_col or not close_col:
            info["issue"] = "required_date_or_close_column_missing"
            return rows, info
        by_date: Dict[dt.date, Dict[str, Any]] = {}
        for raw in reader:
            info["raw_rows"] += 1
            d = parse_date(raw.get(date_col))
            c = parse_float(raw.get(close_col))
            if d is None or c is None:
                info["parse_errors"] += 1
                continue
            o = parse_float(raw.get(open_col)) if open_col else None
            h = parse_float(raw.get(high_col)) if high_col else None
            l = parse_float(raw.get(low_col)) if low_col else None
            v = parse_float(raw.get(volume_col)) if volume_col else None
            by_date[d] = {
                "date_utc": d.isoformat(),
                "open": o if o is not None else c,
                "high": h if h is not None else c,
                "low": l if l is not None else c,
                "close": c,
                "volume": v if v is not None else 0.0,
                "source": raw.get("source") or raw.get("Source") or "EXTERNAL_BROKER_OR_SPOT_D1_USER_SUPPLIED",
                "available_after_utc": raw.get("available_after_utc") or (d.isoformat() + "T23:59:59Z"),
            }
    rows = [by_date[d] for d in sorted(by_date)]
    for r in rows:
        r["_date"] = parse_date(r["date_utc"])
        r["_close"] = float(r["close"])
    info["parsed_rows"] = len(rows)
    if rows:
        info["first_date"] = rows[0]["date_utc"]
        info["last_date"] = rows[-1]["date_utc"]
    return rows, info


def add_broker_trend_features(rows: List[Dict[str, Any]]) -> None:
    closes = [float(r["_close"]) for r in rows]
    for i, r in enumerate(rows):
        def sma(n: int) -> Optional[float]:
            if i + 1 < n:
                return None
            return sum(closes[i + 1 - n:i + 1]) / n
        s20, s50, s200 = sma(20), sma(50), sma(200)
        r["broker_sma20"] = s20
        r["broker_sma50"] = s50
        r["broker_sma200"] = s200
        r["broker_sma20_over_50"] = None if s20 is None or s50 is None else s20 - s50
        r["broker_sma50_over_200"] = None if s50 is None or s200 is None else s50 - s200
        if i + 120 < len(rows):
            fwd = (closes[i + 120] / closes[i] - 1.0) * 10000.0
            r["fwd_120_bps"] = fwd
        else:
            r["fwd_120_bps"] = None


def safe_gt(row: Dict[str, Any], col: str, threshold: float) -> bool:
    x = parse_float(row.get(col))
    return x is not None and x > threshold


def safe_lt(row: Dict[str, Any], col: str, threshold: float) -> bool:
    x = parse_float(row.get(col))
    return x is not None and x < threshold


def broker_b1_rule(row: Dict[str, Any]) -> bool:
    return safe_gt(row, "broker_sma20_over_50", 0.0) and safe_gt(row, "broker_sma50_over_200", 0.0)


def candidate_rule(row: Dict[str, Any]) -> bool:
    return (
        broker_b1_rule(row)
        and safe_lt(row, "dxy_ret_20d", 0.0)
        and safe_lt(row, "real_yield_change_20d", 0.0)
        and safe_gt(row, "etf_flow_tonnes_3m", 0.0)
        and safe_gt(row, "central_bank_demand_tonnes_6m", 0.0)
    )


def z_p_one_sided_gt_zero(values: List[float]) -> float:
    if len(values) < 2:
        return 1.0
    m = mean(values)
    sd = pstdev(values)
    if sd <= 0:
        return 0.0 if m > 0 else 1.0
    z = m / (sd / math.sqrt(len(values)))
    # survival function for standard normal: 0.5*erfc(z/sqrt(2))
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def split_id_for_date(d: dt.date, splits: List[Dict[str, str]]) -> Optional[str]:
    for s in splits:
        if parse_date(s["start"]) <= d <= parse_date(s["end"]):
            return s["split_id"]
    return None


def evaluate_transfer(dataset: List[Dict[str, Any]], external_rows: List[Dict[str, Any]], cfg: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
    add_broker_trend_features(external_rows)
    ext_by_date = {r["_date"]: r for r in external_rows}
    joined: List[Dict[str, Any]] = []
    candidate_returns: List[float] = []
    b1_returns: List[float] = []
    split_candidate: Dict[str, List[float]] = defaultdict(list)
    split_b1: Dict[str, List[float]] = defaultdict(list)
    year_counts: Counter[str] = Counter()

    for feat in dataset:
        d = feat["_date"]
        ext = ext_by_date.get(d)
        if not ext:
            continue
        fwd = ext.get("fwd_120_bps")
        if fwd is None:
            continue
        row = dict(feat)
        row.update({
            "broker_close": ext["_close"],
            "broker_sma20_over_50": ext.get("broker_sma20_over_50"),
            "broker_sma50_over_200": ext.get("broker_sma50_over_200"),
            "broker_fwd_120_bps": fwd,
        })
        is_b1 = broker_b1_rule(row)
        is_candidate = candidate_rule(row)
        sid = split_id_for_date(d, cfg["split_definitions"])
        rec = {
            "date_utc": d.isoformat(),
            "split_id": sid or "OUT_OF_SPLIT",
            "broker_close": ext["_close"],
            "broker_fwd_120_bps": fwd,
            "broker_b1_active": is_b1,
            "candidate_active": is_candidate,
        }
        joined.append(rec)
        if is_b1:
            b1_returns.append(fwd)
            if sid:
                split_b1[sid].append(fwd)
        if is_candidate:
            candidate_returns.append(fwd)
            year_counts[str(d.year)] += 1
            if sid:
                split_candidate[sid].append(fwd)

    split_rows: List[Dict[str, Any]] = []
    positive_splits = 0
    for s in cfg["split_definitions"]:
        sid = s["split_id"]
        cvals = split_candidate.get(sid, [])
        bvals = split_b1.get(sid, [])
        cmean = mean(cvals) if cvals else None
        bmean = mean(bvals) if bvals else None
        excess = (cmean - bmean) if cmean is not None and bmean is not None else None
        pos = bool(excess is not None and excess > 0)
        if pos:
            positive_splits += 1
        split_rows.append({
            "split_id": sid,
            "candidate_active_days": len(cvals),
            "benchmark_active_days": len(bvals),
            "candidate_mean_bps": cmean,
            "benchmark_mean_bps": bmean,
            "excess_vs_external_B1_bps": excess,
            "positive_excess": pos,
        })

    c_active = len(candidate_returns)
    b_active = len(b1_returns)
    c_mean = mean(candidate_returns) if candidate_returns else None
    b_mean = mean(b1_returns) if b1_returns else None
    excess = (c_mean - b_mean) if c_mean is not None and b_mean is not None else None
    diffs = []
    # For p-value, use candidate returns minus benchmark mean, matching prior project approximation style.
    if b_mean is not None:
        diffs = [x - b_mean for x in candidate_returns]
    p_unc = z_p_one_sided_gt_zero(diffs) if diffs else 1.0
    split_counts = {k: len(v) for k, v in split_candidate.items()}
    max_split_share = (max(split_counts.values()) / c_active) if c_active else 1.0
    max_year_share = (max(year_counts.values()) / c_active) if c_active else 1.0

    gates_cfg = cfg["transfer_gates"]
    gates = [
        {"gate": "min_joined_return_days", "value": len(joined), "op": ">=", "threshold": gates_cfg["min_joined_return_days"], "pass": len(joined) >= gates_cfg["min_joined_return_days"]},
        {"gate": "min_candidate_active_days", "value": c_active, "op": ">=", "threshold": gates_cfg["min_candidate_active_days"], "pass": c_active >= gates_cfg["min_candidate_active_days"]},
        {"gate": "mean_excess_vs_external_B1_bps", "value": excess, "op": ">", "threshold": gates_cfg["mean_excess_vs_external_B1_bps_min_exclusive"], "pass": excess is not None and excess > gates_cfg["mean_excess_vs_external_B1_bps_min_exclusive"]},
        {"gate": "one_sided_p_uncorrected_z_approx", "value": p_unc, "op": "<=", "threshold": gates_cfg["one_sided_p_uncorrected_z_approx_max"], "pass": p_unc <= gates_cfg["one_sided_p_uncorrected_z_approx_max"]},
        {"gate": "positive_excess_splits_vs_external_B1", "value": positive_splits, "op": ">=", "threshold": gates_cfg["positive_excess_splits_vs_external_B1_min"], "pass": positive_splits >= gates_cfg["positive_excess_splits_vs_external_B1_min"]},
        {"gate": "max_split_share_of_candidate_active_days", "value": max_split_share, "op": "<=", "threshold": gates_cfg["max_split_share_of_candidate_active_days_max"], "pass": max_split_share <= gates_cfg["max_split_share_of_candidate_active_days_max"]},
        {"gate": "max_year_share_of_candidate_active_days", "value": max_year_share, "op": "<=", "threshold": gates_cfg["max_year_share_of_candidate_active_days_max"], "pass": max_year_share <= gates_cfg["max_year_share_of_candidate_active_days_max"]},
    ]
    overall = {
        "horizon_days": 120,
        "joined_return_days": len(joined),
        "candidate_active_days": c_active,
        "candidate_mean_bps": c_mean,
        "external_B1_active_days": b_active,
        "external_B1_mean_bps": b_mean,
        "mean_excess_vs_external_B1_bps": excess,
        "one_sided_p_uncorrected_z_approx": p_unc,
        "positive_excess_splits_vs_external_B1": positive_splits,
        "max_split_share_of_candidate_active_days": max_split_share,
        "max_year_share_of_candidate_active_days": max_year_share,
        "candidate_split_counts": split_counts,
        "candidate_year_counts_top10": dict(year_counts.most_common(10)),
        "transfer_pass": all(g["pass"] for g in gates),
        "gates": gates,
    }
    return overall, split_rows, joined


def ensure_template(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    rows = [
        {"date_utc": "2011-01-03", "open": "", "high": "", "low": "", "close": "", "volume": "", "source": "EXTERNAL_BROKER_OR_SPOT_D1", "available_after_utc": "2011-01-03T23:59:59Z"}
    ]
    write_csv(path, rows, ["date_utc", "open", "high", "low", "close", "volume", "source", "available_after_utc"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    cfg_path = Path(args.config)
    if not cfg_path.is_absolute():
        cfg_path = root / cfg_path
    out = Path(args.out)
    if not out.is_absolute():
        out = root / out
    out.mkdir(parents=True, exist_ok=True)

    cfg = read_json(cfg_path)
    rel = cfg["root_relative_paths"]
    stage64q_summary_path = root / rel["stage64q_summary"]
    dataset_path = root / rel["stage64k_dataset"]
    external_path = root / rel["external_spot_d1_raw"]
    template_path = root / rel["external_spot_d1_template"]
    ensure_template(template_path)

    generated = utc_now()
    stage64q = read_json(stage64q_summary_path) if stage64q_summary_path.exists() else {}
    dataset, dataset_info = read_dataset(dataset_path)
    external_rows, external_info = read_external_d1(external_path)

    preflight = {
        "external_file_found": external_info.get("found"),
        "external_rows": external_info.get("parsed_rows", 0),
        "external_first_date": external_info.get("first_date"),
        "external_last_date": external_info.get("last_date"),
        "external_issue": external_info.get("issue"),
        "dataset_found": dataset_info.get("found"),
        "dataset_rows": dataset_info.get("rows", 0),
    }

    transfer: Dict[str, Any] = {"data_available": False, "transfer_pass": False, "overall": {}, "split_rows": [], "joined_rows_written": False}
    external_preflight_ok = False
    if external_rows and dataset:
        gates0 = cfg["external_spot_preflight_gates"]
        first_ok = parse_date(external_info.get("first_date")) is not None and parse_date(external_info.get("first_date")) <= parse_date(gates0["min_first_date"])
        rows_ok = len(external_rows) >= int(gates0["min_rows"])
        last_ok = True
        if dataset:
            ds_last = dataset[-1]["_date"]
            ext_last = parse_date(external_info.get("last_date"))
            last_ok = ext_last is not None and (ds_last - ext_last).days <= int(gates0["max_last_date_lag_days_from_dataset_last"])
        external_preflight_ok = bool(rows_ok and first_ok and last_ok)
        preflight.update({"external_rows_ok": rows_ok, "external_first_date_ok": first_ok, "external_last_date_ok": last_ok, "external_preflight_ok": external_preflight_ok})
        if external_preflight_ok:
            overall, split_rows, joined_rows = evaluate_transfer(dataset, external_rows, cfg)
            write_csv(out / "stage64r_external_spot_transfer_splits.csv", split_rows)
            # keep joined rows local/report only; can be large but acceptable
            write_csv(out / "stage64r_external_spot_transfer_joined_returns.csv", joined_rows)
            canonical = [{k: r[k] for k in ["date_utc", "open", "high", "low", "close", "volume", "source", "available_after_utc"]} for r in external_rows]
            write_csv(out / "stage64r_external_spot_d1_canonical.csv", canonical)
            transfer = {"data_available": True, "transfer_pass": overall["transfer_pass"], "overall": overall, "split_rows": split_rows, "joined_rows_written": True}

    if not external_info.get("found"):
        decision = "EXTERNAL_BROKER_OR_SPOT_D1_FILE_REQUIRED_NO_ORDER"
        status = "EXTERNAL_SPOT_D1_INTAKE_WAITING_FOR_DATA_NO_PROMOTION"
        next_step = "ACQUIRE_EXTERNAL_BROKER_OR_SPOT_D1_CSV_AND_RERUN_STAGE64R_NO_ORDER"
        conclusion = "External broker/spot D1 file is not present. A template was ensured; acquire the file and rerun Stage64R. No order path is authorized."
    elif not external_preflight_ok:
        decision = "EXTERNAL_BROKER_OR_SPOT_D1_PREFLIGHT_FAILED_FIX_FILE_OR_REDESIGN_NO_ORDER"
        status = "EXTERNAL_SPOT_D1_INTAKE_PREFLIGHT_FAILED_NO_PROMOTION"
        next_step = "FIX_EXTERNAL_BROKER_OR_SPOT_D1_CSV_AND_RERUN_STAGE64R_OR_REDESIGN_NO_ORDER"
        conclusion = "External broker/spot D1 file is present but failed preflight. Fix the file coverage/schema or redesign the macro thesis; no order path is authorized."
    elif transfer["transfer_pass"]:
        decision = "EXTERNAL_SPOT_D1_TRANSFER_PASS_STAGE64S_GOVERNANCE_REPLICATION_ALLOWED_NO_ORDER"
        status = "EXTERNAL_SPOT_D1_TRANSFER_FASTLANE_PASS_NO_PROMOTION"
        next_step = "Stage64S_GOVERNANCE_REPLICATION_AND_NO_ORDER_DECISION"
        conclusion = "External broker/spot D1 transfer passed the declared gates. The survivor remains no-order; proceed only to governance/replication decision."
    else:
        decision = "EXTERNAL_SPOT_D1_TRANSFER_FAIL_OR_INCONCLUSIVE_REDESIGN_OR_DATA_REVIEW_NO_ORDER"
        status = "EXTERNAL_SPOT_D1_TRANSFER_FASTLANE_FAIL_NO_PROMOTION"
        next_step = "REDESIGN_MACRO_THESIS_OR_REVIEW_EXTERNAL_SPOT_D1_DATA_NO_ORDER"
        conclusion = "External broker/spot D1 transfer did not pass declared gates. Redesign at thesis/data level only; no tuning or order path is authorized."

    summary: Dict[str, Any] = {
        "stage": STAGE,
        "status": status,
        "decision": decision,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_order": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "validation_allowed_for_order_or_promotion": False,
        "validation_run_performed": bool(transfer.get("data_available")),
        "order_path": "NONE",
        "broker_connection": "NONE",
        "generated_utc": generated,
        "root": str(root),
        "inputs": {
            "config": str(cfg_path),
            "stage64q_summary": str(stage64q_summary_path),
            "stage64k_dataset": str(dataset_path),
            "external_spot_d1_raw": str(external_path),
        },
        "stage64q_input_decision": stage64q.get("decision"),
        "target_survivor": cfg["target_survivor"],
        "dataset_info": dataset_info,
        "external_spot_info": external_info,
        "external_spot_preflight": preflight,
        "external_spot_transfer_validation": transfer,
        "executive_conclusion": conclusion,
        "next_allowed_step": next_step,
        "hard_blocks": cfg["hard_blocks"],
        "outputs": {
            "summary_json": str(out / "stage64r_external_spot_d1_intake_transfer_fastlane_summary.json"),
            "report_md": str(out / "stage64r_external_spot_d1_intake_transfer_fastlane_report.md"),
            "template_csv": str(template_path),
            "canonical_external_d1_csv_if_preflight_pass": str(out / "stage64r_external_spot_d1_canonical.csv"),
            "joined_returns_csv_if_run": str(out / "stage64r_external_spot_transfer_joined_returns.csv"),
            "splits_csv_if_run": str(out / "stage64r_external_spot_transfer_splits.csv"),
        },
    }

    # Write gates if present
    gate_rows = transfer.get("overall", {}).get("gates", []) if isinstance(transfer.get("overall"), dict) else []
    if gate_rows:
        write_csv(out / "stage64r_external_spot_transfer_gates.csv", gate_rows)
        summary["outputs"]["gates_csv_if_run"] = str(out / "stage64r_external_spot_transfer_gates.csv")

    write_json(out / "stage64r_external_spot_d1_intake_transfer_fastlane_summary.json", summary)

    lines = [
        "# Stage64R - External Broker/Spot D1 Intake Transfer Fastlane (No Order)",
        "",
        f"Generated UTC: `{generated}`",
        "",
        "## Status",
        "",
        f"- status: `{status}`",
        f"- decision: `{decision}`",
        "- promotion/paper/live: `NO_GO`",
        "- validation_allowed_for_order_or_promotion: `False`",
        "",
        "## Executive conclusion",
        "",
        conclusion,
        "",
        "## External D1 preflight",
        "",
        f"- external_file_found: `{preflight.get('external_file_found')}`",
        f"- external_rows: `{preflight.get('external_rows')}`",
        f"- first: `{preflight.get('external_first_date')}`",
        f"- last: `{preflight.get('external_last_date')}`",
        f"- issue: `{preflight.get('external_issue')}`",
        f"- template: `{template_path}`",
        "",
    ]
    if transfer.get("data_available"):
        ov = transfer["overall"]
        lines += [
            "## External spot transfer headline",
            "",
            "| metric | value |",
            "|---|---:|",
            f"| `joined_return_days` | `{ov.get('joined_return_days')}` |",
            f"| `candidate_active_days` | `{ov.get('candidate_active_days')}` |",
            f"| `candidate_mean_bps` | `{ov.get('candidate_mean_bps')}` |",
            f"| `external_B1_active_days` | `{ov.get('external_B1_active_days')}` |",
            f"| `external_B1_mean_bps` | `{ov.get('external_B1_mean_bps')}` |",
            f"| `mean_excess_vs_external_B1_bps` | `{ov.get('mean_excess_vs_external_B1_bps')}` |",
            f"| `one_sided_p_uncorrected_z_approx` | `{ov.get('one_sided_p_uncorrected_z_approx')}` |",
            f"| `positive_excess_splits_vs_external_B1` | `{ov.get('positive_excess_splits_vs_external_B1')}` |",
            f"| `max_split_share_of_candidate_active_days` | `{ov.get('max_split_share_of_candidate_active_days')}` |",
            f"| `max_year_share_of_candidate_active_days` | `{ov.get('max_year_share_of_candidate_active_days')}` |",
            "",
            "## Transfer gates",
            "",
            "| gate | value | op | threshold | pass |",
            "|---|---:|---|---:|---:|",
        ]
        for g in ov.get("gates", []):
            lines.append(f"| `{g['gate']}` | `{g['value']}` | `{g['op']}` | `{g['threshold']}` | `{g['pass']}` |")
        lines += ["", "## Split diagnostics", "", "| split | cand_days | b1_days | cand_mean | b1_mean | excess | positive |", "|---|---:|---:|---:|---:|---:|---:|"]
        for r in transfer.get("split_rows", []):
            lines.append(f"| `{r['split_id']}` | `{r['candidate_active_days']}` | `{r['benchmark_active_days']}` | `{r['candidate_mean_bps']}` | `{r['benchmark_mean_bps']}` | `{r['excess_vs_external_B1_bps']}` | `{r['positive_excess']}` |")
        lines.append("")
    lines += [
        "## Hard blocks",
        "",
    ]
    lines += [f"- `{b}`" for b in cfg["hard_blocks"]]
    lines += ["", "## Next allowed step", "", f"`{next_step}`", ""]
    (out / "stage64r_external_spot_d1_intake_transfer_fastlane_report.md").write_text("\n".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
