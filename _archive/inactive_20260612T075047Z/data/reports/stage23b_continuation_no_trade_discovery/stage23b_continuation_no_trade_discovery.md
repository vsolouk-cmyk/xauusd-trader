# Stage23B Continuation / No-Trade-Regime Discovery

Generated UTC: 2026-06-11T15:18:48+00:00

## Decision

```text
STAGE23B_HAS_PROMOTION_REVIEW_CANDIDATE_RESEARCH_ONLY
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
- Candidate cap: 72
- Data load mode: csv_first

## Discovery families

1. `london_oneway_continuation` — mirror of rejected Stage23A one-way London fade.
2. `asia_london_breakout_continuation` — continuation after London closes outside Asia range.
3. `prev_day_extreme_breakout_continuation` — continuation after previous-day extreme hold.

## Counts

- Proxy candidates tested: 72
- Proxy candidates passing min events: 61
- Exact replayed: 4
- Promotion-review candidates: 4
- Watchlist-only candidates: 0

## Top exact M1 results

| decision | family | name | events | pf_x1 | pf_x4 | test20_pf_x1 | pf_2026_x1 | boot_pf_p05_x1 | median_x1 | total_x1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| STAGE23B_PROMOTION_CANDIDATE_REVIEW_ONLY | london_oneway_continuation | london_oneway_cont_mv0.9_eff0.72_pb0.1_conf0.15_h180_e13_tp0.6_sl0.65 | 56 | 6.6576 | 3.5097 | 26.1167 | inf | 3.6382 | 2.2141 | 154.1035 |
| STAGE23B_PROMOTION_CANDIDATE_REVIEW_ONLY | london_oneway_continuation | london_oneway_cont_mv0.9_eff0.72_pb0.3_conf0.15_h180_e13_tp0.6_sl0.65 | 56 | 6.6576 | 3.5097 | 26.1167 | inf | 3.6382 | 2.2141 | 154.1035 |
| STAGE23B_PROMOTION_CANDIDATE_REVIEW_ONLY | london_oneway_continuation | london_oneway_cont_mv0.9_eff0.6_pb0.1_conf0.15_h180_e13_tp0.6_sl0.65 | 100 | 5.579 | 2.8514 | 15.3407 | inf | 3.6632 | 2.0794 | 232.6156 |
| STAGE23B_PROMOTION_CANDIDATE_REVIEW_ONLY | london_oneway_continuation | london_oneway_cont_mv0.9_eff0.6_pb0.3_conf0.15_h180_e13_tp0.6_sl0.65 | 100 | 5.579 | 2.8514 | 15.3407 | inf | 3.6632 | 2.0794 | 232.6156 |

## Top M15 proxy results

| family | name | events | pf_x1 | pf_x4 | test20_pf_x1 | boot_pf_p05_x1 | median_x1 | proxy_rank_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| london_oneway_continuation | london_oneway_cont_mv0.9_eff0.72_pb0.1_conf0.15_h180_e13_tp0.6_sl0.65 | 56 | 1.784 | 1.0326 | 2.6614 | 0.9569 | 1.6763 | 8.5689 |
| london_oneway_continuation | london_oneway_cont_mv0.9_eff0.72_pb0.3_conf0.15_h180_e13_tp0.6_sl0.65 | 56 | 1.784 | 1.0326 | 2.6614 | 0.9569 | 1.6763 | 8.5689 |
| london_oneway_continuation | london_oneway_cont_mv0.9_eff0.6_pb0.1_conf0.15_h180_e13_tp0.6_sl0.65 | 100 | 1.5223 | 0.8324 | 2.3231 | 1.0523 | 1.4588 | 7.8774 |
| london_oneway_continuation | london_oneway_cont_mv0.9_eff0.6_pb0.3_conf0.15_h180_e13_tp0.6_sl0.65 | 100 | 1.5223 | 0.8324 | 2.3231 | 1.0523 | 1.4588 | 7.8774 |
| london_oneway_continuation | london_oneway_cont_mv0.9_eff0.72_pb0.1_conf0.15_h90_e13_tp0.6_sl0.65 | 56 | 1.6635 | 0.9279 | 2.3678 | 0.8375 | 1.4628 | 7.8102 |
| london_oneway_continuation | london_oneway_cont_mv0.9_eff0.72_pb0.3_conf0.15_h90_e13_tp0.6_sl0.65 | 56 | 1.6635 | 0.9279 | 2.3678 | 0.8375 | 1.4628 | 7.8102 |
| london_oneway_continuation | london_oneway_cont_mv0.9_eff0.72_pb0.1_conf0.0_h90_e13_tp0.6_sl0.65 | 108 | 1.2941 | 0.7356 | 2.6793 | 0.7372 | 1.1134 | 7.4153 |
| london_oneway_continuation | london_oneway_cont_mv0.9_eff0.6_pb0.1_conf0.15_h90_e13_tp0.6_sl0.65 | 100 | 1.4128 | 0.7503 | 2.1429 | 1.0201 | 1.4069 | 7.3639 |
| london_oneway_continuation | london_oneway_cont_mv0.9_eff0.6_pb0.3_conf0.15_h90_e13_tp0.6_sl0.65 | 100 | 1.4128 | 0.7503 | 2.1429 | 1.0201 | 1.4069 | 7.3639 |
| london_oneway_continuation | london_oneway_cont_mv0.9_eff0.72_pb0.1_conf0.15_h90_e13_tp0.4_sl0.5 | 56 | 1.553 | 0.6827 | 2.2315 | 0.9062 | 1.041 | 7.2764 |
| london_oneway_continuation | london_oneway_cont_mv0.9_eff0.72_pb0.1_conf0.15_h180_e13_tp0.4_sl0.5 | 56 | 1.553 | 0.6827 | 2.2315 | 0.9062 | 1.041 | 7.2764 |
| london_oneway_continuation | london_oneway_cont_mv0.9_eff0.72_pb0.3_conf0.15_h90_e13_tp0.4_sl0.5 | 56 | 1.553 | 0.6827 | 2.2315 | 0.9062 | 1.041 | 7.2764 |
| london_oneway_continuation | london_oneway_cont_mv0.9_eff0.72_pb0.3_conf0.15_h180_e13_tp0.4_sl0.5 | 56 | 1.553 | 0.6827 | 2.2315 | 0.9062 | 1.041 | 7.2764 |
| london_oneway_continuation | london_oneway_cont_mv0.9_eff0.6_pb0.1_conf0.0_h90_e13_tp0.6_sl0.65 | 198 | 1.1877 | 0.6696 | 1.8765 | 0.9646 | 1.0527 | 6.8861 |
| london_oneway_continuation | london_oneway_cont_mv0.9_eff0.6_pb0.1_conf0.0_h180_e13_tp0.6_sl0.65 | 198 | 1.2502 | 0.7675 | 1.696 | 0.9007 | 1.2989 | 6.8646 |
| london_oneway_continuation | london_oneway_cont_mv0.9_eff0.72_pb0.3_conf0.0_h90_e13_tp0.6_sl0.65 | 166 | 1.1654 | 0.6996 | 1.4428 | 0.8981 | 1.0279 | 6.3713 |
| london_oneway_continuation | london_oneway_cont_mv0.9_eff0.72_pb0.1_conf0.0_h180_e13_tp0.6_sl0.65 | 108 | 1.2115 | 0.7287 | 1.8434 | 0.6996 | 1.3043 | 6.3697 |
| london_oneway_continuation | london_oneway_cont_mv0.9_eff0.6_pb0.1_conf0.0_h90_e13_tp0.4_sl0.5 | 198 | 1.0793 | 0.5098 | 1.819 | 0.8367 | 0.756 | 6.3241 |
| london_oneway_continuation | london_oneway_cont_mv0.9_eff0.72_pb0.1_conf0.0_h90_e13_tp0.4_sl0.5 | 108 | 1.1664 | 0.5341 | 2.0684 | 0.6835 | 0.8733 | 6.2938 |
| london_oneway_continuation | london_oneway_cont_mv0.9_eff0.6_pb0.1_conf0.0_h180_e13_tp0.4_sl0.5 | 198 | 1.0153 | 0.4953 | 1.5441 | 0.7679 | 0.7529 | 5.8379 |

## Operational reminder

Stage23B is discovery only. Continue operational forward-shadow collection separately:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage18a_unified_shadow_ops_cycle
cat data/reports/stage18a_unified_shadow_ops_cycle/stage18a_unified_shadow_ops_cycle.md
```

## Output files

- `data/reports/stage23b_continuation_no_trade_discovery/stage23b_continuation_no_trade_discovery.json`
- `data/reports/stage23b_continuation_no_trade_discovery/stage23b_continuation_no_trade_discovery.md`
- `data/reports/stage23b_continuation_no_trade_discovery/stage23b_proxy_candidates.csv`
- `data/reports/stage23b_continuation_no_trade_discovery/stage23b_exact_candidates.csv`
- `data/reports/stage23b_continuation_no_trade_discovery/stage23b_exact_trades.csv`
