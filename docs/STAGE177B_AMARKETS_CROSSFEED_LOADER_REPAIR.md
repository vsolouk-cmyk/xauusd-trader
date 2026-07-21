# Stage177B AMarkets Cross-Feed Loader Repair

## Why this repair is required

The first Stage177B run reported only 41 H1 rows and 478 M5 rows, then selected
-840 and -900 minute shifts despite zero overlap. Those shifts are not evidence;
they are tie-breaking artifacts from an unevaluable candidate grid.

The repaired script:

- detects the delimiter deterministically from the MT5 header;
- parses MT5 `YYYY.MM.DD` date/time explicitly;
- reports raw rows, retained rows, file size, hash, first/last timestamps and
  dropped-row reasons;
- prefers the largest historical AMarkets file among known paths;
- uses M5-derived H1 if the direct H1 export is visibly truncated;
- returns `shift_minutes: null` when no candidate has enough overlap;
- fails closed on short history or non-overlapping date ranges.

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m py_compile app/stage177b_amarkets_crossfeed.py

python3 -m unittest discover \
  -s tests \
  -p 'test_stage177b_amarkets_crossfeed_repair.py' \
  -v

python3 app/stage177b_amarkets_crossfeed.py
```

A nonzero exit is expected for a fail-closed `BLOCK_` or `REVIEW_` decision.
The reports are still written.

## Send back

```text
reports/stage177b_extended_history_integration/
  stage177b_amarkets_source_diagnostics.json
  stage177b_amarkets_crossfeed_summary.json
  stage177b_amarkets_crossfeed_decision.md
  stage177b_h1_shift_candidates.csv
  stage177b_m5_shift_candidates.csv
```

No paper, demo or live execution is authorized.
