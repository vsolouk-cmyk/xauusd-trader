# Stage32C — Dense Forward Shadow Tracker

## Purpose

Stage32B creates a dense forward-shadow intake queue. Stage32C connects that queue to recurring signal collection.

The goal is commercial acceleration: build forward-observable samples from dense families faster than waiting for low-cadence macro/watchlist candidates.

## Safety

- Research/shadow only.
- No EA change.
- No paper/live.
- No order authorization.

## Default inputs

```text
data/reports/stage32b_dense_forward_shadow_intake/shadow_intake_queue.csv
data/local/xauusd_local_store.sqlite
```

Stage32C reuses the Stage28A DB-first loader, registry, and event logic. This avoids duplicating behavioral definitions.

## Direct run

```bash
python3 -m app.stage32c_dense_forward_shadow_tracker
```

## Orchestrator run

```bash
python3 -m app.run_xauusd_research_shadow_orchestrator --mode aggregate
python3 -m app.run_xauusd_research_shadow_orchestrator --mode supply
```

Stage32C runs after Stage32B by default. To skip it:

```bash
python3 -m app.run_xauusd_research_shadow_orchestrator --mode supply --skip-stage32c-tracker
```

## Outputs

```text
data/reports/stage32c_dense_forward_shadow_tracker/stage32c_dense_forward_shadow_tracker.md
data/reports/stage32c_dense_forward_shadow_tracker/selected_dense_specs.csv
data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_signal_snapshot.csv
data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_signal_ledger.csv
data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_candidate_summary.csv
data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_family_summary.csv
data/reports/stage32c_dense_forward_shadow_tracker/stage32c_summary.json
```

## Interpretation

- `snapshot` = signals found in the current lookback window.
- `ledger` = deduplicated cumulative research-shadow signal ledger.
- `candidate_summary` = whether any dense candidate has enough forward-observable samples for review.
- `family_summary` = which dense family is producing samples fastest.

A review queue is still not paper/live authorization. It only means a candidate has enough shadow evidence for manual review.
