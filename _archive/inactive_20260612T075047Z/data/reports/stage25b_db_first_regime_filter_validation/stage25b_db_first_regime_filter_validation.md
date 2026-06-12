# Stage25B DB-First Regime Filter Validation

Generated UTC: `2026-06-11T17:00:23.745297+00:00`

## Decision

```text
STAGE25B_DB_FIRST_HAS_FILTER_CANDIDATE_REVIEW_ONLY
```

## Scope guardrails

- Research/shadow diagnostic only.
- Stage18A v2 remains unchanged.
- Stage23D remains unchanged.
- No EA change, no automatic trading, no paper/live/order authorization.
- AMarkets CSV fallback is intentionally disabled; candles are DB-first.

## DB source of truth

- db_path: `/Users/vahid/Desktop/xauusd-trader/data/local/xauusd_local_store.sqlite`
- m1_table: `bars`
- m1_mode: `db_schema_introspection`
- m1_rows: `1532440`
- m1_span: `2022-05-01 23:01:00+00:00 → 2026-06-11 17:15:00+00:00`
- h1_table: `bars`
- h1_mode: `db_schema_introspection`
- h1_rows: `25579`
- h1_span: `2022-05-01 23:00:00+00:00 → 2026-06-11 17:00:00+00:00`
- m15_rows_derived_from_m1: `102237`

## Base Stage23C trade metrics, DB-derived features

```json
{
  "events": 468,
  "pf_x1": 5.86384088059708,
  "pf_x4": 2.8795789427487484,
  "pf_x6": 1.6681425688004845,
  "total_x1": 1102.9809300000002,
  "total_x4": 611.58093,
  "total_x6": 283.98093000000017,
  "win_rate_x4": 0.7799145299145299,
  "median_x4": 1.0094300000000005
}
```

## Top DB-first filter diagnostics

| decision | filter_name | retained_events | retained_ratio | pf_x1 | pf_x4 | pf_x6 | improvement_pf_x4 | improvement_pf_x6 | total_x4 | win_rate_x4 | median_x4 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | keep_short_only | 204 | 0.4359 | 10.7117 | 5.5659 | 3.3384 | 2.6863 | 1.6703 | 473.7086 | 0.8284 | 1.0523 |
| STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | london_range_drop_low30 | 327 | 0.6987 | 10.1321 | 5.4259 | 3.4502 | 2.5463 | 1.782 | 723.7062 | 0.8593 | 1.417 |
| STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | early_ny_range_drop_low30 | 327 | 0.6987 | 9.6215 | 5.0731 | 3.1613 | 2.1935 | 1.4931 | 703.0122 | 0.8318 | 1.4054 |
| STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | asia_range_drop_low30 | 327 | 0.6987 | 8.7209 | 4.7405 | 3.0685 | 1.8609 | 1.4004 | 700.2469 | 0.844 | 1.4054 |
| STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | early_ny_range_drop_low20 | 375 | 0.8013 | 8.8897 | 4.5895 | 2.7408 | 1.7099 | 1.0727 | 707.58 | 0.8373 | 1.1886 |
| STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | london_range_drop_low20 | 375 | 0.8013 | 8.4011 | 4.3524 | 2.6329 | 1.4728 | 0.9648 | 697.9223 | 0.8293 | 1.1886 |
| STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | prior_day_range_drop_low30 | 327 | 0.6987 | 7.5756 | 3.8802 | 2.3816 | 1.0006 | 0.7135 | 601.8664 | 0.8073 | 1.1054 |
| STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | asia_range_drop_low20 | 375 | 0.8013 | 7.2126 | 3.7925 | 2.3721 | 0.9129 | 0.704 | 670.7276 | 0.8133 | 1.1886 |
| STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | london_eff_middle_30_70 | 192 | 0.4103 | 7.0011 | 3.636 | 2.2983 | 0.7564 | 0.6302 | 374.2461 | 0.7708 | 1.1886 |
| STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | prior_day_range_drop_low20 | 378 | 0.8077 | 6.4336 | 3.2706 | 1.9436 | 0.391 | 0.2755 | 582.1856 | 0.7857 | 1.0407 |
| STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | london_eff_drop_low30 | 330 | 0.7051 | 6.3457 | 3.1873 | 1.9258 | 0.3078 | 0.2577 | 514.0509 | 0.7697 | 1.1496 |
| STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | london_eff_drop_low20 | 375 | 0.8013 | 6.2932 | 3.1507 | 1.8747 | 0.2711 | 0.2066 | 560.4885 | 0.7813 | 1.078 |
| STAGE25B_REJECT | diagnostic_drop_year_2022 | 351 | 0.75 | 7.4946 | 3.8824 | 2.3903 | 1.0028 | 0.7222 | 647.3206 | 0.7892 | 1.1787 |
| STAGE25B_REJECT | diagnostic_drop_year_2023 | 357 | 0.7628 | 6.7843 | 3.593 | 2.2144 | 0.7134 | 0.5463 | 619.9431 | 0.8039 | 1.1496 |
| STAGE25B_REJECT | london_eff_middle_20_80 | 285 | 0.609 | 6.0876 | 3.0431 | 1.8153 | 0.1635 | 0.1472 | 427.2931 | 0.7614 | 1.087 |
| STAGE25B_REJECT | london_eff_drop_high30 | 330 | 0.7051 | 6.0589 | 3.0305 | 1.7919 | 0.1509 | 0.1238 | 471.7761 | 0.7848 | 1.0313 |
| STAGE25B_REJECT | early_ny_range_middle_30_70 | 189 | 0.4038 | 7.2808 | 3.1468 | 1.5373 | 0.2672 | -0.1309 | 194.6067 | 0.8519 | 1.1886 |
| STAGE25B_REJECT | keep_prior_day_aligned | 255 | 0.5449 | 5.2972 | 2.8677 | 1.8166 | -0.0119 | 0.1484 | 401.2467 | 0.7647 | 0.9229 |
| STAGE25B_REJECT | keep_entry_hour_13 | 468 | 1 | 5.8638 | 2.8796 | 1.6681 | 0 | 0 | 611.5809 | 0.7799 | 1.0094 |
| STAGE25B_REJECT | keep_london_aligned | 468 | 1 | 5.8638 | 2.8796 | 1.6681 | 0 | 0 | 611.5809 | 0.7799 | 1.0094 |
| STAGE25B_REJECT | diagnostic_drop_year_2024 | 339 | 0.7244 | 5.5182 | 2.8136 | 1.7182 | -0.066 | 0.0501 | 493.737 | 0.7522 | 0.8534 |
| STAGE25B_REJECT | drop_prior_day_aligned | 213 | 0.4551 | 7.1046 | 2.9027 | 1.4022 | 0.0231 | -0.2659 | 210.3342 | 0.7981 | 1.0313 |
| STAGE25B_REJECT | london_eff_drop_high20 | 378 | 0.8077 | 5.6238 | 2.7465 | 1.5877 | -0.1331 | -0.0804 | 478.3855 | 0.7646 | 0.9229 |
| STAGE25B_REJECT | diagnostic_drop_year_2025 | 375 | 0.8013 | 5.5937 | 2.4941 | 1.2972 | -0.3855 | -0.3709 | 358.9457 | 0.784 | 0.8483 |
| STAGE25B_REJECT | early_ny_range_middle_20_80 | 282 | 0.6026 | 5.2314 | 2.2589 | 1.0574 | -0.6207 | -0.6107 | 209.5783 | 0.8369 | 1.078 |
| STAGE25B_REJECT | diagnostic_drop_year_2026 | 450 | 0.9615 | 4.5228 | 2.0031 | 1.0268 | -0.8765 | -0.6414 | 326.3774 | 0.7711 | 0.9066 |
| STAGE25B_REJECT | asia_range_middle_30_70 | 189 | 0.4038 | 4.6397 | 1.9148 | 0.8124 | -0.9648 | -0.8558 | 105.631 | 0.836 | 1.087 |
| STAGE25B_REJECT | london_range_middle_30_70 | 186 | 0.3974 | 4.581 | 1.7761 | 0.6832 | -1.1035 | -0.985 | 86.1738 | 0.8333 | 0.9914 |
| STAGE25B_REJECT | keep_long_only | 264 | 0.5641 | 3.6618 | 1.6221 | 0.8345 | -1.2575 | -0.8337 | 137.8724 | 0.7424 | 0.8641 |
| STAGE25B_REJECT | asia_range_middle_20_80 | 282 | 0.6026 | 3.6936 | 1.4814 | 0.6167 | -1.3982 | -1.0515 | 99.153 | 0.7872 | 1.0274 |
| STAGE25B_REJECT | early_ny_range_drop_high30 | 330 | 0.7051 | 3.6769 | 1.4238 | 0.6026 | -1.4557 | -1.0656 | 103.1754 | 0.7697 | 0.8483 |
| STAGE25B_REJECT | london_range_middle_20_80 | 282 | 0.6026 | 3.5952 | 1.4232 | 0.5751 | -1.4564 | -1.093 | 86.6997 | 0.7872 | 0.9914 |
| STAGE25B_REJECT | early_ny_range_drop_high20 | 375 | 0.8013 | 3.4546 | 1.3854 | 0.6095 | -1.4942 | -1.0586 | 113.5793 | 0.7653 | 0.8641 |
| STAGE25B_REJECT | prior_day_range_middle_30_70 | 186 | 0.3974 | 3.1014 | 1.3143 | 0.6515 | -1.5652 | -1.0167 | 53.2847 | 0.7366 | 0.5573 |
| STAGE25B_REJECT | prior_day_range_drop_high20 | 375 | 0.8013 | 3.2049 | 1.3156 | 0.6105 | -1.5639 | -1.0576 | 100.6246 | 0.736 | 0.6953 |

## Stage25A vs Stage25B comparison

| filter_name | decision | stage25a_pf_x4 | stage25b_pf_x4 | delta_pf_x4_b_minus_a | stage25a_pf_x6 | stage25b_pf_x6 | delta_pf_x6_b_minus_a | stage25a_retained_events | stage25b_retained_events |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| keep_short_only | STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | 5.5659 | 5.5659 | 0 | 3.3384 | 3.3384 | -0 | 204 | 204 |
| london_range_drop_low30 | STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | 5.4259 | 5.4259 | 0 | 3.4502 | 3.4502 | 0 | 327 | 327 |
| early_ny_range_drop_low30 | STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | 4.4172 | 5.0731 | 0.6559 | 2.8479 | 3.1613 | 0.3134 | 330 | 327 |
| asia_range_drop_low30 | STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | 4.7405 | 4.7405 | 0 | 3.0685 | 3.0685 | 0 | 327 | 327 |
| early_ny_range_drop_low20 | STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | 4.1271 | 4.5895 | 0.4625 | 2.5426 | 2.7408 | 0.1983 | 375 | 375 |
| london_range_drop_low20 | STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | 4.3524 | 4.3524 | 0 | 2.6329 | 2.6329 | 0 | 375 | 375 |
| prior_day_range_drop_low30 | STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | 3.8335 | 3.8802 | 0.0467 | 2.4569 | 2.3816 | -0.0753 | 330 | 327 |
| asia_range_drop_low20 | STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | 3.7925 | 3.7925 | -0 | 2.3721 | 2.3721 | 0 | 375 | 375 |
| london_eff_middle_30_70 | STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | 3.636 | 3.636 | 0 | 2.2983 | 2.2983 | -0 | 192 | 192 |
| prior_day_range_drop_low20 | STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | 3.3996 | 3.2706 | -0.129 | 2.1023 | 1.9436 | -0.1587 | 375 | 378 |
| london_eff_drop_low30 | STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | 3.1873 | 3.1873 | 0 | 1.9258 | 1.9258 | 0 | 330 | 330 |
| london_eff_drop_low20 | STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | 3.1507 | 3.1507 | 0 | 1.8747 | 1.8747 | 0 | 375 | 375 |
| diagnostic_drop_year_2022 | STAGE25B_REJECT | 3.8824 | 3.8824 | -0 | 2.3903 | 2.3903 | 0 | 351 | 351 |
| diagnostic_drop_year_2023 | STAGE25B_REJECT | 3.593 | 3.593 | 0 | 2.2144 | 2.2144 | 0 | 357 | 357 |
| london_eff_middle_20_80 | STAGE25B_REJECT | 3.0431 | 3.0431 | -0 | 1.8153 | 1.8153 | 0 | 285 | 285 |
| london_eff_drop_high30 | STAGE25B_REJECT | 3.0305 | 3.0305 | 0 | 1.7919 | 1.7919 | 0 | 330 | 330 |
| early_ny_range_middle_30_70 | STAGE25B_REJECT | 1.8798 | 3.1468 | 1.267 | 0.9101 | 1.5373 | 0.6272 | 189 | 189 |
| keep_prior_day_aligned | STAGE25B_REJECT | 2.6253 | 2.8677 | 0.2424 | 1.5534 | 1.8166 | 0.2632 | 237 | 255 |
| keep_entry_hour_13 | STAGE25B_REJECT | 2.8796 | 2.8796 | 0 | 1.6681 | 1.6681 | 0 | 468 | 468 |
| keep_london_aligned | STAGE25B_REJECT | 2.8796 | 2.8796 | 0 | 1.6681 | 1.6681 | 0 | 468 | 468 |
| diagnostic_drop_year_2024 | STAGE25B_REJECT | 2.8136 | 2.8136 | 0 | 1.7182 | 1.7182 | 0 | 339 | 339 |
| drop_prior_day_aligned | STAGE25B_REJECT | 3.1983 | 2.9027 | -0.2956 | 1.8057 | 1.4022 | -0.4035 | 231 | 213 |
| london_eff_drop_high20 | STAGE25B_REJECT | 2.7465 | 2.7465 | 0 | 1.5877 | 1.5877 | 0 | 378 | 378 |
| diagnostic_drop_year_2025 | STAGE25B_REJECT | 2.4941 | 2.4941 | 0 | 1.2972 | 1.2972 | 0 | 375 | 375 |
| early_ny_range_middle_20_80 | STAGE25B_REJECT | 1.8382 | 2.2589 | 0.4207 | 0.8378 | 1.0574 | 0.2197 | 282 | 282 |

## Interpretation

- This module validates Stage25A-style filters using SQLite candles as source of truth.
- Stage23C exact trade artifact is still used as the trade list; candle/regime features are rebuilt from DB.
- Any filter candidate remains research-only and requires separate forward-shadow validation.
- If filter candidates survive here, the next step is a DB-first filtered Stage23D tracker, not EA/paper/live.

## Operational reminder

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage18a_unified_shadow_ops_cycle
cat data/reports/stage18a_unified_shadow_ops_cycle/stage18a_unified_shadow_ops_cycle.md

python3 -m app.stage23d_forward_shadow_candidate
cat data/reports/stage23d_forward_shadow_candidate/stage23d_forward_shadow_candidate.md
```

## Output files

- `data/reports/stage25b_db_first_regime_filter_validation/stage25b_db_first_regime_filter_validation.json`
- `data/reports/stage25b_db_first_regime_filter_validation/stage25b_db_first_regime_filter_validation.md`
- `data/reports/stage25b_db_first_regime_filter_validation/stage25b_filter_candidates.csv`
- `data/reports/stage25b_db_first_regime_filter_validation/stage25b_enriched_stage23c_trades.csv`
- `data/reports/stage25b_db_first_regime_filter_validation/stage25b_stage25a_comparison.csv`
- `data/reports/stage25b_db_first_regime_filter_validation/stage25b_db_schema_diagnostic.csv`