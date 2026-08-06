# XAUUSD Successor Parallel Scan V1.2

Program: `XAUUSD_SUCCESSOR_PARALLEL_SCAN_V1_2_DYNAMIC_FEATURE_CONTRACT_REPAIR`

## Purpose

Evaluate a fixed, materially diverse set of deterministic XAUUSD H1 successor
formulations. Candidate selection is restricted to the pre-2025 reference
window. A family-diverse shortlist is frozen before one-time 2025+ holdout
assessment. This program has no paper, demo, MT5 order, broker, or live path.

## V1.2 repair

V1/V1.1 generated rolling features from a hard-coded window set
`24, 72, 120, 240`. The frozen candidate registry also contained London and New
York session breakout candidates using `range_window=12`, so the real run failed
with `KeyError: prior_high_12` before shortlist or holdout-lock creation.

V1.2 derives all return lags and rolling windows directly from the frozen
candidate registry. It validates the per-candidate feature contract before
candidate evaluation and records that contract in the shortlist and final
summary. The packaged full 19-candidate registry is covered by an end-to-end
regression test.

Candidate definitions, thresholds, costs, selection boundary, holdout boundary,
bootstrap settings, commercial gates, and the no-order contract are unchanged.

## Commands

```bash
python3 app/xauusd_successor_parallel_scan.py preflight --root .
python3 app/xauusd_successor_parallel_scan.py run --root .
python3 app/xauusd_successor_parallel_scan.py collect --root .
```

A real `run` writes `successor_holdout_access_lock.json` only after the
pre-2025 shortlist has been frozen and immediately before holdout metrics are
persisted. Do not delete or bypass a real holdout lock.
