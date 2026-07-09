# Stage169 Event Branch Kill + Current Event Guard

## Purpose

Stage169 is a decision-control stage after Stage168. If the broadened GDELT/event reaction rulespace fails to produce a commercial shortlist, Stage169 explicitly kills the event-alpha branch and preserves the news/event panel only as a current regime/risk guard.

This prevents the recurring failure mode:

1. low-frequency or sparse event rules,
2. attractive holdout fragments,
3. weak or insufficient train evidence,
4. waiting for more samples,
5. delayed commercial progress.

## What it does

- Reads Stage168 summary.
- Confirms whether Stage168 scanned a valid rulespace and produced zero shortlist.
- Reads the installed Stage166-compatible current-event panel.
- Computes positive-train thresholds for `shock_abs`, `gold_long_pressure`, and `gold_short_pressure`.
- Builds a current guard state from the most recent event panel window.
- Writes a decision memo and guard JSON.

## Safety

Stage169 is read-only for execution:

- `order_routing_allowed = false`
- `demo_release_allowed = false`
- No MT5 signal files are written.

## Interpretation

If the decision is:

`STAGE169_KILL_GDELT_REACTION_ALPHA_KEEP_CURRENT_EVENT_GUARD_ONLY`

then GDELT/news is not a standalone alpha path. It can still be useful as:

- current-event regime guard,
- risk throttling context,
- manual review trigger,
- feature for future supervised event-label rebuilds.

It should not trigger Stage169 execution replay because there is no Stage168 shortlist.

## Outputs

- `stage169_event_branch_kill_and_current_guard_summary.json`
- `stage169_current_event_guard.json`
- `stage169_current_event_guard_recent_hours.csv`
- `stage169_decision.md`
