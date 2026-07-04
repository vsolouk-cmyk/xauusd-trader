# Stage144C Demo Execution Ledger Reconciliation Hotfix

Stage144C replaces the Stage144 reconciliation script with a more robust read-only reconciler.

It fixes the Stage144B failure mode where all entries were marked `OPEN_OR_UNMATCHED` even though the MT5 deal history contained matching entry/exit deals.

Core rules:

- Use only successful `DEMO_BUY_ATTEMPT` rows as entry attempts.
- Ignore `TIME_EXIT` rows as new attempts.
- Deduplicate Stage140 deal history by deal ticket because the collector appends repeated snapshots.
- Match a trade attempt to an entry deal using symbol, volume, fill time, and fill price.
- Pair the exit using the MT5 `position_id`, even if exit magic/comment is blank.

No orders are sent and no positions are modified.
