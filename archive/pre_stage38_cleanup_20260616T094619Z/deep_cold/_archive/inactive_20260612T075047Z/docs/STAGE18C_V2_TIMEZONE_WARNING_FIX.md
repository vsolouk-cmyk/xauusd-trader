# Stage 18C v2 Timezone Warning Fix

This patch fixes repeated pandas warnings during Stage18C execution:

```text
UserWarning: Converting to PeriodArray/Index representation will drop timezone information.
```

## Why it happened

Stage18C calculates metrics many times inside a refinement grid. The warning came from pandas conversions such as:

```text
.dt.to_period("M")
.dt.to_period("Q")
```

on timezone-aware timestamps.

The warning is not an infinite loop, but repeated printing can slow the run and make the terminal look stuck.

## Fix

v2 intentionally converts timestamps to timezone-naive values before monthly/quarterly period grouping:

```text
period_no_tz(...)
```

It also suppresses the exact pandas warning as a safety fallback.

## Install

```bash
cd ~/Desktop/xauusd-trader
unzip -o ~/Downloads/xauusd_stage18c_v2_timezone_warning_fix_patch.zip -d .
```

## Run

```bash
python3 -m app.stage18c_near_miss_refinement_lab
cat data/reports/stage18c_near_miss_refinement_lab/stage18c_near_miss_refinement_lab.md
```

For a fast check:

```bash
python3 -m app.stage18c_near_miss_refinement_lab --fast
```

## Hard rule

Research refinement only:

```text
No EA change
No automatic trading
No paper/live authorization
No direct conversion to order
```
