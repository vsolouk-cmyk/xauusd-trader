# Stage 12A Consolidated Forward-Shadow Report

Stage 12A creates one operational report across:

```text
1. Long v2 forward-shadow state
2. Macro context
3. GDELT/news monitoring
4. Event/news guard conclusion
5. Recent short-regime watchlist
6. Final authorization flags
```

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage12a_consolidated_forward_shadow_report
cat data/reports/stage12a_consolidated_forward_shadow_report/stage12a_consolidated_forward_shadow_report.md
```

## Outputs

```text
data/reports/stage12a_consolidated_forward_shadow_report/stage12a_consolidated_forward_shadow_report.md
data/reports/stage12a_consolidated_forward_shadow_report/stage12a_consolidated_forward_shadow_report.json
```

## Hard rule

Consolidated report only.

```text
No EA change
No automatic trading
No demo/paper/live authorization
No short authorization
No news-trading authorization
```
