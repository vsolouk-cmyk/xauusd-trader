# Stage178 — Commercial Edge Decision Sprint

## Objective

This is a bounded commercial decision sprint, not another infrastructure or
open-ended research stage.

It answers one question:

> Does a fixed, controlled model produce a transferable net edge on extended
> XAUUSD history and an untouched AMarkets 2025+ holdout?

## Frozen scope

The stage evaluates exactly:

- two model classes: regularized logistic regression and one fixed histogram
  gradient-boosting model;
- four targets: 6h, 12h, 24h directional and a fixed 24h triple barrier;
- one fixed feature set;
- one fixed probability threshold;
- three purged walk-forward reference folds;
- one untouched AMarkets holdout beginning 2025-01-01;
- normal cost of 3.0 bps and severe cost of 4.5 bps.

There is no hyperparameter scan and no use of the AMarkets final holdout for
candidate selection.

## Inputs

```text
data/local/stage177b_extended_history/xauusd_extended_history.sqlite
data/local/stage177c_amarkets_alignment/xauusd_amarkets_alignment.sqlite
```

Reference table:

```text
dukascopy_h1_canonical
```

AMarkets table:

```text
amarkets_h1_from_m5_utc
```

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 app/stage178_commercial_edge_decision_sprint.py
```

The full run may take approximately 10–35 minutes on the user's 2015 MacBook,
depending on local BLAS performance.

## Outputs

```text
reports/stage178_commercial_edge_decision_sprint/stage178_summary.json
reports/stage178_commercial_edge_decision_sprint/stage178_decision.md
reports/stage178_commercial_edge_decision_sprint/stage178_candidate_metrics.csv
reports/stage178_commercial_edge_decision_sprint/stage178_fold_metrics.csv
reports/stage178_commercial_edge_decision_sprint/stage178_selected_holdout_trades.csv
reports/stage178_commercial_edge_decision_sprint/stage178_holdout_baselines.csv
reports/stage178_commercial_edge_decision_sprint/stage178_legacy_survivor_inventory.csv
```

Local model artifact:

```text
data/local/stage178_commercial_edge_decision_sprint/stage178_selected_model.pkl
```

The local model directory contains a `.gitignore` and is not committed.

## Possible decisions

```text
PROMOTE_TO_CONTROLLED_PAPER_DESIGN
RESEARCH_SURVIVOR_NEEDS_ONE_TARGETED_TEST
KILL_CURRENT_CANDIDATE_SET_AND_CHANGE_METHOD_FAMILY
```

A PROMOTE decision authorizes preparation of a controlled paper-design package
only. It does not authorize paper, demo, or live orders.

## Exit code

- `0`: PROMOTE or one targeted test remains.
- `2`: current candidate set is killed.

Reports are written in both cases.

## Anti-leakage controls

- Features at signal time use only candles at or before that time.
- Entry is the next H1 open.
- Training removes cost-dead-zone labels, but evaluation retains every resolved
  outcome, including neutral/small moves. This prevents conditioning trades on
  future move magnitude.
- Each fold applies an embargo equal to the target horizon.
- Candidate selection ends at 2024-12-31.
- The AMarkets 2025+ holdout is evaluated only after the candidate is frozen.
- The selected model must beat the simple 24h trend baseline in both reference
  walk-forward and final holdout mean net return.

## Dependency preflight

Stage178 no longer imports scikit-learn/joblib at module-import time. Run the
explicit preflight before the full sprint:

```bash
python3 app/stage178_commercial_edge_decision_sprint.py --check-dependencies
```

If the environment is incomplete:

```bash
python3 -m pip install --user -r requirements/stage178.txt
```

Unit tests remain importable when joblib is absent; the ML end-to-end test is
skipped in that environment rather than crashing the entire test loader.
