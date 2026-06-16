# Stage23A Lite Proxy-Then-Exact Discovery

Generated UTC: 2026-06-11T15:10:18+00:00

## Decision

```text
STAGE23_NO_PROMOTION_KEEP_DISCOVERY_OPEN
```

## Scope guardrails

- Research/shadow only.
- Stage18A v2 remains the active operational forward-shadow runner.
- No EA change, no automatic trading, no paper/live/order authorization.
- Stage19B/20A/21B/22A watchlist-only families are not touched or added to Stage18A.

## Data

- M1 rows: 1452834 | span: 2022-05-02 01:01:00 → 2026-06-11 17:15:00
- H1 rows: 24275 | span: 2022-05-02 01:00:00 → 2026-06-11 17:00:00
- M15 proxy rows: 97011 | span: 2022-05-02 01:00:00 → 2026-06-11 17:15:00
- Roundtrip cost x1: 0.35
- Exact replay cap: 12 total / 4 per family
- Runtime cap seconds: 180
- Candidate cap: 60
- Data load mode: csv_first

## Discovery families

1. `london_oneway_fade` — intraday mean-reversion after a one-way London move.
2. `asia_london_double_expansion_reversal` — NY reversal after Asia/London double expansion.
3. `prev_day_range_extreme_fade` — range-day / previous-day extreme fade logic.

## Counts

- Proxy candidates tested: 60
- Proxy candidates passing min events: 60
- Exact replayed: 4
- Promotion-review candidates: 0
- Watchlist-only candidates: 0

## Top exact M1 results

| decision | family | name | events | pf_x1 | pf_x4 | test20_pf_x1 | pf_2026_x1 | boot_pf_p05_x1 | median_x1 | total_x1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| STAGE23_REJECT | london_oneway_fade | london_oneway_fade_mv1.2_eff0.6_cont0.0_h90_e15_tp0.6_sl0.65 | 160 | 0.5002 | 0.3117 | 0.4384 | 0.5896 | 0.341 | -2.6888 | -257.7142 |
| STAGE23_REJECT | london_oneway_fade | london_oneway_fade_mv1.2_eff0.6_cont0.0_h180_e15_tp0.6_sl0.65 | 160 | 0.4603 | 0.291 | 0.3786 | 0.4525 | 0.3103 | -2.7861 | -302.9745 |
| STAGE23_REJECT | london_oneway_fade | london_oneway_fade_mv1.2_eff0.6_cont0.0_h90_e15_tp0.4_sl0.5 | 160 | 0.3385 | 0.1675 | 0.2487 | 0.2555 | 0.2351 | -2.1914 | -305.1434 |
| STAGE23_REJECT | london_oneway_fade | london_oneway_fade_mv1.2_eff0.6_cont0.0_h180_e15_tp0.4_sl0.5 | 160 | 0.3385 | 0.1675 | 0.2487 | 0.2555 | 0.2351 | -2.1914 | -305.1434 |

## Top M15 proxy results

| family | name | events | pf_x1 | pf_x4 | test20_pf_x1 | boot_pf_p05_x1 | median_x1 | proxy_rank_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| london_oneway_fade | london_oneway_fade_mv1.2_eff0.6_cont0.0_h90_e15_tp0.4_sl0.5 | 160 | 0.8162 | 0.4309 | 1.1743 | 0.575 | 0.6766 | 4.8126 |
| london_oneway_fade | london_oneway_fade_mv1.2_eff0.6_cont0.0_h90_e15_tp0.6_sl0.65 | 160 | 0.8349 | 0.5392 | 0.9618 | 0.6308 | -0.5574 | 4.8016 |
| london_oneway_fade | london_oneway_fade_mv1.2_eff0.6_cont0.0_h180_e15_tp0.4_sl0.5 | 160 | 0.7969 | 0.423 | 1.1743 | 0.5724 | 0.6766 | 4.7635 |
| london_oneway_fade | london_oneway_fade_mv1.2_eff0.6_cont0.0_h180_e15_tp0.6_sl0.65 | 160 | 0.8172 | 0.5297 | 0.9618 | 0.6105 | -1.851 | 4.7364 |
| london_oneway_fade | london_oneway_fade_mv0.9_eff0.6_cont0.0_h90_e15_tp0.6_sl0.65 | 170 | 0.8288 | 0.542 | 0.8856 | 0.537 | 1.1266 | 4.6222 |
| london_oneway_fade | london_oneway_fade_mv1.2_eff0.6_cont0.2_h90_e15_tp0.6_sl0.65 | 126 | 0.8343 | 0.5297 | 1.0543 | 0.5765 | 1.231 | 4.6166 |
| london_oneway_fade | london_oneway_fade_mv0.9_eff0.6_cont0.0_h180_e15_tp0.6_sl0.65 | 170 | 0.8233 | 0.5421 | 0.8856 | 0.5277 | 1.1266 | 4.602 |
| london_oneway_fade | london_oneway_fade_mv0.9_eff0.6_cont0.2_h90_e15_tp0.6_sl0.65 | 135 | 0.8339 | 0.5396 | 0.9796 | 0.537 | 1.492 | 4.5678 |
| london_oneway_fade | london_oneway_fade_mv0.9_eff0.6_cont0.2_h180_e15_tp0.6_sl0.65 | 135 | 0.8268 | 0.5398 | 0.9796 | 0.5477 | 1.492 | 4.5644 |
| london_oneway_fade | london_oneway_fade_mv1.2_eff0.6_cont0.2_h180_e15_tp0.6_sl0.65 | 126 | 0.8113 | 0.5176 | 1.0543 | 0.5757 | 1.231 | 4.5577 |
| london_oneway_fade | london_oneway_fade_mv0.9_eff0.6_cont0.0_h90_e15_tp0.4_sl0.5 | 170 | 0.7839 | 0.4199 | 0.9117 | 0.5276 | 0.8537 | 4.427 |
| london_oneway_fade | london_oneway_fade_mv0.9_eff0.6_cont0.0_h180_e15_tp0.4_sl0.5 | 170 | 0.7733 | 0.4177 | 0.9117 | 0.5131 | 0.8537 | 4.3891 |
| london_oneway_fade | london_oneway_fade_mv1.2_eff0.6_cont0.2_h90_e15_tp0.4_sl0.5 | 126 | 0.7379 | 0.377 | 1.0673 | 0.497 | 0.6766 | 4.2046 |
| london_oneway_fade | london_oneway_fade_mv1.2_eff0.6_cont0.2_h180_e15_tp0.4_sl0.5 | 126 | 0.7163 | 0.3685 | 1.0673 | 0.4893 | 0.6766 | 4.1452 |
| london_oneway_fade | london_oneway_fade_mv0.9_eff0.6_cont0.2_h90_e15_tp0.4_sl0.5 | 135 | 0.7162 | 0.3739 | 0.7678 | 0.4519 | 0.878 | 3.8697 |
| london_oneway_fade | london_oneway_fade_mv0.9_eff0.6_cont0.2_h180_e15_tp0.4_sl0.5 | 135 | 0.7049 | 0.3722 | 0.7678 | 0.4526 | 0.878 | 3.8462 |
| london_oneway_fade | london_oneway_fade_mv1.2_eff0.6_cont0.0_h90_e13_tp0.4_sl0.5 | 147 | 0.6076 | 0.2429 | 0.7142 | 0.3684 | 0.5691 | 3.4594 |
| london_oneway_fade | london_oneway_fade_mv0.9_eff0.72_cont0.0_h90_e15_tp0.6_sl0.65 | 99 | 0.6642 | 0.439 | 0.6204 | 0.4431 | -2.0107 | 3.4497 |
| london_oneway_fade | london_oneway_fade_mv0.9_eff0.72_cont0.2_h90_e15_tp0.6_sl0.65 | 75 | 0.6694 | 0.4383 | 0.7739 | 0.4271 | -1.9973 | 3.4468 |
| london_oneway_fade | london_oneway_fade_mv0.9_eff0.72_cont0.0_h90_e15_tp0.4_sl0.5 | 99 | 0.6616 | 0.366 | 0.7303 | 0.3866 | -1.6275 | 3.4249 |

## Operational reminder

Stage23A is discovery only. Continue operational forward-shadow collection separately:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage18a_unified_shadow_ops_cycle
cat data/reports/stage18a_unified_shadow_ops_cycle/stage18a_unified_shadow_ops_cycle.md
```

## Output files

- `data/reports/stage23a_lite_proxy_exact_discovery/stage23a_lite_proxy_exact_discovery.json`
- `data/reports/stage23a_lite_proxy_exact_discovery/stage23a_lite_proxy_exact_discovery.md`
- `data/reports/stage23a_lite_proxy_exact_discovery/stage23a_proxy_candidates.csv`
- `data/reports/stage23a_lite_proxy_exact_discovery/stage23a_exact_candidates.csv`
- `data/reports/stage23a_lite_proxy_exact_discovery/stage23a_exact_trades.csv`
