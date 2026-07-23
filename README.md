# XAUUSD Bidirectional Controlled-Paper Direction-Parity Closure

This overlay closes the direction-policy mismatch identified by the source-proven historical replay.

## Locked execution-side contract

- LONG when `probability_up >= 0.60`.
- SHORT when `probability_up <= 0.40`.
- Neutral band `(0.40, 0.60)` creates no position.
- Stage180 `direction` is retained as metadata only and is never used to derive execution side.
- A legacy Stage180 `NO_SIGNAL` status is acceptable for a low-tail SHORT because Stage180 was originally long-only.

## Exact paper lifecycle

- Signal row: aligned H1 row `i`.
- Entry: open of aligned H1 row `i+1`.
- Exit: close of aligned H1 row `i+24`.
- Entry admissibility spread guard: observable entry spread for both sides; no future leakage.
- Commercial execution cost:
  - LONG uses entry spread.
  - SHORT uses the final M5 spread of the exit H1 bucket, matching the source generator.
- Normal cost: `max(3.0, observed_spread + 0.5)` bps.
- Severe cost: `max(4.5, observed_spread * 1.5 + 2.0)` bps.
- Stress 8: `max(8.0, observed_spread + 4.0)` bps.
- Stress 10: `max(10.0, observed_spread + 6.0)` bps.

## Safety boundary

- Paper ledger only.
- No broker API.
- No demo or live order path.
- Existing V1.4 SQLite ledger is migrated in place; it is not reset.
- Bidirectional preflight is blocked until the V6 historical replay proves source hashes, 55/91 direction scope, commercial metric parity, source-proven stress cost, and zero forward-wait dependency.

## Required execution order

1. Install this overlay.
2. Run the combined tests.
3. Run V6 historical replay.
4. Confirm direction parity is closed.
5. Refresh Stage180 and run controlled-paper preflight/run.

Historical event context remains incomplete. This does not require waiting for a future signal, but it remains a bounded pre-demo data requirement.
