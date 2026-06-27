# Stage97 COT Positioning Hard Audit

Stage97 hard-audits the Stage96 COT discovery shortlist before any observer-portfolio expansion.

It does not:
- authorize orders
- connect to a broker
- change MT5 or EA files
- tune Stage96 thresholds
- promote paper/live execution

Inputs:
- `reports/stage96_cot_positioning_thesis_discovery/stage96_cot_positioning_thesis_discovery_summary.json`
- `reports/stage96_cot_positioning_thesis_discovery/stage96_cot_thesis_shortlist.csv`
- fallback: `reports/stage96_cot_positioning_thesis_discovery/stage96_cot_candidate_metrics.csv`

Outputs:
- `stage97_cot_positioning_hard_audit_summary.json`
- `stage97_cot_positioning_hard_audit_report.md`
- `stage97_cot_hard_audit_metrics.csv`
- `stage97_selected_for_stage98.csv`

Stage98, if reached, must be a portfolio-increment review and not a direct observer expansion.
