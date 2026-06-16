# Stage38A — Spread Percentile Audit Result

**Project:** XAUUSD / Gold Trading System  
**Stage:** Stage38A  
**Document type:** Spread percentile audit result and execution-readiness decision  
**Generated UTC:** 2026-06-16T12:23:08Z  
**Input:** `data/reports/stage38a_local_data_audit/spread_percentile_audit.txt`  
**Execution authorization:** NO EA, NO paper-live, NO live order, NO strategy backtest  
**Cost policy:** FREE-FIRST ONLY

---

چپ‌چین ادامه می‌دهم.

این سند نتیجه بررسی خروجی spread percentile audit است. هدف این مرحله پاسخ به نقد متخصص درباره execution realism بود: آیا داده‌ای داریم که بتواند مدل هزینه اجرای XAUUSD را حداقل در سطح v0 پشتیبانی کند؟

پاسخ کوتاه:

```text
YES, but only partially.
```

داده spread داریم، اما پوشش آن کامل intraday نیست. نمونه‌ها به‌شدت حوالی ساعت‌های 23 و 00 UTC متمرکزند. بنابراین این داده برای مدل stress/rollover/open بسیار مفید است، اما برای base spread تمام روز کافی نیست.

---

## 1. Executive Decision

نتیجه تصمیمی:

```text
SPREAD_DATA_EXISTS = YES
SPREAD_COVERAGE_YEARS = 2022-05 to 2026-06
SPREAD_PERCENTILES_USABLE = YES
SPREAD_BY_HOUR = YES
SPREAD_BY_WEEKDAY = YES
SPREAD_BY_SESSION = NO_OUTPUT
SPREAD_SAMPLE_BIASED_TO_UTC_23_00 = YES
BASE_INTRADAY_SPREAD_MODEL = SYNTHETIC_CONSERVATIVE_REQUIRED
ROLLOVER_OPEN_STRESS_MODEL = DATA_SUPPORTED
UNIT_CONVERSION = NOT_CONFIRMED
STAGE38A_EXECUTION_COST_MODEL_V0 = CAN_BE_CREATED
STAGE39 = STILL_NO_GO
```

مهم‌ترین تصمیم:

```text
Use AMarkets observed spread as a broker-specific stress proxy.
Do not assume it represents full-session normal spread.
Do not convert spread_points to USD until MT5 point/digit/contract conventions are verified.
```

---

## 2. Spread Coverage Window

Audit output:

```text
1h spread rows = 1,304
1h min_spread_utc = 2022-05-01T23:00:00+00:00
1h max_spread_utc = 2026-06-09T00:00:00+00:00

1m spread rows = 79,606
1m min_spread_utc = 2022-05-01T23:01:00+00:00
1m max_spread_utc = 2026-06-09T01:00:00+00:00
```

### Interpretation

پوشش تاریخی از نظر بازه زمانی خوب است. اما تعداد ردیف‌های spread نسبت به کل price rows حدود ۵٪ بود، پس باید بررسی کنیم این نمونه‌ها نماینده کل روز هستند یا نه.

با توجه به توزیع ساعتی، نمونه‌ها نماینده کل روز نیستند.

---

## 3. Global Spread Percentiles

Audit output:

```text
1h:
min = 15
avg = 34.683282
p50 = 35
p75 = 41
p90 = 43
p95 = 51
p99 = 59
max = 74

1m:
min = 15
avg = 37.369357
p50 = 37
p75 = 43
p90 = 49
p95 = 51
p99 = 70
max = 183
```

### Interpretation

For v0, prefer 1m spread statistics for execution realism because actual execution occurs below H1.

Suggested raw levels in `spread_points`:

```text
BASE_OBSERVED_P50 = 37
NORMAL_STRESS_P75 = 43
HIGH_STRESS_P90 = 49
EXTREME_STRESS_P95 = 51
TAIL_STRESS_P99 = 70
MAX_OBSERVED = 183
```

But these are not yet converted to price or dollars.

### Important Caution

Because samples are concentrated near UTC 23/00, even p50=37 may not represent normal liquid-session spread. It may already be a stressed/open/rollover-biased sample.

Therefore:

```text
Observed p50 should be treated as conservative base, not true median trading-day spread.
```

---

## 4. Spread by UTC Hour

Key finding:

```text
1m hour 00: n=59,184
1m hour 23: n=19,091
1m hour 22: n=948
All other hours have very small sample counts.
```

1h also concentrates around:

```text
hour 00: n=986
hour 23: n=300
hour 22: n=15
hour 21: n=3
```

### Interpretation

This is the most important audit result.

The spread data is not full intraday spread coverage. It appears concentrated around daily open/rollover/collection windows.

This means:

```text
The spread data is good for stress/open/rollover modeling.
The spread data is weak for normal session modeling.
Do not infer London/NY normal spread from this sample.
```

### Execution Cost Consequence

A T1 backtest cannot simply apply observed hour-based spread across all trades unless we explicitly choose a conservative model.

Recommended approach:

```text
For v0, use a conservative fixed spread_points model based on observed p50/p75/p90.
For rollover/open windows, use observed hour 23/00 and Sunday/Monday stress values.
For news windows, use synthetic multiplier because direct news-window spread is not proven.
```

---

## 5. Spread by Session

Audit output for session section was empty.

Interpretation:

```text
SESSION_SPREAD_MODEL = NOT_AVAILABLE
```

Likely reason:

```text
bars table does not include session_utc, or session_utc is null in local bars.
```

Decision:

```text
Do not use session-specific spread model in v0.
Use UTC-hour model instead.
```

---

## 6. Spread by Weekday

Key 1m weekday values:

```text
weekday 0 / Sunday:
n=13,487
p50=40
p90=56
p95=65
max=181

weekday 1 / Monday:
n=14,375
p50=38
p90=51
p95=53
max=183

weekday 2 / Tuesday:
p50=37
p90=46
p95=51
max=84

weekday 3 / Wednesday:
p50=36
p90=45
p95=51
max=160

weekday 4 / Thursday:
p50=37
p90=46
p95=51
max=94

weekday 5 / Friday:
p50=36
p90=45
p95=51
max=82
```

### Interpretation

Sunday/Monday open risk is visible.

Sunday has:

```text
higher p50
higher p90
higher p95
very high max
```

Monday also has high max.

Decision:

```text
Weekend/open gap and spread stress must be explicitly blocked or heavily penalized.
No new T1 entries around Sunday open / Monday early UTC until model is finalized.
```

---

## 7. Monthly Concentration

Spread samples exist across 2022-05 to 2026-06 for both 1h and 1m.

This is positive:

```text
SPREAD_SAMPLE_NOT_ONLY_RECENT = TRUE
```

However, sample count per month is much smaller than all minutes/hours, so it is still sparse.

Important observed shifts:

```text
2022 spreads were generally higher.
2023 varied materially.
2024-2025 often had many months near 30-36 average.
2026 moved higher again, especially Jan-May.
```

### Interpretation

Spread regime changes over years. Execution model should not use a single optimistic cost.

Recommended v0:

```text
Use 1m p50=37 as conservative base.
Use p75=43 as normal stress.
Use p90=49 as cost-stressed backtest default.
Use p95=51 as high-stress.
Use p99=70 / max cap for tail scenario.
```

---

## 8. Sunday/Monday Open Proxy

Audit output:

```text
1m Sunday 22 UTC:
n=895
avg=35.41
max=179

1m Sunday 23 UTC:
n=12,592
avg=41.02
max=181

1m Monday 00 UTC:
n=11,764
avg=36.64
max=179

1m Monday 01 UTC:
n=68
avg=42.40
max=74
```

### Interpretation

Open/rollover stress is real and observable.

Decision:

```text
T1 should block new entries in Sunday 22-23 UTC and Monday 00-01 UTC by default.
If a future setup explicitly wants to trade this window, it must use tail stress.
```

---

## 9. Execution Cost Decision for T1

T1 can proceed to read-only test design only under these constraints:

```text
1. No trade during blocked open/rollover windows.
2. Use cost-stressed PF, not raw PF.
3. Use spread_points cost levels from observed AMarkets sample.
4. Treat p50=37 as conservative base, not optimistic base.
5. Use p90=49 as default cost-stressed scenario.
6. Use p95=51 or p99=70 for event/open stress scenario.
7. Do not use TwelveData spread.
8. Do not convert spread_points to USD until point-size rule is verified.
```

---

## 10. Proposed v0 Cost Levels

All values are in `spread_points`.

```text
BASE_SPREAD_POINTS = 37
NORMAL_STRESS_SPREAD_POINTS = 43
DEFAULT_COST_STRESS_SPREAD_POINTS = 49
HIGH_STRESS_SPREAD_POINTS = 51
TAIL_STRESS_SPREAD_POINTS = 70
ABSOLUTE_OBSERVED_MAX_SPREAD_POINTS = 183
```

Window rules:

```text
BLOCK_NEW_ENTRIES:
    Sunday 22:00-23:59 UTC
    Monday 00:00-01:59 UTC
    rollover/open windows until finalized

NEWS_WINDOW:
    Use HIGH_STRESS or TAIL_STRESS until news-specific spread audit exists.

EVENT_TRADE:
    No event trade may use base spread.

NORMAL_T1_STRUCTURE_TRADE:
    Evaluate with at least DEFAULT_COST_STRESS_SPREAD_POINTS = 49.
```

---

## 11. Remaining Unknowns

Before Stage39 code, still unknown:

```text
1. spread_points to price-unit conversion
2. whether spread includes broker markup only or all round-trip assumptions
3. commission, if any
4. swap/rollover cost
5. slippage during news
6. gap handling
7. partial fill / limit non-fill assumption
8. actual order-fill realism in MT5
```

These must be captured in:

```text
docs/STAGE38A_EXECUTION_COST_MODEL_V0.md
```

---

## 12. Updated Gate

Current gate:

```text
[PASS] AMarkets multi-year OHLC
[PASS] AMarkets spread sample exists
[PASS] spread percentile audit complete
[PASS] open/rollover stress observable
[FAIL] session spread model unavailable
[FAIL] spread_points conversion not confirmed
[FAIL] swap/rollover cost not yet documented
[FAIL] news-specific spread not audited
[BLOCKED] Stage39
```

T1 decision:

```text
T1 = READY_FOR_READ_ONLY_TEST_DESIGN_AFTER_EXECUTION_COST_MODEL_V0
```

Stage39 decision:

```text
STAGE39 = NO_GO_FOR_NOW
```

---

## 13. Recommended Commit

After placing this file in the repo:

```bash
cd ~/Desktop/xauusd-trader
mkdir -p docs
cp ~/Downloads/STAGE38A_SPREAD_PERCENTILE_AUDIT_RESULT.md docs/STAGE38A_SPREAD_PERCENTILE_AUDIT_RESULT.md
git status --short
git add -A
git commit -m "Add Stage38A spread percentile audit result"
git pull --rebase origin main
git push
```

---

## 14. Practical Next Step

Create and commit:

```text
docs/STAGE38A_EXECUTION_COST_MODEL_V0.md
```

That file should turn this audit into fixed cost assumptions and gates for future T1 testing.
