# STAGE38E — Macro/Risk H1 Join Review

**Project:** XAUUSD / Gold research  
**Stage:** Stage38E  
**Status:** PASS — macro/risk data foundation usable  
**Decision:** Proceed to read-only macro context diagnostic  
**Execution status:** No Stage39, no EA, no paper-live, no live order

---

## 1. Purpose

Stage38E was opened after Stage38B/C/D failed to produce a promotable edge:

- Stage38B COT/T3 produced a useful data foundation, but only marginal overlay value.
- Stage38C H1 session/price baselines were weak and not promotable.
- Stage38D M5/M15 session baselines were weak and archived.

The goal of Stage38E is therefore not to build a trading system. The goal is to build a free macro/risk data foundation and then test whether macro/risk regimes explain forward XAUUSD behavior better than pure price/session baselines.

---

## 2. Data Source

The Stage38E audit used free FRED CSV endpoints without API keys.

Default series:

```text
DGS10     10Y nominal yield
DGS2      2Y nominal yield
DFII10    10Y real yield
T10YIE    10Y breakeven inflation
DTWEXBGS  broad USD index
VIXCLS    VIX
```

Lookahead rule:

```text
observation_date = YYYY-MM-DD
available_from_utc = observation_date + 1 calendar day at 00:00:00 UTC
```

This is conservative. It avoids using the same day's macro observation before it is assumed available.

---

## 3. Audit Result

User-reported audit result:

```text
status = PASS
decision = PROCEED_TO_STAGE38E_MACRO_H1_JOIN_REVIEW
series_requested = 6
series_pass_count = 6
series_warn_count = 0
series_fail_count = 0
raw_rows_written = 38,271
daily_feature_rows = 6,901
h1_bars_total = 25,643
h1_joined_count = 25,643
h1_unjoined_count = 0
lookahead_violation_count = 0
warning_count = 0
note_count = 2
```

Interpretation:

```text
Stage38E macro/risk data foundation is usable.
All H1 bars have a joined macro/risk context.
No lookahead violation was detected.
No series failed.
```

---

## 4. Series Coverage

User-reported series audit:

```text
DFII10    PASS  5,866 valid observations  2003-01-02 to 2026-06-12
DGS10     PASS  6,615 valid observations  2000-01-03 to 2026-06-12
DGS2      PASS  6,615 valid observations  2000-01-03 to 2026-06-12
DTWEXBGS  PASS  5,126 valid observations  2006-01-02 to 2026-06-12
T10YIE    PASS  5,867 valid observations  2003-01-02 to 2026-06-15
VIXCLS    PASS  6,683 valid observations  2000-01-03 to 2026-06-15
```

All required macro/risk inputs are available over the active XAUUSD H1 period.

---

## 5. H1 Join Result

User-reported H1 join check:

```text
joined_rows = 25,643
bar range = 2022-05-01T23:00:00Z to 2026-06-16T12:00:00Z
macro observation range = 2022-04-29 to 2026-06-15
lookahead violations = 0
```

This is a clean join and can be used for read-only macro context diagnostics.

---

## 6. Latest Macro State Snapshot

Latest available rows showed:

```text
2026-06-15:
    DGS10 = 4.48
    DGS2 = 4.09
    DFII10 = 2.17
    T10YIE = 2.32
    DTWEXBGS = 119.5073
    VIXCLS = 16.2
    curve_10y2y = 0.39
    real_10y_chg_5d = -0.04
    dollar_chg_5d = -0.527
    macro_gold_pressure = REAL_YIELD_FLAT+USD_DOWN
    macro_risk_state = RISK_NORMAL
```

This is not a trading signal. It is only a descriptive macro/risk context.

---

## 7. Decision

```text
STAGE38E_MACRO_DATA_FOUNDATION = PASS
STAGE38E_H1_JOIN = PASS
LOOKAHEAD_STATUS = CLEAN
PROCEED_TO_MACRO_CONTEXT_DIAGNOSTIC = YES
PROMOTE_TO_BASELINE_OR_STRATEGY = NO
STAGE39 = NO-GO
EA = NO-GO
PAPER_LIVE = NO-GO
LIVE_ORDER = NO-GO
```

---

## 8. Next Step

Next file:

```text
app/stage38e_macro_context_diagnostic.py
```

Purpose:

```text
Measure whether macro/risk states separate XAUUSD forward returns.
```

Method:

```text
Use event-level daily macro observations, not repeated H1 rows as independent samples.
For each macro observation, use the first H1 bar after macro_available_from_utc.
Measure forward returns over fixed horizons.
No entry rule.
No optimization.
No ML.
No paper/live.
```

Primary groupings:

```text
macro_gold_pressure
macro_risk_state
macro_gold_pressure × macro_risk_state
real yield 5D bucket
USD 5D bucket
macro bias: SUPPORTIVE / HOSTILE / MIXED
```

Promotion rule:

```text
Macro context can only proceed if it provides stable event-level separation across years.
If separation is weak, year-concentrated, or only visible in 2025/2026, Stage38E remains a data foundation only.
```
