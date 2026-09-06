#!/usr/bin/env python3
"""Fail-closed checks for central manuscript quantities and submission files."""
from __future__ import annotations

from pathlib import Path
import json
import re
import pandas as pd

ROOT = Path(__file__).resolve().parent


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    specs = pd.read_csv(ROOT / "specification_reference_metrics.csv")
    fam = pd.read_csv(ROOT / "family_reference_decisions.csv")
    cross = pd.read_csv(ROOT / "cross_feed_replication.csv")
    dsr = pd.read_csv(ROOT / "deflated_sharpe_ratio.csv")
    align = pd.read_csv(ROOT / "alignment_warning_sensitivity.csv")
    registry = pd.read_csv(ROOT / "locked_registry.csv")

    require(len(registry) == 47, "registry count")
    require((registry["primary_eligible"].astype(str).str.lower() == "true").sum() == 39, "primary count")
    require((registry["primary_eligible"].astype(str).str.lower() == "false").sum() == 8, "forensic count")
    require(len(specs) == 39 and specs["specification_id"].is_unique, "specification table")
    require(specs["trades"].sum() == 28685, "normalized row count")
    expected = [24, 9, 5, 1]
    cols = ["mean_gross_bps", "mean_normal_net_bps", "mean_severe_net_bps", "mean_fixed_stress_net_bps"]
    require([(specs[c] > 0).sum() for c in cols] == expected, "cost attrition")
    require(specs["source_native_pass"].astype(str).str.lower().eq("false").all(), "native pass count")
    require(len(fam) == 20 and fam["economic_family"].is_unique, "family table")
    require(fam["decision"].eq("NO_EDGE_UNDER_LOCKED_PROTOCOL").all(), "family decisions")
    require(abs(fam["family_adjusted_p"].min() - 0.4461107778444311) < 1e-12, "minimum family p")

    applicable = cross[cross["applicable"].astype(str).str.lower() == "true"]
    require(len(applicable) == 20, "cross-feed applicable")
    require(applicable["pass"].astype(str).str.lower().eq("true").sum() == 13, "cross-feed passes")
    require(applicable["pass"].astype(str).str.lower().eq("false").sum() == 7, "cross-feed failures")
    require((applicable["effect_direction_consistent"].astype(str).str.lower() == "false").sum() == 2, "sign reversals")

    require(len(dsr) == 39, "DSR row count")
    require(dsr["passes_0_95"].astype(str).str.lower().eq("false").all(), "DSR passes")
    require(abs(dsr["deflated_sharpe_probability"].max() - 0.011284134012404051) < 1e-15, "maximum DSR")
    applicable_align = align[align["applicable"].astype(str).str.lower() == "true"]
    require((applicable_align["effect_sign_changed"].astype(str).str.lower() == "false").all(), "alignment signs")
    require((applicable_align["source_native_pass_changed"].astype(str).str.lower() == "false").all(), "alignment native gates")

    for path in [
        "manuscript.pdf", "manuscript_anonymized.pdf", "supplementary_material.pdf",
        "title_page.pdf", "cover_letter.pdf", "figure1_cost_attrition.pdf",
        "figure2_severe_mean_vs_family_p.pdf", "figure3_cross_feed_replication.pdf",
    ]:
        require((ROOT / path).is_file() and (ROOT / path).stat().st_size > 1000, f"missing output: {path}")

    highlights = [line.strip() for line in (ROOT / "highlights.txt").read_text().splitlines() if line.strip()]
    require(3 <= len(highlights) <= 5, "highlight count")
    require(all(len(line) <= 85 for line in highlights), "highlight length")

    log_names = [
        "manuscript.log", "manuscript_anonymized.log", "supplementary_material.log",
        "title_page.log", "cover_letter.log",
    ]
    logs = "\n".join((ROOT / f).read_text(errors="replace") for f in log_names)
    bad = [r"LaTeX Warning: There were undefined references", r"Citation .* undefined", r"! LaTeX Error"]
    for pattern in bad:
        require(re.search(pattern, logs) is None, f"LaTeX validation failed: {pattern}")

    # Literature contract: the updated bibliography must remain fully integrated,
    # not merely enlarged with uncited entries.
    bib_text = (ROOT / "references.bib").read_text(encoding="utf-8")
    body_text = (ROOT / "manuscript_body.tex").read_text(encoding="utf-8")
    manuscript_text = (ROOT / "manuscript.tex").read_text(encoding="utf-8")
    anonymized_text = (ROOT / "manuscript_anonymized.tex").read_text(encoding="utf-8")
    supplement_text = (ROOT / "supplementary_material.tex").read_text(encoding="utf-8")
    ai_declaration = (ROOT / "ai_use_declaration.txt").read_text(encoding="utf-8")
    bib_entries = re.findall(r"@article\{([^,]+),", bib_text)
    cited_entries = []
    for group in re.findall(r"\\cite[tp]?\{([^}]+)\}", body_text):
        cited_entries.extend(key.strip() for key in group.split(","))
    years = [int(value) for value in re.findall(r"\byear\s*=\s*\{(\d{4})\}", bib_text)]
    require(len(bib_entries) == 42 and len(set(bib_entries)) == 42, "bibliography size or duplicate key")
    require(set(bib_entries) == set(cited_entries), "uncited or unresolved bibliography entry")
    require(sum(year >= 2023 for year in years) == 15, "recent-literature count")
    require(max(years) == 2026, "latest literature year")

    # Revision 1.2 style and disclosure contract. Long technical identifiers
    # remain in machine-readable manifests rather than the article narrative.
    main_article_sources = "\n".join([manuscript_text, anonymized_text, body_text])
    require(
        r"\section{Research design, data, and implementation}" in body_text,
        "revised Section 3 title",
    )
    require(
        r"\subsection{Research software and reproducibility architecture}" in body_text,
        "software architecture subsection",
    )
    require(r"\label{tab:software_architecture}" in body_text, "software architecture table")
    require(
        all(command not in main_article_sources for command in [r"\emph{", r"\textit{", r"\textbf{"]),
        "manual emphasis remains in main article",
    )
    require(
        re.search(r"\b[0-9a-fA-F]{40,64}\b", main_article_sources + "\n" + supplement_text) is None,
        "long hash remains in article narrative",
    )
    require(
        re.search(r"(?:^|[.!?]\s+)(?:No|Not)\b", body_text, flags=re.MULTILINE) is None,
        "negative sentence opening remains in manuscript body",
    )
    require("code" not in ai_declaration.lower(), "code-development language remains in AI declaration")
    require(
        "OpenAI ChatGPT was used for portions of code drafting and review" in body_text,
        "research-code disclosure missing from Methods",
    )

    # CAS 2.4 emits a fixed internal front-matter box warning. Depending on the
    # clean-build state, the blinded front matter can emit zero or one copy even
    # after its empty ORCID line is suppressed. Constrain each CAS document to
    # its observed safe range and reject every other overfull-box width.
    cas_frontmatter_warnings = 0
    allowed_cas_warning_counts = {
        "manuscript.log": (1, 1),
        "manuscript_anonymized.log": (0, 1),
        "supplementary_material.log": (0, 1),
        "title_page.log": (0, 0),
        "cover_letter.log": (0, 0),
    }
    for log_name in log_names:
        log_text = (ROOT / log_name).read_text(errors="replace")
        widths = [float(v) for v in re.findall(r"Overfull \\hbox \(([0-9.]+)pt too wide\)", log_text)]
        for width in widths:
            require(abs(width - 117.0831) < 0.01, f"unexpected content overflow in {log_name}: {width}pt")
            cas_frontmatter_warnings += 1
        lower, upper = allowed_cas_warning_counts[log_name]
        require(lower <= len(widths) <= upper, f"unexpected CAS front-matter warning count in {log_name}")

    metadata_text = (ROOT / "author_metadata.tex").read_text(encoding="utf-8")
    pending_markers = []
    for line in metadata_text.splitlines():
        if "TO BE COMPLETED" in line or "TO BE CONFIRMED" in line:
            macro = re.search(r"\\newcommand\{\\([^}]+)\}", line)
            marker = "TO BE COMPLETED" if "TO BE COMPLETED" in line else "TO BE CONFIRMED"
            pending_markers.append(f"{macro.group(1) if macro else 'metadata'}: {marker}")
    metadata_values = dict(re.findall(r"\\newcommand\{\\([^}]+)\}\{([^}]*)\}", metadata_text))
    for required_name in ["RepositoryURL", "RepositoryCommit"]:
        if not metadata_values.get(required_name, "").strip():
            pending_markers.append(f"{required_name}: EMPTY")
    orcid = metadata_values.get("AuthorORCID", "").replace("-", "")
    require(re.fullmatch(r"\d{15}[\dX]", orcid) is not None, "ORCID format")
    orcid_total = 0
    for digit in orcid[:-1]:
        orcid_total = (orcid_total + int(digit)) * 2
    orcid_result = (12 - (orcid_total % 11)) % 11
    orcid_check = "X" if orcid_result == 10 else str(orcid_result)
    require(orcid_check == orcid[-1], "ORCID checksum")
    require(re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", metadata_values.get("RepositoryURL", "")) is not None, "repository URL")
    require(re.fullmatch(r"[0-9a-f]{40}", metadata_values.get("RepositoryCommit", "")) is not None, "repository commit")
    pending_markers = sorted(set(pending_markers))
    submission_ready = len(pending_markers) == 0

    report = {
        "decision": (
            "PASS_JIFMIM_ARTICLE1_SUBMISSION_PACKAGE_READY"
            if submission_ready
            else "PASS_TECHNICAL_VALIDATION_BLOCKED_PENDING_AUTHOR_METADATA"
        ),
        "technical_validation_pass": True,
        "submission_ready": submission_ready,
        "pending_author_metadata_markers": pending_markers,
        "registry": {"all": 47, "primary": 39, "forensic_only": 8},
        "primary_records": 28685,
        "positive_means": dict(zip(cols, expected)),
        "native_passes": 0,
        "supported_families": 0,
        "cross_feed": {"applicable": 20, "pass": 13, "fail": 7, "sign_reversals": 2},
        "generated_pdfs": 5,
        "literature": {
            "cited_journal_articles": 42,
            "articles_2023_2026": 15,
            "latest_year": 2026,
            "uncited_entries": 0,
        },
        "revision_v1_2": {
            "section_3_title_revised": True,
            "software_architecture_subsection_present": True,
            "software_architecture_table_present": True,
            "manual_emphasis_commands_in_main_article": 0,
            "long_hash_values_in_article_and_supplement": 0,
            "negative_sentence_openings_in_manuscript_body": 0,
            "code_development_mentioned_in_ai_declaration": False,
            "research_code_disclosure_in_methods": True,
        },
        "author_metadata": {
            "orcid": metadata_values.get("AuthorORCID"),
            "orcid_checksum_pass": True,
            "repository_url": metadata_values.get("RepositoryURL"),
            "repository_commit": metadata_values.get("RepositoryCommit"),
        },
        "editorial_attestations_not_machine_verifiable": [
            "CRediT roles",
            "originality and exclusive submission",
            "third-party raw-data licensing status",
        ],
        "latex_content_overflow_warnings": 0,
        "cas_class_frontmatter_warnings": cas_frontmatter_warnings,
    }
    (ROOT / "validation_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
