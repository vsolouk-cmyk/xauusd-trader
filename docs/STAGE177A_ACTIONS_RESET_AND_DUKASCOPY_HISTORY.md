# Stage177A — Actions Storage Reset and Dukascopy Extended History

## Purpose

Stage177A is infrastructure only. It does not test a strategy and does not authorize ML, paper, demo, or live execution.

It performs three bounded operations:

1. Delete all existing GitHub Actions artifacts and optionally all Actions caches.
2. Remove the active GDELT workflow and delete the obsolete `automation/gdelt-latest` snapshot branch.
3. Test Dukascopy acquisition from a GitHub-hosted runner, then acquire extended XAUUSD history in validated chunks.

## Why GitHub Actions

The local Mac/network path previously had Dukascopy access failures. A GitHub-hosted Ubuntu runner provides a materially different network and runtime environment. This is a data-access test, not an assumption that the feed will work.

## Storage policy

- No `actions/cache` is used.
- Every Dukascopy artifact has `retention-days: 1`.
- Data is compressed by chunk before upload.
- A failed full run still uploads validated partial chunks plus a manifest.
- Download the artifact locally before its one-day expiration.

## Workflow order

### 1. Storage preview

Run **XAUUSD Stage177A One-Time Actions Storage Purge** with:

- `dry_run = true`
- `confirmation = PREVIEW`
- `purge_caches = true`
- `delete_gdelt_snapshot_branch = true`

Review the count and byte totals in the workflow log.

### 2. Destructive purge

Run the same workflow with:

- `dry_run = false`
- `confirmation = DELETE_ALL_XAUUSD_ACTIONS_STORAGE`
- `purge_caches = true`
- `delete_gdelt_snapshot_branch = true`

Artifact deletion is irreversible. The cleanup workflow itself uploads no artifact.

### 3. Dukascopy smoke test

Run **XAUUSD Stage177A Dukascopy Extended History** with:

- `preset = smoke_h1_2025`
- `price_type = bid`

Download the resulting artifact. Confirm `stage177a_dukascopy_summary.json` reports `PASS_DOWNLOAD_COMPLETE`.

### 4. Extended H1

Run:

- `preset = h1_full`
- `price_type = bid`

Coverage: 2003-05-05 through the UTC run date. Chunks are 24 months.

### 5. Extended M5

Only after H1 succeeds, run:

- `preset = m5_full`
- `price_type = bid`

Coverage: 2010-01-01 through the UTC run date. Chunks are 12 months.

## Output contract

Each artifact contains:

- `chunks/*.csv.gz`
- `stage177a_dukascopy_manifest.json`
- `stage177a_dukascopy_summary.json`

Each manifest row includes:

- date range and price type;
- row count and timestamps;
- duplicate/non-monotonic checks;
- OHLC and volume checks;
- large-gap inventory;
- compressed SHA-256.

## Kill / block gates

- Smoke test cannot download or validate one month: `BLOCK_DUKASCOPY_GITHUB_ACCESS`.
- H1 full has one or more failed chunks: `PARTIAL_DOWNLOAD_REQUIRES_RERUN`.
- Duplicate timestamps, non-monotonic timestamps, invalid OHLC, or negative volume: chunk rejected.
- A Dukascopy data failure does not kill the XAUUSD project; it blocks this acquisition path only.

## GDELT

The active file `.github/workflows/xauusd_stage166f_gdelt_backfill.yml` must be removed before commit. A disabled historical stub is retained under `archive/disabled_workflows/`. The cleanup workflow deletes `automation/gdelt-latest` if the branch exists.
