# Source and Design Rationale

## External sources used to lock the mechanism

1. Engle & Granger cointegration framework: long-run relations can be represented by a stationary linear combination of non-stationary series. The package uses this idea only as the mechanism basis; it does not use an in-sample cointegration p-value as a trade-selection gate.

2. Pairs-trading diffusion literature: a common spread representation is a log-price linear combination, `log(P) - beta*log(Q) - intercept`, with mean-reversion entry/exit around deviations from equilibrium. The package adopts this form.

3. Caporale, Fons Palomares & Gil-Alaña (CESifo Working Paper 12559, 2026), *Long-Run Linkages and Parameter Instability in the Gold–Silver Relationship, 2010–2025*: the paper reports instability in the gold–silver relation and a late-2017 structural break, with standard full-sample cointegration not stable. The package therefore explicitly forbids hard-coding that breakpoint and instead estimates the relation on a rolling past-only window.

## Why 252 / 2 sigma / zero / 4 sigma / 60 days?

This is a single pre-registered engineering specification, not a claim that these are universally optimal parameters. They are selected before observing the project reference result and are not searched:

- 252 trading sessions: approximately one trading year and long enough to estimate a relationship without using the reported 2017/2018 break.
- |z|=2 entry: conventional large-deviation threshold in pairs-trading practice.
- z=0 exit: direct test of mean reversion to the estimated equilibrium.
- |z|=4 adverse stop: fixed tail-risk containment rather than an optimized threshold.
- 60 trading-day maximum hold: allows relatively slow adjustment while keeping capital lockup bounded.

A failure does not authorize trying nearby values.

## Important limitation

XAUUSD and XAGUSD are broker CFD/spot-style instruments, not COMEX futures. Therefore the result applies to this broker relative-value implementation. It is not a direct test of a GC/SI futures spread strategy.
