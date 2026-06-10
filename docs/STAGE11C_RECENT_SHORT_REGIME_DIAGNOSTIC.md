# Stage 11C Recent Short-Regime Diagnostic

Stage 11B found no robust all-history short candidate, but some short_rally_rejection variants had strongly positive test-period results and poor all-history distribution.

Stage 11C checks whether that is:

```text
1. a real all-history research candidate,
2. recent-regime watchlist only,
3. or reject.
```

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage11c_recent_short_regime_diagnostic
cat data/reports/stage11c_recent_short_regime_diagnostic/stage11c_recent_short_regime_diagnostic.md
```

## Outputs

```text
data/reports/stage11c_recent_short_regime_diagnostic/stage11c_recent_short_regime_diagnostic.md
data/reports/stage11c_recent_short_regime_diagnostic/stage11c_recent_candidate_summary.csv
data/reports/stage11c_recent_short_regime_diagnostic/stage11c_recent_candidate_period_breakdown.csv
data/reports/stage11c_recent_short_regime_diagnostic/stage11c_recent_short_regime_diagnostic.json
```

## Decision logic

```text
ALL_HISTORY_RESEARCH_CANDIDATE:
  can move to strict robustness research only.

RECENT_REGIME_WATCHLIST_ONLY:
  no EA rule; can appear in forward-shadow report/watchlist.

REJECT:
  no short mechanical thesis from this family.
```

## Hard rule

Diagnostic only. No EA change, no automatic trading, no paper/live authorization.
