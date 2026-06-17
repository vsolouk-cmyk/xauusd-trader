# Stage39 Final Archive After Stage39F Recency Bias Audit

## Decision

```text
scope = RESEARCH_STAGE_ARCHIVE_ONLY_NO_PROMOTION
Stage39A_F = ARCHIVE
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

Stage39F produced the final stopping condition for this branch:

```text
strict_stable_frozen_watch_count = 0
recency_biased_watch_count = 6
classification_counts = {"RECENCY_BIASED_FROZEN_RULE_WATCH_ONLY_NO_PROMOTION": 6}
```

Final interpretation:

```text
NO_STABLE_FROZEN_RULE_SURVIVOR
```

All Stage39F survivors were classified as:

```text
RECENCY_BIASED_FROZEN_RULE_WATCH_ONLY_NO_PROMOTION
```

Therefore Stage39A-F must be archived. The surviving rules must not be extended with more filters.

## What Stage39 found

Stage39 started after Stage38 archive/no-go as a benchmark-first reversal / mean-reversion research branch. It gradually narrowed to a single family:

```text
RANGE_BOTTOM_REV_LONG_W48_Q0.05
```

Temporary watch-only rules appeared around:

```text
weekday = Monday
trigger_severity_bucket = SEVERITY_LOW / SEVERITY_MID
prior_ret72_regime = NEUTRAL_-75_75BPS
prior_ret72_regime = DOWN_MODERATE_-200_-75BPS
spread_regime = NA
```

However, Stage39F showed that these rules are not stable enough. Their later/OOS performance is much stronger than early/train performance, and early quarter / worst quarter behavior fails strict robustness floors.

## Stage39F survivor audit table

| spec_label | full_n | train_cost_mean_bps | oos_cost_mean_bps | worst_quarter_cost_mean_bps | failed_hard_checks | recency_flags |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: weekday=Monday | 38 | 22.10 | 179.41 | -5.31 | train_slip16_floor;worst_quarter_cost_floor;worst_quarter_slip16_floor | oos_train_gap_high;oos_train_ratio_high;early_quarter_negative;early_quarter_slip16_negative |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: trigger_severity_bucket=SEVERITY_LOW | 52 | 5.59 | 106.27 | -27.72 | train_cost_floor;train_slip16_floor;worst_quarter_cost_floor;worst_quarter_slip16_floor | oos_train_gap_high;oos_train_ratio_high;early_quarter_negative;early_quarter_slip16_negative |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: prior_ret72_regime=NEUTRAL_-75_75BPS | 81 | 19.60 | 86.04 | -7.98 | train_slip16_floor;worst_quarter_cost_floor;worst_quarter_slip16_floor | oos_train_gap_high;oos_train_ratio_high;q4_to_full_ratio_high;early_quarter_negative;early_quarter_slip16_negative |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: trigger_severity_bucket=SEVERITY_MID | 52 | 23.47 | 78.45 | 11.12 | train_slip16_floor;worst_quarter_slip16_floor;oos_median_mae_cap;oos_stop100_cap | oos_train_ratio_high;early_quarter_slip16_negative |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: prior_ret72_regime=DOWN_MODERATE_-200_-75BPS | 50 | 24.23 | 76.70 | -22.43 | train_slip16_floor;worst_quarter_cost_floor;worst_quarter_slip16_floor | oos_train_ratio_high;early_quarter_negative;early_quarter_slip16_negative |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: spread_regime=NA | 156 | 14.38 | 74.20 | 9.53 | train_cost_floor;train_slip16_floor;worst_quarter_slip16_floor | oos_train_ratio_high;early_quarter_slip16_negative |

## Technical conclusion

Do not promote any Stage39 rule.

Do not continue by adding filters to:

```text
RANGE_BOTTOM_REV_LONG_W48_Q0.05
```

The apparent edge is dominated by recent/OOS behavior and does not pass stable frozen-rule robustness. Adding more filters after Stage39F would likely overfit the recent regime.

## What not to do next

Do not:

- promote to EA,
- start paper-live,
- start live,
- send trade alerts,
- add more conditions to Monday / severity / prior-ret72 survivors,
- treat OOS strength as trade readiness,
- continue Stage39G as another filter layer.

## Allowed next research direction

A future next branch should be new-thesis only. It should not be a Stage39 continuation.

Recommended label:

```text
Stage40_NEW_THESIS_BENCHMARK_FIRST_SCAN
```

Stage40 should only begin if it tests a materially different idea, for example:

```text
false-breakout / liquidity sweep behavior
intraday volatility compression and expansion
news-window exclusion/annotation
session transition behavior
multi-timeframe structure independent of Stage39 range-bottom filters
```

Stage40 must inherit the same constraints:

```text
research-stage only
benchmark-first
cost-stressed
drift-adjusted
year split
exclude-2025
leave-one-year-out
forward split
no EA / no paper-live / no live until strict stable frozen evidence exists
```

## Commit command

```bash
cd ~/Desktop/xauusd-trader

git status --short

git add \
  docs/STAGE39_FINAL_ARCHIVE_AFTER_STAGE39F.md \
  reports/stage39_final/stage39_final_archive_decision.json \
  stage39_final_archive_manifest.json

git commit -m "Archive Stage39 after recency bias stability audit"

git pull --rebase origin main
git push
```
