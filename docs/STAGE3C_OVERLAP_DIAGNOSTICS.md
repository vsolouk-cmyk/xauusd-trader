# Stage 3C Overlap Feed Diagnostics

## Purpose

Stage 3A failed only on degradation. The secondary source was still positive, PF-positive, and cost-stress positive.

Stage 3C determines whether the degradation is caused by comparing different date ranges.

## What it does

- Loads primary Twelve Data SQLite.
- Loads secondary MT5 SQLite.
- Slices both sources to their common overlapping date range.
- Evaluates the fixed candidate on the common range.
- Runs secondary timestamp-shift diagnostics for -3 to +3 hours.

## Important

The official decision uses the exact imported timestamps.

The shifted rows are diagnostics only. They help identify possible broker-server timezone/feed alignment effects.

## Local command

```bash
python3 -m app.xauusd_stage3c_overlap_diagnostics
```

## Interpretation

- `overlap_second_source_pass`: feed degradation was mostly a range-comparison issue.
- `overlap_second_source_fail`: candidate is feed-sensitive or MT5 candles differ materially.
