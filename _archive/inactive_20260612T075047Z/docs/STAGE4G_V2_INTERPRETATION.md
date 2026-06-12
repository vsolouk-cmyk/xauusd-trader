# Stage 4G v2 Interpretation

Stage 4G v2 moved from every-signal replay to non-overlap replay. This is the correct decision basis because only one active dry-run trade should exist at a time until TP, SL, or 12 H1-bar time-exit resolves.

Current interpretation:

- The locked rule survives AMarkets backfill but is not commercially strong enough for demo-order.
- The weak areas are negative median, Asia session weakness, early-year weakness, and fragility under high cost stress.
- The next fast path is not waiting passively for many live signals; it is parallel work:
  - continue Stage 5A live dry-run logging,
  - run Stage 4H session guard lab,
  - build Stage 5C outcome tracking for live dry-run signals.

Demo-order remains forbidden until non-overlap replay, live dry-run outcomes, spread guard, and risk guards pass together.
