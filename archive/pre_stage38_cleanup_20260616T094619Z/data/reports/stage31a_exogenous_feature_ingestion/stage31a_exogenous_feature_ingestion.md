# Stage31A External/Macro/News Feature Ingestion

Generated UTC: `2026-06-13T22:22:32.920826+00:00`

## Decision

```text
STAGE31A_EXOGENOUS_FEATURE_DATASET_READY_FOR_STAGE31B_REVIEW_ONLY
```

## Scope guardrails

- Research/shadow feature ingestion only.
- No EA change, no automatic trading, no paper/live/order authorization.
- Consumes Stage30A ML dataset and manually supplied exogenous CSVs only.
- No external internet fetch is performed by this stage.
- Existing trade artifacts remain research evidence only, not market-data fallback.
- All joined exogenous values use asof/backward joins only: no future values are allowed.

## Base dataset

```json
{
  "dataset_path": "/Users/vahid/Desktop/xauusd-trader/data/reports/stage30a_candidate_pool_builder_ml_dataset/stage30a_ml_meta_dataset.csv",
  "loaded": true,
  "rows_raw": 17124,
  "columns": [
    "event_key",
    "entry_ts_norm",
    "source_stage",
    "source_file",
    "family",
    "candidate_name",
    "net_x1",
    "net_x4",
    "net_x6",
    "label_win_x4",
    "label_win_x6",
    "label_strong_win_x4",
    "label_bad_loss_x4",
    "sample_weight_abs_net_x4",
    "prior_day_range",
    "asia_range",
    "asia_eff",
    "london_range",
    "london_eff",
    "h1_range",
    "h1_atr20",
    "h1_atr20_pct_rank_250",
    "direction_num",
    "prior_day_aligned",
    "london_aligned",
    "entry_hour",
    "dow",
    "month",
    "year"
  ],
  "time_column_used": "entry_ts_norm",
  "rows_after_time_parse": 17124,
  "rows_dropped_bad_time": 0
}
```

## Counts

- base_rows: `17124`
- enriched_rows: `17124`
- expected_source_count: `7`
- sources_loaded: `6`
- numeric_sources_loaded: `6`
- templates_created_this_run: `0`
- feature_quality_rows: `195`
- output_feature_cols: `57`

## Source manifest

| source          | path                                                                  | exists   | loaded   |   rows_raw | status           | time_col   | value_col   |   rows_loaded | span                                                  |
|:----------------|:----------------------------------------------------------------------|:---------|:---------|-----------:|:-----------------|:-----------|:------------|--------------:|:------------------------------------------------------|
| dxy             | /Users/vahid/Desktop/xauusd-trader/data/exogenous/dxy.csv             | True     | True     |       1025 | loaded           | timestamp  | close       |          1025 | 2022-05-02 00:00:00+00:00 → 2026-06-05 00:00:00+00:00 |
| us10y           | /Users/vahid/Desktop/xauusd-trader/data/exogenous/us10y.csv           | True     | True     |       1028 | loaded           | timestamp  | close       |          1028 | 2022-05-02 00:00:00+00:00 → 2026-06-11 00:00:00+00:00 |
| real_yield      | /Users/vahid/Desktop/xauusd-trader/data/exogenous/real_yield.csv      | True     | True     |       1028 | loaded           | timestamp  | close       |          1028 | 2022-05-02 00:00:00+00:00 → 2026-06-11 00:00:00+00:00 |
| vix             | /Users/vahid/Desktop/xauusd-trader/data/exogenous/vix.csv             | True     | True     |       1062 | loaded           | timestamp  | close       |          1062 | 2022-05-02 00:00:00+00:00 → 2026-06-11 00:00:00+00:00 |
| spx             | /Users/vahid/Desktop/xauusd-trader/data/exogenous/spx.csv             | True     | True     |       1033 | loaded           | timestamp  | close       |          1033 | 2022-05-02 00:00:00+00:00 → 2026-06-12 00:00:00+00:00 |
| oil             | /Users/vahid/Desktop/xauusd-trader/data/exogenous/oil.csv             | True     | True     |       1023 | loaded           | timestamp  | close       |          1023 | 2022-05-02 00:00:00+00:00 → 2026-06-08 00:00:00+00:00 |
| calendar_events | /Users/vahid/Desktop/xauusd-trader/data/exogenous/calendar_events.csv | True     | False    |        nan | template_present | nan        | nan         |             0 | nan                                                   |

## Feature quality sample

| feature            | gate                      | status           |   coverage |     threshold |   events |    pf_x4 |    pf_x6 |   total_x4 |   total_x6 |   win_rate_x4 |   median_x4 |   rank_score |
|:-------------------|:--------------------------|:-----------------|-----------:|--------------:|---------:|---------:|---------:|-----------:|-----------:|--------------:|------------:|-------------:|
| vix_z60            | vix_z60_le_q20            | numeric_quantile |     0.9908 |   -1.1074     |     3405 | 0.217824 | 0.103577 |   -4456.52 |   -6840.02 |      0.256975 |    -0.8648  |     -44.2438 |
| vix_rank250        | vix_rank250_le_q20        | numeric_quantile |     0.9765 |    0.092      |     3384 | 0.117288 | 0.047308 |   -4463.98 |   -6832.78 |      0.183215 |    -0.78065 |     -44.4752 |
| oil_z60            | oil_z60_le_q20            | numeric_quantile |     0.9908 |   -1.31107    |     3400 | 0.293989 | 0.161011 |   -4530.53 |   -6910.53 |      0.293824 |    -1.08545 |     -44.8503 |
| us10y_rank250      | us10y_rank250_ge_q80      | numeric_quantile |     0.9751 |    0.886      |     3342 | 0.23662  | 0.135204 |   -4568.69 |   -6908.09 |      0.226212 |    -1.4     |     -45.3151 |
| oil_rank250        | oil_rank250_le_q20        | numeric_quantile |     0.9751 |    0.056      |     3362 | 0.336595 | 0.194871 |   -4588.13 |   -6941.53 |      0.332838 |    -1.4     |     -45.3498 |
| oil_ret_5          | oil_ret_5_le_q20          | numeric_quantile |     0.9975 |   -0.0385581  |     3417 | 0.302538 | 0.169887 |   -4593.89 |   -6985.79 |      0.303775 |    -1.4     |     -45.4665 |
| real_yield_ret_1   | real_yield_ret_1_le_q20   | numeric_quantile |     0.9994 |   -0.0223214  |     3436 | 0.238718 | 0.128984 |   -4602.23 |   -7007.43 |      0.243306 |    -1.4     |     -45.6546 |
| oil_chg_5          | oil_chg_5_le_q20          | numeric_quantile |     0.9975 |   -2.97       |     3427 | 0.287652 | 0.160861 |   -4641.68 |   -7040.58 |      0.288591 |    -1.4     |     -45.9683 |
| real_yield_rank250 | real_yield_rank250_ge_q80 | numeric_quantile |     0.9751 |    0.872      |     3360 | 0.204399 | 0.114764 |   -4681.62 |   -7033.62 |      0.197024 |    -1.4     |     -46.497  |
| oil_value          | oil_value_ge_q80          | numeric_quantile |     1      |   85.79       |     3446 | 0.403023 | 0.270077 |   -4718.16 |   -7130.36 |      0.286999 |    -1.4     |     -46.5085 |
| spx_value          | spx_value_le_q20          | numeric_quantile |     1      | 4130.29       |     3427 | 0.050075 | 0.008056 |   -4783.89 |   -7182.79 |      0.194047 |    -1.4     |     -47.7808 |
| spx_ret_1          | spx_ret_1_ge_q80          | numeric_quantile |     0.9994 |    0.00770761 |     3435 | 0.297663 | 0.17345  |   -4840.92 |   -7245.42 |      0.293741 |    -1.4     |     -47.9381 |
| vix_value          | vix_value_le_q20          | numeric_quantile |     1      |   14.35       |     3426 | 0.094237 | 0.03143  |   -4823.78 |   -7221.98 |      0.190601 |    -1.4     |     -48.1122 |
| us10y_value        | us10y_value_le_q20        | numeric_quantile |     1      |    3.74       |     3486 | 0.053963 | 0.008765 |   -4827.35 |   -7267.55 |      0.180149 |    -1.4     |     -48.2108 |
| real_yield_chg_1   | real_yield_chg_1_le_q20   | numeric_quantile |     0.9994 |   -0.04       |     3647 | 0.265894 | 0.14571  |   -4875.31 |   -7428.21 |      0.27173  |    -1.4     |     -48.3415 |
| spx_chg_1          | spx_chg_1_ge_q80          | numeric_quantile |     0.9994 |   41.73       |     3430 | 0.332381 | 0.199746 |   -4900.56 |   -7301.56 |      0.330029 |    -1.4     |     -48.4735 |
| real_yield_value   | real_yield_value_ge_q80   | numeric_quantile |     1      |    2.07       |     3492 | 0.303814 | 0.168642 |   -4914.35 |   -7358.75 |      0.342497 |    -1.4     |     -48.671  |
| oil_ret_5          | oil_ret_5_ge_q80          | numeric_quantile |     0.9975 |    0.037666   |     3417 | 0.363799 | 0.237581 |   -4944.72 |   -7336.62 |      0.29441  |    -1.4     |     -48.8458 |
| spx_chg_5          | spx_chg_5_ge_q80          | numeric_quantile |     0.9975 |   98.47       |     3428 | 0.324478 | 0.194062 |   -4945.42 |   -7345.02 |      0.325554 |    -1.4     |     -48.9357 |
| dxy_rank250        | dxy_rank250_ge_q80        | numeric_quantile |     0.9751 |    0.868      |     3384 | 0.112303 | 0.025957 |   -4924.09 |   -7292.89 |      0.322695 |    -1.4     |     -49.1027 |
| real_yield_value   | real_yield_value_le_q20   | numeric_quantile |     1      |    1.51       |     3523 | 0.048711 | 0.008089 |   -4916.65 |   -7382.75 |      0.173716 |    -1.4     |     -49.1097 |
| real_yield_z60     | real_yield_z60_ge_q80     | numeric_quantile |     0.9908 |    1.47417    |     3403 | 0.268854 | 0.155648 |   -4972.69 |   -7354.79 |      0.277402 |    -1.4     |     -49.3024 |
| real_yield_chg_5   | real_yield_chg_5_le_q20   | numeric_quantile |     0.9975 |   -0.08       |     3478 | 0.190133 | 0.088121 |   -4975.1  |   -7409.7  |      0.276883 |    -1.4     |     -49.4727 |
| real_yield_ret_5   | real_yield_ret_5_le_q20   | numeric_quantile |     0.9975 |   -0.0432432  |     3424 | 0.166838 | 0.074776 |   -4974.75 |   -7371.55 |      0.248248 |    -1.4     |     -49.5059 |
| dxy_chg_1          | dxy_chg_1_ge_q80          | numeric_quantile |     0.9994 |    0.2987     |     3433 | 0.32764  | 0.204305 |   -5004.21 |   -7407.31 |      0.297408 |    -1.4     |     -49.5101 |
| us10y_ret_1        | us10y_ret_1_le_q20        | numeric_quantile |     0.9994 |   -0.0117647  |     3425 | 0.214727 | 0.11278  |   -4990.76 |   -7388.26 |      0.248759 |    -1.4     |     -49.5801 |
| spx_rank250        | spx_rank250_le_q20        | numeric_quantile |     0.9751 |    0.652174   |     3347 | 0.288214 | 0.174396 |   -5006.57 |   -7349.47 |      0.291007 |    -1.4     |     -49.6031 |
| oil_rank250        | oil_rank250_ge_q80        | numeric_quantile |     0.9751 |    0.684      |     3408 | 0.426874 | 0.296993 |   -5036.01 |   -7421.61 |      0.306338 |    -1.4     |     -49.6362 |
| dxy_ret_1          | dxy_ret_1_ge_q80          | numeric_quantile |     0.9994 |    0.00242322 |     3444 | 0.326978 | 0.203807 |   -5019.28 |   -7430.08 |      0.296458 |    -1.4     |     -49.662  |
| oil_chg_5          | oil_chg_5_ge_q80          | numeric_quantile |     0.9975 |    2.83       |     3423 | 0.338409 | 0.220108 |   -5035.78 |   -7431.88 |      0.273736 |    -1.4     |     -49.7993 |

## Interpretation

- Stage31A does not create a tradable strategy; it only builds an exogenous-feature dataset for Stage31B.
- Missing source files are not an error; templates are created under `data/exogenous/`.
- All numerical joins are backward/asof joins, so event rows do not receive future exogenous values.
- Calendar event proximity features are schedule-based proxies and still require careful validation before use.

## Operational reminder

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage31a_exogenous_feature_ingestion
```

## Output files

- `/Users/vahid/Desktop/xauusd-trader/data/reports/stage31a_exogenous_feature_ingestion/stage31a_exogenous_feature_ingestion.json`
- `/Users/vahid/Desktop/xauusd-trader/data/reports/stage31a_exogenous_feature_ingestion/stage31a_exogenous_feature_ingestion.md`
- `/Users/vahid/Desktop/xauusd-trader/data/reports/stage31a_exogenous_feature_ingestion/stage31a_exogenous_ml_dataset.csv`
- `/Users/vahid/Desktop/xauusd-trader/data/reports/stage31a_exogenous_feature_ingestion/stage31a_exogenous_source_manifest.csv`
- `/Users/vahid/Desktop/xauusd-trader/data/reports/stage31a_exogenous_feature_ingestion/stage31a_exogenous_feature_quality.csv`