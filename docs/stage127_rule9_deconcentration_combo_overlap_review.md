# Stage127 rule9 deconcentration and combo-overlap review

Stage127 reviews the Stage126 Rule9 frontier candidate in one consolidated pass before any further portfolio integration review.

It is shadow/review only. It does not change the active `Unified_ObserverOnly_EA`, does not send orders, does not use CTrade, and does not open any paper/live/broker surface.

## Inputs

- `reports/stage126_frontier_candidate_hardening_and_shadow_overlay/stage126_selected_for_stage127.csv`
- `reports/stage126_frontier_candidate_hardening_and_shadow_overlay/stage126_split_hardening_metrics.csv`
- `data/fundamental_event_inbox/features/stage117_joined_macro_cot_dollar_h1_research_dataset.csv`
- Optional: `reports/stage124_consolidated_shadow_csv_ea_and_frontier_discovery/stage124_consolidated_replay_events.csv`

## Checks

- Rebuild Rule9 events from frozen conditions.
- Recalculate selection / validation / tail economics.
- Review validation year concentration.
- Calculate 120-hour non-overlap path metrics and drawdown-like cumulative cost path.
- Estimate overlap with Rule8 if Stage124 replay events are available.
- Estimate overlap with legacy macro rules when the required feature columns are available.
- Emit Stage128 queue only if deconcentration, non-overlap, tail economics, and overlap gates pass.

## Outputs

- `stage127_rule9_deconcentration_combo_overlap_review_summary.json`
- `stage127_rule9_deconcentration_metrics.csv`
- `stage127_split_validation_concentration.csv`
- `stage127_nonoverlap_path_metrics.csv`
- `stage127_combo_overlap_review.csv`
- `stage127_selected_for_stage128.csv`
- `stage127_watch_or_defer.csv`
- `stage127_rule9_review_status_kv.csv`
- `stage127_governance_no_order_manifest.csv`

## Runtime note

The package also carries refreshed Stage124F / Stage126 indicator sources with smaller fixed-pixel bottom-left layout defaults. These are status-only indicators and do not replace the seven-rule unified observer EA.
