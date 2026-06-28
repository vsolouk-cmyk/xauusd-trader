# Stage121 dry-run observer preflight

Stage121 consumes Stage120 observer-design review outputs and performs a reports-only dry-run preflight.

It does not:
- write active observer files
- write MT5/MQL5/Files
- modify EA
- connect to broker
- create paper/live orders

## Inputs

Expected paths:

```text
reports/stage120_observer_design_review/stage120_stage121_preflight_queue.csv
reports/stage117_segmented_macro_cot_dollar_discovery/stage117_selection_rows.csv
reports/stage117_segmented_macro_cot_dollar_discovery/stage117_validation_rows.csv
reports/stage117_segmented_macro_cot_dollar_discovery/stage117_tail_forward_proxy_rows.csv
```

If available, the preferred dataset is:

```text
data/fundamental_event_inbox/features/stage117_joined_macro_cot_dollar_h1_research_dataset.csv
```

## Run

```bash
cd /Users/vahid/Desktop/xauusd-trader

python3 app/stage121_dry_run_observer_preflight.py   --root /Users/vahid/Desktop/xauusd-trader
```

## Outputs

```text
reports/stage121_dry_run_observer_preflight/stage121_dry_run_observer_preflight_summary.json
reports/stage121_dry_run_observer_preflight/stage121_dry_run_observer_preflight_report.md
reports/stage121_dry_run_observer_preflight/stage121_dry_run_signal_events.csv
reports/stage121_dry_run_observer_preflight/stage121_preflight_metrics.csv
reports/stage121_dry_run_observer_preflight/stage121_feature_availability.csv
reports/stage121_dry_run_observer_preflight/stage121_governance_gate.csv
reports/stage121_dry_run_observer_preflight/stage121_no_write_manifest.csv
reports/stage121_dry_run_observer_preflight/stage121_selected_for_stage122.csv
reports/stage121_dry_run_observer_preflight/stage121_rejected_or_watch.csv
```

## Pass criteria

A rule can pass Stage121 only if:

- all required features exist
- condition text is parsed
- dry-run signals are generated
- no active observer/MT5/EA/order surfaces are touched

A Stage121 pass is not permission to activate observer. It only permits Stage122 packaging/review.
