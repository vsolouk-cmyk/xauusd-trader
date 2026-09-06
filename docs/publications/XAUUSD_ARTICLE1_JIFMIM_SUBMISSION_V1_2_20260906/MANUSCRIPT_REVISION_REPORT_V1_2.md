# Manuscript revision report - version 1.2

Date: 6 September 2026

## Scope

Version 1.2 is a full stylistic and methodological-presentation revision of the Article 1 manuscript. Numerical results, the registered strategy universe, source data, evaluation protocol, figures, and bibliography remain unchanged.

## Changes made

1. **Scholarly voice and sentence structure.** The Introduction, literature review, research design, Results, Discussion, limitations, and Conclusion were rewritten rather than locally paraphrased. Recurrent template-like contrasts, defensive qualifications, highly symmetrical lists, and repeated paragraph openings were reduced. The revised body contains no sentence beginning with `No` or `Not`.

2. **Negative sentence openings.** Negative findings are now expressed through their evidential subject, for example, `Every specification failed at least one source-native gate` and `Adjusted evidence remained weak across all 20 families`. This preserves the result without repeatedly opening sentences with a negation.

3. **Section 3 title.** `Research design, data, and locked protocol` was replaced by `Research design, data, and implementation`. The chronology and registry still explain the pre-execution lock, but the lock is no longer presented as a method in the section heading.

4. **Manual emphasis.** Author-added `\emph`, `\textit`, and `\textbf` commands were removed from the main article. Mathematical notation, code-status labels, journal-title styling outside the article, and formatting imposed by the Elsevier class remain unaffected.

5. **SHA values.** Long SHA-256 values were removed from the manuscript and supplementary narrative. Digests remain available in machine-readable manifests and provenance records, where they are useful for verification without disrupting the article's argument. The public repository is still identified in the non-anonymized data-availability statement.

6. **Research software.** The 143-word AI-centered subsection was replaced by a 470-word account of the research software and reproducibility architecture. It now explains the five source-specific strategy engines, registry builder, outcome-blind preflight, database and schema checks, normalized result contract, inference layer, cross-feed reconstruction, non-overwritable execution, structured outputs, and independent audit. A new table maps the software components to their functions and controls.

7. **AI disclosure.** The final AI declaration now concerns manuscript preparation only. The earlier discussion of code drafting, code review, diagnostics, and figure preparation was removed from that declaration. Elsevier's current policy asks authors to describe AI-assisted code development in the Methods section, so a short, neutral statement remains at the end of the software subsection. Scientific and software responsibilities remain assigned to the human author.

8. **Submission sources.** The package includes a separate flat anonymized LaTeX archive. It contains no author name, affiliation, email, ORCID, or repository identifier and is the only source archive suitable for an initial double-anonymized review if the submission system requires LaTeX sources.

## Validation contract

The package validator now fails if any of the following reappears:

- the former Section 3 title;
- missing software architecture text or table;
- manual emphasis commands in the main article;
- a 40- to 64-character hexadecimal identifier in the article or supplement;
- a manuscript-body sentence beginning with `No` or `Not`;
- code-development language in the final AI declaration; or
- omission of the research-code disclosure required in Methods.

Stylistic revision can improve authorship fidelity and readability, but no responsible workflow can guarantee the output of commercial AI-text detectors. The controlling standard for this version is a natural scholarly voice, factual fidelity to the research record, transparent disclosure, and line-by-line human author review before submission.
