# XAUUSD Stage 2A Baseline Lab

- Generated at UTC: `2026-06-04T06:11:27.541461+00:00`
- Overall decision: `candidate_baseline_found`
- Decision reason: `At least one simple baseline passed sample and net-cost filters.`

## Important limitation

This is not a trading approval. This is an early diagnostic baseline lab.
Twelve Data does not provide broker bid/ask spread in this pipeline, so costs are assumed conservatively.

## Cost model

- `assumed_spread_usd`: `0.3`
- `assumed_slippage_usd`: `0.05`
- `total_roundtrip_cost_usd`: `0.35`
- `effective_roundtrip_cost_usd`: `0.35`
- `cost_warning`: `Spread is assumed because Twelve Data does not provide broker bid/ask spread in this pipeline.`

## Baseline metrics

| Baseline | Trades | Sample OK | Candidate | Reason | Win rate | Avg net USD | Total net USD | Max DD USD |
|---|---:|---:|---:|---|---:|---:|---:|---:|
| asia_range_breakout_5min | 1 | False | False | insufficient_trades | 1.000 | 12.1308 | 12.1308 | 0.0000 |
| atr_range_expansion_15min | 60 | True | False | negative_or_zero_avg_net_usd | 0.500 | -0.1994 | -11.9622 | -82.8853 |
| higher_timeframe_sma20_trend | 478 | True | True | candidate | 0.366 | 0.8826 | 421.8871 | -452.4734 |
| london_open_breakout_5min | 1 | False | False | insufficient_trades | 1.000 | 3.7417 | 3.7417 | 0.0000 |
| session_momentum_15min | 300 | True | False | negative_or_zero_avg_net_usd | 0.280 | -0.7331 | -219.9254 | -265.7106 |

## Data files used

- `15min`: `data/normalized/normalized_twelvedata_XAU_USD_15min_20260604T060247Z.csv`
- `1h`: `data/normalized/normalized_twelvedata_XAU_USD_1h_20260604T060251Z.csv`
- `5min`: `data/normalized/normalized_twelvedata_XAU_USD_5min_20260604T060243Z.csv`

