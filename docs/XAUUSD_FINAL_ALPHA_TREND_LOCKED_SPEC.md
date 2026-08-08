# Locked specification — Final Alpha Long-Horizon Trend

This document is part of the executable contract.

## Literature anchor

Moskowitz, Tobias J.; Ooi, Yao Hua; Pedersen, Lasse Heje (2012). *Time Series Momentum*. Journal of Financial Economics 104(2): 228–250.

The canonical family uses a 12-month lookback, 1-month holding period, and inverse ex-ante-volatility position sizing. The paper's ex-ante volatility estimator uses exponentially weighted daily squared returns with a 60-day center of mass, annualized by 261 trading days. The published individual-instrument implementation uses 40% ex-ante volatility; the authors state the scaling choice is inconsequential.

## Broker-commercial deviations, fixed ex ante

1. XAUUSD AMarkets CFD is used instead of COMEX gold futures because it is the current executable broker instrument.
2. Trailing price return is used as the signal proxy; futures roll/excess-return decomposition is unavailable in the broker series.
3. Target risk is fixed at 20% annualized, with a 2.0x cap, to avoid turning the alpha test into a leverage test.
4. Costs are charged on actual monthly notional turnover at 3/6 bps normal/severe.

No deviation may be tuned after seeing the result.

## Interpretation

A failure closes this **XAUUSD-CFD implementation** of long-horizon TSMOM. It does not falsify diversified futures trend following in general.

A pass does not authorize trading. It triggers one independent replication on GC futures / an independent institutional-quality feed before any execution promotion.
