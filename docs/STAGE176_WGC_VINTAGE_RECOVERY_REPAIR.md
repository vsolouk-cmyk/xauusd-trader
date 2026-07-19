# Stage176 WGC Vintage Recovery Repair

## Purpose

Repair the WGC original-publication collector without changing the locked Stage176 thesis, formulation, holdout, costs, baselines, or decision gates.

The first completed run produced `KILL_ASOF_DATA_CONTRACT_UNAVAILABLE`, but inspection showed that this was not yet a valid terminal data finding:

- 80 report roots were found and 96 numeric candidates were extracted;
- only 10 quarters entered the manifest;
- many pages exposed publication dates only as visible text, not metadata;
- report summaries mixed quarterly, year-to-date, and annual central-bank values;
- at least one accepted row was semantically wrong: 2016Q3 used the YTD value 271.1t instead of the quarter value 81.7t;
- older reports often keep the quarter value in the dedicated Central Banks section or original XLS/XLSX/PDF attachment.

## Changes

1. Visible-date publication fallback constrained to 10–180 days after quarter end.
2. Period-aware text scoring:
   - exact report-quarter references are preferred;
   - YTD, H1/H2, annual, and full-year values are penalized;
   - values for another explicit quarter are penalized.
3. Dedicated WGC Central Banks / official-sector section pages are discovered and preferred over report summaries.
4. Original attachments are recovered in this order:
   - XLSX;
   - XLS (converted with LibreOffice when available);
   - ZIP contents;
   - PDF with `pdftotext -layout`.
5. Spreadsheet extraction maps the central-bank row to the exact report-quarter column.
6. PDF tables use layout-column alignment to map the report quarter to the correct number.
7. WGC download endpoints receive Referer/Accept headers and a browser-like curl fallback.
8. Regional, Japanese, US-focus, and India-focus duplicates are excluded.
9. An existing failed manifest is automatically rebuilt; it no longer blocks online repair merely because the CSV exists.
10. Existing report-page cache is retained and reused.

## Hard controls unchanged

- No parameter grid.
- No threshold reoptimization.
- No ML.
- No paper/demo/live/order path.
- Latest revised WGC series cannot substitute for original-publication vintages.
- A failed rebuilt contract remains fail-closed.

## Install

```bash
cd ~/Downloads

mv xauusd_stage176_wgc_vintage_recovery_repair_patch.zip \
  ~/Desktop/xauusd-trader/

cd ~/Desktop/xauusd-trader

rm -rf _incoming_stage176_recovery
mkdir _incoming_stage176_recovery

unzip xauusd_stage176_wgc_vintage_recovery_repair_patch.zip \
  -d _incoming_stage176_recovery

rsync -a _incoming_stage176_recovery/ ./
rm -rf _incoming_stage176_recovery
rm xauusd_stage176_wgc_vintage_recovery_repair_patch.zip
```

## Test

```bash
cd ~/Desktop/xauusd-trader

python3 -m unittest \
  tests/test_stage176_central_bank_allocation_falsification.py
```

Expected:

```text
Ran 25 tests
OK
```

## Run

No manifest deletion is required. If the existing manifest fails, the repaired collector automatically rebuilds it from cached/original WGC publications.

```bash
cd ~/Desktop/xauusd-trader

python3 app/stage176_central_bank_allocation_falsification.py \
  --root ~/Desktop/xauusd-trader \
  --config configs/stage176_central_bank_allocation_falsification.json
```

Progress remains available at:

```text
reports/stage176_central_bank_allocation_falsification/stage176_progress.log
reports/stage176_central_bank_allocation_falsification/stage176_progress.json
```

## Expected behavior

Cached report pages should show `cache hit`. New section pages and attachments may be downloaded once and then cached under:

```text
data/macro_regime/vintages/wgc_gdt_original_report_pages/
data/macro_regime/vintages/wgc_gdt_original_report_attachments/
```

A valid run must either:

- pass the original-publication vintage contract and execute the allocation audit; or
- fail with a traceable list of quarters that still lack a defensible original-publication value.

Do not interpret the previous 10-row manifest or its `KILL_ASOF_DATA_CONTRACT_UNAVAILABLE` as a terminal thesis decision.

## Files to return

Always return:

```text
stage176_summary.json
stage176_decision.md
stage176_wgc_vintage_preflight.csv
stage176_wgc_extraction_candidates.csv
stage176_wgc_online_fetch_ledger.csv
```

If the audit runs, also return:

```text
stage176_gate_checks.csv
stage176_metrics.csv
stage176_episode_contributions.csv
stage176_1q_regime_test.json
stage176_2q_nonoverlap_test.json
```
