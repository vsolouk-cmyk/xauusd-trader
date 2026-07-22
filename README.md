# XAUUSD Integrated Controlled-Paper Package

This package operationalizes the frozen `logistic__direction_24h` candidate as a **paper-log-only** process.

It does not retrain the model, change the `0.60` threshold, import a broker API, or send an order. It verifies the frozen model and contract hashes against the latest Stage180 summary, consumes only the frozen Stage180 observation, and applies exact aligned-H1 row semantics:

- entry: open of row `i+1`;
- exit: close of row `i+24`.

The package remains fail-closed until its bounded audit identifies exactly 22 missing historical executions and confirms that they are pre-operational or bounded historical M5-coverage gaps rather than a current-period systematic defect.

See `docs/XAUUSD_CONTROLLED_PAPER_RUNBOOK.md` for installation and operation.
