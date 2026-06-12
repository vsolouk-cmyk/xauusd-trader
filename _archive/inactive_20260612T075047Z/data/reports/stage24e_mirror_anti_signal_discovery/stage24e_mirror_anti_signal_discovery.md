# Stage24E Mirror / Anti-Signal Discovery

Generated UTC: 2026-06-11T16:35:07.284165+00:00

## Decision

```text
STAGE24E_NO_PROMOTION_KEEP_DISCOVERY_OPEN
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

1. `day_open_extension_continuation` — mirror of rejected day-open reclaim/reversal: extension away from daily open continues.
2. `prev_day_expansion_continuation` — mirror of exhaustion reversal: yesterday's expansion direction continues after current-day extension.
3. `london_range_breakout_hold_continuation` — mirror of London stop-run/reclaim: NY break holds outside London range and continues.

## Counts

- proxy_candidates_tested: 84
- proxy_candidates_passing_min_events: 48
- exact_replayed: 4
- promotion_review_candidates: 0
- watchlist_only_candidates: 0
- proxy_timed_out: True
- exact_timed_out: False

## Top exact M1 results

| decision | family | name | events | pf_x1 | pf_x4 | pf_x6 | test20_pf_x1 | pf_2026_x1 | boot_pf_p05_x1 | median_x1 | total_x1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| STAGE24E_REJECT | day_open_extension_continuation | day_open_ext_cont_ext0.7_cf0.0_h180_e16_tp0.8_sl0.8 | 1053 | 0.9557 | 0.6972 | 0.5601 | 1.0107 | 1.1437 | 0.8224 | 0.01 | -160.7232 |
| STAGE24E_REJECT | day_open_extension_continuation | day_open_ext_cont_ext0.45_cf0.0_h180_e16_tp0.8_sl0.8 | 1057 | 0.9509 | 0.6935 | 0.557 | 1.0147 | 1.1437 | 0.8362 | -0.32 | -178.9748 |
| STAGE24E_REJECT | day_open_extension_continuation | day_open_ext_cont_ext0.45_cf0.05_h180_e16_tp0.8_sl0.8 | 1038 | 0.9444 | 0.6888 | 0.5534 | 1.0186 | 1.1221 | 0.817 | -0.63 | -199.95 |
| STAGE24E_REJECT | day_open_extension_continuation | day_open_ext_cont_ext0.45_cf0.1_h180_e16_tp0.8_sl0.8 | 1019 | 0.929 | 0.6753 | 0.5409 | 0.9887 | 1.0651 | 0.8318 | -0.73 | -250.0696 |

## Top M15 proxy results

| family | name | events | pf_x1 | pf_x4 | pf_x6 | test20_pf_x1 | boot_pf_p05_x1 | median_x1 | rank_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| day_open_extension_continuation | day_open_ext_cont_ext0.45_cf0.0_h180_e16_tp0.8_sl0.8 | 1057 | 1.0271 | 0.7494 | 0.6021 | 1.1031 | 0.9066 | 2.2216 | 17.1211 |
| day_open_extension_continuation | day_open_ext_cont_ext0.7_cf0.0_h180_e16_tp0.8_sl0.8 | 1053 | 1.0324 | 0.7536 | 0.6055 | 1.099 | 0.8868 | 2.2454 | 17.1093 |
| day_open_extension_continuation | day_open_ext_cont_ext0.45_cf0.05_h180_e16_tp0.8_sl0.8 | 1038 | 1.0207 | 0.745 | 0.5986 | 1.1091 | 0.906 | 2.2106 | 17.1089 |
| day_open_extension_continuation | day_open_ext_cont_ext0.45_cf0.1_h180_e16_tp0.8_sl0.8 | 1019 | 1.0073 | 0.7328 | 0.5872 | 1.0822 | 0.8898 | 2.2216 | 17.0383 |
| day_open_extension_continuation | day_open_ext_cont_ext0.45_cf0.0_h180_e16_tp0.6_sl0.65 | 1057 | 0.9185 | 0.6136 | 0.4581 | 1.0247 | 0.8227 | 1.6994 | 16.5269 |
| day_open_extension_continuation | day_open_ext_cont_ext0.45_cf0.05_h180_e16_tp0.6_sl0.65 | 1038 | 0.918 | 0.6138 | 0.4587 | 1.0473 | 0.8049 | 1.6582 | 16.5111 |
| day_open_extension_continuation | day_open_ext_cont_ext0.7_cf0.0_h180_e16_tp0.6_sl0.65 | 1053 | 0.9218 | 0.6162 | 0.4602 | 1.0211 | 0.793 | 1.7721 | 16.5077 |
| day_open_extension_continuation | day_open_ext_cont_ext0.45_cf0.1_h180_e16_tp0.6_sl0.65 | 1019 | 0.9062 | 0.6023 | 0.4473 | 1.0116 | 0.8026 | 1.7721 | 16.4757 |
| day_open_extension_continuation | day_open_ext_cont_ext0.7_cf0.0_h90_e16_tp0.8_sl0.8 | 1053 | 0.9682 | 0.6926 | 0.5488 | 0.9785 | 0.835 | 0.58 | 16.4629 |
| day_open_extension_continuation | day_open_ext_cont_ext0.45_cf0.05_h90_e16_tp0.8_sl0.8 | 1038 | 0.9601 | 0.687 | 0.5445 | 0.9942 | 0.8687 | 0.3 | 16.4445 |
| day_open_extension_continuation | day_open_ext_cont_ext0.45_cf0.0_h90_e16_tp0.8_sl0.8 | 1057 | 0.963 | 0.6887 | 0.5456 | 0.9828 | 0.8556 | 0.38 | 16.4412 |
| day_open_extension_continuation | day_open_ext_cont_ext0.45_cf0.1_h90_e16_tp0.8_sl0.8 | 1019 | 0.9514 | 0.6782 | 0.5358 | 0.9756 | 0.8289 | 0.35 | 16.3671 |
| day_open_extension_continuation | day_open_ext_cont_ext0.45_cf0.05_h90_e16_tp0.6_sl0.65 | 1038 | 0.8723 | 0.5738 | 0.4227 | 0.9562 | 0.781 | 1.4898 | 16.273 |
| day_open_extension_continuation | day_open_ext_cont_ext0.45_cf0.1_h90_e16_tp0.6_sl0.65 | 1019 | 0.8697 | 0.5692 | 0.4171 | 0.9422 | 0.7706 | 1.5625 | 16.2543 |
| day_open_extension_continuation | day_open_ext_cont_ext0.45_cf0.0_h90_e16_tp0.6_sl0.65 | 1057 | 0.8737 | 0.5743 | 0.4228 | 0.9359 | 0.7669 | 1.5164 | 16.2481 |
| day_open_extension_continuation | day_open_ext_cont_ext0.7_cf0.0_h90_e16_tp0.6_sl0.65 | 1053 | 0.8769 | 0.5767 | 0.4247 | 0.9322 | 0.7547 | 1.5622 | 16.2458 |
| day_open_extension_continuation | day_open_ext_cont_ext0.45_cf0.1_h180_e15_tp0.8_sl0.8 | 1022 | 0.8725 | 0.6404 | 0.5177 | 0.9938 | 0.7446 | -3.0331 | 15.4542 |
| day_open_extension_continuation | day_open_ext_cont_ext0.45_cf0.1_h90_e14_tp0.8_sl0.8 | 1013 | 0.7915 | 0.5391 | 0.4128 | 0.7679 | 0.6874 | -0.86 | 15.4132 |
| day_open_extension_continuation | day_open_ext_cont_ext0.7_cf0.0_h180_e15_tp0.8_sl0.8 | 1051 | 0.8571 | 0.6287 | 0.5078 | 0.9533 | 0.7658 | -3.0713 | 15.4116 |
| day_open_extension_continuation | day_open_ext_cont_ext0.7_cf0.0_h90_e14_tp0.8_sl0.8 | 1042 | 0.7898 | 0.5368 | 0.4099 | 0.7317 | 0.6897 | -0.82 | 15.3936 |

## Interpretation

- Promotion-review here is still research-only.
- A candidate cannot enter Stage18A from this module without separate validation and forward-shadow tracking.
- If no promotion appears, close Stage24E and move to a non-entry discovery track such as regime/no-trade filters rather than widening mirror grids indefinitely.

## Operational reminder

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage18a_unified_shadow_ops_cycle
cat data/reports/stage18a_unified_shadow_ops_cycle/stage18a_unified_shadow_ops_cycle.md

python3 -m app.stage23d_forward_shadow_candidate
cat data/reports/stage23d_forward_shadow_candidate/stage23d_forward_shadow_candidate.md
```

## Output files

- `data/reports/stage24e_mirror_anti_signal_discovery/stage24e_mirror_anti_signal_discovery.json`
- `data/reports/stage24e_mirror_anti_signal_discovery/stage24e_mirror_anti_signal_discovery.md`
- `data/reports/stage24e_mirror_anti_signal_discovery/stage24e_proxy_candidates.csv`
- `data/reports/stage24e_mirror_anti_signal_discovery/stage24e_exact_candidates.csv`
- `data/reports/stage24e_mirror_anti_signal_discovery/stage24e_exact_trades.csv`
