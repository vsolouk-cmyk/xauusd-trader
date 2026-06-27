# Stage83 Orthogonal Thesis Discovery Expansion

Stage83 continues thesis-first discovery after Stage82 kept the current Stage77B observer portfolio unchanged.

## Why this stage exists

Stage82 showed that the hard-audited Stage81B survivors were strong on standalone return metrics but had too much overlap with the current K06/K03/K07 portfolio. Stage83 therefore does **not** loosen the overlap gate. It searches for lower-overlap candidates using pullback, flow-against-headwind, central-bank-against-headwind, benign pullback, and longer-lookback orthogonal macro families.

## Inputs

- `data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv`
- Current portfolio reference:
  - `K06_RESILIENT_GOLD_VS_DXY_H120`
  - `K03_SAFE_HAVEN_REALYIELD_H120`
  - `K07_DXY_TREND_RELIEF_GOLD_TREND_H120`

## Outputs

- `stage83_orthogonal_thesis_discovery_expansion_summary.json`
- `stage83_orthogonal_thesis_discovery_expansion_report.md`
- `stage83_orthogonal_discovery_candidate_metrics.csv`
- `stage83_orthogonal_discovery_shortlist.csv`
- `stage83_orthogonal_discovery_entry_returns.csv`
- `stage83_orthogonal_missing_data_requirements.csv`

## Hard blocks

- No automated order
- No paper order
- No broker connection
- No EA promotion
- No paper-live/live
- No direct MT5/EA change
- No threshold tuning from this stage

## Interpretation

If Stage83 produces a shortlist, run Stage84 hard audit. If it produces no shortlist, keep the Stage77B portfolio and consider adding missing data families such as COT, event surprise, or intraday session/liquidity instead of loosening gates.
