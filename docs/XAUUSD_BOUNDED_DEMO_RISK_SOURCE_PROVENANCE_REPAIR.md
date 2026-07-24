# Bounded Demo Risk Source Provenance Repair

## Problem

The Commercial Closure risk-contract artifact stores numerical risk limits but
not the observed spread percentile. The old preflight treated the missing
spread field as a mismatch.

## Correct source contract

- Sizing and loss limits: `commercial_closure_risk_contract.json`
- Observed spread guard: `commercial_closure_summary.json` field
  `observed_spread_p95_bps`
- Runtime parity: Replay V7 locked contract and controlled-paper risk contract

The preflight fails closed if any authoritative spread source differs.

## Authorization boundary

The legacy Commercial Closure risk decision is retained as provenance and is
not reinterpreted as authorization. Bounded demo design eligibility comes from
the later event-aware V7 replay. Orders remain forbidden until a separately
reviewed bridge is explicitly armed.
