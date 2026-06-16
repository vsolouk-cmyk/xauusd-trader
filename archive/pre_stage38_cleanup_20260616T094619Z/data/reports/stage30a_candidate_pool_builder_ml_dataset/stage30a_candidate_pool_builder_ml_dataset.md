# Stage30A Candidate Pool Builder + ML-ready Meta Dataset

Generated UTC: `2026-06-14T18:04:31.198582+00:00`

## Decision

```text
STAGE30A_ML_META_DATASET_READY_FOR_STAGE30B_REVIEW_ONLY
```

## Scope guardrails

- Research/shadow dataset building only.
- No EA change, no automatic trading, no paper/live/order authorization.
- DB candle access is DB-first through Stage25C loader when available.
- Existing CSV trade artifacts are research artifacts only, not market-data fallback.
- Exported ML features are restricted to a forward-safe whitelist.

## DB source of truth

```json
{
  "loader_mode": "reused:app.stage25c_deduped_filter_validation.load_bars_from_db",
  "db_path": "data/local/xauusd_local_store.sqlite",
  "db_first": true,
  "csv_fallback_enabled": false,
  "candle_table": "bars",
  "m1_mode": "db_schema_introspection",
  "m1_rows": 1534217,
  "m1_span": "2022-05-01 23:01:00+00:00 → 2026-06-12 23:54:00+00:00",
  "h1_mode": "db_schema_introspection",
  "h1_rows": 25608,
  "h1_span": "2022-05-01 23:00:00+00:00 → 2026-06-12 23:00:00+00:00",
  "m1_rows_stage30a": 1534217,
  "h1_rows_stage30a": 25608
}
```

## Enrichment diagnostics

```json
{
  "db_session_enrichment": false,
  "h1_enrichment": true,
  "db_session_enrichment_warning": "TypeError: \"value\" parameter must be a scalar, dict or Series, but you passed a \"ndarray\""
}
```

## Counts

- artifact_count_discovered: `10`
- artifact_count_loaded: `6`
- ml_dataset_rows: `17951`
- feature_cols_ready_count: `12`
- feature_cols_ready: `prior_day_range, asia_range, asia_eff, london_range, london_eff, h1_range, h1_atr20, h1_atr20_pct_rank_250, direction_num, entry_hour, dow, month`
- min_pool_events: `250`

## Base dataset metrics

```json
{
  "events": 17951,
  "pf_x1": 0.70996,
  "pf_x4": 0.284247,
  "pf_x6": 0.164538,
  "total_x4": -26397.566135,
  "win_rate_x4": 0.298368,
  "median_x4": -1.4,
  "years_positive_x4": 0,
  "year_count": 5
}
```

## Top feature quality diagnostics

| feature | gate | status | retained_events | retained_ratio | pf_x4 | pf_x6 | total_x4 | win_rate_x4 | rank_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| direction_num | direction_num==0.0 | categorical_bucket | 100.0 | 0.0056 | 2.8514 | 1.6534 | 127.6156 | 0.81 | 3.2358 |
| prior_day_aligned |  | low_coverage |  |  |  |  |  |  | 0.0 |
| london_aligned |  | low_coverage |  |  |  |  |  |  | 0.0 |
| entry_hour | entry_hour==15 | categorical_bucket | 1062.0 | 0.0592 | 0.3351 | 0.1927 | -1363.5501 | 0.339 | -2.6281 |
| entry_hour | entry_hour==14 | categorical_bucket | 1062.0 | 0.0592 | 0.2698 | 0.1488 | -1610.9086 | 0.3371 | -3.199 |
| month | month==1.0 | categorical_bucket | 1436.0 | 0.08 | 0.3159 | 0.1936 | -1892.3738 | 0.2876 | -3.7047 |
| month | month==6.0 | categorical_bucket | 1403.0 | 0.0782 | 0.2664 | 0.1371 | -1861.6323 | 0.2901 | -3.7068 |
| month | month==4.0 | categorical_bucket | 1418.0 | 0.079 | 0.4445 | 0.2941 | -1986.8526 | 0.4083 | -3.74 |
| month | month==5.0 | categorical_bucket | 1761.0 | 0.0981 | 0.426 | 0.26 | -2070.6044 | 0.3725 | -3.9345 |
| month | month==12.0 | categorical_bucket | 1474.0 | 0.0821 | 0.2288 | 0.1094 | -1979.4623 | 0.2849 | -3.987 |
| month | month==11.0 | categorical_bucket | 1535.0 | 0.0855 | 0.2496 | 0.1326 | -2236.9943 | 0.2671 | -4.4755 |
| month | month==7.0 | categorical_bucket | 1442.0 | 0.0803 | 0.1018 | 0.0213 | -2170.5902 | 0.2552 | -4.5183 |
| month | month==8.0 | categorical_bucket | 1511.0 | 0.0842 | 0.0931 | 0.0197 | -2200.3182 | 0.2277 | -4.5868 |
| month | month==10.0 | categorical_bucket | 1593.0 | 0.0887 | 0.2905 | 0.1774 | -2346.0819 | 0.3176 | -4.6416 |
| month | month==9.0 | categorical_bucket | 1486.0 | 0.0828 | 0.1242 | 0.0401 | -2293.0696 | 0.2416 | -4.7362 |
| month | month==3.0 | categorical_bucket | 1551.0 | 0.0864 | 0.4005 | 0.2752 | -2468.1234 | 0.3507 | -4.7512 |
| month | month==2.0 | categorical_bucket | 1341.0 | 0.0747 | 0.27 | 0.1865 | -2891.4631 | 0.261 | -5.7506 |
| dow | dow==0 | categorical_bucket | 2727.0 | 0.1519 | 0.3187 | 0.1916 | -4055.875 | 0.3308 | -8.0294 |
| dow | dow==2 | categorical_bucket | 3747.0 | 0.2087 | 0.3255 | 0.1865 | -4886.0009 | 0.3109 | -9.6842 |
| dow | dow==3 | categorical_bucket | 3768.0 | 0.2099 | 0.281 | 0.1636 | -5645.1478 | 0.3049 | -11.2527 |
| dow | dow==4 | categorical_bucket | 3822.0 | 0.2129 | 0.2446 | 0.1399 | -5693.8129 | 0.2439 | -11.3923 |
| entry_hour | entry_hour==9 | categorical_bucket | 4067.0 | 0.2266 | 0.2736 | 0.1642 | -5860.6854 | 0.2186 | -11.691 |
| entry_hour | entry_hour==12 | categorical_bucket | 4133.0 | 0.2302 | 0.2555 | 0.1414 | -5988.3517 | 0.2848 | -11.9701 |
| london_eff | london_eff_ge_q75 | numeric_quantile | 4497.0 | 0.2505 | 0.3225 | 0.1868 | -6031.3551 | 0.3213 | -11.9778 |
| dow | dow==1 | categorical_bucket | 3887.0 | 0.2165 | 0.2626 | 0.1498 | -6116.7296 | 0.3108 | -12.2176 |
| prior_day_range | prior_day_range_le_q25 | numeric_quantile | 4499.0 | 0.2506 | 0.0869 | 0.0279 | -6200.296 | 0.1767 | -12.591 |
| h1_atr20_pct_rank_250 | h1_atr20_pct_rank_250_le_q25 | numeric_quantile | 4508.0 | 0.2511 | 0.2006 | 0.0959 | -6333.8263 | 0.274 | -12.7273 |
| asia_eff | asia_eff_le_q25 | numeric_quantile | 4490.0 | 0.2501 | 0.3329 | 0.2065 | -6471.5436 | 0.3051 | -12.8428 |
| h1_atr20 | h1_atr20_le_q25 | numeric_quantile | 4490.0 | 0.2501 | 0.0114 | 0.0007 | -6332.1757 | 0.057 | -12.9371 |
| h1_range | h1_range_le_q25 | numeric_quantile | 4505.0 | 0.251 | 0.0156 | 0.0015 | -6381.6139 | 0.0677 | -13.0315 |

## Candidate family contribution

| source_stage | family | events | pf_x4 | pf_x6 | total_x4 | win_rate_x4 | candidate_count | source_file_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| STAGE28A | calendar_time_risk_proxy_v1 | 5570 | 0.2715 | 0.1543 | -7619.0428 | 0.2512 | 6 | 1 |
| STAGE28A | volatility_transition_v1 | 4129 | 0.3106 | 0.1733 | -5393.8876 | 0.3306 | 6 | 1 |
| STAGE28A | session_handoff_imbalance_v1 | 3186 | 0.3132 | 0.1787 | -4349.5396 | 0.3384 | 6 | 1 |
| STAGE28A | session_compression_expansion_v1 | 1734 | 0.3112 | 0.1867 | -2275.0288 | 0.2359 | 6 | 1 |
| STAGE28A | liquidity_sweep_regime_v1 | 931 | 0.2073 | 0.118 | -1619.6264 | 0.2599 | 6 | 1 |
| STAGE29A | high_range_london_continuation_v1 | 850 | 0.133 | 0.0808 | -2409.6456 | 0.2482 | 3 | 1 |
| STAGE29A | high_range_broad_pullback_continuation_v1 | 762 | 0.1642 | 0.1022 | -2101.2078 | 0.2861 | 3 | 1 |
| STAGE29A | high_range_asia_london_alignment_v1 | 284 | 0.2 | 0.1255 | -687.8209 | 0.2923 | 2 | 1 |
| STAGE29A | high_range_london_breakout_follow_v1 | 105 | 0.0781 | 0.0442 | -452.229 | 0.2571 | 2 | 1 |
| STAGE25C | london_oneway_continuation | 100 | 2.8514 | 1.6534 | 127.6156 | 0.81 | 1 | 1 |
| STAGE27B | london_oneway_continuation | 100 | 2.8514 | 1.6534 | 127.6156 | 0.81 | 1 | 1 |
| STAGE27C | london_oneway_continuation | 100 | 2.8514 | 1.6534 | 127.6156 | 0.81 | 1 | 1 |
| STAGE28B | london_oneway_continuation | 100 | 2.8514 | 1.6534 | 127.6156 | 0.81 | 1 | 1 |

## Artifact manifest sample

| status | path | rows_raw | rows_loaded | reason |
| --- | --- | --- | --- | --- |
| error | data/reports/stage23d_forward_shadow_candidate/stage23d_forward_shadow_ledger.csv | 0 | 0 | read_csv: No columns to parse from file |
| loaded | data/reports/stage25c_deduped_filter_validation/stage25c_enriched_canonical_trades.csv | 100 | 100 | loaded |
| error | data/reports/stage25d_db_first_filtered_forward_shadow/stage25d_filtered_forward_shadow_ledger.csv | 0 | 0 | read_csv: No columns to parse from file |
| loaded | data/reports/stage27b_db_first_lineage_gate_discovery/stage27b_enriched_lineage_trades.csv | 100 | 100 | loaded |
| loaded | data/reports/stage27c_db_first_h1_atr_gate_validation/stage27c_enriched_h1_atr_trades.csv | 100 | 100 | loaded |
| error | data/reports/stage27d_db_first_h1_atr_filtered_forward_shadow/stage27d_h1_atr_filtered_forward_shadow_ledger.csv | 0 | 0 | read_csv: No columns to parse from file |
| loaded | data/reports/stage28a_discovery_factory_batch_runner/stage28a_exact_trades.csv | 16422 | 16422 | loaded |
| loaded | data/reports/stage28b_ml_meta_feature_screen/stage28b_normalized_lineage_trades.csv | 100 | 100 | loaded |
| error | data/reports/stage28d_forward_safe_meta_gate_tracker/stage28d_meta_gate_forward_shadow_ledger.csv | 0 | 0 | read_csv: No columns to parse from file |
| loaded | data/reports/stage29a_high_range_regime_continuation_discovery/stage29a_exact_trades.csv | 2001 | 2001 | loaded |

## Interpretation

- Stage30A does not decide a tradable strategy. It creates the ML-ready dataset for Stage30B.
- If `ml_dataset_rows` is low, Stage30B should stay ML-lite and avoid high-capacity models.
- If enough rows and feature coverage exist, the next stage can run simple, auditable classifiers/rankers.
- Any model result from Stage30B remains research-only and requires validation plus forward-shadow tracking.

## Operational reminder

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.run_active_shadow_suite
python3 -m app.stage30a_candidate_pool_builder_ml_dataset
```

## Output files

- `/Users/vahid/Desktop/xauusd-trader/data/reports/stage30a_candidate_pool_builder_ml_dataset/stage30a_candidate_pool_builder_ml_dataset.json`
- `/Users/vahid/Desktop/xauusd-trader/data/reports/stage30a_candidate_pool_builder_ml_dataset/stage30a_candidate_pool_builder_ml_dataset.md`
- `/Users/vahid/Desktop/xauusd-trader/data/reports/stage30a_candidate_pool_builder_ml_dataset/stage30a_ml_meta_dataset.csv`
- `/Users/vahid/Desktop/xauusd-trader/data/reports/stage30a_candidate_pool_builder_ml_dataset/stage30a_feature_quality_report.csv`
- `/Users/vahid/Desktop/xauusd-trader/data/reports/stage30a_candidate_pool_builder_ml_dataset/stage30a_candidate_family_contribution.csv`
- `/Users/vahid/Desktop/xauusd-trader/data/reports/stage30a_candidate_pool_builder_ml_dataset/stage30a_artifact_manifest.csv`
