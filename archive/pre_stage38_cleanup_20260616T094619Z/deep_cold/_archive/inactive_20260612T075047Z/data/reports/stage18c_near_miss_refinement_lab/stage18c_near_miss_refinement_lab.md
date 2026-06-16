# Stage 18C Near-Miss Refinement Lab

Generated UTC: `2026-06-11T09:03:07+00:00`
Tool version: `v2_timezone_warning_fix`

> Hard rule: research refinement only. No EA change, no automatic trading, no paper/live authorization.

## Purpose
- Refine the strongest Stage18B near-miss families.
- Do not forward-shadow watchlist candidates directly.
- Search for stricter variants that survive cost x4, chronological splits, 2026, and bootstrap.

## Inputs
- db: `data/local/xauusd_local_store.sqlite`
- m1_rows: `1532063`
- m15_rows: `102403`
- m1_first: `2022-05-01T23:01:00+00:00`
- m1_last: `2026-06-11T10:58:00+00:00`
- cost_usd: `0.35`
- buffer_usd: `0.2`
- variants_tested: `608`
- fast: `False`

## Final decision
- final_decision: `REFINED_PROMOTIONS_FOUND`

## Counts
- promoted: `13`
- refined_watchlist: `104`

## Top refined variants
| Rank | Variant | Family | Decision | Events | Freq/mo | PF x1 | Median x1 | Total x1 | PF x2 | PF x4 | Test20 events | Test20 total | Test20 PF | 2026 total | 2026 PF | Boot PF p05 | Score |
|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | `pdl_sweep_reclaim_long_sweep2.5_reclaim2_london_new_york_h6_cool4` | `pdl_sweep_reclaim_refined` | `PROMOTE_FORWARD_SHADOW_DESIGN_CANDIDATE` | 103 | 2.288889 | 1.856382 | 1.17 | 229.87 | 1.680763 | 1.381603 | 21 | 239.68 | 9.760234 | 148.6 | 26.445205 | 1.236296 | 24.827146 |
| 2 | `pdl_sweep_reclaim_long_sweep2.5_reclaim2_london_new_york_h6_cool0` | `pdl_sweep_reclaim_refined` | `PROMOTE_FORWARD_SHADOW_DESIGN_CANDIDATE` | 105 | 2.333333 | 1.827849 | 1.02 | 225.68 | 1.652383 | 1.354885 | 21 | 239.68 | 9.760234 | 148.6 | 26.445205 | 1.215611 | 24.548297 |
| 3 | `pdl_sweep_reclaim_long_sweep2.5_reclaim2_london_new_york_h4_cool0` | `pdl_sweep_reclaim_refined` | `PROMOTE_FORWARD_SHADOW_DESIGN_CANDIDATE` | 110 | 2.444444 | 1.597122 | 0.915 | 170.98 | 1.435131 | 1.162132 | 22 | 175.69 | 5.49335 | 140.56 | 12.446254 | 1.07047 | 23.383899 |
| 4 | `pdl_sweep_reclaim_long_sweep2_reclaim2_london_new_york_h6_cool4` | `pdl_sweep_reclaim_refined` | `PROMOTE_FORWARD_SHADOW_DESIGN_CANDIDATE` | 133 | 2.770833 | 1.670719 | 0.44 | 213.51 | 1.490107 | 1.190013 | 27 | 235.01 | 5.455166 | 153.4 | 27.267123 | 1.169715 | 23.05874 |
| 5 | `pdl_sweep_reclaim_long_sweep2_reclaim2_london_new_york_h6_cool0` | `pdl_sweep_reclaim_refined` | `PROMOTE_FORWARD_SHADOW_DESIGN_CANDIDATE` | 141 | 2.9375 | 1.609348 | 0.42 | 211.2 | 1.43663 | 1.149563 | 29 | 223.66 | 4.489236 | 153.4 | 27.267123 | 1.108772 | 21.770016 |
| 6 | `pdl_sweep_reclaim_long_sweep1.62_reclaim2_london_new_york_h6_cool4` | `pdl_sweep_reclaim_refined` | `PROMOTE_FORWARD_SHADOW_DESIGN_CANDIDATE` | 158 | 3.22449 | 1.706473 | 0.47 | 256.81 | 1.51701 | 1.203542 | 32 | 199.77 | 3.233564 | 143.24 | 9.9525 | 1.235079 | 19.554264 |
| 7 | `pdl_sweep_reclaim_long_sweep1.62_reclaim2_london_new_york_h4_cool4` | `pdl_sweep_reclaim_refined` | `PROMOTE_FORWARD_SHADOW_DESIGN_CANDIDATE` | 163 | 3.326531 | 1.47021 | 0.28 | 171.65 | 1.291804 | 1.001105 | 33 | 167.1 | 3.531435 | 135.12 | 40.393586 | 1.031624 | 18.859983 |
| 8 | `pdl_sweep_reclaim_long_sweep1.62_reclaim2_london_new_york_h6_cool0` | `pdl_sweep_reclaim_refined` | `PROMOTE_FORWARD_SHADOW_DESIGN_CANDIDATE` | 168 | 3.428571 | 1.592508 | 0.35 | 241.21 | 1.418564 | 1.13025 | 34 | 188.42 | 2.869431 | 143.24 | 9.9525 | 1.136512 | 18.257269 |
| 9 | `pdl_sweep_reclaim_long_sweep1.62_reclaim1.55_london_new_york_h6_cool4` | `pdl_sweep_reclaim_refined` | `PROMOTE_FORWARD_SHADOW_DESIGN_CANDIDATE` | 143 | 3.108696 | 1.573934 | 0.28 | 190.11 | 1.393715 | 1.097594 | 29 | 161.06 | 2.809053 | 122.91 | 8.681875 | 1.118049 | 17.516358 |
| 10 | `pdl_sweep_reclaim_long_sweep1.62_reclaim1.55_london_new_york_h6_cool0` | `pdl_sweep_reclaim_refined` | `PROMOTE_FORWARD_SHADOW_DESIGN_CANDIDATE` | 148 | 3.217391 | 1.539204 | 0.27 | 188.15 | 1.364095 | 1.07611 | 30 | 161.5 | 2.813995 | 122.91 | 8.681875 | 1.073183 | 17.357052 |
| 11 | `pdl_sweep_reclaim_long_sweep1.62_reclaim2_london_new_york_h8_cool4` | `pdl_sweep_reclaim_refined` | `PROMOTE_FORWARD_SHADOW_DESIGN_CANDIDATE` | 152 | 3.102041 | 1.467613 | 0.765 | 208.13 | 1.32875 | 1.092533 | 31 | 158.41 | 2.323724 | 92.76 | 2.989704 | 1.062976 | 16.157904 |
| 12 | `asia_high_breakout_long_close2_range4-35_new_york_only_h48_cool0` | `asia_high_breakout_refined` | `PROMOTE_FORWARD_SHADOW_DESIGN_CANDIDATE` | 436 | 9.083333 | 1.20546 | 0.155 | 524.5 | 1.141442 | 1.023918 | 88 | 278.72 | 1.389829 | 301.73 | 999.0 | 1.015511 | 14.757371 |
| 13 | `asia_high_breakout_long_close2_range4-35_new_york_only_h48_cool4` | `asia_high_breakout_refined` | `PROMOTE_FORWARD_SHADOW_DESIGN_CANDIDATE` | 436 | 9.083333 | 1.20546 | 0.155 | 524.5 | 1.141442 | 1.023918 | 88 | 278.72 | 1.389829 | 301.73 | 999.0 | 1.015511 | 14.757371 |
| 14 | `pdl_sweep_reclaim_long_sweep2.5_reclaim2_london_new_york_h4_cool4` | `pdl_sweep_reclaim_refined` | `KEEP_REFINED_WATCHLIST` | 104 | 2.311111 | 1.552691 | 0.765 | 147.9 | 1.391201 | 1.120429 | 21 | 184.24 | 7.491896 | 127.6 | 82.794872 | 0.962086 | 22.578656 |
| 15 | `pdl_sweep_reclaim_long_sweep2.5_reclaim2_london_new_york_h3_cool0` | `pdl_sweep_reclaim_refined` | `KEEP_REFINED_WATCHLIST` | 110 | 2.444444 | 1.513968 | -0.21 | 134.12 | 1.34026 | 1.057405 | 22 | 144.61 | 6.106285 | 110.03 | 12.216106 | 0.938029 | 20.910921 |
| 16 | `pdl_sweep_reclaim_long_sweep2_reclaim2_london_new_york_h4_cool4` | `pdl_sweep_reclaim_refined` | `KEEP_REFINED_WATCHLIST` | 137 | 2.854167 | 1.377776 | 0.16 | 124.53 | 1.21656 | 0.952231 | 28 | 171.76 | 4.709719 | 120.62 | 36.166181 | 0.927191 | 20.160249 |
| 17 | `pdl_sweep_reclaim_long_sweep2.5_reclaim2_london_new_york_h3_cool4` | `pdl_sweep_reclaim_refined` | `KEEP_REFINED_WATCHLIST` | 105 | 2.333333 | 1.446859 | -0.22 | 112.26 | 1.279418 | 1.006453 | 21 | 145.78 | 6.212013 | 87.81 | 10.282241 | 0.872008 | 20.10386 |
| 18 | `pdl_sweep_reclaim_long_sweep2_reclaim1.55_london_new_york_h6_cool4` | `pdl_sweep_reclaim_refined` | `KEEP_REFINED_WATCHLIST` | 119 | 2.644444 | 1.484773 | 0.26 | 142.15 | 1.320257 | 1.047952 | 24 | 185.24 | 4.265867 | 133.07 | 23.785959 | 0.962151 | 20.103203 |
| 19 | `pdl_sweep_reclaim_long_sweep2.5_reclaim2_london_new_york_h8_cool0` | `pdl_sweep_reclaim_refined` | `KEEP_REFINED_WATCHLIST` | 104 | 2.311111 | 1.457973 | 1.585 | 162.04 | 1.338424 | 1.130068 | 21 | 181.23 | 3.460358 | 87.49 | 2.876662 | 0.935495 | 19.290185 |
| 20 | `pdl_sweep_reclaim_long_sweep2.5_reclaim2_london_new_york_h8_cool4` | `pdl_sweep_reclaim_refined` | `KEEP_REFINED_WATCHLIST` | 103 | 2.288889 | 1.480876 | 1.42 | 166.71 | 1.358848 | 1.146726 | 21 | 181.23 | 3.460358 | 87.49 | 2.876662 | 0.906307 | 19.125311 |
| 21 | `pdl_sweep_reclaim_long_sweep1.25_reclaim2_london_new_york_h4_cool4` | `pdl_sweep_reclaim_refined` | `KEEP_REFINED_WATCHLIST` | 194 | 3.959184 | 1.402228 | 0.155 | 172.21 | 1.225809 | 0.94119 | 39 | 192.05 | 3.868987 | 137.27 | 41.020408 | 1.031368 | 19.031391 |
| 22 | `pdl_sweep_reclaim_long_sweep2_reclaim2_london_new_york_h4_cool0` | `pdl_sweep_reclaim_refined` | `KEEP_REFINED_WATCHLIST` | 150 | 3.125 | 1.367351 | 0.215 | 138.01 | 1.212913 | 0.95732 | 30 | 175.48 | 3.691824 | 133.58 | 10.440283 | 0.983654 | 18.508134 |
| 23 | `pdl_sweep_reclaim_long_sweep1.62_reclaim2_london_new_york_h3_cool0` | `pdl_sweep_reclaim_refined` | `KEEP_REFINED_WATCHLIST` | 181 | 3.693878 | 1.357492 | -0.35 | 143.49 | 1.183892 | 0.908623 | 37 | 176.05 | 3.836771 | 138.23 | 11.448224 | 0.993898 | 18.424868 |
| 24 | `pdl_sweep_reclaim_long_sweep2_reclaim1.55_london_new_york_h6_cool0` | `pdl_sweep_reclaim_refined` | `KEEP_REFINED_WATCHLIST` | 122 | 2.711111 | 1.497435 | 0.21 | 148.35 | 1.330663 | 1.05536 | 25 | 170.11 | 3.367571 | 133.07 | 23.785959 | 0.96939 | 18.291514 |
| 25 | `pdl_sweep_reclaim_long_sweep2_reclaim2_london_new_york_h3_cool0` | `pdl_sweep_reclaim_refined` | `KEEP_REFINED_WATCHLIST` | 151 | 3.145833 | 1.287995 | -0.35 | 102.12 | 1.128622 | 0.872986 | 31 | 154.56 | 3.976314 | 106.61 | 9.058201 | 0.90264 | 17.686646 |
| 26 | `pdl_sweep_reclaim_long_sweep1.62_reclaim2_london_new_york_h4_cool0` | `pdl_sweep_reclaim_refined` | `KEEP_REFINED_WATCHLIST` | 177 | 3.612245 | 1.448144 | 0.28 | 184.51 | 1.277473 | 0.997354 | 36 | 167.24 | 2.879101 | 148.08 | 11.465018 | 1.029626 | 17.634484 |
| 27 | `pdl_sweep_reclaim_long_sweep1.25_reclaim2_london_new_york_h3_cool0` | `pdl_sweep_reclaim_refined` | `KEEP_REFINED_WATCHLIST` | 222 | 4.530612 | 1.3458 | -0.34 | 159.59 | 1.1624 | 0.876429 | 45 | 181.89 | 3.25698 | 141.76 | 11.715042 | 0.996084 | 17.224227 |
| 28 | `pdl_sweep_reclaim_long_sweep1.25_reclaim2_london_new_york_h6_cool4` | `pdl_sweep_reclaim_refined` | `KEEP_REFINED_WATCHLIST` | 186 | 3.795918 | 1.446426 | -0.115 | 206.53 | 1.284808 | 1.019749 | 38 | 206.98 | 2.953379 | 142.09 | 9.285131 | 0.997852 | 17.112753 |
| 29 | `pdl_sweep_reclaim_long_sweep2_reclaim2_london_new_york_h3_cool4` | `pdl_sweep_reclaim_refined` | `KEEP_REFINED_WATCHLIST` | 140 | 2.916667 | 1.262554 | -0.36 | 85.54 | 1.10386 | 0.849414 | 28 | 132.17 | 4.086642 | 75.46 | 6.858696 | 0.838518 | 16.880313 |
| 30 | `pdl_sweep_reclaim_long_sweep1.62_reclaim1.55_london_new_york_h4_cool0` | `pdl_sweep_reclaim_refined` | `KEEP_REFINED_WATCHLIST` | 155 | 3.369565 | 1.407722 | 0.28 | 143.4 | 1.235765 | 0.955531 | 31 | 140.95 | 2.757262 | 120.03 | 9.482686 | 1.046156 | 16.78229 |

## Promoted refined candidates
- `pdl_sweep_reclaim_long_sweep2.5_reclaim2_london_new_york_h6_cool4` — Refined variant passed strict robustness criteria.
- `pdl_sweep_reclaim_long_sweep2.5_reclaim2_london_new_york_h6_cool0` — Refined variant passed strict robustness criteria.
- `pdl_sweep_reclaim_long_sweep2.5_reclaim2_london_new_york_h4_cool0` — Refined variant passed strict robustness criteria.
- `pdl_sweep_reclaim_long_sweep2_reclaim2_london_new_york_h6_cool4` — Refined variant passed strict robustness criteria.
- `pdl_sweep_reclaim_long_sweep2_reclaim2_london_new_york_h6_cool0` — Refined variant passed strict robustness criteria.
- `pdl_sweep_reclaim_long_sweep1.62_reclaim2_london_new_york_h6_cool4` — Refined variant passed strict robustness criteria.
- `pdl_sweep_reclaim_long_sweep1.62_reclaim2_london_new_york_h4_cool4` — Refined variant passed strict robustness criteria.
- `pdl_sweep_reclaim_long_sweep1.62_reclaim2_london_new_york_h6_cool0` — Refined variant passed strict robustness criteria.
- `pdl_sweep_reclaim_long_sweep1.62_reclaim1.55_london_new_york_h6_cool4` — Refined variant passed strict robustness criteria.
- `pdl_sweep_reclaim_long_sweep1.62_reclaim1.55_london_new_york_h6_cool0` — Refined variant passed strict robustness criteria.
- `pdl_sweep_reclaim_long_sweep1.62_reclaim2_london_new_york_h8_cool4` — Refined variant passed strict robustness criteria.
- `asia_high_breakout_long_close2_range4-35_new_york_only_h48_cool0` — Refined variant passed strict robustness criteria.
- `asia_high_breakout_long_close2_range4-35_new_york_only_h48_cool4` — Refined variant passed strict robustness criteria.

## Interpretation
- `REFINED_PROMOTIONS_FOUND` means only that a candidate can go to forward-shadow design, not paper/live.
- `REFINED_WATCHLIST_ONLY` means positive but still insufficient for adding to Stage18A.
- If no refined promotion appears, keep Stage18A running and move discovery to new families.
- No paper/live/order escalation is authorized.

## Output files
- summary_csv: `data/reports/stage18c_near_miss_refinement_lab/stage18c_refinement_summary.csv`
- promoted_csv: `data/reports/stage18c_near_miss_refinement_lab/stage18c_refined_promoted_candidates.csv`
- trades_csv: `data/reports/stage18c_near_miss_refinement_lab/stage18c_refinement_trades.csv`
- json: `data/reports/stage18c_near_miss_refinement_lab/stage18c_near_miss_refinement_lab.json`
- md: `data/reports/stage18c_near_miss_refinement_lab/stage18c_near_miss_refinement_lab.md`
