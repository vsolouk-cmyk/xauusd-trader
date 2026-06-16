# Stage31F Exogenous Tracker Cadence Audit

Generated UTC: `2026-06-16T09:41:23.140028+00:00`

## Decision

```text
STAGE31F_LOW_CADENCE_WATCHLIST_REVIEW_ONLY
```

## Scope guardrails

- Research/shadow cadence audit only.
- No EA change, no automatic trading, no paper/live/order authorization.
- Runs Stage31E across multiple lookbacks and summarizes observation cadence.
- Does not fetch internet data.

## Counts

- lookback_count: `4`
- any_recent_signal_rows: `1`
- max_recent_signal_rows: `4`

## Cadence summary

| lookback_hours | stage31e_decision | recent_signal_rows | recent_signal_gate_count | latest_recent_entry_ts | tracker_results | returncode |
|---:|:---|---:|---:|:---|---:|---:|
| 336 | STAGE31E_NO_RECENT_FORWARD_SHADOW_SIGNAL_RESEARCH_ONLY | 0 | 0 |  | 8 | 0 |
| 720 | STAGE31E_NO_RECENT_FORWARD_SHADOW_SIGNAL_RESEARCH_ONLY | 0 | 0 |  | 8 | 0 |
| 2160 | STAGE31E_NO_RECENT_FORWARD_SHADOW_SIGNAL_RESEARCH_ONLY | 0 | 0 |  | 8 | 0 |
| 4320 | STAGE31E_FORWARD_SHADOW_ACTIVE_SIGNAL_REVIEW_ONLY | 4 | 8 | 2026-03-06 13:01:00+00:00 | 8 | 0 |

## Interpretation

- Sparse historical/recent matches do not authorize execution.
- If only long lookbacks produce matches, the candidate should remain in observation/watchlist mode.
- Active-suite integration, if used, should be status-only and should not change EA, paper/live, or order behavior.

## Output files

- `data/reports/stage31f_exogenous_tracker_cadence_audit/stage31f_exogenous_tracker_cadence_audit.md`
- `data/reports/stage31f_exogenous_tracker_cadence_audit/stage31f_exogenous_tracker_cadence_audit.json`
- `data/reports/stage31f_exogenous_tracker_cadence_audit/stage31f_cadence_summary.csv`
- copied Stage31E lookback artifacts under the same directory
