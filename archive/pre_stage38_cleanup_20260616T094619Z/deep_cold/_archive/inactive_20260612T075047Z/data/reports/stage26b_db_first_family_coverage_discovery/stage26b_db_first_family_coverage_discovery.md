# Stage26B DB-First Family-Coverage Discovery

## Decision

```text
STAGE26B_NO_PROMOTION_KEEP_DISCOVERY_OPEN
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
- m1_rows: `1532791` | span: `2022-05-01 23:01:00+00:00 → 2026-06-11 23:06:00+00:00`
- h1_rows: `25585` | span: `2022-05-01 23:00:00+00:00 → 2026-06-11 23:00:00+00:00`
- h1_mode: `db_schema_introspection`
- m15_rows: `102452` | span: `2022-05-01 23:15:00+00:00 → 2026-06-11 23:15:00+00:00`

## Discovery families

1. `htf_bias_pullback_v2` — H1 bias, London impulse, controlled pullback continuation.
2. `asia_breakout_pullback_v2` — Asia range breakout with hold/pullback continuation.
3. `session_transition_imbalance_v2` — London imbalance carried into NY transition.
4. `squeeze_release_continuation_v2` — low prior London range regime followed by release.

## Counts
- proxy_candidates_tested: `36`
- proxy_candidates_passing_min_events: `24`
- exact_replayed: `12`
- promotion_review_candidates: `0`
- watchlist_only_candidates: `0`
- proxy_timed_out: `False`
- exact_timed_out: `False`
- runtime_seconds: `42.16`

## Family coverage diagnostics
| family | proxy_tested | proxy_passing_min_events | exact_replayed | best_proxy_pf_x4 | best_exact_pf_x4 |
| --- | --- | --- | --- | --- | --- |
| asia_breakout_pullback_v2 | 8 | 8 | 3 | 0.3083 | 0.3049 |
| htf_bias_pullback_v2 | 16 | 4 | 3 | 0.3731 | 0.2581 |
| session_transition_imbalance_v2 | 8 | 8 | 3 | 0.3375 | 0.3375 |
| squeeze_release_continuation_v2 | 4 | 4 | 3 | 0.3709 | 0.3709 |

## Top exact M1 results
| decision | family | name | events | pf_x1 | pf_x4 | pf_x6 | boot_pf_p05_x4 | median_x4 | total_x4 | win_rate_x4 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| STAGE26B_REJECT | squeeze_release_continuation_v2 | squeeze_release_q0.3_lm0.7_h180_tp08_sl08 | 192 | 0.8689 | 0.3709 | 0.2114 | 0.2509 | -1.3527 | -237.0458 | 0.3698 |
| STAGE26B_REJECT | squeeze_release_continuation_v2 | squeeze_release_q0.3_lm0.7_h90_tp08_sl08 | 192 | 0.8672 | 0.3703 | 0.2112 | 0.2505 | -1.565 | -237.3685 | 0.3646 |
| STAGE26B_REJECT | session_transition_imbalance_v2 | sess_imb_lm0.75_eff0.7_h90_tp08_sl08 | 215 | 0.738 | 0.3375 | 0.1985 | 0.231 | -0.279 | -325.356 | 0.4186 |
| STAGE26B_REJECT | session_transition_imbalance_v2 | sess_imb_lm0.75_eff0.7_h180_tp08_sl08 | 215 | 0.738 | 0.3375 | 0.1985 | 0.231 | -0.279 | -325.356 | 0.4186 |
| STAGE26B_REJECT | session_transition_imbalance_v2 | sess_imb_lm1.0_eff0.7_h180_tp08_sl08 | 215 | 0.738 | 0.3375 | 0.1985 | 0.231 | -0.279 | -325.356 | 0.4186 |
| STAGE26B_REJECT | squeeze_release_continuation_v2 | squeeze_release_q0.3_lm1.0_h180_tp08_sl08 | 154 | 0.7802 | 0.3151 | 0.1728 | 0.2147 | -2.2651 | -209.702 | 0.3571 |
| STAGE26B_REJECT | asia_breakout_pullback_v2 | asia_br_pb_ar0.7_hold0.15_h90_tp08_sl08 | 547 | 0.6984 | 0.3049 | 0.1785 | 0.2305 | -2.3858 | -845.8295 | 0.3547 |
| STAGE26B_REJECT | asia_breakout_pullback_v2 | asia_br_pb_ar0.45_hold0.15_h90_tp08_sl08 | 547 | 0.6984 | 0.3049 | 0.1785 | 0.2305 | -2.3858 | -845.8295 | 0.3547 |
| STAGE26B_REJECT | asia_breakout_pullback_v2 | asia_br_pb_ar0.45_hold0.15_h180_tp08_sl08 | 547 | 0.6939 | 0.3046 | 0.1786 | 0.2309 | -2.406 | -854.0943 | 0.3583 |
| STAGE26B_REJECT | htf_bias_pullback_v2 | htf_pb_lm1.0_eff0.55_pb0.3_h90_tp08_sl08 | 53 | 0.5678 | 0.2581 | 0.1501 | 0.1248 | -2.676 | -97.4775 | 0.3019 |
| STAGE26B_REJECT | htf_bias_pullback_v2 | htf_pb_lm0.75_eff0.55_pb0.3_h90_tp08_sl08 | 53 | 0.5678 | 0.2581 | 0.1501 | 0.1248 | -2.676 | -97.4775 | 0.3019 |
| STAGE26B_REJECT | htf_bias_pullback_v2 | htf_pb_lm0.75_eff0.55_pb0.3_h180_tp08_sl08 | 53 | 0.5419 | 0.2493 | 0.1459 | 0.1154 | -2.7418 | -102.0925 | 0.3019 |

## Top M15 proxy results
| decision | family | name | events | pf_x1 | pf_x4 | pf_x6 | boot_pf_p05_x4 | median_x4 | rank_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| STAGE26B_REJECT | squeeze_release_continuation_v2 | squeeze_release_q0.3_lm0.7_h180_tp08_sl08 | 192 | 0.8689 | 0.3709 | 0.2114 | 0.2509 | -1.3527 | 1.4951 |
| STAGE26B_REJECT | squeeze_release_continuation_v2 | squeeze_release_q0.3_lm0.7_h90_tp08_sl08 | 192 | 0.8672 | 0.3703 | 0.2112 | 0.2505 | -1.565 | 1.4932 |
| STAGE26B_REJECT | session_transition_imbalance_v2 | sess_imb_lm0.75_eff0.7_h90_tp08_sl08 | 215 | 0.738 | 0.3375 | 0.1985 | 0.231 | -0.279 | 1.3725 |
| STAGE26B_REJECT | session_transition_imbalance_v2 | sess_imb_lm0.75_eff0.7_h180_tp08_sl08 | 215 | 0.738 | 0.3375 | 0.1985 | 0.231 | -0.279 | 1.3725 |
| STAGE26B_REJECT | session_transition_imbalance_v2 | sess_imb_lm1.0_eff0.7_h180_tp08_sl08 | 215 | 0.738 | 0.3375 | 0.1985 | 0.231 | -0.279 | 1.3725 |
| STAGE26B_REJECT | session_transition_imbalance_v2 | sess_imb_lm1.0_eff0.7_h90_tp08_sl08 | 215 | 0.738 | 0.3375 | 0.1985 | 0.231 | -0.279 | 1.3725 |
| STAGE26B_REJECT | squeeze_release_continuation_v2 | squeeze_release_q0.3_lm1.0_h180_tp08_sl08 | 154 | 0.7802 | 0.3151 | 0.1728 | 0.2147 | -2.2651 | 1.2615 |
| STAGE26B_REJECT | squeeze_release_continuation_v2 | squeeze_release_q0.3_lm1.0_h90_tp08_sl08 | 154 | 0.7778 | 0.3145 | 0.1726 | 0.212 | -2.2335 | 1.2571 |
| STAGE26B_REJECT | session_transition_imbalance_v2 | sess_imb_lm0.75_eff0.55_h90_tp08_sl08 | 405 | 0.6603 | 0.2997 | 0.1806 | 0.218 | -2.4005 | 1.0181 |
| STAGE26B_REJECT | session_transition_imbalance_v2 | sess_imb_lm1.0_eff0.55_h90_tp08_sl08 | 405 | 0.6603 | 0.2997 | 0.1806 | 0.218 | -2.4005 | 1.0181 |
| STAGE26B_REJECT | session_transition_imbalance_v2 | sess_imb_lm1.0_eff0.55_h180_tp08_sl08 | 405 | 0.6435 | 0.2941 | 0.1777 | 0.2163 | -2.4542 | 0.9982 |
| STAGE26B_REJECT | session_transition_imbalance_v2 | sess_imb_lm0.75_eff0.55_h180_tp08_sl08 | 405 | 0.6435 | 0.2941 | 0.1777 | 0.2163 | -2.4542 | 0.9982 |
| STAGE26B_REJECT | htf_bias_pullback_v2 | htf_pb_lm1.0_eff0.55_pb0.3_h90_tp08_sl08 | 53 | 0.5678 | 0.2581 | 0.1501 | 0.1248 | -2.676 | 0.9952 |
| STAGE26B_REJECT | htf_bias_pullback_v2 | htf_pb_lm0.75_eff0.55_pb0.3_h90_tp08_sl08 | 53 | 0.5678 | 0.2581 | 0.1501 | 0.1248 | -2.676 | 0.9952 |
| STAGE26B_REJECT | htf_bias_pullback_v2 | htf_pb_lm0.75_eff0.55_pb0.3_h180_tp08_sl08 | 53 | 0.5419 | 0.2493 | 0.1459 | 0.1154 | -2.7418 | 0.9576 |
| STAGE26B_REJECT | htf_bias_pullback_v2 | htf_pb_lm1.0_eff0.55_pb0.3_h180_tp08_sl08 | 53 | 0.5419 | 0.2493 | 0.1459 | 0.1154 | -2.7418 | 0.9576 |
| STAGE26B_REJECT | asia_breakout_pullback_v2 | asia_br_pb_ar0.45_hold0.15_h90_tp08_sl08 | 547 | 0.6984 | 0.3049 | 0.1785 | 0.2305 | -2.3858 | 0.4726 |
| STAGE26B_REJECT | asia_breakout_pullback_v2 | asia_br_pb_ar0.7_hold0.15_h90_tp08_sl08 | 547 | 0.6984 | 0.3049 | 0.1785 | 0.2305 | -2.3858 | 0.4726 |
| STAGE26B_REJECT | asia_breakout_pullback_v2 | asia_br_pb_ar0.45_hold0.15_h180_tp08_sl08 | 547 | 0.6939 | 0.3046 | 0.1786 | 0.2309 | -2.406 | 0.4723 |
| STAGE26B_REJECT | asia_breakout_pullback_v2 | asia_br_pb_ar0.7_hold0.15_h180_tp08_sl08 | 547 | 0.6939 | 0.3046 | 0.1786 | 0.2309 | -2.406 | 0.4723 |

## Interpretation

- Stage26B is a DB-first continuation of structured discovery with explicit family coverage diagnostics.
- Exact replay is selected per family first, then globally capped, to avoid the Stage26A failure mode where one family consumed all exact slots.
- A promotion-review result here remains research-only and requires separate validation and forward-shadow tracking.

## Operational reminder

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage18a_unified_shadow_ops_cycle
python3 -m app.stage23d_forward_shadow_candidate
python3 -m app.stage25d_db_first_filtered_forward_shadow
```

## Output files
- `data/reports/stage26b_db_first_family_coverage_discovery/stage26b_db_first_family_coverage_discovery.json`
- `data/reports/stage26b_db_first_family_coverage_discovery/stage26b_db_first_family_coverage_discovery.md`
- `data/reports/stage26b_db_first_family_coverage_discovery/stage26b_proxy_candidates.csv`
- `data/reports/stage26b_db_first_family_coverage_discovery/stage26b_exact_candidates.csv`
- `data/reports/stage26b_db_first_family_coverage_discovery/stage26b_exact_trades.csv`
- `data/reports/stage26b_db_first_family_coverage_discovery/stage26b_family_coverage.csv`
- `data/reports/stage26b_db_first_family_coverage_discovery/stage26b_db_schema_diagnostic.csv`