# Stage36B — Session / Regime Baseline Scout

Purpose: start a distinct thesis branch while Stage35C waits for h13/h14 forward confirmation.

This stage evaluates London / NY / late-NY continuation and reversal baselines with ATR-normalized TP/SL and cost stress. It is not a continuation of the Stage33-35 h13/h14 variant branch.

It reads OHLC data from the local SQLite store, automatically detects an OHLC table, prefers H1 candles, and can resample lower-timeframe candles to H1 if needed.

Outputs are written to:

- `data/reports/stage36b_session_regime_baseline_scout/stage36b_session_regime_baseline_scout.md`
- `data/reports/stage36b_session_regime_baseline_scout/stage36b_summary.json`
- `data/reports/stage36b_session_regime_baseline_scout/stage36b_data_source_audit.csv`
- `data/reports/stage36b_session_regime_baseline_scout/stage36b_session_regime_candidate_summary.csv`
- `data/reports/stage36b_session_regime_baseline_scout/stage36b_strict_review_queue.csv`
- `data/reports/stage36b_session_regime_baseline_scout/stage36b_background_queue.csv`
- `data/reports/stage36b_session_regime_baseline_scout/stage36b_kill_or_repair_queue.csv`

Possible decisions:

- `STAGE36B_HAS_SESSION_REGIME_STRICT_REVIEW_CANDIDATE_RESEARCH_ONLY`
- `STAGE36B_SESSION_REGIME_BACKGROUND_ACCELERATION_ONLY_RESEARCH_ONLY`
- `STAGE36B_NO_SESSION_REGIME_EDGE_RESEARCH_ONLY`
- `STAGE36B_NO_OHLC_DATA_AVAILABLE_RESEARCH_ONLY`
- `STAGE36B_INSUFFICIENT_H1_HISTORY_RESEARCH_ONLY`

No EA, paper-live, or order transition is authorized by this stage.
