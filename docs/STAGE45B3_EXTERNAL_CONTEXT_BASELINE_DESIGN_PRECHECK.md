# Stage45B3 External Context Baseline Design Precheck

Stage45B3 is a design precheck after Stage45B2/Stage45B2A. It verifies whether the aligned external context is suitable for designing a predefined baseline scan.

It does not create signals, shortlist candidates, rescue archived rows, or authorize EA/paper/live/live.

## Inputs

```text
reports/stage45b2/stage45b2_external_context_alignment_audit_summary.json
reports/stage45b2a/stage45b2a_external_context_alignment_repair_summary.json
```

## Outputs

```text
reports/stage45b3/stage45b3_external_context_baseline_design_precheck_summary.json
reports/stage45b3/stage45b3_external_context_baseline_design_precheck.md
reports/stage45b3/stage45b3_design_precheck_matrix.csv
reports/stage45b3/stage45b3_context_feature_contract.csv
reports/stage45b3/stage45b3_news_calendar_quality_profile.csv
```

## Default gates

```text
min_daily_safe_lag_coverage_pct = 0.95
min_cme_overlap_pct = 0.70
min_cme_return_corr = 0.65
min_cme_sign_agreement_pct = 0.60
min_selected_blackout_pct = 0.001
max_selected_blackout_pct = 0.25
```

The upper blackout threshold is intentionally conservative. A no-trade blackout that removes too large a share of M15 bars is not a clean risk filter; it changes the sample too aggressively and can make subsequent evidence hard to interpret.

## Usage

```bash
python3 scripts/stage45b3_external_context_baseline_design_precheck.py --print-summary
```

Optional stricter or looser blackout bound:

```bash
python3 scripts/stage45b3_external_context_baseline_design_precheck.py \
  --max-selected-blackout-pct 0.15 \
  --print-summary
```

## Expected interpretations

If Stage45B2A is ready but the selected blackout covers too many bars, Stage45B3 blocks baseline design and recommends:

```text
Stage45B3A_NEWS_CALENDAR_SEMANTIC_REDUCTION
```

If all checks pass, the next step is:

```text
Stage46_EXTERNAL_CONTEXT_BASELINE_SCAN_DESIGN
```

## Not allowed

- Candidate rescue from Stage41/42/43
- Post-hoc filtering of bad buckets
- EA/paper/live/live promotion
- ML before robust baseline evidence
- New blind megascan before context design is clean
