# Stage52 LoaderFix1 — True Forward Shadow, No Initial Backfill

This patch replaces the Stage52 forward-shadow runner with a true forward-only state machine.

## Problem fixed

The previous Stage52 run generated thousands of historical signals on its first run and evaluated almost all of them immediately. That is useful as a backfill diagnostic, but it is not forward-shadow evidence.

## New default behavior

- First normal run initializes `forward_watermark_m15_utc` at the latest available M15 bar.
- First normal run creates zero historical signals.
- Later runs only scan M15 bars newer than the saved watermark.
- Pending signals are evaluated only after their horizon matures.
- Historical backfill exists only behind `--allow-historical-backfill` and should not be used for forward evidence.

## One-time migration

Because the previous state DB already contains historical pseudo-forward signals, run the fixed script once with:

```bash
--reset-forward-state
```

This deletes the accidental Stage52 shadow state and initializes a clean watermark-only state.

No promotion, EA, paper-live, or live trading is authorized.
