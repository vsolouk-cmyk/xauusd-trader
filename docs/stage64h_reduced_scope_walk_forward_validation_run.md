# Stage64H - Reduced-Scope Walk-Forward Validation Run

Stage64H is the first authorized reduced-scope validation run after Stage64G. It remains a no-order, no-promotion research stage.

## Inputs

- `data/macro_regime/normalized/stage64f_reduced_scope_lag_safe_feature_dataset.csv`
- `reports/stage64g_walk_forward_validation_design/stage64g_walk_forward_validation_design_summary.json`
- `configs/stage64h_reduced_scope_walk_forward_validation_run.json`

## Scope

The validation scope is the Stage64E/Stage64G predeclared reduced scope:

- gold proxy daily OHLC features
- DXY daily trend/acceleration features
- real-yield daily pressure feature
- VIX daily volatility-regime feature

Excluded from this run:

- ETF holdings/flows
- central-bank demand regime
- historical event-calendar risk
- broker/spot XAUUSD D1 backfill

## Predeclared hypotheses

Benchmarks:

- `H64G_B0_ALWAYS_LONG_REFERENCE`
- `H64G_B1_GOLD_TREND_ONLY_REFERENCE`

Candidates:

- `H64G_H1_MACRO_TAILWIND_TREND_LONG`
- `H64G_H2_HEADWIND_AVOID_LONG_FILTER`
- `H64G_H3_VOL_SHOCK_SUPPRESSED_MACRO_LONG`

Horizons:

- 5 trading days
- 10 trading days
- 20 trading days

Multiple-testing correction:

- Bonferroni over `3 candidate hypotheses * 3 horizons = 9` tests.

## What Stage64H does

- Reads the feature-only dataset.
- Computes forward gold proxy returns for fixed horizons.
- Applies only the predeclared benchmark and candidate rules.
- Reports overall and split-level metrics.
- Applies corrected feasibility gates.
- Produces a no-order decision memo.

## What Stage64H does not do

- It does not create signals for execution.
- It does not connect to a broker.
- It does not authorize paper-order, paper-live, live, or EA promotion.
- It does not claim full macro-regime thesis validation.
- It does not optimize parameters or search new filters.

## Output files

- `stage64h_validation_results.csv`
- `stage64h_split_results.csv`
- `stage64h_candidate_decisions.csv`
- `stage64h_signal_sample.csv`
- `stage64h_reduced_scope_walk_forward_validation_summary.json`
- `stage64h_reduced_scope_walk_forward_validation_report.md`

## Decision discipline

A corrected feasibility survivor is not a tradable strategy. It only allows independent confirmation or broker/spot proxy alignment work. If no corrected survivor exists, the reduced-scope path must move to kill/redesign/data-completion decision.
