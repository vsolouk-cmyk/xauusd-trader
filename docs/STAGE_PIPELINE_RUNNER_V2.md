# XAUUSD Stage Pipeline Runner v2

This runner executes the allowed research/dry-run validation modules in a reproducible order.

Fix in v2:
- Stage 5C outcome reports are now summarized as `OPEN_OR_UNRESOLVED`, `RESOLVED_ALL`, or `PARTIAL_RESOLVE` instead of `UNKNOWN`.

## Live-only quick check

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage_pipeline_runner --mode live_only
cat data/reports/stage_pipeline/stage_pipeline_summary.md
```

Expected while the latest signal has not reached its 12-hour horizon:

```text
stage5b_dryrun_signal_csv_validator: PASS_WITH_WARNINGS
stage5c_live_outcome_tracker: OPEN_OR_UNRESOLVED(...)
```

Hard rule:
- No demo/paper/live authorization.
- No MT5 EA modification.
- No order sending.
