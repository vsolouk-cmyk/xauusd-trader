# Stage24A Remaining Behavior Discovery

Generated UTC: 2026-06-11T15:59:42+00:00

## Decision

```text
STAGE24A_NO_PROMOTION_KEEP_DISCOVERY_OPEN
```

## Scope guardrails

- Research/shadow only.
- Stage18A v2 remains the active operational forward-shadow runner.
- No EA change, no automatic trading, no paper/live/order authorization.
- Stage18A v2 and Stage23D are not modified. Stage19B/20A/21B/22A watchlist-only families are not touched or added to Stage18A.

## Data

- M1 rows: 1452834 | span: 2022-05-02 01:01:00 → 2026-06-11 17:15:00
- H1 rows: 24275 | span: 2022-05-02 01:00:00 → 2026-06-11 17:00:00
- M15 proxy rows: 97011 | span: 2022-05-02 01:00:00 → 2026-06-11 17:15:00
- Roundtrip cost x1: 0.35
- Exact replay cap: 12 total / 4 per family
- Runtime cap seconds: 180
- Candidate cap: 84
- Data load mode: csv_first

## Discovery families

1. `asia_compression_failed_breakout_fade` — quiet Asia range followed by failed expansion/reclaim.
2. `london_compression_expansion_continuation` — London compression followed by NY expansion continuation.
3. `london_extreme_stoprun_reclaim` — NY stop-run/reclaim around London extremes.

## Counts

- Proxy candidates tested: 84
- Proxy candidates passing min events: 25
- Exact replayed: 4
- Promotion-review candidates: 0
- Watchlist-only candidates: 0

## Top exact M1 results

| decision | family | name | events | pf_x1 | pf_x4 | test20_pf_x1 | pf_2026_x1 | boot_pf_p05_x1 | median_x1 | total_x1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| STAGE24A_REJECT | london_extreme_stoprun_reclaim | london_extreme_stoprun_reclaim_rng0.7_sw0.1_rec0.0_h90_e16_tp0.6_sl0.65 | 314 | 1.323 | 0.8522 | 1.2288 | 1.1344 | 1.05 | 2.0056 | 213.6956 |
| STAGE24A_REJECT | london_extreme_stoprun_reclaim | london_extreme_stoprun_reclaim_rng0.7_sw0.25_rec0.0_h90_e16_tp0.6_sl0.65 | 264 | 1.3045 | 0.8339 | 1.0162 | 0.9356 | 0.9304 | 1.9855 | 168.8094 |
| STAGE24A_REJECT | london_extreme_stoprun_reclaim | london_extreme_stoprun_reclaim_rng0.7_sw0.1_rec0.1_h90_e16_tp0.6_sl0.65 | 287 | 1.3255 | 0.8231 | 1.1209 | 0.9002 | 1.0587 | 2.0817 | 182.8982 |
| STAGE24A_REJECT | london_extreme_stoprun_reclaim | london_extreme_stoprun_reclaim_rng0.7_sw0.25_rec0.0_h180_e15_tp0.6_sl0.65 | 202 | 0.8616 | 0.531 | 0.7865 | 1.0139 | 0.6357 | 1.3583 | -69.596 |

## Top M15 proxy results

| family | name | events | pf_x1 | pf_x4 | test20_pf_x1 | boot_pf_p05_x1 | median_x1 | proxy_rank_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| london_extreme_stoprun_reclaim | london_extreme_stoprun_reclaim_rng0.7_sw0.1_rec0.0_h90_e16_tp0.6_sl0.65 | 314 | 0.7864 | 0.5057 | 0.8914 | 0.5254 | 0.535 | 6.7681 |
| london_extreme_stoprun_reclaim | london_extreme_stoprun_reclaim_rng0.7_sw0.1_rec0.1_h90_e16_tp0.6_sl0.65 | 287 | 0.7401 | 0.4575 | 0.8642 | 0.5856 | 0.49 | 6.5427 |
| london_extreme_stoprun_reclaim | london_extreme_stoprun_reclaim_rng0.7_sw0.1_rec0.0_h180_e16_tp0.6_sl0.65 | 314 | 0.7858 | 0.5118 | 0.9166 | 0.5137 | -1.8037 | 5.6281 |
| london_extreme_stoprun_reclaim | london_extreme_stoprun_reclaim_rng0.7_sw0.1_rec0.1_h180_e16_tp0.6_sl0.65 | 287 | 0.7406 | 0.4656 | 0.8959 | 0.5651 | -1.9527 | 5.3537 |
| london_extreme_stoprun_reclaim | london_extreme_stoprun_reclaim_rng0.7_sw0.25_rec0.0_h90_e16_tp0.6_sl0.65 | 264 | 0.6925 | 0.4381 | 0.6433 | 0.5299 | -1.8037 | 4.855 |
| london_extreme_stoprun_reclaim | london_extreme_stoprun_reclaim_rng0.7_sw0.25_rec0.0_h180_e16_tp0.6_sl0.65 | 264 | 0.6759 | 0.4312 | 0.6357 | 0.514 | -2.206 | 4.6671 |
| london_extreme_stoprun_reclaim | london_extreme_stoprun_reclaim_rng0.7_sw0.25_rec0.0_h180_e15_tp0.6_sl0.65 | 202 | 0.5692 | 0.3456 | 0.4832 | 0.4504 | -2.2909 | 3.839 |
| london_extreme_stoprun_reclaim | london_extreme_stoprun_reclaim_rng0.7_sw0.25_rec0.0_h90_e15_tp0.6_sl0.65 | 202 | 0.5672 | 0.3447 | 0.4832 | 0.4461 | -2.2807 | 3.8256 |
| london_extreme_stoprun_reclaim | london_extreme_stoprun_reclaim_rng0.7_sw0.1_rec0.0_h90_e15_tp0.6_sl0.65 | 291 | 0.5476 | 0.3365 | 0.4713 | 0.4298 | -2.4857 | 3.8105 |
| london_extreme_stoprun_reclaim | london_extreme_stoprun_reclaim_rng0.7_sw0.1_rec0.0_h180_e15_tp0.6_sl0.65 | 291 | 0.5475 | 0.3364 | 0.4713 | 0.4299 | -2.553 | 3.8101 |
| london_extreme_stoprun_reclaim | london_extreme_stoprun_reclaim_rng0.7_sw0.1_rec0.0_h180_e15_tp0.4_sl0.5 | 291 | 0.5505 | 0.2632 | 0.4723 | 0.449 | -1.6968 | 3.7971 |
| london_extreme_stoprun_reclaim | london_extreme_stoprun_reclaim_rng0.7_sw0.1_rec0.0_h90_e15_tp0.4_sl0.5 | 291 | 0.5505 | 0.2632 | 0.4723 | 0.449 | -1.6968 | 3.7971 |
| london_extreme_stoprun_reclaim | london_extreme_stoprun_reclaim_rng0.7_sw0.1_rec0.1_h180_e15_tp0.6_sl0.65 | 249 | 0.5275 | 0.3309 | 0.464 | 0.4458 | -2.6408 | 3.7259 |
| london_extreme_stoprun_reclaim | london_extreme_stoprun_reclaim_rng0.7_sw0.1_rec0.1_h90_e15_tp0.6_sl0.65 | 249 | 0.5275 | 0.331 | 0.464 | 0.4437 | -2.6366 | 3.723 |
| london_extreme_stoprun_reclaim | london_extreme_stoprun_reclaim_rng0.7_sw0.1_rec0.1_h180_e16_tp0.4_sl0.5 | 287 | 0.5333 | 0.2586 | 0.6293 | 0.3851 | -2.0004 | 3.6911 |
| london_extreme_stoprun_reclaim | london_extreme_stoprun_reclaim_rng0.7_sw0.1_rec0.1_h90_e16_tp0.4_sl0.5 | 287 | 0.5333 | 0.2586 | 0.6293 | 0.3851 | -2.0004 | 3.6911 |
| london_extreme_stoprun_reclaim | london_extreme_stoprun_reclaim_rng0.7_sw0.1_rec0.0_h180_e16_tp0.4_sl0.5 | 314 | 0.4988 | 0.2504 | 0.5389 | 0.3854 | -2.0152 | 3.5008 |
| london_extreme_stoprun_reclaim | london_extreme_stoprun_reclaim_rng0.7_sw0.1_rec0.0_h90_e16_tp0.4_sl0.5 | 314 | 0.4988 | 0.2504 | 0.5389 | 0.3854 | -2.0152 | 3.5008 |
| london_extreme_stoprun_reclaim | london_extreme_stoprun_reclaim_rng0.7_sw0.1_rec0.1_h180_e15_tp0.4_sl0.5 | 249 | 0.4893 | 0.2422 | 0.4596 | 0.401 | -1.9104 | 3.3681 |
| london_extreme_stoprun_reclaim | london_extreme_stoprun_reclaim_rng0.7_sw0.1_rec0.1_h90_e15_tp0.4_sl0.5 | 249 | 0.4893 | 0.2422 | 0.4596 | 0.401 | -1.9104 | 3.3681 |

## Operational reminder

Stage24A is discovery only. Continue Stage18A v2 and Stage23D forward-shadow collection separately:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage18a_unified_shadow_ops_cycle
cat data/reports/stage18a_unified_shadow_ops_cycle/stage18a_unified_shadow_ops_cycle.md

python3 -m app.stage23d_forward_shadow_candidate
cat data/reports/stage23d_forward_shadow_candidate/stage23d_forward_shadow_candidate.md
```

## Output files

- `data/reports/stage24a_remaining_behavior_discovery/stage24a_remaining_behavior_discovery.json`
- `data/reports/stage24a_remaining_behavior_discovery/stage24a_remaining_behavior_discovery.md`
- `data/reports/stage24a_remaining_behavior_discovery/stage24a_proxy_candidates.csv`
- `data/reports/stage24a_remaining_behavior_discovery/stage24a_exact_candidates.csv`
- `data/reports/stage24a_remaining_behavior_discovery/stage24a_exact_trades.csv`
