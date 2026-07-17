# Stage174B — MT5 H1 Schema Compatibility Bugfix

## Scope

This is an integration repair to Stage174, not a new research stage.

Stage174 successfully resolved:

- H64L holding horizon: 120 D1 rows;
- historical DXY contract: ICE DXY;
- Stage64K DXY fingerprint: exact numerical match.

Track A did not run because the Stage174 bar loader accepted normalized columns only and rejected the actual AMarkets MT5 export contract:

```text
<DATE> + <TIME> + <OPEN> + <HIGH> + <LOW> + <CLOSE>
```

Stage172 had already read the same AMarkets files with this schema. Stage174B restores that compatibility without changing the H64L rule, holding horizon, costs, gates, holdout, source contract, or time shift.

## Changes

- Accept MT5 `<DATE>` and `<TIME>` as one timestamp.
- Accept angle-bracket OHLC columns.
- Retain support for normalized direct timestamp columns.
- Validate OHLC invariants.
- Include actual input columns in schema errors.
- Classify a post-contract loader failure as an input/integration defect, not an unresolved contract.

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m unittest \
  tests/test_stage174_h64l_contract_resolution_and_track_a_final_audit.py

python3 app/stage174_h64l_contract_resolution_and_track_a_final_audit.py \
  --root ~/Desktop/xauusd-trader \
  --config configs/stage174_h64l_contract_resolution_and_track_a_final_audit.json
```

## Required outputs

Send back:

```text
stage174_summary.json
stage174_decision.md
stage174_h64l_episodes.csv                  # if generated
stage174_simple_trend_baseline_episodes.csv  # if generated
```

No order, paper-order, demo, live, ML, Track B rerun, COT scan, or broad scan is authorized.
