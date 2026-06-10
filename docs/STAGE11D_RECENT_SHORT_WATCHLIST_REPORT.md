# Stage 11D Recent Short Watchlist Report

Stage 11C found no all-history robust short candidate, but some short candidates are useful as recent-regime watchlist only.

Stage 11D reports whether those watchlist patterns are currently active.

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage11d_recent_short_watchlist_report
cat data/reports/stage11d_recent_short_watchlist_report/stage11d_recent_short_watchlist_report.md
```

## Outputs

```text
data/reports/stage11d_recent_short_watchlist_report/stage11d_recent_short_watchlist_report.md
data/reports/stage11d_recent_short_watchlist_report/stage11d_recent_short_watchlist_report.csv
data/reports/stage11d_recent_short_watchlist_report/stage11d_recent_short_watchlist_report.json
```

## Hard rule

Report/watchlist only. No EA change, no automatic trading, no paper/live authorization.
