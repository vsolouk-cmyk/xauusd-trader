# Stage66A3 — Exact-Match Rule-Lock Resolution

## Purpose

Stage66A2 correctly refused to auto-select a rule because four variants were inside the ±2% reconstruction tolerance. However, the uploaded output shows only one variant exactly reproduces the Stage64R active-event count of 336.

This patch formalizes a deterministic tie-break:

```text
unique exact active-event-count match
beats
tolerance-only near matches
```

This is not threshold tuning. It does not change the Stage66A tolerance, episode-merge rule, return horizon, or signal thresholds. It only resolves the rule-lock ambiguity created by allowing near matches.

## Selected exact variant

```text
v1_plus_central_bank_demand_tonnes_3m__gold_sma50_over_200
```

Extra locked conditions:

```text
central_bank_demand_tonnes_3m > 0
gold_sma50_over_200 > 0
```

Reason:

```text
active_event_count_with_horizon = 336
expected_stage64r_candidate_active_days = 336
difference_pct_vs_expected = 0.0
```

The other tolerance matches reconstruct 340 events, not 336, and should remain near-match diagnostics rather than rule locks.

## What the script writes

If and only if exactly one exact match exists, the script writes:

```text
configs/h64l_locked_rule_v2_stage66a3_exact_reconciled.json
configs/stage66a_h64l_concentration_audit_reconciled_v2.json
```

Then Stage66A must be rerun with the reconciled config, followed immediately by Stage66F.

## Hard blocks

```text
NO_PAPER_ORDER
NO_EA_PROMOTION
NO_PAPER_LIVE
NO_LIVE
NO_BROKER_CONNECTION
NO_THRESHOLD_TUNING
NO_RESCUE_FILTERING
NO_PROMOTION_FROM_RECONCILIATION_ONLY
```

## Next command after installing

```bash
python3 app/stage66a3_h64l_exact_match_rule_lock_resolver.py \
  --root . \
  --config configs/stage66a3_h64l_exact_match_rule_lock_resolver.json \
  --out reports/stage66a3_h64l_exact_match_rule_lock_resolver
```

If it writes the v2 artifacts, run:

```bash
python3 app/stage66a_h64l_concentration_audit.py \
  --root . \
  --config configs/stage66a_h64l_concentration_audit_reconciled_v2.json \
  --out reports/stage66a_h64l_concentration_audit_reconciled_v2 \
  --write-events

python3 app/stage66f_governance_dashboard.py \
  --root . \
  --out reports/stage66f_governance_dashboard
```
