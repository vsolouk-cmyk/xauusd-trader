# Stage58B Context-Aware Stage51 True Forward Shadow

This stage creates a separate true-forward shadow collector for the Stage58A context-aware Stage51 shortlist.

Scope:
- Read AMarkets broker-real multi-timeframe SQLite data.
- Read Stage58A pass candidates.
- Read Stage57A M15/M5 context regime tables.
- On the first normal run, initialize the forward watermark only.
- On subsequent runs, collect only new context-aware Stage51 signals after the watermark.
- Evaluate pending signals after their M5 horizon matures.

Hard blockers:
- No promotion.
- No EA.
- No paper-live.
- No live trading.
- No order submission.
- Historical results are not forward evidence.

State DB:

```text

data/shadow/stage58b_context_forward_shadow.sqlite

```

Expected outputs:

```text
reports/stage58_context_forward_shadow/stage58b_context_forward_shadow_summary.json
reports/stage58_context_forward_shadow/stage58b_context_forward_shadow_report.md
reports/stage58_context_forward_shadow/stage58b_context_forward_shadow_signals.csv
```
