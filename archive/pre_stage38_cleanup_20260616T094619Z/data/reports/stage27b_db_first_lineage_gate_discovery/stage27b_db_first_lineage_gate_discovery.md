# Stage27B DB-First Lineage Gate Discovery

Generated UTC: `2026-06-14T17:58:44.107653+00:00`

## Decision

```text
STAGE27B_HAS_GATE_CANDIDATE_REVIEW_ONLY
```

## Scope guardrails

- Research/shadow gate discovery only.
- Stage18A v2 remains the active operational forward-shadow runner.
- Stage23D and Stage25D remain separate DB-first trackers.
- No EA change, no automatic trading, no paper/live/order authorization.
- Candles/regime features are DB-first from SQLite via the validated Stage25C loader; AMarkets CSV market fallback is disabled.
- Prior trade CSVs are used only as research artifacts, not as market-data fallback.

## DB source of truth

- db_path: `data/local/xauusd_local_store.sqlite`
- candle_table: `bars`
- db_first: `True`
- csv_fallback_enabled: `False`
- m1_rows: `1534217` | span: `2022-05-01 23:01:00+00:00 → 2026-06-12 23:54:00+00:00`
- h1_rows: `25608` | span: `2022-05-01 23:00:00+00:00 → 2026-06-12 23:00:00+00:00`
- m15_rows: `102547` | span: `2022-05-01 23:15:00+00:00 → 2026-06-13 00:00:00+00:00`

## Trade artifact

- selected_artifact: `data/reports/stage25c_deduped_filter_validation/stage25c_enriched_canonical_trades.csv`
- requested_candidate: `S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65`
- rows_after_event_dedup: `100`

| path | exists | rows | status |
| --- | --- | --- | --- |
| data/reports/stage25c_deduped_filter_validation/stage25c_enriched_canonical_trades.csv | True | 100 | loaded |

## Base lineage metrics before new gates

```json
{
  "events": 100,
  "pf_x1": 5.578963613461408,
  "pf_x4": 2.851412305366161,
  "pf_x6": 1.653421789024173,
  "boot_pf_p05_x4": 1.7789723241189819,
  "median_x4": 1.0293600000000005,
  "total_x4": 127.61561,
  "win_rate_x4": 0.81,
  "years_positive_x4": 4,
  "year_count": 5
}
```

## Counts

- gate_candidates_tested: `29`
- gate_candidate_review_count: `6`
- watchlist_only_count: `1`
- runtime_seconds: `15.21`

## Top gate diagnostics
| decision | gate_name | gate_kind | retained_events | retained_ratio | pf_x1 | pf_x4 | pf_x6 | boot_pf_p05_x4 | median_x4 | total_x4 | win_rate_x4 | years_positive_x4 | year_count | improvement_pf_x4 | improvement_pf_x6 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| STAGE27B_GATE_CANDIDATE_REVIEW_ONLY | h1_atr_drop_low30 | volatility | 59 | 0.59 | 8.0999 | 4.7712 | 3.288 | 2.4634 | 1.4401 | 137.7543 | 0.8644 | 4 | 5 | 1.9198 | 1.6346 |
| STAGE27B_GATE_CANDIDATE_REVIEW_ONLY | prior_range_drop_low30 | regime | 50 | 0.5 | 8.6224 | 4.7532 | 2.9675 | 2.0587 | 1.2593 | 107.3271 | 0.82 | 3 | 4 | 1.9018 | 1.314 |
| STAGE27B_GATE_CANDIDATE_REVIEW_ONLY | prior_range_drop_low40 | regime | 46 | 0.46 | 8.2522 | 4.6286 | 2.9657 | 2.418 | 1.501 | 103.7634 | 0.8043 | 3 | 4 | 1.7772 | 1.3122 |
| STAGE27B_GATE_CANDIDATE_REVIEW_ONLY | prior_range_drop_low20 | regime | 57 | 0.57 | 8.1767 | 4.5306 | 2.84 | 2.2923 | 1.33 | 118.2571 | 0.8246 | 3 | 4 | 1.6792 | 1.1866 |
| STAGE27B_GATE_CANDIDATE_REVIEW_ONLY | drop_monday | calendar | 78 | 0.78 | 7.4145 | 3.7003 | 2.0479 | 2.1905 | 1.0114 | 114.7057 | 0.8333 | 4 | 5 | 0.8489 | 0.3945 |
| STAGE27B_GATE_CANDIDATE_REVIEW_ONLY | keep_h1_aligned | bias | 53 | 0.53 | 6.8031 | 3.6948 | 2.2358 | 1.9885 | 1.0523 | 90.7205 | 0.8302 | 4 | 5 | 0.8434 | 0.5824 |
| STAGE27B_WATCHLIST_ONLY | keep_short_only | direction_diag | 45 | 0.45 | 8.7853 | 4.8171 | 2.9188 | 2.2302 | 1.0471 | 92.9491 | 0.8444 | 5 | 5 | 1.9657 | 1.2654 |
| STAGE27B_REJECT | keep_london_aligned | bias | 99 | 0.99 | 5.9337 | 3.0312 | 1.7483 | 1.7059 | 1.0313 | 131.7029 | 0.8182 | 4 | 5 | 0.1797 | 0.0949 |
| STAGE27B_REJECT | drop_friday | calendar | 80 | 0.8 | 5.1118 | 2.5764 | 1.47 | 1.4067 | 0.9066 | 90.5218 | 0.8 | 3 | 5 | -0.275 | -0.1835 |
| STAGE27B_REJECT | drop_h1_aligned | bias | 47 | 0.47 | 4.3718 | 2.0463 | 1.0892 | 1.0418 | 0.8641 | 36.8951 | 0.7872 | 3 | 5 | -0.8052 | -0.5642 |
| STAGE27B_REJECT | keep_long_only | direction_diag | 55 | 0.55 | 3.8182 | 1.7777 | 0.9317 | 1.1225 | 0.9914 | 34.6665 | 0.7818 | 3 | 5 | -1.0738 | -0.7217 |
| STAGE27B_REJECT | h1_atr_drop_high70 | volatility | 72 | 0.72 | 2.9866 | 1.1971 | 0.5049 | 0.8054 | 0.673 | 11.8358 | 0.7639 | 2 | 5 | -1.6543 | -1.1486 |
| STAGE27B_REJECT | london_range_drop_low20 | regime | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -2.8514 | -1.6534 |
| STAGE27B_REJECT | asia_range_drop_low20 | regime | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -2.8514 | -1.6534 |
| STAGE27B_REJECT | london_range_drop_low30 | regime | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -2.8514 | -1.6534 |
| STAGE27B_REJECT | asia_range_drop_low30 | regime | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -2.8514 | -1.6534 |
| STAGE27B_REJECT | london_range_drop_low40 | regime | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -2.8514 | -1.6534 |
| STAGE27B_REJECT | asia_range_drop_low40 | regime | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -2.8514 | -1.6534 |
| STAGE27B_REJECT | london_range_drop_high70 | regime | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -2.8514 | -1.6534 |
| STAGE27B_REJECT | asia_range_drop_high70 | regime | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -2.8514 | -1.6534 |
| STAGE27B_REJECT | london_range_drop_high80 | regime | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -2.8514 | -1.6534 |
| STAGE27B_REJECT | asia_range_drop_high80 | regime | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -2.8514 | -1.6534 |
| STAGE27B_REJECT | london_eff_drop_low20 | regime | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -2.8514 | -1.6534 |
| STAGE27B_REJECT | london_eff_drop_low30 | regime | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -2.8514 | -1.6534 |
| STAGE27B_REJECT | london_range_drop_low30_and_h1_atr_drop_high70 | combo | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -2.8514 | -1.6534 |
| STAGE27B_REJECT | london_range_drop_low30_and_london_aligned | combo | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -2.8514 | -1.6534 |
| STAGE27B_REJECT | london_range_drop_low30_and_h1_aligned | combo | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -2.8514 | -1.6534 |
| STAGE27B_REJECT | london_range_drop_low30_and_short_only | combo_direction_diag | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -2.8514 | -1.6534 |
| STAGE27B_REJECT | drop_london_aligned | bias | 1 | 0.01 | 0 | 0 | 0 | 0 | -4.0873 | -4.0873 | 0 | 0 | 1 | -2.8514 | -1.6534 |

## Top gate split diagnostics
| gate_name | split | bucket | events | pf_x4 | pf_x6 | total_x4 | win_rate_x4 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| h1_atr_drop_low30 | year | 2022 | 7 | 0.7175 | 0.2372 | -2.2534 | 0.7143 |
| h1_atr_drop_low30 | year | 2023 | 13 | 1.9551 | 0.7536 | 6.9548 | 0.8462 |
| h1_atr_drop_low30 | year | 2024 | 21 | 3.1783 | 1.6212 | 21.7854 | 0.9048 |
| h1_atr_drop_low30 | year | 2025 | 14 | 5.6816 | 4.3905 | 52.746 | 0.8571 |
| h1_atr_drop_low30 | year | 2026 | 4 | inf | inf | 58.5216 | 1 |
| h1_atr_drop_low30 | direction | -1 | 28 | 6.3831 | 4.611 | 90.3028 | 0.8571 |
| h1_atr_drop_low30 | direction | 1 | 31 | 3.4023 | 2.1407 | 47.4515 | 0.871 |
| h1_atr_drop_low30 | entry_hour | 13 | 59 | 4.7712 | 3.288 | 137.7543 | 0.8644 |
| h1_atr_drop_low30 | year_direction | 2022/-1 | 5 | 1.2591 | 0.4282 | 0.9666 | 0.8 |
| h1_atr_drop_low30 | year_direction | 2022/1 | 2 | 0.2419 | 0.0662 | -3.22 | 0.5 |
| h1_atr_drop_low30 | year_direction | 2023/-1 | 7 | 2.1376 | 0.8037 | 4.0619 | 0.8571 |
| h1_atr_drop_low30 | year_direction | 2023/1 | 6 | 1.7795 | 0.7053 | 2.8929 | 0.8333 |
| h1_atr_drop_low30 | year_direction | 2024/-1 | 8 | 2.9042 | 1.6435 | 9.1436 | 0.875 |
| h1_atr_drop_low30 | year_direction | 2024/1 | 13 | 3.4315 | 1.6004 | 12.6418 | 0.9231 |
| h1_atr_drop_low30 | year_direction | 2025/-1 | 5 | 6.8257 | 5.4151 | 27.2191 | 0.8 |
| h1_atr_drop_low30 | year_direction | 2025/1 | 9 | 4.871 | 3.6358 | 25.5269 | 0.8889 |
| h1_atr_drop_low30 | year_direction | 2026/-1 | 3 | inf | inf | 48.9116 | 1 |
| h1_atr_drop_low30 | year_direction | 2026/1 | 1 | inf | inf | 9.61 | 1 |
| h1_atr_drop_low30 | dow | 0 | 14 | 2.2656 | 1.5184 | 18.4427 | 0.7857 |
| h1_atr_drop_low30 | dow | 1 | 9 | 11.2328 | 8.7268 | 47.8104 | 0.8889 |
| h1_atr_drop_low30 | dow | 2 | 10 | 6.5603 | 4.0878 | 20.6355 | 0.9 |
| h1_atr_drop_low30 | dow | 3 | 11 | 1.9185 | 1.0348 | 8.0551 | 0.8182 |
| h1_atr_drop_low30 | dow | 4 | 15 | 9.9155 | 6.8727 | 42.8106 | 0.9333 |

## Interpretation

- Stage27B does not invent a new entry rule; it evaluates forward-safe no-trade/regime gates around the stronger Stage23/25 lineage.
- Direction-only gates are marked diagnostic and are not standalone market-regime filters.
- A gate-candidate result remains research-only and requires a dedicated validation stage plus a separate forward-shadow tracker before any operational consideration.
- If no gate candidate improves the canonical lineage, discovery should move toward broader data-quality/broker-source checks or higher-timeframe thesis changes rather than repeated micro-entry mutations.

## Operational reminder

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage18a_unified_shadow_ops_cycle
python3 -m app.stage23d_forward_shadow_candidate
python3 -m app.stage25d_db_first_filtered_forward_shadow
```

## Output files

- `data/reports/stage27b_db_first_lineage_gate_discovery/stage27b_db_first_lineage_gate_discovery.json`
- `data/reports/stage27b_db_first_lineage_gate_discovery/stage27b_db_first_lineage_gate_discovery.md`
- `data/reports/stage27b_db_first_lineage_gate_discovery/stage27b_artifact_manifest.csv`
- `data/reports/stage27b_db_first_lineage_gate_discovery/stage27b_enriched_lineage_trades.csv`
- `data/reports/stage27b_db_first_lineage_gate_discovery/stage27b_gate_candidates.csv`
- `data/reports/stage27b_db_first_lineage_gate_discovery/stage27b_top_gate_splits.csv`
- `data/reports/stage27b_db_first_lineage_gate_discovery/stage27b_db_schema_diagnostic.csv`