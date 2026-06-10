# Stage 10B v2 Rate-Limit Aware Event Pipeline

This patch updates Stage 10B after the GDELT probe showed:

```text
GitHub can fetch GDELT.
Some broad queries hit HTTP 429 Too Many Requests.
```

## Main changes

```text
tool_version = v2_rate_limit_metadata
default query mode = rate_safe
default queries:
  XAUUSD
  gold federal reserve
  gold central bank

default max_records = 10
default query delay = 20 seconds
429 handling with retry/backoff
per-query status CSV
workflow run metadata in artifact
artifact name includes GitHub run number
```

## Workflow run metadata

Every artifact created by this workflow contains:

```text
data/reports/stage10b_event_pipeline_update/workflow_run_metadata.json
data/reports/stage10b_event_pipeline_update/workflow_run_metadata.md
```

The report also includes:

```text
GITHUB_RUN_ID
GITHUB_RUN_NUMBER
GITHUB_RUN_ATTEMPT
GITHUB_WORKFLOW
GITHUB_SHA
```

The artifact name is:

```text
xauusd-event-pipeline-update-run-${{ github.run_number }}
```

## Run locally

Local GDELT may still timeout. That is acceptable.

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage10b_event_pipeline_update --gdelt-query-mode smoke --gdelt-timespan 24h --gdelt-max-records 5
cat data/reports/stage10b_event_pipeline_update/stage10b_event_pipeline_update.md
```

## Run in GitHub

```text
Actions -> XAUUSD Event Pipeline Update -> Run workflow
```

Download artifact:

```text
xauusd-event-pipeline-update-run-<RUN_NUMBER>
```

Inspect:

```text
stage10b_event_pipeline_update.md
stage10b_gdelt_query_status.csv
workflow_run_metadata.md
workflow_run_metadata.json
```

## After artifact download

Copy artifact outputs into local repo, then run:

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage10a_event_impact_lab
python3 -m app.stage10d_event_impact_validation_lab
```

## Hard rule

Data/event collection only. No EA change, no automatic news trading, no paper/live authorization.
