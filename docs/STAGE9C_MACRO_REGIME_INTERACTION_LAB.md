# Stage 9C Macro Regime Interaction Lab

Stage 9C converts imported FRED numeric macro observations into daily macro regimes and tests interaction with the Stage 8B/8D technical candidate.

## What it uses

SQLite table:

```text
macro_numeric_observations
```

created by Stage 9B numeric update or GitHub artifact import.

Stage 8B trades:

```text
data/reports/stage8b_single_regime_thesis_lab/stage8b_single_regime_trades.csv
```

Optional Stage 8D signal CSV:

```text
XAUUSD_DryRun_v2_regime_shadow_signals.csv
```

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage9c_macro_regime_interaction_lab
cat data/reports/stage9c_macro_regime_interaction_lab/stage9c_macro_regime_interaction_lab.md
```

## Outputs

```text
data/reports/stage9c_macro_regime_interaction_lab/stage9c_macro_regime_interaction_lab.md
data/reports/stage9c_macro_regime_interaction_lab/stage9c_macro_daily_regimes.csv
data/reports/stage9c_macro_regime_interaction_lab/stage9c_stage8b_candidate_macro_summary.csv
data/reports/stage9c_macro_regime_interaction_lab/stage9c_stage8b_all_macro_summary.csv
data/reports/stage9c_macro_regime_interaction_lab/stage9c_stage8b_trades_macro_annotated.csv
data/reports/stage9c_macro_regime_interaction_lab/stage9c_stage8d_signals_macro_annotated.csv
```

It also writes/updates SQLite table:

```text
macro_daily_regime
```

## Numeric macro scoring

For long-gold bias:

```text
rising real yield  -> hostile
falling real yield -> supportive
strong USD         -> hostile
weak USD           -> supportive
oil spike          -> mixed/hostile through inflation/Fed pressure
deeply inverted yield curve -> mild growth-fear support
```

The daily score is intentionally simple and explainable. It is not a machine-learning model.

## Decision rule

If macro segmentation improves PF/median/DD without destroying trade count, Stage 9D can create a macro-aware forward-shadow report.

If macro only removes trades cosmetically, reject it as filter-mining.

## Hard rule

Research only. No EA change, no demo, no paper, no live authorization.
