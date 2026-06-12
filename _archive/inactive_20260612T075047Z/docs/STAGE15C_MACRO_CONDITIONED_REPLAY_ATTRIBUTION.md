# Stage 15C Macro-Conditioned Exact Replay Attribution

Stage 15C adds macro/fundamental context to the Stage 15B validated research candidate.

Candidate:

```text
setup = prev_day_low_sweep_rejection
side = LONG
branch = sweep_depth_ge_q50
regime = reclaim_lt_q50
replay = exact M1 time-exit, 60 minutes
```

## Purpose

This stage does **not** create a standalone macro signal.

It asks:

```text
Does available macro/event context improve or explain the Stage 15B candidate?
```

## Data used

The script first audits available local data:

```text
- SQLite macro/FRED/event/news-like tables
- Stage 10 event calendar if available
- Stage 15B exact replay trades
```

If macro/event data is missing, the report returns a clear data-availability decision instead of failing silently.

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage15c_macro_conditioned_replay_attribution
cat data/reports/stage15c_macro_conditioned_replay_attribution/stage15c_macro_conditioned_replay_attribution.md
```

If macro tables have non-obvious names:

```bash
python3 -m app.stage15c_macro_conditioned_replay_attribution --include-all-tables
```

## Decisions

```text
MACRO_CONTEXT_CANDIDATE_FOUND
MACRO_CONTEXT_WEAK_ATTRIBUTION_ONLY
MACRO_CONTEXT_NO_IMPROVEMENT
MACRO_EVENT_DATA_MISSING
INCONCLUSIVE_NO_CONTEXT_RESULTS
```

## Hard rule

Research attribution only:

```text
No EA change
No automatic trading
No paper/live authorization
No direct conversion to signal
```
