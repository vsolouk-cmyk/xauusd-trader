# Stage 4I Guard Robustness Comparator

Generated UTC: `2026-06-08T19:40:05+00:00`
Tool version: `v1`
Strategy ID: `xauusd_long_tp24_sl15_no_london_v1`

> Hard rule: this is guard robustness research only. It does not authorize demo, paper, or live orders.

## Critical interpretation
- Stage 4G v2 non-overlap remains the replay basis.
- A guard must be reasonably stable across both server UTC offset assumptions.
- Do not change the current live dry-run EA ad hoc. A strategy change requires a new locked strategy version.

## Consensus ranking
| Rank | Guard | Status | Score | Min trades | Min total | Min PF | Min median | Min cost x3 | Min cost x4 | Max |DD| | Flags |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | no_asia | PROMISING_WITH_WARNINGS | 170.851 | 631 | 782.29 | 1.187423 | -2.24 | 340.59 | 119.74 | 323.42 | negative_median_one_offset |
| 2 | overlap_newyork_other | PROMISING_WITH_WARNINGS | 170.851 | 631 | 782.29 | 1.187423 | -2.24 | 340.59 | 119.74 | 323.42 | negative_median_one_offset |
| 3 | new_york_other | PROMISING_WITH_WARNINGS | 162.579 | 281 | 464.34 | 1.222781 | -2.76 | 252.24 | 146.19 | 157.07 | negative_median_one_offset |
| 4 | base_all | PROMISING_WITH_WARNINGS | 127.068 | 941 | 746.29 | 1.10945 | -3.57 | 87.59 | -241.76 | 440.9 | cost_x4_not_positive_one_offset, negative_median_one_offset |
| 5 | london_ny_overlap_only | PROMISING_WITH_WARNINGS | 124.336 | 345 | 291.0 | 1.13414 | -1.89 | 46.0 | -76.5 | 273.19 | cost_x4_not_positive_one_offset, negative_median_one_offset |
| 6 | overlap_other | PROMISING_WITH_WARNINGS | 123.96 | 443 | 338.31 | 1.110427 | -2.645 | 20.51 | -138.39 | 282.1 | cost_x4_not_positive_one_offset, negative_median_one_offset |
| 7 | new_york_only | WEAK | 109.932 | 177 | 81.83 | 1.058403 | -2.86 | -61.67 | -133.42 | 118.95 | pf_below_1_10_one_offset, cost_x3_not_positive_both_offsets, cost_x4_not_positive_one_offset, negative_median_one_offset |
| 8 | other_only | WEAK | 103.861 | 98 | 47.31 | 1.052903 | -15.35 | -25.49 | -61.89 | 158.22 | low_min_trades, pf_below_1_10_one_offset, cost_x3_not_positive_both_offsets, cost_x4_not_positive_one_offset, negative_median_one_offset |

## Per-offset details
### base_all
| Offset | Status | Trades | Total | PF | Median | Max DD | Cost x3 total | Cost x4 total | Flags |
|---|---|---|---|---|---|---|---|---|---|
| offset2 | WARN | 961 | 854.85 | 1.122411 | -3.57 | -396.42 | 182.15 | -154.2 | negative_median, cost_x4_not_positive |
| offset3 | WARN | 941 | 746.29 | 1.10945 | -3.57 | -440.9 | 87.59 | -241.76 | negative_median, cost_x4_not_positive |

### no_asia
| Offset | Status | Trades | Total | PF | Median | Max DD | Cost x3 total | Cost x4 total | Flags |
|---|---|---|---|---|---|---|---|---|---|
| offset2 | WARN | 648 | 1020.58 | 1.242286 | -1.44 | -323.42 | 566.98 | 340.18 | negative_median |
| offset3 | WARN | 631 | 782.29 | 1.187423 | -2.24 | -299.77 | 340.59 | 119.74 | negative_median |

### overlap_newyork_other
| Offset | Status | Trades | Total | PF | Median | Max DD | Cost x3 total | Cost x4 total | Flags |
|---|---|---|---|---|---|---|---|---|---|
| offset2 | WARN | 648 | 1020.58 | 1.242286 | -1.44 | -323.42 | 566.98 | 340.18 | negative_median |
| offset3 | WARN | 631 | 782.29 | 1.187423 | -2.24 | -299.77 | 340.59 | 119.74 | negative_median |

### london_ny_overlap_only
| Offset | Status | Trades | Total | PF | Median | Max DD | Cost x3 total | Cost x4 total | Flags |
|---|---|---|---|---|---|---|---|---|---|
| offset2 | WARN | 345 | 556.24 | 1.26139 | -0.73 | -205.35 | 314.74 | 193.99 | negative_median |
| offset3 | WARN | 350 | 291.0 | 1.13414 | -1.89 | -273.19 | 46.0 | -76.5 | negative_median, cost_x4_not_positive |

### new_york_only
| Offset | Status | Trades | Total | PF | Median | Max DD | Cost x3 total | Cost x4 total | Flags |
|---|---|---|---|---|---|---|---|---|---|
| offset2 | WARN | 205 | 81.83 | 1.058403 | -2.86 | -118.95 | -61.67 | -133.42 | pf_below_1_10, negative_median, cost_x3_not_positive, cost_x4_not_positive |
| offset3 | PASS | 177 | 443.98 | 1.399885 | 0.3 | -99.15 | 320.08 | 258.13 |  |

### other_only
| Offset | Status | Trades | Total | PF | Median | Max DD | Cost x3 total | Cost x4 total | Flags |
|---|---|---|---|---|---|---|---|---|---|
| offset2 | PASS | 98 | 382.51 | 1.559905 | 2.33 | -101.23 | 313.91 | 279.61 |  |
| offset3 | WARN | 104 | 47.31 | 1.052903 | -15.35 | -158.22 | -25.49 | -61.89 | pf_below_1_10, negative_median, cost_x3_not_positive, cost_x4_not_positive |

### overlap_other
| Offset | Status | Trades | Total | PF | Median | Max DD | Cost x3 total | Cost x4 total | Flags |
|---|---|---|---|---|---|---|---|---|---|
| offset2 | WARN | 443 | 938.75 | 1.333935 | -0.37 | -282.1 | 628.65 | 473.6 | negative_median |
| offset3 | WARN | 454 | 338.31 | 1.110427 | -2.645 | -271.3 | 20.51 | -138.39 | negative_median, cost_x4_not_positive |

### new_york_other
| Offset | Status | Trades | Total | PF | Median | Max DD | Cost x3 total | Cost x4 total | Flags |
|---|---|---|---|---|---|---|---|---|---|
| offset2 | WARN | 303 | 464.34 | 1.222781 | -2.63 | -157.07 | 252.24 | 146.19 | negative_median |
| offset3 | WARN | 281 | 491.29 | 1.245087 | -2.76 | -146.57 | 294.59 | 196.24 | negative_median |

## Decision
- Top guard by robustness score: `no_asia` with status `PROMISING_WITH_WARNINGS`.
- No demo-order authorization. Continue live dry-run and run deeper exact validation before any EA change.
