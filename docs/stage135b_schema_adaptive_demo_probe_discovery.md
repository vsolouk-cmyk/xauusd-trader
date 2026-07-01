# Stage135B Schema-adaptive demo probe discovery

Fixes Stage135 hard-coded schema binding. It scans available numeric feature columns, validates simple threshold probes, and writes a Stage134-compatible KV only if a current-active PASS candidate exists. Stage135B itself sends no orders.
