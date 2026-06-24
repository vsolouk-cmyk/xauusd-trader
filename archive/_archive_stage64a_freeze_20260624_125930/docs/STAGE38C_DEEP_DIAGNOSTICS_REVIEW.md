# Stage38C — Deep Diagnostics Review

**Project:** XAUUSD / Gold Trading System  
**Stage:** 38C  
**Status:** Deep diagnostics completed  
**Trading status:** `NO-GO` for Stage39, EA, paper-live, and live orders  
**Next step:** Candidate specification review, read-only

---

## 1. Executive decision

```text
STAGE38C_DEEP_DIAGNOSTICS = PASS_WITH_CAUTION
PROMOTE_TO_BACKTEST = NO
PROMOTE_TO_STAGE39 = NO
PROMOTE_TO_EA = NO
PROMOTE_TO_PAPER_LIVE = NO
NEXT_STEP = CANDIDATE_SPEC_REVIEW_READ_ONLY
```

The Stage38C simple baseline lab found two candidates that deserve further read-only specification work, but neither is strong enough for strategy promotion.

The lead candidate is:

```text
C1 = ASIA_RANGE_BREAKOUT / 24H
```

The secondary candidate is:

```text
C2 = ATR_EXP_CONT_T1P5 / 24H
```

Both remain research candidates only.

---

## 2. Lead candidate: ASIA_RANGE_BREAKOUT / 24H

Summary:

```text
sample_count = 972
mean_net_bps = +7.63
median_net_bps = +2.37
win_rate = 0.507
t_stat = 2.18
exclude_2025_mean = +5.51
y2025_mean = +14.56
pre2025_mean = +1.86
y2026_mean = +32.00
cost_x_1_5_mean = +6.60
cost_x_2_mean = +5.56
worst_leave_one_year_out_mean = +5.14
worst_leave_one_year_out_excluded_year = 2026
```

Positive points:

```text
- sample size is adequate.
- full-sample mean is positive after stress cost.
- t-stat is above 2.
- exclude-2025 remains positive.
- cost x2 remains positive.
- leave-one-year-out remains positive.
```

Weak points:

```text
- pre-2025-only mean is weak at +1.86 bps.
- 2025 and 2026 materially improve the edge.
- first chronological half is weak at +1.63 bps.
- 2022 is negative.
- median is positive but small.
```

Interpretation:

```text
ASIA_RANGE_BREAKOUT / 24H is the only Stage38C candidate worth preserving, but it is not yet promotable. It should move to candidate-spec review and targeted filter diagnostics only.
```

---

## 3. Secondary candidate: ATR_EXP_CONT_T1P5 / 24H

Summary:

```text
sample_count = 1002
mean_net_bps = +5.54
median_net_bps = -0.18
win_rate = 0.497
t_stat = 1.50
exclude_2025_mean = +3.93
y2025_mean = +10.96
pre2025_mean = +0.70
y2026_mean = +25.88
cost_x_1_5_mean = +4.51
cost_x_2_mean = +3.48
worst_leave_one_year_out_mean = +3.32
```

Positive points:

```text
- full-sample mean is positive.
- exclude-2025 remains positive.
- cost sensitivity remains positive.
```

Weak points:

```text
- median is non-positive.
- win rate is below 50%.
- 2023 and 2024 are negative.
- pre-2025-only mean is nearly flat.
- performance appears tail-driven.
```

Interpretation:

```text
ATR_EXP_CONT_T1P5 / 24H should not be promoted. It may remain a secondary diagnostic comparator, but it should not define the next research path.
```

---

## 4. Killed / downgraded candidates

The following are not eligible for immediate candidate-spec promotion:

```text
NY_OPEN_CONT_H13 / 24H
ASIA_RANGE_BREAKOUT / 8H
HTF_BIAS_NY_H13 / 24H
NY_OPEN_CONT_H14 / 24H
```

Reasons include low mean, weak t-stat, year concentration, non-positive chronological halves, and/or weak leave-one-year-out behavior.

---

## 5. COT status in Stage38C

COT remains useful as context only.

```text
COT_AS_ENTRY_FILTER = NO
COT_AS_PRIMARY_GATE = NO
COT_AS_REPORT_ANNOTATION = YES
```

Stage38B showed that COT/T3 infrastructure is valid, but its standalone and restricted overlay edge was marginal. It must not be reused as an optimizer to rescue weak baselines.

---

## 6. Required next step

Next file:

```text
app/stage38c_candidate_spec_review.py
```

Purpose:

```text
- lock candidate identifiers
- write candidate-spec summary tables
- preserve ASIA_RANGE_BREAKOUT / 24H as restricted read-only candidate
- keep ATR_EXP_CONT_T1P5 / 24H only as secondary comparator
- block Stage39 / EA / paper-live / live
```

If the candidate-spec review confirms this reading, the next technical diagnostic should be:

```text
app/stage38c_asia_range_targeted_filter_diagnostic.py
```

That later file should test ASIA_RANGE_BREAKOUT / 24H by direction, breakout timing, Asia range size, volatility bucket, and session context. It must remain read-only and non-optimized.
