# XAUUSD Controlled-Paper Runbook — Execution-Ledger Parser Repair

## Defect repaired

The bounded coverage audit found the correct production file:

```text
reports/commercial_closure_sprint/commercial_closure_execution_ledger.csv
rows = 168
```

but did not derive the expected split of 146 evaluated rows and 22 missing-coverage rows.

The defect was unsafe status substring matching. `UNEVALUATED` contains `EVALUATED`; therefore positive-first matching could classify a missing row as evaluated.

## Repaired coverage contract

The canonical Commercial Closure ledger is a single 168-row file. The parser now proves:

```text
signals = 168
evaluated = 146
missing execution coverage = 22
```

Classification rules:

- negative status tokens are processed first;
- `research_gross_bps` alone never proves execution coverage;
- evaluated rows require consistent execution evidence such as `normal_net_bps`, or entry + exit + M5 gross values;
- missing rows may retain research fields and partial execution fields;
- contradictory full execution evidence plus a negative status blocks fail-closed;
- stale paths containing `invalid`, `archive`, `backup`, `old`, or `tmp` are ranked below the canonical ledger.

## Hard boundary

- Paper ledger only.
- No broker library or order call.
- No demo or live authorization.
- No retraining or threshold tuning.
- Stage180 remains the frozen inference producer.
- Missing spread, wrong DST mapping, source parity failure, stale source, unresolved historical coverage, incomplete entry bucket, or missing event context remains fail-closed.

## Unchanged trading contract

```text
candidate = logistic__direction_24h
threshold = 0.60
direction = LONG_ONLY
entry = open of aligned H1 row i+1
exit = close of aligned H1 row i+24
maximum notional/equity = 0.1570396406876166
maximum concurrent positions = 1
new positions per UTC day = 1
weekly loss pause = 2%
hard drawdown kill = 8%
normal cost floor = 3.0 bps
severe cost floor = 4.5 bps
entry spread guard = 3.0764778059487488 bps
```

## Installation over the current package

This overlay does not delete the controlled-paper SQLite ledger or existing reports.

```bash
cd ~/Downloads
mv XAUUSD_CONTROLLED_PAPER_EXECUTION_LEDGER_PARSER_REPAIR.zip \
  ~/Desktop/xauusd-trader/

cd ~/Desktop/xauusd-trader
rm -rf _incoming_xauusd_controlled_paper_ledger_parser_repair
mkdir -p _incoming_xauusd_controlled_paper_ledger_parser_repair

unzip -q XAUUSD_CONTROLLED_PAPER_EXECUTION_LEDGER_PARSER_REPAIR.zip \
  -d _incoming_xauusd_controlled_paper_ledger_parser_repair

rsync -a _incoming_xauusd_controlled_paper_ledger_parser_repair/ ./

rm -rf \
  _incoming_xauusd_controlled_paper_ledger_parser_repair \
  XAUUSD_CONTROLLED_PAPER_EXECUTION_LEDGER_PARSER_REPAIR.zip
```

## Local QA and preflight

```bash
cd ~/Desktop/xauusd-trader
python3 -m py_compile \
  app/xauusd_controlled_paper.py \
  tests/test_xauusd_controlled_paper.py

python3 -m unittest -v tests.test_xauusd_controlled_paper
python3 app/xauusd_controlled_paper.py preflight --root .
```

Expected test result:

```text
Ran 13 tests
OK
```

A successful preflight must contain:

```text
decision = PASS_CONTROLLED_PAPER_PREFLIGHT
missing_coverage_audit.decision = PASS_BOUNDED_MISSING_COVERAGE_NOT_CURRENT_SYSTEMATIC_DEFECT
missing_coverage_audit.source.mode = single_execution_ledger_status_and_fields
missing_coverage_audit.source.classification_counts.EVALUATED = 146
missing_coverage_audit.source.classification_counts.MISSING = 22
missing_coverage_audit.source.classification_counts.CONFLICT = 0
```

## Operational run

Only after preflight passes:

```bash
cd ~/Desktop/xauusd-trader
python3 app/xauusd_controlled_paper.py run --root .
```

The run is idempotent. A current Stage180 `NO_SIGNAL` observation is logged without opening a paper position.

## GitHub Actions QA

From GitHub UI run:

```text
Actions → XAUUSD Controlled Paper QA → Run workflow
```

The workflow compiles and runs tests on Python 3.13 and 3.14. It does not execute Stage180 or access local market data.

## Safe Git commands

After local preflight passes:

```bash
cd ~/Desktop/xauusd-trader
git add -A
git commit -m "Repair controlled-paper execution ledger parser"
git pull --rebase
git push
```
