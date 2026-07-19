# Stage176 — Central-Bank Accumulation Allocation Falsification

## Executive purpose

Stage176 is a single, time-boxed falsification of one causal thesis:

> Original-publication WGC official-sector purchases may identify a low-frequency gold allocation regime when high trailing accumulation is combined with a 200-trading-day price trend gate.

This is not an intraday strategy, a parameter scan, or an execution bridge. The prospective product is a quarterly decision-support engine with two research states:

```text
HIGH exposure = 1.0
LOW exposure  = 0.0
leverage      = forbidden
orders/demo/paper/live = forbidden
```

A successful result authorizes quarterly shadow reporting only.

## Why the data preflight is the first gate

The current WGC demand workbook is revised when new information becomes available. Using today's revised historical values as if they had been known at each past report date creates look-ahead.

Stage176 therefore accepts only one row per quarter backed by an original WGC Gold Demand Trends publication, publication timestamp and traceable source hash. The online collector attempts to create this manifest from the WGC report archive. If the archive cannot establish the contract, the audit stops.

Terminal data decision:

```text
KILL_ASOF_DATA_CONTRACT_UNAVAILABLE
```

It is forbidden to bypass this decision by substituting the latest revised XLSX.

## Locked formulation

The executable contains an immutable contract and verifies that the JSON config is byte-for-byte equivalent in meaning.

At every WGC quarterly report:

```text
trailing_4q_purchases = sum of the four quarterly values as originally published
prior_expanding_median = expanding median of trailing_4q values available before this report
trend_ok = last gold close available before release > 200-trading-day SMA
```

State transition:

```text
initial state = LOW

if quarterly purchases declined in two consecutive reports:
    state = LOW
elif trailing_4q_purchases > prior_expanding_median and trend_ok:
    state = HIGH
else:
    keep previous state
```

The state persists between reports. No missing condition is silently treated as an exit.

Availability:

```text
trend observation = last daily gold close on or before publication date
tradable date      = first complete daily bar strictly after publication date
```

This conservative convention prevents same-day publication leakage when only daily price bars are available.

## Fixed costs

```text
primary switching cost = 10 bps
stress switching cost  = 20 bps
```

A cost is charged only when exposure changes. No cost threshold is optimized.

## Fixed sample design

```text
minimum original quarters = 56
required start             = 2010Q1
maximum missing quarters   = 2
locked final holdout       = 20% of quarterly decision intervals
```

The last 20% is never used to alter the formulation.

## Baselines

All baselines use the same WGC decision dates and price source:

```text
1. Buy and hold / always HIGH
2. Price-only 200D allocation
3. Central-bank-only rule without the 200D trend gate — comparator only
4. Locked candidate: central-bank accumulation + 200D trend
```

The central-bank-only version is not selectable as an alternative candidate. It exists only to identify the incremental role of the trend gate.

## Horizon tests

Primary outcome is the non-overlapping return between consecutive WGC decision dates.

Additional tests:

```text
1-quarter HIGH versus LOW:
  deterministic one-sided permutation test

2-quarter HIGH versus LOW:
  two separate non-overlapping cohorts, starting on even and odd quarters
```

Two-quarter observations are never pooled as overlapping rows.

## Allocation / tail-catcher gates

Unlike a frequent mean-reversion strategy, profit need not be evenly distributed by month. The rule must instead show independent regime episodes.

Required:

```text
HIGH episodes in full sample >= 5
HIGH episodes occur in all three locked calendar eras:
  2010–2014, 2015–2019, 2020–2029
both HIGH and LOW states appear in holdout
holdout net return > 0
holdout candidate return > price-only 200D return
leave-one-episode-out median excess return > 0
one episode <= 70% of all positive excess return
1Q HIGH and LOW samples each >= 8
1Q HIGH-minus-LOW mean > 0 with one-sided permutation p <= 0.10
both non-overlapping 2Q cohort effects > 0
```

Risk/return target — at least one:

```text
A. Candidate Calmar exceeds buy-and-hold and price-only 200D

or

B. Candidate reduces buy-and-hold max drawdown by at least 25%
   while retaining at least 80% of buy-and-hold return
```

## Terminal decisions

```text
ALLOCATION_SHADOW_CANDIDATE
KILL_NO_INCREMENTAL_ALLOCATION_VALUE
KILL_ASOF_DATA_CONTRACT_UNAVAILABLE
INCONCLUSIVE_LOW_POWER_ESCALATE_PRODUCT_SCOPE
```

`INCONCLUSIVE_LOW_POWER_ESCALATE_PRODUCT_SCOPE` is terminal for this formulation. It does not authorize Stage176A/B/C, a threshold relaxation or automatic transition to GVZ.

## ML rule

```text
ML_ALLOWED_NOW = false
```

Conditional re-entry exists only if the locked causal baseline passes a multi-regime holdout. Then ML may be used only as an ON/OFF or interaction filter around the same mechanism. Direct price prediction remains outside scope.

## GDELT operation

The package removes the four-hour schedule from:

```text
.github/workflows/xauusd_stage166f_gdelt_backfill.yml
```

The workflow remains available through manual `workflow_dispatch` for bounded blackout-support investigations. It is no longer a scheduled alpha-feature pipeline.

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m unittest \
  tests/test_stage176_central_bank_allocation_falsification.py

python3 app/stage176_central_bank_allocation_falsification.py \
  --root ~/Desktop/xauusd-trader \
  --config configs/stage176_central_bank_allocation_falsification.json
```

Online WGC collection is enabled when no valid local manifest is found. It can also be requested explicitly:

```bash
python3 app/stage176_central_bank_allocation_falsification.py \
  --root ~/Desktop/xauusd-trader \
  --config configs/stage176_central_bank_allocation_falsification.json \
  --online
```

An explicit audited manifest may be supplied:

```bash
python3 app/stage176_central_bank_allocation_falsification.py \
  --root ~/Desktop/xauusd-trader \
  --config configs/stage176_central_bank_allocation_falsification.json \
  --vintage-manifest ~/Downloads/wgc_official_sector_quarterly_vintages.csv
```

## Outputs

Always produced:

```text
reports/stage176_central_bank_allocation_falsification/stage176_summary.json
reports/stage176_central_bank_allocation_falsification/stage176_decision.md
reports/stage176_central_bank_allocation_falsification/stage176_wgc_vintage_preflight.csv
reports/stage176_central_bank_allocation_falsification/stage176_gold_price_inventory.csv
```

When online collection runs:

```text
stage176_wgc_online_fetch_ledger.csv
stage176_wgc_extraction_candidates.csv
```

When both data contracts pass:

```text
stage176_decision_panel.csv
stage176_interval_returns.csv
stage176_metrics.csv
stage176_gate_checks.csv
stage176_episode_contributions.csv
stage176_1q_regime_test.json
stage176_2q_nonoverlap_test.json
```

## Exit codes

```text
0 = valid terminal research decision produced
2 = data contract, locked contract or fatal integration block
```

A data-contract exit code 2 must not be bypassed by changing locked thresholds.

## Files required for the next decision

Return these files:

```text
stage176_summary.json
stage176_decision.md
stage176_wgc_vintage_preflight.csv
stage176_gold_price_inventory.csv
```

If the audit ran, also return:

```text
stage176_gate_checks.csv
stage176_metrics.csv
stage176_episode_contributions.csv
stage176_1q_regime_test.json
stage176_2q_nonoverlap_test.json
```

## Progress and resumable collection

The Stage176 online WGC collector prints flushed progress events to the terminal and writes:

```text
reports/stage176_central_bank_allocation_falsification/stage176_progress.log
reports/stage176_central_bank_allocation_falsification/stage176_progress.json
```

The HTML cache remains under:

```text
data/macro_regime/vintages/wgc_gdt_original_report_pages/
```

Interrupting the process with `Ctrl+C` does not remove completed cached snapshots. A later run checks the cache before downloading each report again.

Watch the live log from a second terminal:

```bash
tail -f reports/stage176_central_bank_allocation_falsification/stage176_progress.log
```

Inspect the latest machine-readable checkpoint:

```bash
cat reports/stage176_central_bank_allocation_falsification/stage176_progress.json
```

Three consecutive index failures or eight consecutive report failures trigger a fail-closed circuit breaker instead of allowing hours of redundant retries. These values are operational controls only and do not alter the research formulation.
