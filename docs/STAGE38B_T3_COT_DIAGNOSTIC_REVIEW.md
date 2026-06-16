# STAGE38B / T3 COT Diagnostic Review

**Project:** XAUUSD / Gold Trading System  
**Stage:** Stage38B — T3 COT Data Foundation  
**Status:** Diagnostic completed; COT is usable as a regime/filter candidate, not as a standalone entry signal.  
**Trading status:** NO-GO for Stage39, EA, paper-live, and live order.  

---

## 1. Purpose

This document reviews the first T3 COT research diagnostic after successful CFTC COT ingestion, SQLite loading, anti-lookahead H1 join, and COT feature-state audit.

The diagnostic tested whether COT positioning states separate future XAUUSD H1 returns without constructing a trading strategy.

This was intentionally limited to:

```text
COT state only
forward returns only
no entry/exit rules
no optimization
no ML
no paper/live
```

---

## 2. Input Validation Summary

The diagnostic audit passed:

```text
status = PASS
bars_total = 25,643
event_count = 216
returns_written = 128,831
summary_rows_written = 70
lookahead_violation_count = 0
warning_count = 0
note_count = 1
```

Interpretation:

```text
The COT-to-H1 research dataset is technically valid for read-only diagnostics.
No lookahead violation was detected.
The primary decision level should remain event_level, not repeated H1 rows.
```

Reason:

```text
COT is weekly. Repeating the same COT state over many H1 bars inflates the apparent sample size. Event-level analysis is more conservative and more decision-relevant.
```

---

## 3. Primary Event-Level Results

### 3.1 Horizon: 120H

| COT state | N | Mean bps | Median bps | Long WR | Diff vs Neutral | t-stat | Positive years | Negative years | Max positive year share |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MM_EXTREME_LONG | 11 | 63.22 | 39.28 | 0.636 | 29.76 | 1.77 | 1 | 0 | 1.000 |
| MM_LONG_CROWDED | 52 | 45.69 | 67.04 | 0.596 | 12.24 | 1.61 | 2 | 1 | 0.506 |
| MM_NEUTRAL | 114 | 33.45 | 23.24 | 0.553 | 0.00 | 1.41 | 3 | 2 | 0.848 |
| MM_SHORT_CROWDED | 28 | -0.08 | -3.69 | 0.500 | -33.53 | -0.00 | 1 | 1 | 1.000 |
| MM_EXTREME_SHORT | 10 | 150.36 | 163.55 | 0.800 | 116.91 | 2.56 | 2 | 0 | 0.813 |

### 3.2 Horizon: 240H

| COT state | N | Mean bps | Median bps | Long WR | Diff vs Neutral | t-stat | Positive years | Negative years | Max positive year share |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MM_EXTREME_LONG | 11 | 134.67 | 128.42 | 0.818 | 61.29 | 2.20 | 1 | 0 | 1.000 |
| MM_LONG_CROWDED | 52 | 107.97 | 82.57 | 0.615 | 34.58 | 2.89 | 2 | 1 | 0.569 |
| MM_NEUTRAL | 113 | 73.38 | 61.99 | 0.584 | 0.00 | 2.11 | 3 | 2 | 0.809 |
| MM_SHORT_CROWDED | 28 | 4.22 | -48.06 | 0.393 | -69.17 | 0.07 | 1 | 1 | 1.000 |
| MM_EXTREME_SHORT | 10 | 259.09 | 285.42 | 0.800 | 185.71 | 3.37 | 2 | 0 | 0.889 |

---

## 4. Interpretation

### 4.1 COT is not a standalone entry signal yet

The diagnostic does not justify promoting T3 into a standalone trading strategy.

Reasons:

```text
- Extreme states have small event samples.
- MM_EXTREME_LONG has only 11 events.
- MM_EXTREME_SHORT has only 10 events.
- Positive contribution is year-concentrated in multiple states.
- The overall gold sample is upward-biased, so neutral and long-crowded states also show positive forward returns.
```

A naive conclusion such as “COT extreme short = buy gold” would be premature.

### 4.2 The strongest raw pattern is extreme-short squeeze risk

`MM_EXTREME_SHORT` has the strongest forward return profile:

```text
120H mean = +150.36 bps
240H mean = +259.09 bps
120H WR = 0.800
240H WR = 0.800
```

But this state is low-sample:

```text
N = 10 events
positive_year_count = 2
max_positive_year_share = 0.813 to 0.889
```

Decision:

```text
Useful as a candidate squeeze regime.
Not promotable alone.
Requires interaction testing with trend, volatility, and macro/structural expansion filters.
```

### 4.3 The most robust negative/useful filter is short-crowded underperformance

`MM_SHORT_CROWDED` is weak versus neutral:

```text
120H mean = -0.08 bps vs neutral +33.45 bps
240H mean = +4.22 bps vs neutral +73.38 bps
120H diff vs neutral = -33.53 bps
240H diff vs neutral = -69.17 bps
240H median = -48.06 bps
240H long WR = 0.393
```

This is important because it suggests COT may be more valuable as a long-regime filter than as an entry trigger.

Candidate use:

```text
Avoid or penalize long continuation trades when MM_SHORT_CROWDED is active, unless price/trend/volatility confirms a squeeze transition.
```

### 4.4 Long crowded and extreme long do not behave as simple contrarian shorts

Both `MM_LONG_CROWDED` and `MM_EXTREME_LONG` show positive forward returns.

This means the data does not support a simple contrarian rule such as:

```text
Managed money very long -> short gold
```

More likely interpretation:

```text
In gold bull regimes, crowded long positioning may persist and continue rather than immediately reverse.
```

This is consistent with T1’s earlier structural-expansion finding: momentum/expansion regimes can dominate naive contrarian logic.

---

## 5. Decision

```text
T3_COT_RAW_DIAGNOSTIC_STATUS = PASS_WITH_CAUTION
T3_COT_STANDALONE_SIGNAL = NO_GO
T3_COT_FILTER_OR_REGIME = PROCEED_TO_INTERACTION_DIAGNOSTIC
STAGE39 = NO_GO
EA = NO_GO
PAPER_LIVE = NO_GO
LIVE_ORDER = NO_GO
```

T3 should proceed only as a regime/filter layer.

It should not be converted directly into a backtest or entry rule.

---

## 6. Kill / Proceed Logic

### Kill T3 as standalone signal

Kill standalone T3 because:

```text
- Event count is small for extreme states.
- Year concentration is high.
- Directional effect is not cleanly contrarian.
- Positive forward returns exist even in neutral/long-crowded states due to broader gold trend.
```

### Proceed T3 as interaction filter

Proceed to interaction diagnostic because:

```text
- MM_SHORT_CROWDED materially underperforms neutral.
- MM_EXTREME_SHORT shows strong squeeze-like positive forward returns.
- COT may help distinguish continuation, squeeze, and avoid-long regimes.
- The dataset is technically clean and anti-lookahead validated.
```

---

## 7. Next Required Diagnostic

Next file:

```text
app/stage38b_t3_cot_interaction_diagnostic.py
```

Purpose:

```text
Test whether COT states become useful when combined with structural market context.
```

Minimum interaction dimensions:

```text
1. COT state × D1 trend pct bucket
2. COT state × H4 trend pct bucket
3. COT state × ATR pct price bucket
4. COT state × macro score long gold bucket, if available
5. COT state × T1 locked structural filter condition, if reconstructable
```

Primary questions:

```text
- Does MM_EXTREME_SHORT only work in bullish/expansion regimes?
- Does MM_SHORT_CROWDED reliably identify avoid-long regimes?
- Do MM_LONG_CROWDED / MM_EXTREME_LONG continue working only when structural trend is strong?
- Does COT add incremental information beyond the known 2025 structural-expansion regime?
```

Primary decision metric:

```text
event_level forward return separation
```

Secondary diagnostic:

```text
h1_all view for coverage only, not final decision
```

---

## 8. Current Stage38B State

Completed:

```text
- CFTC COT download through GitHub Actions artifact
- COT gold SQLite loader
- COT-to-H1 anti-lookahead join audit
- T3 COT feature audit
- T3 raw COT research diagnostic
```

Current conclusion:

```text
COT data foundation is valid.
Raw COT has useful regime information.
Standalone COT signal is rejected.
COT interaction/regime-filter research is justified.
```
