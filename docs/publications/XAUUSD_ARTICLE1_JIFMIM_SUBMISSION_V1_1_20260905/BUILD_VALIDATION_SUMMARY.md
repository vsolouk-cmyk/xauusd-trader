# Build and validation summary

Technical validation status: PASS.

Submission-file status: READY. The supplied author identity, academic title, affiliation, postal address, university email, ORCID, funding statement, competing-interest statement, repository URL, and immutable repository commit are complete. Originality, CRediT, data-license, and exclusive-submission attestations remain actions for the corresponding author in Editorial Manager and cannot be machine-verified.

Checks completed on 2026-09-05:

- Official author-supplied Elsevier CAS 2.4 single-column template used.
- Five PDFs compiled with `latexmk -pdf -interaction=nonstopmode -halt-on-error`.
- No undefined citations, undefined references, or LaTeX errors in final logs.
- No content-generated overfull boxes. CAS 2.4 emits two or three environment-dependent 117.0831 pt internal front-matter notices at `\maketitle`; they do not produce visible overflow. The empty ORCID line is suppressed in files without a registered ORCID.
- The bibliography contains 42 cited journal articles, including 15 from 2023--2026; no bibliography entry is uncited and no citation key is unresolved.
- All 19 manuscript pages, 19 anonymized-manuscript pages, 9 supplement pages, 1 title page, and 1 cover-letter page rendered to PNG and visually inspected.
- All figures are legible vector PDFs with PNG previews and are reproducible from frozen CSV tables.
- Locked numerical checks passed: 47 registered, 39 primary, 8 forensic-only, 28,685 normalized records, positive means 24/9/5/1, 0 native passes, 0 supported families, 20 cross-feed applicable, 13 replication passes, 7 failures, 2 sign reversals, 0 DSR passes.
- The LaTeX source archive is flat and contains no subdirectories.
- ZIP CRC checks and SHA-256 package manifest checks passed.
- ORCID checksum and author-name resolution passed.
- The repository URL and commit were obtained from the audited local Git state; local and origin `main` both resolved to the referenced commit before the article files were committed.

The final build reports `PASS_JIFMIM_ARTICLE1_SUBMISSION_PACKAGE_READY`.
