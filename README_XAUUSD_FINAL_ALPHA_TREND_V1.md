# XAUUSD Final Alpha Campaign — Canonical Long-Horizon Vol-Scaled Trend V1

## Purpose

One bounded final-alpha test. This is not a scan and has no stage number.

The strategy family is anchored to Moskowitz, Ooi & Pedersen (2012), *Time Series Momentum*, Journal of Financial Economics 104, 228–250:

- trailing 12-month return sign determines long/short direction;
- one-month holding/rebalance;
- ex-ante volatility estimated from past daily returns with an exponentially weighted variance whose center of mass is 60 days;
- position size is inverse-volatility scaled.

The paper uses 40% ex-ante volatility per individual instrument and explicitly states that this scaling choice is inconsequential for the economic signal. For this broker-commercial XAUUSD implementation, the target is pre-registered at 20% annualized volatility with a hard 2.0x absolute position cap. There is no target-vol or leverage scan.

This is a broker-price proxy, not a faithful COMEX futures replication: XAUUSD CFD price returns do not contain the full futures excess-return / roll-yield structure. A surviving result therefore requires independent GC futures replication before any paper/demo/live consideration.

## Locked execution contract

- Input: AMarkets XAUUSD H1 CSV.
- AMarkets server time converted using the frozen EU-DST contract: UTC = server timestamp -2h standard / -3h DST.
- Monthly entry/rebalance: first executable H1 open of each UTC calendar month.
- Signal information: only completed H1 bars available at or before that entry.
- 12-month signal: sign of the prior 12 monthly completed closes.
- Volatility: past-only EWMA of daily returns, 60-day center of mass, annualized with 261 days.
- Target annual vol: 20%.
- Absolute leverage/position cap: 2.0x.
- Normal cost: 3 bps per 1x notional turnover.
- Severe cost: 6 bps per 1x notional turnover.
- Turnover cost applies to monthly changes in position, so a +1 to -1 flip costs on 2x turnover.
- No stop, TP, macro filter, session filter, threshold optimization, lookback optimization or variant selection.

## Reference / diagnostic discipline

Reference selection ends strictly before `2025-01-01T00:00:00Z` and only completed monthly holding periods ending before that boundary are used.

Any month crossing the boundary is quarantined.

2025+ is evaluated only if **all** reference gates pass. If reference fails, diagnostic metrics are not computed.

2025+ is labelled `SEEN_DIAGNOSTIC_NOT_PRISTINE_HOLDOUT` and is kill-only; it cannot rescue a failed reference result.

## Primary benchmark

`PASSIVE_VOL_SCALED_GOLD`: always-long XAUUSD with the **same** ex-ante volatility estimator, target volatility, leverage cap and turnover cost model.

This benchmark is essential: it isolates the directional trend signal from the benefit of volatility scaling and from gold's positive drift.

A standard 1x buy-and-hold series is also reported as context.

## Reference gates

All must pass:

- at least 120 eligible reference months;
- severe-cost annualized return > 2%;
- severe-cost Sharpe > 0.20;
- moving-block bootstrap p10 of mean monthly return > 0;
- annualized return remains > 0 after deleting the best month;
- at least 2 of 3 chronological folds positive;
- worst fold annualized return > -10%;
- at least 55% of calendar years positive;
- largest positive year's share of all positive-year P&L <= 50%;
- max drawdown <= 50%;
- mean paired monthly excess over passive vol-scaled gold > 0;
- moving-block bootstrap p10 of paired excess > 0.

These are strategy-class-specific commercial gates, not copied from the intraday 4h framework.

## Possible decisions

- `NO_REFERENCE_EDGE_CLOSE_LONG_HORIZON_TREND_ON_XAUUSD_CFD`
- `REFERENCE_PASS_DIAGNOSTIC_BREAKDOWN_REJECT_TREND_PATH`
- `REFERENCE_PASS_DIAGNOSTIC_SUPPORT_READY_FOR_INDEPENDENT_GC_REPLICATION`
- `FINAL_ALPHA_TREND_FAIL_CLOSED`

No outcome authorizes paper, demo or live orders.

## Commands

### Preflight

```bash
python3 app/xauusd_final_alpha_trend.py preflight --root .
```

### Run

```bash
python3 app/xauusd_final_alpha_trend.py run --root .
```

Exit code 2 is an economically valid rejection decision, not a runtime error.

### Collect

Run collect after a completed `run` even if the strategy was rejected:

```bash
python3 app/xauusd_final_alpha_trend.py collect --root .
```

Artifact:

```text
~/Downloads/XAUUSD_FINAL_ALPHA_TREND_RESULTS.zip
```

## What to return

Send only `XAUUSD_FINAL_ALPHA_TREND_RESULTS.zip` unless preflight/run fails. On failure, send:

- `xauusd_final_alpha_trend_console.txt`
- `reports/xauusd_final_alpha_trend_failure.json`
