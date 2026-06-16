# Stage 8A Regime Discovery Lab

Stage 8A is a regime/opportunity discovery lab, not a trading strategy.

It should be used after Stage 7D if all entry/exit geometries fail.

## What it does

It probes the forward distribution of XAUUSD from broker-feed H1/M1 data and groups results by:

- session
- year
- H1 trend
- H4 trend
- volatility bucket
- compression bucket
- impulse/shock candle state
- macro bucket

For each group, it evaluates both long and short forward behavior over 3h, 6h, and 12h.

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage8a_regime_discovery_lab
cat data/reports/stage8a_regime_discovery_lab/stage8a_regime_discovery_lab.md
```

## Run with geopolitical shock window

```bash
python3 -m app.stage8a_regime_discovery_lab \
  --shock-window 2026-06-08T00:00:00Z,2026-06-10T23:59:00Z,iran_israel_shock

cat data/reports/stage8a_regime_discovery_lab/stage8a_regime_discovery_lab.md
```

## Outputs

```text
data/reports/stage8a_regime_discovery_lab/stage8a_regime_discovery_lab.md
data/reports/stage8a_regime_discovery_lab/stage8a_regime_summaries.csv
data/reports/stage8a_regime_discovery_lab/stage8a_regime_probes.csv
data/reports/stage8a_regime_discovery_lab/stage8a_regime_discovery_lab.json
```

## Important

- This is not a strategy.
- It does not create EA changes.
- It does not authorize demo/paper/live.
- If no promising regimes appear, pause mechanical price-only development.
