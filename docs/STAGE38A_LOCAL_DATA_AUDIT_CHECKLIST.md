# Stage38A — Local Data Audit Checklist

**Project:** XAUUSD / Gold Trading System  
**Stage:** Stage38A  
**Document type:** Local data inventory and readiness audit checklist  
**Generated UTC:** 2026-06-16T11:56:18Z  
**Status:** Required before any Stage39 implementation  
**Cost policy:** FREE-FIRST ONLY  
**Execution authorization:** NO EA, NO paper-live, NO live order, NO strategy backtest

---

چپ‌چین ادامه می‌دهم.

این سند، audit عملی داده‌های موجود پروژه است. هدف آن این است که قبل از ساخت هر loader یا backtest جدید، دقیقاً بدانیم چه داریم، چه نداریم، چه کیفیتی دارد، و کدام thesis واقعاً با داده موجود قابل شروع است.

این checklist با در نظر گرفتن نقد متخصص تکمیل شده است. بنابراین علاوه بر داده‌های price/macro/flow، این بار execution realism هم جزئی از audit است.

---

## 1. Audit Decision

تا وقتی این audit انجام نشده، Stage39 مجاز نیست.

Current status:

```text
LOCAL_DATA_AUDIT=REQUIRED
STAGE39=NO_GO
STRATEGY_BACKTEST=NO_GO
LOADER_BUILD=NO_GO_UNTIL_GAP_CONFIRMED
PAID_DATA=NO_GO
```

این audit باید پاسخ بدهد:

```text
1. آیا داده قیمت XAUUSD کافی داریم؟
2. آیا spread واقعی یا قابل تخمین داریم؟
3. آیا H4/D1 قابل ساخت است؟
4. آیا macro data قبلاً دانلود شده؟
5. آیا real yield/USD/VIX موجود است یا باید رایگان گرفته شود؟
6. آیا COT/ETF نداریم و باید رایگان اضافه شود؟
7. آیا event actual/previous داریم؟
8. آیا forecast/consensus رایگان داریم یا T2 blocked می‌ماند؟
9. آیا داده لازم برای execution cost model داریم؟
10. آیا PF threshold بعداً می‌تواند از cost واقعی استخراج شود؟
```

---

## 2. Audit Scope

این audit فقط read-only است.

مجاز:

```text
find files
inspect folders
inspect CSV headers
inspect SQLite schema
count rows
check date coverage
check missing columns
summarize available data
```

غیرمجاز:

```text
strategy backtest
signal generation
variant generation
Stage39 implementation
EA/paper/live changes
order authorization
paid API usage
```

---

## 3. Repository Structure Audit

### Command

```bash
cd ~/Desktop/xauusd-trader
pwd
find . -maxdepth 3 -type d | sort
```

### Expected Output to Record

```text
REPO_PATH:
APP_DIR_EXISTS:
CONFIGS_DIR_EXISTS:
DATA_DIR_EXISTS:
DOCS_DIR_EXISTS:
TOOLS_DIR_EXISTS:
TESTS_DIR_EXISTS:
GITHUB_WORKFLOWS_EXISTS:
```

### Decision

```text
PASS if repo structure matches cleaned Stage38 transfer status.
FAIL if important directories are missing.
```

---

## 4. Data File Inventory

### Command

```bash
cd ~/Desktop/xauusd-trader
find data -maxdepth 4 -type f | sort > /tmp/xauusd_data_files.txt
sed -n '1,250p' /tmp/xauusd_data_files.txt
wc -l /tmp/xauusd_data_files.txt
```

### Record

```text
TOTAL_DATA_FILES:
RAW_FILES:
NORMALIZED_FILES:
MACRO_FILES:
EXOGENOUS_FILES:
REPORT_FILES:
STORE_FILES:
CSV_FILES:
DB_FILES:
PARQUET_FILES:
JSON_FILES:
```

### Decision

```text
PASS if data folders contain usable price/store files.
WARN if only reports exist but no price/store data.
FAIL if data folder is empty or missing.
```

---

## 5. SQLite Store Audit

### Find DB Files

```bash
cd ~/Desktop/xauusd-trader
find data -name "*.db" -print
```

### Inspect Tables

For each DB found:

```bash
cd ~/Desktop/xauusd-trader
for db in $(find data -name "*.db"); do
  echo "==== DB: $db ===="
  sqlite3 "$db" ".tables"
done
```

### Inspect Schema

```bash
cd ~/Desktop/xauusd-trader
for db in $(find data -name "*.db"); do
  echo "==== SCHEMA: $db ===="
  sqlite3 "$db" ".schema" | sed -n '1,200p'
done
```

### Record

```text
DB_PATH:
TABLES:
PRICE_TABLE_EXISTS:
SPREAD_COLUMN_EXISTS:
TIME_COLUMN_NAME:
SYMBOL_COLUMN_NAME:
OHLC_COLUMNS:
VOLUME_COLUMNS:
ROW_COUNTS:
MIN_TIMESTAMP:
MAX_TIMESTAMP:
```

### Useful Row Count Command

Replace table name after seeing `.tables`:

```bash
sqlite3 data/store/YOUR_DB.db "select count(*), min(ts), max(ts) from YOUR_TABLE;"
```

If timestamp column is different, adapt after inspecting schema.

### Decision

```text
PASS if H1 or lower timeframe XAUUSD data exists with sufficient coverage.
WARN if OHLC exists but spread is missing.
FAIL if no usable price table exists.
```

---

## 6. CSV Header Audit

### Command

```bash
cd ~/Desktop/xauusd-trader
for f in $(find data -name "*.csv" | head -50); do
  echo "==== $f ===="
  head -1 "$f"
  sed -n '2p' "$f"
done
```

### Record

```text
CSV_PATH:
HAS_TIMESTAMP:
HAS_OPEN_HIGH_LOW_CLOSE:
HAS_VOLUME:
HAS_SPREAD:
HAS_BID_ASK:
TIMEZONE_KNOWN:
SAMPLE_ROW_OK:
```

### Decision

```text
PASS if broker CSV has timestamp + OHLC and preferably spread/bid/ask.
WARN if OHLC exists but spread/bid/ask absent.
FAIL if timestamp or OHLC columns are unusable.
```

---

## 7. XAUUSD OHLC Coverage Audit

### Goal

Determine if T1 can start after Stage38A.

### Required Coverage

```text
Minimum useful:
H1 XAUUSD data with enough history for H4/D1 resampling and regime tests.

Preferred:
M15/M5/M1 data for better execution/event reaction analysis.
```

### Record

```text
XAUUSD_H1_AVAILABLE:
XAUUSD_M15_AVAILABLE:
XAUUSD_M5_AVAILABLE:
XAUUSD_M1_AVAILABLE:
START_DATE:
END_DATE:
TOTAL_ROWS:
MISSING_PERIODS:
TIMEZONE:
BROKER_SOURCE:
```

### Decision

```text
T1_DATA_GO if H1 + spread/usable cost proxy + H4/D1 derivation are possible.
T2_INTRADAY_LIMITED if only H1 exists.
T2_EVENT_REACTION_BETTER if M15/M5/M1 exists.
```

---

## 8. Spread / Execution Data Audit

این بخش به‌دلیل نقد متخصص اضافه شده و بسیار مهم است.

### Check Spread Fields

Look for columns such as:

```text
spread
bid
ask
bid_open
ask_open
bid_close
ask_close
```

### Record

```text
SPREAD_AVAILABLE:
BID_ASK_AVAILABLE:
SPREAD_TIME_SERIES_AVAILABLE:
SPREAD_BY_SESSION_POSSIBLE:
SPREAD_AROUND_NEWS_POSSIBLE:
ROLLOVER_WINDOW_IDENTIFIABLE:
SUNDAY_GAP_MEASURABLE:
```

### Minimum Statistics Needed Later

```text
median_spread
spread_p75
spread_p90
spread_p95
spread_by_session
spread_by_hour
spread_near_event
spread_near_rollover
```

### Decision

```text
PASS if spread series exists.
WARN if no spread series but broker typical spread can be manually documented.
FAIL for Stage39 if no cost model can be built.
```

### Important Gate

```text
No candidate can pass Stage39 using raw PF only.
Cost-stressed PF must be derived after this audit.
```

---

## 9. Macro / FRED Data Audit

### Command

```bash
cd ~/Desktop/xauusd-trader
find data/exogenous data/macro -type f | sort
```

### Check Existing Files

```bash
cd ~/Desktop/xauusd-trader
for f in $(find data/exogenous data/macro -type f | head -50); do
  echo "==== $f ===="
  head -5 "$f" 2>/dev/null || true
done
```

### Required Series

```text
DFII10 = 10Y real yield
DTWEXBGS = broad nominal USD index proxy
VIXCLS = VIX
optional SPX proxy
optional Fed funds/SOFR proxy
```

### Record

```text
DFII10_AVAILABLE:
DTWEXBGS_AVAILABLE:
VIXCLS_AVAILABLE:
SPX_PROXY_AVAILABLE:
FED_EXPECTATION_PROXY_AVAILABLE:
MACRO_START_DATE:
MACRO_END_DATE:
MACRO_FREQUENCY:
MISSING_VALUES:
```

### Decision

```text
PASS for T1 if DFII10 + USD proxy are available or can be freely fetched.
WARN if VIX absent; VIX can be added later.
FAIL if macro alignment cannot be performed.
```

---

## 10. Event Data Audit

### Goal

Determine whether T2 is true-surprise feasible or blocked.

### Check Existing Event Files

```bash
cd ~/Desktop/xauusd-trader
find data -iname "*event*" -o -iname "*calendar*" -o -iname "*macro*" | sort
```

### Required for True Surprise

```text
event_type
event_timestamp_utc
actual
forecast
previous
surprise
surprise_z
```

### Record

```text
EVENT_TIMESTAMPS_AVAILABLE:
CPI_ACTUAL_AVAILABLE:
NFP_ACTUAL_AVAILABLE:
PCE_ACTUAL_AVAILABLE:
FOMC_DATES_AVAILABLE:
FORECAST_CONSENSUS_AVAILABLE:
PREVIOUS_VALUES_AVAILABLE:
EVENT_TIMEZONE_KNOWN:
```

### Decision

```text
T2_TRUE_SURPRISE_GO only if forecast/consensus exists or a reliable free path is confirmed.
T2_REACTION_FEASIBILITY_ONLY if actual/previous/timestamps exist but forecast is missing.
T2_BLOCKED if event data is absent or unreliable.
```

### Rule

```text
actual - previous is not consensus surprise.
event/no-event is not surprise modeling.
```

---

## 11. COT / Positioning Audit

### Check Existing COT Files

```bash
cd ~/Desktop/xauusd-trader
find data -iname "*cot*" -o -iname "*cftc*" -o -iname "*position*" | sort
```

### Required for T3

```text
CFTC gold futures weekly positioning
non-commercial long
non-commercial short
net speculative = long - short
rolling percentile
4-week change
```

### Record

```text
COT_AVAILABLE:
COT_SOURCE:
GOLD_CONTRACT_MAPPED:
NONCOMM_LONG_AVAILABLE:
NONCOMM_SHORT_AVAILABLE:
NET_SPEC_COMPUTABLE:
COT_START_DATE:
COT_END_DATE:
WEEKLY_ALIGNMENT_POSSIBLE:
```

### Decision

```text
T3_GO_AFTER_COT if COT can be freely downloaded and aligned.
T3_BLOCKED if COT mapping or parsing fails.
```

---

## 12. ETF Flow Audit

### Check Existing ETF Files

```bash
cd ~/Desktop/xauusd-trader
find data -iname "*etf*" -o -iname "*gld*" -o -iname "*iau*" -o -iname "*wgc*" | sort
```

### Required / Optional

```text
ETF is useful for T3 and T1 filtering, but not mandatory for first COT-only feasibility.
```

### Record

```text
ETF_FLOW_AVAILABLE:
ETF_HOLDINGS_AVAILABLE:
SOURCE:
FREQUENCY:
START_DATE:
END_DATE:
FLOW_20D_COMPUTABLE:
```

### Decision

```text
PASS if free ETF data is available.
WARN if ETF missing; do not block T1/T3 COT-only.
FAIL only if project later claims ETF-based thesis without ETF data.
```

---

## 13. Multi-Timeframe Derivation Audit

### Goal

Confirm H4/D1 can be derived consistently.

### Required

```text
timestamp timezone known
session/calendar handling known
no duplicated timestamps
no severe missing gaps
H1 → H4 resampling possible
H1/H4 → D1 resampling possible
```

### Record

```text
TIMEZONE_KNOWN:
DUPLICATES_FOUND:
GAPS_FOUND:
H4_DERIVABLE:
D1_DERIVABLE:
BROKER_DAY_BOUNDARY:
```

### Decision

```text
PASS if H4/D1 bars can be derived reproducibly.
WARN if broker day boundary is unclear.
FAIL if timestamp quality is too poor.
```

---

## 14. Local Reports Audit

### Command

```bash
cd ~/Desktop/xauusd-trader
find data/reports docs -type f | sort | sed -n '1,250p'
```

### Required Reports to Keep Visible

```text
STAGE38A_GOLD_MARKET_THESIS_ROADMAP.md
STAGE38A_GOLD_MARKET_THESIS_RECONSTRUCTION.md
STAGE38A_THESIS_TEMPLATES_V0.md
STAGE38A_DATA_FEASIBILITY_MATRIX.md
STAGE38A_LOCAL_DATA_AUDIT_CHECKLIST.md
STAGE38A_SENIOR_REVIEW_ACTION_PLAN.md
```

### Decision

```text
PASS if Stage38A docs are committed.
WARN if docs exist only in Downloads, not repo.
```

---

## 15. Audit Output Template

After running the audit, create or paste results in this format:

```text
REPO_PATH:
AUDIT_DATE:

1. PRICE_DATA
XAUUSD_H1:
XAUUSD_M15:
XAUUSD_M5:
XAUUSD_M1:
START_DATE:
END_DATE:
SPREAD_AVAILABLE:
BID_ASK_AVAILABLE:
TIMEZONE:

2. STORE
DB_FILES:
TABLES:
PRICE_TABLE:
ROW_COUNT:
MIN_TS:
MAX_TS:

3. MACRO
DFII10:
DTWEXBGS:
VIXCLS:
SPX_PROXY:
FED_PROXY:

4. EVENT
CPI_ACTUAL:
NFP_ACTUAL:
PCE_ACTUAL:
FOMC_DATES:
FORECAST_CONSENSUS:

5. POSITIONING
COT_AVAILABLE:
ETF_AVAILABLE:

6. EXECUTION
SPREAD_PERCENTILES_POSSIBLE:
NEWS_SPREAD_POSSIBLE:
ROLLOVER_COST_SOURCE:
GAP_RISK_MEASURABLE:
SLIPPAGE_MODEL_POSSIBLE:

7. THESIS_READINESS
T1:
T2:
T3:

8. BLOCKERS
BLOCKER_1:
BLOCKER_2:
BLOCKER_3:
```

---

## 16. Thesis Readiness Rules After Audit

### T1

```text
GO if:
XAUUSD H1 + H4/D1 derivation + spread/cost proxy + DFII10 + USD proxy are available.
```

### T2

```text
GO only if:
event actual/forecast/previous + timestamps + intraday reaction data are available.

Otherwise:
T2_EVENT_REACTION_FEASIBILITY_ONLY or BLOCKED.
```

### T3

```text
GO if:
COT free data can be fetched/aligned + D1/H4 structure exists.

ETF flow is optional for v0.
```

---

## 17. Senior Review Additions to Audit

Because of the senior review, these are now mandatory audit questions:

```text
[ ] Can we build a spread percentile model?
[ ] Can we identify news-window spread behavior?
[ ] Can we identify rollover windows?
[ ] Can we estimate Sunday/open gaps?
[ ] Can we define cost-stressed PF from real or conservative costs?
[ ] Do T2/T3 have enough data for precise execution rules?
[ ] Can low-frequency T3 trades be reviewed with a structured form?
[ ] Can degradation be diagnosed by regime/spread/event/MTF/positioning?
```

If the answer is no, Stage39 remains blocked.

---

## 18. Recommended Commit

After placing this file in the repo:

```bash
cd ~/Desktop/xauusd-trader
git status --short
git add -A
git commit -m "Add Stage38A local data audit checklist"
git pull --rebase origin main
git push
```

---

## 19. Practical Next Step

Run these three commands first and paste the output:

```bash
cd ~/Desktop/xauusd-trader
find data -maxdepth 4 -type f | sort | sed -n '1,250p'
find data -name "*.db" -print
find data/exogenous data/macro -type f | sort
```

Then run SQLite schema inspection if DB files exist:

```bash
cd ~/Desktop/xauusd-trader
for db in $(find data -name "*.db"); do
  echo "==== DB: $db ===="
  sqlite3 "$db" ".tables"
  sqlite3 "$db" ".schema" | sed -n '1,200p'
done
```

No strategy code should be written before the audit result is reviewed.
