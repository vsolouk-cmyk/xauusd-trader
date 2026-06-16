# Stage 10B v3 Query-Intent Classification

Stage 10B v2 proved that GitHub can fetch GDELT, but most central-bank gold articles were non-English and were classified as `market_news`.

v3 fixes this by using query intent as a classification prior.

## Example

If query is:

```text
gold central bank
```

and the title is Chinese, keyword matching may not see `central bank`. v3 still classifies it as:

```text
event_class = central_bank_gold_demand
event_channel = central_bank_demand
expected_gold_direction = +1
```

unless stronger title keywords override it.

## Quality controls

v3 also drops obvious marketing/broker articles from the `XAUUSD` query.

## Artifact metadata

The workflow artifact still contains:

```text
workflow_run_metadata.json
workflow_run_metadata.md
```

with:

```text
GITHUB_RUN_ID
GITHUB_RUN_NUMBER
GITHUB_RUN_ATTEMPT
GITHUB_WORKFLOW
GITHUB_SHA
```

Artifact name:

```text
xauusd-event-pipeline-update-run-${{ github.run_number }}
```

## Run in GitHub

```text
Actions -> XAUUSD Event Pipeline Update -> Run workflow
```

Then download:

```text
xauusd-event-pipeline-update-run-<RUN_NUMBER>
```

Copy artifact files to local repo and rerun:

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage10a_event_impact_lab
python3 -m app.stage10d_event_impact_validation_lab
```

## Hard rule

Data/event collection only. No EA change, no automatic news trading.
