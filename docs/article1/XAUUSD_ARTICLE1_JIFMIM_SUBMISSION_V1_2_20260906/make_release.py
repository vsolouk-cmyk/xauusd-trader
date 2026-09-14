#!/usr/bin/env python3
"""Create deterministic, flat journal source/data archives and the full handoff ZIP."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parent
RELEASE_NAME = "XAUUSD_ARTICLE1_JIFMIM_COMPLETE_SUBMISSION_PACKAGE_V1_2_20260906.zip"
SOURCE_NAME = "JIFMIM_ARTICLE1_LATEX_SOURCE_FLAT.zip"
ANON_SOURCE_NAME = "JIFMIM_ARTICLE1_LATEX_SOURCE_ANONYMIZED_FLAT.zip"
DATA_NAME = "supplementary_data.zip"
MANIFEST_NAME = "PACKAGE_MANIFEST_SHA256.txt"

SOURCE_FILES = [
    "author_metadata.tex", "manuscript.tex", "manuscript_anonymized.tex",
    "manuscript_body.tex", "supplementary_material.tex", "title_page.tex",
    "cover_letter.tex", "references.bib", "manuscript.bbl",
    "manuscript_anonymized.bbl", "cas-sc.cls", "cas-common.sty",
    "cas-model2-names.bst", "figure1_cost_attrition.pdf",
    "figure2_severe_mean_vs_family_p.pdf", "figure3_cross_feed_replication.pdf",
    "supp_registry_table.tex", "supp_spec_table.tex", "supp_family_table.tex",
    "supp_crossfeed_table.tex", "supp_alignment_table.tex", "supp_dsr_table.tex",
]

ANON_SOURCE_FILES = [
    "manuscript_anonymized.tex", "manuscript_body.tex", "references.bib",
    "manuscript_anonymized.bbl", "cas-sc.cls", "cas-common.sty",
    "cas-model2-names.bst", "figure1_cost_attrition.pdf",
    "figure2_severe_mean_vs_family_p.pdf", "figure3_cross_feed_replication.pdf",
]

DATA_FILES = [
    "specification_reference_metrics.csv", "family_reference_decisions.csv",
    "cross_feed_replication.csv", "alignment_warning_sensitivity.csv",
    "deflated_sharpe_ratio.csv", "locked_registry.csv",
    "publication_results_summary.csv", "evaluation_protocol.json",
    "data_contract_decision.json", "protocol_deviation_log.json",
    "independent_audit_report.json", "figure_manifest.json",
    "validation_report.json", "build_figures.py", "validate_package.py",
]

PACKAGE_FILES = [
    "README.md", "author_completion_checklist.md", "journal_compliance_matrix.md",
    "submission_upload_map.md", "publishing_route_note.md",
    "RECENT_LITERATURE_UPDATE.md", "MANUSCRIPT_REVISION_REPORT_V1_2.md",
    "BUILD_VALIDATION_SUMMARY.md", "author_metadata.tex", "manuscript.tex",
    "manuscript_anonymized.tex", "manuscript_body.tex", "references.bib",
    "supplementary_material.tex", "title_page.tex", "cover_letter.tex",
    "manuscript.bbl", "manuscript_anonymized.bbl",
    "highlights.txt", "ai_use_declaration.txt", "declaration_of_interest.txt",
    "data_code_availability.txt", "manuscript.pdf", "manuscript_anonymized.pdf",
    "supplementary_material.pdf", "title_page.pdf", "cover_letter.pdf",
    "figure1_cost_attrition.pdf", "figure2_severe_mean_vs_family_p.pdf",
    "figure3_cross_feed_replication.pdf", "figure1_cost_attrition.png",
    "figure2_severe_mean_vs_family_p.png", "figure3_cross_feed_replication.png",
    "figure_manifest.json", "build_figures.py", "build_all.sh",
    "validate_package.py", "verify_package_manifest.py", "make_release.py",
    "github_repository_audit.sh", "manuscript.log", "manuscript_anonymized.log",
    "supplementary_material.log", "title_page.log", "cover_letter.log",
    "cas-sc.cls", "cas-common.sty", "cas-model2-names.bst",
    "supp_registry_table.tex", "supp_spec_table.tex", "supp_family_table.tex",
    "supp_crossfeed_table.tex", "supp_alignment_table.tex", "supp_dsr_table.tex",
    *DATA_FILES[:13], SOURCE_NAME, ANON_SOURCE_NAME, DATA_NAME, MANIFEST_NAME,
]


def require_files(names: list[str]) -> None:
    missing = [name for name in names if not (ROOT / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing release files: {missing}")


def write_zip(path: Path, names: list[str], prefix: str = "") -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name in names:
            source = ROOT / name
            arcname = f"{prefix}{name}" if prefix else name
            zf.write(source, arcname=arcname)


def digest(path: Path) -> str:
    h = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    require_files(SOURCE_FILES + ANON_SOURCE_FILES + DATA_FILES)
    write_zip(ROOT / SOURCE_NAME, SOURCE_FILES)
    write_zip(ROOT / ANON_SOURCE_NAME, ANON_SOURCE_FILES)
    write_zip(ROOT / DATA_NAME, DATA_FILES)

    manifest_targets = [name for name in PACKAGE_FILES if name != MANIFEST_NAME]
    require_files(manifest_targets)
    manifest_lines = [f"{digest(ROOT / name)}  {name}" for name in sorted(set(manifest_targets))]
    (ROOT / MANIFEST_NAME).write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")

    require_files(PACKAGE_FILES)
    release_path = ROOT.parent / RELEASE_NAME
    write_zip(release_path, sorted(set(PACKAGE_FILES)), prefix=ROOT.name + "/")

    with zipfile.ZipFile(ROOT / SOURCE_NAME) as zf:
        if any("/" in name.rstrip("/") for name in zf.namelist()):
            raise AssertionError("LaTeX source archive is not flat")
        if zf.testzip() is not None:
            raise AssertionError("LaTeX source archive CRC failure")
    with zipfile.ZipFile(ROOT / ANON_SOURCE_NAME) as zf:
        if any("/" in name.rstrip("/") for name in zf.namelist()):
            raise AssertionError("Anonymized LaTeX source archive is not flat")
        if zf.testzip() is not None:
            raise AssertionError("Anonymized LaTeX source archive CRC failure")
    with zipfile.ZipFile(ROOT / DATA_NAME) as zf:
        if zf.testzip() is not None:
            raise AssertionError("Supplementary data archive CRC failure")
    with zipfile.ZipFile(release_path) as zf:
        if zf.testzip() is not None:
            raise AssertionError("Release archive CRC failure")

    print(f"RELEASE={release_path}")
    print(f"SHA256={digest(release_path)}")
    print(f"SIZE_BYTES={release_path.stat().st_size}")
    print(f"SOURCE_FILES={len(SOURCE_FILES)}")
    print(f"ANON_SOURCE_FILES={len(ANON_SOURCE_FILES)}")
    print(f"PACKAGE_FILES={len(set(PACKAGE_FILES))}")


if __name__ == "__main__":
    main()
