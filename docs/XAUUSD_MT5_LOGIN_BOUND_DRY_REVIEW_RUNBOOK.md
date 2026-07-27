# XAUUSD MT5 Login-Bound Fresh Dry-Cycle Runbook

## Defect closed

`dry-cycle` formerly inspected the existing controlled-paper ledger without
refreshing Stage180 or controlled-paper. A market-open run could therefore reuse
a stale neutral observation and incorrectly look current.

## Safe command

```bash
python3 app/xauusd_mt5_demo_login_bound_review.py fresh-dry-cycle --root .
```

The command streams three existing project steps:

1. Stage180 frozen-model refresh;
2. controlled-paper preflight;
3. controlled-paper run.

It then validates:

- Stage180 was generated during this run;
- latest aligned H1 is no more than 180 minutes old;
- controlled-paper was generated during this run;
- controlled operational freshness is `PASS_OPERATIONAL_FRESHNESS_OPEN_MARKET`;
- login remains `7907958`, account remains DEMO and volume contract remains safe;
- no active `arming_permit.txt` or `demo_candidate.txt` exists.

## Outputs

```text
reports/xauusd_mt5_demo_bridge/mt5_demo_login_bound_fresh_dry_cycle_summary.json
reports/xauusd_mt5_demo_bridge/mt5_demo_login_bound_dry_cycle_summary.json
reports/xauusd_mt5_demo_bridge/mt5_demo_dry_candidate_preview.json
```

A fresh neutral observation is a successful dry-cycle and does not create a
new forward-wait gate. It still does not authorize an active permit or an order.

## Failure behavior

The command fails closed when:

- the Stage180 runner cannot be uniquely discovered from `app/stage180*.py`;
- raw AMarkets data are stale and Stage180 cannot produce a fresh H1 result;
- controlled-paper freshness fails;
- any broker/demo/live order boundary is open;
- an active permit or active candidate already exists.
