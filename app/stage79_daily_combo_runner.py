#!/usr/bin/env python3
"""Stage79 daily combo runner for XAUUSD K06/portfolio observer workflow.

Runs the existing local refresh/bridge stages in sequence and optionally copies
MT5 observer CSV files to the user's MQL5/Files folder. This stage is strictly
observer-only and cannot authorize orders.
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
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

STAGE = "Stage79_DAILY_COMBO_RUNNER"
DEFAULT_HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_ORDER_SEND_IN_EA",
    "OBSERVER_ONLY_EA",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE79",
    "NO_THRESHOLD_TUNING_FROM_DAILY_COMBO",
]


@dataclass
class ChildRun:
    name: str
    enabled: bool
    command: List[str]
    returncode: Optional[int]
    status: str
    stdout_tail: str = ""
    stderr_tail: str = ""
    missing_script: bool = False


@dataclass
class CsvCopy:
    source: str
    destination: Optional[str]
    copied: bool
    status: str
    sha256: Optional[str] = None
    error: Optional[str] = None


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def tail(text: str, max_chars: int = 4000) -> str:
    text = text or ""
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def run_child(root: Path, name: str, script: str, config: str, out_dir: str, enabled: bool, timeout_seconds: int, extra_args: Sequence[str] = ()) -> ChildRun:
    cmd = [
        sys.executable,
        str(root / script),
        "--root",
        str(root),
        "--config",
        str(root / config),
        "--out",
        str(root / out_dir),
    ]
    cmd.extend(extra_args)
    if not enabled:
        return ChildRun(name=name, enabled=False, command=cmd, returncode=None, status="SKIPPED_DISABLED")
    if not (root / script).exists():
        return ChildRun(name=name, enabled=True, command=cmd, returncode=None, status="FAIL_MISSING_SCRIPT", missing_script=True)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(root),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
        )
        status = "PASS" if proc.returncode == 0 else "FAIL_RETURN_CODE"
        return ChildRun(name=name, enabled=True, command=cmd, returncode=proc.returncode, status=status, stdout_tail=tail(proc.stdout), stderr_tail=tail(proc.stderr))
    except subprocess.TimeoutExpired as exc:
        return ChildRun(name=name, enabled=True, command=cmd, returncode=None, status="FAIL_TIMEOUT", stdout_tail=tail(exc.stdout or ""), stderr_tail=tail(exc.stderr or ""))
    except Exception as exc:  # pragma: no cover - defensive
        return ChildRun(name=name, enabled=True, command=cmd, returncode=None, status="FAIL_EXCEPTION", stderr_tail=str(exc))


def parse_key_value_csv(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    data: Dict[str, str] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if not rows:
        return {}
    header = [c.strip().lower() for c in rows[0]]
    # key,value schema
    if len(header) >= 2 and header[0] == "key" and header[1] == "value":
        for row in rows[1:]:
            if len(row) >= 2:
                data[row[0].strip()] = row[1].strip()
        return data
    # wide schema fallback
    if len(rows) >= 2:
        for k, v in zip(rows[0], rows[1]):
            data[k.strip()] = v.strip()
    return data


def copy_csv_if_requested(root: Path, source_rel: str, mt5_files_dir: str) -> CsvCopy:
    src = root / source_rel
    if not src.exists():
        return CsvCopy(source=str(src), destination=None, copied=False, status="FAIL_SOURCE_MISSING")
    digest = sha256_file(src)
    if not mt5_files_dir:
        return CsvCopy(source=str(src), destination=None, copied=False, status="SKIPPED_NO_MT5_FILES_DIR", sha256=digest)
    dst_dir = Path(os.path.expanduser(mt5_files_dir)).resolve()
    try:
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / src.name
        shutil.copy2(src, dst)
        return CsvCopy(source=str(src), destination=str(dst), copied=True, status="COPIED", sha256=digest)
    except Exception as exc:
        return CsvCopy(source=str(src), destination=str(dst_dir / src.name), copied=False, status="FAIL_COPY", sha256=digest, error=str(exc))


def load_config(path: Path) -> Dict[str, Any]:
    cfg = read_json(path)
    cfg.setdefault("timeout_seconds", 180)
    cfg.setdefault("run_stage67d6", True)
    cfg.setdefault("run_stage67e", True)
    cfg.setdefault("run_stage76e", True)
    cfg.setdefault("run_stage78", True)
    cfg.setdefault("mt5_files_dir", "")
    cfg.setdefault("copy_to_mt5_files", False)
    return cfg


def build_report(summary: Dict[str, Any]) -> str:
    lines = [
        "# Stage79 Daily Combo Runner",
        "",
        "## Decision",
        f"- status: `{summary['status']}`",
        f"- decision: `{summary['decision']}`",
        f"- classification: `{summary['classification']}`",
        f"- disposition: `{summary['disposition']}`",
        "",
        "## Child stages",
    ]
    for cr in summary["child_runs"]:
        lines.append(f"- `{cr['name']}`: status=`{cr['status']}`, returncode=`{cr['returncode']}`")
    lines.extend(["", "## Observer CSV snapshots"])
    for name, snap in summary["csv_snapshots"].items():
        lines.append(f"### `{name}`")
        if not snap.get("exists"):
            lines.append("- exists: `False`")
            continue
        for key in ["feature_date", "latest_feature_date_utc", "mode", "signal_active", "any_signal_active", "selected_rule", "selected_rule_id", "thesis", "thesis_id"]:
            if key in snap:
                lines.append(f"- {key}: `{snap[key]}`")
    lines.extend(["", "## MT5 copy"])
    for cp in summary["csv_copies"]:
        lines.append(f"- `{cp['source']}` -> `{cp.get('destination')}`: status=`{cp['status']}`, copied=`{cp['copied']}`")
    lines.extend(["", "## Issues"])
    if summary["issues"]:
        lines.extend([f"- {x}" for x in summary["issues"]])
    else:
        lines.append("- none")
    lines.extend(["", "## Hard blocks"])
    lines.extend([f"- `{x}`" for x in summary["hard_blocks"]])
    lines.append("")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run Stage79 daily combo observer pipeline.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--skip-refresh", action="store_true", help="Skip Stage67D6/Stage67E and only rebuild observer bridges.")
    parser.add_argument("--copy-to-mt5-files", action="store_true", help="Copy generated CSV files to mt5_files_dir from config.")
    parser.add_argument("--mt5-files-dir", default="", help="Override MT5 MQL5/Files directory for CSV copy.")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    cfg = load_config(Path(args.config))
    timeout = int(cfg.get("timeout_seconds", 180))
    mt5_files_dir = args.mt5_files_dir or cfg.get("mt5_files_dir", "")
    copy_to_mt5 = bool(args.copy_to_mt5_files or cfg.get("copy_to_mt5_files", False))

    run_refresh = not args.skip_refresh
    child_runs: List[ChildRun] = []
    child_runs.append(run_child(
        root,
        "Stage67D6_DOWNLOAD_FORMAT_AWARE_REBUILD_MACRO",
        "app/stage67d6_download_format_aware_rebuild_macro.py",
        "configs/stage67d6_download_format_aware_rebuild_macro.json",
        "reports/stage67d6_download_format_aware_rebuild_macro",
        enabled=bool(cfg.get("run_stage67d6", True) and run_refresh),
        timeout_seconds=timeout,
    ))
    child_runs.append(run_child(
        root,
        "Stage67E_CENTRAL_BANK_CHANGES_MAPPER",
        "app/stage67e_central_bank_changes_mapper.py",
        "configs/stage67e_central_bank_changes_mapper.json",
        "reports/stage67e_central_bank_changes_mapper",
        enabled=bool(cfg.get("run_stage67e", True) and run_refresh),
        timeout_seconds=timeout,
        extra_args=("--run-readiness", "--run-frequency", "--timeout-seconds", str(timeout)),
    ))
    child_runs.append(run_child(
        root,
        "Stage76E_K06_OBSERVER_MODE_FIX",
        "app/stage76e_k06_observer_mode_fix.py",
        "configs/stage76e_k06_observer_mode_fix.json",
        "reports/stage76e_k06_observer_mode_fix",
        enabled=bool(cfg.get("run_stage76e", True)),
        timeout_seconds=timeout,
    ))
    child_runs.append(run_child(
        root,
        "Stage78_PORTFOLIO_OBSERVER_BRIDGE",
        "app/stage78_portfolio_observer_bridge.py",
        "configs/stage78_portfolio_observer_bridge.json",
        "reports/stage78_portfolio_observer_bridge",
        enabled=bool(cfg.get("run_stage78", True)),
        timeout_seconds=timeout,
    ))

    issues: List[str] = []
    for cr in child_runs:
        if cr.enabled and cr.status != "PASS":
            issues.append(f"CHILD_STAGE_{cr.name}_{cr.status}")

    csv_sources = {
        "k06_observer_signal": "data/mt5_bridge/k06_observer_signal.csv",
        "portfolio_observer_signal": "data/mt5_bridge/portfolio_observer_signal.csv",
    }
    csv_snapshots: Dict[str, Any] = {}
    for name, rel in csv_sources.items():
        path = root / rel
        parsed = parse_key_value_csv(path)
        snap: Dict[str, Any] = {"path": str(path), "exists": path.exists()}
        if path.exists():
            snap["sha256"] = sha256_file(path)
            snap.update(parsed)
        csv_snapshots[name] = snap
        if not path.exists():
            issues.append(f"CSV_MISSING:{name}")

    copies: List[CsvCopy] = []
    if copy_to_mt5:
        for rel in csv_sources.values():
            copies.append(copy_csv_if_requested(root, rel, mt5_files_dir))
            if copies[-1].status.startswith("FAIL"):
                issues.append(f"MT5_COPY_{Path(rel).name}_{copies[-1].status}")
    else:
        for rel in csv_sources.values():
            copies.append(copy_csv_if_requested(root, rel, ""))

    decision = "STAGE79_DAILY_COMBO_COMPLETE_OBSERVER_READY_NO_ORDER" if not issues else "STAGE79_DAILY_COMBO_COMPLETE_WITH_ISSUES_NO_ORDER"
    classification = "S79_OBSERVER_READY" if not issues else "S79_OBSERVER_ISSUES"
    disposition = "DAILY_COMBO_OBSERVER_READY_NO_ORDER" if not issues else "DAILY_COMBO_REVIEW_ISSUES_NO_ORDER"

    summary = {
        "stage": STAGE,
        "root": str(root),
        "config": str(Path(args.config).resolve()),
        "generated_utc": utc_now(),
        "status": "STAGE79_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
        "combo_role": "Local daily operator combo for macro refresh and observer-only MT5 bridge generation.",
        "child_runs": [asdict(cr) for cr in child_runs],
        "csv_snapshots": csv_snapshots,
        "csv_copies": [asdict(cp) for cp in copies],
        "issues": issues,
        "hard_blocks": DEFAULT_HARD_BLOCKS,
        "operator_instructions": [
            "Stage79 cannot authorize orders.",
            "Use --skip-refresh when source files have not changed and only observer CSVs must be rebuilt.",
            "Use --copy-to-mt5-files with mt5_files_dir only after confirming the correct MQL5/Files path.",
            "EA files are not daily artifacts; only observer CSV files are refreshed daily unless EA logic changes.",
        ],
        "outputs": {
            "summary_json": str(out_dir / "stage79_daily_combo_runner_summary.json"),
            "report_md": str(out_dir / "stage79_daily_combo_runner_report.md"),
        },
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "stage79_daily_combo_runner_summary.json", summary)
    (out_dir / "stage79_daily_combo_runner_report.md").write_text(build_report(summary), encoding="utf-8")
    return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
