# Stage111 Macro/Flow Absorption Frontier Discovery

## Decision context

Stage110 closed as an operational checkpoint with Stage109 as the current daily runner and the 7-rule unified observer as the active observer-only bridge. Stage111 does not alter the observer, EA, or order path.

## Selected next thesis

The next thesis is **macro/flow absorption**:

> When gold is under pullback or macro headwind, but institutional flow support is visible through ETF flow, central-bank demand, and non-crowded or decrowding COT positioning, the market may be absorbing supply before a 120-trading-day long continuation/reversal window.

This is deliberately different from simply waiting for DXY or real-yield relief. The existing 7-rule observer already covers DXY relief, real-yield relief, central-bank support, COT decrowding, and some gold-vs-DXY resilience. Stage111 tests whether **flow support during pullback/headwind** adds incremental, non-overlapping candidates.

## Method

- Load the lag-safe full-scope macro dataset:
  `data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv`
- Join COT by `available_after_utc` using backward as-of merge when needed:
  `data/external_frontiers/cot_positioning_normalized.csv`
- Build H120 long-only net outcome after a configurable cost.
- Generate candidate rules from the selected thesis.
- Evaluate train / validation / tail-forward historical segments.
- Run historical-as-of forward-year checks.
- Compare overlap against the current 7-rule observer.
- Export only candidates that pass gate to `stage111_selected_for_stage112.csv`.

## Hard blocks

- No automated order.
- No paper order.
- No broker connection.
- No MT5/EA change from Stage111.
- No paper-live.
- No live.
- No order authorization from Stage111.

## Run

```bash
cd /Users/vahid/Desktop/xauusd-trader
python3 app/stage111_macro_flow_absorption_frontier_discovery.py \
  --root /Users/vahid/Desktop/xauusd-trader \
  --config configs/stage111_macro_flow_absorption_frontier_discovery.json \
  --out reports/stage111_macro_flow_absorption_frontier_discovery
```

## Main outputs

```text
reports/stage111_macro_flow_absorption_frontier_discovery/stage111_macro_flow_absorption_frontier_discovery_summary.json
reports/stage111_macro_flow_absorption_frontier_discovery/stage111_macro_flow_absorption_frontier_discovery_report.md
reports/stage111_macro_flow_absorption_frontier_discovery/stage111_candidate_metrics.csv
reports/stage111_macro_flow_absorption_frontier_discovery/stage111_selected_for_stage112.csv
reports/stage111_macro_flow_absorption_frontier_discovery/stage111_review_queue.csv
reports/stage111_macro_flow_absorption_frontier_discovery/stage111_asof_forward_checks.csv
reports/stage111_macro_flow_absorption_frontier_discovery/stage111_overlap_matrix.csv
```

## Interpretation

If `stage111_selected_for_stage112.csv` is empty, the 7-rule observer remains unchanged and the next thesis should be scanned. If it contains rows, those rows are not promoted to order; they are candidates for Stage112 observer review / combo expansion only.
