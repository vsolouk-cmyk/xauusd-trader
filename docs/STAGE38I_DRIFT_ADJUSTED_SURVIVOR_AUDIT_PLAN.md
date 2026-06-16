# STAGE38I Drift-Adjusted Survivor Audit Plan

## Purpose

Stage38H showed that unconditional XAUUSD bull drift is strong enough to explain many positive forward-return diagnostics. Stage38I therefore performs a strict survivor audit across previous Stage38 context and overlay outputs.

The objective is not to discover a new signal. The objective is to decide whether any previous Stage38 candidate survives after subtracting the Stage38H drift reference.

## Inputs

Primary required input:

- `stage38h_bull_drift_summary`

Optional prior-stage inputs, used when present:

- `stage38e_macro_pass_gate_summary`
- `stage38f_gld_pass_gate_summary`
- `stage38g_exogenous_composite_gate_summary`
- `stage38e_macro_context_era_summary`
- `stage38f_gld_feature_context_summary`

## Reference drift

Stage38I uses `DAILY_ANCHOR` from Stage38H as the primary drift reference for horizons 24, 72, and 120 bars.

If a daily-anchor row is unavailable, it falls back to `H1_ALL`; if that is unavailable, the horizon is not assessed.

## Residual metric

For event-clock gate rows:

```text
drift_adjusted_event_clock_bps = event_clock_mean_bps - daily_anchor_long_mean_bps
```

For context-only rows without event-clock accounting:

```text
drift_adjusted_raw_bps = raw_context_mean_bps - daily_anchor_long_mean_bps
```

Context-only rows cannot be promoted. They can only be retained as watch annotations.

## Promotion discipline

A row can only become a strict watch candidate if all of the following are true:

```text
drift_adjusted_event_clock_bps >= 8.0
positive_year_count >= 4
worst_loo_event_clock_mean_bps > 5.0
max_positive_year_share <= 0.55
source_event_count >= 150
```

A row becomes a weak watch candidate if it has residual value but fails at least one robustness requirement.

All other rows remain `NO_PROMOTION`.

## Expected outcome

Based on Stage38F and Stage38G gate outputs, most rows are expected to fail because their event-clock uplift above baseline was small. Stage38I is mainly a kill-switch and sanity audit.

## Non-goals

Stage38I does not:

- create a trading strategy,
- tune thresholds,
- run ML,
- produce signals,
- promote to Stage39,
- create EA/paper/live logic.

## Go/no-go rule after Stage38I

If Stage38I has no strict pass rows, the Stage38 exogenous and session exploration branch should be archived as data/context only.

If a strict pass row exists, the next step is still only a narrow read-only retest design, not paper/live.
