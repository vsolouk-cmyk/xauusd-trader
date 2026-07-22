# XAUUSD Commercial Closure Sprint

## Purpose

This is the bounded bridge between the current frozen research survivor and a
controlled paper-order decision. It is not a new strategy scan and does not add
another numbered research stage.

The sprint:

1. reconstructs the exact Stage178 reference walk-forward trades;
2. fails closed if Stage178 parity is not exact;
3. combines those trades with the untouched 2025+ holdout ledger;
4. applies the frozen AMarkets EU-DST contract;
5. evaluates entry and exit on complete M5 buckets;
6. uses observed broker spread plus fixed normal/severe slippage;
7. measures multi-period stability and transfer degradation;
8. performs moving-block bootstrap uncertainty analysis;
9. creates a bounded paper risk contract;
10. emits one decision.

## Decisions

- `READY_FOR_CONTROLLED_PAPER_ORDERS`
- `KEEP_SHADOW_AND_START_PARALLEL_NEXT_METHOD_FAMILY`
- `KILL_CURRENT_COMMERCIAL_FORMULATION`

No demo or live order is authorized.

## Historical policy

The raw AMarkets files may begin in 2011. The commercial gate uses the
operationally validated AMarkets floor from the current PASS alignment
database. Earlier rows are retained but cannot change the commercial
decision until their timestamp regime receives a separate bounded audit.

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 app/commercial_closure_sprint.py
```

## Outputs

```text
reports/commercial_closure_sprint/commercial_closure_summary.json
reports/commercial_closure_sprint/commercial_closure_decision.md
reports/commercial_closure_sprint/commercial_closure_execution_ledger.csv
reports/commercial_closure_sprint/commercial_closure_period_metrics.csv
reports/commercial_closure_sprint/commercial_closure_cost_stress.csv
reports/commercial_closure_sprint/commercial_closure_bootstrap.json
reports/commercial_closure_sprint/commercial_closure_risk_contract.json
```
