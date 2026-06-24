# Stage38A — Local Data Audit Result v2: Coverage, Spread, and Thesis Readiness

**Project:** XAUUSD / Gold Trading System  
**Stage:** Stage38A  
**Document type:** Local data audit result based on coverage/spread output  
**Generated UTC:** 2026-06-16T12:16:17Z  
**Status:** Coverage audit reviewed; execution-cost percentile audit still required  
**Execution authorization:** NO EA, NO paper-live, NO live order, NO strategy backtest  
**Cost policy:** FREE-FIRST ONLY

---

چپ‌چین ادامه می‌دهم.

این سند نتیجه بررسی خروجی coverage audit است. این خروجی نسبت به مراحل قبلی تعیین‌کننده‌تر است، چون حالا می‌دانیم داده price، macro، spread-column population، OHLC store coverage، regime coverage و event reaction coverage در چه سطحی قرار دارند.

---

## 1. Executive Decision

نتیجه فعلی:

```text
PRICE_COVERAGE_LOCAL_AMARKETS = STRONG_PASS
PRICE_COVERAGE_PERSISTENT_TWELVEDATA = PASS_AS_BACKUP_OHLC
MACRO_DAILY_REGIME_COVERAGE = PASS
MACRO_CONTEXT_H1_COVERAGE = PASS_BUT_REGIME_LABEL_COLLAPSED_TO_NEUTRAL
EVENT_REACTION_COVERAGE = PASS_FOR_REACTION_FEASIBILITY_ONLY
SPREAD_COLUMN_POPULATION = PARTIAL_5_PERCENT_ONLY
SPREAD_DISTRIBUTION = AVAILABLE_BUT_NEEDS_PERCENTILE_TIME_COVERAGE_AUDIT
T1_PRICE_MACRO = READY_FOR_READ_ONLY_TEST_DESIGN
T1_EXECUTION_COST = BLOCKED_UNTIL_SPREAD_PERCENTILE_MODEL
T2_TRUE_SURPRISE = STILL_BLOCKED
T2_REACTION_FEASIBILITY = POSSIBLE
T3 = STILL_BLOCKED_UNTIL_FREE_COT
STAGE39_STRATEGY_CODE = NO_GO_FOR_NOW
```

تفسیر کلیدی:

```text
T1 is no longer blocked by lack of price or macro data.
T1 is now blocked only by execution-cost model and final pre-test design gate.
```

---

## 2. Local AMarkets MT5 Price Coverage

Audit output:

```text
amarkets_mt5 XAUUSD 1h rows=25,643
min_utc=2022-05-01T23:00:00+00:00
max_utc=2026-06-16T12:00:00+00:00
spread_rows=1,304
spread_pct=5.09

amarkets_mt5 XAUUSD 1m rows=1,536,273
min_utc=2022-05-01T23:01:00+00:00
max_utc=2026-06-16T12:18:00+00:00
spread_rows=79,606
spread_pct=5.18
```

### Interpretation

این داده بسیار مهم است.

از نظر price coverage:

```text
LOCAL_AMARKETS_1H = strong, multi-year, broker-consistent
LOCAL_AMARKETS_1M = strong, multi-year, broker-consistent
```

این یعنی برای T1، H1/H4/D1 structure و حتی M1-based execution checks از نظر قیمت قابل ساخت هستند.

### Concern

فقط حدود ۵٪ ردیف‌ها spread دارند.

این به معنی fail قطعی نیست؛ اما یعنی execution-cost model باید با احتیاط ساخته شود. باید بفهمیم این ۵٪ spread:

```text
1. مربوط به چه بازه زمانی است؟
2. آیا فقط داده‌های جدید spread دارند؟
3. آیا در همه sessionها پخش شده یا concentrated است؟
4. آیا در news/rollover/sunday windows نمونه دارد؟
5. آیا spread واحدش point است یا price unit؟
```

### Decision

```text
PRICE_DATA_FOR_T1 = PASS
SPREAD_DATA_FOR_COST_MODEL = PARTIAL_PASS_REQUIRES_DEEP_AUDIT
```

---

## 3. Spread Distribution

Audit output:

```text
1h spread:
min=15
avg=34.683282
max=74
spread_rows=1,304

1m spread:
min=15
avg=37.369357
max=183
spread_rows=79,606
```

### Interpretation

وجود spread واقعی در local AMarkets مثبت است.

اما فقط min/avg/max برای execution model کافی نیست. برای مدل هزینه باید داشته باشیم:

```text
p50
p75
p90
p95
p99
spread by hour UTC
spread by session
spread near rollover
spread near scheduled events
spread coverage start/end
```

### Current Cost Implication

تا وقتی واحد spread و percentileها معلوم نیستند، نمی‌توان PF threshold را دقیق کرد.

اما یک تصمیم محافظه‌کارانه می‌توان ثبت کرد:

```text
Do not use normalized TwelveData spread.
Use AMarkets spread rows as primary free broker-cost evidence.
If spread coverage is sparse or biased, use conservative synthetic stress cost.
```

### Decision

```text
EXECUTION_COST_MODEL = REQUIRED_NEXT
COST_STRESSED_PF = NOT_FINAL
```

---

## 4. Persistent TwelveData OHLC Store

Audit output:

```text
1min: 16,923 rows, 2026-05-31 to 2026-06-16
5min: 8,184 rows, 2026-05-17 to 2026-06-16
15min: 14,779 rows, 2026-01-13 to 2026-06-16
1h: 26,031 rows, 2022-05-27 to 2026-06-16
```

### Interpretation

TwelveData store is useful for clean OHLC backup and multi-timeframe structure.

But it has no usable spread:

```text
spread_available=False
spread_close blank
```

### Decision

```text
TWELVEDATA_1H = usable as OHLC backup
TWELVEDATA_INTRADAY = useful but limited coverage
TWELVEDATA_EXECUTION_COST = unusable
```

The preferred source for strategy realism remains:

```text
amarkets_mt5 local bars
```

---

## 5. Macro Daily Regime Coverage

Audit output:

```text
rows=1,620
min_date=2022-01-01
max_date=2026-06-08

neutral=853
mixed=483
hostile=173
supportive=111
```

### Interpretation

Macro daily regime coverage is strong and matches the needed historical window.

This is a major positive finding.

The project already has a macro regime table with real yield, USD, oil, CPI, PPI, Fed funds, yield curve, macro score and regime reason.

### Decision

```text
MACRO_DAILY_REGIME = PASS
T1_MACRO_FILTER_INPUT = AVAILABLE
```

### Remaining Issue

The labels are currently:

```text
neutral
mixed
hostile
supportive
```

Stage38A needs mapping to:

```text
GOLD_BULL_MACRO_TAILWIND
GOLD_BEAR_MACRO_HEADWIND
RANGE_MACRO_CONFUSION
SAFE_HAVEN_SPIKE
POSITIONING_SQUEEZE_OR_CROWDING_REVERSAL
```

Initial mapping can be:

```text
supportive -> GOLD_BULL_MACRO_TAILWIND candidate
hostile -> GOLD_BEAR_MACRO_HEADWIND candidate
mixed/neutral -> RANGE_MACRO_CONFUSION or neutral baseline
safe_haven_spike -> must be added from VIX/gold-DXY co-rise/news shock
positioning_squeeze -> requires COT/ETF later
```

---

## 6. Macro Context H1 Coverage

Audit output:

```text
rows=24,225
min_utc=2022-05-01T23:00:00+00:00
max_utc=2026-06-09T11:00:00+00:00

macro_regime:
neutral=24,225
```

### Interpretation

H1 macro context exists and covers the relevant AMarkets period. However, all rows are labeled `neutral`.

This is a problem if Stage39 tries to use `macro_context_h1.macro_regime` directly.

Possible causes:

```text
1. H1 macro context was generated before daily regime labels were enriched.
2. Macro score exists but label assignment collapsed to neutral.
3. active event logic works but regime label is not propagated.
4. Previous regime classifier was too conservative.
```

### Decision

```text
MACRO_CONTEXT_H1_TABLE = PASS_FOR_ALIGNMENT
MACRO_CONTEXT_H1_REGIME_LABEL = FAIL_AS_CURRENT_FILTER
```

### Corrective Action

Before T1 backtest, do not rely on existing H1 `macro_regime` label.

Instead:

```text
Join H1 bars to macro_daily_regime by date.
Use macro_daily_regime.supportive/hostile/mixed/neutral mapping.
Rebuild or override H1 regime labels in a read-only derived report.
```

This is not strategy mining. It is required data alignment.

---

## 7. Event Reaction Coverage

Audit output:

```text
rows=510
min_event_utc=2022-01-10T13:30:00+00:00
max_event_utc=2026-06-08T13:30:00+00:00
```

Event classes:

```text
oil_supply_shock=217
real_yield_shock=143
usd_shock=55
front_end_yield_shock=52
nominal_yield_shock=33
central_bank_gold_demand=10
```

### Interpretation

Event reaction layer is meaningful but not a true economic surprise layer.

It is mostly numeric shock/event reaction:

```text
real yield shock
front-end yield shock
USD shock
oil shock
central-bank gold demand news
```

This is useful for:

```text
T2_EVENT_REACTION_FEASIBILITY_ONLY
macro shock impact diagnostics
safe-haven / macro shock regime development
```

It is not enough for:

```text
T2_TRUE_SURPRISE_MODEL
```

because it lacks:

```text
actual
forecast
previous
consensus
surprise_z
official release timestamp
```

### Decision

```text
T2_REACTION_FEASIBILITY_ONLY = POSSIBLE
T2_TRUE_SURPRISE = BLOCKED
```

---

## 8. Stage33D Cost-Aware Prior Evidence

Audit output confirms:

```text
cost_guard_summary:
pf_x4=1.8297
avg_net_x4=1.1882
win_rate_x4=0.84
passes_cost_guard=True
```

But the candidate snapshot confirms recent degradation:

```text
last_batch_pf_x4=0.7413
last_batch_avg_net_x4=-0.9071
recent_degradation_ratio=0.3257
stage33d_decision=STAGE33D_BLOCKED_RECENT_DEGRADATION_SHORT_SHADOW_RESEARCH_ONLY
commercial_status=RESEARCH_ONLY_NO_EA_NO_PAPER_LIVE_NO_ORDER
```

### Interpretation

This validates the Stage38A decision.

The old candidate was not promoted because recent forward behavior degraded. This supports the new thesis-driven reconstruction path.

### Decision

```text
PRIOR_COST_GATING = EXISTS
RECENT_DEGRADATION = CONFIRMED
OLD_H13_H14 = MONITOR_ONLY
NO_PROMOTION = CORRECT
```

---

## 9. Updated T1 Readiness

T1 now has enough data for pre-implementation design.

### T1 Passes

```text
[PASS] AMarkets MT5 H1 data 2022-05-01 to 2026-06-16
[PASS] AMarkets MT5 1m data 2022-05-01 to 2026-06-16
[PASS] spread column exists
[PASS-PARTIAL] spread values exist
[PASS] macro_daily_regime exists 2022-01-01 to 2026-06-08
[PASS] daily macro supportive/hostile/mixed/neutral labels exist
[PASS] event reaction layer exists
```

### T1 Still Blocked By

```text
[BLOCKER] spread percentile/session/hour coverage unknown
[BLOCKER] H1 macro_context label collapsed to neutral
[BLOCKER] exact T1 test design not frozen
[BLOCKER] execution cost model not yet written
```

### T1 Decision

```text
T1_STATUS = READY_FOR_READ_ONLY_TEST_DESIGN_AFTER_EXECUTION_COST_AUDIT
```

Important:

This does not mean Stage39 strategy code is allowed.

It means the next allowed technical artifact should be:

```text
docs/STAGE38A_EXECUTION_COST_MODEL_V0.md
```

and optionally a read-only report script for spread percentiles.

---

## 10. Updated T2 Readiness

### T2 Passes

```text
[PASS] event reaction table exists
[PASS] macro shock classes exist
[PASS] ret_1h/4h/12h/24h structure exists in schema
[PASS] event coverage 2022-01-10 to 2026-06-08
```

### T2 Fails

```text
[FAIL] no forecast/consensus
[FAIL] no actual/forecast/previous/surprise_z schema
[FAIL] numeric shock timestamp is a daily proxy, not original release time
```

### T2 Decision

```text
T2_TRUE_SURPRISE = BLOCKED
T2_EVENT_REACTION_FEASIBILITY_ONLY = ALLOWED_LATER
```

No paid data. No fake surprise.

---

## 11. Updated T3 Readiness

### T3 Fails

```text
[FAIL] no COT layer
[FAIL] no ETF layer
[FAIL] no positioning percentile
```

### T3 Decision

```text
T3 = BLOCKED_UNTIL_FREE_CFTC_COT_LAYER
```

ETF is still optional for v0, but COT is mandatory.

---

## 12. Execution Cost Model Implications

The available evidence is now enough to start a free execution cost model, but not enough to finish it.

Required next statistics:

```text
spread_p50
spread_p75
spread_p90
spread_p95
spread_p99
spread by hour UTC
spread by session if session_utc available
spread by weekday
spread coverage min/max where spread is non-null
Sunday/open spread behavior
rollover-window spread behavior
```

Potential issue:

```text
spread_rows are only about 5% of bars.
If spread rows are concentrated in recent period only, use them as recent broker-cost proxy.
If spread rows are sparse but distributed, use them as observed sample.
If spread rows are biased to certain runs, add conservative synthetic spread stress.
```

Cost policy:

```text
No paid data.
Use AMarkets spread if populated.
Use conservative stress if incomplete.
Do not use TwelveData spread.
```

---

## 13. New Required Read-only Audit

Before writing `STAGE38A_EXECUTION_COST_MODEL_V0.md`, run a spread percentile audit.

Required output:

```text
1. spread non-null min/max timestamp
2. spread percentiles by timeframe
3. spread by hour UTC
4. spread by session_utc if available
5. spread by weekday
6. sample concentration by month
```

This will decide whether execution model can be evidence-based or synthetic-conservative.

---

## 14. Updated Stage38A Gate

Current gate:

```text
[PASS] multi-year AMarkets H1/H1m OHLC
[PASS] macro daily regime coverage
[PASS] event reaction coverage
[PASS-PARTIAL] spread exists
[FAIL] H1 macro context labels collapsed to neutral
[FAIL] true event surprise data
[FAIL] COT/ETF
[BLOCKED] execution cost model not finalized
[BLOCKED] T1 test design not frozen
[BLOCKED] Stage39
```

Next gate target:

```text
STAGE38A_EXECUTION_COST_MODEL_V0
```

---

## 15. Recommended Commit

After placing this file in the repo:

```bash
cd ~/Desktop/xauusd-trader
mkdir -p docs
cp ~/Downloads/STAGE38A_LOCAL_DATA_AUDIT_RESULT_V2_COVERAGE.md docs/STAGE38A_LOCAL_DATA_AUDIT_RESULT_V2_COVERAGE.md
git status --short
git add -A
git commit -m "Add Stage38A coverage and spread audit result"
git pull --rebase origin main
git push
```

---

## 16. Practical Next Step

Run the next read-only spread audit script:

```text
tools/stage38a_audit_spread_percentiles.sh
```

Then paste:

```text
data/reports/stage38a_local_data_audit/spread_percentile_audit.txt
```

After that, create:

```text
docs/STAGE38A_EXECUTION_COST_MODEL_V0.md
```

No strategy backtest before this.
