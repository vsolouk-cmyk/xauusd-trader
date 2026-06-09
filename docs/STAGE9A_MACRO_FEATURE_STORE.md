# Stage 9A Macro/Fundamental Feature Store

Stage 9A adds a structured macro/fundamental layer to the XAUUSD research system.

It is not a news scraper and not an AI sentiment toy. It starts with curated, testable macro events.

## Why this exists

The Stage 8D technical candidate is only a technical forward-shadow candidate. Gold also reacts to:

- CPI / PPI / NFP
- FOMC and Fed communication
- real-yield pressure
- USD pressure
- oil/inflation pressure
- geopolitical shock
- risk-off/risk-on flows
- central-bank/physical-demand regimes

Stage 9A stores these events as features and annotates technical candidates with macro regimes.

## Setup

```bash
cd ~/Desktop/xauusd-trader
cp data/config/stage9a_macro_events_template.csv data/config/stage9a_macro_events.csv
```

Then edit:

```text
data/config/stage9a_macro_events.csv
```

Delete the `EXAMPLE_DELETE_ME` row and enter real events.

## Score model

For long-gold bias:

```text
score = event_gold_bias
      + safe_haven_score
      + growth_fear_score
      + central_bank_demand_score
      - real_yield_pressure
      - usd_pressure
      - oil_inflation_pressure
```

Regime labels:

```text
score >= +2      supportive
score <= -2      hostile
abs(score)>=.75  mixed
otherwise        neutral
```

If `mode=block`, the H1 context becomes `event_risk_*`.

## Practical scoring examples

### Hawkish CPI surprise

```text
real_yield_pressure = +2
usd_pressure = +1
event_gold_bias = -1
```

Usually hostile to long gold.

### Geopolitical safe-haven shock without rates pressure

```text
safe_haven_score = +2
event_gold_bias = +1
real_yield_pressure = 0
usd_pressure = 0
```

Usually supportive to long gold.

### Oil shock that raises inflation/Fed pressure

```text
safe_haven_score = +1
oil_inflation_pressure = +2
real_yield_pressure = +1
```

Mixed or hostile depending on market interpretation.

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage9a_macro_feature_store
cat data/reports/stage9a_macro_feature_store/stage9a_macro_feature_store.md
```

## Outputs

```text
data/reports/stage9a_macro_feature_store/stage9a_macro_feature_store.md
data/reports/stage9a_macro_feature_store/stage9a_macro_events_loaded.csv
data/reports/stage9a_macro_feature_store/stage9a_macro_context_h1.csv
data/reports/stage9a_macro_feature_store/stage9a_stage8b_macro_summary.csv
data/reports/stage9a_macro_feature_store/stage9a_stage8b_trades_annotated.csv
data/reports/stage9a_macro_feature_store/stage9a_stage8d_signals_annotated.csv
```

It also creates/updates local SQLite tables:

```text
macro_events
macro_context_h1
```

These live inside:

```text
data/local/xauusd_local_store.sqlite
```

Do not push the SQLite database.

## Hard rule

Research only. No EA change, no demo, no paper, no live authorization.
