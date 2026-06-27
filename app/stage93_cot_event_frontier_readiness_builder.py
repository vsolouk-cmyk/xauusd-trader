#!/usr/bin/env python3
"""Stage93 COT/Event frontier readiness builder.

This stage does not discover or promote a trading rule. It prepares the next
credible data frontiers after macro-only and intraday/session residual searches
failed to produce a shortlist.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

STAGE = "Stage93_COT_EVENT_FRONTIER_READINESS_BUILDER"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path, limit_bytes: Optional[int] = None) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        if limit_bytes is None:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        else:
            h.update(f.read(limit_bytes))
    return h.hexdigest()


def read_json(path: Path) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    if not path.exists():
        return False, None, "missing"
    try:
        return True, json.loads(path.read_text(encoding="utf-8")), None
    except Exception as exc:  # noqa: BLE001
        return True, None, f"read_error:{type(exc).__name__}:{exc}"


def normalize_col(c: str) -> str:
    c = str(c).strip().strip("\ufeff")
    c = c.strip("<>")
    c = c.lower()
    c = re.sub(r"[^a-z0-9]+", "_", c).strip("_")
    return c


def sniff_delimiter(sample: str) -> str:
    counts = {",": sample.count(","), "\t": sample.count("\t"), ";": sample.count(";"), "|": sample.count("|")}
    return max(counts, key=counts.get) if max(counts.values()) > 0 else ","


def quick_csv_profile(path: Path, max_rows: int = 200000) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "read_ok": False,
        "error": None,
        "size_bytes": None,
        "sha256_head": None,
        "delimiter": None,
        "header": [],
        "normalized_header": [],
        "row_count_sampled_or_exact": 0,
        "row_count_exact": True,
    }
    try:
        out["size_bytes"] = path.stat().st_size
        out["sha256_head"] = sha256_file(path, limit_bytes=1024 * 1024)
        sample = path.read_text(encoding="utf-8", errors="replace")[:8192]
        delim = sniff_delimiter(sample)
        out["delimiter"] = "tab" if delim == "\t" else delim
        with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.reader(f, delimiter=delim)
            try:
                header = next(reader)
            except StopIteration:
                header = []
            out["header"] = header
            n = 0
            for n, _ in enumerate(reader, start=1):
                if n >= max_rows:
                    out["row_count_exact"] = False
                    break
            out["row_count_sampled_or_exact"] = n
        out["normalized_header"] = [normalize_col(c) for c in out["header"]]
        out["read_ok"] = True
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}:{exc}"
    return out


def expand_scan_root(root: Path, scan_root: str) -> Path:
    p = Path(os.path.expanduser(scan_root))
    if not p.is_absolute():
        p = root / p
    return p


def iter_candidate_files(root: Path, scan_roots: Sequence[str], keywords: Sequence[str]) -> Iterable[Path]:
    seen = set()
    lowered = [k.lower() for k in keywords]
    for sr in scan_roots:
        base = expand_scan_root(root, sr)
        if not base.exists():
            continue
        if base.is_file():
            candidates = [base]
        else:
            candidates = []
            for ext in ("*.csv", "*.txt", "*.tsv", "*.json"):
                candidates.extend(base.rglob(ext))
        for p in candidates:
            key = str(p.resolve()) if p.exists() else str(p)
            if key in seen:
                continue
            seen.add(key)
            name = p.name.lower()
            if any(k in name for k in lowered):
                yield p


def coverage(required: Sequence[str], header: Sequence[str]) -> Tuple[int, List[str]]:
    hs = set(header)
    missing = [c for c in required if normalize_col(c) not in hs]
    return len(required) - len(missing), missing


def classify_cot(profile: Dict[str, Any], required: Sequence[str]) -> Dict[str, Any]:
    header = profile.get("normalized_header", [])
    score, missing = coverage(required, header)
    hset = set(header)
    heuristic = 0
    for token in ["managed_money", "m_money", "noncommercial", "open_interest", "report_date", "market_and_exchange_names"]:
        if any(token in h for h in hset):
            heuristic += 1
    ready = profile.get("read_ok") and score == len(required)
    return {
        "frontier": "COT_POSITIONING",
        "schema_score": score,
        "schema_required": len(required),
        "missing_required_columns": "|".join(missing),
        "heuristic_score": heuristic,
        "ready_normalized_schema": bool(ready),
    }


def classify_event(profile: Dict[str, Any], required: Sequence[str]) -> Dict[str, Any]:
    header = profile.get("normalized_header", [])
    score, missing = coverage(required, header)
    hset = set(header)
    heuristic = 0
    for token in ["actual", "forecast", "consensus", "previous", "surprise", "event", "datetime", "importance"]:
        if any(token in h for h in hset):
            heuristic += 1
    ready = profile.get("read_ok") and score == len(required)
    return {
        "frontier": "EVENT_SURPRISE",
        "schema_score": score,
        "schema_required": len(required),
        "missing_required_columns": "|".join(missing),
        "heuristic_score": heuristic,
        "ready_normalized_schema": bool(ready),
    }


def write_csv(path: Path, rows: Sequence[Dict[str, Any]], fieldnames: Optional[Sequence[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        keys: List[str] = []
        for r in rows:
            for k in r.keys():
                if k not in keys:
                    keys.append(k)
        fieldnames = keys
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(fieldnames))
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in fieldnames})


def write_template_csv(path: Path, columns: Sequence[str], sample_row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(columns))
        writer.writeheader()
        writer.writerow({c: sample_row.get(c, "") for c in columns})


def build_templates(root: Path, cfg: Dict[str, Any]) -> Dict[str, str]:
    out_dir = expand_scan_root(root, cfg.get("output_templates_dir", "data/frontier_templates"))
    cot_cols = [
        "report_date_utc", "available_after_utc", "market", "contract", "open_interest",
        "managed_money_long", "managed_money_short", "managed_money_spreading",
        "producer_merchant_long", "producer_merchant_short", "swap_dealer_long", "swap_dealer_short",
        "source_file", "source_url", "vintage_id"
    ]
    cot_sample = {
        "report_date_utc": "2026-06-23", "available_after_utc": "2026-06-26T19:30:00Z",
        "market": "GOLD", "contract": "COMEX_GOLD", "open_interest": "",
        "managed_money_long": "", "managed_money_short": "", "managed_money_spreading": "",
        "source_file": "", "source_url": "", "vintage_id": "as_downloaded_no_revisions"
    }
    event_cols = [
        "event_datetime_utc", "available_after_utc", "country", "event_type", "event_name", "importance",
        "actual", "consensus", "previous", "revised_previous", "unit", "surprise", "surprise_pct",
        "surprise_z_2y", "direction_for_gold", "source_file", "source_url", "vintage_id"
    ]
    event_sample = {
        "event_datetime_utc": "2026-06-26T12:30:00Z", "available_after_utc": "2026-06-26T12:31:00Z",
        "country": "US", "event_type": "PCE|CPI|NFP|FOMC|ISM|RetailSales", "event_name": "",
        "importance": "high", "actual": "", "consensus": "", "previous": "", "unit": "", "surprise": "",
        "surprise_z_2y": "", "direction_for_gold": "risk_off|usd_down|yield_down|ambiguous",
        "source_file": "", "source_url": "", "vintage_id": "as_downloaded_no_revisions"
    }
    cot_path = out_dir / "stage93_cot_positioning_normalized_template.csv"
    event_path = out_dir / "stage93_event_surprise_normalized_template.csv"
    write_template_csv(cot_path, cot_cols, cot_sample)
    write_template_csv(event_path, event_cols, event_sample)
    return {"cot_template": str(cot_path), "event_surprise_template": str(event_path)}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    cfg_path = Path(args.config).expanduser()
    if not cfg_path.is_absolute():
        cfg_path = root / cfg_path
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    out_dir = Path(args.out).expanduser()
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    references = []
    for name, rel in cfg.get("reference_reports", {}).items():
        p = root / rel
        exists, data, err = read_json(p)
        references.append({
            "name": name,
            "path": str(p),
            "exists": exists,
            "read_ok": data is not None,
            "decision": data.get("decision") if isinstance(data, dict) else None,
            "disposition": data.get("disposition") if isinstance(data, dict) else None,
            "error": err,
        })

    scan_roots = cfg.get("scan_roots", [])
    cot_files = list(iter_candidate_files(root, scan_roots, cfg.get("cot_filename_keywords", [])))
    event_files = list(iter_candidate_files(root, scan_roots, cfg.get("event_filename_keywords", [])))

    cot_rows: List[Dict[str, Any]] = []
    for p in cot_files:
        prof = quick_csv_profile(p) if p.suffix.lower() in {".csv", ".txt", ".tsv"} else {
            "path": str(p), "exists": p.exists(), "read_ok": False, "error": "non_csv_json_or_other", "size_bytes": p.stat().st_size if p.exists() else None,
            "sha256_head": sha256_file(p, limit_bytes=1024 * 1024) if p.exists() else None, "delimiter": "", "header": [], "normalized_header": [], "row_count_sampled_or_exact": 0,
            "row_count_exact": False,
        }
        cot_rows.append({**prof, **classify_cot(prof, cfg["required_columns"]["cot_normalized"])})

    event_rows: List[Dict[str, Any]] = []
    for p in event_files:
        prof = quick_csv_profile(p) if p.suffix.lower() in {".csv", ".txt", ".tsv"} else {
            "path": str(p), "exists": p.exists(), "read_ok": False, "error": "non_csv_json_or_other", "size_bytes": p.stat().st_size if p.exists() else None,
            "sha256_head": sha256_file(p, limit_bytes=1024 * 1024) if p.exists() else None, "delimiter": "", "header": [], "normalized_header": [], "row_count_sampled_or_exact": 0,
            "row_count_exact": False,
        }
        event_rows.append({**prof, **classify_event(prof, cfg["required_columns"]["event_surprise_normalized"])})

    min_rows = cfg.get("minimum_ready_rows", {})
    cot_ready_files = [r for r in cot_rows if r.get("ready_normalized_schema") and int(r.get("row_count_sampled_or_exact") or 0) >= int(min_rows.get("cot", 300))]
    event_ready_files = [r for r in event_rows if r.get("ready_normalized_schema") and int(r.get("row_count_sampled_or_exact") or 0) >= int(min_rows.get("event_surprise", 500))]

    template_paths = build_templates(root, cfg)

    frontier_rows = [
        {
            "frontier": "COT_POSITIONING",
            "file_count": len(cot_rows),
            "ready_file_count": len(cot_ready_files),
            "status": "READY" if cot_ready_files else "NOT_READY",
            "next_stage": "Stage94_COT_POSITIONING_THESIS_DISCOVERY" if cot_ready_files else "BUILD_COT_NORMALIZED_DATASET_FIRST",
            "why": "COT adds futures positioning state unavailable in current macro and intraday/session portfolios.",
        },
        {
            "frontier": "EVENT_SURPRISE",
            "file_count": len(event_rows),
            "ready_file_count": len(event_ready_files),
            "status": "READY" if event_ready_files else "NOT_READY",
            "next_stage": "Stage94_EVENT_SURPRISE_THESIS_DISCOVERY" if event_ready_files else "BUILD_EVENT_SURPRISE_NORMALIZED_DATASET_FIRST",
            "why": "Event surprise captures dated repricing not represented by smoothed daily macro states.",
        },
    ]

    if cot_ready_files:
        decision = "STAGE93_COT_FRONTIER_READY_FOR_STAGE94_NO_ORDER"
        classification = "S93_COT_READY"
        disposition = "COT_FRONTIER_READY_FOR_STAGE94"
        selected_next = "Stage94_COT_POSITIONING_THESIS_DISCOVERY"
    elif event_ready_files:
        decision = "STAGE93_EVENT_SURPRISE_FRONTIER_READY_FOR_STAGE94_NO_ORDER"
        classification = "S93_EVENT_SURPRISE_READY"
        disposition = "EVENT_SURPRISE_FRONTIER_READY_FOR_STAGE94"
        selected_next = "Stage94_EVENT_SURPRISE_THESIS_DISCOVERY"
    else:
        decision = "STAGE93_EXTERNAL_FRONTIER_DATA_NOT_READY_NO_ORDER"
        classification = "S93_DATA_FRONTIER_NOT_READY"
        disposition = "BUILD_COT_OR_EVENT_SURPRISE_DATASET_BEFORE_STAGE94"
        selected_next = "DATA_BUILD_REQUIRED_BEFORE_DISCOVERY"

    requirements = [
        {"frontier": "COT_POSITIONING", "requirement": "normalized weekly COT gold/COMEX rows", "minimum": min_rows.get("cot", 300), "template": template_paths["cot_template"], "lookahead_rule": "available_after_utc must be after public release; no revised future values in past rows"},
        {"frontier": "COT_POSITIONING", "requirement": "managed money long/short/open interest fields", "minimum": "all rows", "template": template_paths["cot_template"], "lookahead_rule": "derive z-scores only from prior rows within each historical-as-of run"},
        {"frontier": "EVENT_SURPRISE", "requirement": "timestamped high-impact US events with actual/consensus/previous/surprise", "minimum": min_rows.get("event_surprise", 500), "template": template_paths["event_surprise_template"], "lookahead_rule": "available_after_utc must be event release time or later"},
        {"frontier": "EVENT_SURPRISE", "requirement": "event_type standardized to CPI/NFP/FOMC/PCE/ISM/RetailSales/etc.", "minimum": "high-impact history", "template": template_paths["event_surprise_template"], "lookahead_rule": "surprise_z must be computed using historical distribution available as-of"},
    ]

    queue = [
        {"priority": 1, "stage": "Stage94_COT_POSITIONING_THESIS_DISCOVERY", "frontier": "COT_POSITIONING", "status": "READY" if cot_ready_files else "BLOCKED_DATA_REQUIRED", "thesis_family": "COT managed-money exhaustion / short-covering / crowded-long risk", "rationale": "Positioning is orthogonal to price/macro state when properly lagged."},
        {"priority": 2, "stage": "Stage94_EVENT_SURPRISE_THESIS_DISCOVERY", "frontier": "EVENT_SURPRISE", "status": "READY" if event_ready_files else "BLOCKED_DATA_REQUIRED", "thesis_family": "post-event gold repricing after CPI/NFP/FOMC surprise", "rationale": "Event-specific surprise may capture impulse response not visible in daily macro panel."},
    ]

    write_csv(out_dir / "stage93_cot_file_inventory.csv", cot_rows)
    write_csv(out_dir / "stage93_event_file_inventory.csv", event_rows)
    write_csv(out_dir / "stage93_frontier_readiness.csv", frontier_rows)
    write_csv(out_dir / "stage93_data_requirements.csv", requirements)
    write_csv(out_dir / "stage93_thesis_queue.csv", queue)

    report_lines = [
        "# Stage93 COT/Event Frontier Readiness Builder",
        "",
        "## Decision",
        f"- status: `STAGE93_COMPLETE_NO_PROMOTION`",
        f"- decision: `{decision}`",
        f"- classification: `{classification}`",
        f"- disposition: `{disposition}`",
        "",
        "## Frontier readiness",
    ]
    for r in frontier_rows:
        report_lines.append(f"- `{r['frontier']}`: status=`{r['status']}` files=`{r['file_count']}` ready_files=`{r['ready_file_count']}` next=`{r['next_stage']}`")
    report_lines += ["", "## Templates", f"- COT: `{template_paths['cot_template']}`", f"- Event surprise: `{template_paths['event_surprise_template']}`", "", "## Hard blocks"]
    for hb in cfg.get("hard_blocks", []):
        report_lines.append(f"- `{hb}`")
    (out_dir / "stage93_cot_event_frontier_readiness_builder_report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    summary = {
        "stage": STAGE,
        "root": str(root),
        "config": str(cfg_path),
        "generated_utc": utc_now(),
        "status": "STAGE93_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
        "principle": cfg.get("principle"),
        "references": references,
        "cot_file_count": len(cot_rows),
        "cot_ready_file_count": len(cot_ready_files),
        "event_file_count": len(event_rows),
        "event_ready_file_count": len(event_ready_files),
        "frontier_readiness": frontier_rows,
        "selected_next_stage": selected_next,
        "template_paths": template_paths,
        "hard_blocks": cfg.get("hard_blocks", []),
        "outputs": {
            "summary_json": str(out_dir / "stage93_cot_event_frontier_readiness_builder_summary.json"),
            "report_md": str(out_dir / "stage93_cot_event_frontier_readiness_builder_report.md"),
            "frontier_readiness_csv": str(out_dir / "stage93_frontier_readiness.csv"),
            "cot_file_inventory_csv": str(out_dir / "stage93_cot_file_inventory.csv"),
            "event_file_inventory_csv": str(out_dir / "stage93_event_file_inventory.csv"),
            "data_requirements_csv": str(out_dir / "stage93_data_requirements.csv"),
            "thesis_queue_csv": str(out_dir / "stage93_thesis_queue.csv"),
        },
    }
    (out_dir / "stage93_cot_event_frontier_readiness_builder_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
