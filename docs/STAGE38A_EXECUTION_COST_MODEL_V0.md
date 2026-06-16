# Stage38A — Execution Cost Model v0

**Project:** XAUUSD / Gold Trading System  
**Stage:** Stage38A  
**Document type:** Conservative execution cost model for pre-Stage39 thesis testing  
**Generated UTC:** 2026-06-16T12:23:08Z  
**Status:** Required gate before any Stage39 strategy backtest  
**Execution authorization:** NO EA, NO paper-live, NO live order  
**Cost policy:** FREE-FIRST ONLY

---

چپ‌چین ادامه می‌دهم.

این سند مدل هزینه اجرای v0 برای پروژه XAUUSD است. هدف آن پاسخ مستقیم به بدهی execution realism است که در نقد متخصص مطرح شد.

این مدل هنوز مدل نهایی execution نیست. این یک مدل محافظه‌کارانه، رایگان، قابل audit و قابل استفاده برای تست‌های read-only آینده است.

---

## 1. Executive Decision

مدل هزینه v0 بر اساس داده spread موجود در AMarkets MT5 local store ساخته می‌شود.

منبع اصلی:

```text
data/local/xauusd_local_store.sqlite
table: bars
source: amarkets_mt5
symbol: XAUUSD
timeframes: 1m and 1h
```

داده‌های دیگر:

```text
TwelveData OHLC = allowed for price backup only
TwelveData spread = not allowed
Stage33D cost gate = historical reference only, not full cost model
```

Current decision:

```text
EXECUTION_COST_MODEL_V0 = CREATED
COST_UNIT = spread_points
POINT_TO_PRICE_CONVERSION = NOT_CONFIRMED
BASE_COST = CONSERVATIVE_OBSERVED_P50
DEFAULT_STRESS = OBSERVED_1M_P90
OPEN_ROLLOVER_WINDOWS = BLOCKED_BY_DEFAULT
NEWS_TRADES = HIGH_STRESS_OR_NO_TRADE
STAGE39 = STILL_BLOCKED_UNTIL TRADE DESIGN GATE
```

---

## 2. Data Basis

Observed spread audit:

```text
1m spread rows = 79,606
1m coverage = 2022-05-01T23:01:00Z to 2026-06-09T01:00:00Z

1h spread rows = 1,304
1h coverage = 2022-05-01T23:00:00Z to 2026-06-09T00:00:00Z
```

Global 1m percentiles:

```text
min = 15
avg = 37.369357
p50 = 37
p75 = 43
p90 = 49
p95 = 51
p99 = 70
max = 183
```

Important limitation:

```text
Spread samples are heavily concentrated around UTC 23 and UTC 00.
Therefore this is not a full-session spread model.
```

---

## 3. Cost Unit Rule

All v0 cost values are expressed as:

```text
spread_points
```

Do not convert to USD, pip, or price-unit until point conversion is verified from broker/MT5 symbol specification.

Required later:

```text
SYMBOL_POINT:
SYMBOL_DIGITS:
CONTRACT_SIZE:
TICK_SIZE:
TICK_VALUE:
COMMISSION:
SWAP_LONG:
SWAP_SHORT:
```

Until then:

```text
Backtest comparisons may use spread_points consistently.
Final monetary interpretation is not allowed.
```

---

## 4. v0 Spread Cost Levels

Use the 1m distribution as primary.

```text
BASE_SPREAD_POINTS = 37
NORMAL_STRESS_SPREAD_POINTS = 43
DEFAULT_COST_STRESS_SPREAD_POINTS = 49
HIGH_STRESS_SPREAD_POINTS = 51
TAIL_STRESS_SPREAD_POINTS = 70
ABSOLUTE_OBSERVED_MAX_SPREAD_POINTS = 183
```

Interpretation:

```text
BASE_SPREAD_POINTS:
    conservative observed p50, likely already biased upward by UTC 23/00 sampling.

NORMAL_STRESS_SPREAD_POINTS:
    observed p75.

DEFAULT_COST_STRESS_SPREAD_POINTS:
    observed p90.
    This should be the default threshold for research pass/fail.

HIGH_STRESS_SPREAD_POINTS:
    observed p95.
    Use for news/proximity stress.

TAIL_STRESS_SPREAD_POINTS:
    observed p99.
    Use for open/rollover/news-tail stress tests.

ABSOLUTE_OBSERVED_MAX:
    not default; used for sanity/tail stress only.
```

---

## 5. Default Testing Cost Policy

Any future T1 read-only backtest must report at least three versions:

```text
RAW_NO_COST
BASE_COST_P50
DEFAULT_STRESS_P90
```

Preferred full report:

```text
RAW_NO_COST
BASE_COST_P50_37
NORMAL_STRESS_P75_43
DEFAULT_STRESS_P90_49
HIGH_STRESS_P95_51
TAIL_STRESS_P99_70
```

Pass decision cannot use raw-only result.

Minimum future reporting columns:

```text
gross_pf
base_cost_pf
stress_p90_pf
stress_p95_pf
avg_R_gross
avg_R_p90
max_dd_p90
trade_count
cost_sensitivity_ratio
```

---

## 6. Open / Rollover Window Rule

Observed Sunday/Monday open proxy:

```text
Sunday 22 UTC 1m:
avg=35.41
max=179

Sunday 23 UTC 1m:
avg=41.02
max=181

Monday 00 UTC 1m:
avg=36.64
max=179

Monday 01 UTC 1m:
avg=42.40
max=74
```

Default rule:

```text
BLOCK_NEW_ENTRIES:
    Sunday 22:00-23:59 UTC
    Monday 00:00-01:59 UTC
```

For open positions:

```text
If holding through blocked window:
    use at least TAIL_STRESS_SPREAD_POINTS = 70
    and add gap-risk flag.
```

No new Stage39 candidate may pass if it depends on entries during blocked open/rollover windows.

---

## 7. News / Event Window Rule

No true news-window spread model exists yet.

Therefore:

```text
NEWS_ENTRY_DEFAULT = NO_TRADE
```

If a future thesis explicitly trades post-event continuation:

```text
Use HIGH_STRESS_SPREAD_POINTS = 51 minimum.
Use TAIL_STRESS_SPREAD_POINTS = 70 for first reaction-window robustness.
Do not enter before event release.
Do not enter while spread is in extreme/open window.
```

For T2:

```text
T2_TRUE_SURPRISE remains blocked.
T2_EVENT_REACTION_FEASIBILITY may report hypothetical returns but cannot be treated as executable without news spread/slippage model.
```

---

## 8. Limit Order Fill Rule

Because actual fill data is unavailable:

```text
PERFECT_LIMIT_FILL = FORBIDDEN
```

Any retest/limit-style entry must use a conservative assumption:

```text
A limit entry is counted as filled only if price trades beyond the level by at least a fill_buffer.
```

Initial fill buffer:

```text
fill_buffer_points = max(BASE_SPREAD_POINTS, ATR_fraction_buffer)
```

If this is not implemented in a future read-only design:

```text
Only close-confirmation/market-at-next-bar assumptions are allowed.
```

---

## 9. Stop Execution Rule

Stops must be modeled conservatively.

For normal windows:

```text
stop_fill = stop_level adjusted by DEFAULT_COST_STRESS_SPREAD_POINTS
```

For news/open/rollover/gap windows:

```text
stop_fill = worse of:
    stop_level adjusted by TAIL_STRESS_SPREAD_POINTS
    next available adverse bar price
```

No candidate may assume stop fills exactly at stop level during event/open stress.

---

## 10. Slippage Rule

No direct slippage data exists.

Therefore v0 uses synthetic conservative slippage:

```text
NORMAL_SLIPPAGE_POINTS = 0.25 * DEFAULT_COST_STRESS_SPREAD_POINTS
HIGH_STRESS_SLIPPAGE_POINTS = 0.50 * HIGH_STRESS_SPREAD_POINTS
TAIL_SLIPPAGE_POINTS = 1.00 * TAIL_STRESS_SPREAD_POINTS
```

For first T1 structure continuation test:

```text
Report with spread-only first.
Then report spread + synthetic slippage stress.
```

Promotion requires surviving spread + slippage stress, not just spread.

---

## 11. Rollover / Swap Rule

Swap/rollover cost is not yet documented.

Until broker swap is manually recorded:

```text
NO_NEW_TRADES_NEAR_ROLLOVER = TRUE
HOLDING_THROUGH_ROLLOVER = DISCOURAGED
SWAP_COST = UNKNOWN
```

For tests that hold beyond intraday:

```text
Apply swap_unknown_flag.
Do not promote candidate if profitability depends on overnight holding before swap is modeled.
```

Future required manual fields:

```text
BROKER_SWAP_LONG_XAUUSD:
BROKER_SWAP_SHORT_XAUUSD:
TRIPLE_SWAP_DAY:
ROLLOVER_TIME_SERVER:
ROLLOVER_TIME_UTC:
SOURCE_DATE:
```

---

## 12. Gap Risk Rule

Gap model is not complete.

For now:

```text
NO_NEW_ENTRIES_NEAR_WEEKEND_CLOSE = TRUE
NO_NEW_ENTRIES_SUNDAY_OPEN = TRUE
```

If a trade holds through weekend:

```text
candidate must report weekend_gap_exposure_count
candidate must use tail stress
candidate cannot be promoted without separate gap audit
```

---

## 13. Cost-Stressed PF Decision Rule

Future research pass thresholds:

```text
RAW_PF:
    informational only

BASE_COST_PF:
    must be > 1.25 for research interest

DEFAULT_STRESS_P90_PF:
    must be >= 1.10 minimum

HIGH_STRESS_P95_PF:
    should remain near or above 1.00

TAIL_STRESS_P99_PF:
    diagnostic only; not mandatory pass for ordinary non-news T1
```

More important than raw PF:

```text
stress_p90_pf
avg_R_p90
max_dd_p90
cost_sensitivity_ratio
performance_inside_permitted_regime
```

If a strategy fails under p90 cost:

```text
Do not rescue it by reducing cost assumption unless broker unit conversion proves the assumption was wrong.
```

---

## 14. T1-Specific Cost Application

For T1 Regime-filtered Structure Continuation:

```text
Allowed:
    H1/H4/D1 structure trades outside blocked windows.
    Retest/confirmation entries with conservative fill logic.
    Read-only test design after this cost model.

Required:
    report p50/p75/p90/p95 cost sensitivity.
    block Sunday/Monday open entries.
    use macro_daily_regime rather than neutral-only macro_context_h1 labels.
    use AMarkets OHLC as primary source.
```

T1 cannot pass if:

```text
It only works at RAW_NO_COST.
It fails under DEFAULT_STRESS_P90.
It relies on blocked open/rollover windows.
It assumes perfect limit fills.
It uses macro_context_h1 neutral labels as if they were meaningful regimes.
```

---

## 15. T2-Specific Cost Application

For T2 Event Surprise:

```text
T2_TRUE_SURPRISE = BLOCKED
T2_EVENT_REACTION_FEASIBILITY_ONLY = ALLOWED_LATER
```

Cost rule:

```text
No executable event thesis can pass without news-window spread/slippage model.
Any event reaction analysis before that is observational, not executable.
```

---

## 16. T3-Specific Cost Application

For T3 Positioning Squeeze:

```text
T3 = BLOCKED_UNTIL_COT
```

Cost rule:

```text
Because T3 is lower-frequency and may hold longer, swap and gap risk matter more.
No promotion without swap/gap audit.
```

---

## 17. Required Next Fields Before Stage39

Still needed:

```text
[ ] point-to-price conversion verified
[ ] AMarkets XAUUSD symbol digits verified
[ ] tick size/value verified if monetary R is used
[ ] commission verified
[ ] swap long/short documented
[ ] rollover time documented
[ ] gap audit performed if holding overnight/weekend
[ ] T1 trade construction finalized
```

---

## 18. Gate Status

Current gate:

```text
EXECUTION_COST_MODEL_V0 = CREATED
T1_READ_ONLY_TEST_DESIGN = ALLOWED_NEXT
T1_STRATEGY_BACKTEST = STILL_BLOCKED_UNTIL_TRADE_CONSTRUCTION_SPEC
T2_TRUE_SURPRISE = BLOCKED
T3 = BLOCKED
EA_PAPER_LIVE_ORDER = NO_GO
```

This document moves the project one step closer to Stage39, but does not authorize Stage39 code yet.

---

## 19. Recommended Commit

After placing this file in the repo:

```bash
cd ~/Desktop/xauusd-trader
mkdir -p docs
cp ~/Downloads/STAGE38A_EXECUTION_COST_MODEL_V0.md docs/STAGE38A_EXECUTION_COST_MODEL_V0.md
git status --short
git add -A
git commit -m "Add Stage38A execution cost model v0"
git pull --rebase origin main
git push
```

---

## 20. Practical Next Step

Next document:

```text
docs/STAGE38A_TRADE_CONSTRUCTION_SPEC_V0.md
```

Purpose:

```text
Turn T1/T2/T3 thesis templates into exact entry/stop/target/time-stop/sizing/fill rules.
```

For speed, T1 should be completed first. T2/T3 remain blocked/limited.
