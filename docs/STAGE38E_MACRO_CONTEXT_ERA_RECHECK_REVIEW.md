# Stage38E Macro Context Era Recheck Review

**Project:** XAUUSD / Gold research  
**Stage:** Stage38E — free macro/risk data foundation  
**Status:** Read-only research review  
**Decision:** `PROCEED_TO_RESTRICTED_MACRO_CONTEXT_GATE_READ_ONLY`  

---

## 1. Executive decision

The corrected era recheck fixed the year/month concentration issue observed in the preliminary macro diagnostic.

Result:

```text
STAGE38E_MACRO_DATA_FOUNDATION = PASS
STAGE38E_MACRO_H1_JOIN = PASS
STAGE38E_MACRO_ERA_RECHECK = PASS
MACRO_CONTEXT_STANDALONE_SIGNAL = NO_GO
MACRO_CONTEXT_AS_RESTRICTED_OVERLAY = PROCEED_READ_ONLY
STAGE39 / EA / PAPER_LIVE / LIVE = NO_GO
```

The macro/risk dataset is useful and the corrected split shows several macro contexts with multi-year separation. However, this is still not a trade strategy. The next step must be a restricted event-clock gate, not a free backtest.

---

## 2. Audit result

The corrected recheck returned:

```text
status = PASS
decision = REVIEW_MACRO_CONTEXT_PASS_CANDIDATES_READ_ONLY
source_return_rows = 3219
valid_return_rows = 3210
summary_rows_written = 183
pass_count = 8
watch_count = 51
no_promotion_count = 124
warning_count = 0
note_count = 1
```

Interpretation:

- Macro/risk forward-return diagnostic is now usable for review.
- Some pass candidates exist, but they are context candidates, not entry rules.
- The pass candidates need event-clock retesting where skipped events count as zero.

---

## 3. Strongest corrected pass candidates

The following candidates passed the corrected era screen and are worth restricted gate testing.

### 3.1 Long-hostile context

```text
horizon = 120H
group_type = macro_gold_pressure
group_value = REAL_YIELD_FLAT+USD_DOWN
sample = 102
mean = -18.50 bps
median = -19.98 bps
win_rate_long = 0.471
diff_vs_all = -57.08 bps
positive_years = 3
negative_years = 2
max_positive_year_share = 0.409
exclude_2025_mean = -31.15 bps
worst_LOO_mean = -31.15 bps
```

This is the clearest **avoid-long / long-hostile** macro context. It should not be turned into a short strategy yet. Its first proper use is as a long-blocking overlay.

### 3.2 VIX-up context

```text
horizon = 120H
group_type = vix_5d_bucket
group_value = VIX_5D_UP
sample = 124
mean = +70.73 bps
median = +40.54 bps
win_rate_long = 0.581
diff_vs_all = +32.15 bps
positive_years = 5
negative_years = 0
max_positive_year_share = 0.487
exclude_2025_mean = +52.33 bps
worst_LOO_mean = +52.33 bps
```

This is a candidate for a **risk-up / gold bid** context. It is materially better than the raw `RISK_STRESS` state because sample size is larger and the era statistics are cleaner.

### 3.3 Real-yield-down / USD-flat context

```text
horizon = 120H
group_type = macro_gold_pressure
group_value = REAL_YIELD_DOWN+USD_FLAT
sample = 139
mean = +63.78 bps
median = +53.34 bps
win_rate_long = 0.597
diff_vs_all = +25.21 bps
positive_years = 5
negative_years = 0
max_positive_year_share = 0.386
exclude_2025_mean = +66.09 bps
worst_LOO_mean = +53.87 bps
```

This is the most intuitive supportive macro context: falling real yield pressure without USD strength.

### 3.4 Real 10Y yield 5D down

```text
horizon = 120H
group_type = real_yield_5d_bucket
group_value = REAL_5D_DOWN
sample = 306
mean = +50.79 bps
median = +52.05 bps
win_rate_long = 0.582
diff_vs_all = +12.21 bps
positive_years = 4
negative_years = 1
max_positive_year_share = 0.362
exclude_2025_mean = +48.20 bps
worst_LOO_mean = +41.19 bps
```

This is broader and more robust than the narrower pressure states. It may be useful as a macro context label even if the narrow policies fail event-clock uplift.

---

## 4. Important cautions

### 4.1 This is not an entry system

The test measures forward returns from macro observation events. It does not specify:

- entry timing,
- stop-loss,
- take-profit,
- trade construction,
- spread/slippage interaction,
- intraday confirmation,
- broker execution realism.

Therefore:

```text
MACRO_CONTEXT_STANDALONE_SIGNAL = NO_GO
```

### 4.2 Event-clock uplift is still unknown

High trade-mean inside a selected context can be misleading. A context is only useful as an overlay if it improves event-clock performance after skipped events are counted as zero.

The next test must compare:

```text
BASELINE_ALL_EVENTS
vs
LONG_PERMITTED / LONG_BLOCKED / LONG_ONLY macro context policies
```

### 4.3 No free optimization

Only a small set of policies directly derived from the corrected pass candidates should be tested. No threshold search, no ML, no Stage39, no EA, no paper-live.

---

## 5. Restricted gate candidates

The next script should test only these policies:

```text
BASELINE_ALWAYS_LONG
BLOCK_REAL_YIELD_FLAT_USD_DOWN
LONG_ONLY_VIX_5D_UP
LONG_ONLY_REAL_YIELD_DOWN_USD_FLAT
LONG_ONLY_REAL_5D_DOWN
LONG_PERMITTED_EXCLUDE_REAL_YIELD_FLAT_USD_DOWN
```

Primary horizon:

```text
120H
```

Secondary horizon:

```text
72H
```

24H may remain diagnostic only because macro data is daily and its effect is usually not an intraday edge by itself.

---

## 6. Promotion rule

A macro gate can only proceed to a baseline-context design if it satisfies all of the following:

```text
event_clock_uplift_vs_baseline >= +8 bps
trade_count >= 60
positive_year_count >= 3
max_positive_year_share <= 0.55
worst_leave_one_year_out_event_clock_mean > 0
no lookahead violations
```

Otherwise Stage38E remains only a data foundation and context annotation layer.

---

## 7. Next artifact

```text
app/stage38e_macro_context_pass_candidate_gate.py
```

Purpose:

```text
Restricted read-only event-clock gate for corrected macro pass candidates.
No strategy. No backtest. No ML. No Stage39. No paper/live.
```
