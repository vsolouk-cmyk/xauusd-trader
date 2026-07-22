# XAUUSD Controlled-Paper Runbook

## Commercial purpose

Move the frozen Stage178 survivor into an auditable, controlled paper process without reopening discovery, changing the model, or authorizing broker execution.

## Hard boundary

- Paper ledger only.
- No broker library.
- No MT5 trade call.
- No demo or live authorization.
- No retraining or threshold tuning.
- Stage180 remains the sole frozen inference producer and continues in parallel.

## How the package works

1. It locates the latest Stage180 summary and verifies that Stage180 is observation-only.
2. It verifies SHA-256 hashes of the frozen Stage178 model and contract.
3. It validates the corrected commercial-closure summary and the locked risk contract.
4. It introspects the aligned SQLite database and detects H1/M5 tables by schema and cadence.
5. It audits the 168 historical signals and classifies the 22 missing execution rows by date and coverage reason.
6. Only after that bounded audit passes, it ingests the latest frozen Stage180 observation.
7. A qualifying long signal is logged as a paper intent. Entry and exit are derived by exact H1 row position, never wall-clock arithmetic.
8. Spread, event, concurrency, daily-cap, weekly-loss, and drawdown guards can block the intent. Missing required event context fails closed.
9. Resolved positions receive normal, severe, 8-bps, and 10-bps P&L measures.

## Locked controls

- Candidate: `logistic__direction_24h`
- Threshold: `0.60`
- Maximum notional/equity: `0.1570396406876166`
- Maximum concurrent positions: `1`
- New positions per UTC day: `1`
- Weekly loss pause: `2%`
- Hard drawdown kill: `8%`
- Normal cost floor: `3.0 bps`
- Severe cost floor: `4.5 bps`
- Entry spread guard: `3.0764778059487488 bps`

## Required local inputs

The existing repo must contain:

- `reports/**/stage180_summary.json`
- `reports/**/commercial_closure_summary.json`
- `reports/**/commercial_closure_risk_contract.json`
- the commercial-closure signal/execution CSV source used to establish `168 / 146 / 22`;
- `data/local/stage177c_amarkets_alignment/xauusd_amarkets_alignment.sqlite`
- `data/local/stage178_commercial_edge_decision_sprint/stage178_selected_model.pkl`
- `data/local/stage178_commercial_edge_decision_sprint/stage178_selected_model_contract.json`
- event context in `data/local/xauusd_local_store.sqlite::macro_context_h1`, or populated rows in `data/controlled_paper/event_blackout.csv`.

Absence or mismatch is blocking. There is no bypass flag.

## Installation

Run these commands after downloading the ZIP:

```bash
cd ~/Downloads
mv XAUUSD_CONTROLLED_PAPER_INTEGRATED_PACKAGE.zip ~/Desktop/xauusd-trader/

cd ~/Desktop/xauusd-trader
rm -rf _incoming_xauusd_controlled_paper
mkdir -p _incoming_xauusd_controlled_paper
unzip -q XAUUSD_CONTROLLED_PAPER_INTEGRATED_PACKAGE.zip -d _incoming_xauusd_controlled_paper
rsync -a _incoming_xauusd_controlled_paper/ ./
rm -rf _incoming_xauusd_controlled_paper XAUUSD_CONTROLLED_PAPER_INTEGRATED_PACKAGE.zip
```

## Local QA and preflight

```bash
cd ~/Desktop/xauusd-trader
python3 -m py_compile app/xauusd_controlled_paper.py tests/test_xauusd_controlled_paper.py
python3 -m unittest -v tests.test_xauusd_controlled_paper
python3 app/xauusd_controlled_paper.py preflight --root .
```

A successful preflight ends with:

```text
PASS_CONTROLLED_PAPER_PREFLIGHT
PASS_BOUNDED_MISSING_COVERAGE_NOT_CURRENT_SYSTEMATIC_DEFECT
```

A blocked preflight writes:

```text
reports/xauusd_controlled_paper/controlled_paper_failure.json
reports/xauusd_controlled_paper/missing_coverage_audit_summary.json
reports/xauusd_controlled_paper/missing_coverage_audit.csv
```

## Operational run

First run the existing Stage180 frozen-shadow routine exactly as currently configured. Then run:

```bash
cd ~/Desktop/xauusd-trader
python3 app/xauusd_controlled_paper.py run --root .
```

The command is idempotent. Reprocessing the same Stage180 observation does not duplicate a signal or position.

## Outputs

SQLite ledger:

```text
data/controlled_paper/xauusd_controlled_paper.sqlite
```

Human- and machine-readable reports:

```text
reports/xauusd_controlled_paper/controlled_paper_preflight.json
reports/xauusd_controlled_paper/controlled_paper_summary.json
reports/xauusd_controlled_paper/controlled_paper_decision.md
reports/xauusd_controlled_paper/missing_coverage_audit.csv
reports/xauusd_controlled_paper/missing_coverage_audit_summary.json
reports/xauusd_controlled_paper/signals.csv
reports/xauusd_controlled_paper/blocked_signals.csv
reports/xauusd_controlled_paper/pending_positions.csv
reports/xauusd_controlled_paper/resolved_positions.csv
reports/xauusd_controlled_paper/all_positions.csv
reports/xauusd_controlled_paper/risk_state.json
```

## GitHub Actions QA

From GitHub UI run:

```text
Actions → XAUUSD Controlled Paper QA → Run workflow
```

This workflow only compiles and tests the package on Python 3.13 and 3.14. It does not run Stage180 and does not operate the local paper ledger.

## Safe Git commands

After local preflight passes:

```bash
cd ~/Desktop/xauusd-trader
git add -A
git commit -m "Add integrated XAUUSD controlled-paper logger"
git pull --rebase
git push
```
