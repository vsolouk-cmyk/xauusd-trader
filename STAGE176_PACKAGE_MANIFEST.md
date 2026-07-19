# Stage176 Package Manifest

## Package

```text
xauusd_stage176_central_bank_allocation_falsification_patch.zip
```

## Purpose

One time-boxed historical-as-of falsification of a quarterly central-bank accumulation gold allocation engine.

The package:

1. collects or validates original WGC Gold Demand Trends quarterly publication vintages;
2. rejects latest-revised historical substitution;
3. resolves one full-coverage daily gold price source;
4. runs the locked accumulation + 200D trend allocation rule;
5. compares it with buy-and-hold, price-only 200D and central-bank-only comparators;
6. applies non-overlapping horizon, episode, holdout, cost and drawdown gates;
7. issues one terminal program decision;
8. removes the scheduled GDELT four-hour refresh while retaining manual dispatch.

## Files

```text
app/stage176_central_bank_allocation_falsification.py
configs/stage176_central_bank_allocation_falsification.json
tests/test_stage176_central_bank_allocation_falsification.py
docs/STAGE176_CENTRAL_BANK_ALLOCATION_FALSIFICATION.md
docs/STAGE176_WGC_VINTAGE_INPUT_CONTRACT.md
docs/STAGE176_PRODUCT_SCOPE_DECISION.md
data/templates/stage176_wgc_official_sector_vintage_manifest_template.csv
.github/workflows/xauusd_stage166f_gdelt_backfill.yml
STAGE176_PACKAGE_MANIFEST.md
```

## Hard controls

```text
orders/demo/paper/live = forbidden
ML_ALLOWED_NOW = false
broad scan = forbidden
parameter grid = forbidden
threshold reoptimization = forbidden
leverage = forbidden
```

## Terminal decisions

```text
ALLOCATION_SHADOW_CANDIDATE
KILL_NO_INCREMENTAL_ALLOCATION_VALUE
KILL_ASOF_DATA_CONTRACT_UNAVAILABLE
INCONCLUSIVE_LOW_POWER_ESCALATE_PRODUCT_SCOPE
```

## Validation completed before delivery

```text
Python compile: PASS
Unit tests: 11/11 PASS
Synthetic historical-as-of end-to-end run: PASS
Latest-revised WGC manifest rejection: PASS
WGC original-source hash traceability: PASS
No same-day price leakage: PASS
Persistent state and two-quarter-decline exit: PASS
Non-overlapping 2Q cohorts: PASS
Locked-contract mutation rejection: PASS
MT5 <DATE> + <TIME> price schema: PASS
GDELT workflow schedule removal: PASS
Clean ZIP extraction, compile, tests and smoke rerun: PASS
```

## Expected outputs

```text
reports/stage176_central_bank_allocation_falsification/stage176_summary.json
reports/stage176_central_bank_allocation_falsification/stage176_decision.md
reports/stage176_central_bank_allocation_falsification/stage176_wgc_vintage_preflight.csv
reports/stage176_central_bank_allocation_falsification/stage176_gold_price_inventory.csv
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
