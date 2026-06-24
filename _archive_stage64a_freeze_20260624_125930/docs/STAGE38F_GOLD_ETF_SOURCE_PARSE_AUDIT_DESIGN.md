# Stage38F Gold ETF Source Parse Audit Design

## Status

Stage38F source availability audit found usable ETF sources and should proceed to parse audit before any normalized loader is written.

## Source availability result

- WGC page: PASS
- WGC XLSX candidate 1: FAIL, HTTP 403
- WGC XLSX candidate 2: PASS
- SPDR GLD page: PASS
- SPDR GLD historical archive XLSX: PASS

## Decision

```text
STAGE38F_SOURCE_AVAILABILITY = PASS
NEXT_STEP = XLSX_PARSE_AUDIT
NORMALIZED_ETF_LOADER = NOT_YET
BASELINE / STRATEGY / STAGE39 / EA / PAPER-LIVE / LIVE = NO-GO
```

## Why parse audit is required

ETF files are not guaranteed to have stable sheet names, header rows, or column names. The next step must inspect workbook structure before writing a loader.

The parse audit must answer:

1. Which downloaded XLSX files are readable?
2. Which sheets contain usable date-like rows?
3. Which sheets contain ETF holdings or flow-like numeric columns?
4. Is SPDR GLD usable as a single-fund daily proxy?
5. Is WGC usable as a broad gold ETF flow/holdings source?
6. Which source should be normalized first?

## Parse audit constraints

- Read-only.
- No strategy or baseline logic.
- No trading signal.
- No Stage39.
- No paper-live or live order.
- No dependency on a fixed workbook schema.
- Use local raw files produced by the Stage38F source availability audit.

## Expected outputs

SQLite tables:

```text
stage38f_etf_source_parse_sheet_audit
stage38f_etf_source_parse_audit
```

Reports:

```text
data/reports/stage38f_gold_etf_source_parse_audit/stage38f_gold_etf_source_parse_audit.json
data/reports/stage38f_gold_etf_source_parse_audit/stage38f_gold_etf_source_parse_audit.md
```

## Promotion rule

A source can proceed to loader design only if the parse audit finds at least one sheet with:

```text
- valid readable workbook
- enough non-empty rows
- date-like values
- flow/holding/ETF/GLD/gold-related keyword evidence
- plausible numeric columns
```

## Preferred next step after parse audit

If SPDR historical archive is clean and WGC is less stable, build GLD loader first.

If WGC workbook has clear global ETF flow/holding tables, build WGC broad ETF loader first and use SPDR GLD as cross-check.

If both are usable, use this order:

```text
1. SPDR GLD daily holdings loader
2. WGC broad gold ETF monthly/weekly loader
3. H1 anti-lookahead join
4. ETF context diagnostic
```
