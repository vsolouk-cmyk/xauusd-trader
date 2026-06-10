# Stage 10B Event Pipeline Update

Stage 10B removes the manual-only event workflow.

It collects and merges:

```text
scheduled calendar events
manual/curated override events
GDELT shock/news candidates
```

and writes the unified file used by Stage 10A:

```text
data/config/stage10a_news_events.csv
```

## Inputs

```text
data/config/stage9b_scheduled_events_seed.csv
data/config/stage10a_news_events_manual.csv
```

Manual file is only for curated overrides/corrections. It should not be the main workflow.

Create it once:

```bash
cd ~/Desktop/xauusd-trader
cp data/config/stage10a_news_events_manual_template.csv data/config/stage10a_news_events_manual.csv
```

Delete the example row.

## Local run

With GDELT fetch:

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage10b_event_pipeline_update
cat data/reports/stage10b_event_pipeline_update/stage10b_event_pipeline_update.md
```

If local DNS/internet fails, run without GDELT and use GitHub artifacts:

```bash
python3 -m app.stage10b_event_pipeline_update --no-gdelt
```

## GitHub Actions

Workflow:

```text
.github/workflows/event_pipeline_update.yml
```

Runs:

```text
every 3 hours on weekdays
manual workflow_dispatch
```

Artifact:

```text
xauusd-event-pipeline-update
```

Copy artifact outputs into local repo, then run:

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage10a_event_impact_lab
cat data/reports/stage10a_event_impact_lab/stage10a_event_impact_lab.md
```

## Outputs

```text
data/config/stage10a_news_events.csv
data/macro/events/stage10b_scheduled_events_normalized.csv
data/macro/events/stage10b_detected_shock_events.csv
data/macro/events/stage10b_unified_news_events.csv
data/reports/stage10b_event_pipeline_update/stage10b_event_pipeline_update.md
```

SQLite tables:

```text
event_pipeline_staging
event_pipeline_runs
```

## Important

GDELT/news candidates are not truth and not trading signals. Stage 10A must measure actual XAUUSD reaction before a class becomes trusted.

## Hard rule

Data/event collection only. No EA change, no automatic news trading, no paper/live authorization.
