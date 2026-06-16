# Stage38D M5/M15 Session Baseline Plan

**Project:** XAUUSD / Gold Trading System  
**Stage:** Stage38D  
**Purpose:** Move from coarse H1 session baselines to execution-aware M5/M15 session baseline research  
**Status:** PLAN ONLY / READ-ONLY  

---

## 1. Why Stage38D is needed

Stage38C showed that the H1 Asia range breakout has weak but non-random structure:

```text
ASIA_RANGE_BREAKOUT_24H_H1 mean_net_bps = +7.63
LONG_ONLY trade_mean_net_bps = +14.45
LONG_ONLY event_clock_uplift = only +0.29 bps
```

The targeted filters did not justify promotion. However, the direction split showed a clear asymmetry:

```text
LONG side positive
SHORT side weak / negative
```

Because Asia range breakout is an intraday construction problem, H1 bars are too coarse for:

```text
- true breakout timing
- range boundary precision
- stop/target placement
- adverse excursion analysis
- spread sensitivity
- session transition logic
```

Stage38D should therefore test whether the same session thesis survives on M5/M15, using the existing lower-timeframe AMarkets data.

---

## 2. Hard restrictions

```text
Stage39 = NO_GO
EA = NO_GO
paper-live = NO_GO
live order = NO_GO
ML = NO_GO
optimization sweep = NO_GO
```

Stage38D is a read-only baseline/data-quality stage.

---

## 3. Required first step

Before any baseline retest, verify lower-timeframe data availability and schema.

Target audit script:

```text
app/stage38d_m5_m15_data_availability_audit.py
```

Required checks:

```text
1. Detect available timeframes in bars table.
2. Count M1/M5/M15 rows if present.
3. Confirm timestamp column.
4. Confirm OHLC columns.
5. Confirm spread column.
6. Confirm source/symbol coverage.
7. Detect gaps by timeframe.
8. Detect duplicate timestamps.
9. Detect weekend/session anomalies.
10. Produce report before any baseline logic.
```

---

## 4. Data construction options

Stage38D should choose one of two paths after audit:

### Option A — use existing M5/M15 if already stored

Pros:

```text
- simpler
- faster
- fewer aggregation assumptions
```

### Option B — aggregate from M1 to M5/M15

Pros:

```text
- more controlled
- consistent session construction
- possible spread aggregation
```

If M1 is available and clean, Option B is preferred.

---

## 5. Initial Stage38D candidate families

Only simple, thesis-driven candidates are allowed:

```text
1. Asia range long breakout only
2. Asia range short breakout diagnostic only
3. London open continuation after Asia break
4. London false-break fade diagnostic
5. NY continuation after London direction
6. ATR/range expansion continuation
```

No ML, no multi-parameter optimizer, no dynamic model.

---

## 6. Initial fixed definitions

Use fixed session definitions first. If server timezone is uncertain, report this as a limitation.

Draft UTC session framework:

```text
Asia range window: 00:00-06:00 UTC
London transition: 06:00-09:00 UTC
London active: 07:00-11:00 UTC
NY active: 12:00-16:00 UTC
```

These may need adjustment after confirming AMarkets server timestamp behavior.

---

## 7. First Stage38D research question

Do not ask whether a trading strategy is profitable yet.

Ask first:

```text
Does lower-timeframe Asia range breakout preserve the long-side asymmetry found in H1?
```

Minimum expected diagnostics:

```text
- trade count
- mean/median net bps
- win rate
- yearly stability
- monthly concentration
- max positive year contribution share
- event-clock performance
- cost sensitivity
- spread percentile sensitivity
- direction split
- breakout timing split
- range-size split
- ATR regime split
```

---

## 8. Kill-switches

Stop Stage38D if any of these hold:

```text
- M1/M5/M15 data has large unexplained gaps.
- Spread is missing or unusable for lower-timeframe cost modeling.
- Lower-timeframe long-side asymmetry disappears.
- Results depend only on 2025/2026.
- Mean after stress cost is below +5 bps at event-clock level.
- Median is persistently non-positive.
- Monthly/yearly concentration is extreme.
```

---

## 9. Promotion standard

A Stage38D candidate cannot be promoted unless it passes all of these:

```text
1. Positive after stress cost.
2. Positive median or defensible payoff asymmetry.
3. Positive exclude-2025 result.
4. No single year dominates contribution.
5. Event-clock improvement is material, not just trade-only mean.
6. Spread sensitivity remains acceptable.
7. Directional thesis is explainable.
```

---

## 10. Next artifact

```text
app/stage38d_m5_m15_data_availability_audit.py
```

This must be built before any M5/M15 baseline test.
