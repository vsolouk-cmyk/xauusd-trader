# Stage25C De-duplicated DB-First Filter Validation

Generated UTC: `2026-06-11T17:05:24.774346+00:00`

## Decision

```text
STAGE25C_DEDUPED_HAS_FILTER_CANDIDATE_REVIEW_ONLY
```

## Scope guardrails

- Research/shadow diagnostic only.
- Stage18A v2 remains unchanged.
- Stage23D remains unchanged.
- No EA change, no automatic trading, no paper/live/order authorization.
- AMarkets CSV fallback is intentionally disabled; candle/regime features are DB-first.
- Stage23C trade artifact is used only as the historical trade list; duplicate variants are not treated as independent evidence.

## DB source of truth

- db_path: `/Users/vahid/Desktop/xauusd-trader/data/local/xauusd_local_store.sqlite`
- candle_table: `bars`
- m1_mode: `db_schema_introspection`
- m1_rows: `1532440`
- m1_span: `2022-05-01 23:01:00+00:00 → 2026-06-11 17:15:00+00:00`
- h1_mode: `db_schema_introspection`
- h1_rows: `25579`
- h1_span: `2022-05-01 23:00:00+00:00 → 2026-06-11 17:00:00+00:00`

## Canonical trade selection

- selection_mode: `exact_candidate_name`
- requested_candidate: `S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65`
- available_candidate_count: `6`
- canonical_rows_before_event_dedup: `100`
- canonical_rows_after_event_dedup: `100`
- available_candidates_sample: `S23B_A_dup_pb0.3_eff0.72_h180_tp0.6_sl0.65, S23B_A_h90_sensitivity_eff0.72_tp0.6_sl0.65, S23B_A_pb0.1_eff0.72_h180_tp0.6_sl0.65, S23B_B_dup_pb0.3_eff0.60_h180_tp0.6_sl0.65, S23B_B_h90_sensitivity_eff0.60_tp0.6_sl0.65, S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65`

## Base canonical Stage23C metrics, DB-derived features

```json
{
  "base_events": 100,
  "base_pf_x1": 5.578963613461408,
  "base_pf_x4": 2.851412305366161,
  "base_pf_x6": 1.653421789024173,
  "base_total_x4": 127.61561,
  "base_win_rate_x4": 0.81,
  "base_median_x4": 1.0293600000000005
}
```

## Top de-duplicated filter diagnostics

| decision | filter_name | retained_events | retained_ratio | pf_x1 | pf_x4 | pf_x6 | improvement_pf_x4 | improvement_pf_x6 | total_x4 | win_rate_x4 | median_x4 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| STAGE25C_DEDUPED_FILTER_CANDIDATE_REVIEW_ONLY | london_and_early_ny_range_drop_low30 | 56 | 0.56 | 9.9902 | 5.9911 | 4.1186 | 3.1397 | 2.4652 | 144.0754 | 0.8929 | 1.7367 |
| STAGE25C_DEDUPED_FILTER_CANDIDATE_REVIEW_ONLY | london_range_drop_low30 | 70 | 0.7 | 8.5804 | 4.9235 | 3.2017 | 2.072 | 1.5483 | 147.1729 | 0.8857 | 1.3677 |
| STAGE25C_DEDUPED_FILTER_CANDIDATE_REVIEW_ONLY | keep_short_only | 45 | 0.45 | 8.7853 | 4.8171 | 2.9188 | 1.9657 | 1.2654 | 92.9491 | 0.8444 | 1.0471 |
| STAGE25C_DEDUPED_FILTER_CANDIDATE_REVIEW_ONLY | asia_range_drop_low30 | 70 | 0.7 | 7.665 | 4.411 | 2.8976 | 1.5596 | 1.2442 | 143.07 | 0.8714 | 1.3677 |
| STAGE25C_DEDUPED_FILTER_CANDIDATE_REVIEW_ONLY | london_range_drop_low20 | 80 | 0.8 | 7.7619 | 4.2566 | 2.6145 | 1.4052 | 0.9611 | 145.4816 | 0.8625 | 1.1836 |
| STAGE25C_DEDUPED_FILTER_CANDIDATE_REVIEW_ONLY | early_ny_range_drop_low30 | 70 | 0.7 | 7.4572 | 4.1589 | 2.6536 | 1.3075 | 1.0002 | 136.7837 | 0.8429 | 1.2912 |
| STAGE25C_DEDUPED_FILTER_CANDIDATE_REVIEW_ONLY | prior_day_range_drop_low30 | 70 | 0.7 | 7.5472 | 4.0135 | 2.4606 | 1.1621 | 0.8072 | 127.173 | 0.8429 | 1.0962 |
| STAGE25C_DEDUPED_FILTER_CANDIDATE_REVIEW_ONLY | early_ny_range_drop_low20 | 80 | 0.8 | 7.313 | 3.9704 | 2.4355 | 1.119 | 0.7821 | 140.7613 | 0.85 | 1.1504 |
| STAGE25C_DEDUPED_FILTER_CANDIDATE_REVIEW_ONLY | asia_range_drop_low20 | 80 | 0.8 | 6.592 | 3.6335 | 2.289 | 0.782 | 0.6356 | 137.6988 | 0.8375 | 1.1836 |
| STAGE25C_DEDUPED_FILTER_CANDIDATE_REVIEW_ONLY | prior_day_range_drop_low20 | 80 | 0.8 | 6.7966 | 3.5637 | 2.092 | 0.7123 | 0.4386 | 125.8072 | 0.825 | 1.0439 |
| STAGE25C_DEDUPED_FILTER_CANDIDATE_REVIEW_ONLY | london_eff_drop_low20 | 80 | 0.8 | 6.6988 | 3.4232 | 1.997 | 0.5718 | 0.3436 | 120.6795 | 0.825 | 1.0626 |
| STAGE25C_DEDUPED_FILTER_CANDIDATE_REVIEW_ONLY | london_eff_drop_low30 | 70 | 0.7 | 6.5145 | 3.4121 | 2.0545 | 0.5607 | 0.4011 | 112.1797 | 0.8143 | 1.0962 |
| STAGE25C_DEDUPED_FILTER_CANDIDATE_REVIEW_ONLY | london_eff_drop_high30 | 70 | 0.7 | 6.2731 | 3.2613 | 1.9065 | 0.4098 | 0.2531 | 101.0755 | 0.8286 | 1.0294 |
| STAGE25C_REJECT | short_and_london_range_drop_low30 | 32 | 0.32 | 14.5799 | 8.6683 | 5.8916 | 5.8169 | 4.2382 | 99.0721 | 0.9062 | 1.4112 |
| STAGE25C_REJECT | short_and_early_ny_range_drop_low30 | 31 | 0.31 | 13.8832 | 8.2769 | 5.4425 | 5.4255 | 3.7891 | 94.9245 | 0.9032 | 1.33 |
| STAGE25C_REJECT | short_and_asia_range_drop_low30 | 31 | 0.31 | 10.6401 | 6.4163 | 4.5131 | 3.5649 | 2.8597 | 93.6597 | 0.871 | 1.417 |
| STAGE25C_REJECT | drop_prior_day_aligned | 46 | 0.46 | 7.1635 | 3.2933 | 1.6687 | 0.4419 | 0.0153 | 52.4896 | 0.8478 | 1.0763 |
| STAGE25C_REJECT | london_eff_drop_high20 | 80 | 0.8 | 5.7997 | 2.995 | 1.7402 | 0.1436 | 0.0868 | 107.3002 | 0.8125 | 1.036 |
| STAGE25C_REJECT | keep_london_aligned | 100 | 1.0 | 5.579 | 2.8514 | 1.6534 | 0.0 | 0.0 | 127.6156 | 0.81 | 1.0294 |
| STAGE25C_REJECT | keep_prior_day_aligned | 54 | 0.54 | 4.8268 | 2.6317 | 1.6454 | -0.2197 | -0.008 | 75.126 | 0.7778 | 0.9066 |
| STAGE25C_REJECT | keep_long_only | 55 | 0.55 | 3.8182 | 1.7777 | 0.9317 | -1.0738 | -0.7217 | 34.6665 | 0.7818 | 0.9914 |
| STAGE25C_REJECT | early_ny_range_drop_high20 | 80 | 0.8 | 3.6545 | 1.5131 | 0.657 | -1.3383 | -0.9964 | 30.1719 | 0.8 | 0.9066 |
| STAGE25C_REJECT | early_ny_range_drop_high30 | 70 | 0.7 | 3.6677 | 1.4783 | 0.618 | -1.3732 | -1.0354 | 24.0342 | 0.8 | 0.8562 |
| STAGE25C_REJECT | asia_range_drop_high20 | 80 | 0.8 | 3.8437 | 1.4247 | 0.5139 | -1.4267 | -1.1395 | 22.2261 | 0.8 | 0.8474 |
| STAGE25C_REJECT | prior_day_range_drop_high20 | 80 | 0.8 | 3.0081 | 1.2613 | 0.5692 | -1.5901 | -1.0842 | 18.012 | 0.7625 | 0.7334 |
| STAGE25C_REJECT | asia_range_drop_high30 | 70 | 0.7 | 3.4175 | 1.1689 | 0.3612 | -1.6825 | -1.2922 | 8.0513 | 0.7857 | 0.6859 |
| STAGE25C_REJECT | prior_day_range_drop_high30 | 70 | 0.7 | 2.8518 | 1.1659 | 0.5086 | -1.6855 | -1.1448 | 10.1533 | 0.7571 | 0.6514 |
| STAGE25C_REJECT | london_range_drop_high20 | 80 | 0.8 | 3.0188 | 1.1182 | 0.3987 | -1.7333 | -1.2547 | 7.3652 | 0.775 | 0.7722 |
| STAGE25C_REJECT | london_range_drop_high30 | 70 | 0.7 | 2.6814 | 0.9233 | 0.2881 | -1.9281 | -1.3653 | -4.3804 | 0.7571 | 0.6514 |
| STAGE25C_REJECT | drop_london_aligned | 0 | 0.0 | 0.0 | 0.0 | 0.0 | -2.8514 | -1.6534 | 0.0 | 0.0 | 0.0 |

## Stage25B aggregate vs Stage25C de-duplicated comparison

| filter_name | decision_stage25c | decision_stage25b | pf_x4_stage25c | pf_x4_stage25b | delta_pf_x4_c_minus_b | pf_x6_stage25c | pf_x6_stage25b | delta_pf_x6_c_minus_b | retained_events_stage25c | retained_events_stage25b |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| london_and_early_ny_range_drop_low30 | STAGE25C_DEDUPED_FILTER_CANDIDATE_REVIEW_ONLY |  | 5.9911 |  |  | 4.1186 |  |  | 56 |  |
| london_range_drop_low30 | STAGE25C_DEDUPED_FILTER_CANDIDATE_REVIEW_ONLY | STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | 4.9235 | 5.4259 | -0.5024 | 3.2017 | 3.4502 | -0.2485 | 70 | 327.0 |
| keep_short_only | STAGE25C_DEDUPED_FILTER_CANDIDATE_REVIEW_ONLY | STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | 4.8171 | 5.5659 | -0.7487 | 2.9188 | 3.3384 | -0.4196 | 45 | 204.0 |
| asia_range_drop_low30 | STAGE25C_DEDUPED_FILTER_CANDIDATE_REVIEW_ONLY | STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | 4.411 | 4.7405 | -0.3295 | 2.8976 | 3.0685 | -0.1709 | 70 | 327.0 |
| london_range_drop_low20 | STAGE25C_DEDUPED_FILTER_CANDIDATE_REVIEW_ONLY | STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | 4.2566 | 4.3524 | -0.0958 | 2.6145 | 2.6329 | -0.0184 | 80 | 375.0 |
| early_ny_range_drop_low30 | STAGE25C_DEDUPED_FILTER_CANDIDATE_REVIEW_ONLY | STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | 4.1589 | 5.0731 | -0.9142 | 2.6536 | 3.1613 | -0.5077 | 70 | 327.0 |
| prior_day_range_drop_low30 | STAGE25C_DEDUPED_FILTER_CANDIDATE_REVIEW_ONLY | STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | 4.0135 | 3.8802 | 0.1333 | 2.4606 | 2.3816 | 0.079 | 70 | 327.0 |
| early_ny_range_drop_low20 | STAGE25C_DEDUPED_FILTER_CANDIDATE_REVIEW_ONLY | STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | 3.9704 | 4.5895 | -0.6192 | 2.4355 | 2.7408 | -0.3053 | 80 | 375.0 |
| asia_range_drop_low20 | STAGE25C_DEDUPED_FILTER_CANDIDATE_REVIEW_ONLY | STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | 3.6335 | 3.7925 | -0.159 | 2.289 | 2.3721 | -0.0831 | 80 | 375.0 |
| prior_day_range_drop_low20 | STAGE25C_DEDUPED_FILTER_CANDIDATE_REVIEW_ONLY | STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | 3.5637 | 3.2706 | 0.2931 | 2.092 | 1.9436 | 0.1484 | 80 | 378.0 |
| london_eff_drop_low20 | STAGE25C_DEDUPED_FILTER_CANDIDATE_REVIEW_ONLY | STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | 3.4232 | 3.1507 | 0.2725 | 1.997 | 1.8747 | 0.1223 | 80 | 375.0 |
| london_eff_drop_low30 | STAGE25C_DEDUPED_FILTER_CANDIDATE_REVIEW_ONLY | STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY | 3.4121 | 3.1873 | 0.2248 | 2.0545 | 1.9258 | 0.1287 | 70 | 330.0 |
| london_eff_drop_high30 | STAGE25C_DEDUPED_FILTER_CANDIDATE_REVIEW_ONLY | STAGE25B_REJECT | 3.2613 | 3.0305 | 0.2308 | 1.9065 | 1.7919 | 0.1146 | 70 | 330.0 |
| short_and_london_range_drop_low30 | STAGE25C_REJECT |  | 8.6683 |  |  | 5.8916 |  |  | 32 |  |
| short_and_early_ny_range_drop_low30 | STAGE25C_REJECT |  | 8.2769 |  |  | 5.4425 |  |  | 31 |  |
| short_and_asia_range_drop_low30 | STAGE25C_REJECT |  | 6.4163 |  |  | 4.5131 |  |  | 31 |  |
| drop_prior_day_aligned | STAGE25C_REJECT | STAGE25B_REJECT | 3.2933 | 2.9027 | 0.3906 | 1.6687 | 1.4022 | 0.2665 | 46 | 213.0 |
| london_eff_drop_high20 | STAGE25C_REJECT | STAGE25B_REJECT | 2.995 | 2.7465 | 0.2485 | 1.7402 | 1.5877 | 0.1525 | 80 | 378.0 |
| keep_london_aligned | STAGE25C_REJECT | STAGE25B_REJECT | 2.8514 | 2.8796 | -0.0282 | 1.6534 | 1.6681 | -0.0147 | 100 | 468.0 |
| keep_prior_day_aligned | STAGE25C_REJECT | STAGE25B_REJECT | 2.6317 | 2.8677 | -0.2359 | 1.6454 | 1.8166 | -0.1712 | 54 | 255.0 |
| keep_long_only | STAGE25C_REJECT | STAGE25B_REJECT | 1.7777 | 1.6221 | 0.1556 | 0.9317 | 0.8345 | 0.0972 | 55 | 264.0 |
| early_ny_range_drop_high20 | STAGE25C_REJECT | STAGE25B_REJECT | 1.5131 | 1.3854 | 0.1277 | 0.657 | 0.6095 | 0.0475 | 80 | 375.0 |
| early_ny_range_drop_high30 | STAGE25C_REJECT | STAGE25B_REJECT | 1.4783 | 1.4238 | 0.0544 | 0.618 | 0.6026 | 0.0154 | 70 | 330.0 |
| asia_range_drop_high20 | STAGE25C_REJECT | STAGE25B_REJECT | 1.4247 | 1.1374 | 0.2873 | 0.5139 | 0.4203 | 0.0936 | 80 | 375.0 |
| prior_day_range_drop_high20 | STAGE25C_REJECT | STAGE25B_REJECT | 1.2613 | 1.3156 | -0.0543 | 0.5692 | 0.6105 | -0.0414 | 80 | 375.0 |

## Interpretation

- This module checks whether Stage25B's strong filters survive after de-duplicating the Stage23C evidence to one canonical Stage23B/C candidate.
- `keep_short_only` is useful diagnostically, but it is a direction filter, not a market-regime filter by itself.
- A robust next filter should ideally survive on the canonical candidate and remain interpretable, such as `london_range_drop_low30` or a conservative combination.
- Any surviving filter remains research-only and requires forward-shadow validation before operational use.

## Operational reminder

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage18a_unified_shadow_ops_cycle
cat data/reports/stage18a_unified_shadow_ops_cycle/stage18a_unified_shadow_ops_cycle.md

python3 -m app.stage23d_forward_shadow_candidate
cat data/reports/stage23d_forward_shadow_candidate/stage23d_forward_shadow_candidate.md
```

## Output files

- `data/reports/stage25c_deduped_filter_validation/stage25c_deduped_filter_validation.json`
- `data/reports/stage25c_deduped_filter_validation/stage25c_deduped_filter_validation.md`
- `data/reports/stage25c_deduped_filter_validation/stage25c_filter_candidates.csv`
- `data/reports/stage25c_deduped_filter_validation/stage25c_enriched_canonical_trades.csv`
- `data/reports/stage25c_deduped_filter_validation/stage25c_stage25b_comparison.csv`
- `data/reports/stage25c_deduped_filter_validation/stage25c_db_schema_diagnostic.csv`