# Stage90 Data Frontier Thesis Router

## Purpose

Stage89 found no additional residual macro-only thesis shortlist after the unified 5-rule observer portfolio. Stage90 therefore routes the next thesis-discovery step toward new data frontiers instead of recombining the same daily macro features.

## Frontiers checked

- `INTRADAY_SESSION`: broker M1/M5/H1 bars, spread/cost history, session structure.
- `COT_POSITIONING`: local COT/CFTC files and lag-safe positioning features.
- `EVENT_SURPRISE`: economic calendar plus actual/forecast/surprise fields.
- `FLOW_REFINEMENT`: ETF/central-bank decomposition beyond current aggregate macro columns.

## Outputs

- `stage90_data_frontier_thesis_router_summary.json`
- `stage90_data_frontier_thesis_router_report.md`
- `stage90_frontier_readiness.csv`
- `stage90_data_requirements.csv`
- `stage90_thesis_queue.csv`
- `stage90_data_inventory.json`

## Hard blocks

Stage90 cannot authorize orders, broker connection, EA promotion, MT5 changes, live/paper-live, or threshold tuning.
