# XAUUSD Controlled-Paper Historical Replay Runbook

## Purpose

Complete historical-as-of validation without waiting for a future low-frequency
signal.

## Frozen side and horizon

```text
LONG  := probability_up >= 0.60
SHORT := probability_up <= 0.40
entry := open of aligned H1 row i+1
exit  := close of aligned H1 row i+24
```

The `direction` column is retained as metadata; executable side is proved from
probability tails and signed gross P&L.

## Source-proven execution-cost contract

The replay validates the exact formulas used by the Commercial Closure source:

```text
stress_8bps_net_bps =
  m5_gross_bps - max(8.0, observed_spread_bps + 4.0)

stress_10bps_net_bps =
  m5_gross_bps - max(10.0, observed_spread_bps + 6.0)
```

The `+4` and `+6` terms are stress slippage add-ons. They must not be removed or
replaced by inferred alternatives.

## Fail-closed conditions

- inventory differs from `168 / 146 / 22`;
- an evaluated probability is inside the neutral band;
- side-adjusted gross differs from `m5_gross_bps`;
- H1 `i+1/i+24` or entry/exit price parity fails;
- normal or severe net/cost parity fails;
- either source-proven stress formula fails on any row;
- aggregate commercial metrics differ from the saved summary.

## Expected output

With the current forward logger configuration:

```text
decision = PASS_HISTORICAL_COMMERCIAL_REPLAY_BLOCK_FORWARD_POLICY_PARITY
forward_wait_required_for_replay = false
validation.stress_cost_contract.source_proven = true
validation.stress_cost_contract.commercial_execution_parity_pass = true
```

This is not demo/live authorization. It identifies the remaining formulation
drift: historical reference is bidirectional, current forward logger is
`LONG_ONLY`.
