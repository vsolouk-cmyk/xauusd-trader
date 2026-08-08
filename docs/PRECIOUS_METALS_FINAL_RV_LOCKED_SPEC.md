# Precious Metals Final RV — Locked Specification

## Purpose

This package performs exactly two sequential tasks:

1. a small clustered, causally-observable regime calibration add-on; and
2. if and only if that calibration passes, one pre-registered Gold–Silver dynamic relative-value test.

It is not a broad scan and contains no parameter grid.

## Scope change

The project is no longer required to remain strictly single-XAUUSD if a multi-asset or portfolio construction has materially stronger evidence. This package uses the smallest such expansion: a two-leg gold/silver relative-value trade. It does not authorize a broad commodity basket scan.

## External-mechanism basis

The economic/statistical mechanism is pairs/relative-value trading: estimate a long-run log-price relation, standardize the residual spread, and take the opposite side of large deviations. Recent gold/silver research also warns that the relationship is structurally unstable, so this test deliberately does **not** hard-code a 2017/2018 breakpoint discovered with hindsight. Instead it uses a rolling, past-only 252-day formation window.

## Locked strategy

- Data: synchronized AMarkets XAUUSD and XAGUSD H1, converted under the existing EU-DST contract.
- Daily construction: first and last synchronized H1 observation of each AMarkets/MT5 broker session date, preserving the locked EU-DST contract; UTC calendar-day grouping is explicitly avoided.
- Formation: 252 completed daily closes immediately preceding the decision date.
- Relation: `log(XAU) = alpha + beta * log(XAG)` by OLS.
- Spread: current `log(XAU) - alpha - beta*log(XAG)`.
- Z-score denominator: formation-window residual standard deviation.
- Entry: `|z| >= 2.0` at daily close.
- Direction: mean-reversion; positive z -> short spread, negative z -> long spread.
- Execution: next synchronized daily open.
- Gross-normalized fixed trade weights from the entry beta.
- Exit: first mean crossing of z=0, adverse |z| >= 4, or 60 trading days; execute next synchronized daily open.
- One open pair at a time.
- No cointegration p-value is used as a selection gate. AR(1), half-life, R2 and a simple DF t-stat are diagnostics only.
- No 2018 breakpoint, no regime threshold, no lookback selection, no z-grid, no stop-grid.

## Costs

The result reports gross, normal and severe returns. The locked commercial gate uses a conservative fixed two-leg severe round-trip cost of 16 bps on gross-normalized notional; normal is 8 bps. If gross is strong but only the severe fixed-cost assumption causes failure, that distinction remains visible for independent review rather than being hidden.

## Reference / diagnostic separation

- Reference entry interval: 2012-01-01 through 2024-12-31.
- A reference trade is valid only if its exit occurs before 2025-01-01.
- 2025+ is not simulated unless the full reference gate passes.
- No post-reference parameter change is allowed.

## Clustered regime calibration

The calibration uses four deterministic 30-trading-day clusters distributed across the reference period. Cluster placement is determined from timeline geometry, not returns. A synthetic regime flag is therefore observable before the simulated outcome.

Noise is block-resampled from empirical daily XAU-minus-XAG log-return differences. Two controls are run:

- Null: no planted edge; expected to fail the validator most of the time.
- Observable clustered edge: positive edge exists only inside the four observable clusters.

The RV strategy is not evaluated if this add-on indicates the concentration/regime validator cannot detect a strong clustered-but-observable edge.

## Reference gates

All must pass:

- >=25 independent pair trades;
- severe-cost mean > 0;
- PF >=1.20;
- moving-block bootstrap p10 mean > 0;
- remove-best-trade mean > 0;
- calendar-period annualized return >=2%;
- max drawdown <=25%;
- >=2/3 positive folds;
- worst fold annualized return >=-5%;
- >=45% positive years;
- largest positive year <=50% of positive-year profits;
- largest winning trade <=25% of all positive trade profits;
- actual severe mean ranks at or above the 90th percentile of a matched random-side control.

## Anti-loop contract

A failure closes this exact Gold–Silver formulation. It does not automatically authorize:

- changing formation length;
- changing z thresholds;
- hard-coding a structural break;
- adding macro/COT filters;
- converting to long-only;
- opening 2025+ for rescue;
- buying futures/options data;
- launching a broad commodity portfolio scan.

A broader diversified portfolio remains a managerial option because project scope now permits it, but it requires a separate evidence-based decision rather than automatic continuation.
