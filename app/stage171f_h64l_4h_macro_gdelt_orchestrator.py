#!/usr/bin/env python3
"""
Stage171F2 — H64L Four-Hour Macro Rebuild + GDELT Snapshot Orchestrator.

Operational scope only:
- checks the manually maintained AMarkets files;
- runs the existing official macro download and normalize/rebuild chain;
- imports the latest GDELT refresh from a dedicated GitHub data branch, with
  Downloads-artifact fallback;
- validates that the H64L feature dataset is fresh;
- only then invokes Stage171D log-only shadow evaluation.

Hard constraints:
- no threshold optimization;
- no MT5 signal;
- no order routing;
- no demo/live authorization;
- stale feature data blocks shadow evaluation instead of re-logging an old row.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

STAGE = "Stage171F2_H64L_4H_MACRO_REBUILD_GDELT_ORCHESTRATOR"
DEFAULT_CONFIG = "configs/stage171f_h64l_4h_macro_gdelt_orchestrator.json"
DEFAULT_REPORT_DIR = "reports/stage171f_h64l_4h_macro_gdelt_orchestrator"
DEFAULT_FEATURE_DATASET = "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv"
DEFAULT_GDELT_PANEL = "reports/stage166_current_event_shock_overlay/stage166_current_event_intraday_panel.csv"
DEFAULT_RULE = "reports/stage171e_h64l_exact_rule_lock_from_archive/stage171e_h64l_exact_locked_rule.json"
DEFAULT_LEDGER = "data/forward_shadow/h64l_manual_shadow_log.csv"
DEFAULT_LOCK = "data/forward_shadow/stage171f_orchestrator.lock"


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def utc_iso(value: Optional[dt.datetime] = None) -> str:
    x = value or utc_now()
    return x.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve(root: Path, value: str | Path) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else root / p


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: Iterable[Dict[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(fieldnames), extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def file_sha256(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def detect_separator(path: Path) -> str:
    with path.open("r", encoding="utf-8-sig", errors="replace") as f:
        line = f.readline()
    counts = {sep: line.count(sep) for sep in ["\t", ",", ";", "|"]}
    return max(counts, key=counts.get) if max(counts.values(), default=0) > 0 else ","


def parse_utcish(value: str) -> Optional[dt.datetime]:
    s = str(value or "").strip()
    if not s:
        return None
    try:
        x = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        if x.tzinfo is None:
            x = x.replace(tzinfo=dt.timezone.utc)
        return x.astimezone(dt.timezone.utc)
    except Exception:
        pass
    for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"]:
        try:
            return dt.datetime.strptime(s, fmt).replace(tzinfo=dt.timezone.utc)
        except Exception:
            pass
    return None


def inspect_feature_dataset(path: Path, max_age_days: float) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "sha256": file_sha256(path),
        "mtime_utc": None,
        "row_count": 0,
        "latest_feature_date_utc": None,
        "latest_sample_available_after_utc": None,
        "age_days": None,
        "fresh": False,
    }
    if not path.exists():
        return out
    out["mtime_utc"] = utc_iso(dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc))
    sep = detect_separator(path)
    latest_row: Optional[Dict[str, str]] = None
    latest_key = ""
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.DictReader(f, delimiter=sep)
        for row in reader:
            out["row_count"] += 1
            key = str(row.get("sample_available_after_utc") or row.get("available_after_utc") or row.get("feature_date_utc") or row.get("date_utc") or "")
            if key >= latest_key:
                latest_key = key
                latest_row = row
    if latest_row:
        feature_date = str(latest_row.get("feature_date_utc") or latest_row.get("date_utc") or "")
        available = str(latest_row.get("sample_available_after_utc") or latest_row.get("available_after_utc") or feature_date)
        out["latest_feature_date_utc"] = feature_date
        out["latest_sample_available_after_utc"] = available
        parsed = parse_utcish(available) or parse_utcish(feature_date)
        if parsed:
            age = (utc_now() - parsed).total_seconds() / 86400.0
            out["age_days"] = round(age, 4)
            out["fresh"] = age <= float(max_age_days)
    return out


def inspect_files(paths: Sequence[Path], stale_hours: float) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    now = utc_now()
    for p in paths:
        row: Dict[str, Any] = {"path": str(p), "exists": p.exists(), "size": None, "mtime_utc": None, "age_hours": None, "fresh": False}
        if p.exists():
            stat = p.stat()
            modified = dt.datetime.fromtimestamp(stat.st_mtime, tz=dt.timezone.utc)
            age = (now - modified).total_seconds() / 3600.0
            row.update({"size": stat.st_size, "mtime_utc": utc_iso(modified), "age_hours": round(age, 3), "fresh": age <= stale_hours})
        rows.append(row)
    return rows


def format_argv(argv: Sequence[str], root: Path, python_exe: str, inbox: Path) -> List[str]:
    mapping = {"{root}": str(root), "{python}": python_exe, "{inbox}": str(inbox)}
    return [mapping.get(str(x), str(x).replace("{root}", str(root)).replace("{python}", python_exe).replace("{inbox}", str(inbox))) for x in argv]


def run_command(name: str, argv: Sequence[str], root: Path, timeout_seconds: int, env_extra: Dict[str, str], required: bool) -> Dict[str, Any]:
    started = utc_now()
    result: Dict[str, Any] = {
        "name": name,
        "argv": list(argv),
        "required": required,
        "started_utc": utc_iso(started),
        "finished_utc": None,
        "elapsed_seconds": None,
        "returncode": None,
        "ok": False,
        "stdout_tail": "",
        "stderr_tail": "",
        "error": "",
    }
    try:
        env = os.environ.copy()
        env.update(env_extra)
        cp = subprocess.run(
            list(argv), cwd=str(root), env=env, text=True, capture_output=True,
            timeout=max(1, int(timeout_seconds)), check=False,
        )
        result["returncode"] = cp.returncode
        result["ok"] = cp.returncode == 0
        result["stdout_tail"] = (cp.stdout or "")[-8000:]
        result["stderr_tail"] = (cp.stderr or "")[-8000:]
    except subprocess.TimeoutExpired as exc:
        result["error"] = f"TIMEOUT:{exc}"
        result["stdout_tail"] = (exc.stdout or "")[-8000:] if isinstance(exc.stdout, str) else ""
        result["stderr_tail"] = (exc.stderr or "")[-8000:] if isinstance(exc.stderr, str) else ""
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"{type(exc).__name__}:{exc}"
    finished = utc_now()
    result["finished_utc"] = utc_iso(finished)
    result["elapsed_seconds"] = round((finished - started).total_seconds(), 3)
    return result


def merge_gdelt_panel(existing_path: Path, incoming_path: Path) -> Dict[str, Any]:
    if not incoming_path.exists():
        return {"ok": False, "error": f"incoming panel missing: {incoming_path}"}
    incoming_sep = detect_separator(incoming_path)
    rows_by_time: Dict[str, Dict[str, str]] = {}
    fields: List[str] = []
    existing_count = 0
    if existing_path.exists():
        with existing_path.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
            reader = csv.DictReader(f, delimiter=detect_separator(existing_path))
            fields = list(reader.fieldnames or [])
            for row in reader:
                k = str(row.get("time_bucket_utc") or "")
                if k:
                    rows_by_time[k] = row
                    existing_count += 1
    incoming_count = 0
    with incoming_path.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.DictReader(f, delimiter=incoming_sep)
        if not fields:
            fields = list(reader.fieldnames or [])
        for col in list(reader.fieldnames or []):
            if col not in fields:
                fields.append(col)
        for row in reader:
            k = str(row.get("time_bucket_utc") or "")
            if k:
                rows_by_time[k] = row
                incoming_count += 1
    if "time_bucket_utc" not in fields:
        return {"ok": False, "error": "time_bucket_utc missing"}
    existing_path.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if existing_path.exists():
        backup = existing_path.with_suffix(".pre_stage171f_backup.csv")
        shutil.copy2(existing_path, backup)
    ordered = [rows_by_time[k] for k in sorted(rows_by_time)]
    write_csv(existing_path, ordered, fields)
    return {
        "ok": True,
        "existing_rows_read": existing_count,
        "incoming_rows_read": incoming_count,
        "merged_rows": len(ordered),
        "backup": str(backup) if backup else None,
        "output": str(existing_path),
    }


def git_import_gdelt(root: Path, cfg: Dict[str, Any], report_dir: Path) -> Dict[str, Any]:
    branch = str(cfg.get("branch", "automation/gdelt-latest"))
    remote = str(cfg.get("remote", "origin"))
    result: Dict[str, Any] = {"mode": "git_branch", "branch": branch, "remote": remote, "ok": False}
    with tempfile.TemporaryDirectory(prefix="stage171f_gdelt_") as td:
        tmp = Path(td)
        fetch = run_command("gdelt_git_fetch", ["git", "fetch", "--quiet", "--depth=1", remote, branch], root, int(cfg.get("fetch_timeout_seconds", 180)), {}, False)
        result["fetch"] = fetch
        if not fetch.get("ok"):
            result["error"] = "GDELT_BRANCH_NOT_PUBLISHED_OR_FETCH_FAILED"
            return result
        wanted = [
            "stage166f_current_event_intraday_panel.csv",
            "stage166f_fetch_status.csv",
            "stage166f_gdelt_points.csv",
            "stage166f_gdelt_backfill_summary.json",
            "stage166f_artifact_manifest.json",
        ]
        extracted: Dict[str, str] = {}
        for name in wanted:
            cp = subprocess.run(["git", "show", f"FETCH_HEAD:{name}"], cwd=str(root), capture_output=True, check=False)
            if cp.returncode == 0:
                dest = tmp / name
                dest.write_bytes(cp.stdout)
                extracted[name] = str(dest)
        panel = tmp / "stage166f_current_event_intraday_panel.csv"
        if not panel.exists():
            result["error"] = "GDELT_BRANCH_PANEL_MISSING"
            result["extracted"] = extracted
            return result
        target_panel = resolve(root, cfg.get("compatible_panel", DEFAULT_GDELT_PANEL))
        result["merge"] = merge_gdelt_panel(target_panel, panel)
        lineage = report_dir.parent / "stage166f_github_gdelt_backfill"
        lineage.mkdir(parents=True, exist_ok=True)
        for name in wanted:
            src = tmp / name
            if src.exists():
                shutil.copy2(src, lineage / f"latest_{name}")
        result["extracted"] = extracted
        result["ok"] = bool(result["merge"].get("ok"))
        return result


def artifact_import_gdelt(root: Path, cfg: Dict[str, Any], report_dir: Path) -> Dict[str, Any]:
    downloads = Path(cfg.get("downloads_dir", "~/Downloads")).expanduser()
    patterns = cfg.get("artifact_globs", ["stage166f-gdelt-refresh-*.zip", "stage166f-gdelt-backfill-*.zip"])
    candidates: List[Path] = []
    for pattern in patterns:
        candidates.extend(downloads.glob(pattern))
    candidates = sorted({p.resolve() for p in candidates if p.is_file()}, key=lambda p: p.stat().st_mtime, reverse=True)
    result: Dict[str, Any] = {"mode": "downloads_artifact", "ok": False, "candidate_count": len(candidates)}
    if not candidates:
        result["error"] = "NO_GDELT_ARTIFACT_IN_DOWNLOADS"
        return result
    selected = candidates[0]
    modified = dt.datetime.fromtimestamp(selected.stat().st_mtime, tz=dt.timezone.utc)
    age_hours = (utc_now() - modified).total_seconds() / 3600.0
    max_age_hours = float(cfg.get("max_artifact_age_hours", 18))
    result.update({
        "selected": str(selected),
        "selected_mtime_utc": utc_iso(modified),
        "selected_age_hours": round(age_hours, 3),
        "max_artifact_age_hours": max_age_hours,
    })
    if age_hours > max_age_hours:
        result["error"] = "STALE_GDELT_ARTIFACT_NOT_IMPORTED"
        return result
    with tempfile.TemporaryDirectory(prefix="stage171f_artifact_") as td:
        temp = Path(td)
        try:
            with zipfile.ZipFile(selected) as zf:
                zf.extractall(temp)
        except Exception as exc:  # noqa: BLE001
            result["error"] = f"BAD_GDELT_ZIP:{exc}"
            return result
        panels = list(temp.rglob("stage166f_current_event_intraday_panel.csv"))
        if not panels:
            result["error"] = "GDELT_ARTIFACT_PANEL_MISSING"
            return result
        target_panel = resolve(root, cfg.get("compatible_panel", DEFAULT_GDELT_PANEL))
        result["merge"] = merge_gdelt_panel(target_panel, panels[0])
        result["ok"] = bool(result["merge"].get("ok"))
        return result


def refresh_gdelt(root: Path, cfg: Dict[str, Any], report_dir: Path) -> Dict[str, Any]:
    if not cfg.get("enabled", True):
        return {"ok": True, "enabled": False, "status": "GDELT_DISABLED_BY_CONFIG"}
    branch_result = git_import_gdelt(root, cfg, report_dir)
    if branch_result.get("ok"):
        return branch_result
    artifact_result = artifact_import_gdelt(root, cfg, report_dir)
    return {"ok": artifact_result.get("ok", False), "branch_attempt": branch_result, "artifact_attempt": artifact_result}


def acquire_lock(path: Path, stale_hours: float) -> Tuple[bool, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        age_hours = (time.time() - path.stat().st_mtime) / 3600.0
        if age_hours > stale_hours:
            path.unlink(missing_ok=True)
        else:
            return False, f"ACTIVE_LOCK age_hours={age_hours:.3f} path={path}"
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps({"pid": os.getpid(), "started_utc": utc_iso()}) + "\n")
        return True, "LOCK_ACQUIRED"
    except FileExistsError:
        return False, f"LOCK_RACE path={path}"


def load_config(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def render_step_commands(cfg: Dict[str, Any], root: Path, python_exe: str, inbox: Path) -> List[Dict[str, Any]]:
    out = []
    for item in cfg.get("local_pipeline", []):
        row = dict(item)
        row["argv"] = format_argv(item.get("argv", []), root, python_exe, inbox)
        out.append(row)
    return out


def run_once(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    config_path = resolve(root, args.config)
    cfg = load_config(config_path)
    report_dir = resolve(root, cfg.get("report_dir", DEFAULT_REPORT_DIR))
    report_dir.mkdir(parents=True, exist_ok=True)
    lock_path = resolve(root, cfg.get("lock_file", DEFAULT_LOCK))
    acquired, lock_note = acquire_lock(lock_path, float(cfg.get("lock_stale_hours", 8)))
    if not acquired:
        summary = {"stage": STAGE, "generated_utc": utc_iso(), "status": "STAGE171F_SKIPPED_LOCKED", "lock": lock_note, "order_routing_allowed": False}
        write_json(report_dir / "stage171f_orchestrator_summary.json", summary)
        print(json.dumps(summary, indent=2))
        return 0

    started = utc_now()
    python_exe = str(cfg.get("python_executable") or sys.executable or "python3")
    inbox = Path(cfg.get("fundamental_event_inbox", "~/Downloads/xauusd_fundamental_event_inbox")).expanduser()
    feature_path = resolve(root, cfg.get("feature_dataset", DEFAULT_FEATURE_DATASET))
    rule_path = resolve(root, cfg.get("locked_rule", DEFAULT_RULE))
    ledger_path = resolve(root, cfg.get("shadow_ledger", DEFAULT_LEDGER))
    before = inspect_feature_dataset(feature_path, float(cfg.get("max_feature_age_days", 3)))
    macro_steps: List[Dict[str, Any]] = []
    try:
        env_extra = {
            "XAUUSD_REPO_ROOT": str(root),
            "XAUUSD_FUNDAMENTAL_EVENT_INBOX": str(inbox),
            "PYTHONUNBUFFERED": "1",
        }
        for item in render_step_commands(cfg, root, python_exe, inbox):
            argv = item.get("argv", [])
            required = bool(item.get("required", False))
            if not argv:
                macro_steps.append({"name": item.get("name", "unnamed"), "ok": not required, "required": required, "error": "EMPTY_ARGV"})
                continue
            executable_path = Path(argv[1]) if len(argv) > 1 and argv[0] == python_exe else None
            if executable_path and not executable_path.is_absolute():
                executable_path = root / executable_path
            if executable_path and not executable_path.exists():
                macro_steps.append({"name": item.get("name", "unnamed"), "argv": argv, "required": required, "ok": not required, "skipped": True, "error": "SCRIPT_NOT_FOUND"})
                continue
            macro_steps.append(run_command(
                str(item.get("name", "unnamed")), argv, root,
                int(item.get("timeout_seconds", 1800)), env_extra, required,
            ))

        gdelt_result = refresh_gdelt(root, cfg.get("gdelt", {}), report_dir)
        after = inspect_feature_dataset(feature_path, float(cfg.get("max_feature_age_days", 3)))
        feature_changed = before.get("sha256") != after.get("sha256")
        required_failures = [s for s in macro_steps if s.get("required") and not s.get("ok")]
        stage64k_steps = [s for s in macro_steps if "stage64k" in str(s.get("name", "")).lower()]
        stage64k_rebuild_ok = bool(stage64k_steps) and all(bool(s.get("ok")) for s in stage64k_steps)

        shadow_result: Dict[str, Any]
        if required_failures:
            shadow_result = {"ok": False, "skipped": True, "reason": "REQUIRED_MACRO_PIPELINE_STEP_FAILED"}
        elif not stage64k_rebuild_ok:
            shadow_result = {"ok": False, "skipped": True, "reason": "STAGE64K_REBUILD_NOT_CONFIRMED"}
        elif not after.get("fresh"):
            shadow_result = {"ok": False, "skipped": True, "reason": "STALE_FEATURE_DATASET", "feature_age_days": after.get("age_days")}
        elif not rule_path.exists():
            shadow_result = {"ok": False, "skipped": True, "reason": "EXACT_LOCKED_RULE_MISSING", "path": str(rule_path)}
        else:
            shadow_argv = [
                python_exe,
                str(resolve(root, cfg.get("shadow_script", "app/stage171d_h64l_shadow_scheduler_and_logger.py"))),
                "run-once",
                "--root", str(root),
                "--macro-dataset", str(feature_path),
                "--locked-rule-candidate", str(rule_path),
                "--ledger-csv", str(ledger_path),
                "--operator-note", "stage171f_4h_orchestrated_refresh",
            ]
            shadow_result = run_command("stage171d_shadow", shadow_argv, root, int(cfg.get("shadow_timeout_seconds", 300)), env_extra, True)

        amarkets_paths = [Path(x).expanduser() for x in cfg.get("amarkets_manual_files", [])]
        amarkets = inspect_files(amarkets_paths, float(cfg.get("amarkets_stale_hours", 36)))
        finished = utc_now()
        if required_failures:
            decision = "STAGE171F2_REQUIRED_MACRO_REFRESH_FAILED_SHADOW_BLOCKED"
        elif not stage64k_rebuild_ok:
            decision = "STAGE171F2_STAGE64K_REBUILD_FAILED_SHADOW_BLOCKED"
        elif not after.get("fresh"):
            decision = "STAGE171F2_MACRO_FEATURE_DATA_STALE_SHADOW_BLOCKED"
        elif not shadow_result.get("ok"):
            decision = "STAGE171F2_FEATURES_FRESH_BUT_SHADOW_RUN_FAILED"
        elif not gdelt_result.get("ok"):
            decision = "STAGE171F2_H64L_SHADOW_UPDATED_GDELT_GUARD_DEGRADED"
        else:
            decision = "STAGE171F2_4H_REFRESH_AND_SHADOW_COMPLETE_NO_ORDER"
        summary = {
            "stage": STAGE,
            "generated_utc": utc_iso(finished),
            "started_utc": utc_iso(started),
            "elapsed_seconds": round((finished - started).total_seconds(), 3),
            "root": str(root),
            "config": str(config_path),
            "interval_seconds": int(cfg.get("interval_seconds", 14400)),
            "order_routing_allowed": False,
            "demo_release_allowed": False,
            "threshold_reoptimization_allowed": False,
            "decision": decision,
            "amarkets_policy": "MANUAL_DOWNLOAD_FRESHNESS_CHECK_ONLY",
            "amarkets_files": amarkets,
            "feature_dataset_before": before,
            "feature_dataset_after": after,
            "feature_dataset_changed": feature_changed,
            "stage64k_rebuild_ok": stage64k_rebuild_ok,
            "macro_pipeline_steps": macro_steps,
            "required_failure_count": len(required_failures),
            "gdelt_refresh": gdelt_result,
            "shadow_run": shadow_result,
            "next": [
                "Keep the Stage171F four-hour LaunchAgent active; it replaces direct Stage171D scheduling.",
                "Update AMarkets CSV files manually; stale AMarkets status is reported but never downloaded by this stage.",
                "Use the GitHub Actions workflow XAUUSD Stage166F GDELT Four-Hour Refresh for remote GDELT collection.",
                "No order is allowed; a real H64L shadow hit only opens the limited demo-bridge review gate.",
            ],
        }
        write_json(report_dir / "stage171f_orchestrator_summary.json", summary)
        write_csv(
            report_dir / "stage171f_pipeline_step_status.csv", macro_steps,
            ["name", "required", "ok", "returncode", "started_utc", "finished_utc", "elapsed_seconds", "error", "argv", "stdout_tail", "stderr_tail"],
        )
        md = f"""# Stage171F2 H64L Four-Hour Macro Rebuild + GDELT Orchestrator

Generated UTC: `{summary['generated_utc']}`

Decision: `{decision}`

- Feature dataset fresh: `{after.get('fresh')}`
- Feature dataset date: `{after.get('latest_feature_date_utc')}`
- Feature dataset age days: `{after.get('age_days')}`
- Feature dataset changed in this run: `{feature_changed}`
- Required macro failures: `{len(required_failures)}`
- Stage64K rebuild confirmed: `{stage64k_rebuild_ok}`
- GDELT refresh OK: `{gdelt_result.get('ok')}`
- Shadow run OK: `{shadow_result.get('ok')}`
- Orders allowed: `False`

AMarkets remains manual. This orchestrator only checks its freshness. If the feature dataset remains stale, Stage171D is intentionally skipped instead of appending another misleading row from old macro data.
"""
        (report_dir / "stage171f_decision.md").write_text(md, encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
        return 0 if decision in {"STAGE171F2_4H_REFRESH_AND_SHADOW_COMPLETE_NO_ORDER", "STAGE171F2_H64L_SHADOW_UPDATED_GDELT_GUARD_DEGRADED"} else 2
    finally:
        lock_path.unlink(missing_ok=True)


def write_plist(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    config = resolve(root, args.config)
    plist_path = Path(args.plist_path).expanduser().resolve()
    report_dir = resolve(root, args.report_dir or DEFAULT_REPORT_DIR)
    report_dir.mkdir(parents=True, exist_ok=True)
    python_exe = str(Path(args.python_executable).expanduser().resolve()) if args.python_executable else (sys.executable or "/usr/bin/python3")
    script = root / "app" / "stage171f_h64l_4h_macro_gdelt_orchestrator.py"
    payload = {
        "Label": args.label,
        "ProgramArguments": [python_exe, str(script), "run-once", "--root", str(root), "--config", str(config)],
        "WorkingDirectory": str(root),
        "StartInterval": int(args.interval_seconds),
        "RunAtLoad": True,
        "StandardOutPath": str(report_dir / "launchd_stdout.log"),
        "StandardErrorPath": str(report_dir / "launchd_stderr.log"),
        "ProcessType": "Background",
    }
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    with plist_path.open("wb") as f:
        plistlib.dump(payload, f, sort_keys=False)
    print(json.dumps({"plist_path": str(plist_path), "label": args.label, "interval_seconds": int(args.interval_seconds), "program": payload["ProgramArguments"]}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Stage171F2 H64L four-hour macro rebuild/GDELT ops orchestrator")
    sub = p.add_subparsers(dest="mode", required=True)
    r = sub.add_parser("run-once")
    r.add_argument("--root", required=True)
    r.add_argument("--config", default=DEFAULT_CONFIG)
    w = sub.add_parser("write-launchd-plist")
    w.add_argument("--root", required=True)
    w.add_argument("--config", default=DEFAULT_CONFIG)
    w.add_argument("--plist-path", required=True)
    w.add_argument("--label", default="com.xauusd.stage171f.h64l-4h-ops")
    w.add_argument("--interval-seconds", type=int, default=14400)
    w.add_argument("--python-executable", default="")
    w.add_argument("--report-dir", default=DEFAULT_REPORT_DIR)
    return p


def main() -> None:
    args = build_parser().parse_args()
    if args.mode == "run-once":
        raise SystemExit(run_once(args))
    if args.mode == "write-launchd-plist":
        raise SystemExit(write_plist(args))
    raise SystemExit(2)


if __name__ == "__main__":
    main()
