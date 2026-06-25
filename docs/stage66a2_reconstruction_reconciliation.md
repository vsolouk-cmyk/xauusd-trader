# Stage66A2 — H64L Reconstruction Reconciliation

## Purpose

Stage66 Package 1 correctly stopped because Stage66A reconstructed `390` active events while Stage64R expected `336`. This is a `16.07%` mismatch and must not be bypassed.

Stage66B passed the forward-like replay, but the governance dashboard correctly mapped `A_KILL × B_PASS_FAST` to:

```text
STOP_FIX_RECONSTRUCTION_OR_RULE_LOCK
```

This document and package define the next operational step: reconcile the rule definition before any Stage66C paper-execution simulator.

## Why this is not a delay loop

The goal is not to wait for more data. The goal is to remove a definition mismatch immediately so the project can either:

1. continue to Stage66C with a reconciled, auditable H64L rule; or
2. demote H64L if the original Stage64R rule cannot be reconstructed.

This directly supports the commercial objective because it prevents moving fast on the wrong rule definition.

## Likely issue being tested

The current `h64l_locked_rule_v1.json` contains four conditions:

```text
gold_sma20_over_50 > 0
dxy_ret_20d < 0
real_yield_change_20d < 0
etf_flow_tonnes_3m > 0
```

However, the hypothesis name is `H64L_H1_FULL_MACRO_TAILWIND_LONG`, and Stage64/65 summaries also carry central-bank-demand fields. It is possible that the locked v1 rule omitted one part of the original Stage64R rule definition. Stage66A2 tests that possibility in a pre-registered way.

## What Stage66A2 does

The reconciler:

- reads the existing locked rule v1;
- builds a small, pre-registered matrix of candidate rule-definition variants;
- compares each variant against `expected_stage64r_candidate_active_days = 336`;
- does not select by Sharpe, return, or attractiveness;
- writes a proposed `h64l_locked_rule_v2_stage66a2_proposed.json` only if exactly one variant matches within the locked `±2%` tolerance.

## What Stage66A2 must not do

It must not:

- loosen the reconstruction tolerance;
- change horizon length;
- change the four existing rule thresholds;
- choose the best-performing variant;
- authorize paper/live/order/broker paths;
- override Stage66F.

## Expected interpretation

If output decision is:

```text
UNIQUE_RECONCILIATION_MATCH_WRITE_PROPOSED_RULE_LOCK_V2_NO_PROMOTION
```

then rerun Stage66A with the generated reconciled config, then rerun Stage66F.

If output decision is:

```text
MULTIPLE_RECONCILIATION_MATCHES_REQUIRE_MANUAL_RULE_LOCK_REVIEW
```

then do not choose manually by performance. Inspect Stage64R source artifacts and exact historical config.

If output decision is:

```text
NO_RECONCILIATION_MATCH_REQUIRES_STAGE64R_SOURCE_AUDIT
```

then H64L cannot proceed to Stage66C until the original Stage64R rule source is recovered or H64L is demoted.

## Execution

```bash
cd /Users/vahid/Desktop/xauusd-trader

python3 app/stage66a2_h64l_reconstruction_reconciler.py \
  --root . \
  --config configs/stage66a2_h64l_reconstruction_reconciler.json \
  --out reports/stage66a2_h64l_reconstruction_reconciler
```

If a unique proposed lock is written, rerun:

```bash
cd /Users/vahid/Desktop/xauusd-trader

python3 app/stage66a_h64l_concentration_audit.py \
  --root . \
  --config configs/stage66a_h64l_concentration_audit_reconciled_v2.json \
  --out reports/stage66a_h64l_concentration_audit_reconciled_v2 \
  --write-events

python3 app/stage66f_governance_dashboard.py \
  --root . \
  --out reports/stage66f_governance_dashboard
```

## Files to send back

```text
reports/stage66a2_h64l_reconstruction_reconciler/stage66a2_h64l_reconstruction_reconciler_summary.json
reports/stage66a2_h64l_reconstruction_reconciler/stage66a2_h64l_reconstruction_variant_matrix.json
reports/stage66a_h64l_concentration_audit_reconciled_v2/stage66a_h64l_concentration_audit_summary.json
reports/stage66f_governance_dashboard/stage66f_governance_dashboard_summary.json
```
