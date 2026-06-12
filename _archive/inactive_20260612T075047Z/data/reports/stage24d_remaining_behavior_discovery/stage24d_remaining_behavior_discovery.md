# Stage24D Remaining Behavior Discovery

Generated UTC: 2026-06-11T16:27:16.448817+00:00

## Decision

```text
STAGE24D_NO_PROMOTION_KEEP_DISCOVERY_OPEN
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

1. `two_day_compression_breakout_continuation` — two compressed prior days followed by envelope breakout continuation.
2. `day_open_reclaim_reversal` — intraday extension away from daily open followed by reclaim/reversal.
3. `asia_midpoint_rejection_reversal` — sweep of compact Asia range followed by midpoint rejection.

## Counts

- proxy_candidates_tested: 84
- proxy_candidates_passing_min_events: 24
- exact_replayed: 4
- promotion_review_candidates: 0
- watchlist_only_candidates: 0
- proxy_timed_out: True
- exact_timed_out: False

## Top exact M1 results

| decision | family | name | events | pf_x1 | pf_x4 | pf_x6 | test20_pf_x1 | pf_2026_x1 | boot_pf_p05_x1 | median_x1 | total_x1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| STAGE24D_REJECT | day_open_reclaim_reversal | day_open_reclaim_rev_ext0.45_rec0.0_h180_e16_tp0.6_sl0.65 | 765 | 0.7781 | 0.5126 | 0.3773 | 0.7375 | 0.8528 | 0.6823 | -2.0727 | -505.6407 |
| STAGE24D_REJECT | day_open_reclaim_reversal | day_open_reclaim_rev_ext0.45_rec0.05_h180_e16_tp0.6_sl0.65 | 746 | 0.7789 | 0.5134 | 0.3781 | 0.7338 | 0.8275 | 0.6601 | -2.0787 | -491.6318 |
| STAGE24D_REJECT | day_open_reclaim_reversal | day_open_reclaim_rev_ext0.45_rec0.0_h90_e16_tp0.6_sl0.65 | 765 | 0.7581 | 0.4922 | 0.3575 | 0.6916 | 0.7813 | 0.6719 | -2.0638 | -542.5487 |
| STAGE24D_REJECT | day_open_reclaim_reversal | day_open_reclaim_rev_ext0.45_rec0.05_h90_e16_tp0.6_sl0.65 | 746 | 0.7579 | 0.4923 | 0.3577 | 0.6867 | 0.7554 | 0.6538 | -2.0787 | -529.8909 |

## Top M15 proxy results

| family | name | events | pf_x1 | pf_x4 | pf_x6 | test20_pf_x1 | boot_pf_p05_x1 | median_x1 | rank_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| day_open_reclaim_reversal | day_open_reclaim_rev_ext0.45_rec0.0_h180_e16_tp0.6_sl0.65 | 765 | 0.8475 | 0.5584 | 0.4111 | 0.8979 | 0.7424 | 1.5625 | 16.1472 |
| day_open_reclaim_reversal | day_open_reclaim_rev_ext0.45_rec0.05_h180_e16_tp0.6_sl0.65 | 746 | 0.8483 | 0.5594 | 0.4123 | 0.9073 | 0.7342 | 1.5395 | 16.1408 |
| day_open_reclaim_reversal | day_open_reclaim_rev_ext0.45_rec0.0_h90_e16_tp0.6_sl0.65 | 765 | 0.8192 | 0.5302 | 0.3844 | 0.8429 | 0.7364 | 1.258 | 15.9665 |
| day_open_reclaim_reversal | day_open_reclaim_rev_ext0.45_rec0.05_h90_e16_tp0.6_sl0.65 | 746 | 0.819 | 0.5304 | 0.3848 | 0.851 | 0.7103 | 1.2418 | 15.9351 |
| day_open_reclaim_reversal | day_open_reclaim_rev_ext0.7_rec0.0_h180_e16_tp0.6_sl0.65 | 614 | 0.8039 | 0.5329 | 0.395 | 0.8518 | 0.6891 | -1.7469 | 15.2992 |
| day_open_reclaim_reversal | day_open_reclaim_rev_ext0.7_rec0.05_h180_e16_tp0.6_sl0.65 | 596 | 0.8048 | 0.5339 | 0.3961 | 0.8614 | 0.6849 | -2.0742 | 15.2376 |
| day_open_reclaim_reversal | day_open_reclaim_rev_ext0.7_rec0.0_h180_e15_tp0.6_sl0.65 | 577 | 0.7911 | 0.5288 | 0.3963 | 1.0146 | 0.6792 | -2.4785 | 15.2346 |
| day_open_reclaim_reversal | day_open_reclaim_rev_ext0.7_rec0.05_h180_e15_tp0.6_sl0.65 | 561 | 0.7865 | 0.5274 | 0.3964 | 1.0058 | 0.6881 | -2.4791 | 15.2331 |
| day_open_reclaim_reversal | day_open_reclaim_rev_ext0.7_rec0.0_h90_e16_tp0.6_sl0.65 | 614 | 0.7724 | 0.5017 | 0.3654 | 0.791 | 0.6639 | -1.405 | 15.2108 |
| day_open_reclaim_reversal | day_open_reclaim_rev_ext0.7_rec0.05_h90_e16_tp0.6_sl0.65 | 596 | 0.7721 | 0.5016 | 0.3655 | 0.7988 | 0.674 | -1.505 | 15.2091 |
| day_open_reclaim_reversal | day_open_reclaim_rev_ext0.45_rec0.0_h90_e14_tp0.6_sl0.65 | 687 | 0.7228 | 0.4626 | 0.3351 | 0.7269 | 0.5981 | -1.41 | 14.9672 |
| day_open_reclaim_reversal | day_open_reclaim_rev_ext0.7_rec0.0_h90_e15_tp0.6_sl0.65 | 577 | 0.7407 | 0.4869 | 0.3597 | 0.8904 | 0.6194 | -2.4791 | 14.9524 |
| day_open_reclaim_reversal | day_open_reclaim_rev_ext0.7_rec0.05_h90_e15_tp0.6_sl0.65 | 561 | 0.7352 | 0.4847 | 0.3591 | 0.8807 | 0.6288 | -2.5544 | 14.9337 |
| day_open_reclaim_reversal | day_open_reclaim_rev_ext0.45_rec0.05_h90_e14_tp0.6_sl0.65 | 671 | 0.7092 | 0.4532 | 0.3279 | 0.7198 | 0.6113 | -1.59 | 14.9148 |
| day_open_reclaim_reversal | day_open_reclaim_rev_ext0.45_rec0.05_h180_e15_tp0.6_sl0.65 | 717 | 0.742 | 0.4916 | 0.3643 | 0.7819 | 0.6385 | -2.4785 | 14.9102 |
| day_open_reclaim_reversal | day_open_reclaim_rev_ext0.45_rec0.0_h180_e15_tp0.6_sl0.65 | 734 | 0.745 | 0.4924 | 0.3641 | 0.7895 | 0.6205 | -2.4645 | 14.8994 |
| day_open_reclaim_reversal | day_open_reclaim_rev_ext0.7_rec0.0_h90_e14_tp0.6_sl0.65 | 515 | 0.6927 | 0.4504 | 0.3312 | 0.7513 | 0.5972 | -2.24 | 14.7675 |
| day_open_reclaim_reversal | day_open_reclaim_rev_ext0.7_rec0.0_h180_e14_tp0.6_sl0.65 | 515 | 0.7081 | 0.4776 | 0.3594 | 0.7883 | 0.601 | -2.756 | 14.7542 |
| day_open_reclaim_reversal | day_open_reclaim_rev_ext0.45_rec0.0_h90_e15_tp0.6_sl0.65 | 734 | 0.7075 | 0.4605 | 0.3362 | 0.7097 | 0.6005 | -2.4645 | 14.7289 |
| day_open_reclaim_reversal | day_open_reclaim_rev_ext0.45_rec0.0_h180_e14_tp0.6_sl0.65 | 687 | 0.7167 | 0.4762 | 0.3531 | 0.7135 | 0.5982 | -2.6744 | 14.7209 |

## Interpretation

- Promotion-review here is still research-only.
- A candidate cannot enter Stage18A from this module without separate validation and forward-shadow tracking.
- If no promotion appears, close Stage24D and continue with a new behavior cluster rather than widening this grid indefinitely.

## Operational reminder

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage18a_unified_shadow_ops_cycle
cat data/reports/stage18a_unified_shadow_ops_cycle/stage18a_unified_shadow_ops_cycle.md

python3 -m app.stage23d_forward_shadow_candidate
cat data/reports/stage23d_forward_shadow_candidate/stage23d_forward_shadow_candidate.md
```

## Output files

- `data/reports/stage24d_remaining_behavior_discovery/stage24d_remaining_behavior_discovery.json`
- `data/reports/stage24d_remaining_behavior_discovery/stage24d_remaining_behavior_discovery.md`
- `data/reports/stage24d_remaining_behavior_discovery/stage24d_proxy_candidates.csv`
- `data/reports/stage24d_remaining_behavior_discovery/stage24d_exact_candidates.csv`
- `data/reports/stage24d_remaining_behavior_discovery/stage24d_exact_trades.csv`
