# Stage38A — Data Feasibility Matrix

**Project:** XAUUSD / Gold Trading System  
**Stage:** Stage38A  
**Document type:** Data inventory, gap analysis, and free-source acquisition plan  
**Generated UTC:** 2026-06-16T11:48:04Z  
**Status:** Non-coding planning document  
**Cost policy:** FREE-FIRST ONLY — paid data/services are not justified at this phase  
**Execution authorization:** NO EA, NO paper-live, NO live order, NO Stage39 code until feasibility gates pass

---

چپ‌چین ادامه می‌دهم.

این سند برای جدا کردن «داشته‌ها» از «نیازها» ساخته شده است. هدف این نیست که همین حالا loader یا کد جدید نوشته شود. هدف این است که مشخص کنیم:

1. کدام داده‌ها همین حالا در پروژه یا زیرساخت موجود احتمالاً قابل استفاده‌اند.
2. کدام داده‌ها لازم‌اند ولی نداریم.
3. برای داده‌های ناقص یا غایب، راه‌حل‌های رایگان چیست.
4. کدام thesis با داده‌های فعلی قابل شروع است.
5. کدام thesis تا تکمیل داده باید blocked بماند.

قاعده اصلی این سند:

```text
No paid data.
No paid API.
No premium calendar.
No commercial forecast feed.
No overbuilding before feasibility.
```

اگر داده‌ای رایگان، پایدار و قابل اتکا نباشد، thesis مربوط به آن باید محدود، delayed یا blocked شود؛ نه اینکه با pattern mining خام جایگزین شود.

---

## 1. Executive Decision

وضعیت داده‌ای فعلی پروژه برای Stage38A چنین است:

```text
T1_REGIME_FILTERED_STRUCTURE_CONTINUATION = MOST_FEASIBLE_FIRST
T3_POSITIONING_SQUEEZE_EXHAUSTION = FEASIBLE_AFTER_FREE_COT_LAYER
T2_EVENT_SURPRISE_FOLLOWTHROUGH_FADE = BLOCKED_OR_LIMITED_UNTIL_FREE_FORECAST_CONSENSUS_FEASIBILITY
```

دلیل:

- Thesis 1 عمدتاً به OHLC، spread، H4/D1 structure، real yield و USD proxy نیاز دارد. این‌ها یا در پروژه موجودند یا با منابع رایگان رسمی قابل تکمیل‌اند.
- Thesis 3 به COT نیاز دارد. CFTC داده COT را رایگان منتشر می‌کند، پس این مسیر از نظر هزینه منطقی است.
- Thesis 2 برای surprise واقعی به actual/forecast/previous نیاز دارد. actual و previous از منابع رسمی رایگان قابل تهیه‌اند، اما consensus forecast معمولاً از منابع رسمی دولتی نمی‌آید. بنابراین T2 نباید با event/no-event خام جایگزین شود.

نتیجه عملی:

```text
Priority 1: audit current OHLC/spread/macro availability
Priority 2: use free FRED/Fed/BLS/BEA/CFTC/WGC sources where available
Priority 3: build free-source feasibility list before writing any loader
Priority 4: keep T2 blocked unless forecast/consensus data is solved free
```

---

## 2. Current Project Data Inventory — What We Already Have

این بخش بر اساس وضعیت ریپو و اسناد انتقالی نوشته شده است. برای هر مورد باید با فایل‌های واقعی روی سیستم کاربر verify شود.

### 2.1 Repository / Pipeline Assets

در پروژه این اجزا موجود یا گزارش‌شده‌اند:

```text
app/stage32f_amarkets_csv_preflight.py
app/stage32f_extended_shadow_refresh_cycle.py
app/xauusd_collect.py
app/xauusd_data_quality.py
app/xauusd_normalize.py
app/xauusd_sqlite_store.py
app/xauusd_store_backfill.py
app/xauusd_store_refresh.py
tools/download_fred_exogenous.py
tools/install_fred_artifact.py
configs/backfill.yaml
configs/data_source.yaml
configs/persistent_store.yaml
configs/project.yaml
data/exogenous
data/local
data/macro
data/normalized
data/raw
data/reports
data/store
```

برداشت عملی:

- زیرساخت قیمت/CSV/SQLite وجود دارد.
- AMarkets CSV preflight وجود دارد.
- FRED/exogenous tooling وجود دارد.
- persistent store وجود دارد.
- data quality/normalize/backfill وجود دارد.
- اما وجود ابزار به معنی کامل بودن داده نیست؛ باید فایل‌ها و ستون‌ها audit شوند.

---

### 2.2 Likely Available / Needs Verification

| Data Layer | Current Status | Confidence | Needed Verification |
|---|---|---:|---|
| XAUUSD raw OHLC | likely available | medium | check `data/raw`, `data/local`, `data/store` |
| normalized XAUUSD OHLC | likely available | medium | check `data/normalized` and SQLite tables |
| H1 price history | likely available | medium-high | inspect store/schema |
| M1/M5 price history | uncertain | low-medium | inspect CSV/store coverage |
| H4/D1 derived bars | probably derivable | medium | confirm resampling path |
| broker spread | likely partial | medium | inspect AMarkets CSV fields |
| Stage35C monitor state | available | high | monitor env exists |
| FRED exogenous tools | available | high | tools exist |
| real yield data | uncertain current coverage | medium | check `data/exogenous`/`data/macro` |
| DXY/USD proxy | uncertain current coverage | medium | check FRED artifact |
| VIX/SPX | uncertain | low-medium | check FRED artifact |
| COT gold positioning | missing | high | no current loader reported |
| ETF flow | missing | high | no current loader reported |
| event actual/forecast/previous | missing | high | no current event surprise DB |
| Fed expectations proxy | missing/uncertain | medium | check FRED/exogenous content |
| slippage/requote/gap model | missing | high | no evidence of detailed model |
| options skew | missing | high | not needed in v0 |

---

## 3. Local Audit Commands

قبل از هر تصمیم Stage39، این audit باید اجرا شود. این‌ها فقط command هستند، نه تغییر کد.

### 3.1 Inspect Data Folders

```bash
cd ~/Desktop/xauusd-trader
find data -maxdepth 3 -type f | sort | sed -n '1,200p'
```

### 3.2 Inspect Store Files

```bash
cd ~/Desktop/xauusd-trader
find data/store -maxdepth 2 -type f -print
```

### 3.3 Inspect SQLite Schema

اگر فایل SQLite مشخص است:

```bash
cd ~/Desktop/xauusd-trader
sqlite3 data/store/*.db ".tables"
sqlite3 data/store/*.db ".schema"
```

اگر چند DB وجود دارد:

```bash
cd ~/Desktop/xauusd-trader
find data -name "*.db" -print
```

### 3.4 Inspect Existing Macro/Exogenous Files

```bash
cd ~/Desktop/xauusd-trader
find data/exogenous data/macro -type f | sort
```

### 3.5 Check CSV Headers

```bash
cd ~/Desktop/xauusd-trader
find data -name "*.csv" -print | head -50
```

برای بررسی header چند فایل اول:

```bash
cd ~/Desktop/xauusd-trader
for f in $(find data -name "*.csv" | head -20); do
  echo "==== $f ===="
  head -1 "$f"
done
```

---

## 4. Required Data by Thesis

### 4.1 Thesis 1 — Regime-filtered Structure Continuation

| Required Data | Status | Free Solution | Priority | Decision |
|---|---|---|---:|---|
| XAUUSD H1 OHLC | likely available | existing AMarkets/MT5 CSV/store | 1 | audit first |
| XAUUSD H4 OHLC | derivable | resample H1 if H4 absent | 1 | feasible |
| XAUUSD D1 OHLC | derivable | resample H1/H4 if D1 absent | 1 | feasible |
| Broker spread | likely partial | existing AMarkets CSV if spread column exists | 1 | audit required |
| Real yield 10Y | uncertain | FRED DFII10 | 1 | free |
| USD proxy | uncertain | FRED DTWEXBGS broad USD index | 1 | free |
| ATR percentile | derivable | compute from OHLC | 1 | feasible later |
| H4/D1 structure | derivable | compute from OHLC | 1 | feasible later |
| Event blackout timestamps | partial/missing | Fed/BLS/BEA release calendars, manually curated | 2 | feasible limited |
| COT/ETF filter | missing | CFTC/WGC free data | 3 | optional for T1 v0 |

T1 feasibility:

```text
T1 is feasible first if OHLC + spread + real yield + USD proxy are confirmed.
T1 should be the first Stage39 candidate after Stage38A gate because it has the lowest external data dependency.
```

---

### 4.2 Thesis 2 — Event Surprise Follow-through / Fade

| Required Data | Status | Free Solution | Priority | Decision |
|---|---|---|---:|---|
| Event timestamps | partially free | BLS/BEA/Fed calendars/releases | 1 | feasible |
| Event actual | free | BLS CPI/NFP, BEA PCE, Fed FOMC statements | 1 | feasible |
| Event previous | free | official historical releases / time series | 1 | feasible |
| Event forecast/consensus | missing | free calendar/manual collection only if reliable | 1 | blocker |
| surprise_z | blocked by forecast | compute only after forecast solved | 1 | blocked |
| Pre-event drift | derivable | OHLC | 2 | feasible |
| Reaction 15m/30m/1h | needs intraday data | M15/M1/H1 OHLC | 2 | depends |
| Follow-through 4h/24h | derivable | H1/H4 OHLC | 2 | feasible |
| Spread around event | uncertain | broker spread data | 1 | audit |
| FOMC tone | missing | manual/rule-based statement metadata | 3 | feasible limited |

T2 feasibility:

```text
T2 is not ready for Stage39 until forecast/consensus data is solved with a free and reliable method.
Actual-minus-previous is NOT a true substitute for consensus surprise.
Event/no-event labels are NOT acceptable as a substitute.
```

Allowed temporary workaround:

```text
Build a feasibility-only event table with:
actual
previous
release timestamp
gold pre/post reaction

But label it:
EVENT_REACTION_FEASIBILITY_ONLY
not:
EVENT_SURPRISE_MODEL
```

Blocked until:

```text
forecast_or_consensus_free_source = confirmed
```

---

### 4.3 Thesis 3 — Positioning Squeeze / Exhaustion

| Required Data | Status | Free Solution | Priority | Decision |
|---|---|---|---:|---|
| COT gold futures positioning | missing | CFTC COT historical compressed files | 1 | free, feasible |
| Net speculative long/short | derivable | COT non-commercial long-short | 1 | feasible |
| COT percentile | derivable | rolling percentile | 1 | feasible |
| 4-week COT change | derivable | weekly COT | 1 | feasible |
| XAUUSD D1/H4 | likely/derivable | existing OHLC/store | 1 | feasible |
| Failed breakout/reclaim | derivable | OHLC structure | 2 | feasible |
| ETF flows/holdings | missing | WGC downloadable monthly xlsx, free account may be required | 2 | feasible with friction |
| VIX/SPX | uncertain | FRED | 3 | free |
| Event shocks | missing/partial | official release timestamps/manual event list | 3 | feasible limited |

T3 feasibility:

```text
T3 is feasible after adding a free COT layer.
ETF flow is useful but not mandatory for first COT-only feasibility.
If COT cannot be parsed reliably, T3 remains blocked.
```

---

## 5. Free Data Source Plan

### 5.1 Real Yield

| Item | Recommended Free Source | Notes |
|---|---|---|
| 10Y real yield | FRED DFII10 | daily, official/Fed source through FRED |
| derived slope | compute locally | 20d slope, 12m percentile |
| use in thesis | T1/T2/T3 regimes | high priority |

Implementation decision:

```text
Use existing FRED tooling if it already supports DFII10.
If not, add only after Stage38A gate.
```

---

### 5.2 USD Proxy

| Item | Recommended Free Source | Notes |
|---|---|---|
| Broad USD index | FRED DTWEXBGS | free, broad trade-weighted USD proxy |
| DXY exact index | not necessary in v0 | broad USD proxy is acceptable |
| USD character | compute locally | slope, impulse, gold/USD co-rise |

Decision:

```text
Use DTWEXBGS as v0 USD proxy.
Do not block project waiting for exact paid DXY feed.
```

---

### 5.3 VIX/SPX Risk Sentiment

| Item | Recommended Free Source | Notes |
|---|---|---|
| VIX | FRED VIXCLS | free |
| SPX | FRED or other free market source | use only if already available |
| risk-off flag | compute locally | VIX jump + equity drawdown |

Decision:

```text
VIX is enough for v0 risk sentiment.
SPX can be added if free and easy.
```

---

### 5.4 CPI / NFP Actual and Previous

| Item | Recommended Free Source | Notes |
|---|---|---|
| CPI actual | BLS official release/API | free |
| NFP actual | BLS Employment Situation / PAYEMS | free |
| previous values | BLS/FRED historical series | free |
| release time | BLS release calendar / news release | free |

Decision:

```text
Actual and previous are feasible.
Forecast/consensus remains the hard gap.
```

---

### 5.5 PCE Actual and Previous

| Item | Recommended Free Source | Notes |
|---|---|---|
| PCE actual | BEA Personal Income and Outlays / PCE data | free |
| previous values | BEA/FRED | free |
| release dates | BEA release schedule/page | free |

Decision:

```text
Actual and previous are feasible.
Forecast/consensus remains the hard gap.
```

---

### 5.6 FOMC

| Item | Recommended Free Source | Notes |
|---|---|---|
| FOMC dates | Federal Reserve calendars | free |
| statements/minutes | Federal Reserve | free |
| rate decision | Federal Reserve | free |
| tone | initially manual/rule-based | avoid NLP overbuild |

Decision:

```text
FOMC event timestamps and statements are free.
Tone classification should start manually/simple-rule, not with complex NLP.
```

---

### 5.7 COT Gold Futures Positioning

| Item | Recommended Free Source | Notes |
|---|---|---|
| COT reports | CFTC Commitments of Traders | free |
| historical compressed files | CFTC historical compressed | free |
| gold futures | COMEX gold code mapping required | free |
| net speculative | non-commercial long - non-commercial short | derivable |
| percentile | local rolling calculation | derivable |

Decision:

```text
COT is the best free missing layer.
T3 should become feasible after COT import.
```

---

### 5.8 ETF Flows / Holdings

| Item | Recommended Free Source | Notes |
|---|---|---|
| gold ETF holdings/flows | World Gold Council Goldhub | downloadable xlsx, free account may be required |
| GLD holdings | issuer/public pages if accessible | free/manual possible |
| monthly ETF flows | WGC | lower frequency but useful |
| daily fund-level flows | may be harder | not mandatory v0 |

Decision:

```text
ETF flow is useful but should not block T1 or COT-only T3.
If WGC download requires a free account, it is acceptable under FREE-FIRST policy.
No paid ETF data.
```

---

### 5.9 Forecast / Consensus Data

This is the biggest unresolved gap.

| Item | Status | Free Options | Decision |
|---|---|---|---|
| CPI forecast | missing | free calendar/manual capture if reliable | blocker |
| NFP forecast | missing | free calendar/manual capture if reliable | blocker |
| PCE forecast | missing | free calendar/manual capture if reliable | blocker |
| FOMC expected rate | possible proxy | Fed funds/SOFR proxies, but not exact consensus | partial |
| historical consensus | hard | often paid/fragile | blocker |

Rules:

```text
Do not use actual-previous as if it were consensus surprise.
Do not label event/no-event models as event surprise models.
Do not pay for forecast feeds at this phase.
Do not scrape fragile websites unless terms and stability are acceptable.
```

Acceptable free-first approaches:

```text
Option A: Manual CSV for only CPI/NFP/PCE/FOMC from free economic calendars.
Option B: Limited forward-only collection of consensus values from free calendars before releases.
Option C: Use official actual/previous only for reaction feasibility, not true surprise.
Option D: Delay T2 until a reliable free forecast source is identified.
```

Recommended decision:

```text
T2 remains BLOCKED for true historical surprise testing.
A limited forward-only forecast collection can start later, manually, at zero cost.
```

---

## 6. Data Feasibility Matrix — Full View

| Data | Needed For | Have? | Free Source / Method | Feasibility | Blocker? | Priority |
|---|---|---|---|---|---|---:|
| XAUUSD H1 OHLC | T1/T2/T3 | likely | existing AMarkets/MT5/store | high | no | 1 |
| XAUUSD H4 OHLC | T1/T3 | derivable | resample H1 | high | no | 1 |
| XAUUSD D1 OHLC | T1/T3 | derivable | resample H1/H4 | high | no | 1 |
| spread history | T1/T2 | likely partial | AMarkets CSV/store | medium | maybe | 1 |
| real yield DFII10 | T1/T2/T3 | uncertain | FRED | high | no | 1 |
| USD proxy DTWEXBGS | T1/T2 | uncertain | FRED | high | no | 1 |
| VIX | all regimes | uncertain | FRED VIXCLS | high | no | 2 |
| SPX | risk sentiment | uncertain | FRED/free market data | medium | no | 3 |
| CPI actual/previous | T2 | no/uncertain | BLS | high | no | 1 |
| NFP actual/previous | T2 | no/uncertain | BLS/FRED PAYEMS | high | no | 1 |
| PCE actual/previous | T2 | no/uncertain | BEA/FRED | high | no | 2 |
| FOMC dates/statements | T2 | no/uncertain | Federal Reserve | high | no | 2 |
| event consensus/forecast | T2 | no | manual/free calendar only | low-medium | yes | 1 |
| COT gold positioning | T3 | no | CFTC | high | no | 1 |
| ETF flows | T3/T1 filter | no | WGC/free account/manual | medium | no for v0 | 2 |
| options skew | advanced | no | no reliable free v0 | low | no, optional | 5 |
| LBMA clearing | advanced | no | public monthly | medium | no, optional | 5 |
| central bank demand | macro context | no | WGC quarterly | medium | no, optional | 5 |
| slippage model | execution | no | infer from spread/wicks; later broker logs | medium | later | 4 |
| requote/partial fill | execution | no | unavailable in backtest | low | later | 5 |

---

## 7. Thesis Feasibility Decision

### 7.1 T1 — Regime-filtered Structure Continuation

Decision:

```text
T1 = GO_FOR_FEASIBILITY_AFTER_LOCAL_DATA_AUDIT
```

Minimum needed:

```text
XAUUSD H1/H4/D1
spread
real_yield_slope_20d
USD proxy slope
H4/D1 structure
ATR percentile
```

Why first:

```text
It reuses current infrastructure.
It directly tests whether the prior Stage36E raw edge can be rescued.
It does not depend on hard-to-get historical forecast consensus.
```

Blocked only if:

```text
OHLC coverage is inadequate
OR spread data is missing/unusable
OR real yield/USD proxy cannot be aligned
```

---

### 7.2 T3 — Positioning Squeeze / Exhaustion

Decision:

```text
T3 = GO_AFTER_FREE_COT_LAYER_FEASIBILITY
```

Minimum needed:

```text
CFTC COT gold historical data
COT net speculative percentile
XAUUSD D1/H4 structure
```

Why second:

```text
COT is free.
It adds a missing market layer.
It can be used both as setup and as filter for T1.
```

Blocked only if:

```text
COT parsing/mapping to gold futures fails
OR weekly alignment to gold data is unreliable
```

ETF decision:

```text
ETF flow is useful but not mandatory for first COT-only feasibility test.
```

---

### 7.3 T2 — Event Surprise Follow-through / Fade

Decision:

```text
T2_TRUE_SURPRISE_MODEL = BLOCKED_UNTIL_FORECAST_CONSENSUS_SOURCE_CONFIRMED
T2_EVENT_REACTION_FEASIBILITY_ONLY = ALLOWED_LATER
```

Minimum for true T2:

```text
event_timestamp
actual
forecast
previous
surprise_z
pre_event_drift
post_event_reaction
regime_at_event
spread_state
```

Why blocked:

```text
Actual/previous are free.
Forecast/consensus is the hard missing layer.
Without forecast, surprise_z is not valid.
```

Allowed limited version:

```text
Create event reaction database with official actual/previous and gold response,
but do not call it a surprise model.
```

---

## 8. Free-Only Acquisition Priority

### Priority 1 — Immediate Audit, No New Data Source Yet

```text
1. Confirm OHLC coverage.
2. Confirm spread availability.
3. Confirm SQLite schema.
4. Confirm current FRED/exogenous files.
5. Confirm whether DFII10/DTWEXBGS/VIX are already present.
```

### Priority 2 — Free FRED/Fed Macro Completion

```text
1. DFII10 real yield.
2. DTWEXBGS broad USD proxy.
3. VIXCLS.
4. Optional SPX proxy.
```

### Priority 3 — Free COT Layer

```text
1. Download CFTC historical compressed COT.
2. Map COMEX gold.
3. Compute non-commercial net.
4. Compute rolling percentile.
5. Align weekly to daily/H4 gold data.
```

### Priority 4 — Free Official Event Actuals

```text
1. BLS CPI actual/previous.
2. BLS NFP/PAYEMS actual/previous.
3. BEA PCE actual/previous.
4. Federal Reserve FOMC dates/statements.
```

### Priority 5 — Forecast/Consensus Feasibility

```text
1. Search for stable free historical forecast source.
2. If unavailable, use manual forward-only capture.
3. Keep T2 true surprise blocked until solved.
```

### Priority 6 — ETF Flow

```text
1. WGC Goldhub monthly ETF flow xlsx.
2. Free account is acceptable.
3. Use monthly/weekly as context, not intraday signal.
```

---

## 9. No-Paid-Data Policy

Paid data is not logical at this phase because:

1. The project has not yet proven a thesis-level edge.
2. Stage38A is still a reconstruction phase.
3. Spending money before Stage39 feasibility would create false commitment.
4. Free official sources cover most T1/T3 needs.
5. The only serious paid-pressure area is historical consensus forecast, and T2 can be delayed.

Policy:

```text
If a data source requires payment, skip it.
If a data source requires free registration, it is allowed only if terms are acceptable and no payment method is needed.
If a source is fragile, manual, or legally unclear, do not automate it blindly.
```

---

## 10. Recommended Next Document / Patch Decision

Before writing any loader, the project should produce one more non-coding document:

```text
docs/STAGE38A_LOCAL_DATA_AUDIT_CHECKLIST.md
```

Purpose:

```text
Turn the audit commands in this document into a checklist of expected files, columns, tables, and minimum coverage.
```

But if the user wants to move faster, the first implementation after Stage38A gates should be a read-only audit script, not a strategy backtest:

```text
app/stage38a_local_data_inventory_audit.py
```

This script would only inspect existing data and produce a report. It would not test a strategy.

---

## 11. Stage38A Data Gate

Stage39 remains blocked until these conditions are answered:

```text
[ ] Do we have usable XAUUSD H1 OHLC?
[ ] Can H4/D1 bars be derived consistently?
[ ] Do we have usable spread history?
[ ] Do we have or can we freely fetch DFII10?
[ ] Do we have or can we freely fetch DTWEXBGS?
[ ] Do we have or can we freely fetch VIXCLS?
[ ] Can we align macro daily data to gold H1/H4?
[ ] Can we freely fetch and parse COT gold positioning?
[ ] Can we compute COT percentile and 4-week change?
[ ] Is ETF flow available free enough for v0?
[ ] Can event actual/previous be obtained from BLS/BEA/Fed?
[ ] Is historical forecast/consensus available free?
[ ] If no, is T2 blocked rather than approximated incorrectly?
```

Current gate status:

```text
STAGE38A_DATA_FEASIBILITY_MATRIX=CREATED
T1_FEASIBILITY=LIKELY_GO_AFTER_AUDIT
T3_FEASIBILITY=GO_AFTER_FREE_COT_LAYER
T2_TRUE_SURPRISE=BLOCKED_UNTIL_FREE_FORECAST_SOURCE
PAID_DATA=NO_GO
STAGE39=NO_GO_FOR_NOW
```

---

## 12. Source Notes — Free / Official Priority

These are reference sources for the free-first data plan.

```text
FRED DFII10:
https://fred.stlouisfed.org/series/DFII10

FRED Nominal Broad U.S. Dollar Index DTWEXBGS:
https://fred.stlouisfed.org/series/DTWEXBGS

CFTC Commitments of Traders:
https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm

CFTC Historical Compressed COT:
https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm

BLS CPI:
https://www.bls.gov/cpi/

BLS Public Data API:
https://www.bls.gov/bls/api_features.htm

BLS Employment Situation:
https://www.bls.gov/news.release/empsit.toc.htm

FRED PAYEMS:
https://fred.stlouisfed.org/series/PAYEMS

BEA PCE:
https://www.bea.gov/data/personal-consumption-expenditures-price-index

Federal Reserve FOMC calendars/statements:
https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm

World Gold Council ETF holdings and flows:
https://www.gold.org/goldhub/data/gold-etfs-holdings-and-flows
```

---

## 13. Recommended Commit

After placing this file in the repo:

```bash
cd ~/Desktop/xauusd-trader
git status --short
git add -A
git commit -m "Add Stage38A data feasibility matrix"
git pull --rebase origin main
git push
```

---

## 14. Practical Next Step

Recommended next step:

```text
Run the local data audit commands and paste the output.
```

Then the next artifact should be either:

```text
docs/STAGE38A_LOCAL_DATA_AUDIT_RESULT.md
```

or, if we choose to automate read-only inspection:

```text
app/stage38a_local_data_inventory_audit.py
```

No strategy backtest should be written before this audit.
