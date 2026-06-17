# Stage40 Final Archive After Stage40B

## Decision

```text
scope = RESEARCH_STAGE_ONLY_NO_PROMOTION
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

Stage40 is archived after Stage40B because the only strict Stage40 megascan survivor failed the dedicated path/stability audit.

## Source

```text
Stage40B_SURVIVOR_PATH_STABILITY_AUDIT
```

## Archived survivor

```text
family = VOL_COMPRESSION_EXPANSION
candidate = VOL_COMP_EXP_LONG_L120_Q0.15_M2.0
side = LONG
horizon_hours = 72
classification = FAIL_STAGE40B_SURVIVOR_AUDIT_NO_PROMOTION
hard_fail_reasons = worst_quarter_slip16_floor
```

## Key metrics

```text
full_n = 88
full_cost_mean_bps = 45.2044
train_cost_mean_bps = 37.7798
oos_cost_mean_bps = 59.5588
worst_quarter_cost_mean_bps = 3.8852
worst_quarter_slip16_mean_bps = -12.1148
boot_p10_bps = 23.4630
boot_prob_mean_gt_0_pct = 99.80
full_median_mae_bps = -84.2959
oos_median_mae_bps = -105.3950
full_touch_stop_100bps_pct = 44.3182
oos_touch_stop_100bps_pct = 53.3333
worst_year_cost_mean_bps = -15.4030
```

## Interpretation

The survivor still has positive full, train, OOS, and bootstrap behavior, but it fails the hardened Stage40B rule because the worst-quarter slippage-16 mean is negative. This indicates that execution/slippage stress can erase the apparent edge in the weakest segment.

The rule should not be rescued by adding filters such as hour, month, weekday, or session exclusions. The Stage40B report shows weak buckets such as specific hours/months/years, but filtering them out after seeing this audit would be a high-risk overfit path.

## Final archive rule

```text
Stage40A/B = ARCHIVE
Stage40C = NOT_ALLOWED
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

## Next allowed step

Start a new independent thesis batch only. Any continuation must introduce genuinely new thesis families or materially different signal construction. Do not extend `VOL_COMP_EXP_LONG_L120_Q0.15_M2.0` with rescue filters.
