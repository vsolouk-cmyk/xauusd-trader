# Stage39B_EVENT_PATH_AND_TRADABILITY_DIAGNOSTIC

## Decision

```text
scope = RESEARCH_STAGE_ONLY_NO_PROMOTION
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

Stage39B is an event-path and tradability diagnostic for Stage39A strict research-watch rows. It is not a promotion gate.

## Data audit

```json
{
  "db_path": "data/local/xauusd_local_store.sqlite",
  "table": "bars",
  "available_columns": [
    "source",
    "symbol",
    "timeframe",
    "utc_time",
    "open",
    "high",
    "low",
    "close",
    "tick_volume",
    "spread",
    "real_volume",
    "source_time",
    "imported_utc",
    "raw_json",
    "volume",
    "ingested_at"
  ],
  "columns": {
    "timestamp": "utc_time",
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "spread": "spread",
    "symbol": "symbol",
    "source": "source",
    "timeframe": "timeframe"
  },
  "requested_filters": {
    "symbol": "XAUUSD",
    "source": "amarkets_mt5",
    "timeframe": "H1"
  },
  "distinct_values_sample": {
    "symbol": [
      "XAUUSD"
    ],
    "source": [
      "amarkets_mt5"
    ],
    "timeframe": [
      "1h",
      "M5",
      "M15",
      "1m"
    ]
  },
  "filter_steps": [
    {
      "filter": "symbol",
      "requested": "XAUUSD",
      "normalized": "XAUUSD",
      "before": 1971743,
      "after": 1971743
    },
    {
      "filter": "source",
      "requested": "amarkets_mt5",
      "normalized": "amarkets_mt5",
      "before": 1971743,
      "after": 1971743
    },
    {
      "filter": "timeframe",
      "requested": "H1",
      "normalized": "H1",
      "before": 1971743,
      "after": 25643
    }
  ],
  "pre_filter_rows": 1971743,
  "post_filter_rows": 25643,
  "loaded_rows": 25643,
  "date_min": "2022-05-01T23:00:00+00:00",
  "date_max": "2026-06-16T12:00:00+00:00"
}
```

## Classification counts

```json
{
  "PATH_DIAGNOSTIC_WATCH_ONLY_NO_PROMOTION": 2,
  "WEAK_RESIDUAL_VS_PATH_RISK_NO_PROMOTION": 2
}
```

## Candidate path diagnostic summary

| classification                          | candidate                                | side   |   horizon_hours |   event_clock_n |   mean_final_bps |   median_final_bps |   cost_stressed_mean_bps |   stage39a_h1_benchmark_cost_adjusted_residual_bps |   residual_to_median_mae_abs |   median_mae_bps |   median_mfe_bps |   ex2025_mean_bps |   leave_one_year_out_min_mean_bps |   touch_stop_100bps_pct |   touch_target_100bps_pct |
|:----------------------------------------|:-----------------------------------------|:-------|----------------:|----------------:|-----------------:|-------------------:|-------------------------:|---------------------------------------------------:|-----------------------------:|-----------------:|-----------------:|------------------:|----------------------------------:|------------------------:|--------------------------:|
| PATH_DIAGNOSTIC_WATCH_ONLY_NO_PROMOTION | BB_LOWER_REV_LONG_W120_K2.5              | LONG   |              72 |              80 |            45.25 |              26.11 |                    37.25 |                                              12.93 |                         0.15 |           -87    |           153.37 |             27.5  |                             27.5  |                   43.75 |                     65    |
| PATH_DIAGNOSTIC_WATCH_ONLY_NO_PROMOTION | RANGE_BOTTOM_REV_LONG_W48_Q0.05          | LONG   |              72 |             145 |            48.13 |              34.58 |                    40.13 |                                               8.96 |                         0.12 |           -76.42 |           123.1  |             32.23 |                             32.23 |                   40.69 |                     62.07 |
| WEAK_RESIDUAL_VS_PATH_RISK_NO_PROMOTION | RET_Z_DOWNSIDE_EXTREME_REV_LONG_L24_T1.5 | LONG   |             120 |             127 |            55.6  |              56.08 |                    47.6  |                                               6.98 |                         0.06 |          -112.11 |           186.57 |             30.76 |                             30.76 |                   58.27 |                     72.44 |
| WEAK_RESIDUAL_VS_PATH_RISK_NO_PROMOTION | BB_LOWER_REV_LONG_W24_K2                 | LONG   |             120 |             132 |            53.2  |              43.49 |                    45.2  |                                               4.92 |                         0.05 |          -107.57 |           166.11 |             35.75 |                             35.75 |                   53.79 |                     68.18 |

## Interpretation

- `PATH_DIAGNOSTIC_WATCH_ONLY_NO_PROMOTION` means the row can remain under research observation only.
- `WEAK_RESIDUAL_VS_PATH_RISK_NO_PROMOTION` means Stage39A residual is too small relative to intrahorizon adverse excursion.
- `YEAR_ROBUSTNESS_WEAK_NO_PROMOTION` means ex-2025 or leave-one-year-out sanity is not robust enough.
- `INSUFFICIENT_PATH_EVENTS_NO_PROMOTION` means event path evidence is still too thin.

## Path plots

- Plot generation skipped because matplotlib was not available.

## Next allowed step

Only if one or more candidates remain `PATH_DIAGNOSTIC_WATCH_ONLY_NO_PROMOTION`, the next step is a Stage39C microstructure/session-condition diagnostic. Otherwise archive Stage39A/B and do not extend weak rows with filters.
