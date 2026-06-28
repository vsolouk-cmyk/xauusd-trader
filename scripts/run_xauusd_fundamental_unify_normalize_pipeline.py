#!/usr/bin/env python3
"""Run XAUUSD fundamental/event data pipeline with visible progress.

Pipeline:
1) optional official-data download batch
2) Stage113 unifier
3) Stage114 normalizer
4) Stage114B classification hotfix
5) Stage115 feature-grade builder
6) Stage116 source-specific validator

No order / MT5 / EA / broker action is performed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence

STAGE = "XAUUSD_FUNDAMENTAL_UNIFY_NORMALIZE_PIPELINE_STAGE116C_ENVFILE_CENSUS_PATCH"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def console(message: str, *, quiet: bool = False) -> None:
    if not quiet:
        print(message, flush=True)


def require_file(root: Path, rel: str) -> None:
    path = root / rel
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")


def write_jsonl(path: Path, row: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def run_cmd(cmd: List[str], cwd: Path, *, step_no: int, total_steps: int, name: str, log_jsonl: Path, quiet: bool, continue_on_error: bool = False) -> Dict[str, object]:
    started = time.time()
    console(f"[{step_no:02d}/{total_steps:02d} START] {name} | {utc_now()}", quiet=quiet)
    console(f"    cmd: {' '.join(cmd)}", quiet=quiet)
    write_jsonl(log_jsonl, {"event": "step_start", "step_no": step_no, "total_steps": total_steps, "name": name, "cmd": cmd, "utc": utc_now()})
    cp = subprocess.run(cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    elapsed = round(time.time() - started, 2)
    result = {
        "name": name,
        "cmd": " ".join(cmd),
        "returncode": cp.returncode,
        "status": "OK" if cp.returncode == 0 else "FAILED",
        "elapsed_sec": elapsed,
        "stdout_tail": cp.stdout[-3000:],
        "stderr_tail": cp.stderr[-3000:],
    }
    write_jsonl(log_jsonl, {"event": "step_done", "step_no": step_no, "name": name, **result, "utc": utc_now()})
    console(f"[{step_no:02d}/{total_steps:02d} DONE ] {name} | status={result['status']} | elapsed={elapsed}s", quiet=quiet)
    if cp.returncode != 0:
        if cp.stderr:
            console(f"    stderr_tail:\n{cp.stderr[-1200:]}", quiet=quiet)
        if not continue_on_error:
            raise RuntimeError(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--root", default="/Users/vahid/Desktop/xauusd-trader")
    ap.add_argument("--inbox", default=str(Path.home() / "Downloads" / "xauusd_fundamental_event_inbox"))
    ap.add_argument("--download-first", action="store_true")
    ap.add_argument("--include-cot-xls", action="store_true")
    ap.add_argument("--skip-wgc-direct", action="store_true")
    ap.add_argument("--env-file", action="append", default=[], help="Pass local API-key env file(s) to the download runner")
    ap.add_argument("--continue-on-error", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    root = Path(args.root)
    inbox = Path(args.inbox).expanduser()
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_dir = root / "reports" / "xauusd_fundamental_unify_normalize_pipeline"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_jsonl = log_dir / f"xauusd_fundamental_unify_normalize_pipeline_{run_id}.jsonl"
    summary_path = log_dir / "xauusd_fundamental_unify_normalize_pipeline_summary.json"

    commands: List[tuple[str, List[str]]] = []
    if args.download_first:
        require_file(root, "scripts/download_xauusd_official_data_batch.py")
        download_cmd = [sys.executable, "scripts/download_xauusd_official_data_batch.py", "--inbox", str(inbox)]
        if args.include_cot_xls:
            download_cmd.append("--include-cot-xls")
        if args.skip_wgc_direct:
            download_cmd.append("--skip-wgc-direct")
        for env_file in args.env_file:
            download_cmd.extend(["--env-file", env_file])
        commands.append(("Official data download batch", download_cmd))

    ordered = [
        ("Stage113 unifier", [sys.executable, "app/stage113_fundamental_event_inbox_unifier.py", "--root", str(root)]),
        ("Stage114 official normalizer", [sys.executable, "app/stage114_official_event_and_fundamental_normalizer.py", "--root", str(root), "--manifest", "data/fundamental_event_inbox/manifests/stage113_fundamental_event_file_manifest.csv"]),
        ("Stage114B classification hotfix", [sys.executable, "app/stage114b_classification_and_macro_event_hotfix.py", "--root", str(root), "--manifest", "data/fundamental_event_inbox/manifests/stage113_fundamental_event_file_manifest.csv"]),
        ("Stage115 feature-grade builder", [sys.executable, "app/stage115_feature_grade_macro_fundamental_builder.py", "--root", str(root)]),
        ("Stage116 WGC/SPDR/DXY validator", [sys.executable, "app/stage116_source_specific_wgc_spdr_dxy_validator.py", "--root", str(root), "--inbox", str(inbox)]),
    ]
    for name, cmd in ordered:
        if len(cmd) >= 2 and cmd[1].startswith("app/"):
            require_file(root, cmd[1])
        commands.append((name, cmd))

    console(f"{STAGE} | started={utc_now()} | root={root} | inbox={inbox}", quiet=args.quiet)
    console(f"Log: {log_jsonl}", quiet=args.quiet)
    started = time.time()
    steps: List[Dict[str, object]] = []
    total = len(commands)
    for step_no, (name, cmd) in enumerate(commands, start=1):
        steps.append(run_cmd(cmd, root, step_no=step_no, total_steps=total, name=name, log_jsonl=log_jsonl, quiet=args.quiet, continue_on_error=args.continue_on_error))

    status = "PIPELINE_COMPLETE" if all(step["status"] == "OK" for step in steps) else "PIPELINE_COMPLETE_WITH_ERRORS"
    summary = {
        "stage": STAGE,
        "generated_utc": utc_now(),
        "root": str(root),
        "inbox": str(inbox),
        "download_first": args.download_first,
        "status": status,
        "elapsed_sec": round(time.time() - started, 2),
        "hard_blocks": ["NO_ORDER", "NO_MT5", "NO_EA", "NO_BROKER"],
        "steps": steps,
        "log_jsonl": str(log_jsonl),
        "summary_json": str(summary_path),
        "expected_latest_summaries": [
            "reports/stage113_fundamental_event_inbox_unifier/stage113_fundamental_event_inbox_unifier_summary.json",
            "reports/stage114_official_event_and_fundamental_normalizer/stage114_official_event_and_fundamental_normalizer_summary.json",
            "reports/stage114b_classification_and_macro_event_hotfix/stage114b_classification_and_macro_event_hotfix_summary.json",
            "reports/stage115_feature_grade_macro_fundamental_builder/stage115_feature_grade_macro_fundamental_builder_summary.json",
            "reports/stage116_source_specific_wgc_spdr_dxy_validator/stage116_source_specific_wgc_spdr_dxy_validator_summary.json",
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    console(f"{STAGE} | finished={utc_now()} | status={status} | elapsed={summary['elapsed_sec']}s", quiet=args.quiet)
    console(json.dumps({"status": status, "elapsed_sec": summary["elapsed_sec"], "log_jsonl": str(log_jsonl), "summary_json": str(summary_path)}, indent=2, ensure_ascii=False), quiet=args.quiet)
    return 0 if status == "PIPELINE_COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
