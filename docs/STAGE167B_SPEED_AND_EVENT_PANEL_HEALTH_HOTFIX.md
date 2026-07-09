# Stage167B Speed and Event Panel Health Hotfix

## Purpose

Stage167B fixes two practical issues from the first Stage167 run:

1. Runtime was too long because the stage exported a full all-rule trade ledger by default.
2. The run was not truly event-aware because Stage166's intraday event panel had too little historical coverage for train-side event thresholds.

## What changed

- Adds an event-panel health gate before scanning rules.
- Fast-stops when event coverage is not trainable:
  - event panel rows below `--min-event-panel-rows`
  - train active event bars below `--min-train-active-event-bars`
  - train event thresholds collapse to zero
- Keeps the newest `--holdout-pct` segment as holdout.
- Uses faster vector-summary evaluation when the event panel is usable.
- Skips full `stage167_all_rule_trades.csv` export by default.
- Still writes scores, shortlist, top trades, summary JSON, and decision MD.

## Why this does not reduce decision quality

The default fast path does not loosen gates or remove cost/slippage logic. It only avoids writing a large audit ledger that is not needed for the commercial keep/kill decision. If full audit rows are required, run with `--export-all-rule-trades`.

## Expected result on the current Stage167 output

Given the observed Stage167 event panel had only a few rows and zero event thresholds, this hotfix should fast-stop with a decision similar to:

`STAGE167B_EVENT_PANEL_NOT_TRAINABLE_FAST_STOP_REBUILD_STAGE166_HISTORY_FIRST`

That is the correct commercial behavior: do not spend time scanning technical rules under a false event-aware label.

## Output files

- `stage167_event_aware_holdout_gate_summary.json`
- `stage167_all_rule_scores.csv`
- `stage167_commercial_shortlist.csv`
- `stage167_top_rule_trades.csv`
- `stage167_decision.md`
- `stage167_train_thresholds.json`
- `stage167_holdout_map.json`

## Full audit mode

Use this only when the score/decision is interesting enough to audit every generated trade:

```bash
--export-all-rule-trades
```

## Force scan mode

Use this only for debugging, not for commercial decisioning:

```bash
--force-scan-with-insufficient-event-panel
```
