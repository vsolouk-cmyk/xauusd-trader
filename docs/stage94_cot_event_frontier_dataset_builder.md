# Stage94 COT/Event Frontier Dataset Builder

Purpose: build normalized external frontier datasets before thesis discovery.

Stage93 found both COT and event-surprise frontiers not ready. Stage94 does not
run discovery. It scans local raw files, normalizes usable COT/event rows, writes
templates, and decides whether Stage95 discovery can proceed.

## Inputs

COT raw files can be placed in:

- `data/frontier_raw/cot/`
- `data/exogenous/`
- `data/cot/`
- `~/Downloads`

Accepted COT fields include common CFTC disaggregated columns:

- `report_date` or `report_date_as_yyyy_mm_dd`
- `m_money_positions_long_all`
- `m_money_positions_short_all`
- `open_interest_all`

Event-surprise raw files can be placed in:

- `data/frontier_raw/events/`
- `data/exogenous/`
- `data/events/`
- `~/Downloads`

Accepted event-surprise fields:

- event timestamp or date/time
- event name/type
- actual
- consensus / forecast / estimate

## Outputs

- `data/external_frontiers/cot_positioning_normalized.csv`
- `data/external_frontiers/event_surprise_normalized.csv`
- `reports/stage94_cot_event_frontier_dataset_builder/*`

## Lookahead controls

- COT `available_after_utc` is set after report date using a conservative release lag.
- COT z-scores use prior rows only.
- Event `available_after_utc` equals event release time.
- Event surprise z-scores use prior rows of the same event type only.

## Hard blocks

No order, no paper order, no broker connection, no EA/MT5 change.
