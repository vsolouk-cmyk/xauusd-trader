# Stage68D Cluster Return Selection Policy

Diagnostic-only audit after Stage68B/68C. It compares pre-registered static rule-priority policies for selecting one representative entry per 60-calendar-day cluster. It also computes an oracle best-in-cluster upper bound for diagnostics only.

Hard blocks remain: no automated order, no paper order, no broker connection, no EA promotion, no paper-live, no live, no threshold tuning, and no promotion from this audit alone.

Inputs:

- `reports/stage68c_return_incremental_value_audit/stage68c_rule_entry_returns.csv`

Outputs:

- `stage68d_cluster_return_selection_policy_summary.json`
- `stage68d_cluster_return_selection_policy_report.md`
- `stage68d_policy_comparison.csv`
- `stage68d_selected_cluster_entries.csv`

The oracle policy is a historical upper bound and must never be used as a forward selection rule.
