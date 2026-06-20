# Stage54 Weekend / Market-Closed Runbook

## Normal closed-market state

If the market is closed, this is expected:

```text
changed_timeframes = 0
latest_m15_time_utc = previous_watermark_utc
true_forward_signals = 0
```

Do not reset Stage52 forward state unless a report explicitly says the state is contaminated by backfill.

## After market reopens

1. Export/update AMarkets files into `~/Downloads`.
2. Run Stage52 combined runner.
3. Run Stage53 gate report.
4. Run Stage54 ops readiness report.
5. Send Stage52 runner summary, Stage52 forward summary, Stage53 gate summary, and Stage54 readiness summary.

## Git safety

Do not commit:

```text
data/broker_normalized/
data/shadow/
*.sqlite
*.db
*.zip
```

Commit only scripts, configs, reports, and workflows.
