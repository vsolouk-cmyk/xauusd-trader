# Stage 10A Event / News Impact Lab

Stage 10A is the first serious news-evaluation layer.

It does not classify news by opinion alone. It measures how XAUUSD actually reacted after curated events.

## Why this matters

Waiting for rare v2 technical signals is too slow for product development. Stage 10A lets us work on the macro/news edge in parallel.

## Event taxonomy

Recommended `event_class` values:

```text
cpi_surprise
ppi_surprise
nfp_surprise
unemployment_surprise
fomc_statement
fed_speech_hawkish
fed_speech_dovish
real_yield_shock
usd_shock
oil_supply_shock
geopolitical_escalation
geopolitical_deescalation
ceasefire_or_truce
sanctions
central_bank_gold_demand
etf_flow
physical_demand
```

Recommended `event_channel` values:

```text
real_yield_fed_path
usd_pressure
oil_inflation_pressure
safe_haven
growth_fear
physical_demand
central_bank_demand
mixed_macro
```

`expected_gold_direction`:

```text
+1 = initially expected to support gold
-1 = initially expected to pressure gold
 0 = direction unknown / impact-only event
```

## Install template

```bash
cd ~/Desktop/xauusd-trader
cp data/config/stage10a_news_events_template.csv data/config/stage10a_news_events.csv
```

Then edit:

```text
data/config/stage10a_news_events.csv
```

Delete the example row and enter real events.

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage10a_event_impact_lab
cat data/reports/stage10a_event_impact_lab/stage10a_event_impact_lab.md
```

## Outputs

```text
data/reports/stage10a_event_impact_lab/stage10a_event_impact_lab.md
data/reports/stage10a_event_impact_lab/stage10a_events_annotated.csv
data/reports/stage10a_event_impact_lab/stage10a_event_class_weights.csv
data/reports/stage10a_event_impact_lab/stage10a_event_impact_lab.json
```

SQLite tables:

```text
news_events
news_event_reactions
news_event_class_weights
```

## How impact is measured

For each event:

```text
anchor = first H1 bar at or after event_time_utc
ret_1h / ret_4h / ret_12h / ret_24h = close_at_horizon - anchor_open
mfe_12h = max high in 12h window - anchor_open
mae_12h = min low in 12h window - anchor_open
normalized_impact = abs move / rolling median absolute H1 move
```

Impact bucket:

```text
normalized_impact_12h >= 4.0  high_impact
>= 2.0                         medium_impact
>= 0.75                        low_impact
else                           noisy_or_no_impact
```

## Adaptive weight

The lab builds event-class weights from:

```text
sample size
normalized impact
direction accuracy
initial confidence
initial importance
```

Small samples are capped, so one dramatic event cannot dominate the system.

## Hard rule

Research only. No EA change, no automatic news trading, no paper/live authorization.
