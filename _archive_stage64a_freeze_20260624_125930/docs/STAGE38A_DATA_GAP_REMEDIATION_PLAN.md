# Stage38A — Data Gap Remediation Plan

**Project:** XAUUSD / Gold Trading System  
**Stage:** Stage38A / Stage38B Transition  
**Document type:** Prioritized data-gap remediation plan  
**Generated UTC:** 2026-06-16T12:37:23Z  
**Status:** Action plan before/alongside T1 read-only implementation  
**Cost policy:** FREE-FIRST ONLY  
**Execution authorization:** NO EA, NO paper-live, NO live order  
**Stage39 authorization:** NO-GO

---

چپ‌چین ادامه می‌دهم.

این سند مشخص می‌کند رفع نواقص دیتا از کجا شروع می‌شود، چه چیزهایی فوری هستند، چه چیزهایی بعداً انجام می‌شوند، و کدام gapها نباید فعلاً باعث توقف T1 شوند.

پاسخ کوتاه:

```text
رفع نواقص دیتا از همین مرحله شروع می‌شود.
اما فقط gapهایی که T1 را مسدود می‌کنند فوری هستند.
COT برای T3 بعد از T1 read-only test شروع می‌شود.
forecast/consensus برای T2 فعلاً در مسیر جدا و محدود باقی می‌ماند.
```

---

## 1. Executive Decision

Current status:

```text
T1_PRICE_DATA = PASS
T1_MACRO_DAILY_REGIME = PASS
T1_SPREAD_PERCENTILES = PASS_PARTIAL
T1_EXECUTION_COST_MODEL = CREATED
T1_TRADE_CONSTRUCTION = CREATED
T1_READ_ONLY_TEST_DESIGN = CREATED
T1_IMPLEMENTATION_PLAN = CREATED

T1_BLOCKERS_REMAINING:
    point-to-price conversion
    symbol spec / contract spec
    swap / rollover documentation
    H1 macro regime label issue
    event guard quality

T3_BLOCKERS_REMAINING:
    COT gold positioning
    COT percentile
    optional ETF flow

T2_BLOCKERS_REMAINING:
    actual / forecast / previous
    historical consensus / forecast
    true surprise_z
```

Decision:

```text
DATA_GAP_REMEDIATION_STARTS_NOW
PRIORITY = T1_BLOCKERS_FIRST
```

---

## 2. Why Not Fix All Data Gaps Immediately?

Because not all data gaps have the same value right now.

### T1

T1 is already close to executable as read-only research.

Missing items are small but important:

```text
symbol conversion
cost interpretation
rollover/swap
macro H1 label repair/derived join
event guard quality
```

These are worth fixing now.

### T3

T3 needs COT. This is important and free, but it is not needed for the first T1 test.

Therefore:

```text
COT starts after the first T1 read-only result or in parallel only if T1 implementation is blocked.
```

### T2

T2 true surprise needs forecast/consensus. This is the hardest free-data gap.

Therefore:

```text
Do not stop T1 for T2.
Do not fake surprise with actual-previous.
Do not pay for forecast data.
Use manual/forward-only collection later if no reliable free source exists.
```

---

## 3. Immediate Data Gaps to Fix Before/Alongside T1 Script

These are the gaps that affect T1 directly.

---

### 3.1 Gap A — XAUUSD Symbol Specification

Problem:

```text
spread_points exist, but conversion to price/USD is not confirmed.
```

Need:

```text
SYMBOL_DIGITS
SYMBOL_POINT
SYMBOL_TRADE_TICK_SIZE
SYMBOL_TRADE_TICK_VALUE
SYMBOL_TRADE_CONTRACT_SIZE
CURRENCY_PROFIT
COMMISSION if any
```

Free solution:

```text
Use MT5 symbol specification from broker terminal.
Manual copy is enough.
No paid API.
No broker trading action.
```

Priority:

```text
P0 — immediate
```

Reason:

```text
Without this, cost model remains in spread_points and cannot become true net R.
```

Action:

```text
Create a small manual file:
data/manual/amarkets_xauusd_symbol_spec_YYYYMMDD.txt
```

Minimum content:

```text
Broker:
Server:
Symbol:
Digits:
Point:
Tick size:
Tick value:
Contract size:
Min lot:
Lot step:
Commission:
Swap long:
Swap short:
Triple swap day:
Rollover/server time:
Captured UTC:
```

---

### 3.2 Gap B — Swap / Rollover Cost

Problem:

```text
T1 is short-horizon, but some trades may hold through rollover or near weekend.
Swap and rollover rules are not documented.
```

Need:

```text
swap_long
swap_short
triple_swap_day
rollover_time_server
rollover_time_utc
```

Free solution:

```text
Manual MT5 symbol spec / broker contract spec page.
No paid data.
```

Priority:

```text
P0 — immediate
```

Decision:

```text
Until documented:
    no new entries near rollover
    no weekend hold
    swap_unknown_flag remains true
```

---

### 3.3 Gap C — H1 Macro Regime Label Collapse

Problem:

```text
macro_context_h1 has 24,225 rows but all labels are neutral.
```

Need:

```text
derive H1 macro regime from macro_daily_regime instead of trusting macro_context_h1 label
```

Free solution:

```text
No new data needed.
Use existing macro_daily_regime and H1 bars.
```

Priority:

```text
P0 — immediate
```

Decision:

```text
Do not repair database table yet.
In read-only T1 script, derive H1 macro label by joining H1 bar date to macro_daily_regime.
```

Output later:

```text
stage38a_t1_macro_join_diagnostics.csv
```

---

### 3.4 Gap D — Event Guard Quality

Problem:

```text
scheduled event data exists but may be incomplete or placeholder-like.
```

Need:

```text
Reliable high-impact event blackout windows for CPI/NFP/FOMC/PCE.
```

Free solution v0:

```text
Use existing scheduled events only if clearly reliable.
Otherwise apply only Sunday/Monday open block and record event_guard_limited.
```

Priority:

```text
P1 — useful but not blocker for first T1 read-only test
```

Decision:

```text
First T1 test may proceed with event_guard_status = limited
but no claim of event-safe execution is allowed.
```

---

### 3.5 Gap E — Spread Session Coverage

Problem:

```text
spread samples are concentrated around UTC 23/00 and session model output is empty.
```

Need:

```text
normal liquid-session spread estimate
```

Free solution v0:

```text
Use conservative p90 spread model from observed AMarkets spread.
Do not claim full-session spread accuracy.
```

Priority:

```text
P1
```

Decision:

```text
Not a blocker for T1 read-only feasibility because cost model is conservative.
Still a blocker for paper/live.
```

---

## 4. Data Gaps for T3 — Start After T1 First Result

### 4.1 Gap F — COT Gold Positioning

Problem:

```text
No COT/CFTC data exists locally.
```

Need:

```text
CFTC gold futures positioning
non-commercial long
non-commercial short
net speculative position
rolling percentile
4-week change
weekly alignment to D1/H4 XAUUSD
```

Free solution:

```text
CFTC historical compressed COT files.
No paid data.
```

Priority:

```text
P2 — after T1 read-only first result
```

Reason:

```text
COT is essential for T3.
But it is not necessary for first T1 test.
```

Future artifact:

```text
docs/STAGE38B_COT_DATA_PLAN.md
```

Future script:

```text
tools/stage38b_download_cftc_cot_gold.py
```

Not authorized yet.

---

### 4.2 Gap G — ETF Flow / Holdings

Problem:

```text
No ETF/GLD/IAU/WGC flow data exists locally.
```

Need:

```text
ETF holdings
ETF flow proxy
monthly/weekly flow if free
```

Free solution:

```text
World Gold Council Goldhub free download if accessible.
Manual download acceptable.
No paid ETF data.
```

Priority:

```text
P3 — after COT
```

Decision:

```text
ETF is useful but not mandatory for first T3 COT-only feasibility.
```

---

## 5. Data Gaps for T2 — Start Later, Not Now

### 5.1 Gap H — Forecast / Consensus

Problem:

```text
No reliable forecast/consensus data is confirmed.
```

Need:

```text
event_type
event_timestamp_utc
actual
forecast
previous
surprise_z
```

Free solution options:

```text
Option A: Manual forward-only collection from free calendars.
Option B: Limited manually curated historical CSV for a few CPI/NFP/FOMC events.
Option C: Official actual/previous only for reaction feasibility, not surprise.
```

Priority:

```text
P4 — later
```

Decision:

```text
T2_TRUE_SURPRISE remains blocked.
Do not spend project time here before T1 read-only result unless T1 collapses.
```

Reason:

```text
Forecast/consensus is the least reliable free-data gap.
It can consume time without improving the near-term path.
```

---

## 6. Prioritized Action Queue

### P0 — Start Now

```text
1. Capture AMarkets XAUUSD symbol specification.
2. Capture swap/rollover fields.
3. Implement read-only macro_daily_regime join in T1 plan/script.
4. Keep cost model in spread_points until conversion is verified.
```

### P1 — During T1 Read-only Script

```text
1. Add event_guard_status diagnostics.
2. Add blocked Sunday/Monday windows.
3. Add spread cost sensitivity outputs.
4. Add macro join diagnostics.
```

### P2 — After First T1 Read-only Result

```text
1. Start CFTC COT data plan.
2. Build COT parser/loader only if T1 result does not require urgent redesign.
3. Add COT percentile and alignment diagnostics.
```

### P3 — After COT

```text
1. Check free ETF/WGC feasibility.
2. Add ETF only if it improves T3 or T1 filter quality.
```

### P4 — Later / Separate Track

```text
1. Forecast/consensus feasibility.
2. Manual event forecast CSV template.
3. T2 true surprise DB only if reliable free path exists.
```

---

## 7. What We Should Do Next

Recommended immediate next step:

```text
Create symbol specification capture template.
```

File:

```text
docs/STAGE38A_AMARKETS_XAUUSD_SYMBOL_SPEC_CAPTURE.md
```

Purpose:

```text
Tell the user exactly what to copy from MT5 symbol specification so spread_points can be converted correctly.
```

After that:

```text
app/stage38a_t1_read_only_test.py
```

can be built with one of two modes:

```text
MODE_A:
    cost conversion available -> net R computed

MODE_B:
    conversion unavailable -> gross R + spread_points diagnostics only
```

---

## 8. Gate Update

Current gate after this plan:

```text
DATA_GAP_REMEDIATION_PLAN = CREATED
T1_DATA_GAPS = ACTIVE_NOW
T3_DATA_GAPS = AFTER_T1_FIRST_RESULT
T2_DATA_GAPS = LATER
STAGE39 = NO_GO
```

The project should not wait to fix all gaps before T1. It should fix only T1-critical gaps now.

---

## 9. Recommended Commit

After placing this file in the repo:

```bash
cd ~/Desktop/xauusd-trader
mkdir -p docs
mv ~/Downloads/STAGE38A_DATA_GAP_REMEDIATION_PLAN.md docs/STAGE38A_DATA_GAP_REMEDIATION_PLAN.md
git status --short
git add -A
git commit -m "Add Stage38A data gap remediation plan"
git pull --rebase origin main
git push
```

---

## 10. Practical Next Step

Next artifact:

```text
docs/STAGE38A_AMARKETS_XAUUSD_SYMBOL_SPEC_CAPTURE.md
```

This should be created before the read-only script if we want true net-cost R. If we want speed, we can create the script first with unresolved cost conversion, but that would keep results diagnostic-only.
