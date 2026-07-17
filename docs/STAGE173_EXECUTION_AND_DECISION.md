# Stage173 — H64L Source Reconciliation and Prior-Thesis Delta Gate

## Purpose

Stage173 is a narrow correction and decision package. It does not search for new alpha.

It performs four linked tasks:

1. repairs the WGC ETF semantic mapping used by the Stage171H forward materializer;
2. reconciles the WGC global holdings total against the sum of fund-level holdings;
3. searches original Stage64/Stage66 artifacts for the actual ETF, DXY and holding-horizon contracts;
4. prevents another generic rerun of already failed technical/COT families without a written material difference.

It also corrects the Stage172 governance error: a missing historical-as-of input is `INCONCLUSIVE_BLOCKED`, not `KILL`.

## What changes

The package replaces:

```text
app/stage171h_h64l_forward_feature_materializer.py
app/stage172_dual_track_decision_audit.py
configs/stage172_dual_track_decision_audit.json
```

It adds:

```text
app/stage173_h64l_source_reconciliation_and_thesis_gate.py
configs/stage173_h64l_source_reconciliation_and_thesis_gate.json
tests/test_stage173_h64l_source_reconciliation_and_thesis_gate.py
```

## ETF correction

The old Stage171H parser trusted the ambiguous spreadsheet heading:

```text
All units in tonnes unless otherwise specified
```

In the WGC `Holdings by month` sheet, that normalized column is the gold-price series, not the global ETF holdings total. Stage173 does not hard-code that heading as holdings.

Instead it:

1. sums all fund-level holdings columns for each month;
2. scores all candidate total columns against that fund sum;
3. accepts a total only if median relative error is at most 2% and 90th-percentile error is at most 5%;
4. applies level and three-month-change plausibility checks;
5. checks official 2026 anchors;
6. writes a canonical holdings series.

Canonical output:

```text
data/macro_regime/normalized/wgc_global_etf_holdings_monthly_stage173.csv
```

Stage171H will prefer this canonical series on later forward runs.

## Historical comparison

If this file exists:

```text
data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv
```

Stage173 compares its historical `etf_flow_tonnes_3m` against the reconciled WGC series using historical-as-of availability. The result is evidence about the historical pipeline; it does not assume that the current Stage171H bug existed in Stage64R.

## DXY and horizon archaeology

Stage173 scans only project artifacts with Stage64/Stage66/H64L-lock paths for:

- `DTWEXBGS` versus ICE DXY/direct DXY evidence;
- ETF source/column evidence;
- explicit `holding_days`, `hold_days`, or horizon-day declarations.

Current scripts that merely discuss Stage64R are not treated as original evidence.

## Prior-thesis gate

The output matrix records the prior status of:

- HTF trend plus intraday pullback;
- London/NY range breakout or continuation;
- volatility expansion with guards;
- COT positioning;
- `high_sweep_continuation_long` with the proposed H4/regime difference.

No family is authorized for another test merely because it has a new stage number or a renamed rule.

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m unittest \
  tests/test_stage173_h64l_source_reconciliation_and_thesis_gate.py

python3 app/stage173_h64l_source_reconciliation_and_thesis_gate.py \
  --root ~/Desktop/xauusd-trader \
  --config configs/stage173_h64l_source_reconciliation_and_thesis_gate.json
```

## Primary outputs

```text
reports/stage173_h64l_source_reconciliation_and_thesis_gate/stage173_summary.json
reports/stage173_h64l_source_reconciliation_and_thesis_gate/stage173_decision.md
reports/stage173_h64l_source_reconciliation_and_thesis_gate/stage173_h64l_archaeology_evidence.csv
reports/stage173_h64l_source_reconciliation_and_thesis_gate/stage172_governance_correction.json
reports/stage173_h64l_source_reconciliation_and_thesis_gate/stage172_governance_correction.md
reports/stage173_h64l_source_reconciliation_and_thesis_gate/stage173_prior_thesis_delta_matrix.csv
```

## Decision meanings

```text
BLOCK_H64L_ETF_RECONCILIATION_FAILED_KEEP_ALL_EXECUTION_FORBIDDEN
```

The WGC source could not be semantically reconciled. Do not run H64L Track A.

```text
H64L_ETF_FIXED_BLOCK_TRACK_A_PENDING_DXY_ARCHAEOLOGY_NO_NEW_SCAN
```

ETF semantics pass, but the original DXY contract remains unresolved.

```text
H64L_SOURCES_PARTLY_RESOLVED_BLOCK_TRACK_A_PENDING_HORIZON_CONTRACT_NO_NEW_SCAN
```

ETF/DXY evidence is adequate but the original holding horizon is not uniquely established.

```text
READY_TO_BUILD_VALIDATED_H64L_HISTORICAL_ASOF_TABLE_AND_RERUN_TRACK_A_ONLY
```

The required contracts are sufficiently recovered. The next action is only the validated H64L historical-as-of build and Track A rerun—not a technical or COT scan.

## Hard controls

- No orders, demo, paper-order or live.
- No ML.
- No broad scan.
- No threshold optimization.
- No generic COT Track C.
- Stage172's exact tested technical formulations remain killed.
