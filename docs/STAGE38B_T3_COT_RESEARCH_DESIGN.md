# Stage38B / T3 COT Research Design — Gold Positioning Foundation

**Project:** XAUUSD / Gold Trading System  
**Stage:** Stage38B  
**Thesis track:** T3 — COT positioning / crowding / squeeze / unwind  
**Mode:** research-only / read-only  
**Trading status:** NO-GO for Stage39, EA, paper-live, and live order  
**Generated:** 2026-06-16  

---

## 1. Purpose

This document locks the research design for T3 before any backtest is written.

The objective is not to create an immediate trading system. The objective is to determine whether free CFTC COT data adds explanatory or filtering value to XAUUSD H1 research after strict anti-lookahead alignment.

T3 should answer one narrow question first:

```text
Does gold futures positioning, especially Managed Money positioning and crowding,
help identify better or worse regimes for XAUUSD intraday/short-horizon baselines?
```

This is a data foundation and hypothesis-testing stage, not an execution stage.

---

## 2. Current validated data state

### 2.1 COT ingestion

Validated CFTC COT gold data:

```text
contract = GOLD - COMMODITY EXCHANGE INC.
cftc_contract_market_code = 088691
rows = 910
as_of_date range = 2009-01-06 to 2026-06-09
available_from_utc range = 2009-01-09T20:30:00Z to 2026-06-12T19:30:00Z
loader_status = LOADED
warnings = 0
notes = 2
```

SQLite tables created:

```text
cot_gold_weekly
cot_gold_features
cot_gold_ingest_audit
```

### 2.2 COT-to-H1 anti-lookahead join

Validated H1 join:

```text
status = PASS
bars_total = 25,643
joined_count = 25,643
unjoined_count = 0
lookahead_violation_count = 0
first_joined_bar_ts_utc = 2022-05-01T23:00:00Z
last_joined_bar_ts_utc = 2026-06-16T12:00:00Z
warnings = 0
notes = 1
```

SQLite tables created:

```text
cot_gold_h1_features_joined
cot_gold_h1_join_audit
```

### 2.3 T3 COT feature audit

Validated feature states:

```text
status = PASS
bars_total = 25,643
feature_rows_written = 25,643
lookahead_violation_count = 0
warning_count = 0
note_count = 1
```

State distribution:

```text
MM_NEUTRAL        = 13,598
MM_LONG_CROWDED   = 6,157
MM_SHORT_CROWDED  = 3,355
MM_EXTREME_LONG   = 1,331
MM_EXTREME_SHORT  = 1,202
```

SQLite tables created:

```text
cot_gold_t3_feature_states
cot_gold_t3_feature_audit
```

---

## 3. Hard scope limits

T3 must remain inside these limits:

```text
NO Stage39
NO EA
NO paper-live
NO live order
NO Telegram trade alert
NO order simulation that implies readiness
NO ML model
NO parameter mining over many thresholds
NO promotion based on one year or one month
```

Allowed:

```text
read-only data audit
feature sanity checks
baseline interaction tests
state-conditioned return diagnostics
cost-aware research metrics
kill/pass decision for whether T3 deserves further research
```

---

## 4. Anti-lookahead rule

The following rule is mandatory in every T3 test:

```text
For an H1 bar with timestamp T,
only COT records with cot_available_from_utc <= T are allowed.
```

Never join by this unsafe condition alone:

```text
cot_as_of_date <= bar_date
```

Reason:

```text
COT reports describe Tuesday positioning but are published later.
Using Tuesday data before its Friday release creates lookahead bias.
```

Every output table/report must include:

```text
lookahead_violation_count
```

The only acceptable value is:

```text
0
```

---

## 5. Core feature concepts

The first T3 design uses only simple, interpretable COT features.

### 5.1 Managed Money net positioning

Main variables:

```text
m_money_net_all
m_money_net_pct_oi
m_money_net_zscore_156w
```

Interpretation:

```text
positive net = Managed Money net long gold futures
negative net = Managed Money net short gold futures
higher pct_oi = larger position relative to open interest
zscore_156w = 3-year relative crowding context
```

### 5.2 COT state

Locked state labels from feature audit:

```text
MM_NEUTRAL
MM_LONG_CROWDED
MM_SHORT_CROWDED
MM_EXTREME_LONG
MM_EXTREME_SHORT
```

Primary use:

```text
condition baseline results by state
compare return/risk/trade quality across states
identify whether crowded/extreme states are helpful filters or danger zones
```

### 5.3 COT pressure / flow

Current feature audit shows recent rows with:

```text
cot_pressure = FLOW_UNKNOWN
```

This should not block Stage38B, but it means T3 must initially avoid relying on flow labels as the primary thesis.

Initial T3 priority:

```text
positioning level / crowding state first
flow/unwind second
```

Flow-based features can be revisited after confirming exact weekly change columns and reconstruction quality.

---

## 6. Research hypotheses

### H1 — Crowded long caution thesis

Hypothesis:

```text
When Managed Money is extremely long or long-crowded,
new long breakouts may have weaker forward expectancy or higher reversal risk,
especially after large recent gold advances.
```

Expected diagnostic signal:

```text
Long-baseline performance deteriorates in MM_EXTREME_LONG or MM_LONG_CROWDED
relative to MM_NEUTRAL.
```

This is a caution/filter thesis, not an automatic short thesis.

### H2 — Short crowded squeeze thesis

Hypothesis:

```text
When Managed Money is short-crowded or extreme short,
upside continuation/breakout baselines may improve because short covering can amplify upward moves.
```

Expected diagnostic signal:

```text
Long-baseline performance improves in MM_SHORT_CROWDED or MM_EXTREME_SHORT
relative to MM_NEUTRAL.
```

### H3 — Neutral positioning trend-follow thesis

Hypothesis:

```text
When Managed Money positioning is neutral,
price/trend baselines may behave more cleanly because there is less crowding pressure.
```

Expected diagnostic signal:

```text
Trend-following or range-breakout baseline has more stable expectancy in MM_NEUTRAL
than in extreme states.
```

### H4 — COT alone is not a timing signal

Hypothesis:

```text
COT state alone is too slow for direct H1 trade timing.
It may work as a regime filter, not as a standalone entry trigger.
```

Expected diagnostic signal:

```text
State-only forward returns are noisy,
but state-conditioned baseline results show meaningful differences.
```

This hypothesis protects the project from overusing slow weekly data as a precise intraday trigger.

---

## 7. Baselines to test under COT states

T3 must not invent many new strategies. It should first test COT as a filter around simple baselines.

Minimum baseline set:

```text
B1: H1 forward return by COT state only
B2: D1 trend bias + H1 forward return by COT state
B3: H1 momentum continuation by COT state
B4: ATR/range expansion by COT state
B5: previous-day high breakout by COT state
B6: previous-day low breakdown by COT state
```

Important:

```text
B1 is diagnostic only.
B2-B6 are baseline interaction tests.
None of them is a promotable strategy at this stage.
```

---

## 8. Evaluation horizons

Because COT is weekly and slow, do not evaluate only one very short horizon.

Required horizons:

```text
H1 forward 1 bar
H1 forward 4 bars
H1 forward 8 bars
H1 forward 24 bars
H1 forward 48 bars
```

Interpretation:

```text
1-4 bars: intraday reaction / noise check
8-24 bars: short-horizon trading relevance
48 bars: slower COT regime relevance
```

T3 should prefer consistency across 8/24/48 bars over isolated 1-bar effects.

---

## 9. Cost model

Stage38A established that raw-only evaluation is not acceptable.

T3 diagnostics must report both:

```text
raw forward return
cost-adjusted forward return
```

Use the existing Stage38A cost model unless explicitly superseded:

```text
stress_p90_spread_price_distance = 0.49
```

For simple direction-conditioned diagnostics:

```text
long_cost_adjusted_return = forward_return - 0.49
short_cost_adjusted_return = -forward_return - 0.49
```

For pure state diagnostics without entry direction:

```text
report raw forward returns first
only apply cost when a directional baseline creates a trade-like event
```

---

## 10. Metrics

Every T3 diagnostic table must include:

```text
sample_count
mean_return
median_return
win_rate
p25_return
p75_return
std_return
sum_return
max_drawdown_proxy
```

For event-like baselines:

```text
trade_count
avg_R_or_avg_cost_adjusted_return
win_rate
profit_factor_proxy
net_return
max_drawdown_proxy
annual_breakdown
era_breakdown
state_breakdown
```

Required breakdowns:

```text
by cot_state
by year
by cot_state + year
by session if session tag is available
```

---

## 11. Minimum sample rules

No conclusion is allowed from tiny groups.

Minimum reporting thresholds:

```text
state-level forward-return diagnostic: at least 500 H1 bars
state-level event baseline: at least 30 events
state+year event cell: at least 10 events before interpreting
```

If a state has fewer samples:

```text
mark as LOW_SAMPLE_DIAGNOSTIC_ONLY
```

---

## 12. Era dominance controls

T1 failed promotion because it was dominated by 2025.

T3 must explicitly prevent the same mistake.

Required era checks:

```text
FULL
EXCLUDE_2025
ERA_2025_ONLY
PRE_2025
POST_2024
```

Required dominance metrics:

```text
max_year_positive_contribution_share
max_month_positive_contribution_share
```

Hard caution threshold:

```text
If one year contributes more than 65% of positive contribution,
mark the result as ERA_DOMINATED_LOW_CONFIDENCE.
```

Hard block threshold:

```text
If a result is negative excluding 2025,
mark it as NOT_PROMOTABLE regardless of full-period performance.
```

---

## 13. Pass / watch / kill criteria

### PASS_RESEARCH_INTEREST

A T3 condition or filter can pass research interest only if:

```text
1. lookahead_violation_count = 0
2. sample size is adequate
3. result is positive after stress-p90 cost where trade-like
4. result is not purely 2025-dependent
5. same directional idea is not contradicted by most years
6. state-conditioned result beats unconditional baseline
```

### WATCH_ONLY

Use WATCH_ONLY if:

```text
result is positive but sample is thin
or result is positive but era/month concentration is high
or result improves risk but not return
or effect exists only in one horizon
```

### KILL

Kill a T3 idea if:

```text
lookahead violation > 0
unconditional baseline beats COT-filtered baseline
cost-adjusted result is negative
result disappears excluding 2025
state effect is inconsistent across horizons
sample count is too low for interpretation
```

---

## 14. Deliverables

The next implementation step should create:

```text
app/stage38b_t3_cot_research_diagnostic.py
```

Expected output directory:

```text
data/reports/stage38b_t3_cot_research_diagnostic/
```

Expected reports:

```text
stage38b_t3_cot_research_diagnostic.json
stage38b_t3_cot_research_diagnostic.md
```

Expected SQLite tables:

```text
cot_gold_t3_forward_returns
cot_gold_t3_state_diagnostics
cot_gold_t3_baseline_diagnostics
cot_gold_t3_research_audit
```

---

## 15. Implementation order

Do not jump directly to variant mining.

Implementation order:

```text
1. Build forward-return diagnostic by COT state.
2. Add D1/H4 trend context if already available in DB.
3. Add simple event baselines one by one.
4. Compare COT-conditioned vs unconditional baseline.
5. Run era ablation.
6. Decide PASS/WATCH/KILL for T3.
```

---

## 16. Immediate next command target

After committing this document, build:

```text
app/stage38b_t3_cot_research_diagnostic.py
```

First version scope:

```text
COT state only + forward returns
no entry strategy
no optimization
no ML
no paper/live
```

This first diagnostic should answer:

```text
Are raw forward returns materially different across MM_NEUTRAL,
MM_LONG_CROWDED, MM_SHORT_CROWDED, MM_EXTREME_LONG,
and MM_EXTREME_SHORT after anti-lookahead alignment?
```

If no meaningful state separation exists, T3 should be downgraded before deeper strategy testing.

---

## 17. Current project decision

Current decision after Stage38B feature audit:

```text
Stage38B COT data foundation: PASS so far
T3 research diagnostic: GO
Stage39: NO-GO
EA: NO-GO
paper-live: NO-GO
live order: NO-GO
```
