# XAUUSD MT5 Demo Pre-Arm Refresh Orchestration Fix

This patch fixes the explicit demo arming sequence.

Before this patch, `arm` ran the login-bound fresh dry cycle directly. If the persistent AMarkets CSV/aligned SQLite had aged while the MT5 recent exporter was already producing fresh files, Stage180 failed freshness and no permit was created.

The corrected sequence is:

1. Validate the existing bridge heartbeat while `InpArmed=false`.
2. Validate fresh recent M5/H1 exporter files.
3. Merge recent completed bars into the persistent AMarkets CSV files with rollback/atomic safeguards.
4. Run Stage180 alignment refresh explicitly.
5. Run the complete login-bound fresh dry cycle.
6. Validate that no candidate, permit, or order permission was created by the dry cycle.
7. Create the login-bound permit.

No risk threshold, model, DST contract, account login, magic number, live boundary, or order path is changed.
