# Stage38A — Local Data Audit Result v1: Schema and Header Review

**Project:** XAUUSD / Gold Trading System  
**Stage:** Stage38A  
**Document type:** Local data audit result based on SQLite schema and CSV headers  
**Generated UTC:** 2026-06-16T12:06:47Z  
**Status:** Partial audit result — schema/header reviewed, row counts still required  
**Execution authorization:** NO EA, NO paper-live, NO live order, NO strategy backtest  
**Cost policy:** FREE-FIRST ONLY

---

چپ‌چین ادامه می‌دهم.

این سند نتیجه بررسی خروجی schema دیتابیس‌ها و header فایل‌های CSV است.

ورودی بررسی‌شده شامل این دو بخش بود:

```text
1. SQLite schema for:
   data/local/xauusd_local_store.sqlite
   data/store/xauusd.sqlite

2. CSV headers/samples for:
   data/exogenous/*.csv
   data/macro/events/*.csv
   data/macro/series/*.csv
   data/normalized/*.csv
   data/reports/stage33d_strict_cost_aware_pre_paper_gate/*.csv
```

این audit هنوز کامل نیست، چون row count، min/max timestamp، coverage، null-rate spread و کیفیت gap/duplicate بررسی نشده‌اند. اما از همین schema/header چند تصمیم مهم به دست آمد.

---

## 1. Executive Decision

نتیجه فعلی:

```text
LOCAL_STORE_SCHEMA = STRONG
PERSISTENT_STORE_SCHEMA = PRICE_ONLY_NO_SPREAD
MACRO_LAYER = STRONG_AND_USABLE_FOR_T1
MACRO_DAILY_REGIME = ALREADY_EXISTS
EVENT_LAYER = PRESENT_BUT_NOT_TRUE_SURPRISE
FORECAST_CONSENSUS = NOT_FOUND
NORMALIZED_TWELVEDATA_SPREAD = NOT_AVAILABLE
STAGE33D_COST_REPORTS = PRESENT_BUT_NOT_FULL_EXECUTION_MODEL
T1 = CONDITIONAL_GO_AFTER_ROWCOUNT_AND_SPREAD_AUDIT
T2_TRUE_SURPRISE = BLOCKED
T2_EVENT_REACTION_FEASIBILITY_ONLY = POSSIBLE
T3 = BLOCKED_UNTIL_COT
STAGE39 = NO_GO_FOR_NOW
```

مهم‌ترین یافته:

```text
data/local/xauusd_local_store.sqlite has a bars table with a spread column.
```

اما در فایل‌های normalized TwelveData مقدار زیر دیده شد:

```text
spread_available = False
spread_close = blank
```

پس برای execution cost model نباید روی فایل‌های normalized TwelveData حساب کنیم. باید ببینیم ستون `spread` در جدول `bars` واقعاً پر است یا نه.

---

## 2. Database 1 — data/local/xauusd_local_store.sqlite

### 2.1 Tables Found

این دیتابیس بسیار غنی‌تر از یک price store ساده است.

Tables:

```text
bars
dryrun_signals
dryrun_outcomes
import_runs
macro_events
macro_context_h1
macro_numeric_observations
macro_update_runs
macro_daily_regime
news_events
news_event_reactions
news_event_class_weights
event_pipeline_staging
event_pipeline_runs
event_impact_validation_summary
numeric_shock_events
numeric_shock_event_runs
```

### 2.2 Key Table: bars

Schema:

```text
source TEXT NOT NULL
symbol TEXT NOT NULL
timeframe TEXT NOT NULL
utc_time TEXT NOT NULL
open REAL NOT NULL
high REAL NOT NULL
low REAL NOT NULL
close REAL NOT NULL
tick_volume REAL
spread REAL
real_volume REAL
source_time TEXT
imported_utc TEXT NOT NULL
raw_json TEXT
volume REAL
ingested_at TEXT
PRIMARY KEY (source, symbol, timeframe, utc_time)
```

Decision:

```text
PRICE_DATA_SCHEMA = PASS
SPREAD_COLUMN_EXISTS = YES
ROW_COUNT_COVERAGE_NEEDED = YES
SPREAD_NONNULL_COUNT_NEEDED = YES
```

This is the most important table for Stage38A/T1.

### 2.3 Macro Regime Tables

`macro_daily_regime` already exists and includes:

```text
obs_date
real_yield_10y
nominal_yield_10y
nominal_yield_2y
usd_index
wti
brent
cpi
ppi
fedfunds
d_real_yield_5d
d_real_yield_20d
d_usd_5d_pct
d_usd_20d_pct
d_oil_5d_pct
d_oil_20d_pct
yield_curve_10y2y
rate_pressure_score
usd_pressure_score
oil_inflation_pressure_score
growth_fear_score
macro_score_long_gold
macro_regime
regime_reason
generated_utc
```

This is very important.

Interpretation:

```text
A Stage38-style macro regime foundation already exists.
It is not enough by itself, but it can be reused/audited rather than rebuilt from scratch.
```

Decision:

```text
MACRO_DAILY_REGIME_SCHEMA = PASS
T1_MACRO_REGIME_INPUT = LIKELY_AVAILABLE
REGIME_LOGIC_REVIEW_REQUIRED = YES
```

### 2.4 Macro Context H1

`macro_context_h1` includes:

```text
utc_time
macro_score
macro_regime
active_event_count
active_event_ids
active_labels
has_block_event
generated_utc
```

Interpretation:

```text
The project already has an H1-aligned macro context layer.
This may reduce Stage39 implementation work for T1.
```

Decision:

```text
H1_MACRO_ALIGNMENT_SCHEMA = PRESENT
COVERAGE_CHECK_REQUIRED = YES
```

### 2.5 News/Event Reaction Tables

`news_event_reactions` includes:

```text
event_id
event_time_utc
title
event_class
event_channel
expected_gold_direction
macro_regime_numeric
macro_score_long_gold
anchor_bar_utc
anchor_price
ret_1h
ret_4h
ret_12h
ret_24h
mfe_12h
mae_12h
normalized_impact_4h
normalized_impact_12h
realized_direction_4h
realized_direction_12h
direction_match_4h
direction_match_12h
adaptive_score
verdict
```

Interpretation:

```text
Event reaction feasibility exists.
True surprise modeling does not yet exist because actual/forecast/previous/surprise_z are absent from the shown schema.
```

Decision:

```text
T2_EVENT_REACTION_FEASIBILITY = POSSIBLE
T2_TRUE_SURPRISE = BLOCKED
```

---

## 3. Database 2 — data/store/xauusd.sqlite

Tables:

```text
store_metadata
candles_i_1min
candles_i_5min
candles_i_15min
candles_i_1h
```

Schema for candle tables:

```text
time_utc TEXT PRIMARY KEY
open REAL NOT NULL
high REAL NOT NULL
low REAL NOT NULL
close REAL NOT NULL
volume REAL
symbol TEXT NOT NULL
interval TEXT NOT NULL
provider TEXT NOT NULL
session_utc TEXT
fetched_at_utc TEXT
updated_at_utc TEXT NOT NULL
```

Interpretation:

```text
This store is a clean OHLC store for 1min/5min/15min/1h.
It does not include spread, bid, or ask.
It is useful for price structure, MTF derivation, and event reaction windows.
It is not sufficient for execution cost modeling by itself.
```

Decision:

```text
OHLC_STORE = PASS
SPREAD_IN_STORE = FAIL
T1_STRUCTURE_DATA = LIKELY_AVAILABLE
T2_REACTION_WINDOWS = POSSIBLE_IF_COVERAGE_SUFFICIENT
EXECUTION_COST_FROM_THIS_STORE = NO
```

---

## 4. Normalized TwelveData Files

Headers show:

```text
time_utc
open
high
low
close
volume
symbol
interval
provider
source_file
fetched_at_utc
spread_available
spread_close
session_utc
```

Sample rows show:

```text
spread_available = False
spread_close = blank
```

Interpretation:

```text
TwelveData normalized files are useful for OHLC and session labels.
They are not useful for real spread modeling.
```

Decision:

```text
NORMALIZED_TWELVEDATA_OHLC = PASS
NORMALIZED_TWELVEDATA_SPREAD = FAIL
```

This directly confirms the senior-review concern: execution realism cannot rely on these normalized files.

---

## 5. Macro / Exogenous Layer

### 5.1 Exogenous Files

Found and sampled:

```text
data/exogenous/dxy.csv
data/exogenous/oil.csv
data/exogenous/real_yield.csv
data/exogenous/spx.csv
data/exogenous/us10y.csv
data/exogenous/vix.csv
```

Headers:

```text
timestamp,close
```

Start examples:

```text
2022-05-02
```

Manifest shows downloaded rows:

```text
DTWEXBGS/dxy: 1025 rows
DGS10/us10y: 1028 rows
DFII10/real_yield: 1028 rows
VIXCLS/vix: 1062 rows
```

Decision:

```text
EXOGENOUS_DAILY_LAYER = PASS
T1_DFII10_DXY_VIX = LIKELY_AVAILABLE
```

### 5.2 Macro Series Files

Found and sampled:

```text
CPIAUCSL
DCOILBRENTEU
DCOILWTICO
DFII10
DGS10
DGS2
DTWEXBGS
FEDFUNDS
PAYEMS
PPIACO
UNRATE
```

Headers:

```text
source
series_id
date
value
realtime_start
realtime_end
label
category
gold_driver
update_frequency
units_hint
fetched_utc
ssl_mode
```

Interpretation:

```text
The macro layer is strong enough for Stage38A/T1 regime filtering.
It includes real yield, broad USD, yields, Fed funds, CPI, payrolls, unemployment, oil, and PPI.
```

Important limitation:

```text
FRED macro series give actual values and historical observations.
They do not provide economic-calendar consensus forecasts.
```

Decision:

```text
T1_MACRO_REQUIREMENT = PASS_AFTER_COVERAGE_CONFIRMATION
T2_ACTUAL_PREVIOUS_PARTIAL = POSSIBLE
T2_FORECAST_CONSENSUS = STILL_MISSING
```

---

## 6. Event Layer

### 6.1 calendar_events.csv

Header:

```text
timestamp,event,importance,currency
```

Sample:

```text
2026-01-01T13:30:00Z,example_cpi_or_fomc_or_nfp,high,USD
```

Interpretation:

```text
This looks like a placeholder/example, not a complete historical event calendar.
```

Decision:

```text
calendar_events.csv = NOT_ENOUGH_FOR_T2
```

### 6.2 stage10b_scheduled_events_normalized.csv

Header includes:

```text
event_id
event_time_utc
event_end_utc
title
event_class
event_channel
expected_gold_direction
initial_importance
confidence
source_name
source_url_or_note
manual_tags
notes
source_kind
dedupe_key
```

Samples are scheduled FOMC events in 2026.

Interpretation:

```text
Useful for future scheduled event blocking and FOMC windows.
Not enough for historical surprise modeling.
```

### 6.3 GDELT / Detected News Events

Files include central-bank-gold-demand news, often from Chinese sources, with low confidence and notes requiring validation.

Interpretation:

```text
Useful as candidate narrative/news layer.
Not reliable enough as a trade signal without validation.
```

### 6.4 numeric_shock_events

Samples include:

```text
DFII10 real_yield_shock
DGS2 front_end_yield_shock
DCOILBRENTEU oil_supply_shock
```

Important note in file:

```text
timestamp is a daily-shock proxy, not original news release time
```

Interpretation:

```text
This can help macro shock analysis.
It cannot replace real economic release timestamps.
```

Decision:

```text
EVENT_LAYER = PARTIAL
MACRO_SHOCK_LAYER = USEFUL
TRUE_EVENT_SURPRISE = NOT_AVAILABLE
T2_TRUE_SURPRISE = BLOCKED
T2_REACTION_FEASIBILITY = POSSIBLE_WITH_LIMITATIONS
```

---

## 7. Prior Cost-Aware Reports

Stage33D files show:

```text
cost_guard_summary.csv
gate_checks.csv
prepaper_candidate_snapshot.csv
recent_degradation_diagnostics.csv
```

Key sample findings:

```text
cost_penalty_x4 = 1.0
pf_x4 = 1.8297
avg_net_x4 = 1.1882
win_rate_x4 = 0.84
passes_cost_guard = True
```

But candidate snapshot shows:

```text
last_batch_pf_x4 = 0.7413
last_batch_avg_net_x4 = -0.9071
recent_degradation_ratio = 0.3257
stage33d_decision = STAGE33D_BLOCKED_RECENT_DEGRADATION_SHORT_SHADOW_RESEARCH_ONLY
commercial_status = RESEARCH_ONLY_NO_EA_NO_PAPER_LIVE_NO_ORDER
```

Interpretation:

```text
The project already had a cost-aware gate.
But this is not the same as the senior-review-required execution model.
It used aggregate cost penalty and candidate metrics, not a full spread/slippage/rollover/gap model.
```

Decision:

```text
PRIOR_COST_GATE = PRESENT
FULL_EXECUTION_COST_MODEL = STILL_REQUIRED
RECENT_DEGRADATION_CONCERN = CONFIRMED
```

---

## 8. T1/T2/T3 Readiness Update

### 8.1 T1 — Regime-filtered Structure Continuation

Status:

```text
T1 = CONDITIONAL GO AFTER ROWCOUNT + SPREAD NONNULL + COVERAGE AUDIT
```

Reasons:

```text
OHLC exists.
H1/H4/D1 likely derivable.
Macro daily regime already exists.
Macro context H1 already exists.
Real yield and USD proxy exist.
```

Remaining blockers:

```text
1. bars table row count by source/symbol/timeframe
2. min/max utc_time by timeframe
3. spread non-null count and distribution
4. H1 coverage length
5. broker/provider consistency
6. whether H4/D1 derivation is stable
```

T1 is still the best first thesis after audit.

---

### 8.2 T2 — Event Surprise Follow-through / Fade

Status:

```text
T2_TRUE_SURPRISE = BLOCKED
T2_EVENT_REACTION_FEASIBILITY_ONLY = POSSIBLE
```

Reasons:

```text
Event/reaction tables exist.
Macro shock events exist.
Reaction returns 1h/4h/12h/24h exist in schema.
```

Blockers:

```text
No actual/forecast/previous/surprise_z schema shown.
calendar_events.csv appears placeholder.
numeric shocks are daily-shock proxies, not original release times.
forecast/consensus not found.
```

Allowed limited path:

```text
Use existing news_event_reactions only as event reaction feasibility.
Do not call it event surprise.
```

---

### 8.3 T3 — Positioning Squeeze / Exhaustion

Status:

```text
T3 = BLOCKED UNTIL FREE COT LAYER
```

Reasons:

```text
No COT/CFTC/positioning files found in audit.
No ETF/GLD/IAU/WGC files found.
```

Allowed next step later:

```text
Free CFTC COT layer.
ETF optional for v0.
```

---

## 9. Execution Realism Update

The senior review remains valid.

Current status:

```text
SPREAD_COLUMN_IN_LOCAL_BARS = YES
SPREAD_VALUES_CONFIRMED = NO
TWELEVEDATA_SPREAD = FALSE/BLANK
BID_ASK_COLUMNS = NOT_FOUND
NEWS_SPREAD_MODEL = NOT_FOUND
ROLLOVER_RULE = NOT_FOUND
GAP_RISK_MODEL = NOT_FOUND
SLIPPAGE_MODEL = NOT_FOUND
```

Therefore:

```text
STAGE39 remains blocked until spread non-null count and cost model are built.
```

But the existence of `bars.spread` is positive. If populated, it can become the core of the free execution model.

---

## 10. Required Next Commands

Run these exact commands next.

### 10.1 Bars Coverage and Spread Audit

```bash
cd ~/Desktop/xauusd-trader
sqlite3 data/local/xauusd_local_store.sqlite "
.headers on
.mode column
select source, symbol, timeframe,
       count(*) as rows,
       min(utc_time) as min_utc,
       max(utc_time) as max_utc,
       sum(case when spread is not null then 1 else 0 end) as spread_rows,
       round(100.0 * sum(case when spread is not null then 1 else 0 end) / count(*), 2) as spread_pct
from bars
group by source, symbol, timeframe
order by symbol, timeframe, source;
"
```

### 10.2 Spread Distribution

```bash
cd ~/Desktop/xauusd-trader
sqlite3 data/local/xauusd_local_store.sqlite "
.headers on
.mode column
select source, symbol, timeframe,
       min(spread) as min_spread,
       avg(spread) as avg_spread,
       max(spread) as max_spread
from bars
where spread is not null
group by source, symbol, timeframe
order by symbol, timeframe, source;
"
```

### 10.3 Persistent Store Coverage

```bash
cd ~/Desktop/xauusd-trader
for t in candles_i_1min candles_i_5min candles_i_15min candles_i_1h; do
  echo "==== $t ===="
  sqlite3 data/store/xauusd.sqlite "
  .headers on
  .mode column
  select symbol, interval, provider,
         count(*) as rows,
         min(time_utc) as min_utc,
         max(time_utc) as max_utc
  from $t
  group by symbol, interval, provider;
  "
done
```

### 10.4 Macro Regime Coverage

```bash
cd ~/Desktop/xauusd-trader
sqlite3 data/local/xauusd_local_store.sqlite "
.headers on
.mode column
select count(*) as rows,
       min(obs_date) as min_date,
       max(obs_date) as max_date
from macro_daily_regime;
select macro_regime, count(*) as rows
from macro_daily_regime
group by macro_regime
order by rows desc;
"
```

### 10.5 H1 Macro Context Coverage

```bash
cd ~/Desktop/xauusd-trader
sqlite3 data/local/xauusd_local_store.sqlite "
.headers on
.mode column
select count(*) as rows,
       min(utc_time) as min_utc,
       max(utc_time) as max_utc
from macro_context_h1;
select macro_regime, count(*) as rows
from macro_context_h1
group by macro_regime
order by rows desc;
"
```

### 10.6 Event Reaction Coverage

```bash
cd ~/Desktop/xauusd-trader
sqlite3 data/local/xauusd_local_store.sqlite "
.headers on
.mode column
select count(*) as rows,
       min(event_time_utc) as min_event_utc,
       max(event_time_utc) as max_event_utc
from news_event_reactions;
select event_class, event_channel, count(*) as rows
from news_event_reactions
group by event_class, event_channel
order by rows desc
limit 30;
"
```

---

## 11. Updated Gate

Current gate after schema/header audit:

```text
[PASS] local SQLite store exists
[PASS] bars table has OHLC + spread column
[PASS] persistent OHLC store has 1m/5m/15m/1h tables
[PASS] macro_daily_regime exists
[PASS] macro_context_h1 exists
[PASS] macro/exogenous FRED layer exists
[PASS-PARTIAL] event reaction tables exist
[FAIL] true event surprise fields not found
[FAIL] COT not found
[FAIL] ETF not found
[FAIL] TwelveData spread unavailable
[UNKNOWN] bars.spread population
[UNKNOWN] OHLC coverage length
[UNKNOWN] macro regime coverage
[UNKNOWN] event reaction coverage
[BLOCKED] execution cost model
```

Stage39 remains blocked.

---

## 12. Recommended Commit

After placing this file in the repo:

```bash
cd ~/Desktop/xauusd-trader
git status --short
git add -A
git commit -m "Add Stage38A schema and header audit result"
git pull --rebase origin main
git push
```

---

## 13. Practical Next Step

The next required output is the result of the six commands in section 10.

After that we can make a real decision:

```text
T1_GO_FOR_READ_ONLY_BACKTEST_DESIGN
or
T1_NEEDS_SPREAD_COST_PROXY
or
T1_BLOCKED_BY_INSUFFICIENT_COVERAGE
```

No strategy backtest should be written before this.
