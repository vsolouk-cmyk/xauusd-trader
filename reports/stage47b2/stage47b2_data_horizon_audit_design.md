# Stage47B2 — Data Horizon Audit Before Stage47B Rerun

## Reason

Stage47B finally executed successfully after LoaderFix5, but it loaded only 500 M5 candles and generated only 3 trades. That is enough to reject promotion, but not enough to judge the structural thesis.

## Purpose

This patch adds a bounded data-horizon audit before rerunning the liquidity-sweep reversal scan. It merges all matching normalized XAUUSD CSV files for the selected timeframe, deduplicates by timestamp, measures coverage, checks gap statistics, and writes an optional merged CSV for a clean Stage47B rerun.

## Guardrail

No rule tuning is introduced. This patch only checks whether the data horizon is large enough for the already-defined Stage47B scan.

## Output

- `reports/stage47b2/stage47b2_data_horizon_audit_summary.json`
- `reports/stage47b2/stage47b2_data_horizon_audit_report.md`
- optional merged CSV, e.g. `reports/stage47b2/stage47b2_merged_m5.csv`

## Status meanings

- `INSUFFICIENT_HISTORY_STOP_NO_PROMOTION`: do not rerun Stage47B as an evidentiary scan; collect/prepare more history first.
- `DATA_HORIZON_READY_FOR_STAGE47B_RERUN_NO_PROMOTION`: rerun Stage47B on the merged CSV, still with no promotion until the scan itself produces survivors.

No EA, paper-live, or live action is allowed from this audit.
