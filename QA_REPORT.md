# QA Report — Bidirectional Direction-Parity Closure

## Source basis

The implementation was derived from the real Commercial Closure execution ledger, summary, and source generator supplied in `XAUUSD_REPLAY_FORENSIC_INPUT.zip`.

## Frozen formulation confirmed from real artifacts

- Signal-ledger rows: 168.
- Execution-evaluated rows: 146.
- Missing-execution-evidence rows: 22.
- LONG rows: 55.
- SHORT rows: 91.
- Execution side: probability tails only.
- Generic `direction` column: non-execution metadata.
- Commercial cost formulas: source-proven from `app/commercial_closure_sprint.py`.

## Implemented controls

- LONG at `probability_up >= 0.60`.
- SHORT at `probability_up <= 0.40`.
- Neutral-band no-position behavior.
- Legacy Stage180 low-tail `NO_SIGNAL` accepted for SHORT.
- Side persisted in signal and position ledgers.
- Non-destructive V1.4 SQLite schema migration.
- Side-adjusted LONG/SHORT P&L.
- SHORT cost spread from the final M5 record of the exit H1 bucket.
- Source-proven normal, severe, stress-8, and stress-10 costs.
- Mandatory V6 historical replay evidence before bidirectional controlled-paper preflight.
- Stale V5 replay evidence rejected.
- No broker, demo, or live execution path.

## Completed QA

- Python compilation: PASS.
- Combined controlled-paper + replay tests: 48/48 PASS.
- Real 168/146/22 artifact tie-out: PASS.
- Real 55/91 probability-tail side tie-out: PASS.
- Real 146-row source-proven cost/net tie-out: PASS.
- Real commercial metric blocks tie-out: PASS.
- SHORT legacy metadata regression: PASS.
- SHORT final-exit-M5-spread regression: PASS.
- Neutral-band regression: PASS.
- Existing V1.4 ledger migration regression: PASS.
- Stale V5 replay authorization rejection: PASS.
- Historical replay V6 CLI smoke: PASS.
- V6 direction parity closure: PASS.
- Event-coverage-incomplete decision: PASS.
- Clean ZIP extraction: required and performed after packaging.
- Manifest verification: required and performed after packaging.

## Remaining bounded gap

Historical event context is absent for the 146 evaluated entries. This is not a forward-signal wait requirement. It remains a pre-demo historical-data requirement. Controlled paper logging may continue; demo/live remain forbidden.
