# Stage38F Gold ETF Holdings / Flow Data Foundation Plan

## Purpose

Build a free or no-cost gold ETF holdings/flow data foundation for XAUUSD research.

This stage addresses a known data gap from earlier stages:

```text
ETF flow missing
```

The goal is not to create a trading signal immediately. The goal is to verify whether ETF holdings/flows are downloadable, stable, timestampable, and joinable to XAUUSD bars without lookahead.

## Current project state

```text
Stage38A / T1 = low-confidence 2025-dominated; no promotion
Stage38B / COT = data foundation success; edge not promotable
Stage38C / H1 baseline = weak; no promotion
Stage38D / M5/M15 session baseline = low-confidence; archived
Stage38E / macro-risk = data foundation success; gate watch-only; no promotion
Stage39 = NO_GO
EA / paper-live / live = NO_GO
```

## Candidate free sources

### Source A — World Gold Council global gold ETF holdings and flows

Use for global/regional gold ETF flow and holdings context.

Expected frequency:

```text
weekly / monthly website updates
monthly downloadable Excel file
```

Initial use:

```text
source_availability_audit only
```

Do not assume the XLSX download is stable until tested from both local machine and GitHub Actions.

### Source B — SPDR Gold Shares GLD official historical archive

Use for daily GLD historical archive / holdings-related information if accessible.

Initial use:

```text
source_availability_audit only
```

The source should be treated as GLD-specific, not global ETF flow.

## Source hierarchy

```text
Tier 1: Official WGC ETF holdings/flows XLSX
Tier 2: Official SPDR GLD historical archive XLSX/API
Tier 3: Public market-price proxies only if official flow/holding data is inaccessible
```

No unofficial proxy should be promoted as true ETF flow without explicit labeling.

## Stage38F first artifact

```text
app/stage38f_gold_etf_source_availability_audit.py
```

Responsibilities:

```text
1. Check WGC ETF page availability
2. Discover XLSX download links from WGC page
3. Attempt WGC XLSX download with normal browser-like headers
4. Check SPDR GLD page availability
5. Attempt SPDR historical archive download/API call
6. Save raw downloaded files if successful
7. Produce JSON and Markdown source audit reports
8. Make a clear local-vs-GitHub decision
```

## Expected outputs

```text
data/etf/gold/source_audit/raw/
data/reports/stage38f_gold_etf_source_availability_audit/stage38f_gold_etf_source_availability_audit.json
data/reports/stage38f_gold_etf_source_availability_audit/stage38f_gold_etf_source_availability_audit.md
```

## Decisions after source audit

```text
PASS_LOCAL:
    Build local downloader/parser.

BLOCKED_LOCAL_BUT_LIKELY_GITHUB:
    Build GitHub Actions workflow and artifact route.

NO_STABLE_SOURCE:
    Do not force ETF flow stage.
    Keep Stage38F as blocked data-gap note.
```

## Guardrails

```text
No strategy.
No backtest.
No optimizer.
No ML.
No Stage39.
No EA.
No paper-live.
No live order.
```

## Why this stage is still worth doing

Gold ETF holdings and flows are closer to institutional allocation pressure than pure price/session baselines. Since pure price/session/COT/macro gates have not produced a promotable edge, the next rational step is not more filtering of weak candidates; it is filling a remaining thesis-level data gap.
