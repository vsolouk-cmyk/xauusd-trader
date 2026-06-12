# Stage25A Regime / No-Trade Filter Discovery

## Purpose

Stage24X concluded that repeated Stage24 no-promotion results are mostly explained by cost sensitivity and design limitations, not by proof of an execution-engine failure. The recommended next action is to stop widening entry-pattern grids and test regime/no-trade filters.

Stage25A is therefore a diagnostic module, not a trading module.

## Scope

- Research/shadow diagnostic only.
- Does not modify Stage18A v2.
- Does not modify Stage23D.
- Does not authorize EA, paper, live, or orders.
- Tests filters on already exact-replayed Stage23C trades.

## Inputs

Primary:

```text
data/reports/stage23c_promotion_candidate_validation/stage23c_exact_trades.csv
```

Candles:

```text
~/Downloads/amarkets_xauusd_1m.csv
```

Fallback candle paths:

```text
data/local/amarkets_xauusd_1m.csv
data/amarkets_xauusd_1m.csv
```

## Output

```text
data/reports/stage25a_regime_filter_discovery/stage25a_regime_filter_discovery.md
data/reports/stage25a_regime_filter_discovery/stage25a_regime_filter_discovery.json
data/reports/stage25a_regime_filter_discovery/stage25a_filter_candidates.csv
data/reports/stage25a_regime_filter_discovery/stage25a_enriched_stage23c_trades.csv
```

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage25a_regime_filter_discovery
cat data/reports/stage25a_regime_filter_discovery/stage25a_regime_filter_discovery.md
```

## Interpretation rules

- `STAGE25A_HAS_PROMOTION_REVIEW_FILTER_RESEARCH_ONLY` means a filter deserves separate forward-shadow tracking.
- It does not mean the filter can be added to Stage18A.
- It does not authorize paper/live/order behavior.
- Year-based filters are diagnostic only and must not be deployed.
