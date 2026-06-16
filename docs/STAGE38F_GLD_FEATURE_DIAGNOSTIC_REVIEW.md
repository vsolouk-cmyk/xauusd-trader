# Stage38F GLD Feature Diagnostic Review

**Project:** XAUUSD / Gold Trading System  
**Stage:** Stage38F — Gold ETF / GLD Flow Data Foundation  
**Status:** Read-only research review  
**Decision date:** 2026-06-16  
**Active trading status:** NO-GO for Stage39, EA, paper-live, and live order

---

## 1. Executive decision

```text
STAGE38F_SPDR_GLD_LOADER = PASS
STAGE38F_GLD_FEATURE_DIAGNOSTIC = PASS_WITH_GATE_REQUIRED
GLD_STANDALONE_SIGNAL = NO-GO
GLD_CONTEXT_GATE = PROCEED_READ_ONLY
STAGE39 / EA / PAPER_LIVE / LIVE = NO-GO
```

The GLD loader and H1 anti-lookahead join are usable. The GLD context diagnostic is materially more interesting than the previous COT and macro gates because several GLD contexts show multi-year separation, positive medians, acceptable sample sizes, and non-trivial differentials versus the all-event reference.

However, this is still not a trading strategy. The next step must be an event-clock gate. Any subset-only result must be penalized by counting skipped events as zero. No promotion is allowed from trade-mean alone.

---

## 2. Data foundation status

Confirmed from the loader output:

```text
parsed_rows = 5,425
daily_rows_written = 5,425
feature_rows_written = 5,425
h1_joined_count = 25,643 / 25,643
h1_unjoined_count = 0
lookahead_violation_count = 0
date_range = 2004-11-18 to 2026-06-15
```

Operational interpretation:

```text
GLD daily holdings and flow features are now usable as context data.
The H1 join is anti-lookahead safe.
The data foundation can remain in the project even if no edge is promoted.
```

---

## 3. Diagnostic result summary

The feature diagnostic returned:

```text
status = PASS
decision = REVIEW_GLD_CONTEXT_PASS_CANDIDATES_READ_ONLY
event_count = 1,034
returns_written = 3,096
pass_count = 13
watch_count = 23
no_promotion_count = 78
```

This is not a strategy pass. It is a context-separation pass that requires restricted gate validation.

---

## 4. Most important pass candidates

### 4.1 ETF_STRONG_OUTFLOW / 120H

```text
group_type = gld_flow_state
group_value = ETF_STRONG_OUTFLOW
sample = 197
mean = +80.90 bps
median = +49.81 bps
win_rate = 0.599
t_stat = 4.85
diff_vs_all = +43.34 bps
positive_years = 5
negative_years = 0
max_positive_year_share = 0.352
pre2025_mean = +63.39 bps
exclude_2025_mean = +75.27 bps
worst_leave_one_year_out = +67.94 bps
```

Interpretation:

```text
This is the strongest broad GLD context candidate.
It is counterintuitive at first glance: strong GLD outflow is followed by positive gold returns.
Possible thesis: liquidation/exhaustion, capitulation, or flow reversal setup.
It must not be treated as an entry signal before event-clock validation.
```

### 4.2 ETF_STRONG_INFLOW / 120H

```text
group_type = gld_flow_state
group_value = ETF_STRONG_INFLOW
sample = 132
mean = +71.64 bps
median = +105.34 bps
win_rate = 0.629
t_stat = 2.52
diff_vs_all = +34.09 bps
positive_years = 5
negative_years = 0
max_positive_year_share = 0.433
pre2025_mean = +114.66 bps
exclude_2025_mean = +95.67 bps
worst_leave_one_year_out = +58.74 bps
```

Interpretation:

```text
This is a more intuitive momentum/confirmation context.
It has fewer observations than broad baseline but is still large enough for a gate.
```

### 4.3 FLOW_5D_INFLOW / 120H

```text
group_type = gld_flow_5d_bucket
group_value = FLOW_5D_INFLOW
sample = 174
mean = +67.05 bps
median = +50.43 bps
win_rate = 0.626
t_stat = 4.02
diff_vs_all = +29.49 bps
positive_years = 4
negative_years = 1
max_positive_year_share = 0.463
exclude_2025_mean = +47.52 bps
worst_leave_one_year_out = +47.52 bps
```

Interpretation:

```text
This is a plausible flow-confirmation context.
It is not as clean as the strong-flow state groups but remains gate-worthy.
```

### 4.4 FLOW_20D_STRONG_OUTFLOW / 120H

```text
group_type = gld_flow_20d_bucket
group_value = FLOW_20D_STRONG_OUTFLOW
sample = 271
mean = +62.06 bps
median = +46.27 bps
win_rate = 0.583
t_stat = 4.61
diff_vs_all = +24.50 bps
positive_years = 5
negative_years = 0
max_positive_year_share = 0.366
exclude_2025_mean = +56.31 bps
worst_leave_one_year_out = +49.78 bps
```

Interpretation:

```text
This supports the exhaustion/capitulation thesis.
It is broad enough to test as a context gate.
```

### 4.5 FLOW_20D_STRONG_INFLOW / 24H and watch at longer horizons

The 24H version passed:

```text
sample = 196
mean = +30.61 bps
diff_vs_all = +23.34 bps
positive_years = 5
negative_years = 0
```

But the 72H and 120H rows were watch, not pass, due to year concentration. This is still worth including as a diagnostic gate, but not as a lead policy.

---

## 5. Important negative/watch contexts

The most relevant hostile context is:

```text
gld_flow_20d_bucket = FLOW_20D_OUTFLOW
120H mean = -38.51 bps
median = -32.38 bps
win_rate = 0.442
diff_vs_all = -76.07 bps
positive_years = 2
negative_years = 3
```

This is not a long entry. It is potentially useful as an avoid-long filter. It should be tested in the gate as a block policy:

```text
BLOCK_FLOW_20D_OUTFLOW
```

---

## 6. Why this does not promote directly

Direct promotion is blocked because:

```text
1. The diagnostic is context-only.
2. It measures subset performance, not event-clock portfolio value.
3. Skipped events must be counted as zero in any realistic overlay comparison.
4. GLD context may be useful only as an overlay, not as an entry trigger.
5. No forward shadow exists.
```

The next step must be:

```text
stage38f_gld_context_pass_candidate_gate.py
```

---

## 7. Gate policies to test

The next gate should compare these policies against an event-clock always-long reference:

```text
BASELINE_ALWAYS_LONG
LONG_ONLY_ETF_STRONG_OUTFLOW
LONG_ONLY_ETF_STRONG_INFLOW
LONG_ONLY_FLOW_5D_INFLOW
LONG_ONLY_FLOW_20D_STRONG_OUTFLOW
LONG_ONLY_FLOW_20D_STRONG_INFLOW
LONG_ONLY_FLOW_1D_FLAT
BLOCK_FLOW_20D_OUTFLOW
LONG_PERMITTED_EXCLUDE_ETF_OUTFLOW_OR_FLOW20_OUTFLOW
```

Rules:

```text
Skipped event = 0 bps
No leverage
No compounding
No cost optimization
No entry/exit optimization
No ML
```

Promotion criteria for watchlist only:

```text
event_clock_uplift_vs_baseline >= +8 bps
worst_leave_one_year_out_event_clock_mean > 0
positive_year_count >= 4
max_positive_year_share <= 0.55
trade_count >= 60
```

If these fail, Stage38F remains only a data/context foundation.

---

## 8. Current final status before gate

```text
STAGE38F_DATA = KEEP
GLD_CONTEXT = GATE_REQUIRED
GLD_STANDALONE_SIGNAL = NO-GO
STAGE39 = NO-GO
EA = NO-GO
PAPER_LIVE = NO-GO
LIVE_ORDER = NO-GO
```
