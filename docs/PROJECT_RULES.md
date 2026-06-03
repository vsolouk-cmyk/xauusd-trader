# XAUUSD Project Rules

This project exists to build a commercially usable XAUUSD/gold trading system, not to run open-ended research.

## Non-negotiable rules

1. Baseline-first.
2. Data-quality-first.
3. No ML before simple baselines are tested.
4. No forward shadow before baseline validation.
5. No paper-order before forward shadow passes.
6. No live trading before paper-order passes.
7. Every phase needs a kill-switch.
8. Stop weak paths quickly.

## Development rules

- Minimize back-and-forth.
- Prefer ready-to-copy files.
- Do not wait for confirmation when the next technical step is clear.
- Do not provide bash install scripts.
- Use safe Git commands only.
- Do not rely on `gh` CLI.
- Include workflow files whenever workflow behavior changes.
- Always state which workflow to run from GitHub UI when workflows are added or changed.

## Environment

- Local repo: `~/Desktop/xauusd-trader`
- Downloads path: `~/Downloads`
- Local Python command: `python3`
- Machine: 2015 MacBook
- Execution style: terminal-based
- Remote automation: GitHub Actions

## Trading-system discipline

The project must not copy the previous crypto microstructure path.

XAUUSD must be built around:

- data quality,
- session awareness,
- spread/cost realism,
- simple baselines,
- strict forward testing,
- careful ON/OFF filtering only after baselines work.

## First-use glossary

- **Session**: a major trading time window such as Asia, London, New York, or London-New York overlap. XAUUSD behavior can differ strongly by session.
- **Spread**: the difference between buy and sell prices. It is a direct trading cost.
- **Slippage**: the difference between expected entry/exit price and actual filled price.
- **Regime**: the current market condition, such as trending, ranging, high volatility, or news-driven.
- **ON/OFF model**: a model that decides whether a baseline strategy should be active or inactive. It does not directly predict price as the first objective.
