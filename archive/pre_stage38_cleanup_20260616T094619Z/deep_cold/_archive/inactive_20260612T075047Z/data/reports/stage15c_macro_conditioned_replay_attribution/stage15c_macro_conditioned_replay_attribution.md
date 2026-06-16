# Stage 15C Macro-Conditioned Exact Replay Attribution

Generated UTC: `2026-06-11T06:03:11+00:00`
Tool version: `v1`

> Hard rule: macro/fundamental attribution only. No EA change, no automatic trading, no paper/live authorization.

## Candidate under attribution
- setup: `prev_day_low_sweep_rejection`
- side: `LONG`
- branch: `sweep_depth_ge_q50`
- regime: `reclaim_lt_q50`
- replay source: `Stage 15B exact M1 time-exit`
- trades: `94`
- cost_usd: `0.35`

## Data availability
- db_exists: `True`
- macro_long_rows: `150294`
- macro_series_loaded: `78`
- macro_selected_series: `40`
- events_loaded: `515`
- context_specs: `45`
- context_rows: `32`

## Final decision
- final_decision: `MACRO_CONTEXT_CANDIDATE_FOUND`

## Reasons
- Top context `macro_daily_regime_real_yield_10y_chg5_up` improved/preserved the validated candidate after cost.
- This permits one focused robustness check for this macro-conditioned context only, not EA/paper/live.

## Baseline Stage 15B candidate
| Events | Total | Avg | Median | WR | PF | DD | Pos years | Pos quarters |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 94 | 143.48 | 1.526383 | 1.105 | 0.617021 | 1.960246 | -58.78 | 4/5 | 10/17 |

## Top macro/event contexts
| Rank | Context | Source | Events | Coverage | Total | Median | WR | PF | DD | Test total | Test PF | Candidate |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | macro_daily_regime_real_yield_10y_chg5_up | macro_series | 48 | 0.510638 | 137.76 | 1.5 | 0.6875 | 3.446023 | -19.77 | 103.24 | 6.556512 | True |
| 2 | macro_daily_regime_d_real_yield_5d_chg5_up | macro_series | 51 | 0.542553 | 134.42 | 1.26 | 0.686275 | 3.317986 | -15.94 | 116.02 | 7.244349 | True |
| 3 | no_event_next_24h | events | 66 | 0.702128 | 136.04 | 1.105 | 0.636364 | 2.87048 | -27.16 | 104.36 | 7.672634 | True |
| 4 | macro_daily_regime_d_usd_20d_pct_chg5_down | macro_series | 38 | 0.404255 | 85.67 | 1.275 | 0.605263 | 2.85674 | -25.71 | 81.91 | 24.336182 | True |
| 5 | macro_daily_regime_d_usd_5d_pct_chg5_down | macro_series | 36 | 0.382979 | 84.51 | 1.99 | 0.638889 | 2.708308 | -30.69 | 60.35 | 6.634921 | True |
| 6 | macro_daily_regime_d_real_yield_20d_chg5_down | macro_series | 42 | 0.446809 | 66.87 | 1.3 | 0.619048 | 2.538302 | -21.37 | 48.29 | 10.094162 | True |
| 7 | no_event_prev_24h | events | 74 | 0.787234 | 138.99 | 1.105 | 0.635135 | 2.508138 | -49.35 | 114.26 | 20.498294 | True |
| 8 | macro_daily_regime_nominal_yield_10y_chg5_up | macro_series | 57 | 0.606383 | 126.42 | 1.18 | 0.649123 | 2.451102 | -43.66 | 129.7 | 8.471198 | True |
| 9 | macro_daily_regime_yield_curve_10y2y_chg5_up | macro_series | 47 | 0.5 | 85.75 | 1.37 | 0.638298 | 2.387092 | -34.98 | 73.03 | 8.444444 | True |
| 10 | macro_numeric_observations_fedfunds_chg5_up | macro_series | 91 | 0.968085 | 150.95 | 1.18 | 0.626374 | 2.096702 | -51.31 | 125.68 | 4.581647 | True |
| 11 | macro_numeric_observations_unrate_chg5_up | macro_series | 91 | 0.968085 | 150.95 | 1.18 | 0.626374 | 2.096702 | -51.31 | 125.68 | 4.581647 | True |
| 12 | macro_numeric_observations_dfii10_chg5_up | macro_series | 94 | 1.0 | 143.48 | 1.105 | 0.617021 | 1.960246 | -58.78 | 126.97 | 4.61841 | True |
| 13 | macro_numeric_observations_dgs10_chg5_up | macro_series | 94 | 1.0 | 143.48 | 1.105 | 0.617021 | 1.960246 | -58.78 | 126.97 | 4.61841 | True |
| 14 | macro_numeric_observations_dgs2_chg5_up | macro_series | 94 | 1.0 | 143.48 | 1.105 | 0.617021 | 1.960246 | -58.78 | 126.97 | 4.61841 | True |
| 15 | macro_numeric_observations_dtwexbgs_chg5_up | macro_series | 94 | 1.0 | 143.48 | 1.105 | 0.617021 | 1.960246 | -58.78 | 126.97 | 4.61841 | True |
| 16 | no_fomc_cpi_nfp_prev_24h | events | 94 | 1.0 | 143.48 | 1.105 | 0.617021 | 1.960246 | -58.78 | 126.97 | 4.61841 | True |
| 17 | macro_daily_regime_rate_pressure_score_chg5_down | macro_series | 17 | 0.180851 | 34.96 | 1.26 | 0.764706 | 5.060395 | -4.3 | 18.97 | 7.65614 | False |
| 18 | macro_daily_regime_usd_index_chg5_down | macro_series | 36 | 0.382979 | 95.52 | 0.665 | 0.583333 | 3.002516 | -23.27 | 82.55 | 11.904888 | False |
| 19 | macro_daily_regime_nominal_yield_2y_chg5_up | macro_series | 56 | 0.595745 | 103.73 | 0.945 | 0.642857 | 2.595355 | -21.07 | 90.3 | 6.201613 | False |
| 20 | macro_supportive | macro_score | 92 | 0.978723 | 137.98 | 1.01 | 0.608696 | 1.923437 | -58.78 | 114.18 | 3.694195 | False |

## Selected macro series
| Series | Class | Supportive when | Rows | First | Last |
|---|---|---|---:|---|---|
| macro_daily_regime.real_yield_10y | real_yield | down | 1618 | 2022-01-03T00:00:00+00:00 | 2026-06-08T00:00:00+00:00 |
| macro_daily_regime.d_real_yield_5d | real_yield | down | 1613 | 2022-01-08T00:00:00+00:00 | 2026-06-08T00:00:00+00:00 |
| macro_daily_regime.d_real_yield_20d | real_yield | down | 1598 | 2022-01-23T00:00:00+00:00 | 2026-06-08T00:00:00+00:00 |
| macro_numeric_observations.DFII10 | real_yield | down | 1156 | 2022-01-03T00:00:00+00:00 | 2026-06-08T00:00:00+00:00 |
| macro_daily_regime.nominal_yield_10y | nominal_yield_10y | down | 1618 | 2022-01-03T00:00:00+00:00 | 2026-06-08T00:00:00+00:00 |
| macro_daily_regime.yield_curve_10y2y | nominal_yield_10y | down | 1618 | 2022-01-03T00:00:00+00:00 | 2026-06-08T00:00:00+00:00 |
| macro_numeric_observations.DGS10 | nominal_yield_10y | down | 1156 | 2022-01-03T00:00:00+00:00 | 2026-06-08T00:00:00+00:00 |
| macro_daily_regime.nominal_yield_2y | nominal_yield_2y | down | 1618 | 2022-01-03T00:00:00+00:00 | 2026-06-08T00:00:00+00:00 |
| macro_numeric_observations.DGS2 | nominal_yield_2y | down | 1156 | 2022-01-03T00:00:00+00:00 | 2026-06-08T00:00:00+00:00 |
| macro_daily_regime.usd_pressure_score | usd | down | 1620 | 2022-01-01T00:00:00+00:00 | 2026-06-08T00:00:00+00:00 |
| macro_daily_regime.usd_index | usd | down | 1618 | 2022-01-03T00:00:00+00:00 | 2026-06-08T00:00:00+00:00 |
| macro_daily_regime.d_usd_5d_pct | usd | down | 1613 | 2022-01-08T00:00:00+00:00 | 2026-06-08T00:00:00+00:00 |
| macro_daily_regime.d_usd_20d_pct | usd | down | 1598 | 2022-01-23T00:00:00+00:00 | 2026-06-08T00:00:00+00:00 |
| macro_numeric_observations.DTWEXBGS | usd | down | 1155 | 2022-01-03T00:00:00+00:00 | 2026-06-05T00:00:00+00:00 |
| macro_daily_regime.fedfunds | policy_rate | down | 1620 | 2022-01-01T00:00:00+00:00 | 2026-06-08T00:00:00+00:00 |
| macro_daily_regime.rate_pressure_score | policy_rate | down | 1620 | 2022-01-01T00:00:00+00:00 | 2026-06-08T00:00:00+00:00 |
| macro_numeric_observations.FEDFUNDS | policy_rate | down | 53 | 2022-01-01T00:00:00+00:00 | 2026-05-01T00:00:00+00:00 |
| macro_numeric_observations.UNRATE | policy_rate | down | 53 | 2022-01-01T00:00:00+00:00 | 2026-05-01T00:00:00+00:00 |
| macro_daily_regime.cpi | inflation | mixed | 1620 | 2022-01-01T00:00:00+00:00 | 2026-06-08T00:00:00+00:00 |
| macro_daily_regime.oil_inflation_pressure_score | inflation | mixed | 1620 | 2022-01-01T00:00:00+00:00 | 2026-06-08T00:00:00+00:00 |
| macro_numeric_observations.CPIAUCSL | inflation | mixed | 52 | 2022-01-01T00:00:00+00:00 | 2026-04-01T00:00:00+00:00 |
| macro_daily_regime.brent | oil | mixed | 1618 | 2022-01-03T00:00:00+00:00 | 2026-06-08T00:00:00+00:00 |
| macro_daily_regime.wti | oil | mixed | 1618 | 2022-01-03T00:00:00+00:00 | 2026-06-08T00:00:00+00:00 |
| macro_daily_regime.d_oil_5d_pct | oil | mixed | 1613 | 2022-01-08T00:00:00+00:00 | 2026-06-08T00:00:00+00:00 |
| macro_daily_regime.d_oil_20d_pct | oil | mixed | 1598 | 2022-01-23T00:00:00+00:00 | 2026-06-08T00:00:00+00:00 |
| macro_numeric_observations.DCOILBRENTEU | oil | mixed | 1151 | 2022-01-03T00:00:00+00:00 | 2026-06-01T00:00:00+00:00 |
| macro_numeric_observations.DCOILWTICO | oil | mixed | 1151 | 2022-01-03T00:00:00+00:00 | 2026-06-01T00:00:00+00:00 |
| macro_context_h1._date | other | unknown | 24225 | 2022-05-01T23:00:00+00:00 | 2026-06-09T11:00:00+00:00 |
| macro_context_h1.active_event_count | other | unknown | 24225 | 2022-05-01T23:00:00+00:00 | 2026-06-09T11:00:00+00:00 |
| macro_context_h1.has_block_event | other | unknown | 24225 | 2022-05-01T23:00:00+00:00 | 2026-06-09T11:00:00+00:00 |

## Year distribution - baseline replay
| Year | Events | Total | Avg | Median | WR | PF | DD |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2022 | 19 | -54.86 | -2.887368 | -2.41 | 0.263158 | 0.178127 | -58.78 |
| 2023 | 21 | 30.28 | 1.441905 | 1.18 | 0.666667 | 2.377616 | -11.93 |
| 2024 | 23 | 41.7 | 1.813043 | 1.63 | 0.652174 | 3.277444 | -10.51 |
| 2025 | 23 | 79.46 | 3.454783 | 1.19 | 0.782609 | 4.175859 | -9.81 |
| 2026 | 8 | 46.9 | 5.8625 | 7.08 | 0.75 | 3.701613 | -15.94 |

## Interpretation
- `MACRO_CONTEXT_CANDIDATE_FOUND` permits one focused robustness check for the top macro-conditioned context only.
- `MACRO_CONTEXT_WEAK_ATTRIBUTION_ONLY` means macro helps explain but is not strong enough for system design.
- `MACRO_CONTEXT_NO_IMPROVEMENT` means available macro/event context did not improve this candidate.
- `MACRO_EVENT_DATA_MISSING` means data is not available in the current repo/local store.
- Macro/fundamental context is not an independent signal here.
- No EA/paper/live/order authorization is granted.

## Output files
- enriched_csv: `data/reports/stage15c_macro_conditioned_replay_attribution/stage15c_trades_with_macro_context.csv`
- macro_long_csv: `data/reports/stage15c_macro_conditioned_replay_attribution/stage15c_macro_long_loaded.csv`
- table_audit_csv: `data/reports/stage15c_macro_conditioned_replay_attribution/stage15c_macro_table_audit.csv`
- macro_series_audit_csv: `data/reports/stage15c_macro_conditioned_replay_attribution/stage15c_macro_series_audit.csv`
- context_csv: `data/reports/stage15c_macro_conditioned_replay_attribution/stage15c_context_summary.csv`
- year_csv: `data/reports/stage15c_macro_conditioned_replay_attribution/stage15c_by_year.csv`
- quarter_csv: `data/reports/stage15c_macro_conditioned_replay_attribution/stage15c_by_quarter.csv`
- json: `data/reports/stage15c_macro_conditioned_replay_attribution/stage15c_macro_conditioned_replay_attribution.json`
- md: `data/reports/stage15c_macro_conditioned_replay_attribution/stage15c_macro_conditioned_replay_attribution.md`
