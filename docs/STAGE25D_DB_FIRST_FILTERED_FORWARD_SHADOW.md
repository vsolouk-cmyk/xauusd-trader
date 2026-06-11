# Stage25D — DB-First Filtered Forward-Shadow Tracker

Stage25D tracks the canonical Stage23B/C candidate with a forward-safe Stage25C filter.

Hard rules:

- Research/shadow only.
- Stage18A v2 remains unchanged.
- Stage23D remains unchanged.
- No EA change.
- No automatic trading.
- No paper/live/order authorization.
- Candles are read DB-first from `data/local/xauusd_local_store.sqlite`.
- AMarkets CSV fallback is intentionally disabled.

Default tracked filter:

```text
london_range_drop_low30
```

Reason: it is knowable before the Stage23D entry hour. Stronger filters using full `early_ny_range` are not used by default because the full 13-16 NY window is not knowable at entry hour 13.
