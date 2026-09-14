# XAUUSD Article 1 - JIFMIM submission package, version 1.1

This is the final-author-metadata build of a flat, compile-tested Elsevier CAS single-column submission directory. It contains the full and anonymized manuscripts, title page, cover letter, highlights, declarations, supplementary material, reproducible figures, frozen article-level result tables, and validation scripts. It was prepared from the official CAS 2.4 template supplied by the author.

## Author and repository metadata

The supplied name, academic title, institutional affiliation, postal address, university email, and ORCID are entered in `author_metadata.tex`. The repository URL and audited immutable commit are mirrored in `data_code_availability.txt`. The author reported no specific funding and no competing interest. No separate public profile URL was supplied. The originality and exclusive-submission attestations remain actions performed by the corresponding author in Editorial Manager; they are not machine-verifiable package metadata.

## Literature status

The literature review was substantively rewritten on 5 September 2026. The bibliography contains 42 cited journal articles, including 15 articles from 2023--2026. Recent evidence is integrated into the Introduction, Related literature, and Discussion rather than appended as an uncited list. See `RECENT_LITERATURE_UPDATE.md` for the verification and integration record.

## Build

```bash
./build_all.sh
```

The script rebuilds data figures and generated supplementary tables, compiles five PDFs, and runs fail-closed numerical and LaTeX checks.

## Editorial Manager files

- Manuscript: use `manuscript.pdf` unless the system explicitly requests anonymization.
- Anonymized manuscript: `manuscript_anonymized.pdf`.
- Title page: `title_page.pdf`.
- Highlights: `highlights.txt`.
- Supplement: `supplementary_material.pdf` and/or `supplementary_data.zip`.
- LaTeX sources: `JIFMIM_ARTICLE1_LATEX_SOURCE_FLAT.zip`.
- Cover letter: `cover_letter.pdf`.
- Declarations: the separate text files are provided in addition to the manuscript sections.

See `submission_upload_map.md` for the exact Editorial Manager item mapping and `publishing_route_note.md` for the zero-APC subscription route.

Elsevier's LaTeX workflow requires all source files at one folder level. The source archive is therefore flat and contains no subdirectories.

## Scientific status

The study is a retrospective systematic audit with a prospectively locked consolidated rerun. It is not a fully prospective experiment. The evidence supports `NO_EDGE_UNDER_LOCKED_PROTOCOL` for all 20 evaluated families; it does not prove universal gold-market efficiency or exclude every future strategy.
