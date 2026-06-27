# Stage68B Overlap / Incremental Frequency Audit

Stage68B is a diagnostic-only follow-up to Stage68. It evaluates the locked H64L, D3, D1, and D4 macro-regime rules on the current macro dataset and measures:

- pairwise active-day overlap,
- incremental active days unique to each rule,
- entry clustering across rules,
- combined active coverage.

It does not authorize orders, threshold tuning, broker connections, EA paths, paper-live, or live trading.

## Run

```bash
python3 app/stage68b_overlap_incremental_frequency_audit.py \
  --root . \
  --config configs/stage68b_overlap_incremental_frequency_audit.json \
  --out reports/stage68b_overlap_incremental_frequency_audit
```

## Outputs

- `stage68b_overlap_incremental_frequency_audit_summary.json`
- `stage68b_overlap_incremental_frequency_audit_report.md`
- `stage68b_pairwise_active_day_overlap.csv`
- `stage68b_incremental_day_contribution.csv`
- `stage68b_entry_clusters.csv`
- `stage68b_rule_entries.csv`
