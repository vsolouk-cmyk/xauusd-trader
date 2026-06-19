# Stage47B Final Archive — Liquidity Sweep Reversal

## Decision

```text
stage = Stage47B_FINAL_ARCHIVE_LIQUIDITY_SWEEP_REVERSAL
status = ARCHIVE_COMPLETE_NO_PROMOTION
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
next_allowed_step = NEW_STRUCTURAL_THESIS_DECISION_OR_PAUSE_ARCHIVE
```

## Input scan recap

```text
rows_loaded = 500
candidate_count = 27
trade_count = 3
strict_survivor_count = 0
soft_survivor_count = 0
cost_bps = 8.0
source = data/normalized/normalized_twelvedata_XAU_USD_5min_20260604T060243Z.csv
```

## Candidate diagnostics

```text
positive_in_sample_count = 0
positive_oos_count = 0
positive_both_count = 0
```

Best in-sample candidate:

```text
candidate_id = ST47B_GRID01_LB24_H12_SW6
trades = 0
mean_net_bps = 0.0
oos_mean_net_bps = nan
strict_survivor = False
soft_survivor = False
```

Best OOS candidate:

```text
candidate_id = ST47B_GRID01_LB24_H12_SW6
trades = 0
mean_net_bps = 0.0
oos_mean_net_bps = nan
strict_survivor = False
soft_survivor = False
```

## Interpretation

Stage47B finally ran on an adequate M5 history horizon after Stage47B3 backfill. The loader and data horizon problems are resolved. However, the predefined liquidity-sweep reversal thesis did not produce any strict or soft survivor after costs.

The key failure is not implementation. It is evidence failure: several configurations show positive in-sample mean net bps, but every candidate has negative out-of-sample mean net bps. Therefore, Stage47C audit is not allowed because there is no survivor to audit.

## Hard prohibitions

- Do not promote this thesis to EA, paper-live, or live.
- Do not rescue a candidate by post-hoc filtering bad sessions, months, spread buckets, or news windows.
- Do not start ML from this failure.
- Do not tune the Stage47B grid after seeing this result.

## Valid next action

```text
NEW_STRUCTURAL_THESIS_DECISION_OR_PAUSE_ARCHIVE
```

A new structural thesis is allowed only if it is predefined from first principles and materially different from Stage41 through Stage47B.
