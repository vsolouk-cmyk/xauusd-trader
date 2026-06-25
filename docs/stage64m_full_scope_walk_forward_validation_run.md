# Stage64M - Full-Scope Walk-Forward Validation Run

Stage64M is the first full-scope no-order validation run after Stage64L. It evaluates only the predeclared Stage64L hypotheses on the Stage64K lag-safe feature dataset.

## Scope

Allowed:

- Read Stage64L validation design.
- Read Stage64K full-scope lag-safe feature dataset.
- Compute forward returns for the predeclared horizons.
- Evaluate only the predeclared benchmark and candidate rules.
- Apply corrected statistical gates and robustness gates.
- Write research reports.

Blocked:

- No order generation.
- No EA promotion.
- No broker connection.
- No paper-order, paper-live, or live.
- No historical event-calendar feature/filter/post-hoc exclusion.
- No reduced-scope retest, rescue filtering, or new intraday scan.

## Statistical comparison

Candidates are compared against the predeclared primary benchmark:

`H64L_B1_GOLD_TREND_ONLY_REFERENCE`

The script uses a standard-library Welch z approximation for the one-sided mean-excess test and applies Bonferroni correction over:

`candidate_count * horizon_count = 12`

This is intentionally conservative and remains research-only.

## Pass gates

A candidate/horizon can pass only if all gates pass:

- Mean excess versus primary benchmark is positive.
- Bonferroni-corrected one-sided p-value is below 0.05.
- Positive excess appears in at least 3 of 4 splits.
- Minimum active days are satisfied by horizon.
- Max split share of active days is no more than 0.45.
- Max calendar-year share of active days is no more than 0.40.
- No forbidden target/signal/validation/event-filter columns are present.

Even a corrected survivor does not authorize orders. It only allows Stage64N decision memo.
