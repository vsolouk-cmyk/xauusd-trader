# Stage28A DB-First Discovery Factory Batch Runner

Generated UTC: `2026-06-14T17:58:27.482467+00:00`

## Decision

```text
STAGE28A_NO_PROMOTION_KEEP_DISCOVERY_OPEN
```

## Scope guardrails

- Research/shadow discovery only.
- Stage18A/Stage23D/Stage25D/Stage27D remain unchanged.
- No EA change, no automatic trading, no paper/live/order authorization.
- Candles are DB-first from SQLite; AMarkets CSV market fallback is disabled.

## DB source of truth

- loader_mode: `reused:app.stage25c_deduped_filter_validation.load_bars_from_db`
- db_path: `data/local/xauusd_local_store.sqlite`
- db_first: `True`
- csv_fallback_enabled: `False`
- m1_rows: `1534217`
- h1_rows: `25608`
- m15_rows: `102355`
- m1_span: `2022-05-01 23:01:00+00:00 → 2026-06-12 23:54:00+00:00`
- h1_span: `2022-05-01 23:00:00+00:00 → 2026-06-12 23:00:00+00:00`
- m15_span: `2022-05-01 23:00:00+00:00 → 2026-06-12 23:45:00+00:00`

## Counts

- registry_candidate_count: `71`
- scheduled_candidate_count: `30`
- max_candidates_per_family: `6`
- candidates_tested: `30`
- candidates_passing_min_events: `28`
- candidate_review_count: `0`
- watchlist_only_count: `0`
- family_count: `5`
- timed_out: `False`
- runtime_seconds: `172.74`

## Family coverage

| family | candidates_tested | passing_min_events | best_pf_x4 | best_total_x4 |
| --- | --- | --- | --- | --- |
| session_compression_expansion_v1 | 6 | 6 | 0.5905 | -253.7795 |
| liquidity_sweep_regime_v1 | 6 | 4 | 0.4459 | -52.3932 |
| volatility_transition_v1 | 6 | 6 | 0.4051 | -654.5864 |
| session_handoff_imbalance_v1 | 6 | 6 | 0.3974 | -609.0585 |
| calendar_time_risk_proxy_v1 | 6 | 6 | 0.3591 | -757.2411 |

## Top candidate diagnostics

| decision | family | name | events | pf_x1 | pf_x4 | pf_x6 | boot_pf_p05_x4 | median_x4 | total_x4 | win_rate_x4 | rank_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| STAGE28A_REJECT | session_compression_expansion_v1 | sess_comp_exp_fade_london_h9_q0.7_tp06_sl065 | 415 | 1.1467 | 0.5905 | 0.389 | 0.4589 | -0.4526 | -344.0792 | 0.3711 | 0.5371 |
| STAGE28A_REJECT | volatility_transition_v1 | vol_trans_follow_h1_low_to_high_h13_tp06_sl065 | 808 | 0.8923 | 0.4051 | 0.2396 | 0.3359 | -0.246 | -983.3256 | 0.4257 | 0.1838 |
| STAGE28A_REJECT | session_handoff_imbalance_v1 | handoff_align_follow_h13_tp06_sl065 | 540 | 0.9419 | 0.3974 | 0.2316 | 0.3133 | -0.4439 | -609.0585 | 0.3778 | 0.1528 |
| STAGE28A_REJECT | liquidity_sweep_regime_v1 | liq_pdl_breakout_follow_h12_tp06_sl065 | 183 | 0.9681 | 0.4459 | 0.2799 | 0.2481 | -0.3911 | -200.6378 | 0.3552 | 0.1355 |
| STAGE28A_REJECT | volatility_transition_v1 | vol_trans_follow_h1_low_to_high_h12_tp06_sl065 | 809 | 0.8301 | 0.3735 | 0.2235 | 0.3059 | -0.3959 | -1066.5805 | 0.3894 | 0.1215 |
| STAGE28A_REJECT | volatility_transition_v1 | vol_trans_fade_h1_low_to_high_h12_tp06_sl065 | 809 | 0.7828 | 0.3546 | 0.2152 | 0.2916 | -0.4628 | -1136.2918 | 0.3634 | 0.0876 |
| STAGE28A_REJECT | calendar_time_risk_proxy_v1 | calendar_keep_tue_wed_thu_h13_tp06_sl065 | 645 | 0.9045 | 0.3591 | 0.2016 | 0.2884 | -0.4394 | -757.2411 | 0.355 | 0.081 |
| STAGE28A_REJECT | session_compression_expansion_v1 | sess_comp_exp_follow_london_h9_q0.7_tp06_sl065 | 415 | 0.6971 | 0.3597 | 0.2409 | 0.2531 | -2.2837 | -683.013 | 0.3108 | 0.0718 |
| STAGE28A_REJECT | session_handoff_imbalance_v1 | handoff_divergence_fade_h15_tp06_sl065 | 522 | 0.8933 | 0.3564 | 0.205 | 0.2673 | -0.5177 | -620.2782 | 0.3276 | 0.0631 |
| STAGE28A_REJECT | session_handoff_imbalance_v1 | handoff_align_follow_h14_tp06_sl065 | 540 | 0.8089 | 0.3299 | 0.1833 | 0.2432 | -0.6122 | -713.8418 | 0.3759 | 0.0074 |
| STAGE28A_REJECT | session_handoff_imbalance_v1 | handoff_align_follow_h15_tp06_sl065 | 540 | 0.7769 | 0.3161 | 0.1817 | 0.2341 | -0.5228 | -743.2719 | 0.35 | -0.0138 |
| STAGE28A_REJECT | liquidity_sweep_regime_v1 | liq_pdh_reclaim_fade_h12_tp06_sl065 | 35 | 0.6114 | 0.2227 | 0.1247 | 0.0608 | -1.4 | -52.3932 | 0.2 | -0.0545 |
| STAGE28A_REJECT | session_handoff_imbalance_v1 | handoff_divergence_fade_h13_tp06_sl065 | 522 | 0.714 | 0.2809 | 0.1623 | 0.2047 | -0.6948 | -766.0224 | 0.2989 | -0.0818 |
| STAGE28A_REJECT | calendar_time_risk_proxy_v1 | calendar_drop_friday_h13_tp06_sl065 | 1288 | 0.7946 | 0.2663 | 0.1443 | 0.2276 | -1.4 | -1632.4717 | 0.2523 | -0.0879 |
| STAGE28A_REJECT | calendar_time_risk_proxy_v1 | calendar_drop_monday_h13_tp06_sl065 | 1288 | 0.7865 | 0.2647 | 0.145 | 0.221 | -1.4 | -1642.3336 | 0.2438 | -0.0936 |
| STAGE28A_REJECT | calendar_time_risk_proxy_v1 | calendar_keep_tue_wed_thu_h9_tp06_sl065 | 645 | 0.6474 | 0.249 | 0.1471 | 0.208 | -2.0971 | -991.6556 | 0.2248 | -0.1181 |
| STAGE28A_REJECT | volatility_transition_v1 | vol_trans_follow_h1_high_cooling_h13_tp06_sl065 | 571 | 0.897 | 0.2373 | 0.1116 | 0.1824 | -0.5564 | -654.5864 | 0.275 | -0.1701 |
| STAGE28A_REJECT | session_handoff_imbalance_v1 | handoff_divergence_fade_h14_tp06_sl065 | 522 | 0.5781 | 0.2137 | 0.1165 | 0.1693 | -2.192 | -897.0668 | 0.2969 | -0.2013 |
| STAGE28A_REJECT | calendar_time_risk_proxy_v1 | calendar_drop_friday_h9_tp06_sl065 | 1288 | 0.6261 | 0.2057 | 0.1175 | 0.1591 | -1.4 | -1876.5694 | 0.17 | -0.2124 |
| STAGE28A_REJECT | calendar_time_risk_proxy_v1 | calendar_drop_monday_h9_tp06_sl065 | 1288 | 0.5842 | 0.192 | 0.1091 | 0.1556 | -1.4 | -1941.5911 | 0.1607 | -0.2337 |

## Interpretation

- Stage28A is a discovery factory branch, not a modification of active forward trackers.
- It tests multiple independent pattern families in one batch using DB-first candles.
- Hotfix: registry execution is family-interleaved with a per-family cap so timeout-limited runs still cover all families.
- Candidate-review results remain research-only and require dedicated validation plus separate forward-shadow tracking.
- Negative families should be archived in the registry history to avoid repeated random mutation.

## Operational reminder

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.run_active_shadow_suite
python3 -m app.stage28a_discovery_factory_batch_runner
```

## Output files

- `data/reports/stage28a_discovery_factory_batch_runner/stage28a_discovery_factory_batch_runner.json`
- `data/reports/stage28a_discovery_factory_batch_runner/stage28a_discovery_factory_batch_runner.md`
- `data/reports/stage28a_discovery_factory_batch_runner/stage28a_all_candidates.csv`
- `data/reports/stage28a_discovery_factory_batch_runner/stage28a_family_balanced_shortlist.csv`
- `data/reports/stage28a_discovery_factory_batch_runner/stage28a_exact_trades.csv`
- `data/reports/stage28a_discovery_factory_batch_runner/stage28a_family_coverage.csv`
- `data/reports/stage28a_discovery_factory_batch_runner/stage28a_db_schema_diagnostic.csv`
