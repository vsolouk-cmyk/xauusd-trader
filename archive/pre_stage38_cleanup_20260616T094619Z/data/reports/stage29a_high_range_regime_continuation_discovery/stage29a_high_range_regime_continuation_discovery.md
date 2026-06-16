# Stage29A DB-First High-Range Regime Continuation Discovery

Generated UTC: `2026-06-14T18:04:05+00:00`

## Decision

```text
STAGE29A_NO_PROMOTION_KEEP_DISCOVERY_OPEN
```

## Scope guardrails

- Research/shadow discovery only.
- Stage18A/23D/25D/27D/28D remain unchanged.
- No EA change, no automatic trading, no paper/live/order authorization.
- Candles are DB-first from SQLite via Stage25C loader; AMarkets CSV fallback is disabled.
- London range is completed before entries at 13:00+; quantile thresholds are prior-day rolling only.

## Thesis

- name: `high_range_regime_continuation_density_expansion`
- description: Use Stage28C high London/prior range insight to create denser continuation variants, not merely gate the sparse Stage23B event.

## DB source of truth

- db_path: `data/local/xauusd_local_store.sqlite`
- candle_table: `bars`
- m1_mode: `db_schema_introspection`
- m1_rows: `1534217`
- m1_span: `2022-05-01 23:01:00+00:00 → 2026-06-12 23:54:00+00:00`
- h1_mode: `db_schema_introspection`
- h1_rows: `25608`
- h1_span: `2022-05-01 23:00:00+00:00 → 2026-06-12 23:00:00+00:00`
- db_first: `True`
- csv_fallback_enabled: `False`
- m1_rows_stage29a: `1534217`
- h1_rows_stage29a: `25608`
- m15_rows_stage29a: `102355`
- m1_span_stage29a: `2022-05-01 23:01:00+00:00 → 2026-06-12 23:54:00+00:00`
- h1_span_stage29a: `2022-05-01 23:00:00+00:00 → 2026-06-12 23:00:00+00:00`
- m15_span_stage29a: `2022-05-01 23:00:00+00:00 → 2026-06-12 23:45:00+00:00`

## Counts

- registry_candidate_count: `132`
- scheduled_candidate_count: `40`
- candidates_tested: `10`
- candidates_passing_min_events: `10`
- candidate_review_count: `0`
- watchlist_only_count: `0`
- family_count: `4`
- replay_cache_size: `891`
- timed_out: `True`
- runtime_seconds: `241.81`

## Family coverage

| family | candidates_tested | passing_min_events | review_count | watchlist_count | best_name | best_events | best_pf_x4 | best_pf_x6 | best_total_x4 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| high_range_asia_london_alignment_v1 | 2 | 2 | 0 | 0 | hr_asia_london_align_h13_lq35_aq35_tp06_sl065 | 137 | 0.2001 | 0.1262 | -335.4667 |
| high_range_broad_pullback_continuation_v1 | 3 | 3 | 0 | 0 | hr_broad_pb_h13_lq40_pb025_tp07_sl08 | 254 | 0.1835 | 0.1173 | -756.4068 |
| high_range_london_continuation_v1 | 3 | 3 | 0 | 0 | hr_london_follow_h13_lq35_pq10_c00_tp06_sl065 | 313 | 0.1433 | 0.0863 | -847.2738 |
| high_range_london_breakout_follow_v1 | 2 | 2 | 0 | 0 | hr_london_breakout_h13_lq40_b00_tp06_sl08 | 56 | 0.0814 | 0.0439 | -228.8706 |

## Top candidate diagnostics

| decision | family | name | events | pf_x1 | pf_x4 | pf_x6 | boot_pf_p05_x4 | median_x4 | total_x4 | win_rate_x4 | years_positive_x4 | year_count | rank_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| STAGE29A_REJECT | high_range_broad_pullback_continuation_v1 | hr_broad_pb_h13_lq40_pb025_tp07_sl08 | 254 | 0.3533 | 0.1835 | 0.1173 | 0.1289 | -3.4058 | -756.4068 | 0.3386 | 0 | 5 | -0.1944 |
| STAGE29A_REJECT | high_range_asia_london_alignment_v1 | hr_asia_london_align_h13_lq35_aq35_tp06_sl065 | 137 | 0.4094 | 0.2001 | 0.1262 | 0.1254 | -3.0503 | -335.4667 | 0.292 | 0 | 5 | -0.225 |
| STAGE29A_REJECT | high_range_asia_london_alignment_v1 | hr_asia_london_align_h13_lq35_aq25_tp06_sl065 | 147 | 0.4144 | 0.1999 | 0.1249 | 0.1172 | -3.0399 | -352.3542 | 0.2925 | 0 | 5 | -0.229 |
| STAGE29A_REJECT | high_range_london_continuation_v1 | hr_london_follow_h13_lq35_pq10_c00_tp06_sl065 | 313 | 0.3205 | 0.1433 | 0.0863 | 0.1047 | -3.024 | -847.2738 | 0.2588 | 0 | 5 | -0.2544 |
| STAGE29A_REJECT | high_range_broad_pullback_continuation_v1 | hr_broad_pb_h13_lq40_pb025_tp055_sl065 | 254 | 0.3431 | 0.1529 | 0.0938 | 0.1102 | -2.9967 | -672.4005 | 0.2598 | 0 | 5 | -0.2564 |
| STAGE29A_REJECT | high_range_broad_pullback_continuation_v1 | hr_broad_pb_h13_lq40_pb05_tp055_sl065 | 254 | 0.3431 | 0.1529 | 0.0938 | 0.1102 | -2.9967 | -672.4005 | 0.2598 | 0 | 5 | -0.2564 |
| STAGE29A_REJECT | high_range_london_continuation_v1 | hr_london_follow_h13_lq35_pq25_c00_tp06_sl065 | 268 | 0.3078 | 0.1427 | 0.0875 | 0.096 | -3.0393 | -759.5612 | 0.2575 | 0 | 5 | -0.2767 |
| STAGE29A_REJECT | high_range_london_continuation_v1 | hr_london_follow_h13_lq35_pq10_c01_tp06_sl065 | 269 | 0.2569 | 0.1122 | 0.0683 | 0.0724 | -3.0399 | -802.8106 | 0.2268 | 0 | 5 | -0.3392 |
| STAGE29A_REJECT | high_range_london_breakout_follow_v1 | hr_london_breakout_h13_lq40_b00_tp06_sl08 | 56 | 0.1929 | 0.0814 | 0.0439 | 0.0333 | -3.304 | -228.8706 | 0.2857 | 0 | 5 | -0.4893 |
| STAGE29A_REJECT | high_range_london_breakout_follow_v1 | hr_london_breakout_h13_lq40_b01_tp06_sl08 | 49 | 0.1617 | 0.0746 | 0.0446 | 0.0237 | -3.4868 | -223.3584 | 0.2245 | 0 | 5 | -0.5042 |

## Interpretation

- Stage29A is not another generic raw-entry grid; it explicitly uses the Stage28C high-range insight to seek more signal density.
- A candidate-review result remains research-only and needs a dedicated validation stage plus a separate forward-shadow tracker.
- If Stage29A does not produce candidates, the next useful step is not more OHLC-only mutation; it is exogenous/macro/news feature integration or ML meta-labeling on a larger candidate pool.

## Operational reminder

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.run_active_shadow_suite
python3 -m app.stage28d_forward_safe_meta_gate_tracker
python3 -m app.stage29a_high_range_regime_continuation_discovery
```

## Output files

- `data/reports/stage29a_high_range_regime_continuation_discovery/stage29a_high_range_regime_continuation_discovery.json`
- `data/reports/stage29a_high_range_regime_continuation_discovery/stage29a_high_range_regime_continuation_discovery.md`
- `data/reports/stage29a_high_range_regime_continuation_discovery/stage29a_candidates.csv`
- `data/reports/stage29a_high_range_regime_continuation_discovery/stage29a_exact_trades.csv`
- `data/reports/stage29a_high_range_regime_continuation_discovery/stage29a_family_coverage.csv`
- `data/reports/stage29a_high_range_regime_continuation_discovery/stage29a_family_balanced_shortlist.csv`
- `data/reports/stage29a_high_range_regime_continuation_discovery/stage29a_db_schema_diagnostic.csv`
