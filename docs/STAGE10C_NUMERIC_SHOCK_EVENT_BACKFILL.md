# Stage 10C Numeric Shock Event Backfill

Stage 10C creates historical event rows from imported FRED macro/market series.

This solves the immediate problem:

```text
Stage 10B scheduled events are mostly future events.
GDELT may fail locally.
Stage 10A needs historical events to measure reactions.
```

## What it generates

From `macro_numeric_observations`, it detects shocks in:

```text
DFII10       real-yield shock
DGS10        nominal 10Y yield shock
DGS2         front-end yield shock
DTWEXBGS     USD shock
DCOILWTICO   WTI oil shock
DCOILBRENTEU Brent oil shock
```

and converts them into Stage 10A-compatible event rows.

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage10c_numeric_shock_event_backfill
cat data/reports/stage10c_numeric_shock_event_backfill/stage10c_numeric_shock_event_backfill.md
```

Then run Stage 10A:

```bash
python3 -m app.stage10a_event_impact_lab
cat data/reports/stage10a_event_impact_lab/stage10a_event_impact_lab.md
```

## Outputs

```text
data/macro/events/stage10c_numeric_shock_events.csv
data/config/stage10a_news_events.csv
data/reports/stage10c_numeric_shock_event_backfill/stage10c_numeric_shock_event_backfill.md
```

SQLite tables:

```text
numeric_shock_events
numeric_shock_event_runs
```

## Important limitation

These are numeric shock proxies, not original news release timestamps.

For example, a real-yield jump on a FRED observation date is a valid macro shock proxy, but it may not match the exact minute of the news that caused it.

This is still useful for historical event-reaction testing and faster product development.

## Hard rule

Historical event backfill only. No EA change, no automatic news trading, no paper/live authorization.
