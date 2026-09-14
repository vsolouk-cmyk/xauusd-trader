#!/usr/bin/env python3
"""Build publication tables and a frozen result snapshot from verified Article 2 evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile


PROGRAM = "XAUUSD_ARTICLE2_MANUSCRIPT_INPUTS_V1"
FULL_ARM = "POINT_IN_TIME_PROVENANCE_FAIL_CLOSED"
ARM_LABELS = {
    "NAIVE_LATEST_STATE": "Naive latest-state",
    "POINT_IN_TIME_FAIL_OPEN": "Point-in-time, fail-open",
    FULL_ARM: "Point-in-time + provenance, fail-closed",
}


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    if not path.is_file():
        raise ValueError(f"missing required evidence file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON evidence file: {path}: {exc}") from exc


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def pct(value: float) -> str:
    return f"{100.0 * value:.2f}%"


def latex_escape(value: object) -> str:
    text = str(value)
    for source, target in (
        ("\\", r"\textbackslash{}"),
        ("&", r"\&"),
        ("%", r"\%"),
        ("_", r"\_"),
        ("#", r"\#"),
    ):
        text = text.replace(source, target)
    return text


def csv_text(fieldnames: list[str], rows: list[dict]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def markdown_table(headers: list[str], rows: list[list[object]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(str(cell) for cell in row) + " |" for row in rows)
    return "\n".join(lines) + "\n"


def latex_table(headers: list[str], rows: list[list[object]], caption: str, label: str) -> str:
    columns = "l" + "r" * (len(headers) - 1)
    body = [
        r"\begin{table}[htbp]",
        r"\centering",
        f"\\caption{{{latex_escape(caption)}}}",
        f"\\label{{{latex_escape(label)}}}",
        f"\\begin{{tabular}}{{{columns}}}",
        r"\hline",
        " & ".join(latex_escape(item) for item in headers) + r" \\",
        r"\hline",
    ]
    body.extend(" & ".join(latex_escape(item) for item in row) + r" \\" for row in rows)
    body.extend([r"\hline", r"\end{tabular}", r"\end{table}", ""])
    return "\n".join(body)


def arm_figure(rows: list[dict]) -> str:
    colors = ["#8c96a0", "#d98e04", "#167d5a"]
    width, height = 940, 520
    baseline = 410
    chart_height = 300
    bar_width = 90
    groups = [("Detection rate", "fault_detection_rate", 150), ("Unsafe acceptance", "unsafe_acceptance_rate", 545)]
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<style>text{font-family:Arial,sans-serif;fill:#17212b}.title{font-size:22px;font-weight:700}.label{font-size:14px}.value{font-size:14px;font-weight:700}.axis{stroke:#53606d;stroke-width:1}</style>',
        '<text class="title" x="470" y="38" text-anchor="middle">Controlled fault-injection benchmark</text>',
    ]
    for title, key, start_x in groups:
        elements.append(f'<text class="label" x="{start_x + 140}" y="78" text-anchor="middle">{title}</text>')
        elements.append(f'<line class="axis" x1="{start_x - 20}" y1="{baseline}" x2="{start_x + 300}" y2="{baseline}"/>')
        for index, row in enumerate(rows):
            value = float(row[key])
            x = start_x + index * 105
            bar_height = chart_height * value
            y = baseline - bar_height
            elements.append(f'<rect x="{x}" y="{y:.2f}" width="{bar_width}" height="{bar_height:.2f}" fill="{colors[index]}"/>')
            elements.append(f'<text class="value" x="{x + bar_width/2:.1f}" y="{max(100, y - 8):.2f}" text-anchor="middle">{100*value:.0f}%</text>')
            elements.append(f'<text class="label" x="{x + bar_width/2:.1f}" y="{baseline + 25}" text-anchor="middle">Arm {index + 1}</text>')
    legend_y = 475
    for index, row in enumerate(rows):
        x = 80 + index * 290
        elements.append(f'<rect x="{x}" y="{legend_y - 13}" width="16" height="16" fill="{colors[index]}"/>')
        elements.append(f'<text class="label" x="{x + 24}" y="{legend_y}">{row["short_label"]}</text>')
    elements.append('</svg>')
    return "\n".join(elements) + "\n"


def deterministic_zip(zip_path: Path, root: Path, files: list[Path]) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(files, key=lambda item: item.as_posix()):
            arcname = path.relative_to(root).as_posix()
            info = zipfile.ZipInfo(arcname, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())


def build(root: Path, evidence_dir: Path, output_dir: Path, zip_path: Path) -> dict:
    decision = load_json(evidence_dir / "article2_decision.json")
    benchmark = load_json(evidence_dir / "article2_benchmark_summary.json")
    coverage = load_json(evidence_dir / "article2_coverage_summary.json")
    reproducibility = load_json(evidence_dir / "article2_reproducibility_report.json")
    regression = load_json(evidence_dir / "article2_existing_core_regression_summary.json")
    unit = load_json(evidence_dir / "article2_unit_test_summary.json")
    adapters = load_json(evidence_dir / "article2_core_adapter_results.json")
    environment = load_json(evidence_dir / "article2_environment.json")

    require(decision.get("decision") == "ARTICLE2_EVIDENCE_SUFFICIENT" and decision.get("pass") is True,
            "source evidence decision is not ARTICLE2_EVIDENCE_SUFFICIENT")
    metrics = benchmark.get("metrics", {})
    require(list(benchmark.get("arms", [])) == list(ARM_LABELS), "benchmark arms changed from the frozen order")
    require(len(benchmark.get("fault_specs", [])) == 12, "frozen fault count must equal 12")
    require(metrics.get(FULL_ARM, {}).get("fault_detection_rate") == 1.0, "full-arm detection rate is not 100%")
    require(metrics.get(FULL_ARM, {}).get("unsafe_acceptance_rate") == 0.0, "full-arm unsafe acceptance is not zero")
    require(metrics.get(FULL_ARM, {}).get("false_blocking_rate") == 0.0, "full-arm false blocking is not zero")
    require(benchmark.get("semantic_branch_coverage", {}).get("rate") == 1.0, "semantic branch coverage is not 100%")
    require(float(coverage.get("rate", 0.0)) >= 0.80, "scoped line coverage is below the frozen gate")
    require(reproducibility.get("deterministic") is True, "reproduction digest is not deterministic")
    require(regression.get("pass") is True and regression.get("skipped") == 0, "existing core regression suite failed or skipped tests")
    require(unit.get("pass") is True and unit.get("skipped") == 0, "Article 2 unit suite failed or skipped tests")
    require(adapters.get("pass") is True and not adapters.get("missing_files"), "core adapters did not pass")

    output_dir.mkdir(parents=True, exist_ok=True)
    source_files = sorted(path for path in evidence_dir.iterdir() if path.is_file())
    source_hashes = {path.name: sha256_path(path) for path in source_files}

    arm_rows = []
    for index, arm in enumerate(benchmark["arms"], start=1):
        metric = metrics[arm]
        runtime = metric["runtime"]
        arm_rows.append({
            "arm": arm,
            "short_label": f"Arm {index}",
            "label": ARM_LABELS[arm],
            "fault_detection_rate": metric["fault_detection_rate"],
            "unsafe_acceptance_rate": metric["unsafe_acceptance_rate"],
            "false_blocking_rate": metric["false_blocking_rate"],
            "silent_acceptance_rate": metric["silent_acceptance_rate"],
            "median_total_microseconds": round(runtime["median_total_ns"] / 1000.0, 3),
            "overhead_ratio_vs_naive": round(runtime["overhead_ratio_vs_naive"], 6),
        })

    snapshot = {
        "schema_version": "article2-manuscript-snapshot-v1",
        "program": PROGRAM,
        "source_decision": decision["decision"],
        "source_evidence_digest_sha256": hashlib.sha256(
            json.dumps(source_hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "source_files_sha256": source_hashes,
        "benchmark": {
            "arm_count": len(arm_rows),
            "fault_count": len(benchmark["fault_specs"]),
            "control_count": metrics[FULL_ARM]["control_count"],
            "arms": arm_rows,
            "deterministic_digest_sha256": benchmark["deterministic_digest_sha256"],
        },
        "verification": {
            "scoped_line_coverage_rate": coverage["rate"],
            "covered_statements": coverage["covered_statements"],
            "total_statements": coverage["total_statements"],
            "semantic_branch_coverage_rate": benchmark["semantic_branch_coverage"]["rate"],
            "semantic_branches_covered": benchmark["semantic_branch_coverage"]["covered"],
            "semantic_branches_total": benchmark["semantic_branch_coverage"]["total"],
            "article2_unit_tests": unit["tests_run"],
            "existing_core_regression_tests": regression["tests_run"],
            "tests_total": unit["tests_run"] + regression["tests_run"],
            "core_adapters": len(adapters["adapters"]),
        },
        "environment": {"python": environment.get("python"), "platform": environment.get("platform")},
        "scientific_boundary": {
            "collector_rerun": decision.get("collector_rerun"),
            "article1_reestimated": decision.get("article1_reestimated"),
            "live_order_allowed": decision.get("live_order_allowed"),
        },
    }

    arm_fields = [
        "arm", "label", "fault_detection_rate", "unsafe_acceptance_rate", "false_blocking_rate",
        "silent_acceptance_rate", "median_total_microseconds", "overhead_ratio_vs_naive",
    ]
    arm_md_rows = [[
        row["label"], pct(row["fault_detection_rate"]), pct(row["unsafe_acceptance_rate"]),
        pct(row["false_blocking_rate"]), f'{row["median_total_microseconds"]:.3f}',
        f'{row["overhead_ratio_vs_naive"]:.2f}x',
    ] for row in arm_rows]
    arm_headers = ["Architecture", "Detection", "Unsafe acceptance", "False blocking", "Median (us)", "Overhead"]

    validation_rows = [
        {"item": "Controlled fault cases", "result": "12", "gate": "Frozen count", "status": "PASS"},
        {"item": "Clean controls per arm", "result": str(metrics[FULL_ARM]["control_count"]), "gate": "No false blocking", "status": "PASS"},
        {"item": "Semantic contract branches", "result": f'{benchmark["semantic_branch_coverage"]["covered"]}/{benchmark["semantic_branch_coverage"]["total"]}', "gate": "100%", "status": "PASS"},
        {"item": "Scoped executable statements", "result": f'{coverage["covered_statements"]}/{coverage["total_statements"]} ({pct(coverage["rate"])})', "gate": ">=80%", "status": "PASS"},
        {"item": "Article 2 unit tests", "result": f'{unit["tests_run"]}/{unit["tests_run"]}', "gate": "No failures or skips", "status": "PASS"},
        {"item": "Existing core regressions", "result": f'{regression["tests_run"]}/{regression["tests_run"]}', "gate": "No failures or skips", "status": "PASS"},
        {"item": "Core adapters", "result": f'{len(adapters["adapters"])}/{len(adapters["adapters"])}', "gate": "All pass", "status": "PASS"},
        {"item": "Deterministic reproduction", "result": reproducibility["digest_sha256"], "gate": "Stable digest", "status": "PASS"},
    ]
    validation_fields = ["item", "result", "gate", "status"]

    prose = f"""# Frozen Article 2 Results Prose

This file is generated from the verified evidence bundle. Do not edit reported values manually.

The benchmark compared three pre-specified architectures across {len(benchmark['fault_specs'])} isolated fault cases and {metrics[FULL_ARM]['control_count']} clean controls per arm. The naive latest-state arm detected {pct(metrics['NAIVE_LATEST_STATE']['fault_detection_rate'])} of injected faults and unsafely accepted {pct(metrics['NAIVE_LATEST_STATE']['unsafe_acceptance_rate'])}. The point-in-time fail-open arm detected {pct(metrics['POINT_IN_TIME_FAIL_OPEN']['fault_detection_rate'])}, but its unsafe-acceptance rate remained {pct(metrics['POINT_IN_TIME_FAIL_OPEN']['unsafe_acceptance_rate'])} because warnings did not block execution. The complete point-in-time, provenance-bound, fail-closed arm detected {pct(metrics[FULL_ARM]['fault_detection_rate'])}, reduced unsafe acceptance to {pct(metrics[FULL_ARM]['unsafe_acceptance_rate'])}, and produced {pct(metrics[FULL_ARM]['false_blocking_rate'])} false blocking across clean controls.

The complete arm's median runtime was {metrics[FULL_ARM]['runtime']['median_total_ns'] / 1000.0:.3f} microseconds for the 15-case microbenchmark, corresponding to {metrics[FULL_ARM]['runtime']['overhead_ratio_vs_naive']:.2f}x the naive arm. This relative overhead must be interpreted together with the sub-millisecond absolute runtime and must not be generalized to full historical backtests.

Verification covered {coverage['covered_statements']} of {coverage['total_statements']} scoped executable statements ({pct(coverage['rate'])}) and both pass and fail outcomes for all {benchmark['semantic_branch_coverage']['total']} frozen semantic contracts ({pct(benchmark['semantic_branch_coverage']['rate'])}). All {unit['tests_run']} Article 2 unit tests and {regression['tests_run']} existing core regression tests passed without skips. Both production-core adapters passed. Repeated runs reproduced digest `{benchmark['deterministic_digest_sha256']}`.

The experiment did not rerun the evidence collector, re-estimate Article 1 trading results, search for alpha, or permit broker, demo, paper, or live orders. Its inference is limited to controlled corruption detection in the frozen benchmark and the selected XAUUSD research-pipeline adapters.
"""

    outputs = {
        "article2_results_snapshot.json": json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
        "table_1_arm_metrics.csv": csv_text(arm_fields, arm_rows),
        "table_1_arm_metrics.md": markdown_table(arm_headers, arm_md_rows),
        "table_1_arm_metrics.tex": latex_table(arm_headers, arm_md_rows, "Controlled fault-injection results by architecture.", "tab:arm-metrics"),
        "table_2_validation_evidence.csv": csv_text(validation_fields, validation_rows),
        "table_2_validation_evidence.md": markdown_table(validation_fields, [[row[key] for key in validation_fields] for row in validation_rows]),
        "table_2_validation_evidence.tex": latex_table(validation_fields, [[row[key] for key in validation_fields] for row in validation_rows], "Software-verification evidence.", "tab:verification"),
        "figure_1_arm_safety_comparison.svg": arm_figure(arm_rows),
        "ARTICLE2_RESULTS_PROSE.md": prose,
    }
    written: list[Path] = []
    for name, content in outputs.items():
        path = output_dir / name
        path.write_text(content, encoding="utf-8")
        written.append(path)

    manifest = {
        "schema_version": "article2-manuscript-package-manifest-v1",
        "program": PROGRAM,
        "source_evidence_directory": evidence_dir.relative_to(root).as_posix(),
        "source_evidence_digest_sha256": snapshot["source_evidence_digest_sha256"],
        "files": [
            {"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": sha256_path(path)}
            for path in sorted(written)
        ],
    }
    manifest_path = output_dir / "package_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    written.append(manifest_path)

    sums_path = output_dir / "SHA256SUMS.txt"
    sums_path.write_text(
        "".join(f"{sha256_path(path)}  {path.relative_to(root).as_posix()}\n" for path in sorted(written)),
        encoding="utf-8",
    )
    written.append(sums_path)
    deterministic_zip(zip_path, root, written)
    sidecar = zip_path.with_suffix(zip_path.suffix + ".sha256")
    sidecar.write_text(f"{sha256_path(zip_path)}  {zip_path.name}\n", encoding="utf-8")

    return {
        "decision": "ARTICLE2_MANUSCRIPT_INPUTS_READY",
        "source_decision": decision["decision"],
        "output_directory": output_dir.relative_to(root).as_posix(),
        "zip": zip_path.relative_to(root).as_posix(),
        "zip_sha256": sha256_path(zip_path),
        "files": len(written),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--evidence-dir", default="artifacts/article2/article2_evidence_v1")
    parser.add_argument("--output-dir", default="artifacts/article2/article2_manuscript_v1")
    parser.add_argument("--zip-path", default="artifacts/article2/XAUUSD_ARTICLE2_MANUSCRIPT_INPUTS_V1.zip")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    try:
        result = build(
            root,
            (root / args.evidence_dir).resolve(),
            (root / args.output_dir).resolve(),
            (root / args.zip_path).resolve(),
        )
    except (OSError, ValueError) as exc:
        print(json.dumps({"decision": "BLOCK_ARTICLE2_MANUSCRIPT_INPUTS", "error": str(exc)}, indent=2))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
