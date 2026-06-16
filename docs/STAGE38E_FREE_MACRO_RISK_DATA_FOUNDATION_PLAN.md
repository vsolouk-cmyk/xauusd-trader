# STAGE38E Free Macro/Risk Data Foundation Plan

**Project:** XAUUSD / Gold Research  
**Stage:** Stage38E  
**Purpose:** Build a free, reproducible macro/risk data foundation for gold research  
**Status:** Plan only  
**Trading status:** Stage39 / EA / paper-live / live = NO-GO

---

## 1. Why Stage38E Is Needed

Prior branches did not produce a promotable edge:

```text
Stage38A / T1 = low-confidence, 2025-dominated
Stage38B / T3 COT = data foundation success, edge not promotable
Stage38C / H1 baselines = weak candidate, not promotable
Stage38D / M5/M15 session baselines = weak, not promotable
```

The repeated pattern is clear: pure price/session structure is not enough yet.

Gold needs a macro/risk context layer.

---

## 2. Stage38E Objective

Create a free data foundation for macro/risk variables that may explain gold regimes.

This stage is not a strategy stage.

Primary objective:

```text
Download, normalize, audit, and join macro/risk daily features to XAUUSD H1/M15/M5 bars without lookahead.
```

Secondary objective:

```text
Determine whether macro/risk regimes explain why technical/session baselines only worked in later regimes.
```

---

## 3. Allowed Data Categories

Stage38E should initially focus on daily or slower variables.

Candidate categories:

```text
US nominal yields:
    2Y yield
    10Y yield
    yield curve slope

US real yield proxy:
    10Y TIPS real yield, if available

Dollar pressure:
    broad dollar index or available USD index proxy

Inflation expectation proxy:
    10Y breakeven proxy if available

Risk sentiment proxy:
    VIX or broad risk index proxy, if a free source is reliably available

Gold ETF / flow proxy:
    optional later only if free and robust
```

Do not add paid APIs.

---

## 4. Preferred Free Source Policy

Source priority:

```text
1. Official / stable public API
2. Public CSV/static endpoint with predictable schema
3. Unofficial market-data package only as optional fallback
```

Preferred first source:

```text
FRED / Federal Reserve Economic Data
```

Reason:

- It provides official macro/financial time series.
- It has documented API access.
- It supports programmatic retrieval of series observations.
- It is suitable for GitHub Actions if local access is blocked.

Important limitation:

```text
FRED may require an API key.
If local access fails, Stage38E should support GitHub Actions download and artifact handoff.
```

---

## 5. Initial Series Candidate List

The exact list must be validated by the availability audit.

Initial candidates:

```text
DGS2      = 2-year US Treasury constant maturity yield
DGS10     = 10-year US Treasury constant maturity yield
DFII10    = 10-year TIPS real yield / inflation-indexed constant maturity
DTWEXBGS  = nominal broad US dollar index
```

Derived features:

```text
yield_10y_minus_2y = DGS10 - DGS2
real_yield_10y_change_5d
real_yield_10y_change_20d
dollar_index_change_5d
dollar_index_change_20d
nominal_yield_10y_change_5d
nominal_yield_10y_change_20d
```

Optional later features:

```text
breakeven_10y = DGS10 - DFII10
risk sentiment proxy
ETF proxy
```

---

## 6. Anti-Lookahead Rule

Macro daily data must not be joined by date alone.

Every macro row must have:

```text
observation_date
source_published_or_available_date
available_from_utc
```

If exact publication time is unavailable, use conservative availability:

```text
available_from_utc = next calendar day 00:00 UTC
```

For XAUUSD bar timestamp `T`, the join rule is:

```text
use only latest macro row where available_from_utc <= T
```

No same-day assumption unless validated.

---

## 7. Stage38E Deliverables

Planned files:

```text
docs/STAGE38E_FREE_MACRO_RISK_DATA_FOUNDATION_PLAN.md
app/stage38e_macro_risk_data_availability_audit.py
.github/workflows/stage38e_macro_risk_download.yml     # only if local/API access fails
```

Planned database tables:

```text
macro_risk_raw_series
macro_risk_daily_features
macro_risk_availability_audit
macro_risk_h1_joined
macro_risk_join_audit
```

Planned reports:

```text
data/reports/stage38e_macro_risk_data_availability_audit/
data/reports/stage38e_macro_risk_h1_join_audit/
```

---

## 8. Stage38E Kill-Switches

Stop or downgrade Stage38E if:

```text
source access is unreliable and cannot be solved through GitHub artifact flow
series coverage does not overlap enough with XAUUSD data
macro rows cannot be timestamped without lookahead ambiguity
data gaps are too large
features are too stale for intraday research
```

---

## 9. What Stage38E Is Not

Stage38E is not:

```text
not a trading strategy
not a model
not a backtest promotion
not Stage39
not EA
not paper-live
not live
```

---

## 10. Immediate Next Step

Build:

```text
app/stage38e_macro_risk_data_availability_audit.py
```

The script should:

```text
1. Try to download/validate the initial free macro series.
2. Normalize dates and numeric values.
3. Report coverage against XAUUSD bar range.
4. Build conservative available_from_utc timestamps.
5. Store output in SQLite.
6. Produce JSON/MD audit reports.
7. Fail clearly if a key source is inaccessible.
```

If local access fails, create a GitHub Actions workflow to download the data and return it as artifact.
