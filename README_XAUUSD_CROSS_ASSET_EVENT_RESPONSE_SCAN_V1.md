# XAUUSD Cross-Asset Event-Response Scan V1.1

## Repair scope

V1 incorrectly reused daily macro-panel columns `official_event_blackout_active/count`.
Because the daily causal panel makes decisions at 00:00 UTC, those blackout columns are
correctly zero and cannot define intraday event windows.

V1.1 loads the locked raw official timestamp source directly:

`data/fundamental_event_inbox/features/stage115_official_core_event_timestamps.csv`

Expected SHA256:

`601f587e0128d4322bc3ea5071545e53adf035b5e08fdbafa72cf16a550ec560`

A panel decision is event-response eligible only when one or more official events occurred
15 to 120 minutes before that decision. The completed M15 reactions therefore remain causal.

The candidate registry, costs, reference period, diagnostic lock, and all order permissions
are unchanged. Preflight failures are now written outside the run output directory so they
do not poison a subsequent run.

No network access, MQL, export, paper order, demo order, or live order is used.
