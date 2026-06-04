# Cache and Artifact Policy

## Why this exists

Repeated Stage 2 runs were downloading the same 5000 candles for 4 intervals on every workflow run.

That is wasteful because:

- Twelve Data has API credit limits.
- Most historical candles do not change.
- GitHub artifacts became too large.
- The full Stage 2D trades CSV can exceed 35MB and is not needed for routine review.

## Twelve Data limits

Twelve Data uses API credits. Standard API requests consume credits, and plan-specific limits apply. Basic/free plans have daily and per-minute constraints, so repeated full downloads should be avoided.

## Current policy

Stage 1 is now cache-aware.

It reuses the latest normalized CSV if:

- interval matches,
- row count is at least the requested outputsize,
- cache age is within `cache.max_age_minutes`,
- `--force-refresh` is not used.

Default cache age:

```yaml
cache:
  max_age_minutes: 720
```

That is 12 hours.

## Local usage

Reuse cache:

```bash
python3 -m app.xauusd_stage1_snapshot --outputsize 5000
```

Force fresh data:

```bash
python3 -m app.xauusd_stage1_snapshot --outputsize 5000 --force-refresh
```

## GitHub Actions

Workflows restore:

```text
data/raw
data/normalized
```

from GitHub cache before Stage 1 runs.

Routine artifact upload is slim:

- quality reports,
- stage summaries,
- grid evaluation CSV.

Routine artifact upload excludes:

- raw JSON candles,
- normalized CSV candles,
- full trades CSV.

## When to upload or inspect full data

Only when debugging:

- provider mismatch,
- bad timestamps,
- suspicious price scale,
- normalization bug,
- strategy/trade reconstruction bug.
