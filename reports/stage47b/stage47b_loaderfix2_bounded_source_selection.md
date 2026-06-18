# Stage47B LoaderFix2: bounded source selection and no fixed repo path

## Purpose

This hotfix addresses two operational failures observed after Stage47B LoaderFix1:

1. The install/run instruction used a fixed repository path:

```text
~/Desktop/xauusd-research
```

The submitted project tree shows a valid repository root, but not necessarily at that path. Future instructions must not assume this fixed location.

2. Auto-discovery remained too DB-oriented. On this project layout the safest Stage47B source is the top-level normalized M5 CSV under:

```text
data/normalized/normalized_twelvedata_XAU_USD_5min_*.csv
```

SQLite paths exist, but they can include larger mixed-timeframe stores and can make the scan appear to hang if the table is large or not sharply filtered.

## LoaderFix2 changes

- Auto-discovery now prefers top-level normalized CSV by default.
- Auto-discovery is bounded and does not recurse through `archive`, `.git`, `.venv`, or the whole filesystem.
- Added `--debug-source` to print the selected source and exit without scanning.
- Added `--prefer-source csv|db`; default is `csv`.
- Added SQLite row safety via `--db-row-cap` and `--allow-large-db`.
- SQLite loading now attempts SQL-side filtering for timeframe/symbol when those columns exist.
- The recommended local run no longer requires a fixed `cd ~/Desktop/xauusd-research` path.

## Required boundary

This remains a research scan only:

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

No Stage47B result authorizes execution. Survivors, if any, can only move to Stage47C strict audit.
