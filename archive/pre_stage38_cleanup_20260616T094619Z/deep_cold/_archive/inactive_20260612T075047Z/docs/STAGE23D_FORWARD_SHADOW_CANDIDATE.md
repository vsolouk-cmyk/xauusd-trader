# Stage23D Forward-Shadow Candidate Tracker

## Purpose

Stage23D tracks one de-duplicated Stage23B/Stage23C candidate in forward-shadow mode.

It is not an operational promotion and it does not change Stage18A v2.

## Candidate

`S23D_PRIMARY_S23B_B_eff0.60_pb0.1_h180_tp0.6_sl0.65`

This is the de-duplicated primary candidate corresponding to the Stage23C validated `S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65` result.

The `pb0.3` duplicate is intentionally not tracked because Stage23C showed identical event signatures.

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage23d_forward_shadow_candidate
cat data/reports/stage23d_forward_shadow_candidate/stage23d_forward_shadow_candidate.md
```

## Outputs

```text
data/reports/stage23d_forward_shadow_candidate/stage23d_forward_shadow_candidate.md
data/reports/stage23d_forward_shadow_candidate/stage23d_forward_shadow_candidate.json
data/reports/stage23d_forward_shadow_candidate/stage23d_forward_shadow_ledger.csv
data/reports/stage23d_forward_shadow_candidate/stage23d_recent_events.csv
```

## Rules

- Research/shadow only.
- No EA change.
- No automatic trading.
- No paper/live/order authorization.
- Stage18A v2 remains the active operational runner.
- Stage23D is separate and must not be merged into Stage18A until forward-shadow evidence exists.

## Interpretation

`FORWARD_OPEN_FIRST_SEEN_BEFORE_OUTCOME` is the useful state.

`LATE_DETECTED_ALREADY_RESOLVED` is only diagnostic/backfill and must not be counted as forward proof.
