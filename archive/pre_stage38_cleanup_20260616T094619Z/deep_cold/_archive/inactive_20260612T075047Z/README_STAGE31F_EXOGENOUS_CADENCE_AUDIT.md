# Stage31F Exogenous Tracker Cadence Audit

Adds a local research/shadow-only cadence wrapper for Stage31E.

## Purpose

Stage31E found no signal in 336h/90d but did find sparse signals in 180d. Stage31F runs Stage31E across multiple lookback windows and writes a single cadence summary so the exogenous confirmed candidate can be monitored without promotion.

## Files

- `app/stage31f_exogenous_tracker_cadence_audit.py`

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage31f_exogenous_tracker_cadence_audit
cat data/reports/stage31f_exogenous_tracker_cadence_audit/stage31f_exogenous_tracker_cadence_audit.md
```

Optional lookbacks:

```bash
STAGE31F_LOOKBACK_HOURS_LIST=336,720,2160,4320 python3 -m app.stage31f_exogenous_tracker_cadence_audit
```

## Output

- `data/reports/stage31f_exogenous_tracker_cadence_audit/stage31f_exogenous_tracker_cadence_audit.md`
- `data/reports/stage31f_exogenous_tracker_cadence_audit/stage31f_exogenous_tracker_cadence_audit.json`
- `data/reports/stage31f_exogenous_tracker_cadence_audit/stage31f_cadence_summary.csv`
- copied Stage31E artifacts by lookback

## Guardrails

- Research/shadow observation only.
- No EA change.
- No paper/live/order authorization.
- This stage does not fetch internet data.
