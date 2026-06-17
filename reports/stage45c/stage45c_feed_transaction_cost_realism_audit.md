# Stage45C_FEED_AND_TRANSACTION_COST_REALISM_AUDIT

## Decision

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
recommended_next_stage = Stage45B_EXTERNAL_CONTEXT_AND_REFERENCE_FEED_DECISION
```

Stage45C is a broker/feed and transaction-cost realism audit only. It does not create trading signals, does not shortlist candidates, and cannot promote any prior row.

## Inputs

```text
db_path: data/local/xauusd_local_store.sqlite
table: bars
source: amarkets_mt5
symbol: XAUUSD
timeframes: M15, H1, M5
```

## Per-timeframe spread and quality profile

| timeframe | rows | start | end | selected_spread_mode | spread_median_bps | spread_p90_bps | spread_p95_bps | spread_p99_bps | median_bar_range_bps | spread/range median | gaps_gt_1p5x |
| :-- | --: | :-- | :-- | :-- | --: | --: | --: | --: | --: | --: | --: |
| M15 | 102493 | 2022-05-01T23:00:00+00:00 | 2026-06-16T12:15:00+00:00 | points_x_0.01 | 1.333 | 2.575 | 2.752 | 3.542 | 10.865 | 0.123 | 255 |
| H1 | 25643 | 2022-05-01T23:00:00+00:00 | 2026-06-16T12:00:00+00:00 | points_x_0.01 | 1.254 | 2.435 | 2.650 | 2.768 | 22.292 | 0.056 | 252 |
| M5 | 307334 | 2022-05-01T23:00:00+00:00 | 2026-06-16T12:15:00+00:00 | points_x_0.01 | 1.321 | 2.541 | 2.727 | 3.338 | 6.081 | 0.217 | 258 |

## Stage45 reference

```json
{
  "exists": true,
  "path": "reports/stage45/stage45_cost_aware_baseline_recalibration_summary.json",
  "recommended_next_stage": "Stage45C_FEED_AND_TRANSACTION_COST_REALISM_AUDIT",
  "rationale": [
    "Only very-low-cost diagnostic assumptions create pass rows; current broker-cost environment likely overwhelms these edges.",
    "Even minimal-edge sanity gates find no robust observed-cost rows.",
    "Cost-stressed p90 is only 8.82 bps, below a practical robust edge gate.",
    "Median cost-stressed mean is negative (-7.38 bps).",
    "Worst-quarter median is deeply negative (-58.55 bps), showing path fragility.",
    "Bootstrap p10 median is below gate (-11.06 bps)."
  ],
  "required_uniform_bps_improvement_profile": {
    "n": 78,
    "min": 12.38547132850297,
    "p10": 16.455562689206612,
    "median": 27.188406848506986,
    "p90": 67.14166589945577,
    "max": 108.74588501975248,
    "mean": 33.77671306776575
  },
  "scenario_pass_counts": [
    {
      "name": "observed_costs_current_strict",
      "cost_saving_bps": 0.0,
      "pass_count": 0,
      "pass_by_stage": {}
    },
    {
      "name": "realistic_cost_improvement_plus4",
      "cost_saving_bps": 4.0,
      "pass_count": 0,
      "pass_by_stage": {}
    },
    {
      "name": "aggressive_cost_improvement_plus8",
      "cost_saving_bps": 8.0,
      "pass_count": 0,
      "pass_by_stage": {}
    },
    {
      "name": "very_low_cost_plus16_diagnostic_only",
      "cost_saving_bps": 16.0,
      "pass_count": 4,
      "pass_by_stage": {
        "stage42": 4
      }
    },
    {
      "name": "minimal_edge_sanity_observed",
      "cost_saving_bps": 0.0,
      "pass_count": 0,
      "pass_by_stage": {}
    },
    {
      "name": "event_scarcity_probe_min40",
      "cost_saving_bps": 0.0,
      "pass_count": 0,
      "pass_by_stage": {}
    }
  ]
}
```

## Decision rationale

```text
- Spread column was detected and converted to bps for broker/feed cost profiling.
- Worst timeframe selected spread p90 is approximately 2.575 bps before extra slippage.
- Worst timeframe median spread / median bar range ratio is approximately 0.217.
- Cost realism is not decisive enough by itself; external context remains the next evidence-based branch.
```

## Not allowed

```text
- candidate_rescue_from_stage41_42_43
- post_hoc_filtering_of_bad_hours_months_years_quarters_or_spread_buckets
- EA_paper_live_live_from_archived_rows
- ML_before_robust_cost_aware_baseline
```

## Anti-overfit note

Do not use this audit to rescue Stage41/42/43 rows by selecting favorable spread buckets after seeing the result. The audit can only choose the next evidence-based research direction.
