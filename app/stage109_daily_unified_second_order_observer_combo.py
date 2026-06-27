#!/usr/bin/env python3
"""Stage109 Daily Unified Second-Order Observer Combo.

Fixed CSV snapshot parser: supports both wide one-row CSVs and key/value bridge CSVs.
No order, no broker connection, no trading authorization.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_ORDER_SEND_IN_EA",
    "OBSERVER_ONLY_EA",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE109",
    "NO_THRESHOLD_TUNING_FROM_DAILY_UNIFIED_SECOND_ORDER_COMBO",
]

EXPECTED_SCHEMA = "stage108_unified_observer_second_order_v1"
EXPECTED_STAGE = "Stage108_UNIFIED_OBSERVER_SECOND_ORDER_EXPANSION"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)
        f.write("\n")


def write_report(path: Path, summary: Dict[str, Any]) -> None:
    lines = [
        "# Stage109 Daily Unified Second-Order Observer Combo",
        "",
        "## Decision",
        f"- status: `{summary.get('status')}`",
        f"- decision: `{summary.get('decision')}`",
        f"- classification: `{summary.get('classification')}`",
        f"- disposition: `{summary.get('disposition')}`",
        "",
        "## Child stages",
    ]
    for run in summary.get("child_runs", []):
        lines.append(f"- `{run.get('name')}`: status=`{run.get('status')}`, returncode=`{run.get('returncode')}`")
    snap = summary.get("csv_snapshot", {})
    lines += [
        "",
        "## Unified observer CSV snapshot",
        f"- feature_date: `{snap.get('feature_date', '')}`",
        f"- schema_version: `{snap.get('schema_version', '')}`",
        f"- rule_count: `{snap.get('rule_count', '')}`",
        f"- mode: `{snap.get('mode') or snap.get('portfolio_mode') or ''}`",
        f"- any_signal_active: `{snap.get('any_signal_active', '')}`",
        f"- selected_rule_id: `{snap.get('selected_rule_id', '')}`",
        f"- C96_07_active: `{snap.get('C96_07_active') or snap.get('C96_07_signal_active') or ''}`",
        f"- S105_03_active: `{snap.get('S105_03_active') or snap.get('S105_03_signal_active') or ''}`",
        "",
        "## MT5 copy",
    ]
    copy = summary.get("csv_copy", {})
    lines.append(f"- `{copy.get('source')}` -> `{copy.get('destination')}`: status=`{copy.get('status')}`, copied=`{copy.get('copied')}`")
    lines += ["", "## Issues"]
    if summary.get("issues"):
        for issue in summary["issues"]:
            lines.append(f"- `{issue}`")
    else:
        lines.append("- none")
    lines += ["", "## Hard blocks"]
    for hb in summary.get("hard_blocks", []):
        lines.append(f"- `{hb}`")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def default_config(root: Path) -> Dict[str, Any]:
    return {
        "macro_stage": {
            "name": "Stage67D6_DOWNLOAD_FORMAT_AWARE_REBUILD_MACRO",
            "enabled": True,
            "refresh_stage": True,
            "script": "app/stage67d6_download_format_aware_rebuild_macro.py",
            "config": "configs/stage67d6_download_format_aware_rebuild_macro.json",
            "out": "reports/stage67d6_download_format_aware_rebuild_macro",
        },
        "central_bank_stage": {
            "name": "Stage67E_CENTRAL_BANK_CHANGES_MAPPER",
            "enabled": True,
            "refresh_stage": True,
            "script": "app/stage67e_central_bank_changes_mapper.py",
            "config": "configs/stage67e_central_bank_changes_mapper.json",
            "out": "reports/stage67e_central_bank_changes_mapper",
        },
        "cot_stage": {
            "name": "Stage95_COT_OFFICIAL_DATASET_BUILDER_NO_DOWNLOAD",
            "enabled": True,
            "refresh_stage": True,
            "script": "app/stage95_cot_official_dataset_builder.py",
            "config": "configs/stage95_cot_official_dataset_builder.json",
            "out": "reports/stage95_cot_official_dataset_builder",
            "extra_args": ["--no-download"],
        },
        "observer_stage": {
            "name": "Stage108_UNIFIED_OBSERVER_SECOND_ORDER_EXPANSION",
            "enabled": True,
            "refresh_stage": False,
            "script": "app/stage108_unified_observer_second_order_expansion.py",
            "config": "configs/stage108_unified_observer_second_order_expansion.json",
            "out": "reports/stage108_unified_observer_second_order_expansion",
        },
        "bridge_csv": "data/mt5_bridge/unified_observer_signal.csv",
        "mt5_files_path": "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files",
        "required_schema_version": EXPECTED_SCHEMA,
        "required_rule_count": 7,
        "required_short_keys": ["C96_07", "S105_03"],
    }


def run_stage(root: Path, stage_cfg: Dict[str, Any], skip_refresh: bool) -> Dict[str, Any]:
    name = stage_cfg.get("name", "UNKNOWN_STAGE")
    enabled = bool(stage_cfg.get("enabled", True))
    refresh_stage = bool(stage_cfg.get("refresh_stage", False))
    skipped = False
    if not enabled:
        return {"name": name, "enabled": False, "refresh_stage": refresh_stage, "skipped": True, "command": [], "returncode": None, "status": "DISABLED", "stdout_tail": "", "stderr_tail": "", "missing_script": False}
    if skip_refresh and refresh_stage:
        return {"name": name, "enabled": True, "refresh_stage": refresh_stage, "skipped": True, "command": [], "returncode": None, "status": "SKIPPED_REFRESH", "stdout_tail": "", "stderr_tail": "", "missing_script": False}
    script = root / stage_cfg["script"]
    if not script.exists():
        return {"name": name, "enabled": True, "refresh_stage": refresh_stage, "skipped": False, "command": [], "returncode": None, "status": "MISSING_SCRIPT", "stdout_tail": "", "stderr_tail": "", "missing_script": True}
    cmd = [sys.executable, str(script), "--root", str(root), "--config", str(root / stage_cfg["config"]), "--out", str(root / stage_cfg["out"])]
    cmd += list(stage_cfg.get("extra_args", []))
    proc = subprocess.run(cmd, cwd=str(root), text=True, capture_output=True)
    return {
        "name": name,
        "enabled": True,
        "refresh_stage": refresh_stage,
        "skipped": skipped,
        "command": cmd,
        "returncode": proc.returncode,
        "status": "PASS" if proc.returncode == 0 else "FAIL",
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
        "missing_script": False,
    }


def _strip_bom(value: str) -> str:
    return value.lstrip("\ufeff").strip()


def parse_bridge_csv(path: Path) -> Dict[str, str]:
    """Parse bridge CSV robustly.

    Supports:
    1. Wide CSV: header row is keys, next row is values.
    2. Key/value CSV: two columns per row; optional key,value header.
    3. Repeated rows after wide form are ignored after first data row.
    """
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = [[_strip_bom(c) for c in row] for row in csv.reader(f)]
    rows = [row for row in rows if row and any(c != "" for c in row)]
    if not rows:
        return {}

    # Wide format: first row has many known keys, second row has values.
    if len(rows) >= 2 and len(rows[0]) >= 3:
        header = rows[0]
        values = rows[1]
        known = {"schema_version", "stage", "mode", "portfolio_mode", "rule_count", "active_rule_count"}
        if known.intersection(header):
            out: Dict[str, str] = {}
            for i, key in enumerate(header):
                if not key:
                    continue
                out[key] = values[i] if i < len(values) else ""
            return out

    # Key-value format.
    start = 0
    if len(rows[0]) >= 2 and rows[0][0].lower() in {"key", "name", "field"} and rows[0][1].lower() in {"value", "val"}:
        start = 1
    out: Dict[str, str] = {}
    for row in rows[start:]:
        if len(row) >= 2 and row[0]:
            out[row[0]] = row[1]
    return out


def truthy_false(value: Any) -> bool:
    return str(value).strip().lower() in {"false", "0", "no", "none", ""}


def has_short_key(snapshot: Dict[str, str], short_id: str) -> bool:
    prefix = f"{short_id}_"
    return any(k.startswith(prefix) for k in snapshot.keys()) or any(short_id in k for k in snapshot.keys())


def validate_snapshot(snapshot: Dict[str, str], cfg: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    expected_schema = cfg.get("required_schema_version", EXPECTED_SCHEMA)
    if snapshot.get("schema_version") != expected_schema:
        issues.append("UNIFIED_CSV_SCHEMA_NOT_STAGE108_SECOND_ORDER")
    mode = snapshot.get("mode") or snapshot.get("portfolio_mode")
    if mode != "OBSERVER_ONLY_NO_TRADE":
        issues.append("UNIFIED_CSV_MODE_NOT_OBSERVER_ONLY")
    if not truthy_false(snapshot.get("order_authorized", "false")):
        issues.append("UNIFIED_CSV_ORDER_AUTHORIZED_NOT_FALSE")
    if not truthy_false(snapshot.get("broker_connection_allowed", "false")):
        issues.append("UNIFIED_CSV_BROKER_CONNECTION_ALLOWED_NOT_FALSE")
    if not truthy_false(snapshot.get("execution_allowed", "false")):
        issues.append("UNIFIED_CSV_EXECUTION_ALLOWED_NOT_FALSE")
    expected_count = str(cfg.get("required_rule_count", 7))
    if str(snapshot.get("rule_count", "")).strip() != expected_count:
        issues.append("UNIFIED_CSV_RULE_COUNT_NOT_7")
    for short_id in cfg.get("required_short_keys", ["C96_07", "S105_03"]):
        if not has_short_key(snapshot, short_id):
            issues.append(f"UNIFIED_CSV_{short_id}_KEYS_MISSING")
    return issues


def copy_to_mt5(root: Path, cfg: Dict[str, Any], bridge_csv: Path, enabled: bool) -> Dict[str, Any]:
    dest_dir = Path(cfg.get("mt5_files_path", ""))
    dest = dest_dir / bridge_csv.name
    rec = {"source": str(bridge_csv), "destination": str(dest), "copied": False, "status": "SKIPPED", "sha256": sha256_file(bridge_csv), "error": None}
    if not enabled:
        return rec
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bridge_csv, dest)
        rec.update({"copied": True, "status": "COPIED", "sha256": sha256_file(dest), "error": None})
    except Exception as e:  # noqa: BLE001
        rec.update({"copied": False, "status": "COPY_FAILED", "error": str(e)})
    return rec


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    p.add_argument("--config", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--skip-refresh", action="store_true")
    p.add_argument("--copy-to-mt5-files", action="store_true")
    args = p.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    cfg_path = Path(args.config).expanduser()
    cfg = load_json(cfg_path) if cfg_path.exists() else default_config(root)
    # Merge defaults to keep compatibility with older config files.
    dcfg = default_config(root)
    for key, val in dcfg.items():
        cfg.setdefault(key, val)

    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    child_runs: List[Dict[str, Any]] = []
    for key in ["macro_stage", "central_bank_stage", "cot_stage", "observer_stage"]:
        child_runs.append(run_stage(root, cfg[key], args.skip_refresh))

    bridge_csv = root / cfg.get("bridge_csv", "data/mt5_bridge/unified_observer_signal.csv")
    snapshot = parse_bridge_csv(bridge_csv)
    issues = []
    for run in child_runs:
        if run.get("status") in {"FAIL", "MISSING_SCRIPT"}:
            issues.append(f"CHILD_STAGE_{run.get('name')}_{run.get('status')}")
    issues.extend(validate_snapshot(snapshot, cfg))

    csv_copy = copy_to_mt5(root, cfg, bridge_csv, args.copy_to_mt5_files)
    if args.copy_to_mt5_files and csv_copy.get("status") != "COPIED":
        issues.append("MT5_COPY_FAILED")

    status = "STAGE109_COMPLETE_NO_PROMOTION" if not issues else "STAGE109_COMPLETE_WITH_ISSUES_NO_PROMOTION"
    decision = "STAGE109_DAILY_UNIFIED_SECOND_ORDER_COMBO_COMPLETE_OBSERVER_READY_NO_ORDER" if not issues else "STAGE109_DAILY_UNIFIED_SECOND_ORDER_COMBO_ISSUES_NO_ORDER"
    classification = "S109_UNIFIED_SECOND_ORDER_OBSERVER_READY" if not issues else "S109_UNIFIED_SECOND_ORDER_OBSERVER_ISSUES"
    disposition = "DAILY_UNIFIED_SECOND_ORDER_COMBO_OBSERVER_READY_NO_ORDER" if not issues else "DAILY_UNIFIED_SECOND_ORDER_COMBO_OBSERVER_ISSUES_NO_ORDER"

    summary = {
        "stage": "Stage109_DAILY_UNIFIED_SECOND_ORDER_OBSERVER_COMBO",
        "root": str(root),
        "config": str(cfg_path),
        "generated_utc": utc_now(),
        "status": status,
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
        "combo_role": "Local daily operator combo for macro/COT refresh and unified second-order observer-only MT5 bridge generation.",
        "skip_refresh": args.skip_refresh,
        "child_runs": child_runs,
        "csv_snapshot": {"path": str(bridge_csv), "exists": bridge_csv.exists(), "sha256": sha256_file(bridge_csv), **snapshot},
        "csv_copy": csv_copy,
        "issues": issues,
        "hard_blocks": HARD_BLOCKS,
        "operator_instructions": [
            "Stage109 cannot authorize orders.",
            "Use --skip-refresh when source files have not changed and only the unified second-order observer CSV must be rebuilt.",
            "Use --copy-to-mt5-files only after confirming the correct MQL5/Files path.",
            "EA files are not daily artifacts; only unified_observer_signal.csv is refreshed daily unless EA logic changes.",
        ],
        "outputs": {
            "summary_json": str(out_dir / "stage109_daily_unified_second_order_observer_combo_summary.json"),
            "report_md": str(out_dir / "stage109_daily_unified_second_order_observer_combo_report.md"),
            "unified_csv": str(bridge_csv),
        },
    }
    write_json(out_dir / "stage109_daily_unified_second_order_observer_combo_summary.json", summary)
    write_report(out_dir / "stage109_daily_unified_second_order_observer_combo_report.md", summary)

    print(json.dumps({
        "stage": summary["stage"],
        "status": status,
        "decision": decision,
        "issues": issues,
        "summary_json": summary["outputs"]["summary_json"],
        "report_md": summary["outputs"]["report_md"],
    }, ensure_ascii=False, indent=2))
    return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
