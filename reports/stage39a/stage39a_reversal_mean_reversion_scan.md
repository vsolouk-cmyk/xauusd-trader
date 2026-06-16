# Stage39A_BENCHMARK_FIRST_REVERSAL_OR_MEAN_REVERSION_SCAN

## Decision

```text
scope = RESEARCH_STAGE_ONLY_NO_PROMOTION
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

This scan is benchmark-first. Any positive mean must be interpreted after direction-matched H1 drift, daily anchor drift, cost stress, year split, 2025 exclusion, leave-one-year-out, and MAE/MFE checks.

## Data audit

```json
{
  "db_path": "/Users/vahid/Desktop/xauusd-trader/data/local/xauusd_local_store.sqlite",
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
    "symbol": "symbol",
    "source": "source",
    "timeframe": "timeframe",
    "spread": "spread"
  },
  "loaded_rows": 25643,
  "date_min": "2022-05-01T23:00:00+00:00",
  "date_max": "2026-06-16T12:00:00+00:00"
}
```

## Drift benchmarks

```json
{
  "24": {
    "h1_all_count": 25619,
    "h1_all_long_mean_bps": 8.502590481085887,
    "daily_anchor_count": 1283,
    "daily_anchor_long_mean_bps": 7.013983104031285
  },
  "72": {
    "h1_all_count": 25571,
    "h1_all_long_mean_bps": 25.002508867881488,
    "daily_anchor_count": 1281,
    "daily_anchor_long_mean_bps": 21.018360592288875
  },
  "120": {
    "h1_all_count": 25523,
    "h1_all_long_mean_bps": 41.34868880772282,
    "daily_anchor_count": 1279,
    "daily_anchor_long_mean_bps": 34.35585536444943
  }
}
```

## Classification counts

```json
{
  "FAIL_BENCHMARK_RESEARCH_ONLY": 157,
  "INSUFFICIENT_EVENTS_RESEARCH_ONLY": 17,
  "STRICT_RESEARCH_WATCH_ONLY_NO_PROMOTION": 4,
  "WATCH_ONLY_BENCHMARK_RESIDUAL_NO_PROMOTION": 2
}
```

## Strict research-watch rows

| classification | candidate | family | side | horizon_hours | event_clock_n | event_clock_mean_bps | event_clock_cost_stressed_mean_bps | directional_h1_all_drift_bps | h1_benchmark_cost_adjusted_residual_bps | ex2025_mean_bps | leave_one_year_out_min_mean_bps | median_mae_bps | median_mfe_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| STRICT_RESEARCH_WATCH_ONLY_NO_PROMOTION | BB_LOWER_REV_LONG_W120_K2.5 | BOLLINGER_REVERSAL | LONG | 72 | 87 | 45.93 | 37.93 | 25.00 | 12.93 | 21.37 | 21.37 | -88.41 | 149.05 |
| STRICT_RESEARCH_WATCH_ONLY_NO_PROMOTION | RANGE_BOTTOM_REV_LONG_W48_Q0.05 | ROLLING_RANGE_REVERSAL | LONG | 72 | 177 | 41.96 | 33.96 | 25.00 | 8.96 | 26.01 | 26.01 | -82.91 | 120.25 |
| STRICT_RESEARCH_WATCH_ONLY_NO_PROMOTION | RET_Z_DOWNSIDE_EXTREME_REV_LONG_L24_T1.5 | RETURN_ZSCORE_REVERSAL | LONG | 120 | 172 | 56.33 | 48.33 | 41.35 | 6.98 | 28.36 | 28.36 | -120.22 | 175.98 |
| STRICT_RESEARCH_WATCH_ONLY_NO_PROMOTION | BB_LOWER_REV_LONG_W24_K2 | BOLLINGER_REVERSAL | LONG | 120 | 200 | 54.27 | 46.27 | 41.35 | 4.92 | 31.60 | 31.60 | -107.57 | 170.56 |

## Soft watch rows

| classification | candidate | family | side | horizon_hours | event_clock_n | event_clock_mean_bps | event_clock_cost_stressed_mean_bps | directional_h1_all_drift_bps | h1_benchmark_cost_adjusted_residual_bps | ex2025_mean_bps | leave_one_year_out_min_mean_bps | median_mae_bps | median_mfe_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| WATCH_ONLY_BENCHMARK_RESIDUAL_NO_PROMOTION | RANGE_BOTTOM_REV_LONG_W24_Q0.1 | ROLLING_RANGE_REVERSAL | LONG | 120 | 195 | 51.46 | 43.46 | 41.35 | 2.11 | 23.08 | 23.08 | -102.72 | 165.02 |
| WATCH_ONLY_BENCHMARK_RESIDUAL_NO_PROMOTION | BB_LOWER_REV_LONG_W24_K2 | BOLLINGER_REVERSAL | LONG | 72 | 278 | 33.18 | 25.18 | 25.00 | 0.18 | 28.36 | 28.36 | -91.33 | 124.81 |

## Top rows by benchmark-cost residual

| classification | candidate | family | side | horizon_hours | event_clock_n | event_clock_mean_bps | event_clock_cost_stressed_mean_bps | directional_h1_all_drift_bps | h1_benchmark_cost_adjusted_residual_bps | ex2025_mean_bps | leave_one_year_out_min_mean_bps | median_mae_bps | median_mfe_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| INSUFFICIENT_EVENTS_RESEARCH_ONLY | RSI_OVERBOUGHT_REV_SHORT_RSI28_T75 | RSI_REVERSAL | SHORT | 72 | 23 | 105.39 | 97.39 | -25.00 | 122.39 | 86.20 | 68.51 | -124.27 | 166.67 |
| INSUFFICIENT_EVENTS_RESEARCH_ONLY | RSI_OVERBOUGHT_REV_SHORT_RSI28_T75 | RSI_REVERSAL | SHORT | 120 | 22 | 57.17 | 49.17 | -41.35 | 90.52 | -7.44 | -7.44 | -138.76 | 182.00 |
| INSUFFICIENT_EVENTS_RESEARCH_ONLY | RSI_OVERBOUGHT_REV_SHORT_RSI28_T75 | RSI_REVERSAL | SHORT | 24 | 25 | 66.90 | 58.90 | -8.50 | 67.40 | 42.42 | 42.42 | -57.63 | 97.15 |
| INSUFFICIENT_EVENTS_RESEARCH_ONLY | RET_Z_UPSIDE_EXTREME_REV_SHORT_L120_T2.5 | RETURN_ZSCORE_REVERSAL | SHORT | 72 | 24 | 19.96 | 11.96 | -25.00 | 36.96 | 57.84 | -35.08 | -160.47 | 100.87 |
| FAIL_BENCHMARK_RESEARCH_ONLY | RET_Z_UPSIDE_EXTREME_REV_SHORT_L24_T2.5 | RETURN_ZSCORE_REVERSAL | SHORT | 72 | 67 | 6.54 | -1.46 | -25.00 | 23.55 | 38.94 | -22.29 | -123.25 | 108.27 |
| FAIL_BENCHMARK_RESEARCH_ONLY | RET_Z_UPSIDE_EXTREME_REV_SHORT_L72_T2.5 | RETURN_ZSCORE_REVERSAL | SHORT | 120 | 30 | -19.02 | -27.02 | -41.35 | 14.33 | -3.21 | -45.34 | -150.83 | 133.00 |
| STRICT_RESEARCH_WATCH_ONLY_NO_PROMOTION | BB_LOWER_REV_LONG_W120_K2.5 | BOLLINGER_REVERSAL | LONG | 72 | 87 | 45.93 | 37.93 | 25.00 | 12.93 | 21.37 | 21.37 | -88.41 | 149.05 |
| FAIL_BENCHMARK_RESEARCH_ONLY | BB_UPPER_REV_SHORT_W72_K2.5 | BOLLINGER_REVERSAL | SHORT | 72 | 144 | -6.49 | -14.49 | -25.00 | 10.51 | 10.12 | -16.98 | -125.60 | 79.72 |
| STRICT_RESEARCH_WATCH_ONLY_NO_PROMOTION | RANGE_BOTTOM_REV_LONG_W48_Q0.05 | ROLLING_RANGE_REVERSAL | LONG | 72 | 177 | 41.96 | 33.96 | 25.00 | 8.96 | 26.01 | 26.01 | -82.91 | 120.25 |
| INSUFFICIENT_EVENTS_RESEARCH_ONLY | RET_Z_UPSIDE_EXTREME_REV_SHORT_L120_T2.5 | RETURN_ZSCORE_REVERSAL | SHORT | 120 | 22 | -24.93 | -32.93 | -41.35 | 8.42 | -3.89 | -64.62 | -205.59 | 123.97 |
| STRICT_RESEARCH_WATCH_ONLY_NO_PROMOTION | RET_Z_DOWNSIDE_EXTREME_REV_LONG_L24_T1.5 | RETURN_ZSCORE_REVERSAL | LONG | 120 | 172 | 56.33 | 48.33 | 41.35 | 6.98 | 28.36 | 28.36 | -120.22 | 175.98 |
| INSUFFICIENT_EVENTS_RESEARCH_ONLY | RSI_OVERSOLD_REV_LONG_RSI28_T25 | RSI_REVERSAL | LONG | 24 | 9 | 23.43 | 15.43 | 8.50 | 6.93 | 23.43 | -24.84 | -60.64 | 61.33 |
| STRICT_RESEARCH_WATCH_ONLY_NO_PROMOTION | BB_LOWER_REV_LONG_W24_K2 | BOLLINGER_REVERSAL | LONG | 120 | 200 | 54.27 | 46.27 | 41.35 | 4.92 | 31.60 | 31.60 | -107.57 | 170.56 |
| FAIL_BENCHMARK_RESEARCH_ONLY | RET_Z_UPSIDE_EXTREME_REV_SHORT_L24_T1.5 | RETURN_ZSCORE_REVERSAL | SHORT | 120 | 167 | -28.99 | -36.99 | -41.35 | 4.36 | -7.86 | -41.74 | -158.08 | 126.58 |
| FAIL_BENCHMARK_RESEARCH_ONLY | RET_Z_UPSIDE_EXTREME_REV_SHORT_L24_T2 | RETURN_ZSCORE_REVERSAL | SHORT | 120 | 116 | -29.72 | -37.72 | -41.35 | 3.63 | -17.03 | -37.47 | -161.54 | 107.82 |
| WATCH_ONLY_BENCHMARK_RESIDUAL_NO_PROMOTION | RANGE_BOTTOM_REV_LONG_W24_Q0.1 | ROLLING_RANGE_REVERSAL | LONG | 120 | 195 | 51.46 | 43.46 | 41.35 | 2.11 | 23.08 | 23.08 | -102.72 | 165.02 |
| FAIL_BENCHMARK_RESEARCH_ONLY | BB_UPPER_REV_SHORT_W120_K2.5 | BOLLINGER_REVERSAL | SHORT | 72 | 97 | -14.92 | -22.92 | -25.00 | 2.09 | 10.63 | -34.65 | -146.56 | 78.14 |
| FAIL_BENCHMARK_RESEARCH_ONLY | RET_Z_UPSIDE_EXTREME_REV_SHORT_L24_T2.5 | RETURN_ZSCORE_REVERSAL | SHORT | 24 | 76 | 1.42 | -6.58 | -8.50 | 1.92 | 15.13 | -6.15 | -59.60 | 59.69 |
| FAIL_BENCHMARK_RESEARCH_ONLY | BB_UPPER_REV_SHORT_W72_K2.5 | BOLLINGER_REVERSAL | SHORT | 120 | 132 | -31.82 | -39.82 | -41.35 | 1.53 | -16.81 | -41.70 | -159.63 | 111.83 |
| FAIL_BENCHMARK_RESEARCH_ONLY | RET_Z_UPSIDE_EXTREME_REV_SHORT_L72_T2.5 | RETURN_ZSCORE_REVERSAL | SHORT | 72 | 33 | -15.67 | -23.67 | -25.00 | 1.33 | 12.61 | -65.20 | -134.24 | 77.90 |
| FAIL_BENCHMARK_RESEARCH_ONLY | RET_Z_UPSIDE_EXTREME_REV_SHORT_L120_T1.5 | RETURN_ZSCORE_REVERSAL | SHORT | 72 | 95 | -16.06 | -24.06 | -25.00 | 0.94 | -23.09 | -23.09 | -140.95 | 91.73 |
| FAIL_BENCHMARK_RESEARCH_ONLY | RSI_OVERBOUGHT_REV_SHORT_RSI28_T70 | RSI_REVERSAL | SHORT | 72 | 72 | -16.43 | -24.43 | -25.00 | 0.57 | 8.37 | -27.41 | -117.03 | 102.79 |
| FAIL_BENCHMARK_RESEARCH_ONLY | BB_UPPER_REV_SHORT_W72_K2 | BOLLINGER_REVERSAL | SHORT | 72 | 196 | -16.79 | -24.79 | -25.00 | 0.21 | -0.30 | -25.01 | -123.71 | 97.85 |
| WATCH_ONLY_BENCHMARK_RESIDUAL_NO_PROMOTION | BB_LOWER_REV_LONG_W24_K2 | BOLLINGER_REVERSAL | LONG | 72 | 278 | 33.18 | 25.18 | 25.00 | 0.18 | 28.36 | 28.36 | -91.33 | 124.81 |
| FAIL_BENCHMARK_RESEARCH_ONLY | BB_LOWER_REV_LONG_W72_K2 | BOLLINGER_REVERSAL | LONG | 120 | 140 | 48.83 | 40.83 | 41.35 | -0.52 | 28.85 | 28.85 | -105.78 | 159.69 |
| FAIL_BENCHMARK_RESEARCH_ONLY | BB_LOWER_REV_LONG_W120_K2.5 | BOLLINGER_REVERSAL | LONG | 24 | 107 | 15.74 | 7.74 | 8.50 | -0.76 | 6.97 | 6.97 | -44.11 | 71.93 |
| FAIL_BENCHMARK_RESEARCH_ONLY | RANGE_BOTTOM_REV_LONG_W48_Q0.05 | ROLLING_RANGE_REVERSAL | LONG | 24 | 242 | 15.61 | 7.61 | 8.50 | -0.89 | 12.12 | 12.12 | -48.33 | 69.54 |
| FAIL_BENCHMARK_RESEARCH_ONLY | RET_Z_UPSIDE_EXTREME_REV_SHORT_L24_T2 | RETURN_ZSCORE_REVERSAL | SHORT | 72 | 130 | -18.05 | -26.05 | -25.00 | -1.05 | 2.60 | -28.86 | -132.76 | 82.23 |
| FAIL_BENCHMARK_RESEARCH_ONLY | RET_Z_UPSIDE_EXTREME_REV_SHORT_L120_T1.5 | RETURN_ZSCORE_REVERSAL | SHORT | 24 | 187 | -2.06 | -10.06 | -8.50 | -1.56 | -4.36 | -4.42 | -65.33 | 55.57 |
| FAIL_BENCHMARK_RESEARCH_ONLY | RET_Z_UPSIDE_EXTREME_REV_SHORT_L24_T2 | RETURN_ZSCORE_REVERSAL | SHORT | 24 | 163 | -2.24 | -10.24 | -8.50 | -1.74 | 8.17 | -6.68 | -61.10 | 48.67 |

## Interpretation rule

- `STRICT_RESEARCH_WATCH_ONLY_NO_PROMOTION` means a row is worth a deeper diagnostic, not tradable.
- `WATCH_ONLY_BENCHMARK_RESIDUAL_NO_PROMOTION` means residual exists after the first benchmark, but robustness is not enough.
- `FAIL_BENCHMARK_RESEARCH_ONLY` means do not extend with filters.
- `INSUFFICIENT_EVENTS_RESEARCH_ONLY` means event count is too low for this stage.

## Next allowed step

Only if one or more strict research-watch rows exist: run a separate Stage39B diagnostic with event-list inspection, MAE/MFE path plots, year-specific sanity, and cost/slippage stress. Otherwise archive Stage39A and do not promote.
