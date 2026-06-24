# Stage38D M5/M15 Session Baseline Lab Review

**Project:** XAUUSD / Gold Trading System  
**Stage:** Stage38D  
**Status:** WATCH-only baseline result  
**Decision:** Deep diagnostics read-only on the single remaining WATCH candidate  

---

## 1. Executive decision

```text
STAGE38D_M5_M15_BASELINE_LAB = PASS_TECHNICALLY / WEAK_ECONOMICALLY
PASS_RESEARCH_INTEREST_COUNT = 0
WATCH_COUNT = 1
KILL_COUNT = 41
PROMOTE_TO_STRATEGY = NO
PROMOTE_TO_STAGE39 = NO
EA / PAPER_LIVE / LIVE = NO-GO
NEXT_STEP = LIMITED_DEEP_DIAGNOSTICS_READ_ONLY
```

The M5/M15 session baseline lab did not find a strong candidate. Only one row reached WATCH status:

```text
M5 / ASIA_RANGE / ASIA_RANGE_BREAKOUT_LONG_FIRST / 48 bars / 240 minutes
sample_count = 507
mean_net_bps = +2.41
median_net_bps = +0.59
win_rate_net = 0.509
t_stat = 1.66
positive_year_count = 4
negative_year_count = 1
max_positive_year_share = 0.487
```

This is not enough for promotion. It is only enough for one read-only deep diagnostic to determine whether the WATCH row is a real weak edge or noise.

---

## 2. Why this is weak

The best M5/M15 candidate has small economic magnitude:

```text
mean net = +2.41 bps
median net = +0.59 bps
```

This is narrow relative to the execution uncertainty of XAUUSD CFD trading. Even if the average survives, it may be too small to justify paper/live exploration.

Also, there were no PASS rows:

```text
pass_count = 0
watch_count = 1
kill_count = 41
```

Therefore Stage38D does not currently justify strategy construction.

---

## 3. Candidate retained only for diagnostic

Candidate ID:

```text
D1_M5_ASIA_RANGE_BREAKOUT_LONG_FIRST_48
```

Candidate definition:

```text
timeframe = M5
baseline_family = ASIA_RANGE
baseline_name = ASIA_RANGE_BREAKOUT_LONG_FIRST
horizon_bars = 48
horizon_minutes = 240
```

Reason for keeping:

```text
- Positive mean after costs.
- Positive median.
- t-stat above watch threshold.
- 4 positive years.
- No year concentration flag in first-pass summary.
```

Reason for not promoting:

```text
- Mean is only +2.41 bps.
- Win rate is only 0.509.
- No PASS candidates exist.
- A small edge can disappear under slightly worse cost/slippage assumptions.
```

---

## 4. What the deep diagnostic must check

The next script must check the candidate against these kill criteria:

```text
1. exclude_2025_mean_net_bps must remain positive.
2. pre2025_mean_net_bps must remain positive.
3. first_half_mean_net_bps and second_half_mean_net_bps must both remain positive.
4. cost_x_1_5_mean_net_bps should remain positive.
5. cost_x_2_mean_net_bps should remain positive for research watchlist status.
6. leave-one-year-out worst mean should remain positive.
7. monthly/yearly contribution must not be dominated by one year/month.
8. drawdown should not be materially worse than expected for a tiny average edge.
```

If any of the core robustness checks fail, the candidate should be downgraded to research archive / not promotable.

---

## 5. COT handling

COT remains annotation-only.

```text
COT_IS_ENTRY_FILTER = NO
COT_IS_OVERLAY_FILTER = NO
COT_IS_CONTEXT_ANNOTATION_ONLY = YES
```

Stage38B already showed that COT/T3 did not provide a promotable edge. It should not be reintroduced as an optimization lever here.

---

## 6. Final guardrail

```text
No Stage39.
No EA.
No Telegram trade alerts.
No paper-live.
No live order.
No ML.
No optimization grid expansion.
```

Stage38D may continue only as a limited read-only diagnostic on the single WATCH candidate.
