# Build and validation summary

Technical validation status: PASS.

Submission status: BLOCKED only by the final GitHub URL/commit and the funding, competing-interest, authorship, and exclusive-submission confirmations listed in `author_completion_checklist.md`. The supplied author identity, academic title, affiliation, postal address, and university email are complete.

Checks completed on 2026-09-05:

- Official author-supplied Elsevier CAS 2.4 single-column template used.
- Five PDFs compiled with `latexmk -pdf -interaction=nonstopmode -halt-on-error`.
- No undefined citations, undefined references, or LaTeX errors in final logs.
- No content-generated overfull boxes; the three remaining 117.0831 pt notices are the identical empty front-matter box emitted by CAS 2.4 at `\maketitle` and do not produce visible overflow.
- The bibliography contains 42 cited journal articles, including 15 from 2023--2026; no bibliography entry is uncited and no citation key is unresolved.
- All 19 manuscript pages, 19 anonymized-manuscript pages, 9 supplement pages, 1 title page, and 1 cover-letter page rendered to PNG and visually inspected.
- All figures are legible vector PDFs with PNG previews and are reproducible from frozen CSV tables.
- Locked numerical checks passed: 47 registered, 39 primary, 8 forensic-only, 28,685 normalized records, positive means 24/9/5/1, 0 native passes, 0 supported families, 20 cross-feed applicable, 13 replication passes, 7 failures, 2 sign reversals, 0 DSR passes.
- The LaTeX source archive is flat and contains no subdirectories.
- ZIP CRC checks and SHA-256 package manifest checks passed.

After inserting the GitHub URL and commit and confirming the declarations in `author_metadata.tex`, run `./build_all.sh` and then `python3 make_release.py`. A fully ready build reports `PASS_JIFMIM_ARTICLE1_SUBMISSION_PACKAGE_READY`.
