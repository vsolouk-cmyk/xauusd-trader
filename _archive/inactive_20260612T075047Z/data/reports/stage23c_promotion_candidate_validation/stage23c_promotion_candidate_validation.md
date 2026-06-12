# Stage23C Promotion-Candidate Validation

Generated UTC: 2026-06-11T15:28:41+00:00

## Decision

```text
STAGE23C_VALIDATED_PROMOTION_REVIEW_ONLY_RESEARCH_ONLY
```

## Scope guardrails

- Research/shadow only.
- Stage18A v2 remains the active operational forward-shadow runner.
- No EA change, no automatic trading, no paper/live/order authorization.
- This module validates Stage23B candidates only; it does not promote them operationally.

## Data

- M1 rows: 1452834 | span: 2022-05-02 01:01:00 → 2026-06-11 17:15:00
- H1 rows: 24275 | span: 2022-05-02 01:00:00 → 2026-06-11 17:00:00
- M15 rows: 97011 | span: 2022-05-02 01:00:00 → 2026-06-11 17:15:00
- Roundtrip cost x1: 0.35

## Duplicate / redundancy check

| candidate_count | candidates |
| --- | --- |
| 3 | S23B_A_pb0.1_eff0.72_h180_tp0.6_sl0.65, S23B_A_dup_pb0.3_eff0.72_h180_tp0.6_sl0.65, S23B_A_h90_sensitivity_eff0.72_tp0.6_sl0.65 |
| 3 | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65, S23B_B_dup_pb0.3_eff0.60_h180_tp0.6_sl0.65, S23B_B_h90_sensitivity_eff0.60_tp0.6_sl0.65 |

## Candidate validation summary

| decision | candidate | events | pf_x1 | pf_x4 | pf_x6 | test20_pf_x4 | boot_pf_p05_x4 | years_pf_positive_x4 | valid_year_count | pf_2026_x4 | events_2026 | loss_count_2026_x4 | median_x4 | total_x4 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| STAGE23C_KEEP_WATCHLIST_ONLY | S23B_A_pb0.1_eff0.72_h180_tp0.6_sl0.65 | 56 | 6.6576 | 3.5097 | 2.1469 | 18.162 | 1.8101 | 3 | 5 | inf | 2 | 0 | 1.1641 | 95.3035 |
| STAGE23C_KEEP_WATCHLIST_ONLY | S23B_A_dup_pb0.3_eff0.72_h180_tp0.6_sl0.65 | 56 | 6.6576 | 3.5097 | 2.1469 | 18.162 | 1.8101 | 3 | 5 | inf | 2 | 0 | 1.1641 | 95.3035 |
| STAGE23C_KEEP_WATCHLIST_ONLY | S23B_A_h90_sensitivity_eff0.72_tp0.6_sl0.65 | 56 | 5.8571 | 2.6253 | 1.5061 | 10.4109 | 1.394 | 3 | 5 | inf | 2 | 0 | 0.8562 | 67.5451 |
| STAGE23C_VALIDATED_PROMOTION_REVIEW_ONLY | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | 100 | 5.579 | 2.8514 | 1.6534 | 10.8935 | 1.8122 | 4 | 5 | inf | 4 | 0 | 1.0294 | 127.6156 |
| STAGE23C_VALIDATED_PROMOTION_REVIEW_ONLY | S23B_B_dup_pb0.3_eff0.60_h180_tp0.6_sl0.65 | 100 | 5.579 | 2.8514 | 1.6534 | 10.8935 | 1.8122 | 4 | 5 | inf | 4 | 0 | 1.0294 | 127.6156 |
| STAGE23C_VALIDATED_PROMOTION_REVIEW_ONLY | S23B_B_h90_sensitivity_eff0.60_tp0.6_sl0.65 | 100 | 5.5478 | 2.4025 | 1.2973 | 10.5898 | 1.5142 | 4 | 5 | inf | 4 | 0 | 0.8474 | 98.1976 |

## Split diagnostics

| candidate | split_type | split | events | pf | total | median | win_rate | loss_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S23B_A_pb0.1_eff0.72_h180_tp0.6_sl0.65 | year | 2022 | 12 | 0.6565 | -3.6362 | 0.3781 | 0.75 | 3 |
| S23B_A_pb0.1_eff0.72_h180_tp0.6_sl0.65 | year | 2023 | 12 | 0.6469 | -4.7329 | 0.3038 | 0.6667 | 4 |
| S23B_A_pb0.1_eff0.72_h180_tp0.6_sl0.65 | year | 2024 | 18 | 4.6079 | 19.6085 | 1.1836 | 0.8889 | 2 |
| S23B_A_pb0.1_eff0.72_h180_tp0.6_sl0.65 | year | 2025 | 12 | 6.5575 | 47.5178 | 4.0463 | 0.8333 | 2 |
| S23B_A_pb0.1_eff0.72_h180_tp0.6_sl0.65 | year | 2026 | 2 | inf | 36.5463 | 18.2731 | 1 | 0 |
| S23B_A_pb0.1_eff0.72_h180_tp0.6_sl0.65 | direction | long | 33 | 1.5041 | 15.3466 | 0.9914 | 0.7273 | 9 |
| S23B_A_pb0.1_eff0.72_h180_tp0.6_sl0.65 | direction | short | 23 | 11.6143 | 79.9569 | 1.4054 | 0.913 | 2 |
| S23B_A_pb0.1_eff0.72_h180_tp0.6_sl0.65 | exit_reason | sl_conservative | 10 | 0 | -37.7385 | -3.6367 | 0 | 10 |
| S23B_A_pb0.1_eff0.72_h180_tp0.6_sl0.65 | exit_reason | tp | 46 | 565.7664 | 133.042 | 1.4112 | 0.9783 | 1 |
| S23B_A_dup_pb0.3_eff0.72_h180_tp0.6_sl0.65 | year | 2022 | 12 | 0.6565 | -3.6362 | 0.3781 | 0.75 | 3 |
| S23B_A_dup_pb0.3_eff0.72_h180_tp0.6_sl0.65 | year | 2023 | 12 | 0.6469 | -4.7329 | 0.3038 | 0.6667 | 4 |
| S23B_A_dup_pb0.3_eff0.72_h180_tp0.6_sl0.65 | year | 2024 | 18 | 4.6079 | 19.6085 | 1.1836 | 0.8889 | 2 |
| S23B_A_dup_pb0.3_eff0.72_h180_tp0.6_sl0.65 | year | 2025 | 12 | 6.5575 | 47.5178 | 4.0463 | 0.8333 | 2 |
| S23B_A_dup_pb0.3_eff0.72_h180_tp0.6_sl0.65 | year | 2026 | 2 | inf | 36.5463 | 18.2731 | 1 | 0 |
| S23B_A_dup_pb0.3_eff0.72_h180_tp0.6_sl0.65 | direction | long | 33 | 1.5041 | 15.3466 | 0.9914 | 0.7273 | 9 |
| S23B_A_dup_pb0.3_eff0.72_h180_tp0.6_sl0.65 | direction | short | 23 | 11.6143 | 79.9569 | 1.4054 | 0.913 | 2 |
| S23B_A_dup_pb0.3_eff0.72_h180_tp0.6_sl0.65 | exit_reason | sl_conservative | 10 | 0 | -37.7385 | -3.6367 | 0 | 10 |
| S23B_A_dup_pb0.3_eff0.72_h180_tp0.6_sl0.65 | exit_reason | tp | 46 | 565.7664 | 133.042 | 1.4112 | 0.9783 | 1 |
| S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | year | 2022 | 27 | 0.7106 | -6.3259 | 0.4943 | 0.7778 | 6 |
| S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | year | 2023 | 25 | 1.0739 | 1.2572 | 0.6764 | 0.76 | 6 |
| S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | year | 2024 | 25 | 3.3114 | 23.6614 | 1.1886 | 0.88 | 3 |
| S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | year | 2025 | 19 | 3.5484 | 50.5014 | 2.8471 | 0.7895 | 4 |
| S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | year | 2026 | 4 | inf | 58.5216 | 10.9876 | 1 | 0 |
| S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | direction | long | 55 | 1.7777 | 34.6665 | 0.9914 | 0.7818 | 12 |
| S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | direction | short | 45 | 4.8171 | 92.9491 | 1.0471 | 0.8444 | 7 |
| S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | exit_reason | sl_conservative | 17 | 0 | -68.6509 | -3.7112 | 0 | 17 |
| S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | exit_reason | tp | 83 | 707.3505 | 196.2665 | 1.1513 | 0.9759 | 2 |
| S23B_B_dup_pb0.3_eff0.60_h180_tp0.6_sl0.65 | year | 2022 | 27 | 0.7106 | -6.3259 | 0.4943 | 0.7778 | 6 |
| S23B_B_dup_pb0.3_eff0.60_h180_tp0.6_sl0.65 | year | 2023 | 25 | 1.0739 | 1.2572 | 0.6764 | 0.76 | 6 |
| S23B_B_dup_pb0.3_eff0.60_h180_tp0.6_sl0.65 | year | 2024 | 25 | 3.3114 | 23.6614 | 1.1886 | 0.88 | 3 |
| S23B_B_dup_pb0.3_eff0.60_h180_tp0.6_sl0.65 | year | 2025 | 19 | 3.5484 | 50.5014 | 2.8471 | 0.7895 | 4 |
| S23B_B_dup_pb0.3_eff0.60_h180_tp0.6_sl0.65 | year | 2026 | 4 | inf | 58.5216 | 10.9876 | 1 | 0 |
| S23B_B_dup_pb0.3_eff0.60_h180_tp0.6_sl0.65 | direction | long | 55 | 1.7777 | 34.6665 | 0.9914 | 0.7818 | 12 |
| S23B_B_dup_pb0.3_eff0.60_h180_tp0.6_sl0.65 | direction | short | 45 | 4.8171 | 92.9491 | 1.0471 | 0.8444 | 7 |
| S23B_B_dup_pb0.3_eff0.60_h180_tp0.6_sl0.65 | exit_reason | sl_conservative | 17 | 0 | -68.6509 | -3.7112 | 0 | 17 |
| S23B_B_dup_pb0.3_eff0.60_h180_tp0.6_sl0.65 | exit_reason | tp | 83 | 707.3505 | 196.2665 | 1.1513 | 0.9759 | 2 |
| S23B_A_h90_sensitivity_eff0.72_tp0.6_sl0.65 | year | 2022 | 12 | 0.4672 | -6.5629 | 0.2515 | 0.6667 | 4 |
| S23B_A_h90_sensitivity_eff0.72_tp0.6_sl0.65 | year | 2023 | 12 | 0.6714 | -3.7025 | 0.1294 | 0.5833 | 5 |
| S23B_A_h90_sensitivity_eff0.72_tp0.6_sl0.65 | year | 2024 | 18 | 3.0734 | 16.0998 | 1.1691 | 0.8333 | 3 |
| S23B_A_h90_sensitivity_eff0.72_tp0.6_sl0.65 | year | 2025 | 12 | 3.4646 | 25.1644 | 2.5152 | 0.6667 | 4 |
| S23B_A_h90_sensitivity_eff0.72_tp0.6_sl0.65 | year | 2026 | 2 | inf | 36.5463 | 18.2731 | 1 | 0 |
| S23B_A_h90_sensitivity_eff0.72_tp0.6_sl0.65 | direction | long | 33 | 1.2817 | 8.4241 | 0.8483 | 0.6667 | 11 |
| S23B_A_h90_sensitivity_eff0.72_tp0.6_sl0.65 | direction | short | 23 | 6.0735 | 59.1209 | 1.2524 | 0.7826 | 5 |
| S23B_A_h90_sensitivity_eff0.72_tp0.6_sl0.65 | exit_reason | horizon_close | 8 | 0 | -13.63 | -1.58 | 0 | 8 |
| S23B_A_h90_sensitivity_eff0.72_tp0.6_sl0.65 | exit_reason | sl_conservative | 7 | 0 | -27.6926 | -3.6509 | 0 | 7 |
| S23B_A_h90_sensitivity_eff0.72_tp0.6_sl0.65 | exit_reason | tp | 41 | 463.146 | 108.8677 | 1.417 | 0.9756 | 1 |
| S23B_B_h90_sensitivity_eff0.60_tp0.6_sl0.65 | year | 2022 | 27 | 0.6078 | -9.2526 | 0.442 | 0.7407 | 7 |
| S23B_B_h90_sensitivity_eff0.60_tp0.6_sl0.65 | year | 2023 | 25 | 1.1614 | 2.2917 | 0.4797 | 0.68 | 8 |
| S23B_B_h90_sensitivity_eff0.60_tp0.6_sl0.65 | year | 2024 | 25 | 2.0832 | 15.2045 | 1.087 | 0.76 | 6 |
| S23B_B_h90_sensitivity_eff0.60_tp0.6_sl0.65 | year | 2025 | 19 | 2.7278 | 31.4324 | 2.3393 | 0.6842 | 6 |
| S23B_B_h90_sensitivity_eff0.60_tp0.6_sl0.65 | year | 2026 | 4 | inf | 58.5216 | 10.9876 | 1 | 0 |
| S23B_B_h90_sensitivity_eff0.60_tp0.6_sl0.65 | direction | long | 55 | 1.7058 | 29.422 | 0.8483 | 0.7273 | 15 |
| S23B_B_h90_sensitivity_eff0.60_tp0.6_sl0.65 | direction | short | 45 | 3.4277 | 68.7755 | 0.7716 | 0.7333 | 12 |
| S23B_B_h90_sensitivity_eff0.60_tp0.6_sl0.65 | exit_reason | horizon_close | 13 | 0 | -21.3 | -1.43 | 0 | 13 |
| S23B_B_h90_sensitivity_eff0.60_tp0.6_sl0.65 | exit_reason | sl_conservative | 12 | 0 | -48.4401 | -3.909 | 0 | 12 |
| S23B_B_h90_sensitivity_eff0.60_tp0.6_sl0.65 | exit_reason | tp | 75 | 605.3968 | 167.9377 | 1.087 | 0.9733 | 2 |

## Interpretation

- `pf_2026 = inf` is treated as a warning if it comes from zero losing trades, not as proof of robustness.
- Duplicate pb0.1/pb0.3 variants are not independent evidence if their event signatures match.
- A validated result here is still research-only. The next step would be a narrow Stage23D forward-shadow candidate module, not EA/paper/live execution.

## Operational reminder

Continue Stage18A v2 separately after AMarkets CSV refresh:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage18a_unified_shadow_ops_cycle
cat data/reports/stage18a_unified_shadow_ops_cycle/stage18a_unified_shadow_ops_cycle.md
```

## Output files

- `data/reports/stage23c_promotion_candidate_validation/stage23c_promotion_candidate_validation.json`
- `data/reports/stage23c_promotion_candidate_validation/stage23c_promotion_candidate_validation.md`
- `data/reports/stage23c_promotion_candidate_validation/stage23c_candidate_summary.csv`
- `data/reports/stage23c_promotion_candidate_validation/stage23c_split_diagnostics.csv`
- `data/reports/stage23c_promotion_candidate_validation/stage23c_exact_trades.csv`
