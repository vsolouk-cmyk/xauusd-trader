# Active XAUUSD Research-Shadow Suite

Generated UTC: `2026-06-16T09:41:09.295308+00:00`

## Decision

```text
ACTIVE_SHADOW_SUITE_COMPLETED
```

## Scope guardrails

- Research/shadow only.
- No EA change, no automatic trading, no paper/live/order authorization.
- CSV import/refresh is attempted first when the import module exists.
- Stage18A still remains the active operational shadow runner.

## Run summary

| label | status | decision | runtime_seconds | report_path |
| --- | --- | --- | --- | --- |
| csv_import_refresh | ok | None | 440.31 | data/reports/stage16e_amarkets_csv_refresh_cycle/stage16e_amarkets_csv_refresh_cycle.md |
| stage18a_unified_shadow_ops_cycle | ok | UNIFIED_FORWARD_SIGNAL_OPEN | 464.61 | data/reports/stage18a_unified_shadow_ops_cycle/stage18a_unified_shadow_ops_cycle.md |
| stage23d_forward_shadow_candidate | ok | STAGE23D_NO_ACTIVE_FORWARD_SIGNAL_RESEARCH_ONLY | 27.02 | data/reports/stage23d_forward_shadow_candidate/stage23d_forward_shadow_candidate.md |
| stage25d_db_first_filtered_forward_shadow | ok | STAGE25D_NO_ACTIVE_FILTERED_FORWARD_SIGNAL_RESEARCH_ONLY | 29.42 | data/reports/stage25d_db_first_filtered_forward_shadow/stage25d_db_first_filtered_forward_shadow.md |
| stage27d_db_first_h1_atr_filtered_forward_shadow | ok | STAGE27D_NO_ACTIVE_H1_ATR_FILTERED_FORWARD_SIGNAL_RESEARCH_ONLY | 27.42 | data/reports/stage27d_db_first_h1_atr_filtered_forward_shadow/stage27d_db_first_h1_atr_filtered_forward_shadow.md |

## Output files

- `data/reports/active_shadow_suite/active_shadow_suite.json`
- `data/reports/active_shadow_suite/active_shadow_suite.md`
