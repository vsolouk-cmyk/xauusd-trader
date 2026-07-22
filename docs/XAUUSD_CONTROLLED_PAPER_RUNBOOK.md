# XAUUSD Controlled-Paper Runbook — Contract/Test-Isolation Repair

## Defects repaired

The first spread-source repair exposed two implementation defects:

1. the deliberately missing-CSV unit test retained production Downloads fallbacks, so it could read the user's real AMarkets M5 file and compare it with temporary 2015 fixture data;
2. the Stage177C contract gate used brittle raw-string equality and omitted the decision/semantic evidence from its failure payload.

Neither defect is a failure of the AMarkets data or Stage177C research contract.

## Hard boundary

- Paper ledger only.
- No broker library or order call.
- No demo or live authorization.
- No retraining or threshold tuning.
- Stage180 remains the sole frozen inference producer.
- Missing spread, wrong DST mapping, time-contract semantic mismatch, parity failure, stale source, incomplete entry bucket, or missing event context remains fail-closed.

## Stage177C spread-time contract

The repaired bridge requires all substantive fields below:

```text
contract = EU_DST_GMT_OFFSET_PAIR
dst_calendar = EU
standard_shift_minutes = -120
dst_shift_minutes = -180
shift_semantics = timestamp_utc = timestamp_naive + shift_minutes
selection_used_holdout = false
```

It additionally requires either:

```text
decision = PASS_AMARKETS_DST_AWARE_UTC_CONTRACT
```

or exact Stage177C identity in the same artifact. Contract, calendar and decision tokens are normalized only for harmless surrounding whitespace and case. Numeric shifts and semantics are not relaxed.

## Spread-source hierarchy

1. Use aligned M5 SQLite spread only if a real spread column exists.
2. Otherwise load the passed Stage177C contract.
3. Resolve the M5 CSV first from `source_amarkets_m5`, then Stage180 refresh sources, then configured Downloads paths.
4. Require `<DATE>`, `<TIME>`, `<OPEN>`, `<HIGH>`, `<LOW>`, `<CLOSE>`, and `<SPREAD>`.
5. Convert broker-naive timestamps using the locked EU DST mapping.
6. Require recent cadence, timestamp overlap, close parity and latest-source alignment against aligned M5.
7. At entry, require 12 aligned M5 rows and 12 valid spread rows in the exact H1 bucket.

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

## Installation over the existing package

This overlay does not delete the ledger or existing reports.

```bash
cd ~/Downloads
mv XAUUSD_CONTROLLED_PAPER_CONTRACT_TEST_ISOLATION_REPAIR.zip ~/Desktop/xauusd-trader/

cd ~/Desktop/xauusd-trader
rm -rf _incoming_xauusd_controlled_paper_contract_test_repair
mkdir -p _incoming_xauusd_controlled_paper_contract_test_repair
unzip -q XAUUSD_CONTROLLED_PAPER_CONTRACT_TEST_ISOLATION_REPAIR.zip \
  -d _incoming_xauusd_controlled_paper_contract_test_repair
rsync -a _incoming_xauusd_controlled_paper_contract_test_repair/ ./
rm -rf \
  _incoming_xauusd_controlled_paper_contract_test_repair \
  XAUUSD_CONTROLLED_PAPER_CONTRACT_TEST_ISOLATION_REPAIR.zip
```

## Local QA and preflight

```bash
cd ~/Desktop/xauusd-trader
python3 -m py_compile app/xauusd_controlled_paper.py tests/test_xauusd_controlled_paper.py
python3 -m unittest -v tests.test_xauusd_controlled_paper
python3 app/xauusd_controlled_paper.py preflight --root .
```

Expected tests:

```text
Ran 11 tests
OK
```

A successful preflight must include:

```text
PASS_CONTROLLED_PAPER_PREFLIGHT
PASS_BOUNDED_MISSING_COVERAGE_NOT_CURRENT_SYSTEMATIC_DEFECT
```

The preflight JSON should show:

```text
checks.spread_time_contract.pass = true
checks.spread_time_contract.evidence_route = CANONICAL_PASS_DECISION
checks.spread_time_contract.checks.contract = true
checks.spread_time_contract.checks.dst_calendar = true
checks.spread_time_contract.checks.standard_shift_minutes = true
checks.spread_time_contract.checks.dst_shift_minutes = true
checks.spread_time_contract.checks.shift_semantics = true
checks.spread_time_contract.checks.selection_no_holdout = true
checks.spread_source.kind = AMARKETS_M5_RAW_CSV_SPREAD
checks.spread_source.pass = true
```

## Operational run

After Stage180 refreshes the frozen observation:

```bash
cd ~/Desktop/xauusd-trader
python3 app/xauusd_controlled_paper.py run --root .
```

The command remains idempotent. A current `NO_SIGNAL` observation is logged without opening a position.

## GitHub Actions QA

From GitHub UI run:

```text
Actions → XAUUSD Controlled Paper QA → Run workflow
```

The workflow compiles and runs the regression suite on Python 3.13 and 3.14. It does not execute Stage180 or access the local ledger.

## Safe Git commands

After local preflight passes:

```bash
cd ~/Desktop/xauusd-trader
git add -A
git commit -m "Repair controlled-paper contract validation and test isolation"
git pull --rebase
git push
```
