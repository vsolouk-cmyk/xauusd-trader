# Stage171F — H64L Four-Hour Macro + GDELT Operations Orchestrator

## Purpose

Stage171F replaces the direct Stage171D LaunchAgent with a single four-hour operational chain:

1. Check the manually updated AMarkets CSV files.
2. Run the repository's existing official macro/fundamental downloader.
3. Run the existing unification and normalization pipeline.
4. Run the existing macro rebuild / Stage64K feature builder when present.
5. Fetch the latest GDELT snapshot from the GitHub branch `automation/gdelt-latest` and merge recent hours into the existing Stage166-compatible panel.
6. Validate the freshness of `stage64k_full_scope_lag_safe_feature_dataset.csv`.
7. Invoke Stage171D only when the H64L feature dataset is fresh.

This is an operations patch, not a new discovery stage.

## Hard constraints

- AMarkets is never downloaded automatically; the files remain user-maintained.
- No threshold changes or feature searches.
- No MT5 signal file.
- No order routing.
- No demo/live authorization.
- A stale Stage64K feature dataset blocks Stage171D instead of logging another row from stale data.

## Local four-hour data chain

The existing repository scripts are called in this order:

- `scripts/download_xauusd_official_data_batch.py`
- `scripts/run_xauusd_fundamental_unify_normalize_pipeline.py`
- `app/stage67d6_download_format_aware_rebuild_macro.py`, if present
- active or archived Stage64K builder, if present

The first two are required. Optional rebuild scripts are logged if absent. Every command's return code and stdout/stderr tail are written to:

- `reports/stage171f_h64l_4h_macro_gdelt_orchestrator/stage171f_pipeline_step_status.csv`
- `reports/stage171f_h64l_4h_macro_gdelt_orchestrator/stage171f_orchestrator_summary.json`

## GDELT workflow

Workflow name:

`XAUUSD Stage166F GDELT Four-Hour Refresh`

Workflow file:

`.github/workflows/xauusd_stage166f_gdelt_backfill.yml`

Scheduled behavior:

- runs every four hours at minute 17 UTC;
- refreshes the most recent 21 days;
- uses one worker, seven-day chunks, bounded retries and delay to reduce HTTP 429 failures;
- uploads an immutable run artifact;
- force-updates the snapshot-only branch `automation/gdelt-latest`.

The local Stage171F process fetches that branch without changing the local working tree. It extracts the files with `git show` and merges the recent panel by `time_bucket_utc`, retaining older historical rows locally.

If the branch fetch fails, Stage171F looks for the newest matching Stage166F artifact ZIP in `~/Downloads`.

## Scheduling

The Stage171F LaunchAgent uses `StartInterval=14400` and `RunAtLoad=true`.

Unload the former direct Stage171D service before enabling Stage171F to prevent duplicate ledger rows.

## Freshness policy

Default maximum H64L feature age is three days. This is intentionally conservative enough for weekends and publication delays while preventing repeated evaluation of materially stale macro data.

AMarkets freshness is reported separately with a default 36-hour threshold. A stale AMarkets file is a visible operator warning; Stage171F does not attempt to replace it.
