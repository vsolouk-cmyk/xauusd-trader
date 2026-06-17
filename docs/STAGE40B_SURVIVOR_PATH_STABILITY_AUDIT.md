# STAGE40B_SURVIVOR_PATH_STABILITY_AUDIT

## Scope

Stage40B is a dedicated research-only audit for strict survivors from `Stage40_PARALLEL_THESIS_MEGASCAN`.

It is not a promotion gate.

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

## Input

Expected inputs:

```text
reports/stage40/stage40_parallel_thesis_megascan_summary.json
reports/stage40/stage40_parallel_thesis_megascan_events.csv
reports/stage40/stage40_parallel_thesis_megascan_summary.csv  # optional but preferred if present
```

The script selects only rows classified as:

```text
STRICT_PARALLEL_THESIS_WATCH_ONLY_NO_PROMOTION
```

Soft rows are not promoted and are not extended with filters.

## What Stage40B audits

For each strict Stage40 survivor, Stage40B performs:

- full event-path recheck;
- train / OOS chronological split;
- first-half / second-half split;
- Q1/Q2/Q3/Q4 stability;
- worst-quarter cost and slippage-16 survival;
- bootstrap mean confidence check;
- year/month/session/hour bucket diagnostics when the event rows expose these fields;
- top-win concentration check;
- MAE / stop-touch risk check.

## Decision labels

```text
STRICT_STAGE40B_SURVIVOR_WATCH_ONLY_NO_PROMOTION
```

The rule remains research-watch only and can proceed to a separate execution-feasibility / lower-timeframe confirmation audit.

```text
RECENCY_OR_CONCENTRATION_WATCH_ONLY_NO_PROMOTION
```

The rule still has positive behavior but is too dominated by recent/OOS, Q4, or a small number of wins.

```text
FAIL_STAGE40B_SURVIVOR_AUDIT_NO_PROMOTION
```

The survivor fails the dedicated audit. Archive it; do not add filters to rescue it.

## Important rule

If Stage40B has zero strict survivors, archive Stage40. Do not create Stage40C by adding filters to a failed or soft row.
