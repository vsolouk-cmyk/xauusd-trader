# Stage39B_EVENT_PATH_AND_TRADABILITY_DIAGNOSTIC

## Scope

```text
scope = RESEARCH_STAGE_ONLY_NO_PROMOTION
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

Stage39B is the allowed follow-up only because Stage39A produced strict research-watch rows. It is not a promotion stage.

## Stage39A audit basis

Stage39A produced:

```text
STRICT_RESEARCH_WATCH_ONLY_NO_PROMOTION = 4
WATCH_ONLY_BENCHMARK_RESIDUAL_NO_PROMOTION = 2
FAIL_BENCHMARK_RESEARCH_ONLY = 157
INSUFFICIENT_EVENTS_RESEARCH_ONLY = 17
```

The strict rows are still weak in tradability terms because their H1 benchmark + cost residuals are small relative to intrahorizon adverse excursion:

```text
BB_LOWER_REV_LONG_W120_K2.5 / 72H      residual ≈ +12.93 bps, median MAE ≈ -88.41 bps
RANGE_BOTTOM_REV_LONG_W48_Q0.05 / 72H  residual ≈ +8.96 bps,  median MAE ≈ -82.91 bps
RET_Z_DOWNSIDE_EXTREME_REV_LONG_L24_T1.5 / 120H residual ≈ +6.98 bps, median MAE ≈ -120.22 bps
BB_LOWER_REV_LONG_W24_K2 / 120H        residual ≈ +4.92 bps,  median MAE ≈ -107.57 bps
```

Therefore Stage39B must inspect event paths before any further research continuation.

## What Stage39B tests

- event-level path behavior,
- MAE/MFE and final return distribution,
- residual-to-MAE ratio,
- stop/target touch diagnostics,
- year split,
- ex-2025 sanity,
- leave-one-year-out sanity,
- cost and extra-slippage stress,
- optional path-profile plots.

## Inputs

Default inputs:

```text
db = data/local/xauusd_local_store.sqlite
table = bars
symbol = XAUUSD
source = amarkets_mt5
timeframe = H1
stage39a events = reports/stage39a/stage39a_reversal_mean_reversion_event_clock_events.csv
```

If the Stage39A events CSV is present and compatible, Stage39B uses it. If not, it reconstructs the strict-row triggers from H1 bars.

## Outputs

```text
reports/stage39b/stage39b_event_path_candidate_summary.csv
reports/stage39b/stage39b_event_path_event_rows.csv
reports/stage39b/stage39b_event_path_year_split.csv
reports/stage39b/stage39b_event_path_profile.csv
reports/stage39b/stage39b_event_path_diagnostic_summary.json
reports/stage39b/stage39b_event_path_tradability.md
reports/stage39b/plots/*.png
```

## Interpretation

`PATH_DIAGNOSTIC_WATCH_ONLY_NO_PROMOTION` means the row can remain under research observation only.

`WEAK_RESIDUAL_VS_PATH_RISK_NO_PROMOTION` means the benchmark residual is too small relative to the adverse path risk.

`YEAR_ROBUSTNESS_WEAK_NO_PROMOTION` means ex-2025 or leave-one-year-out stability is not strong enough.

`INSUFFICIENT_PATH_EVENTS_NO_PROMOTION` means the event-path evidence is too thin.

## Next rule

Only if one or more rows survive as `PATH_DIAGNOSTIC_WATCH_ONLY_NO_PROMOTION`, the next allowed step is:

```text
Stage39C_MICROSTRUCTURE_SESSION_CONDITION_DIAGNOSTIC
```

Otherwise Stage39A/B should be archived. No EA, no paper-live, no live.

## Schema hotfix note

The Stage39B loader is intentionally DB-first and tolerant:

- reads the requested table before metadata filtering,
- accepts `utc_time` as the timestamp column,
- normalizes symbol case,
- normalizes source case and surrounding whitespace,
- maps common H1 aliases such as `H1`, `1H`, `60M`, `60MIN`, and `1HR` to the same internal timeframe.

This matches Stage39A loader behavior and prevents false zero-row failures caused by exact SQL predicates on `source` or `timeframe`.
