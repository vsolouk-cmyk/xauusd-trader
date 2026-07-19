# Stage176 Progress and Checkpoint Bugfix

## Scope

This is an operational repair to Stage176, not a new research stage. It does not change the central-bank allocation thesis, thresholds, holdout, costs, baselines, or decision gates.

## Why the original run could appear frozen

The collector used a 35-second request timeout and up to four attempts per URL. If the WGC site or a route to it repeatedly failed, index discovery and report collection could continue for many minutes without terminal output. The process could therefore be alive but indistinguishable from a hang.

## Changes

- Flushed terminal progress before and after every network attempt.
- Phase progress for archive indexes and report pages.
- Current/total count, percentage, elapsed time, quarter, URL, cache status, extracted value, and failure streak.
- Durable progress files:
  - `stage176_progress.log`
  - `stage176_progress.json`
- Incremental fetch-ledger and extraction-candidate checkpoints after every report.
- Cache reuse after interruption.
- Circuit breaker after three consecutive index failures.
- Circuit breaker after eight consecutive report failures.
- `--no-progress` switch for controlled test environments.

## Safe handling of the currently running process

Stop the silent run with `Ctrl+C`. Previously downloaded HTML snapshots are retained in:

```text
data/macro_regime/vintages/wgc_gdt_original_report_pages/
```

Install this patch and rerun Stage176. Cached pages will be reported as `cache hit` and will not be downloaded again.

## Live monitoring

Run Stage176 normally:

```bash
python3 app/stage176_central_bank_allocation_falsification.py \
  --root ~/Desktop/xauusd-trader \
  --config configs/stage176_central_bank_allocation_falsification.json
```

From another terminal:

```bash
cd ~/Desktop/xauusd-trader

tail -f \
  reports/stage176_central_bank_allocation_falsification/stage176_progress.log
```

Latest checkpoint:

```bash
cat \
  reports/stage176_central_bank_allocation_falsification/stage176_progress.json
```

Typical output:

```text
[Stage176][00:01:12][WGC_INDEX 4/16 25.0%] page complete new_reports=10 total_reports=36
[Stage176][00:03:41][WGC_REPORTS 18/64 28.1%] cache hit quarter=2018Q2 bytes=184221
[Stage176][00:03:41][WGC_REPORTS 18/64 28.1%] report complete quarter=2018Q2 extraction=PASS value=117.4t valid_rows=17
```

## Fail-closed behavior

A circuit breaker does not produce a research KILL. It prevents wasteful retries and then lets the normal vintage preflight issue `KILL_ASOF_DATA_CONTRACT_UNAVAILABLE` when the historical-as-of input contract cannot be satisfied.
