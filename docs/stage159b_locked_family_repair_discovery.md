# Stage159B Locked-Family Repair Discovery Hotfix

Stage159B is a failure-safe hotfix for Stage159.

It preserves the original offline, no-order repair discovery logic, but guarantees that if the run fails before scoring, the report directory and placeholder CSV/summary artifacts are written. This prevents silent "no files created" runs.

It does not write execution KV files and does not send orders.

Expected outputs are under:

`reports/stage159_locked_family_repair_discovery/`

Key files:

- `stage159_locked_family_repair_discovery_summary.json`
- `stage159_locked_family_shortlist.csv`
- `stage159_family_repair_summary.csv`
- `stage159_session_repair_summary.csv`
- `stage159_candidate_replay_scores.csv`

If the run fails, the summary has:

- `decision = STAGE159B_REPAIR_DISCOVERY_RUN_FAILED_NO_DEMO_RELEASE`
- `error_type`
- `error_message`

Stage157 freeze should remain active while this stage is inspected.
