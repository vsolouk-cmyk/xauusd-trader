# Stage38B / T3 COT Interaction Diagnostic Review

**Project:** XAUUSD / Gold Research  
**Stage:** Stage38B / T3 COT data foundation  
**Status:** Interaction diagnostic reviewed  
**Decision date:** 2026-06-16  
**Scope:** Read-only research diagnostic only. No strategy, no ML, no paper-live, no EA, no Stage39.

---

## 1. Executive Decision

```text
T3_COT_INTERACTION_STATUS = PASS_WITH_CAUTION
T3_AS_STANDALONE_SIGNAL = NO_GO
T3_AS_PRIMARY_T1_INTERACTION_DRIVER = NO_GO
T3_AS_SECONDARY_RISK_OR_REGIME_OVERLAY = PROCEED_TO_RESTRICTED_GATE
STAGE39 = NO_GO
EA = NO_GO
PAPER_LIVE = NO_GO
LIVE_ORDER = NO_GO
```

COT has useful information, but not enough evidence to promote it as a direct entry signal or a primary strategy driver.

The correct next step is a restricted gate test that checks whether COT can improve an existing or simple baseline as a filter/overlay, especially around:

```text
MM_SHORT_CROWDED x ATR_EXPANSION
MM_EXTREME_SHORT x ATR_EXPANSION
MM_NEUTRAL x ATR_LOW
```

No trading strategy should be built from the raw COT interaction results yet.

---

## 2. Audit Result

The interaction diagnostic passed structurally.

```text
status = PASS
bars_total = 25,643
event_count = 216
context_rows_written = 25,643
returns_written = 51,355
summary_rows_written = 388
lookahead_violation_count = 0
warning_count = 0
note_count = 2
```

This means the COT/H1/context dataset is technically usable for research.

Important: the decisive sample count is the event-level count, not the repeated H1 count, because COT is a weekly report.

```text
event_count = 216
```

---

## 3. T1 Structural Interaction Result

T1-like structural state distribution:

```text
T1_STRUCT_OFF      = 23,167 H1 bars
T1_STRUCT_ON       = 1,493 H1 bars
T1_STRUCT_UNKNOWN  = 983 H1 bars
```

Event-level COT x T1 result did not establish a robust interaction.

### 120H horizon

Main observations:

```text
MM_NEUTRAL__T1_STRUCT_OFF:
    n = 104
    mean = +42.19 bps
    median = +33.03 bps
    WR = 0.577

MM_LONG_CROWDED__T1_STRUCT_OFF:
    n = 49
    mean = +38.22 bps
    median = +61.43 bps
    WR = 0.592

MM_EXTREME_SHORT__T1_STRUCT_OFF:
    n = 10
    mean = +150.36 bps
    median = +163.55 bps
    WR = 0.800
    note = YEAR_CONCENTRATED

MM_NEUTRAL__T1_STRUCT_ON:
    n = 8
    mean = -12.22 bps
    median = -129.96 bps
    WR = 0.375
    note = YEAR_CONCENTRATED
```

### 240H horizon

Main observations:

```text
MM_NEUTRAL__T1_STRUCT_OFF:
    n = 103
    mean = +92.11 bps
    median = +78.54 bps
    WR = 0.602

MM_LONG_CROWDED__T1_STRUCT_OFF:
    n = 49
    mean = +100.16 bps
    median = +81.59 bps
    WR = 0.612

MM_EXTREME_SHORT__T1_STRUCT_OFF:
    n = 10
    mean = +259.09 bps
    median = +285.42 bps
    WR = 0.800
    note = YEAR_CONCENTRATED

MM_NEUTRAL__T1_STRUCT_ON:
    n = 8
    mean = -66.00 bps
    median = -6.53 bps
    WR = 0.500
    note = YEAR_CONCENTRATED
```

### Interpretation

T1 interaction is not strong enough to promote.

Reasons:

```text
1. Most usable samples are T1_STRUCT_OFF.
2. T1_STRUCT_ON event sample is too small.
3. Strong-looking T1_STRUCT_ON subsets are low sample and year-concentrated.
4. T1 structural expansion does not clearly amplify COT edge.
```

Therefore:

```text
COT x T1_STRUCTURAL = NOT PROMOTABLE
```

---

## 4. ATR Interaction Result

ATR interaction is more useful than T1 interaction.

Primary 240H event-level observations:

```text
MM_NEUTRAL__ATR_NORMAL:
    n = 40
    mean = +116.98 bps
    median = +102.59 bps
    WR = 0.625
    note = None

MM_LONG_CROWDED__ATR_NORMAL:
    n = 28
    mean = +104.81 bps
    median = +81.51 bps
    WR = 0.643
    note = None

MM_LONG_CROWDED__ATR_EXPANSION:
    n = 24
    mean = +111.65 bps
    median = +98.09 bps
    WR = 0.583
    note = None

MM_SHORT_CROWDED__ATR_EXPANSION:
    n = 11
    mean = -46.79 bps
    median = -90.40 bps
    WR = 0.273
    note = YEAR_CONCENTRATED

MM_EXTREME_SHORT__ATR_EXPANSION:
    n = 10
    mean = +259.09 bps
    median = +285.42 bps
    WR = 0.800
    note = YEAR_CONCENTRATED

MM_NEUTRAL__ATR_LOW:
    n = 13
    mean = -13.33 bps
    median = -3.52 bps
    WR = 0.462
    note = None
```

### Interpretation

The most important ATR result is not a clean entry signal. It is a potential regime/risk overlay:

```text
MM_SHORT_CROWDED__ATR_EXPANSION appears hostile to long exposure.
```

But it is still not robust enough to use directly, because:

```text
sample_count = 11
year concentration is flagged
```

`MM_EXTREME_SHORT__ATR_EXPANSION` looks strong on the long side, but also has only 10 events and is year-concentrated. It is a research clue, not a promotable signal.

---

## 5. What Was Not Confirmed

The diagnostic did not confirm these assumptions:

```text
1. COT extreme long = short signal.
2. COT extreme short = automatically tradable long signal.
3. T1 structural expansion + COT = robust edge.
4. COT alone is enough to build T3.
```

The result is more modest:

```text
COT may help as a regime/risk overlay, especially when combined with ATR state.
```

---

## 6. Working Hypotheses for the Next Gate

Only these restricted hypotheses should be tested next.

### H1 — Avoid-long filter

```text
When COT state is MM_SHORT_CROWDED and ATR bucket is ATR_EXPANSION,
long exposure may have poor forward expectancy.
```

Use as:

```text
avoid-long / penalize-long overlay
```

Do not use as:

```text
short-entry signal
```

### H2 — Squeeze-risk regime

```text
When COT state is MM_EXTREME_SHORT and ATR bucket is ATR_EXPANSION,
forward gold return has been strongly positive in the sample.
```

Use as:

```text
possible squeeze-risk / do-not-short regime
```

Do not use as:

```text
blind long-entry signal
```

### H3 — Low-vol neutral caution

```text
MM_NEUTRAL x ATR_LOW is weak and may not justify active long exposure.
```

Use as:

```text
low-conviction / no-trade regime candidate
```

---

## 7. Required Next Test

The next test must be a restricted gate, not a free-form strategy search.

Suggested file:

```text
app/stage38b_t3_cot_overlay_gate.py
```

Purpose:

```text
Measure whether COT/ATR overlay improves simple forward-return or baseline exposure metrics.
```

Allowed tests:

```text
1. Long-permitted vs long-blocked forward return comparison.
2. Do-not-short / squeeze-risk comparison.
3. Overlay impact on unconditional H1/event forward returns.
4. Year-by-year stability and contribution concentration.
5. Cost-aware directional sanity check using Stage38A stress p90 cost.
```

Forbidden:

```text
1. No optimized entry/exit.
2. No ML.
3. No Stage39.
4. No EA.
5. No paper-live.
6. No live orders.
7. No Telegram signal alerts.
```

---

## 8. Decision Gate for Next Step

The overlay gate can proceed only if it shows:

```text
1. Positive or protective effect versus neutral/unfiltered baseline.
2. Not dependent on one year or one event cluster.
3. Sufficient event-level sample size.
4. No lookahead violations.
5. Clear interpretation as filter/overlay, not curve-fit entry logic.
```

Kill or downgrade if:

```text
1. Improvements are only from MM_EXTREME_SHORT with n≈10.
2. Positive results are year-concentrated.
3. Effect disappears after cost-aware framing.
4. Overlay does not improve simple baseline exposure.
```

---

## 9. Current Stage38B Status

```text
COT_DOWNLOAD = PASS
COT_SQLITE_LOAD = PASS
COT_H1_ANTI_LOOKAHEAD_JOIN = PASS
COT_FEATURE_AUDIT = PASS
COT_RAW_DIAGNOSTIC = PASS_WITH_CAUTION
COT_INTERACTION_DIAGNOSTIC = PASS_WITH_CAUTION
T3_STANDALONE = NO_GO
T3_OVERLAY_GATE = NEXT
STAGE39 = NO_GO
EA = NO_GO
PAPER_LIVE = NO_GO
LIVE_ORDER = NO_GO
```
