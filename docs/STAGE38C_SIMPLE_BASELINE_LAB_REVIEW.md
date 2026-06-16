# Stage38C Simple Baseline Lab Review

**Project:** XAUUSD / Gold Trading System  
**Stage:** Stage38C — Simple Baseline Lab  
**Status:** Read-only research  
**Decision:** Proceed to deep diagnostics, but do not promote any baseline yet  

---

## 1. Guardrails

This review keeps the existing project constraints intact:

```text
Stage39 = NO-GO
EA = NO-GO
paper-live = NO-GO
live order = NO-GO
ML = NO-GO
```

Stage38C is only a simple baseline lab. COT/T3 remains context only and must not be used as a primary entry condition after Stage38B showed only marginal overlay value.

---

## 2. Lab audit

```text
status = PASS
decision = PROCEED_TO_DEEP_DIAGNOSTICS_READ_ONLY
bars_total = 25,643
events_written = 63,580
summary_rows_written = 64
pass_count = 2
watch_count = 8
kill_count = 54
warning_count = 0
note_count = 1
```

The baseline lab executed successfully and produced enough events for diagnostic screening.

---

## 3. Research-interest candidates

Two baselines passed initial research-interest thresholds:

| decision | family | baseline | horizon | sample | mean net bps | median net bps | win rate | t-stat | positive years | negative years | max positive year share | note |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| PASS_RESEARCH_INTEREST | ASIA_RANGE | ASIA_RANGE_BREAKOUT | 24 | 972 | 7.63 | 2.37 | 0.507 | 2.18 | 4 | 1 | 0.421 | none |
| PASS_RESEARCH_INTEREST | ATR_EXPANSION | ATR_EXP_CONT_T1P5 | 24 | 1002 | 5.54 | -0.18 | 0.497 | 1.50 | 3 | 2 | 0.430 | none |

---

## 4. Immediate interpretation

### 4.1 ASIA_RANGE_BREAKOUT / 24H

This is the current lead candidate.

Positive points:

```text
sample_count = 972
mean_net_bps = +7.63
median_net_bps = +2.37
positive_year_count = 4
negative_year_count = 1
max_positive_year_share = 0.421
```

Weak points:

```text
win_rate = 0.507 only slightly above random
edge size is modest
needs 2025 ablation and month concentration check
needs cost sensitivity check
```

Provisional status:

```text
LEAD_READ_ONLY_CANDIDATE_FOR_DEEP_DIAGNOSTICS
```

### 4.2 ATR_EXP_CONT_T1P5 / 24H

This is a secondary candidate.

Positive points:

```text
sample_count = 1002
mean_net_bps = +5.54
positive_year_count = 3
max_positive_year_share = 0.430
```

Weak points:

```text
median_net_bps = -0.18
win_rate = 0.497
positive_year_count is weaker than Asia breakout
edge may be tail-driven
```

Provisional status:

```text
SECONDARY_READ_ONLY_CANDIDATE_FOR_DEEP_DIAGNOSTICS
```

---

## 5. Watch rows

The watch list should not be promoted before deep diagnostics.

Most important watch rows:

```text
HTF_BIAS_NY_H13 / 24H:
    mean = +3.62 bps
    note = YEAR_CONCENTRATED
    status = weak / likely not promotable

NY_OPEN_CONT_H13 / 24H:
    mean = +3.39 bps
    no concentration note
    status = possible fallback but weak

ASIA_RANGE_BREAKOUT / 8H:
    mean = +3.13 bps
    same family as lead, shorter horizon
    status = useful for horizon comparison only
```

All watch rows are weaker than the two pass candidates. They should be included only as secondary diagnostics, not as new research branches.

---

## 6. Kill rows

Most tested baselines were killed:

```text
kill_count = 54 / 64
```

This is healthy. It confirms the lab is not over-promoting weak baselines.

Notable kills:

```text
London open continuation/reversal at short horizons
NY open short horizons
ATR reversal family
Asia range breakout at 3H
```

No killed row should be revived unless a later structural explanation justifies it.

---

## 7. Required deep diagnostics

Before any baseline-specific design, the next script must test:

```text
1. yearly contribution and 2025 ablation
2. month contribution concentration
3. chronological first-half vs second-half stability
4. leave-one-year-out robustness
5. cost sensitivity at 1.5x and 2.0x stress cost
6. COT annotation only, not filtering
7. drawdown profile
8. median/mean mismatch
```

Decision criteria must be strict because T1 already failed due to 2025/event concentration.

---

## 8. Locked decision

```text
STAGE38C_SIMPLE_BASELINE_LAB = PASS
PROMOTE_TO_BACKTEST = NO
PROMOTE_TO_STAGE39 = NO
PROMOTE_TO_EA = NO
PROMOTE_TO_PAPER_LIVE = NO
NEXT_STEP = STAGE38C_DEEP_DIAGNOSTICS_READ_ONLY
```

Candidate priority:

```text
1. ASIA_RANGE_BREAKOUT / 24H
2. ATR_EXP_CONT_T1P5 / 24H
3. NY_OPEN_CONT_H13 / 24H only as fallback/watch
4. ASIA_RANGE_BREAKOUT / 8H only as horizon comparison
```

---

## 9. Next artifact

```text
app/stage38c_deep_diagnostics.py
```

This must remain read-only and must not generate orders, paper trades, live signals, Telegram alerts, or Stage39 promotion.
