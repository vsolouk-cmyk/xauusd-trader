# MT5 demo bridge contract — implementation boundary

The next implementation may consume a file-based intent matching `schemas/xauusd_demo_intent.schema.json`.

Mandatory properties:

- Default disabled arming.
- Demo account only.
- No live-account fallback.
- Idempotent intent IDs.
- One symbol: XAUUSD.
- LONG/SHORT only from frozen probability tails.
- Event and spread guards must pass before intent creation.
- Maximum one concurrent position and one new position per day.
- Emergency flat and hard-kill handling.
- Full request/result ledger with broker timestamp, requested price, fill price, spread, slippage, ticket, and rejection reason.

This package does not implement the bridge and does not authorize any order.
