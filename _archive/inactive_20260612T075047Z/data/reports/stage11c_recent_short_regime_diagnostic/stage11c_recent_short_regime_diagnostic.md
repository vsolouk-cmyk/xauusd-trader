# Stage 11C Recent Short-Regime Diagnostic

Generated UTC: `2026-06-10T19:19:32+00:00`
Tool version: `v1`

> Hard rule: diagnostic only. No EA change, no automatic trading, no paper/live authorization.

## Inputs
- summary_csv: `data/reports/stage11b_alternative_short_thesis_lab/stage11b_short_candidate_summary.csv`
- trades_csv: `data/reports/stage11b_alternative_short_thesis_lab/stage11b_short_candidate_trades.csv`
- candidates_checked: `20`

## Decision
- decision: `recent_short_watchlist_only`

## Verdict counts
| Verdict | Candidates |
|---|---:|
| RECENT_REGIME_WATCHLIST_ONLY | 9 |
| SHORT_TERM_WATCHLIST_ONLY | 7 |
| REJECT | 4 |

## Top diagnostic candidates
| Rank | Verdict | Definition | Trades | All total | All PF | All median | All DD | Recent24m trades | Recent24m total | Recent24m PF | Prior total |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | RECENT_REGIME_WATCHLIST_ONLY | short_rally_rejection | 399 | 782.08 | 1.09333 | -3.76 | -2063.24 | 189 | 1310.52 | 1.226192 | -528.44 |
| 2 | RECENT_REGIME_WATCHLIST_ONLY | short_rally_rejection | 409 | 528.6 | 1.060704 | -3.96 | -2409.76 | 196 | 1099.6 | 1.181461 | -571.0 |
| 3 | RECENT_REGIME_WATCHLIST_ONLY | short_rally_rejection | 394 | 783.68 | 1.124804 | -2.18 | -682.0 | 184 | 1078.32 | 1.25527 | -294.64 |
| 4 | RECENT_REGIME_WATCHLIST_ONLY | short_rally_rejection | 432 | 559.52 | 1.07815 | -2.68 | -870.88 | 204 | 1077.4 | 1.221045 | -517.88 |
| 5 | RECENT_REGIME_WATCHLIST_ONLY | short_rally_rejection | 441 | 562.92 | 1.076829 | -2.56 | -897.08 | 211 | 1075.0 | 1.214196 | -512.08 |
| 6 | RECENT_REGIME_WATCHLIST_ONLY | short_rally_rejection | 404 | 714.32 | 1.110486 | -2.18 | -837.8 | 191 | 1014.24 | 1.23175 | -299.92 |
| 7 | RECENT_REGIME_WATCHLIST_ONLY | short_rally_rejection | 260 | 374.68 | 1.078338 | -2.18 | -861.24 | 124 | 997.96 | 1.32201 | -623.28 |
| 8 | RECENT_REGIME_WATCHLIST_ONLY | short_rally_rejection | 113 | 140.16 | 1.057139 | -6.8 | -1026.68 | 55 | 948.96 | 1.760092 | -808.8 |

## Interpretation
- `ALL_HISTORY_RESEARCH_CANDIDATE` may move to strict robustness research only.
- `RECENT_REGIME_WATCHLIST_ONLY` must not become an EA rule; it can be monitored in forward-shadow reports.
- `REJECT` means no short-side mechanical candidate from this thesis family.
- If only recent-watchlist appears, do not run full-grid on MacBook; collect forward evidence instead.

## Outputs
- candidate_summary_csv: `data/reports/stage11c_recent_short_regime_diagnostic/stage11c_recent_candidate_summary.csv`
- period_breakdown_csv: `data/reports/stage11c_recent_short_regime_diagnostic/stage11c_recent_candidate_period_breakdown.csv`
- json: `data/reports/stage11c_recent_short_regime_diagnostic/stage11c_recent_short_regime_diagnostic.json`
