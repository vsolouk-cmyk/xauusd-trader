# Runbook

## Review

```bash
python3 app/xauusd_mt5_demo_login_bound_review.py review --root .
```

Expected decision:

`PASS_LOGIN_BOUND_ARMING_REVIEW_DRY_ONLY_NO_ORDER`

## Dry cycle

```bash
python3 app/xauusd_mt5_demo_login_bound_review.py dry-cycle --root .
```

Expected top-level decision:

`PASS_LOGIN_BOUND_DRY_CANDIDATE_CYCLE_NO_ORDER`

The nested dry-cycle status may report no waiting signal, a future entry window,
an event blackout, a stale signal, or a candidate preview. None of these paths
writes an active MT5 candidate or an active arming permit.
