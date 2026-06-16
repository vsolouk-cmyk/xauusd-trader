# Stage30B ML-lite Feature Ranker / Scorecard

## Decision

```text
STAGE30B_NO_ML_LITE_PROMOTION_KEEP_RESEARCH_OPEN
```

## Scope guardrails

- Research/shadow ML-lite screening only.
- No EA change, no automatic trading, no paper/live/order authorization.
- Consumes Stage30A ML-ready dataset; existing trade artifacts remain research evidence only.
- Uses strict forward-safe feature whitelist and blocks source/stage/candidate fields from modeling.
- direction_num is blocked by default unless STAGE30B_ALLOW_DIRECTION=1.
- Gates are selected on prior training years and evaluated on future test years.

## Dataset

```json
{
  "dataset_path": "data/reports/stage30a_candidate_pool_builder_ml_dataset/stage30a_ml_meta_dataset.csv",
  "loaded": true,
  "rows_raw": 17951,
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
  "rows_after_required_dropna": 17951,
  "rows_after_dedup": 8497,
  "dedup_removed": 9454
}
```

## Base dataset metrics after Stage30B dedup

```json
{
  "events": 8497,
  "pf_x1": 0.807784,
  "pf_x4": 0.33057,
  "pf_x6": 0.192283,
  "total_x4": -11204.42603,
  "win_rate_x4": 0.323055,
  "median_x4": -0.6566,
  "years_positive_x4": 0,
  "year_count": 5
}
```

## Features

- features_used: `prior_day_range, asia_range, asia_eff, london_range, london_eff, h1_range, h1_atr20, h1_atr20_pct_rank_250, entry_hour, dow, month`
- blocked_features: `direction_num, year, source_stage, source_file, family, candidate_name`
- feature_coverage:
```json
{
  "prior_day_range": 1.0,
  "asia_range": 1.0,
  "asia_eff": 1.0,
  "london_range": 1.0,
  "london_eff": 1.0,
  "h1_range": 1.0,
  "h1_atr20": 0.9992,
  "h1_atr20_pct_rank_250": 0.9979,
  "entry_hour": 1.0,
  "dow": 1.0,
  "month": 1.0
}
```

## Counts

- rows_used_after_dedup: `8497`
- years: `[2022, 2023, 2024, 2025, 2026]`
- feature_count: `11`
- selected_gate_rows: `48`
- oos_gate_rows: `49`
- ensemble_rows: `12`
- family_holdout_rows: `18`

## OOS summary

```json
{
  "top1_years_tested": 4,
  "top1_kept_events": 694,
  "top1_pf_x4_median": 0.280478,
  "top1_pf_x6_median": 0.184704,
  "top1_total_x4_sum": -979.081725,
  "ensemble_vote1_years": 4,
  "ensemble_vote1_kept_events": 6901,
  "ensemble_vote1_total_x4_sum": -9026.31894,
  "ensemble_vote1_pf_x4_median": 0.282533,
  "ensemble_vote1_pf_x6_median": 0.139858,
  "ensemble_vote2_years": 4,
  "ensemble_vote2_kept_events": 631,
  "ensemble_vote2_total_x4_sum": -857.47985,
  "ensemble_vote2_pf_x4_median": 0.0,
  "ensemble_vote2_pf_x6_median": 0.0,
  "ensemble_vote3_years": 4,
  "ensemble_vote3_kept_events": 144,
  "ensemble_vote3_total_x4_sum": -195.05921,
  "ensemble_vote3_pf_x4_median": 0.0,
  "ensemble_vote3_pf_x6_median": 0.0
}
```

## Top selected train gates

| year | rank | gate_name | feature | side | threshold | value | train_events | train_pf_x4 | train_pf_x6 | train_total_x4 | train_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2023 | 1 | month_eq_6.0 | month | eq |  | 6.0 | 120 | 0.0437 | 0.0023 | -141.3965 | -0.0981 |
| 2023 | 2 | month_eq_7.0 | month | eq |  | 7.0 | 142 | 0.0569 | 0.0085 | -187.3091 | -0.1489 |
| 2023 | 3 | month_eq_5.0 | month | eq |  | 5.0 | 129 | 0.0761 | 0.0153 | -204.4247 | -0.1767 |
| 2023 | 4 | month_eq_10.0 | month | eq |  | 10.0 | 175 | 0.0632 | 0.0062 | -246.5806 | -0.2234 |
| 2023 | 5 | entry_hour_eq_15.0 | entry_hour | eq |  | 15.0 | 174 | 0.0479 | 0.0053 | -238.7481 | -0.2245 |
| 2023 | 6 | london_range_ge_q80 | london_range | ge | 13.544 |  | 257 | 0.1047 | 0.012 | -322.4191 | -0.2357 |
| 2023 | 7 | month_eq_8.0 | month | eq |  | 8.0 | 186 | 0.0227 | 0.0004 | -239.3006 | -0.2385 |
| 2023 | 8 | month_eq_9.0 | month | eq |  | 9.0 | 186 | 0.0476 | 0.003 | -256.5149 | -0.2471 |
| 2023 | 9 | month_eq_12.0 | month | eq |  | 12.0 | 168 | 0.0127 | 0.0 | -228.6595 | -0.2484 |
| 2023 | 10 | h1_range_ge_q80 | h1_range | ge | 5.514 |  | 257 | 0.0936 | 0.0086 | -330.7499 | -0.2646 |
| 2023 | 11 | month_eq_11.0 | month | eq |  | 11.0 | 178 | 0.0292 | 0.0015 | -251.3654 | -0.265 |
| 2023 | 12 | dow_eq_0.0 | dow | eq |  | 0.0 | 242 | 0.0631 | 0.0129 | -327.5799 | -0.3049 |
| 2024 | 1 | month_eq_1.0 | month | eq |  | 1.0 | 174 | 0.0506 | 0.0031 | -205.3535 | -0.2813 |
| 2024 | 2 | month_eq_2.0 | month | eq |  | 2.0 | 159 | 0.0427 | 0.0026 | -199.4868 | -0.2844 |
| 2024 | 3 | month_eq_4.0 | month | eq |  | 4.0 | 155 | 0.0573 | 0.0112 | -208.0058 | -0.2855 |
| 2024 | 4 | month_eq_3.0 | month | eq |  | 3.0 | 203 | 0.1515 | 0.0396 | -271.0774 | -0.2861 |
| 2024 | 5 | month_eq_6.0 | month | eq |  | 6.0 | 294 | 0.0192 | 0.0009 | -383.726 | -0.6166 |
| 2024 | 6 | month_eq_7.0 | month | eq |  | 7.0 | 306 | 0.0261 | 0.0038 | -421.8198 | -0.6795 |
| 2024 | 7 | month_eq_5.0 | month | eq |  | 5.0 | 306 | 0.0465 | 0.0081 | -454.3692 | -0.7227 |
| 2024 | 8 | month_eq_12.0 | month | eq |  | 12.0 | 331 | 0.0253 | 0.003 | -451.3191 | -0.7284 |
| 2024 | 9 | month_eq_10.0 | month | eq |  | 10.0 | 348 | 0.0414 | 0.0037 | -475.7189 | -0.7532 |
| 2024 | 10 | month_eq_9.0 | month | eq |  | 9.0 | 356 | 0.0254 | 0.0016 | -494.4127 | -0.8039 |
| 2024 | 11 | month_eq_11.0 | month | eq |  | 11.0 | 354 | 0.0186 | 0.0014 | -496.7746 | -0.8163 |
| 2024 | 12 | month_eq_8.0 | month | eq |  | 8.0 | 372 | 0.0119 | 0.0002 | -501.4431 | -0.8247 |
| 2025 | 1 | month_eq_4.0 | month | eq |  | 4.0 | 339 | 0.1517 | 0.0374 | -445.6542 | -0.6337 |
| 2025 | 2 | month_eq_1.0 | month | eq |  | 1.0 | 353 | 0.0387 | 0.0031 | -439.1679 | -0.7418 |
| 2025 | 3 | month_eq_2.0 | month | eq |  | 2.0 | 323 | 0.0198 | 0.0012 | -440.4504 | -0.7722 |
| 2025 | 4 | month_eq_3.0 | month | eq |  | 3.0 | 368 | 0.1056 | 0.0232 | -506.2463 | -0.7979 |
| 2025 | 5 | month_eq_6.0 | month | eq |  | 6.0 | 468 | 0.0782 | 0.0186 | -575.2831 | -0.9377 |
| 2025 | 6 | month_eq_7.0 | month | eq |  | 7.0 | 484 | 0.0604 | 0.0102 | -651.9088 | -1.1072 |

## Yearly OOS gate diagnostics

| year | status | rank | gate_name | test_events | test_pf_x4 | test_pf_x6 | test_total_x4 | test_win_rate_x4 | retained_ratio |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2022 | skipped_insufficient_train_or_test |  |  | 1284 |  |  |  |  |  |
| 2023 | tested | 1.0 | month_eq_6.0 | 174 | 0.0043 | 0.0 | -242.3294 | 0.0287 | 0.0839 |
| 2023 | tested | 2.0 | month_eq_7.0 | 164 | 0.0 | 0.0 | -234.5107 | 0.0 | 0.0791 |
| 2023 | tested | 3.0 | month_eq_5.0 | 177 | 0.0209 | 0.0024 | -249.9445 | 0.0904 | 0.0853 |
| 2023 | tested | 4.0 | month_eq_10.0 | 173 | 0.0169 | 0.0011 | -229.1383 | 0.0694 | 0.0834 |
| 2023 | tested | 5.0 | entry_hour_eq_15.0 | 256 | 0.0246 | 0.0023 | -340.7066 | 0.1094 | 0.1234 |
| 2023 | tested | 6.0 | london_range_ge_q80 | 277 | 0.1639 | 0.0382 | -337.06 | 0.3935 | 0.1336 |
| 2023 | tested | 7.0 | month_eq_8.0 | 186 | 0.0019 | 0.0 | -262.1425 | 0.0108 | 0.0897 |
| 2023 | tested | 8.0 | month_eq_9.0 | 170 | 0.0002 | 0.0 | -237.8978 | 0.0118 | 0.082 |
| 2023 | tested | 9.0 | month_eq_12.0 | 163 | 0.038 | 0.0061 | -222.6596 | 0.135 | 0.0786 |
| 2023 | tested | 10.0 | h1_range_ge_q80 | 257 | 0.1193 | 0.0289 | -334.8927 | 0.3191 | 0.1239 |
| 2023 | tested | 11.0 | month_eq_11.0 | 176 | 0.0075 | 0.0012 | -245.4092 | 0.0114 | 0.0849 |
| 2023 | tested | 12.0 | dow_eq_0.0 | 386 | 0.0472 | 0.016 | -545.5864 | 0.0959 | 0.1861 |
| 2024 | tested | 1.0 | month_eq_1.0 | 179 | 0.0281 | 0.0031 | -233.8144 | 0.1173 | 0.0845 |
| 2024 | tested | 2.0 | month_eq_2.0 | 164 | 0.0 | 0.0 | -240.9636 | 0.0 | 0.0774 |
| 2024 | tested | 3.0 | month_eq_4.0 | 184 | 0.22 | 0.0588 | -237.6483 | 0.4891 | 0.0869 |
| 2024 | tested | 4.0 | month_eq_3.0 | 165 | 0.0461 | 0.0032 | -235.169 | 0.2061 | 0.0779 |
| 2024 | tested | 5.0 | month_eq_6.0 | 174 | 0.1772 | 0.0502 | -191.5571 | 0.3793 | 0.0822 |
| 2024 | tested | 6.0 | month_eq_7.0 | 178 | 0.1175 | 0.0215 | -230.089 | 0.3652 | 0.084 |
| 2024 | tested | 7.0 | month_eq_5.0 | 191 | 0.1541 | 0.0299 | -232.8043 | 0.4398 | 0.0902 |
| 2024 | tested | 8.0 | month_eq_12.0 | 171 | 0.1315 | 0.0166 | -236.547 | 0.4152 | 0.0807 |
| 2024 | tested | 9.0 | month_eq_10.0 | 189 | 0.0912 | 0.0048 | -276.7633 | 0.4021 | 0.0892 |
| 2024 | tested | 10.0 | month_eq_9.0 | 170 | 0.1141 | 0.0087 | -224.8322 | 0.3882 | 0.0803 |
| 2024 | tested | 11.0 | month_eq_11.0 | 171 | 0.2491 | 0.0752 | -234.52 | 0.5029 | 0.0807 |
| 2024 | tested | 12.0 | month_eq_8.0 | 182 | 0.1824 | 0.0434 | -229.7638 | 0.4835 | 0.0859 |
| 2025 | tested | 1.0 | month_eq_4.0 | 173 | 0.5329 | 0.3663 | -233.8728 | 0.5087 | 0.0827 |
| 2025 | tested | 2.0 | month_eq_1.0 | 168 | 0.0816 | 0.003 | -250.9911 | 0.381 | 0.0803 |
| 2025 | tested | 3.0 | month_eq_2.0 | 162 | 0.2488 | 0.0531 | -206.7278 | 0.537 | 0.0774 |
| 2025 | tested | 4.0 | month_eq_3.0 | 182 | 0.2798 | 0.0838 | -221.2796 | 0.544 | 0.087 |
| 2025 | tested | 5.0 | month_eq_6.0 | 161 | 0.3515 | 0.1647 | -227.3311 | 0.5031 | 0.0769 |
| 2025 | tested | 6.0 | month_eq_7.0 | 180 | 0.2405 | 0.0587 | -248.1732 | 0.5111 | 0.086 |
| 2025 | tested | 7.0 | month_eq_5.0 | 183 | 0.5378 | 0.3432 | -212.5585 | 0.541 | 0.0874 |
| 2025 | tested | 8.0 | month_eq_12.0 | 176 | 0.4833 | 0.2998 | -229.6058 | 0.517 | 0.0841 |
| 2025 | tested | 9.0 | month_eq_11.0 | 174 | 0.612 | 0.4317 | -192.7783 | 0.5345 | 0.0831 |
| 2025 | tested | 10.0 | month_eq_8.0 | 167 | 0.1872 | 0.0454 | -239.5373 | 0.4251 | 0.0798 |
| 2025 | tested | 11.0 | month_eq_9.0 | 170 | 0.362 | 0.1717 | -234.5165 | 0.5118 | 0.0812 |
| 2025 | tested | 12.0 | month_eq_10.0 | 197 | 0.6953 | 0.5403 | -210.9738 | 0.5178 | 0.0941 |
| 2026 | tested | 1.0 | month_eq_4.0 | 168 | 0.59 | 0.4598 | -269.0651 | 0.494 | 0.181 |
| 2026 | tested | 2.0 | month_eq_2.0 | 167 | 0.6171 | 0.5288 | -373.9525 | 0.4431 | 0.18 |
| 2026 | tested | 3.0 | month_eq_3.0 | 189 | 0.7701 | 0.6651 | -242.1361 | 0.5079 | 0.2037 |

## Scorecard ensemble OOS

| year | vote_min | kept_events | pf_x4 | pf_x6 | total_x4 | win_rate_x4 | train_events | test_events |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2023.0 | 1.0 | 1762.0 | 0.0338 | 0.0063 | -2385.3999 | 0.1039 | 1284.0 | 2074.0 |
| 2023.0 | 2.0 | 631.0 | 0.0556 | 0.0135 | -857.4798 | 0.1379 | 1284.0 | 2074.0 |
| 2023.0 | 3.0 | 144.0 | 0.1326 | 0.0404 | -195.0592 | 0.2708 | 1284.0 | 2074.0 |
| 2024.0 | 1.0 | 2118.0 | 0.1305 | 0.0265 | -2804.4721 | 0.3527 | 3358.0 | 2118.0 |
| 2024.0 | 2.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 3358.0 | 2118.0 |
| 2024.0 | 3.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 3358.0 | 2118.0 |
| 2025.0 | 1.0 | 2093.0 | 0.4345 | 0.2532 | -2708.3457 | 0.5036 | 5476.0 | 2093.0 |
| 2025.0 | 2.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 5476.0 | 2093.0 |
| 2025.0 | 3.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 5476.0 | 2093.0 |
| 2026.0 | 1.0 | 928.0 | 0.7163 | 0.5857 | -1128.1013 | 0.5151 | 7569.0 | 928.0 |
| 2026.0 | 2.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 7569.0 | 928.0 |
| 2026.0 | 3.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 7569.0 | 928.0 |

## Family/source holdout diagnostics

| holdout_source_stage | holdout_family | holdout_events | vote_min | kept_events | pf_x4 | pf_x6 | total_x4 | win_rate_x4 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| STAGE28A | session_handoff_imbalance_v1 | 3186 | 1 | 3186 | 0.3132 | 0.1787 | -4349.5396 | 0.3384 |
| STAGE28A | volatility_transition_v1 | 2194 | 1 | 2172 | 0.3237 | 0.188 | -2931.0505 | 0.332 |
| STAGE28A | calendar_time_risk_proxy_v1 | 1536 | 1 | 1493 | 0.2745 | 0.1629 | -2183.1414 | 0.2451 |
| STAGE28A | session_compression_expansion_v1 | 868 | 1 | 868 | 0.3671 | 0.2204 | -981.5385 | 0.2408 |
| STAGE29A | high_range_broad_pullback_continuation_v1 | 309 | 1 | 309 | 0.4267 | 0.2586 | -391.5077 | 0.4919 |
| STAGE28A | liquidity_sweep_regime_v1 | 164 | 1 | 164 | 0.1405 | 0.0743 | -306.0227 | 0.2134 |
| STAGE25C | london_oneway_continuation | 100 | 1 | 100 | 2.8514 | 1.6534 | 127.6156 | 0.81 |
| STAGE28B | london_oneway_continuation | 100 | 1 | 100 | 2.8514 | 1.6534 | 127.6156 | 0.81 |
| STAGE29A | high_range_london_breakout_follow_v1 | 40 | 1 | 40 | 0.0066 | 0.0009 | -246.9376 | 0.075 |
| STAGE28A | volatility_transition_v1 | 2194 | 2 | 1722 | 0.35 | 0.2082 | -2257.0946 | 0.3362 |
| STAGE28A | calendar_time_risk_proxy_v1 | 1536 | 2 | 991 | 0.2654 | 0.1606 | -1486.4215 | 0.217 |
| STAGE25C | london_oneway_continuation | 100 | 2 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| STAGE28A | liquidity_sweep_regime_v1 | 164 | 2 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| STAGE28A | session_compression_expansion_v1 | 868 | 2 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| STAGE28A | session_handoff_imbalance_v1 | 3186 | 2 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| STAGE28B | london_oneway_continuation | 100 | 2 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| STAGE29A | high_range_broad_pullback_continuation_v1 | 309 | 2 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| STAGE29A | high_range_london_breakout_follow_v1 | 40 | 2 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |

## Interpretation

- Stage30B is a ML-lite scorecard/gate ranker, not a tradable strategy.
- Because the candidate pool contains many weak raw-entry artifacts, family/source holdout is critical.
- If a scorecard candidate appears here, the next stage must validate it on a stricter deduped pool and then create a separate forward-shadow tracker.
- If no scorecard survives, the next useful step is adding exogenous/macro/news features, not adding higher-capacity ML to the same OHLC-only features.

## Operational reminder

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage30a_candidate_pool_builder_ml_dataset
python3 -m app.stage30b_ml_lite_feature_ranker
```

## Output files

- `/Users/vahid/Desktop/xauusd-trader/data/reports/stage30b_ml_lite_feature_ranker/stage30b_ml_lite_feature_ranker.json`
- `/Users/vahid/Desktop/xauusd-trader/data/reports/stage30b_ml_lite_feature_ranker/stage30b_ml_lite_feature_ranker.md`
- `/Users/vahid/Desktop/xauusd-trader/data/reports/stage30b_ml_lite_feature_ranker/stage30b_yearly_oos_gate_results.csv`
- `/Users/vahid/Desktop/xauusd-trader/data/reports/stage30b_ml_lite_feature_ranker/stage30b_selected_train_gates.csv`
- `/Users/vahid/Desktop/xauusd-trader/data/reports/stage30b_ml_lite_feature_ranker/stage30b_scorecard_ensemble_oos.csv`
- `/Users/vahid/Desktop/xauusd-trader/data/reports/stage30b_ml_lite_feature_ranker/stage30b_scorecard_predictions.csv`
- `/Users/vahid/Desktop/xauusd-trader/data/reports/stage30b_ml_lite_feature_ranker/stage30b_family_holdout.csv`