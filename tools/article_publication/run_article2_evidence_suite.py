#!/usr/bin/env python3
"""Build the frozen Article 2 benchmark/fault-injection evidence bundle.

The collector is not called.  The expanded evidence directory is never deleted.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import importlib.util
import io
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
import trace
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

UTC = timezone.utc
PROGRAM = "XAUUSD_ARTICLE2_BENCHMARK_FAULT_INJECTION_SUITE_V1"
OUTPUT_FOLDER = "article2_evidence_v1"
ZIP_NAME = "XAUUSD_ARTICLE2_BENCHMARK_FAULT_INJECTION_EVIDENCE_V1.zip"


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def import_path(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def git_head(root: Path) -> str | None:
    proc = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], cwd=root, text=True, capture_output=True)
    return proc.stdout.strip() if proc.returncode == 0 else None


def run_core_adapters(root: Path) -> dict[str, Any]:
    stage170c_path = root / "app/stage170c_asof_join_enforcement_and_validation_framework.py"
    replay_path = root / "app/xauusd_controlled_paper_historical_replay.py"
    missing = [str(path.relative_to(root)) for path in (stage170c_path, replay_path) if not path.is_file()]
    if missing:
        return {"pass": False, "missing_files": missing, "adapters": []}

    stage170c = import_path(stage170c_path, "article2_stage170c_adapter")
    replay = import_path(replay_path, "article2_replay_adapter")
    contract_rows = [
        {
            "source_id": "CLEAN_BARS",
            "historical_asof_status": "HIGH",
            "observed_time_field": "bar_open_time_utc",
            "available_time_field": "bar_close_time_utc",
            "embargo_policy": "next_bar_only",
            "blocking_issue": "",
            "required_test": "clean",
        },
        {
            "source_id": "FAULT_MACRO",
            "historical_asof_status": "LOW",
            "observed_time_field": "observation_date",
            "available_time_field": "MISSING_OR_ASSUMED",
            "embargo_policy": "next_day",
            "blocking_issue": "future state risk",
            "required_test": "fault",
        },
    ]
    contract_report = stage170c.enforce_contract(contract_rows)
    contract_pass = contract_report[0]["pass_for_new_discovery"] is True and contract_report[1]["pass_for_new_discovery"] is False

    gross = 20.0
    spread = 12.5
    expected8 = gross - max(8.0, spread + 4.0)
    expected10 = gross - max(10.0, spread + 6.0)
    valid_cost = replay.source_proven_stress_contract(gross, spread, expected8, expected10, tolerance_bps=1e-9)
    corrupted_cost = replay.source_proven_stress_contract(gross, spread, gross - 8.0, gross - 10.0, tolerance_bps=1e-9)
    cost_pass = valid_cost["pass"] is True and corrupted_cost["pass"] is False and valid_cost["spread_plus_slippage_branch"] is True

    adapters = [
        {
            "adapter_id": "STAGE170C_CONTRACT_ENFORCEMENT",
            "pass": contract_pass,
            "clean_allowed": contract_report[0]["pass_for_new_discovery"],
            "fault_blocked": not contract_report[1]["pass_for_new_discovery"],
            "source_path": str(stage170c_path.relative_to(root)),
        },
        {
            "adapter_id": "HISTORICAL_REPLAY_COST_PARITY",
            "pass": cost_pass,
            "valid_contract_pass": valid_cost["pass"],
            "corrupted_contract_blocked": not corrupted_cost["pass"],
            "source_path": str(replay_path.relative_to(root)),
        },
    ]
    return {"pass": all(row["pass"] for row in adapters), "missing_files": [], "adapters": adapters}


def run_unit_tests(root: Path) -> dict[str, Any]:
    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    loader = unittest.TestLoader()
    suite = loader.discover(str(root / "tests"), pattern="test_article2_fail_closed_benchmark.py")
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    return {
        "pass": result.wasSuccessful(),
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "console": stream.getvalue(),
    }


def run_existing_core_regressions(root: Path) -> dict[str, Any]:
    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    stream = io.StringIO()
    replay_suite = unittest.TestLoader().discover(
        str(root / "tests"), pattern="test_xauusd_controlled_paper_historical_replay.py"
    )
    replay = unittest.TextTestRunner(stream=stream, verbosity=2).run(replay_suite)
    smoke_specs = [
        ("test_stage170a_methodology_temporal_integrity_audit_smoke.py", "test_stage170a_smoke"),
        ("test_stage170b_data_asof_contract_validation_redesign_smoke.py", "test_stage170b_smoke"),
        ("test_stage170c_asof_join_enforcement_and_validation_framework_smoke.py", "test_stage170c_smoke"),
    ]
    smoke_rows: list[dict[str, Any]] = []
    smoke_code = (
        "import importlib.util,sys; from pathlib import Path; "
        "p=Path(sys.argv[1]); s=importlib.util.spec_from_file_location('article2_smoke',p); "
        "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
        "getattr(m,sys.argv[2])(Path(sys.argv[3]))"
    )
    for index, (filename, function_name) in enumerate(smoke_specs, start=1):
        path = root / "tests" / filename
        if not path.is_file():
            smoke_rows.append({"test": function_name, "pass": False, "error": "FILE_MISSING"})
            continue
        with tempfile.TemporaryDirectory(prefix=f"article2-smoke-{index}-") as directory:
            proc = subprocess.run(
                [sys.executable, "-c", smoke_code, str(path), function_name, directory],
                cwd=root,
                text=True,
                capture_output=True,
            )
        stream.write(proc.stdout)
        stream.write(proc.stderr)
        smoke_rows.append({
            "test": function_name,
            "pass": proc.returncode == 0,
            "error": None if proc.returncode == 0 else f"RETURN_CODE_{proc.returncode}",
        })
    smoke_pass = all(row["pass"] for row in smoke_rows)
    return {
        "pass": replay.wasSuccessful() and smoke_pass,
        "tests_run": replay.testsRun + len(smoke_rows),
        "replay_tests_run": replay.testsRun,
        "smoke_tests_run": len(smoke_rows),
        "failures": len(replay.failures) + sum(not row["pass"] for row in smoke_rows),
        "errors": len(replay.errors),
        "skipped": len(replay.skipped),
        "smoke": smoke_rows,
        "console": stream.getvalue(),
    }


def function_statement_lines(path: Path, function_names: Iterable[str]) -> dict[str, set[int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    wanted = set(function_names)
    found: dict[str, set[int]] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in wanted:
            lines = {
                item.lineno
                for item in ast.walk(node)
                if isinstance(item, ast.stmt) and not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            found[node.name] = lines
    return found


def collect_scoped_line_coverage(root: Path, engine: Any, workload: Callable[[], Any]) -> dict[str, Any]:
    scopes = {
        root / "app/article2_fail_closed_benchmark.py": [
            "parse_aware_utc", "base_fixture", "apply_fault", "_full_checks", "_pit_fail_open_warnings",
            "evaluate_arm", "build_cases", "outcome_digest", "_runtime_profile", "run_benchmark", "article2_gate",
        ],
        root / "app/stage170c_asof_join_enforcement_and_validation_framework.py": ["norm_text", "enforce_contract"],
        root / "app/xauusd_controlled_paper_historical_replay.py": ["source_proven_stress_contract"],
    }
    tracer = trace.Trace(count=True, trace=False, ignoredirs=[sys.prefix, sys.exec_prefix])
    tracer.runfunc(workload)
    counts = tracer.results().counts
    rows: list[dict[str, Any]] = []
    total_statements = 0
    covered_statements = 0
    for path, names in scopes.items():
        if not path.is_file():
            for name in names:
                rows.append({"path": str(path.relative_to(root)), "function": name, "statements": 0, "covered": 0, "rate": 0.0, "missing": "FILE_MISSING"})
            continue
        found = function_statement_lines(path, names)
        for name in names:
            statement_lines = found.get(name, set())
            covered = {line for line in statement_lines if counts.get((str(path), line), 0) > 0}
            total_statements += len(statement_lines)
            covered_statements += len(covered)
            rows.append({
                "path": str(path.relative_to(root)),
                "function": name,
                "statements": len(statement_lines),
                "covered": len(covered),
                "rate": len(covered) / len(statement_lines) if statement_lines else 0.0,
                "missing_lines": sorted(statement_lines - covered),
            })
    return {
        "method": "CPYTHON_STDLIB_TRACE_OVER_FROZEN_FUNCTION_SCOPES",
        "scope_rule": "AST statement lines inside pre-registered functions; imported dependencies and unrelated historical stages excluded",
        "covered_statements": covered_statements,
        "total_statements": total_statements,
        "rate": covered_statements / total_statements if total_statements else 0.0,
        "functions": rows,
    }


def build_core_manifest(root: Path, intake_zip: Path | None, intake_root: Path | None) -> dict[str, Any]:
    selected = [
        "app/article2_fail_closed_benchmark.py",
        "app/stage170a_methodology_temporal_integrity_audit.py",
        "app/stage170b_data_asof_contract_validation_redesign.py",
        "app/stage170c_asof_join_enforcement_and_validation_framework.py",
        "app/xauusd_controlled_paper_historical_replay.py",
        "tools/article_publication/run_article2_evidence_suite.py",
        "tools/article_publication/verify_article2_evidence_bundle.py",
        "tests/test_article2_fail_closed_benchmark.py",
        "tests/test_stage170a_methodology_temporal_integrity_audit_smoke.py",
        "tests/test_stage170b_data_asof_contract_validation_redesign_smoke.py",
        "tests/test_stage170c_asof_join_enforcement_and_validation_framework_smoke.py",
        "tests/test_xauusd_controlled_paper_historical_replay.py",
        "configs/article2_benchmark_v1.json",
        "docs/article2/ARTICLE2_BENCHMARK_AND_FAULT_INJECTION_PROTOCOL.md",
        ".github/workflows/xauusd_article2_evidence.yml",
    ]
    files = []
    for rel in selected:
        path = root / rel
        files.append({
            "path": rel,
            "exists": path.is_file(),
            "size_bytes": path.stat().st_size if path.is_file() else None,
            "sha256": sha256_file(path) if path.is_file() else None,
        })
    intake: dict[str, Any] = {"zip": None, "expanded_root": None, "source_git_head": git_head(root)}
    if intake_zip and intake_zip.is_file():
        intake["zip"] = {"file_name": intake_zip.name, "size_bytes": intake_zip.stat().st_size, "sha256": sha256_file(intake_zip)}
    if intake_root and intake_root.is_dir():
        head_path = intake_root / "git_metadata/git_head.txt"
        intake["expanded_root"] = {
            "folder_name": intake_root.name,
            "preserved": True,
            "source_git_head": head_path.read_text(encoding="utf-8").strip() if head_path.is_file() else None,
        }
    return {
        "schema_version": "article2-core-evidence-manifest-v1",
        "all_required_files_present": all(row["exists"] for row in files),
        "files": files,
        "intake": intake,
    }


def deterministic_zip(folder: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(folder.rglob("*")):
            if not path.is_file():
                continue
            rel = Path(folder.name) / path.relative_to(folder)
            info = zipfile.ZipInfo(str(rel).replace(os.sep, "/"), date_time=(2026, 9, 14, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())


def decision_markdown(decision: Mapping[str, Any]) -> str:
    lines = [
        "# XAUUSD Article 2 Evidence Decision",
        "",
        f"Decision: **{decision['decision']}**",
        "",
        "This decision concerns the software/method evidence only. It does not reopen Article 1 strategy claims and does not authorize broker, demo, paper, or live orders.",
        "",
        "## Gate results",
        "",
        "| Gate | Pass |",
        "| --- | --- |",
    ]
    lines.extend(f"| {key} | {value} |" for key, value in decision["gates"].items())
    if decision["blocking_reasons"]:
        lines.extend(["", "## Blocking reasons", ""] + [f"- {item}" for item in decision["blocking_reasons"]])
    lines.extend([
        "",
        "## Scientific boundary",
        "",
        "Article 1 remains the empirical XAUUSD strategy audit. Article 2 evaluates whether point-in-time, provenance-bound, fail-closed controls reduce unsafe acceptance under controlled corruption.",
        "",
    ])
    return "\n".join(lines)


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).expanduser().resolve()
    config_path = (root / args.config).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    engine = import_path(root / "app/article2_fail_closed_benchmark.py", "article2_benchmark_engine")
    if config["arms"] != list(engine.ARMS) or config["fault_ids"] != [item.fault_id for item in engine.FAULTS]:
        raise RuntimeError("frozen config does not match benchmark code")

    out_parent = (root / args.output_dir).resolve()
    out_dir = out_parent / OUTPUT_FOLDER
    out_dir.mkdir(parents=True, exist_ok=True)
    intake_zip = Path(args.intake_zip).expanduser().resolve() if args.intake_zip else None
    intake_root = Path(args.intake_root).expanduser().resolve() if args.intake_root else None

    benchmark = engine.run_benchmark(repeats=int(config["controls"]["runtime_repeats"]), control_count=int(config["controls"]["clean_control_count"]))
    benchmark_gate, benchmark_reasons = engine.article2_gate(benchmark)
    adapters = run_core_adapters(root)
    tests = run_unit_tests(root)
    existing_regressions = run_existing_core_regressions(root)

    def workload() -> None:
        clean_benchmark = engine.run_benchmark(repeats=2, control_count=3)
        engine.article2_gate(clean_benchmark)
        mutations = []
        for path, value in [
            (("metrics", engine.ARMS[2], "fault_detection_rate"), 0.0),
            (("metrics", engine.ARMS[2], "unsafe_acceptance_rate"), 1.0),
            (("metrics", engine.ARMS[2], "false_blocking_rate"), 1.0),
            (("deterministic_reproduction",), False),
            (("semantic_branch_coverage", "rate"), 0.0),
        ]:
            item = json.loads(json.dumps(clean_benchmark))
            cursor = item
            for key in path[:-1]:
                cursor = cursor[key]
            cursor[path[-1]] = value
            mutations.append(item)
        small_fault_matrix = json.loads(json.dumps(clean_benchmark))
        small_fault_matrix["fault_specs"] = small_fault_matrix["fault_specs"][:2]
        mutations.append(small_fault_matrix)
        missing_arm = json.loads(json.dumps(clean_benchmark))
        missing_arm["arms"] = missing_arm["arms"][:2]
        mutations.append(missing_arm)
        for item in mutations:
            engine.article2_gate(item)
        run_core_adapters(root)

    coverage = collect_scoped_line_coverage(root, engine, workload)
    manifest = build_core_manifest(root, intake_zip, intake_root)
    coverage_gate = coverage["rate"] >= float(config["gates"]["scoped_line_coverage_min"])
    semantic_branch_gate = benchmark["semantic_branch_coverage"]["rate"] >= float(config["gates"]["semantic_branch_coverage_min"])
    expanded = manifest["intake"]["expanded_root"] or {}
    intake_bound = bool(manifest["intake"]["zip"] or expanded.get("source_git_head"))
    gates = {
        "benchmark": benchmark_gate,
        "core_adapters": adapters["pass"],
        "unit_tests": tests["pass"] and tests["tests_run"] >= 10,
        "existing_core_regressions": existing_regressions["pass"] and existing_regressions["tests_run"] >= 31,
        "scoped_line_coverage": coverage_gate,
        "semantic_branch_coverage": semantic_branch_gate,
        "core_manifest_complete": manifest["all_required_files_present"],
        "intake_provenance_bound": intake_bound,
        "no_execution_connector": engine.no_execution_connector_tokens(),
        "article_boundary_frozen": config["article_boundary"]["trading_alpha_reestimation_allowed"] is False,
    }
    blockers = list(benchmark_reasons)
    blockers.extend(key.upper() for key, value in gates.items() if not value)
    sufficient = all(gates.values()) and not blockers
    decision = {
        "program": PROGRAM,
        "generated_utc": utc_now(),
        "decision": "ARTICLE2_EVIDENCE_SUFFICIENT" if sufficient else "BLOCK_ARTICLE2",
        "pass": sufficient,
        "broker_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
        "gates": gates,
        "blocking_reasons": sorted(set(blockers)),
        "article1_reestimated": False,
        "collector_rerun": False,
        "expanded_intake_preserved": bool(intake_root and intake_root.is_dir()),
    }

    outcomes_rows = []
    for row in benchmark["outcomes"]:
        outcomes_rows.append({
            "arm": row["arm"], "case_id": row["case_id"], "is_fault": row["is_fault"],
            "accepted": row["accepted"], "detected": row["detected"], "reasons": ";".join(row["reasons"]),
        })
    fault_rows = [dict(item) for item in benchmark["fault_specs"]]
    write_json(out_dir / "article2_benchmark_summary.json", benchmark)
    write_csv(out_dir / "article2_benchmark_outcomes.csv", outcomes_rows)
    write_csv(out_dir / "article2_fault_injection_matrix.csv", fault_rows)
    write_json(out_dir / "article2_core_adapter_results.json", adapters)
    write_json(out_dir / "article2_core_evidence_manifest.json", manifest)
    write_json(out_dir / "article2_coverage_summary.json", coverage)
    write_json(out_dir / "article2_reproducibility_report.json", {
        "deterministic": benchmark["deterministic_reproduction"],
        "digest_sha256": benchmark["deterministic_digest_sha256"],
        "fixture_generation": "deterministic; no random state; one isolated mutation per fault case",
        "runtime_values_excluded_from_digest": True,
    })
    write_json(out_dir / "article2_environment.json", {
        "generated_utc": utc_now(),
        "python": sys.version,
        "platform": platform.platform(),
        "executable": sys.executable,
    })
    (out_dir / "article2_unit_test_console.txt").write_text(tests["console"], encoding="utf-8")
    write_json(out_dir / "article2_unit_test_summary.json", {key: value for key, value in tests.items() if key != "console"})
    (out_dir / "article2_existing_core_regression_console.txt").write_text(existing_regressions["console"], encoding="utf-8")
    write_json(out_dir / "article2_existing_core_regression_summary.json", {key: value for key, value in existing_regressions.items() if key != "console"})
    write_json(out_dir / "article2_decision.json", decision)
    (out_dir / "article2_decision.md").write_text(decision_markdown(decision), encoding="utf-8")
    (out_dir / "FROZEN_BENCHMARK_CONFIG.json").write_text(config_path.read_text(encoding="utf-8"), encoding="utf-8")

    artifact_files = sorted(path for path in out_dir.rglob("*") if path.is_file() and path.name not in {"SHA256SUMS.txt", "package_manifest.json"})
    package_rows = [
        {"path": str(path.relative_to(out_dir)), "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in artifact_files
    ]
    write_json(out_dir / "package_manifest.json", {
        "program": PROGRAM,
        "file_count": len(package_rows),
        "files": package_rows,
    })
    artifact_files = sorted(path for path in out_dir.rglob("*") if path.is_file() and path.name != "SHA256SUMS.txt")
    sums = "".join(f"{sha256_file(path)}  {path.relative_to(out_dir)}\n" for path in artifact_files)
    (out_dir / "SHA256SUMS.txt").write_text(sums, encoding="utf-8")

    zip_path = out_parent / ZIP_NAME
    deterministic_zip(out_dir, zip_path)
    zip_sha = sha256_file(zip_path)
    (out_parent / f"{ZIP_NAME}.sha256").write_text(f"{zip_sha}  {ZIP_NAME}\n", encoding="utf-8")
    summary = {
        **decision,
        "output_folder": str(out_dir),
        "output_zip": str(zip_path),
        "output_zip_sha256": zip_sha,
        "output_zip_size_bytes": zip_path.stat().st_size,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", default="configs/article2_benchmark_v1.json")
    parser.add_argument("--output-dir", default="artifacts/article2")
    parser.add_argument("--intake-zip")
    parser.add_argument("--intake-root")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        summary = run(build_parser().parse_args(argv))
    except Exception as exc:  # fail closed and leave a concise machine-readable terminal record
        print(json.dumps({"program": PROGRAM, "decision": "BLOCK_ARTICLE2", "pass": False, "error": f"{type(exc).__name__}: {exc}"}, indent=2), file=sys.stderr)
        return 2
    return 0 if summary["pass"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
