# Stage27A DB-First Outcome-Surface Discovery

Generated UTC: `2026-06-11T21:27:37.768708+00:00`

## Decision

```text
STAGE27A_NO_PROMOTION_KEEP_DISCOVERY_OPEN
```

## Scope guardrails

- Research/shadow discovery only.
- Stage18A v2 remains the active operational forward-shadow runner.
- Stage23D and Stage25D remain separate DB-first trackers.
- No EA change, no automatic trading, no paper/live/order authorization.
- Candles are DB-first from SQLite via the validated Stage25C loader; AMarkets CSV market fallback is disabled.

## DB source of truth

- db_path: `data/local/xauusd_local_store.sqlite`
- candle_table: `bars`
- db_first: `True`
- csv_fallback_enabled: `False`
- m1_rows: `1532791` | span: `2022-05-01 23:01:00+00:00 → 2026-06-11 23:06:00+00:00`
- h1_rows: `25585` | span: `2022-05-01 23:00:00+00:00 → 2026-06-11 23:00:00+00:00`
- m15_rows: `102452` | span: `2022-05-01 23:15:00+00:00 → 2026-06-11 23:15:00+00:00`

## Discovery surface families

1. `hour_h1_bias_surface_v1` — fixed-hour follow/fade of H1 bias.
2. `london_direction_surface_v1` — follow/fade London direction conditioned on London range size known before/at entry.
3. `day_open_extension_surface_v1` — follow/fade extension away from day open known at entry.
4. `prior_day_location_surface_v1` — follow/fade position outside prior-day high/low.
5. `asia_london_alignment_surface_v1` — follow/fade Asia/London directional alignment.

## Counts

- candidates_tested: `22`
- candidates_passing_min_events: `22`
- promotion_review_candidates: `0`
- watchlist_only_candidates: `0`
- timed_out: `True`
- runtime_seconds: `185.0`

## Family coverage diagnostics
| family | candidates_tested | passing_min_events | best_pf_x4 | best_pf_x6 | best_total_x4 |
| --- | --- | --- | --- | --- | --- |
| london_direction_surface_v1 | 8 | 8 | 0.6157 | 0.4024 | -194.167 |
| day_open_extension_surface_v1 | 8 | 8 | 0.4612 | 0.3036 | -715.569 |
| hour_h1_bias_surface_v1 | 6 | 6 | 0.4389 | 0.2832 | -1660.6015 |

## Top candidate diagnostics
| decision | family | name | events | pf_x1 | pf_x4 | pf_x6 | boot_pf_p05_x4 | median_x4 | total_x4 | win_rate_x4 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| STAGE27A_REJECT | london_direction_surface_v1 | london_follow_h12_min0.8_tp08_sl08 | 243 | 1.1577 | 0.6157 | 0.4024 | 0.4757 | -0.2157 | -194.167 | 0.4486 |
| STAGE27A_REJECT | london_direction_surface_v1 | london_follow_h12_min1.1_tp08_sl08 | 243 | 1.1577 | 0.6157 | 0.4024 | 0.4757 | -0.2157 | -194.167 | 0.4486 |
| STAGE27A_REJECT | london_direction_surface_v1 | london_follow_h13_min0.8_tp08_sl08 | 213 | 1.0529 | 0.5094 | 0.3163 | 0.39 | -0.36 | -207.176 | 0.3991 |
| STAGE27A_REJECT | london_direction_surface_v1 | london_follow_h13_min1.1_tp08_sl08 | 213 | 1.0529 | 0.5094 | 0.3163 | 0.39 | -0.36 | -207.176 | 0.3991 |
| STAGE27A_REJECT | day_open_extension_surface_v1 | day_open_ext_fade_h9_min0.9_tp08_sl08 | 720 | 0.9297 | 0.4612 | 0.3036 | 0.369 | -0.5519 | -836.67 | 0.3222 |
| STAGE27A_REJECT | day_open_extension_surface_v1 | day_open_ext_fade_h9_min1.3_tp08_sl08 | 618 | 0.9308 | 0.4563 | 0.2988 | 0.3681 | -0.6328 | -715.569 | 0.3188 |
| STAGE27A_REJECT | hour_h1_bias_surface_v1 | h1_bias_follow_h11_hz180_tp08_sl08 | 1279 | 0.8605 | 0.4389 | 0.2832 | 0.3782 | -0.4493 | -1660.6015 | 0.4003 |
| STAGE27A_REJECT | hour_h1_bias_surface_v1 | h1_bias_fade_h15_hz180_tp08_sl08 | 1279 | 0.8272 | 0.4199 | 0.2659 | 0.3635 | -0.63 | -1743.1315 | 0.4269 |
| STAGE27A_REJECT | hour_h1_bias_surface_v1 | h1_bias_follow_h13_hz180_tp08_sl08 | 1279 | 0.831 | 0.4155 | 0.2628 | 0.3545 | -1.67 | -1720.5615 | 0.398 |
| STAGE27A_REJECT | day_open_extension_surface_v1 | day_open_ext_fade_h13_min0.9_tp08_sl08 | 645 | 0.8934 | 0.4126 | 0.2493 | 0.3448 | -0.3952 | -783.1487 | 0.4016 |
| STAGE27A_REJECT | hour_h1_bias_surface_v1 | h1_bias_follow_h15_hz180_tp08_sl08 | 1279 | 0.7788 | 0.3972 | 0.2517 | 0.3541 | -2.2795 | -1871.367 | 0.4128 |
| STAGE27A_REJECT | hour_h1_bias_surface_v1 | h1_bias_fade_h11_hz180_tp08_sl08 | 1279 | 0.7528 | 0.3896 | 0.2569 | 0.3338 | -2.3938 | -1946.4625 | 0.3597 |
| STAGE27A_REJECT | day_open_extension_surface_v1 | day_open_ext_fade_h13_min1.3_tp08_sl08 | 572 | 0.8411 | 0.3801 | 0.2264 | 0.3018 | -0.4881 | -742.116 | 0.3934 |
| STAGE27A_REJECT | hour_h1_bias_surface_v1 | h1_bias_fade_h13_hz180_tp08_sl08 | 1279 | 0.7654 | 0.3776 | 0.2384 | 0.3176 | -1.39 | -1886.5025 | 0.3886 |
| STAGE27A_REJECT | day_open_extension_surface_v1 | day_open_ext_follow_h9_min0.9_tp08_sl08 | 720 | 0.6714 | 0.3263 | 0.2139 | 0.2791 | -2.2581 | -1195.6875 | 0.2986 |
| STAGE27A_REJECT | day_open_extension_surface_v1 | day_open_ext_follow_h13_min1.3_tp08_sl08 | 572 | 0.715 | 0.3245 | 0.1974 | 0.2653 | -2.3583 | -875.8415 | 0.3462 |
| STAGE27A_REJECT | day_open_extension_surface_v1 | day_open_ext_follow_h13_min0.9_tp08_sl08 | 645 | 0.6809 | 0.3124 | 0.1922 | 0.2553 | -2.415 | -1039.2088 | 0.3395 |
| STAGE27A_REJECT | day_open_extension_surface_v1 | day_open_ext_follow_h9_min1.3_tp08_sl08 | 618 | 0.6608 | 0.3114 | 0.1994 | 0.2444 | -2.2334 | -1031.1885 | 0.3058 |
| STAGE27A_REJECT | london_direction_surface_v1 | london_fade_h12_min0.8_tp08_sl08 | 243 | 0.5749 | 0.3004 | 0.1997 | 0.2082 | -2.5843 | -486.233 | 0.321 |
| STAGE27A_REJECT | london_direction_surface_v1 | london_fade_h12_min1.1_tp08_sl08 | 243 | 0.5749 | 0.3004 | 0.1997 | 0.2082 | -2.5843 | -486.233 | 0.321 |
| STAGE27A_REJECT | london_direction_surface_v1 | london_fade_h13_min0.8_tp08_sl08 | 213 | 0.5947 | 0.273 | 0.1632 | 0.1919 | -2.44 | -389.224 | 0.3474 |
| STAGE27A_REJECT | london_direction_surface_v1 | london_fade_h13_min1.1_tp08_sl08 | 213 | 0.5947 | 0.273 | 0.1632 | 0.1919 | -2.44 | -389.224 | 0.3474 |

## Family-balanced top seeds
| decision | family | name | events | pf_x1 | pf_x4 | pf_x6 | boot_pf_p05_x4 | median_x4 | total_x4 | win_rate_x4 | rank_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| STAGE27A_REJECT | london_direction_surface_v1 | london_follow_h12_min0.8_tp08_sl08 | 243 | 1.1577 | 0.6157 | 0.4024 | 0.4757 | -0.2157 | -194.167 | 0.4486 | 1.5517 |
| STAGE27A_REJECT | london_direction_surface_v1 | london_follow_h12_min1.1_tp08_sl08 | 243 | 1.1577 | 0.6157 | 0.4024 | 0.4757 | -0.2157 | -194.167 | 0.4486 | 1.5517 |
| STAGE27A_REJECT | london_direction_surface_v1 | london_follow_h13_min0.8_tp08_sl08 | 213 | 1.0529 | 0.5094 | 0.3163 | 0.39 | -0.36 | -207.176 | 0.3991 | 1.2204 |
| STAGE27A_REJECT | london_direction_surface_v1 | london_follow_h13_min1.1_tp08_sl08 | 213 | 1.0529 | 0.5094 | 0.3163 | 0.39 | -0.36 | -207.176 | 0.3991 | 1.2204 |
| STAGE27A_REJECT | day_open_extension_surface_v1 | day_open_ext_fade_h9_min0.9_tp08_sl08 | 720 | 0.9297 | 0.4612 | 0.3036 | 0.369 | -0.5519 | -836.67 | 0.3222 | 1.1145 |
| STAGE27A_REJECT | day_open_extension_surface_v1 | day_open_ext_fade_h9_min1.3_tp08_sl08 | 618 | 0.9308 | 0.4563 | 0.2988 | 0.3681 | -0.6328 | -715.569 | 0.3188 | 1.1014 |
| STAGE27A_REJECT | hour_h1_bias_surface_v1 | h1_bias_follow_h11_hz180_tp08_sl08 | 1279 | 0.8605 | 0.4389 | 0.2832 | 0.3782 | -0.4493 | -1660.6015 | 0.4003 | 1.0697 |
| STAGE27A_REJECT | hour_h1_bias_surface_v1 | h1_bias_fade_h15_hz180_tp08_sl08 | 1279 | 0.8272 | 0.4199 | 0.2659 | 0.3635 | -0.63 | -1743.1315 | 0.4269 | 1.0093 |
| STAGE27A_REJECT | hour_h1_bias_surface_v1 | h1_bias_follow_h13_hz180_tp08_sl08 | 1279 | 0.831 | 0.4155 | 0.2628 | 0.3545 | -1.67 | -1720.5615 | 0.398 | 0.9905 |
| STAGE27A_REJECT | day_open_extension_surface_v1 | day_open_ext_fade_h13_min0.9_tp08_sl08 | 645 | 0.8934 | 0.4126 | 0.2493 | 0.3448 | -0.3952 | -783.1487 | 0.4016 | 0.963 |
| STAGE27A_REJECT | hour_h1_bias_surface_v1 | h1_bias_follow_h15_hz180_tp08_sl08 | 1279 | 0.7788 | 0.3972 | 0.2517 | 0.3541 | -2.2795 | -1871.367 | 0.4128 | 0.9517 |
| STAGE27A_REJECT | day_open_extension_surface_v1 | day_open_ext_fade_h13_min1.3_tp08_sl08 | 572 | 0.8411 | 0.3801 | 0.2264 | 0.3018 | -0.4881 | -742.116 | 0.3934 | 0.8483 |

## Interpretation

- Stage27A is not another mutation of Stage26A/B/C entries; it maps simple outcome surfaces to identify whether any broad time/regime/direction asymmetry exists.
- A promotion-review result here is still research-only and would require a dedicated validation stage and separate forward-shadow tracker.
- If no surface candidate survives, discovery should pivot toward no-trade/regime gating around the already stronger Stage23/25 lineage rather than inventing more raw entries.

## Operational reminder

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage18a_unified_shadow_ops_cycle
python3 -m app.stage23d_forward_shadow_candidate
python3 -m app.stage25d_db_first_filtered_forward_shadow
```

## Output files

- `data/reports/stage27a_db_first_outcome_surface_discovery/stage27a_db_first_outcome_surface_discovery.json`
- `data/reports/stage27a_db_first_outcome_surface_discovery/stage27a_db_first_outcome_surface_discovery.md`
- `data/reports/stage27a_db_first_outcome_surface_discovery/stage27a_surface_candidates.csv`
- `data/reports/stage27a_db_first_outcome_surface_discovery/stage27a_family_balanced_top.csv`
- `data/reports/stage27a_db_first_outcome_surface_discovery/stage27a_exact_trades.csv`
- `data/reports/stage27a_db_first_outcome_surface_discovery/stage27a_family_coverage.csv`
- `data/reports/stage27a_db_first_outcome_surface_discovery/stage27a_db_schema_diagnostic.csv`