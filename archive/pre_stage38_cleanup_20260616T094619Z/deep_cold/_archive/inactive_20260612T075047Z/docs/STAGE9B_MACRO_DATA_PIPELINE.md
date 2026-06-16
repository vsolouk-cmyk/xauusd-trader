# Stage 9B Macro Data Pipeline

Stage 9B implements the data-update architecture:

```text
numeric macro data    -> regular schedule
calendar/event data   -> calendar/manual schedule
execution             -> local + GitHub Actions
outputs               -> local SQLite/CSV + GitHub artifacts
```

## Numeric updater

Primary source: FRED series/observations API.

Series currently collected:

```text
DGS10       US 10Y Treasury yield
DGS2        US 2Y Treasury yield
DFII10      US 10Y TIPS real yield
DTWEXBGS    Broad USD index
DCOILWTICO  WTI crude
DCOILBRENTEU Brent crude
CPIAUCSL    CPI
PPIACO      PPI all commodities
PAYEMS      Nonfarm payrolls
UNRATE      Unemployment rate
FEDFUNDS    Effective fed funds rate
```

Run locally:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage9b_macro_numeric_update --start-date 2022-01-01
cat data/reports/stage9b_macro_numeric_update/macro_numeric_update.md
```

Required environment variable:

```text
FRED_API_KEY
```

If `FRED_API_KEY` is missing, the updater creates a report but skips fetching.

## Event calendar updater

Inputs:

```text
data/config/stage9a_macro_events.csv
data/config/stage9b_scheduled_events_seed.csv
```

Run locally:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage9b_macro_event_calendar_update
cat data/reports/stage9b_macro_event_calendar_update/macro_event_calendar_update.md
```

## GitHub Actions

Workflows:

```text
.github/workflows/macro_numeric_update.yml
.github/workflows/macro_event_calendar_update.yml
```

Numeric workflow:

```text
Runs weekdays at 21:15 UTC
Manual workflow_dispatch available
Uploads artifact: xauusd-macro-numeric-update
```

Event calendar workflow:

```text
Runs daily at 06:25 UTC
Manual workflow_dispatch available
Uploads artifact: xauusd-macro-event-calendar-update
```

## GitHub Secret

Add this repository secret:

```text
FRED_API_KEY
```

GitHub path:

```text
Settings -> Secrets and variables -> Actions -> New repository secret
```

## Artifact usage

If local internet fails, run the GitHub workflow manually and download the artifact from the workflow run. Copy these folders into the local repo:

```text
data/macro/
data/reports/stage9b_macro_numeric_update/
data/macro/events/
data/reports/stage9b_macro_event_calendar_update/
```

## Do not commit local output data

Recommended `.gitignore` entries:

```text
data/macro/
data/reports/stage9b_*/
```

Keep config files tracked:

```text
data/config/stage9a_macro_events.csv
data/config/stage9b_scheduled_events_seed.csv
```

## Hard rule

Data only. No EA change, no demo, no paper, no live authorization.
