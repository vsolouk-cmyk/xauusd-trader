# XAUUSD Controlled-Paper Execution-Ledger Parser Repair

This overlay repairs the bounded missing-coverage audit for the actual Commercial Closure ledger schema.

The production artifact is one 168-row `commercial_closure_execution_ledger.csv` containing:

- 146 execution-evaluated rows;
- 22 rows with missing execution coverage;
- a shared `status` column and execution-result fields.

The previous parser used unsafe substring matching, so `UNEVALUATED` could match `EVALUATED`. The repaired parser:

1. evaluates negative status tokens before positive tokens;
2. distinguishes research-only values from execution evidence;
3. verifies the locked `168 / 146 / 22` split in the same ledger;
4. rejects contradictory status/evidence combinations fail-closed;
5. prefers the canonical closure ledger over stale `invalid`, `archive`, or backup outputs.

No model, threshold, H1 row semantics, spread guard, event guard, risk limit, ledger state, or broker boundary is changed.

See `docs/XAUUSD_CONTROLLED_PAPER_RUNBOOK.md` for installation and operation.
