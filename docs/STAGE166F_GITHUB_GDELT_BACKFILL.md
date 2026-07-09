# Stage166F GitHub GDELT Backfill

## Purpose

Stage166F moves GDELT collection from the local Mac/Wine/filtered network path to GitHub Actions. It creates a downloadable artifact containing a GDELT-derived event shock panel that can be installed locally as the Stage166-compatible current-event panel.

It never routes orders, never writes MT5 files, and never authorizes demo/live trading.

## How it works

1. GitHub Actions runs `app/stage166f_github_gdelt_backfill.py fetch` on `ubuntu-latest`.
2. The script queries GDELT DOC API `timelinevolraw` profiles for geopolitical escalation, de-escalation, Fed hawkish/dovish, inflation/energy shocks, market stress, and central-bank gold.
3. It writes raw GDELT files, normalized points, fetch status, and a dense hourly panel.
4. GitHub uploads these as a workflow artifact.
5. The user downloads the artifact locally and runs `install-artifact` to copy the panel into `reports/stage166_current_event_shock_overlay/stage166_current_event_intraday_panel.csv`.
6. Stage167B can then be rerun with a real historical external-event panel.

## Expected artifact files

- `stage166f_gdelt_backfill_summary.json`
- `stage166f_fetch_status.csv`
- `stage166f_gdelt_points.csv`
- `stage166f_current_event_intraday_panel.csv`
- `stage166f_artifact_manifest.json`
- `raw_gdelt/*`

## Recommended run sequence

Start with a probe run:

- `max_queries=20`
- `chunk_days=180`
- `max_workers=4`

If `fetch_ok_count > 0` and `fetch_point_count > 0`, run the full backfill:

- `max_queries=0`
- `chunk_days=180` or `365`
- `max_workers=4`

## Local install after downloading artifact

Unzip the downloaded artifact under:

`~/Downloads/stage166f-gdelt-backfill-<run_id>`

Then run:

```bash
python3 app/stage166f_github_gdelt_backfill.py install-artifact \
  --root ~/Desktop/xauusd-trader \
  --artifact-dir ~/Downloads/stage166f-gdelt-backfill-<run_id> \
  --split-date 2025-08-13 \
  --write-stage166-compatible-panel \
  --backup-existing-compatible-panel
```

## Gate

Do not rerun Stage167 as external-news-aware unless the installed panel has historical train coverage. A good first-pass health condition is:

- `fetch_point_count > 0`
- `health.train_nonzero_shock_hours >= 500`

If this fails, the artifact is useful only as current/regime context, not historical discovery.
