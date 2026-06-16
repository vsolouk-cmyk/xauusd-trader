# Stage24X Discovery Audit

## Decision

```text
STAGE24X_AUDIT_FOUND_DESIGN_LIMITATIONS_NO_EXECUTION_PROOF_YET
```

## Scope guardrails

- Research/shadow diagnostic only.
- Does not modify Stage18A v2 or Stage23D.
- Does not authorize EA, paper, live, or orders.

## Stage summary
| stage | decision | exact_replayed | promotion_review_candidates | proxy_timed_out | exact_timed_out | best_exact_family | best_exact_pf_x1 | best_exact_pf_x4 | best_exact_pf_x6 | failure_mode |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| stage23b | STAGE23B_HAS_PROMOTION_REVIEW_CANDIDATE_RESEARCH_ONLY | 4 | 4 |  |  | london_oneway_continuation | 6.6576 | 3.5097 | nan | HAS_PROMOTION_OR_REVIEW_CANDIDATE |
| stage23c | STAGE23C_VALIDATED_PROMOTION_REVIEW_ONLY_RESEARCH_ONLY | nan | nan |  |  | london_oneway_continuation | 6.6576 | 3.5097 | 2.1469 | HAS_PROMOTION_OR_REVIEW_CANDIDATE |
| stage24a | STAGE24A_NO_PROMOTION_KEEP_DISCOVERY_OPEN | 4 | 0 |  |  | london_extreme_stoprun_reclaim | 1.323 | 0.8522 | nan | COST_KILLS_EDGE |
| stage24b | STAGE24B_NO_PROMOTION_KEEP_DISCOVERY_OPEN | 8 | nan | True | False | prev_day_inside_breakout_continuation | 1.0461 | 0.7175 | 0.5488 | COST_KILLS_EDGE |
| stage24c | STAGE24C_NO_PROMOTION_KEEP_DISCOVERY_OPEN | 4 | nan | True | False | prev_day_expansion_exhaustion_reversal | 1.0363 | 0.7547 | 0.6031 | COST_KILLS_EDGE |
| stage24d | STAGE24D_NO_PROMOTION_KEEP_DISCOVERY_OPEN | 4 | nan | True | False | day_open_reclaim_reversal | 0.7789 | 0.5134 | 0.3781 | NO_RAW_EDGE |
| stage24e | STAGE24E_NO_PROMOTION_KEEP_DISCOVERY_OPEN | 4 | nan | True | False | day_open_extension_continuation | 0.9557 | 0.6972 | 0.5601 | NO_RAW_EDGE |

## Audit interpretation

- Repeated no-promotion is mostly explained by cost sensitivity: many candidates are near 1.0 under x1 but fall below 1.0 under x4/x6.
- Several Stage24 modules timed out during proxy search, so absence of candidates is not a mathematical proof that all variants are bad.
- Exact replay still ran and the exact-replayed leaders were generally weak after costs, so there is no immediate promotion candidate hidden in the visible top rows.
- Proxy ranking is a design limitation: high-frequency generic families can dominate exact slots, causing family coverage risk.
- Stage23B/23C remain the positive counterexample, so the engine is capable of finding strong candidates; the repeated failures are not by themselves proof that the whole pipeline is broken.

## Recommended next action

Run a Stage25 no-trade/regime-filter discovery instead of more entry-pattern grids. Test whether the weak Stage24 patterns can be used to filter active Stage18A/Stage23D candidates, not to create new entries.