# Stage50 Broker-Real Session Open Range Breakout Audit Design

## Thesis

Fixed UTC session opening ranges may contain exploitable continuation information when breakout direction is confirmed by M15 trend and entry spread is below the broker-real cost gate.

This is not a rescue of Stage49 H1 expansion persistence. It does not use post-hoc long-only/short-only filtering from failed Stage49 candidates.

## Data

- AMarkets broker-real normalized SQLite from Stage49B fast importer.
- Required timeframes: M5 and M15.
- Cost model: Stage48F broker-real cost model.

## Sessions

- London open: 07:00 UTC.
- New York open: 13:00 UTC.

## Audit logic

- Build opening range from first 30 or 60 minutes.
- Detect first breakout within a fixed post-range window.
- Require M15 SMA trend confirmation using already-closed M15 bars.
- Enter on the breakout close; exit after a fixed M5 horizon.
- Subtract Stage48F stress cost.
- Apply spread gate using Stage48F extreme cost reference.
- Run hard-audit style checks in the same executable.

## Gate

No output authorizes EA, paper-live, live trading, or promotion.
