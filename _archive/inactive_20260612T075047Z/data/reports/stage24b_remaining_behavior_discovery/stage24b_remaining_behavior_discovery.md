# Stage24B Remaining Behavior Discovery

Generated UTC: 2026-06-11T16:16:50.937757+00:00

## Decision

```text
STAGE24B_NO_PROMOTION_KEEP_DISCOVERY_OPEN
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

1. `prev_day_inside_breakout_continuation` — previous-day compression/inside range followed by breakout continuation.
2. `ny_open_impulse_continuation` — London directional drive plus NY confirmation.
3. `asia_london_alignment_continuation` — Asia and London aligned directional pressure continued into NY.

## Counts

- proxy_candidates_tested: 84
- proxy_candidates_passing_min_events: 69
- exact_replayed: 8
- promotion_review_candidates: 0
- watchlist_only_candidates: 0
- proxy_timed_out: True
- exact_timed_out: False

## Top exact M1 results

| decision | family | name | events | pf_x1 | pf_x4 | pf_x6 | test20_pf_x1 | pf_2026_x1 | boot_pf_p05_x1 | median_x1 | total_x1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| STAGE24B_REJECT | ny_open_impulse_continuation | ny_impulse_cont_lm0.45_cf0.1_h90_e14_tp0.8_sl0.8 | 274 | 0.6779 | 0.4426 | 0.3292 | 0.7074 | 0.8033 | 0.5545 | -1.27 | -264.1112 |
| STAGE24B_REJECT | ny_open_impulse_continuation | ny_impulse_cont_lm0.45_cf0.1_h180_e13_tp0.8_sl0.8 | 247 | 0.7543 | 0.5227 | 0.4032 | 0.7541 | 0.5706 | 0.5815 | -2.9867 | -202.5541 |
| STAGE24B_REJECT | ny_open_impulse_continuation | ny_impulse_cont_lm0.45_cf0.1_h90_e14_tp0.6_sl0.65 | 274 | 0.6488 | 0.3964 | 0.276 | 0.7042 | 0.7044 | 0.5256 | -2.2154 | -265.3971 |
| STAGE24B_REJECT | ny_open_impulse_continuation | ny_impulse_cont_lm0.45_cf0.1_h180_e13_tp0.6_sl0.65 | 247 | 0.6646 | 0.4171 | 0.2945 | 0.7084 | 0.705 | 0.4891 | -2.8024 | -239.5389 |
| STAGE24B_REJECT | prev_day_inside_breakout_continuation | inside_break_cont_in0.85_cf0.1_h180_e13_tp0.6_sl0.65 | 150 | 1.0388 | 0.7134 | 0.5463 | 1.3531 | 1.3702 | 0.7836 | 1.8781 | 16.325 |
| STAGE24B_REJECT | prev_day_inside_breakout_continuation | inside_break_cont_in0.85_cf0.05_h180_e13_tp0.6_sl0.65 | 151 | 1.0461 | 0.7175 | 0.5488 | 1.308 | 1.3702 | 0.6979 | 1.8914 | 19.4258 |
| STAGE24B_REJECT | prev_day_inside_breakout_continuation | inside_break_cont_in0.85_cf0.1_h90_e13_tp0.8_sl0.8 | 150 | 0.9668 | 0.5847 | 0.4183 | 1.0614 | 1.2451 | 0.6941 | -0.045 | -10.5012 |
| STAGE24B_REJECT | prev_day_inside_breakout_continuation | inside_break_cont_in0.85_cf0.05_h90_e13_tp0.8_sl0.8 | 151 | 0.9519 | 0.5762 | 0.4124 | 1.0444 | 1.2451 | 0.6731 | -0.06 | -15.4523 |

## Top M15 proxy results

| family | name | events | pf_x1 | pf_x4 | pf_x6 | test20_pf_x1 | boot_pf_p05_x1 | median_x1 | rank_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ny_open_impulse_continuation | ny_impulse_cont_lm0.45_cf0.1_h180_e13_tp0.6_sl0.65 | 247 | 0.9253 | 0.5858 | 0.4191 | 1.2106 | 0.6937 | 1.4839 | 16.2586 |
| ny_open_impulse_continuation | ny_impulse_cont_lm0.45_cf0.1_h180_e13_tp0.8_sl0.8 | 247 | 0.9601 | 0.6679 | 0.5193 | 1.2386 | 0.717 | -1.36 | 15.9058 |
| ny_open_impulse_continuation | ny_impulse_cont_lm0.45_cf0.1_h90_e14_tp0.6_sl0.65 | 274 | 0.8671 | 0.543 | 0.3878 | 1.1417 | 0.7 | -1.025 | 15.7401 |
| ny_open_impulse_continuation | ny_impulse_cont_lm0.45_cf0.1_h90_e14_tp0.8_sl0.8 | 274 | 0.8548 | 0.5813 | 0.445 | 1.1075 | 0.6746 | -1.15 | 15.707 |
| ny_open_impulse_continuation | ny_impulse_cont_lm0.45_cf0.1_h90_e13_tp0.6_sl0.65 | 247 | 0.9147 | 0.534 | 0.3663 | 1.1074 | 0.6556 | -0.3 | 15.6865 |
| ny_open_impulse_continuation | ny_impulse_cont_lm0.45_cf0.1_h180_e14_tp0.6_sl0.65 | 274 | 0.8721 | 0.5569 | 0.4027 | 1.2161 | 0.7173 | -2.4423 | 15.5584 |
| ny_open_impulse_continuation | ny_impulse_cont_lm0.45_cf0.1_h90_e13_tp0.8_sl0.8 | 247 | 0.8624 | 0.5236 | 0.376 | 0.8926 | 0.6464 | -0.37 | 15.4412 |
| ny_open_impulse_continuation | ny_impulse_cont_lm0.45_cf0.1_h180_e14_tp0.8_sl0.8 | 274 | 0.8418 | 0.5915 | 0.4621 | 1.1543 | 0.6834 | -3.2615 | 15.3324 |
| ny_open_impulse_continuation | ny_impulse_cont_lm0.7_cf0.1_h180_e13_tp0.6_sl0.65 | 202 | 1.031 | 0.6595 | 0.4789 | 1.7764 | 0.7534 | 1.5002 | 14.7092 |
| ny_open_impulse_continuation | ny_impulse_cont_lm0.7_cf0.1_h90_e14_tp0.6_sl0.65 | 230 | 0.85 | 0.5367 | 0.3862 | 1.0712 | 0.6461 | -2.09 | 14.3806 |
| ny_open_impulse_continuation | ny_impulse_cont_lm0.7_cf0.1_h90_e13_tp0.6_sl0.65 | 202 | 1.0357 | 0.6052 | 0.4194 | 1.6781 | 0.7008 | -0.17 | 14.1558 |
| ny_open_impulse_continuation | ny_impulse_cont_lm0.7_cf0.1_h180_e13_tp0.8_sl0.8 | 202 | 1.0496 | 0.7325 | 0.5722 | 1.6438 | 0.6924 | -1.115 | 14.1493 |
| ny_open_impulse_continuation | ny_impulse_cont_lm0.7_cf0.1_h90_e13_tp0.8_sl0.8 | 202 | 0.9582 | 0.5763 | 0.4139 | 1.2654 | 0.6944 | -0.315 | 13.7059 |
| ny_open_impulse_continuation | ny_impulse_cont_lm0.45_cf0.2_h180_e14_tp0.6_sl0.65 | 178 | 0.9074 | 0.5748 | 0.4129 | 1.2342 | 0.6787 | -0.4336 | 12.3866 |
| ny_open_impulse_continuation | ny_impulse_cont_lm0.45_cf0.2_h90_e14_tp0.6_sl0.65 | 178 | 0.8679 | 0.5375 | 0.3795 | 1.1145 | 0.6591 | -0.76 | 12.1129 |
| ny_open_impulse_continuation | ny_impulse_cont_lm0.45_cf0.2_h90_e14_tp0.8_sl0.8 | 178 | 0.8286 | 0.5559 | 0.4206 | 1.0285 | 0.6358 | -0.99 | 11.9665 |
| prev_day_inside_breakout_continuation | inside_break_cont_in0.85_cf0.1_h180_e13_tp0.6_sl0.65 | 150 | 1.0047 | 0.6943 | 0.5336 | 1.2808 | 0.7567 | 1.8673 | 11.8692 |
| prev_day_inside_breakout_continuation | inside_break_cont_in0.85_cf0.05_h180_e13_tp0.6_sl0.65 | 151 | 0.9954 | 0.6873 | 0.5281 | 1.2407 | 0.6638 | 1.8647 | 11.7494 |
| ny_open_impulse_continuation | ny_impulse_cont_lm0.45_cf0.2_h180_e14_tp0.8_sl0.8 | 178 | 0.8405 | 0.5879 | 0.4576 | 1.1233 | 0.6264 | -3.2074 | 11.6404 |
| prev_day_inside_breakout_continuation | inside_break_cont_in0.85_cf0.1_h90_e13_tp0.8_sl0.8 | 150 | 1.0576 | 0.6826 | 0.5096 | 1.2488 | 0.7768 | -0.225 | 11.4888 |

## Interpretation

- Promotion-review here is still research-only.
- A candidate cannot enter Stage18A from this module without separate validation and forward-shadow tracking.
- If no promotion appears, close Stage24B and continue with a new behavior cluster rather than widening this grid indefinitely.

## Operational reminder

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage18a_unified_shadow_ops_cycle
cat data/reports/stage18a_unified_shadow_ops_cycle/stage18a_unified_shadow_ops_cycle.md

python3 -m app.stage23d_forward_shadow_candidate
cat data/reports/stage23d_forward_shadow_candidate/stage23d_forward_shadow_candidate.md
```

## Output files

- `data/reports/stage24b_remaining_behavior_discovery/stage24b_remaining_behavior_discovery.json`
- `data/reports/stage24b_remaining_behavior_discovery/stage24b_remaining_behavior_discovery.md`
- `data/reports/stage24b_remaining_behavior_discovery/stage24b_proxy_candidates.csv`
- `data/reports/stage24b_remaining_behavior_discovery/stage24b_exact_candidates.csv`
- `data/reports/stage24b_remaining_behavior_discovery/stage24b_exact_trades.csv`
