# Stage105 Second-Order COT/Macro Thesis Discovery

## Purpose
Stage104 showed event-surprise discovery is blocked without paid historical consensus/estimate data. Stage105 continues thesis discovery using only already-available free/local datasets:

- lag-safe daily macro feature dataset
- official CFTC COT positioning dataset built in Stage95

## Scope
This is a discovery stage only. It searches second-order COT/macro interaction rules that are not direct event-surprise rules.

## What it scans
Examples:

- not-crowded COT + gold pullback + real-yield relief
- not-crowded COT + DXY weakness + gold pullback
- COT decrowding + central-bank support
- COT washout recovery + gold stabilization
- COT filter layered on known macro trend/resilience setups

## Outputs

- `stage105_second_order_cot_macro_thesis_discovery_summary.json`
- `stage105_second_order_cot_macro_thesis_discovery_report.md`
- `stage105_second_order_cot_macro_candidate_metrics.csv`
- `stage105_second_order_cot_macro_shortlist.csv`
- `stage105_second_order_cot_macro_entry_returns.csv`
- `stage105_second_order_cot_macro_joined_snapshot.csv`

## Hard blocks

- No automated order
- No paper order
- No broker connection
- No MT5/EA change
- No paper-live
- No live
- No order authorization
- No threshold tuning from this discovery stage

## Next stage logic
If shortlist is non-empty, route to Stage106 hard audit. If no shortlist, close this frontier and move to either observer validation drills or another free-data frontier.


## Stage105B loader fix
- Macro date aliases now include `date_utc`, `asof_date_utc`, `as_of_date`, `trading_date`, and `datetime` in addition to the original aliases.
- The loader error now prints the first available columns to speed schema diagnosis.
- No rule, threshold, gate, MT5, EA, order, broker, or observer behavior changed.
