# Existing-Pipeline Historical Event Context Runbook

## Purpose

Close scheduled USD event-blackout coverage for the 146 evaluated commercial entries without creating a second downloader or waiting for forward signals.

## Source ownership

Only this script downloads official data:

```text
scripts/download_xauusd_official_data_batch.py
```

The download target remains:

```text
~/Downloads/xauusd_fundamental_event_inbox
```

`app/xauusd_historical_event_context.py` performs no network access.

## Timestamp semantics

Official dates are sourced from:

- FRED release-dates API for BLS and BEA release families.
- Locally downloaded Federal Reserve FOMC calendar/history pages for FOMC decision days.

Release times are explicit policy mappings in U.S. Eastern time:

```text
Employment Situation             08:30 ET
Consumer Price Index             08:30 ET
Producer Price Index             08:30 ET
JOLTS                            10:00 ET
Employment Cost Index            08:30 ET
Gross Domestic Product           08:30 ET
Personal Income and Outlays      08:30 ET
FOMC Statement                   14:00 ET
FOMC Press Conference            14:30 ET
```

All timestamps are converted with `zoneinfo` and therefore respect U.S. daylight-saving transitions.

This is a scheduled-blackout layer only. It does not claim that event-surprise fields such as actual, consensus and previous are complete.

## Execute

```bash
cd ~/Desktop/xauusd-trader
python3 scripts/run_xauusd_fundamental_unify_normalize_pipeline.py \
  --download-first \
  --event-core-only \
  --build-historical-event-context \
  --run-replay
```

## Fail-closed conditions

The bridge stops if:

- Stage115 timestamped events are missing.
- Any event timestamp or required field is invalid.
- BLS, BEA or Fed coverage is below conservative annual floors.
- A required category is absent.
- The mapping is not exactly 146 unique evaluated entry hours.
- The commercial ledger hash or replay contract does not tie out.

## Expected decisions

Context build:

```text
PASS_EXISTING_PIPELINE_HISTORICAL_EVENT_CONTEXT_CORE_BLACKOUT
```

Replay full pass:

```text
PASS_FULL_HISTORICAL_EVENT_AWARE_REPLAY_DEMO_DESIGN_ALLOWED_NO_FORWARD_WAIT
```

A full pass permits bounded demo design only. It does not allow demo orders or live orders.
