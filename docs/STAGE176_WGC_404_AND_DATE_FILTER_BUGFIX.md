# Stage176 WGC 404 and pre-2010 filter bugfix

## Scope

This patch changes collector transport/control behavior only. It does not alter the locked allocation thesis, data-vintage contract, holdout, costs, baselines, or decision gates.

## Fixes

1. HTTP 400, 404 and 410 are treated as permanent URL failures and skipped without retry/backoff.
2. WGC report quarters before the locked contract start (`2010Q1`) are excluded during discovery and never enter the report-fetch queue.
3. Discovered report URLs are ordered chronologically by quarter.
4. Progress output explicitly reports a permanent HTTP status and immediate skip.

## Current-run action

Stop the existing run with `Ctrl+C`, install this patch, run tests, and restart Stage176. Existing cached HTML snapshots are preserved and reused.

## Expected progress example

```text
[Stage176][...][WGC_REPORT_FETCH] fetch failed ... error=HTTPError:HTTP Error 404: Not Found permanent=True ...
[Stage176][...][WGC_REPORT_FETCH] permanent HTTP status; skip without retry ...
```

No API key is required by Stage176.
