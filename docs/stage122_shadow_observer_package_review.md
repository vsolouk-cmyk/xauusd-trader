# Stage122 Shadow Observer Package Review

Stage122 is a report-only shadow-observer package review. It consumes Stage121 dry-run observer preflight outputs and prepares a package for Stage123 static replay.

It does not update the active observer, observer bridge, MT5, EA, MQL5/Files, paper-order, or live-order surfaces.

## Inputs

```text
reports/stage121_dry_run_observer_preflight/stage121_dry_run_observer_preflight_summary.json
reports/stage121_dry_run_observer_preflight/stage121_preflight_metrics.csv
reports/stage121_dry_run_observer_preflight/stage121_selected_for_stage122.csv
reports/stage120_observer_design_review/stage120_observer_rule_specs_draft.json
```

## Outputs

```text
reports/stage122_shadow_observer_package_review/stage122_shadow_observer_package_review_summary.json
reports/stage122_shadow_observer_package_review/stage122_shadow_observer_package_review_report.md
reports/stage122_shadow_observer_package_review/stage122_shadow_package_manifest.csv
reports/stage122_shadow_observer_package_review/stage122_shadow_observer_rule_specs_review.json
reports/stage122_shadow_observer_package_review/stage122_stage123_static_replay_queue.csv
reports/stage122_shadow_observer_package_review/stage122_watch_or_block.csv
reports/stage122_shadow_observer_package_review/stage122_governance_gate.csv
reports/stage122_shadow_observer_package_review/stage122_no_write_manifest.csv
```

## Run

```bash
cd /Users/vahid/Desktop/xauusd-trader

python3 app/stage122_shadow_observer_package_review.py \
  --root /Users/vahid/Desktop/xauusd-trader
```

## Pass condition

A candidate can enter Stage123 static replay only when:

```text
preflight_status == PASS_DRY_RUN_PREFLIGHT
spaced_signal_rows >= 20
abs(raw_event_count_delta_pct) <= 1
missing_required_features is empty
condition_parse_count >= 1
event_spacing_hours >= 120
readiness_score >= 70
bucket == PRIMARY_DESIGN
```

Candidate-only SPDR-based rules remain shadow-only and require further replay/governance before any active observer path.
