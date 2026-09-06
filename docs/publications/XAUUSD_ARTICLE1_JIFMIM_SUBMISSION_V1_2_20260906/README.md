# XAUUSD Article 1 - JIFMIM submission package, version 1.2

This is the revised, final-author-metadata build of a flat, compile-tested Elsevier CAS single-column submission directory. It contains the full and anonymized manuscripts, title page, cover letter, highlights, declarations, supplementary material, reproducible figures, frozen article-level result tables, and validation scripts. It was prepared from the official CAS 2.4 template supplied by the author.

## Author and repository metadata

The supplied name, academic title, institutional affiliation, postal address, university email, and ORCID are entered in `author_metadata.tex`. The repository URL and audited research-snapshot commit are retained in the author metadata; the readable availability statement links to the repository without printing a long commit identifier in the article. The author reported no specific funding and no competing interest. No separate public profile URL was supplied. The originality and exclusive-submission attestations remain actions performed by the corresponding author in Editorial Manager; they are not machine-verifiable package metadata.

## Literature status

The literature review was substantively rewritten on 5 September 2026 and the full prose was revised again on 6 September 2026. The bibliography contains 42 cited journal articles, including 15 articles from 2023--2026. Recent evidence is integrated into the Introduction, Related literature, and Discussion rather than appended as an uncited list. See `RECENT_LITERATURE_UPDATE.md` for the verification and integration record and `MANUSCRIPT_REVISION_REPORT_V1_2.md` for the prose and methods revision.

## Build

```bash
./build_all.sh
```

The script rebuilds data figures and generated supplementary tables, compiles five PDFs, and runs fail-closed numerical and LaTeX checks.

After extracting the complete release ZIP, verify every packaged file and archive without rebuilding:

```bash
python3 verify_package_manifest.py
```

## Editorial Manager files

- Manuscript for initial double-anonymized review: `manuscript_anonymized.pdf`.
- Named manuscript for the author archive or a later production request: `manuscript.pdf`.
- Title page: `title_page.pdf`.
- Highlights: `highlights.txt`.
- Supplement: `supplementary_material.pdf` and/or `supplementary_data.zip`.
- Anonymized LaTeX sources for a blinded source-code upload: `JIFMIM_ARTICLE1_LATEX_SOURCE_ANONYMIZED_FLAT.zip`.
- Complete named LaTeX sources for the author archive or production: `JIFMIM_ARTICLE1_LATEX_SOURCE_FLAT.zip`.
- Cover letter: `cover_letter.pdf`.
- Declarations: the separate text files are provided in addition to the manuscript sections.

See `submission_upload_map.md` for the exact Editorial Manager item mapping and `publishing_route_note.md` for the zero-APC subscription route.

Elsevier's LaTeX workflow requires all source files at one folder level. The source archive is therefore flat and contains no subdirectories.

## Scientific status

The study is a retrospective systematic audit whose consolidated evaluation was fixed before execution. It is not a fully prospective experiment. None of the 20 evaluated families produced a strategy that survived the complete statistical and economic assessment. This result neither proves universal gold-market efficiency nor excludes every future strategy.
