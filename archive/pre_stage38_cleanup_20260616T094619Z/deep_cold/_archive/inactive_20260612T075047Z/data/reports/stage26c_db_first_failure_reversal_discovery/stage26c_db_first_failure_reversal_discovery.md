# Stage26C DB-First Failure/Reversal Discovery

Generated UTC: `2026-06-11T20:47:01.469197+00:00`

## Decision

```text
STAGE26C_NO_PROMOTION_KEEP_DISCOVERY_OPEN
```

## Scope guardrails

- Research/shadow discovery only.
- Stage18A v2 remains the active operational forward-shadow runner.
- Stage23D and Stage25D remain separate DB-first trackers.
- No EA change, no automatic trading, no paper/live/order authorization.
- Candles are DB-first from SQLite via the validated Stage25C loader; AMarkets CSV fallback is disabled.

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
1. `failed_asia_breakout_reversal_v1` — Asia range break that fails/reclaims before entry; fade the failed breakout.
2. `london_impulse_failure_reversal_v1` — Strong London impulse that fails back through midpoint/open before entry.
3. `prior_day_extreme_failure_reversal_v1` — Prior-day high/low break that fails back inside the prior extreme.
4. `day_open_drive_failure_reversal_v1` — Drive away from day open that fails back through day open.

## Counts
- proxy_candidates_tested: `5`
- proxy_candidates_passing_min_events: `5`
- exact_replayed: `3`
- promotion_review_candidates: `0`
- watchlist_only_candidates: `0`
- proxy_timed_out: `True`
- exact_timed_out: `False`
- runtime_seconds: `141.57`

## Family coverage diagnostics
| family | proxy_tested | proxy_passing_min_events | exact_replayed | best_proxy_pf_x4 | best_exact_pf_x4 |
| --- | --- | --- | --- | --- | --- |
| day_open_drive_failure_reversal_v1 | 0 | 0 | 0 | 0 | 0 |
| failed_asia_breakout_reversal_v1 | 5 | 5 | 3 | 0.3991 | 0.4017 |
| london_impulse_failure_reversal_v1 | 0 | 0 | 0 | 0 | 0 |
| prior_day_extreme_failure_reversal_v1 | 0 | 0 | 0 | 0 | 0 |

## Top exact M1 results
| decision | family | name | events | pf_x1 | pf_x4 | pf_x6 | boot_pf_p05_x4 | median_x4 | total_x4 | win_rate_x4 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| STAGE26C_REJECT | failed_asia_breakout_reversal_v1 | fail_asia_br_b0.15_r0.1_e12_tp0.8_sl0.8 | 317 | 0.8509 | 0.4017 | 0.2473 | 0.3174 | -0.5402 | -409.1047 | 0.388 |
| STAGE26C_REJECT | failed_asia_breakout_reversal_v1 | fail_asia_br_b0.15_r0.0_e12_tp0.8_sl0.8 | 330 | 0.8441 | 0.4006 | 0.2479 | 0.3097 | -0.6099 | -429.9515 | 0.3818 |
| STAGE26C_REJECT | failed_asia_breakout_reversal_v1 | fail_asia_br_b0.15_r0.0_e13_tp0.8_sl0.8 | 311 | 0.851 | 0.3933 | 0.237 | 0.2856 | -1 | -398.7805 | 0.3826 |

## Top M15 proxy results
| decision | family | name | events | pf_x1 | pf_x4 | pf_x6 | boot_pf_p05_x4 | median_x4 | rank_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| STAGE26C_REJECT | failed_asia_breakout_reversal_v1 | fail_asia_br_b0.15_r0.1_e12_tp0.8_sl0.8 | 317 | 0.8443 | 0.3991 | 0.2462 | 0.3174 | -0.5978 | 1.6783 |
| STAGE26C_REJECT | failed_asia_breakout_reversal_v1 | fail_asia_br_b0.15_r0.0_e12_tp0.8_sl0.8 | 330 | 0.8378 | 0.3981 | 0.2469 | 0.3079 | -0.6157 | 1.5948 |
| STAGE26C_REJECT | failed_asia_breakout_reversal_v1 | fail_asia_br_b0.15_r0.0_e13_tp0.8_sl0.8 | 311 | 0.845 | 0.3912 | 0.2361 | 0.2855 | -1.03 | 1.641 |
| STAGE26C_REJECT | failed_asia_breakout_reversal_v1 | fail_asia_br_b0.15_r0.0_e11_tp0.8_sl0.8 | 334 | 0.6983 | 0.3495 | 0.2283 | 0.2255 | -2.5823 | 1.3163 |
| STAGE26C_REJECT | failed_asia_breakout_reversal_v1 | fail_asia_br_b0.15_r0.1_e11_tp0.8_sl0.8 | 321 | 0.6834 | 0.3428 | 0.2242 | 0.2311 | -2.598 | 1.3681 |

## Interpretation

- Stage26C is a DB-first discovery branch focused on failed-continuation/reversal behavior after Stage26B rejected continuation-style families.
- Conditions use only information knowable at the chosen entry bar; no full future early-NY window is used at entry.
- Exact replay is selected per family first, then globally capped, to keep discovery coverage broad.
- A promotion-review result here remains research-only and requires separate validation and forward-shadow tracking.

## Operational reminder

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage18a_unified_shadow_ops_cycle
python3 -m app.stage23d_forward_shadow_candidate
python3 -m app.stage25d_db_first_filtered_forward_shadow
```

## Output files
- `data/reports/stage26c_db_first_failure_reversal_discovery/stage26c_db_first_failure_reversal_discovery.json`
- `data/reports/stage26c_db_first_failure_reversal_discovery/stage26c_db_first_failure_reversal_discovery.md`
- `data/reports/stage26c_db_first_failure_reversal_discovery/stage26c_proxy_candidates.csv`
- `data/reports/stage26c_db_first_failure_reversal_discovery/stage26c_exact_candidates.csv`
- `data/reports/stage26c_db_first_failure_reversal_discovery/stage26c_exact_trades.csv`
- `data/reports/stage26c_db_first_failure_reversal_discovery/stage26c_family_coverage.csv`
- `data/reports/stage26c_db_first_failure_reversal_discovery/stage26c_db_schema_diagnostic.csv`
