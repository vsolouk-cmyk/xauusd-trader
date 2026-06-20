# Stage58A Context-Aware Stage51 Regime Audit

This stage applies a bounded context/regime overlay to the existing Stage51 volatility-squeeze candidate family. It is a historical audit only and is not forward evidence.

## Purpose

Stage56 showed that broad price-action-only alternatives did not pass hard audit. Stage57A produced broker-derived context/regime tables. Stage58A uses those context regimes to test whether the only surviving price-action family, Stage51 volatility squeeze breakout, has a defensible regime-dependent profile.

## Guardrails

- No promotion.
- No EA.
- No paper-live.
- No live trading.
- No order submission.
- Historical context-audit results never count as true-forward evidence.
- If any context-aware candidate passes, it must get its own forward-shadow design before any paper-order simulation.

## Inputs

- `data/broker_normalized/amarkets_multitf.sqlite`
- `reports/stage48f/stage48f_cost_model.json`
- `reports/stage51_volatility_squeeze/stage51_volatility_squeeze_breakout_candidates.csv`
- `reports/stage57_context_precheck/stage57a_m15_context_regime_table.csv`
- `reports/stage57_context_precheck/stage57a_m5_context_regime_table.csv`

## Output

- `stage58a_context_aware_stage51_regime_audit_summary.json`
- `stage58a_context_aware_stage51_regime_audit_report.md`
- `stage58a_context_aware_stage51_regime_audit_candidates.csv`
- `stage58a_context_aware_stage51_regime_audit_event_sample.csv`
