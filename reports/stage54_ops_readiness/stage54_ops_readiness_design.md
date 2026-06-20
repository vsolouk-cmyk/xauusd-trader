# Stage54 Ops Readiness and Data/Git Hygiene

## Purpose

Stage54 is an operational readiness layer for the XAUUSD project while Stage52 true-forward evidence is waiting for live market data.

It does not create trading signals, orders, EA, paper-live, live trading, or promotion. It only checks whether the local environment is safe and ready for the next AMarkets update cycle.

## What it checks

- Git hygiene:
  - local broker databases ignored
  - shadow runtime databases ignored
  - zip transfer packs ignored
  - no large local data tracked by Git
- AMarkets export freshness:
  - M1, M5, M15, M30, H1 export files exist
  - last row timestamp is parseable
- Persistent broker DB:
  - `amarkets_bars` schema is readable
  - row counts and latest timestamp by timeframe
- Stage52 true-forward state:
  - state DB schema is readable
  - backfill signal count remains zero
  - pending/evaluated true-forward signal counts are visible
- Stage52/Stage53 summaries:
  - runner summary and gate summary are available
  - watermark vs latest M15 state can be compared

## Decision logic

- `OPS_READINESS_BLOCKED_FIX_HIGH_SEVERITY_CHECKS_NO_PROMOTION`
  - local data is still tracked by Git, or shadow DB/schema is unsafe.
- `OPS_READY_NEW_DB_BARS_AVAILABLE_RUN_STAGE52_STAGE53_NO_PROMOTION`
  - DB has M15 bars newer than the known Stage52 watermark.
- `OPS_READY_WAIT_FOR_NEW_AMARKETS_M15_BARS_NO_PROMOTION`
  - environment is safe, but no new M15 bars are available yet.

## Safety

Promotion, EA, paper-live, live trading, and order submission are all hard blocked.
