# Stage24C Remaining Behavior Discovery

Generated UTC: 2026-06-11T16:22:09.756096+00:00

## Decision

```text
STAGE24C_NO_PROMOTION_KEEP_DISCOVERY_OPEN
```

## Scope guardrails

- Research/shadow only.
- Stage18A v2 remains the active operational forward-shadow runner.
- Stage23D remains a separate forward-shadow candidate tracker.
- No EA change, no automatic trading, no paper/live/order authorization.
- This module does not add candidates to Stage18A.

## Data

- m1_rows: 1452943
- m1_span: 2022-05-02 01:01:00+00:00 → 2026-06-11 19:04:00+00:00
- h1_rows: 24277
- h1_span: 2022-05-02 01:00:00+00:00 → 2026-06-11 19:00:00+00:00
- m15_proxy_rows: 97018
- m15_span: 2022-05-02 01:00:00+00:00 → 2026-06-11 19:00:00+00:00
- roundtrip_cost_x1: 0.35
- exact_replay_cap: 12 total / 4 per family
- runtime_cap_seconds: 180
- candidate_cap: 84
- data_load_mode: csv_first

## Discovery families

1. `prev_day_expansion_exhaustion_reversal` — previous-day expansion followed by intraday extension/exhaustion reversal.
2. `ny_opening_range_failed_breakout_reversal` — NY sweep of London range followed by reclaim/failure.
3. `london_midpoint_hold_continuation` — London directional move that holds above/below midpoint into NY.

## Counts

- proxy_candidates_tested: 84
- proxy_candidates_passing_min_events: 61
- exact_replayed: 4
- promotion_review_candidates: 0
- watchlist_only_candidates: 0
- proxy_timed_out: True
- exact_timed_out: False

## Top exact M1 results

| decision | family | name | events | pf_x1 | pf_x4 | pf_x6 | test20_pf_x1 | pf_2026_x1 | boot_pf_p05_x1 | median_x1 | total_x1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| STAGE24C_REJECT | prev_day_expansion_exhaustion_reversal | prev_exp_exhaust_rev_px1.2_ext0.7_cf0.0_h180_e15_tp0.8_sl0.8 | 777 | 1.0363 | 0.7547 | 0.6031 | 1.0583 | 0.8041 | 0.9179 | 2.644 | 93.5713 |
| STAGE24C_REJECT | prev_day_expansion_exhaustion_reversal | prev_exp_exhaust_rev_px1.5_ext0.7_cf0.0_h180_e15_tp0.8_sl0.8 | 777 | 1.0363 | 0.7547 | 0.6031 | 1.0583 | 0.8041 | 0.9179 | 2.644 | 93.5713 |
| STAGE24C_REJECT | prev_day_expansion_exhaustion_reversal | prev_exp_exhaust_rev_px1.2_ext0.7_cf0.0_h90_e15_tp0.8_sl0.8 | 777 | 1.0358 | 0.7195 | 0.5562 | 1.0414 | 0.767 | 0.8891 | 1.9691 | 80.3198 |
| STAGE24C_REJECT | prev_day_expansion_exhaustion_reversal | prev_exp_exhaust_rev_px1.5_ext0.7_cf0.0_h90_e15_tp0.8_sl0.8 | 777 | 1.0358 | 0.7195 | 0.5562 | 1.0414 | 0.767 | 0.8891 | 1.9691 | 80.3198 |

## Top M15 proxy results

| family | name | events | pf_x1 | pf_x4 | pf_x6 | test20_pf_x1 | boot_pf_p05_x1 | median_x1 | rank_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| prev_day_expansion_exhaustion_reversal | prev_exp_exhaust_rev_px1.2_ext0.7_cf0.0_h180_e15_tp0.8_sl0.8 | 777 | 0.9701 | 0.7075 | 0.5665 | 1.0092 | 0.8402 | 2.4938 | 16.8995 |
| prev_day_expansion_exhaustion_reversal | prev_exp_exhaust_rev_px1.5_ext0.7_cf0.0_h180_e15_tp0.8_sl0.8 | 777 | 0.9701 | 0.7075 | 0.5665 | 1.0092 | 0.8402 | 2.4938 | 16.8995 |
| prev_day_expansion_exhaustion_reversal | prev_exp_exhaust_rev_px1.2_ext0.7_cf0.0_h90_e15_tp0.8_sl0.8 | 777 | 0.9608 | 0.6819 | 0.5359 | 0.9878 | 0.8257 | 1.7359 | 16.6639 |
| prev_day_expansion_exhaustion_reversal | prev_exp_exhaust_rev_px1.5_ext0.7_cf0.0_h90_e15_tp0.8_sl0.8 | 777 | 0.9608 | 0.6819 | 0.5359 | 0.9878 | 0.8257 | 1.7359 | 16.6639 |
| prev_day_expansion_exhaustion_reversal | prev_exp_exhaust_rev_px1.2_ext0.45_cf0.0_h180_e15_tp0.8_sl0.8 | 875 | 0.9231 | 0.6687 | 0.5328 | 0.9807 | 0.8016 | 2.1022 | 16.6421 |
| prev_day_expansion_exhaustion_reversal | prev_exp_exhaust_rev_px1.5_ext0.45_cf0.0_h180_e15_tp0.8_sl0.8 | 875 | 0.9231 | 0.6687 | 0.5328 | 0.9807 | 0.8016 | 2.1022 | 16.6421 |
| prev_day_expansion_exhaustion_reversal | prev_exp_exhaust_rev_px1.2_ext0.7_cf0.0_h180_e15_tp0.6_sl0.65 | 777 | 0.9009 | 0.6003 | 0.4453 | 0.9392 | 0.792 | 1.8422 | 16.4168 |
| prev_day_expansion_exhaustion_reversal | prev_exp_exhaust_rev_px1.5_ext0.7_cf0.0_h180_e15_tp0.6_sl0.65 | 777 | 0.9009 | 0.6003 | 0.4453 | 0.9392 | 0.792 | 1.8422 | 16.4168 |
| prev_day_expansion_exhaustion_reversal | prev_exp_exhaust_rev_px1.2_ext0.7_cf0.0_h90_e15_tp0.6_sl0.65 | 777 | 0.8979 | 0.5884 | 0.4312 | 0.9757 | 0.7808 | 1.7816 | 16.3937 |
| prev_day_expansion_exhaustion_reversal | prev_exp_exhaust_rev_px1.5_ext0.7_cf0.0_h90_e15_tp0.6_sl0.65 | 777 | 0.8979 | 0.5884 | 0.4312 | 0.9757 | 0.7808 | 1.7816 | 16.3937 |
| prev_day_expansion_exhaustion_reversal | prev_exp_exhaust_rev_px1.2_ext0.45_cf0.0_h90_e15_tp0.8_sl0.8 | 875 | 0.9154 | 0.6459 | 0.5055 | 0.967 | 0.7934 | 0.84 | 16.3253 |
| prev_day_expansion_exhaustion_reversal | prev_exp_exhaust_rev_px1.5_ext0.45_cf0.0_h90_e15_tp0.8_sl0.8 | 875 | 0.9154 | 0.6459 | 0.5055 | 0.967 | 0.7934 | 0.84 | 16.3253 |
| prev_day_expansion_exhaustion_reversal | prev_exp_exhaust_rev_px1.2_ext0.45_cf0.0_h180_e15_tp0.6_sl0.65 | 875 | 0.8532 | 0.5632 | 0.4147 | 0.9114 | 0.7215 | 1.6909 | 16.1685 |
| prev_day_expansion_exhaustion_reversal | prev_exp_exhaust_rev_px1.5_ext0.45_cf0.0_h180_e15_tp0.6_sl0.65 | 875 | 0.8532 | 0.5632 | 0.4147 | 0.9114 | 0.7215 | 1.6909 | 16.1685 |
| prev_day_expansion_exhaustion_reversal | prev_exp_exhaust_rev_px1.2_ext0.45_cf0.0_h90_e15_tp0.6_sl0.65 | 875 | 0.8501 | 0.5523 | 0.402 | 0.9428 | 0.7419 | 1.4892 | 16.156 |
| prev_day_expansion_exhaustion_reversal | prev_exp_exhaust_rev_px1.5_ext0.45_cf0.0_h90_e15_tp0.6_sl0.65 | 875 | 0.8501 | 0.5523 | 0.402 | 0.9428 | 0.7419 | 1.4892 | 16.156 |
| prev_day_expansion_exhaustion_reversal | prev_exp_exhaust_rev_px1.2_ext0.7_cf0.0_h180_e13_tp0.6_sl0.65 | 750 | 0.8348 | 0.5507 | 0.4056 | 0.78 | 0.7235 | 1.5474 | 16.0121 |
| prev_day_expansion_exhaustion_reversal | prev_exp_exhaust_rev_px1.5_ext0.7_cf0.0_h180_e13_tp0.6_sl0.65 | 750 | 0.8348 | 0.5507 | 0.4056 | 0.78 | 0.7235 | 1.5474 | 16.0121 |
| prev_day_expansion_exhaustion_reversal | prev_exp_exhaust_rev_px1.2_ext0.7_cf0.1_h180_e15_tp0.8_sl0.8 | 241 | 0.8734 | 0.6436 | 0.5188 | 0.9463 | 0.6948 | 2.0962 | 15.9381 |
| prev_day_expansion_exhaustion_reversal | prev_exp_exhaust_rev_px1.2_ext0.45_cf0.0_h180_e13_tp0.6_sl0.65 | 878 | 0.8017 | 0.5242 | 0.3834 | 0.7695 | 0.6889 | 1.2491 | 15.8245 |

## Interpretation

- Promotion-review here is still research-only.
- A candidate cannot enter Stage18A from this module without separate validation and forward-shadow tracking.
- If no promotion appears, close Stage24C and continue with a new behavior cluster rather than widening this grid indefinitely.

## Operational reminder

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage18a_unified_shadow_ops_cycle
cat data/reports/stage18a_unified_shadow_ops_cycle/stage18a_unified_shadow_ops_cycle.md

python3 -m app.stage23d_forward_shadow_candidate
cat data/reports/stage23d_forward_shadow_candidate/stage23d_forward_shadow_candidate.md
```

## Output files

- `data/reports/stage24c_remaining_behavior_discovery/stage24c_remaining_behavior_discovery.json`
- `data/reports/stage24c_remaining_behavior_discovery/stage24c_remaining_behavior_discovery.md`
- `data/reports/stage24c_remaining_behavior_discovery/stage24c_proxy_candidates.csv`
- `data/reports/stage24c_remaining_behavior_discovery/stage24c_exact_candidates.csv`
- `data/reports/stage24c_remaining_behavior_discovery/stage24c_exact_trades.csv`
