# Stage 18D Promotion Consolidation and Overlap Audit

Generated UTC: `2026-06-11T09:46:14+00:00`
Tool version: `v1`

> Hard rule: research consolidation only. No EA change, no automatic trading, no paper/live authorization.

## Purpose
- Avoid rerunning slow Stage18C exhaustive refinement for routine work.
- De-duplicate promoted variants that are only small parameter variations.
- Select a small forward-shadow design shortlist.

## Inputs
- summary_csv: `data/reports/stage18c_near_miss_refinement_lab/stage18c_refinement_summary.csv`
- trades_csv: `data/reports/stage18c_near_miss_refinement_lab/stage18c_refinement_trades.csv`
- promoted_rows: `13`
- max_per_family: `1`
- overlap_threshold: `0.8`

## Final decision
- final_decision: `MULTI_FAMILY_FORWARD_SHADOW_SHORTLIST_READY`

## Reasons
- At least two independent behavior families have representatives.

## Selected forward-shadow design shortlist
| Rank | Variant | Family | Events | Freq/mo | PF x1 | PF x4 | Test20 PF | 2026 PF | Boot PF p05 | Consolidation score | Reason |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | `pdl_sweep_reclaim_long_sweep2.5_reclaim2_london_new_york_h6_cool4` | `pdl_sweep_reclaim_refined` | 103 | 2.288889 | 1.856382 | 1.381603 | 9.760234 | 26.445205 | 1.236296 | 21.919068 | Best non-duplicate representative for this family. |
| 2 | `asia_high_breakout_long_close2_range4-35_new_york_only_h48_cool0` | `asia_high_breakout_refined` | 436 | 9.083333 | 1.20546 | 1.023918 | 1.389829 | 999.0 | 1.015511 | 16.19903 | Best non-duplicate representative for this family. |

## Top promoted overlap pairs
| Rank | Variant A | Variant B | Events A | Events B | Overlap | Jaccard |
|---:|---|---|---:|---:|---:|---:|
| 1 | `asia_high_breakout_long_close2_range4-35_new_york_only_h48_cool0` | `asia_high_breakout_long_close2_range4-35_new_york_only_h48_cool4` | 436 | 436 | 1.0 | 1.0 |
| 2 | `pdl_sweep_reclaim_long_sweep1.62_reclaim1.55_london_new_york_h6_cool4` | `pdl_sweep_reclaim_long_sweep1.62_reclaim1.55_london_new_york_h6_cool0` | 143 | 148 | 1.0 | 0.966216 |
| 3 | `pdl_sweep_reclaim_long_sweep2.5_reclaim2_london_new_york_h6_cool0` | `pdl_sweep_reclaim_long_sweep2.5_reclaim2_london_new_york_h4_cool0` | 105 | 110 | 1.0 | 0.954545 |
| 4 | `pdl_sweep_reclaim_long_sweep2_reclaim2_london_new_york_h6_cool4` | `pdl_sweep_reclaim_long_sweep2_reclaim2_london_new_york_h6_cool0` | 133 | 141 | 1.0 | 0.943262 |
| 5 | `pdl_sweep_reclaim_long_sweep2.5_reclaim2_london_new_york_h6_cool4` | `pdl_sweep_reclaim_long_sweep2.5_reclaim2_london_new_york_h4_cool0` | 103 | 110 | 1.0 | 0.936364 |
| 6 | `pdl_sweep_reclaim_long_sweep2_reclaim2_london_new_york_h6_cool0` | `pdl_sweep_reclaim_long_sweep1.62_reclaim2_london_new_york_h6_cool0` | 141 | 168 | 1.0 | 0.839286 |
| 7 | `pdl_sweep_reclaim_long_sweep2_reclaim2_london_new_york_h6_cool4` | `pdl_sweep_reclaim_long_sweep1.62_reclaim2_london_new_york_h4_cool4` | 133 | 163 | 1.0 | 0.815951 |
| 8 | `pdl_sweep_reclaim_long_sweep2_reclaim2_london_new_york_h6_cool4` | `pdl_sweep_reclaim_long_sweep1.62_reclaim2_london_new_york_h6_cool0` | 133 | 168 | 1.0 | 0.791667 |
| 9 | `pdl_sweep_reclaim_long_sweep1.62_reclaim2_london_new_york_h6_cool0` | `pdl_sweep_reclaim_long_sweep1.62_reclaim2_london_new_york_h4_cool4` | 168 | 163 | 0.993865 | 0.95858 |
| 10 | `pdl_sweep_reclaim_long_sweep1.62_reclaim2_london_new_york_h6_cool4` | `pdl_sweep_reclaim_long_sweep1.62_reclaim2_london_new_york_h4_cool4` | 158 | 163 | 0.993671 | 0.957317 |
| 11 | `pdl_sweep_reclaim_long_sweep1.62_reclaim2_london_new_york_h6_cool4` | `pdl_sweep_reclaim_long_sweep1.62_reclaim2_london_new_york_h6_cool0` | 158 | 168 | 0.993671 | 0.928994 |
| 12 | `pdl_sweep_reclaim_long_sweep1.62_reclaim2_london_new_york_h4_cool4` | `pdl_sweep_reclaim_long_sweep1.62_reclaim2_london_new_york_h8_cool4` | 163 | 152 | 0.993421 | 0.920732 |
| 13 | `pdl_sweep_reclaim_long_sweep1.62_reclaim2_london_new_york_h6_cool0` | `pdl_sweep_reclaim_long_sweep1.62_reclaim2_london_new_york_h8_cool4` | 168 | 152 | 0.993421 | 0.893491 |
| 14 | `pdl_sweep_reclaim_long_sweep1.62_reclaim2_london_new_york_h6_cool0` | `pdl_sweep_reclaim_long_sweep1.62_reclaim1.55_london_new_york_h6_cool0` | 168 | 148 | 0.993243 | 0.869822 |
| 15 | `pdl_sweep_reclaim_long_sweep1.62_reclaim2_london_new_york_h4_cool4` | `pdl_sweep_reclaim_long_sweep1.62_reclaim1.55_london_new_york_h6_cool4` | 163 | 143 | 0.993007 | 0.865854 |
| 16 | `pdl_sweep_reclaim_long_sweep1.62_reclaim2_london_new_york_h6_cool0` | `pdl_sweep_reclaim_long_sweep1.62_reclaim1.55_london_new_york_h6_cool4` | 168 | 143 | 0.993007 | 0.840237 |
| 17 | `pdl_sweep_reclaim_long_sweep2_reclaim2_london_new_york_h6_cool4` | `pdl_sweep_reclaim_long_sweep1.62_reclaim2_london_new_york_h6_cool4` | 133 | 158 | 0.992481 | 0.830189 |
| 18 | `pdl_sweep_reclaim_long_sweep2.5_reclaim2_london_new_york_h6_cool4` | `pdl_sweep_reclaim_long_sweep2.5_reclaim2_london_new_york_h6_cool0` | 103 | 105 | 0.990291 | 0.962264 |
| 19 | `pdl_sweep_reclaim_long_sweep1.62_reclaim2_london_new_york_h6_cool4` | `pdl_sweep_reclaim_long_sweep1.62_reclaim2_london_new_york_h8_cool4` | 158 | 152 | 0.986842 | 0.9375 |
| 20 | `pdl_sweep_reclaim_long_sweep1.62_reclaim2_london_new_york_h6_cool4` | `pdl_sweep_reclaim_long_sweep1.62_reclaim1.55_london_new_york_h6_cool4` | 158 | 143 | 0.979021 | 0.869565 |

## Interpretation
- Selected rows are not trade signals; they are only candidates for a later forward-shadow collector patch.
- Highly overlapping variants should not all enter Stage18A; doing so would double-count the same behavior.
- A future Stage18E/19 patch should add only the selected shortlist to unified shadow operations.
- No paper/live/order escalation is authorized.

## Output files
- selected_csv: `data/reports/stage18d_promotion_consolidation/stage18d_selected_forward_shadow_shortlist.csv`
- rejected_csv: `data/reports/stage18d_promotion_consolidation/stage18d_duplicate_or_rejected_promotions.csv`
- overlap_csv: `data/reports/stage18d_promotion_consolidation/stage18d_promoted_overlap_matrix.csv`
- json: `data/reports/stage18d_promotion_consolidation/stage18d_promotion_consolidation.json`
- md: `data/reports/stage18d_promotion_consolidation/stage18d_promotion_consolidation.md`
