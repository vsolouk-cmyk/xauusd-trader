# Stage91 Intraday Frontier Readiness Router

Purpose: after Stage89 exhausted residual macro-only thesis discovery, inspect local intraday data readiness before launching thesis-first intraday/session discovery.

This stage does not change MT5, EA files, observer CSVs, thresholds, or order permissions.

Expected outputs:

- `stage91_intraday_frontier_readiness_router_summary.json`
- `stage91_intraday_frontier_readiness_router_report.md`
- `stage91_intraday_file_inventory.csv`
- `stage91_intraday_db_inventory.csv`
- `stage91_intraday_thesis_queue.csv`
- `stage91_intraday_data_requirements.csv`

If the stage reports `INTRADAY_FRONTIER_READY_FOR_STAGE92`, the next step is a thesis-first Stage92 intraday/session residual discovery. If not, update AMarkets CSV/DB inputs first.
