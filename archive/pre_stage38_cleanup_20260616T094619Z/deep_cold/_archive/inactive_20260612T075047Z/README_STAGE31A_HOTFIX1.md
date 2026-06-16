# Stage31A Hotfix1 — Crash-safe feature quality + template detection

## Purpose

Fixes a Stage31A execution crash:

```text
KeyError: 'pf_x6'
```

The crash occurred when feature-quality rows were diagnostic/low-coverage rows and did not contain the optional `pf_x6` metric column.

## Changes

- `app/stage31a_exogenous_feature_ingestion.py`
  - Makes `_metrics()` return stable x4/x6 keys even when `net_x6` is absent.
  - Makes `feature_quality()` add missing metric columns before ranking.
  - Detects untouched Stage31A template files and marks them as `template_present` instead of real loaded exogenous data.
  - Keeps report generation crash-safe when exogenous data is missing, low-coverage, or template-only.

## Safety

- Research/shadow only.
- No EA change.
- No paper/live/order authorization.
- No internet fetch.
- No changes to Stage18A/23D/25D/27D/28D.

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage31a_exogenous_feature_ingestion
cat data/reports/stage31a_exogenous_feature_ingestion/stage31a_exogenous_feature_ingestion.md
```
