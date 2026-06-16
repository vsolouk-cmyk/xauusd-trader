# Stage 11D Recent Short Watchlist Report

Generated UTC: `2026-06-10T19:22:31+00:00`
Tool version: `v1`

> Hard rule: report/watchlist only. No EA change, no automatic trading, no paper/live authorization.

## Inputs
- db: `data/local/xauusd_local_store.sqlite`
- stage11b_summary: `data/reports/stage11b_alternative_short_thesis_lab/stage11b_short_candidate_summary.csv`
- stage11c_summary: `data/reports/stage11c_recent_short_regime_diagnostic/stage11c_recent_candidate_summary.csv`
- latest_closed_h1: `2026-06-09T11:00:00+00:00`
- watchlist_candidates_loaded: `12`
- recent_hours: `72`

## Decision
- decision: `recent_short_watchlist_seen_report_only`
- latest_active_count: `0`
- recent_signal_candidate_count: `12`

## Watchlist status
| Rank | Status | Verdict | Active now | Recent count | Last signal UTC | Age h | Recent24m total | Recent24m PF | All PF | All median | All DD | Variant |
|---:|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---|
| 1 | RECENT_WATCHLIST_SIGNAL_ONLY | RECENT_REGIME_WATCHLIST_ONLY | 0 | 6 | 2026-06-09T05:00:00+00:00 | 6.0 | 1310.52 | 1.226192 | 1.09333 | -3.76 | -2063.24 | short_rally_rejection_h4sma20_slope3_look12_comp6_1.8_rej6_imp1.2_h6_cool1_all |
| 2 | RECENT_WATCHLIST_SIGNAL_ONLY | RECENT_REGIME_WATCHLIST_ONLY | 0 | 6 | 2026-06-09T05:00:00+00:00 | 6.0 | 1099.6 | 1.181461 | 1.060704 | -3.96 | -2409.76 | short_rally_rejection_h4sma20_slope2_look12_comp6_1.8_rej6_imp1.2_h6_cool1_all |
| 3 | RECENT_WATCHLIST_SIGNAL_ONLY | RECENT_REGIME_WATCHLIST_ONLY | 0 | 6 | 2026-06-09T05:00:00+00:00 | 6.0 | 1078.32 | 1.25527 | 1.124804 | -2.18 | -682.0 | short_rally_rejection_h4sma20_slope3_look12_comp6_1.8_rej6_imp1.2_h3_cool4_all |
| 4 | RECENT_WATCHLIST_SIGNAL_ONLY | RECENT_REGIME_WATCHLIST_ONLY | 0 | 6 | 2026-06-09T05:00:00+00:00 | 6.0 | 1077.4 | 1.221045 | 1.07815 | -2.68 | -870.88 | short_rally_rejection_h4sma20_slope3_look12_comp6_1.8_rej6_imp1.2_h3_cool1_all |
| 5 | RECENT_WATCHLIST_SIGNAL_ONLY | RECENT_REGIME_WATCHLIST_ONLY | 0 | 6 | 2026-06-09T05:00:00+00:00 | 6.0 | 1075.0 | 1.214196 | 1.076829 | -2.56 | -897.08 | short_rally_rejection_h4sma20_slope2_look12_comp6_1.8_rej6_imp1.2_h3_cool1_all |
| 6 | RECENT_WATCHLIST_SIGNAL_ONLY | RECENT_REGIME_WATCHLIST_ONLY | 0 | 6 | 2026-06-09T05:00:00+00:00 | 6.0 | 1014.24 | 1.23175 | 1.110486 | -2.18 | -837.8 | short_rally_rejection_h4sma20_slope2_look12_comp6_1.8_rej6_imp1.2_h3_cool4_all |
| 7 | RECENT_WATCHLIST_SIGNAL_ONLY | SHORT_TERM_WATCHLIST_ONLY | 0 | 6 | 2026-06-09T05:00:00+00:00 | 6.0 | 698.48 | 1.091112 | 1.065527 | -5.14 | -2476.8 | short_rally_rejection_h4sma20_slope2_look12_comp6_1.8_rej6_imp1.2_h12_cool1_all |
| 8 | RECENT_WATCHLIST_SIGNAL_ONLY | SHORT_TERM_WATCHLIST_ONLY | 0 | 6 | 2026-06-09T05:00:00+00:00 | 6.0 | 624.0 | 1.094494 | 1.062672 | -5.32 | -2101.48 | short_rally_rejection_h4sma20_slope2_look12_comp6_1.8_rej6_imp1.2_h12_cool4_all |
| 9 | RECENT_WATCHLIST_SIGNAL_ONLY | SHORT_TERM_WATCHLIST_ONLY | 0 | 5 | 2026-06-09T03:00:00+00:00 | 8.0 | 696.0 | 1.10431 | 1.013624 | -5.64 | -3157.76 | short_rally_rejection_h4sma10_slope3_look12_comp6_1.8_rej6_imp1.2_h12_cool1_all |
| 10 | RECENT_WATCHLIST_SIGNAL_ONLY | RECENT_REGIME_WATCHLIST_ONLY | 0 | 3 | 2026-06-08T18:00:00+00:00 | 17.0 | 997.96 | 1.32201 | 1.078338 | -2.18 | -861.24 | short_rally_rejection_h4sma20_slope3_look12_comp6_1.8_rej6_imp1.2_h3_cool4_no_asia |
| 11 | RECENT_WATCHLIST_SIGNAL_ONLY | RECENT_REGIME_WATCHLIST_ONLY | 0 | 3 | 2026-06-08T18:00:00+00:00 | 17.0 | 948.96 | 1.760092 | 1.057139 | -6.8 | -1026.68 | short_rally_rejection_h4sma10_slope3_look12_comp6_1.8_rej6_imp1.2_h6_cool1_ny_only |
| 12 | RECENT_WATCHLIST_SIGNAL_ONLY | RECENT_REGIME_WATCHLIST_ONLY | 0 | 3 | 2026-06-08T18:00:00+00:00 | 17.0 | 948.96 | 1.760092 | 1.057139 | -6.8 | -1026.68 | short_rally_rejection_h4sma10_slope3_look12_comp6_1.8_rej6_imp1.2_h6_cool4_ny_only |

## Interpretation
- `ACTIVE_WATCHLIST_ONLY` is not a trade command.
- It means a recent-regime short pattern is currently active and should be observed only.
- Because Stage 11C did not find all-history robustness, these short candidates must not become EA rules.
- Use this report as situational awareness while the validated long-only forward-shadow continues.

## Outputs
- csv: `data/reports/stage11d_recent_short_watchlist_report/stage11d_recent_short_watchlist_report.csv`
- json: `data/reports/stage11d_recent_short_watchlist_report/stage11d_recent_short_watchlist_report.json`
