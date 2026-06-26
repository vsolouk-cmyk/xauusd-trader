# Stage66 GitHub Workflow Cleanup & Local-Data Runtime Policy

## Decision

Stage64/Stage65/Stage66 GitHub Actions that depend on locally generated datasets should not be active while those datasets are not available in the GitHub runner.

The active operational path is local-first:

- update/refresh local macro and external D1 datasets locally;
- run Stage66J2 locally after the data refresh;
- inspect dry-run tickets if any appear;
- keep broker/order/EA/paper-live/live blocked unless a later explicit authorization package is produced.

## Why GitHub workflows are currently unsafe/noisy

The repository does not contain the large local datasets and local DB artifacts required by the Stage64–Stage66 scripts. A GitHub runner starts from the pushed repo state only. If the required data artifacts are missing, stale, or only available on the Mac, workflow executions can fail or repeat stale snapshots.

## Required rule

Do not rely on GitHub Actions for forward-shadow signal discovery until a separate cloud-safe data refresh pipeline exists and passes preflight checks.

## Recommended cleanup

Move or delete active `.github/workflows/*stage64*`, `*stage65*`, and `*stage66*` YAML files that require local data.

Recommended conservative approach: move them to a docs archive and rename them with `.disabled` so GitHub cannot run them.

Keep no Stage64–Stage66 workflow active unless it is explicitly rebuilt to either:

1. generate/download the required dataset inside the runner, or
2. fail gracefully as a documentation/status-only workflow with no operational decision.

## Minimal daily local command

Run this only after local macro/external datasets have been refreshed:

```bash
cd /Users/vahid/Desktop/xauusd-trader

python3 app/stage66j2_multi_readiness_daily_ops.py \
  --root . \
  --config configs/stage66j2_multi_readiness_daily_ops.json \
  --out reports/stage66j2_multi_readiness_daily_ops
```

## Expected no-signal output

If no rule is active:

```text
STAGE66J2_ALL_READINESS_WAIT_SIGNALS_NO_ORDER
```

## Hard blocks

- NO_AUTOMATED_ORDER
- NO_PAPER_ORDER
- NO_BROKER_CONNECTION
- NO_EA_PROMOTION
- NO_PAPER_LIVE
- NO_LIVE
- NO_ORDER_AUTHORIZATION_FROM_WORKFLOW_CLEANUP
- NO_THRESHOLD_TUNING
