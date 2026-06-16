# Stage26A DB-First Structured Behavior Discovery

Generated UTC: `2026-06-11T20:28:59.511958+00:00`

## Decision

```text
STAGE26A_NO_PROMOTION_KEEP_DISCOVERY_OPEN
```

## Scope guardrails

- Research/shadow discovery only.
- Stage18A v2 remains the active operational forward-shadow runner.
- Stage23D and Stage25D remain separate DB-first trackers.
- No EA change, no automatic trading, no paper/live/order authorization.
- Candles are DB-first from SQLite; AMarkets CSV fallback is disabled.

## DB source of truth
- db_path: `data/local/xauusd_local_store.sqlite`
- candle_table: `bars`
- db_first: `True`
- csv_fallback_enabled: `False`
- m1_rows: `1532791`
- m1_span: `2022-05-01 23:01:00+00:00 → 2026-06-11 23:06:00+00:00`
- h1_rows: `25585`
- h1_span: `2022-05-01 23:00:00+00:00 → 2026-06-11 23:00:00+00:00`
- h1_mode: `db_schema_introspection`
- m15_rows: `102260`
- m15_span: `2022-05-01 23:00:00+00:00 → 2026-06-11 23:00:00+00:00`

## Discovery families

1. `htf_bias_pullback_continuation` — H1 trend bias plus London directional move and controlled pullback.
2. `breakout_pullback_continuation` — Asia range breakout, pullback/hold, then continuation.
3. `session_transition_imbalance` — London imbalance carried into early NY/session transition.

## Counts
- proxy_candidates_tested: `24`
- proxy_candidates_passing_min_events: `24`
- exact_replayed: `4`
- promotion_review_candidates: `0`
- watchlist_only_candidates: `0`
- proxy_timed_out: `True`
- exact_timed_out: `False`
- runtime_seconds: `150.91`

## Top exact M1 results
| decision | family | name | events | pf_x1 | pf_x4 | pf_x6 | boot_pf_p05_x4 | median_x4 | total_x4 | win_rate_x4 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| STAGE26A_REJECT | htf_bias_pullback_continuation | htf_bias_pullback_cont_lm0.6_eff0.7_pb0.15_h90_e13_tp0.8_sl0.8 | 114 | 1.6859 | 0.8755 | 0.5592 | 0.5149 | 0.1303 | -23.8263 | 0.5439 |
| STAGE26A_REJECT | htf_bias_pullback_continuation | htf_bias_pullback_cont_lm0.6_eff0.7_pb0.15_h180_e13_tp0.8_sl0.8 | 114 | 1.5972 | 0.8484 | 0.5447 | 0.4996 | 0.2783 | -30.2389 | 0.5614 |
| STAGE26A_REJECT | htf_bias_pullback_continuation | htf_bias_pullback_cont_lm0.6_eff0.55_pb0.15_h90_e13_tp0.8_sl0.8 | 188 | 1.3965 | 0.7007 | 0.4363 | 0.5166 | 0.0211 | -100.0349 | 0.5053 |
| STAGE26A_REJECT | htf_bias_pullback_continuation | htf_bias_pullback_cont_lm0.6_eff0.55_pb0.15_h180_e13_tp0.8_sl0.8 | 188 | 1.3536 | 0.6909 | 0.4313 | 0.4923 | 0.0629 | -106.1949 | 0.5213 |

## Top M15 proxy results
| decision | family | name | events | pf_x1 | pf_x4 | pf_x6 | boot_pf_p05_x4 | median_x4 | rank_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| STAGE26A_REJECT | htf_bias_pullback_continuation | htf_bias_pullback_cont_lm0.6_eff0.7_pb0.15_h90_e13_tp0.8_sl0.8 | 114 | 0.9453 | 0.5021 | 0.3247 | 0.3114 | -1.645 | 1.4303 |
| STAGE26A_REJECT | htf_bias_pullback_continuation | htf_bias_pullback_cont_lm0.6_eff0.55_pb0.15_h90_e13_tp0.8_sl0.8 | 188 | 0.9363 | 0.4772 | 0.3002 | 0.3592 | -1.0724 | 1.4129 |
| STAGE26A_REJECT | htf_bias_pullback_continuation | htf_bias_pullback_cont_lm0.6_eff0.55_pb0.15_h180_e13_tp0.8_sl0.8 | 188 | 0.9245 | 0.4743 | 0.2989 | 0.3549 | -0.6094 | 1.3989 |
| STAGE26A_REJECT | htf_bias_pullback_continuation | htf_bias_pullback_cont_lm0.6_eff0.7_pb0.15_h180_e13_tp0.8_sl0.8 | 114 | 0.9095 | 0.4875 | 0.3167 | 0.3036 | -2.3166 | 1.3776 |
| STAGE26A_REJECT | htf_bias_pullback_continuation | htf_bias_pullback_cont_lm0.6_eff0.55_pb0.3_h90_e13_tp0.8_sl0.8 | 194 | 0.9261 | 0.4715 | 0.2964 | 0.3395 | -1.0724 | 1.3682 |
| STAGE26A_REJECT | htf_bias_pullback_continuation | htf_bias_pullback_cont_lm0.6_eff0.55_pb0.3_h180_e13_tp0.8_sl0.8 | 194 | 0.9143 | 0.4685 | 0.295 | 0.3358 | -0.6094 | 1.3549 |
| STAGE26A_REJECT | htf_bias_pullback_continuation | htf_bias_pullback_cont_lm0.6_eff0.7_pb0.15_h90_e14_tp0.8_sl0.8 | 93 | 0.9093 | 0.4707 | 0.2974 | 0.299 | -2.4469 | 1.3111 |
| STAGE26A_REJECT | htf_bias_pullback_continuation | htf_bias_pullback_cont_lm0.6_eff0.7_pb0.15_h180_e14_tp0.8_sl0.8 | 93 | 0.8757 | 0.4575 | 0.2904 | 0.287 | -2.8114 | 1.2569 |
| STAGE26A_REJECT | htf_bias_pullback_continuation | htf_bias_pullback_cont_lm0.6_eff0.55_pb0.15_h90_e14_tp0.8_sl0.8 | 147 | 0.8144 | 0.397 | 0.2416 | 0.2827 | -2.5069 | 1.0591 |
| STAGE26A_REJECT | htf_bias_pullback_continuation | htf_bias_pullback_cont_lm0.6_eff0.55_pb0.3_h90_e14_tp0.8_sl0.8 | 153 | 0.8177 | 0.3967 | 0.2391 | 0.2847 | -2.4469 | 1.0582 |
| STAGE26A_REJECT | htf_bias_pullback_continuation | htf_bias_pullback_cont_lm0.6_eff0.55_pb0.15_h180_e14_tp0.8_sl0.8 | 147 | 0.7949 | 0.3899 | 0.2379 | 0.2782 | -2.6371 | 1.0326 |
| STAGE26A_REJECT | htf_bias_pullback_continuation | htf_bias_pullback_cont_lm0.6_eff0.55_pb0.3_h180_e14_tp0.8_sl0.8 | 153 | 0.7988 | 0.3898 | 0.2356 | 0.2787 | -2.528 | 1.0304 |
| STAGE26A_REJECT | htf_bias_pullback_continuation | htf_bias_pullback_cont_lm0.6_eff0.7_pb0.15_h90_e13_tp0.6_sl0.65 | 114 | 0.8672 | 0.3691 | 0.217 | 0.2146 | -0.356 | 0.873 |
| STAGE26A_REJECT | htf_bias_pullback_continuation | htf_bias_pullback_cont_lm0.6_eff0.7_pb0.15_h180_e13_tp0.6_sl0.65 | 114 | 0.8672 | 0.3691 | 0.217 | 0.2146 | -0.356 | 0.873 |
| STAGE26A_REJECT | htf_bias_pullback_continuation | htf_bias_pullback_cont_lm0.6_eff0.55_pb0.3_h180_e13_tp0.6_sl0.65 | 194 | 0.7231 | 0.2849 | 0.1593 | 0.2081 | -0.6948 | 0.6094 |
| STAGE26A_REJECT | htf_bias_pullback_continuation | htf_bias_pullback_cont_lm0.6_eff0.55_pb0.3_h90_e13_tp0.6_sl0.65 | 194 | 0.7141 | 0.2814 | 0.1582 | 0.2064 | -0.7424 | 0.598 |
| STAGE26A_REJECT | htf_bias_pullback_continuation | htf_bias_pullback_cont_lm0.6_eff0.55_pb0.15_h180_e13_tp0.6_sl0.65 | 188 | 0.7195 | 0.2848 | 0.1598 | 0.1897 | -0.7424 | 0.5839 |
| STAGE26A_REJECT | htf_bias_pullback_continuation | htf_bias_pullback_cont_lm0.6_eff0.55_pb0.15_h90_e13_tp0.6_sl0.65 | 188 | 0.7102 | 0.2812 | 0.1587 | 0.1855 | -0.8071 | 0.5687 |
| STAGE26A_REJECT | htf_bias_pullback_continuation | htf_bias_pullback_cont_lm0.6_eff0.7_pb0.15_h90_e14_tp0.6_sl0.65 | 93 | 0.6871 | 0.2857 | 0.1623 | 0.1678 | -2.5472 | 0.5581 |
| STAGE26A_REJECT | htf_bias_pullback_continuation | htf_bias_pullback_cont_lm0.6_eff0.7_pb0.15_h180_e14_tp0.6_sl0.65 | 93 | 0.6871 | 0.2857 | 0.1623 | 0.1678 | -2.5472 | 0.5581 |

## Interpretation

- Stage26A is a new DB-first discovery branch, not a modification of Stage18A/23D/25D.
- Exact replay is family-balanced so one high-frequency family cannot consume all exact slots.
- Generic high-frequency candidates are penalized in ranking to reduce the Stage24 failure mode.
- A promotion-review result here remains research-only and requires separate validation and forward-shadow tracking.

## Operational reminder

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage18a_unified_shadow_ops_cycle
python3 -m app.stage23d_forward_shadow_candidate
python3 -m app.stage25d_db_first_filtered_forward_shadow
```

## Output files
- `data/reports/stage26a_db_first_structured_behavior_discovery/stage26a_db_first_structured_behavior_discovery.json`
- `data/reports/stage26a_db_first_structured_behavior_discovery/stage26a_db_first_structured_behavior_discovery.md`
- `data/reports/stage26a_db_first_structured_behavior_discovery/stage26a_proxy_candidates.csv`
- `data/reports/stage26a_db_first_structured_behavior_discovery/stage26a_exact_candidates.csv`
- `data/reports/stage26a_db_first_structured_behavior_discovery/stage26a_exact_trades.csv`
- `data/reports/stage26a_db_first_structured_behavior_discovery/stage26a_db_schema_diagnostic.csv`
