# Stage123 Static Replay Shadow Observer Package

Stage123 is a reports-only static replay of the Stage122 shadow-observer package. It reviews the Stage121 dry-run signal events, verifies the shadow contract, checks event spacing, summarizes split/return metrics when available, and prepares a Stage124 shadow-telemetry queue.

It does not write active observer files, observer bridge files, MT5/MQL5/Files, EA files, paper-order surfaces, or live-order surfaces.

## Inputs

```text
reports/stage122_shadow_observer_package_review/stage122_stage123_static_replay_queue.csv
reports/stage121_dry_run_observer_preflight/stage121_dry_run_signal_events.csv
reports/stage121_dry_run_observer_preflight/stage121_dry_run_observer_preflight_summary.json
reports/stage122_shadow_observer_package_review/stage122_shadow_observer_package_review_summary.json
```

## Outputs

```text
reports/stage123_static_replay_shadow_observer_package/stage123_static_replay_shadow_observer_package_summary.json
reports/stage123_static_replay_shadow_observer_package/stage123_static_replay_shadow_observer_package_report.md
reports/stage123_static_replay_shadow_observer_package/stage123_static_replay_events.csv
reports/stage123_static_replay_shadow_observer_package/stage123_static_replay_metrics.csv
reports/stage123_static_replay_shadow_observer_package/stage123_year_distribution.csv
reports/stage123_static_replay_shadow_observer_package/stage123_month_distribution.csv
reports/stage123_static_replay_shadow_observer_package/stage123_latest_signal_snapshot.csv
reports/stage123_static_replay_shadow_observer_package/stage123_governance_gate.csv
reports/stage123_static_replay_shadow_observer_package/stage123_no_write_manifest.csv
reports/stage123_static_replay_shadow_observer_package/stage123_selected_for_stage124.csv
reports/stage123_static_replay_shadow_observer_package/stage123_watch_or_block.csv
```

## Run

```bash
cd /Users/vahid/Desktop/xauusd-trader
python3 app/stage123_static_replay_shadow_observer_package.py --root /Users/vahid/Desktop/xauusd-trader
```

## Decision

A passing rule moves only to Stage124 shadow telemetry package review. This is not observer activation and is not an observer update.
