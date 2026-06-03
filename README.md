# xauusd-trader

Commercial XAUUSD/gold trading-system research pipeline.

This repository is intentionally **baseline-first** and **data-quality-first**. It must not start with machine learning, paper orders, or live trading.

## Current phase

**Stage 0 — Data source decision**

Before writing any signal or model, the project must decide the initial data source:

1. REST/cloud feed for fast research and GitHub Actions collection.
2. MT5 broker feed for execution realism.
3. Futures reference data for institutional benchmarking.

No strategy code should be added until this decision is made.

## Core project rule

The first real objective is not profit.  
The first objective is to prove that the data is reliable enough to test a simple baseline.

## Development path

1. Data source decision.
2. Collector.
3. Data quality reports.
4. Baseline lab.
5. Regime ON/OFF model only if a baseline works.
6. Forward shadow only after baseline validation.
7. Paper-order only after forward shadow passes.
8. Live trading remains forbidden until paper-order passes.

## First definitions

- **XAUUSD**: gold priced in US dollars. In practical retail trading, it is usually traded as a CFD or broker symbol, not physical gold.
- **Baseline**: a simple trading rule used as the minimum benchmark. If an advanced method cannot beat it after costs, the advanced method is not worth using.
- **Forward shadow**: signal logging without placing orders. It tests whether signals work in real time before risking paper/live execution.
- **Paper-order**: simulated order execution. It is stricter than signal logging but still uses no real money.
- **Kill-switch**: a predefined stop condition that prevents wasting time on a weak path.

## Repository structure

```text
xauusd-trader/
├── app/                    # Python application modules
├── configs/                # Non-secret configuration files
├── data/
│   ├── raw/                # Raw collected candles/ticks
│   ├── normalized/         # Cleaned normalized datasets
│   ├── reports/            # Data quality and baseline reports
│   └── logs/               # Local runtime logs
├── docs/                   # Project rules and design notes
├── notebooks/              # Optional analysis notebooks
├── tests/                  # Tests
└── .github/workflows/      # GitHub Actions workflows
```

## Operating environment

Local repo:

```text
~/Desktop/xauusd-trader
```

Python command:

```text
python3
```

Do not rely on GitHub CLI (`gh`).  
Do not assume GitHub Actions cron timing is precise.

## Immediate next task

Decide the first data source. The recommended starting point is a REST/cloud data path for speed, while keeping MT5 as the later execution-realistic path.
