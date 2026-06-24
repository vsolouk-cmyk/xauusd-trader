# XAUUSD Stage38A Transfer Pack — After T1 Final Diagnostics

**Project:** XAUUSD / Gold Trading System  
**Generated UTC:** 2026-06-16T14:17:57Z  
**Purpose:** Transfer current session state to a fresh session  
**Current status:** T1 concluded as low-confidence 2025-dominated research candidate  
**Next recommended phase:** COT/T3 data foundation  
**Stage39:** NO-GO  
**EA / paper-live / live order:** NO-GO

---

چپ‌چین ادامه می‌دهم.

این بسته برای انتقال سشن است. سشن فعلی سنگین شده و بهتر است ادامه در یک سشن تازه انجام شود.

---

## 1. Standing User Preferences

```text
- پاسخ‌ها برای پروژه XAUUSD با عبارت «چپ‌چین ادامه می‌دهم.» شروع شوند.
- از رفت‌وبرگشت غیرضروری پرهیز شود.
- وقتی گام بعدی روشن است، فایل/پچ و دستور انتقال در همان پیام داده شود.
- برای انتقال فایل از Downloads به ریپو از mv استفاده شود، نه cp.
- توضیحات فارسی کامل و فنی باشد، اما قالب ساده باشد.
- HTML یا wrapper راست‌چین اجباری استفاده نشود.
- code block فقط برای command/path/log/raw content استفاده شود.
- در پایان پیام‌های اجرایی «گام بعدی» روشن باشد.
```

---

## 2. Environment

Local repo:

```text
~/Desktop/xauusd-trader
```

Main language/tooling:

```text
Python 3
SQLite
macOS terminal
GitHub repo
```

Core DB:

```text
data/local/xauusd_local_store.sqlite
```

Primary tables used:

```text
bars
macro_daily_regime
```

Primary symbol/source:

```text
source = amarkets_mt5
symbol = XAUUSD
timeframe = 1h
```

---

## 3. Stage38A Big Decision

Old direction:

```text
pattern mining / variant mining / Stage36-37 revival
```

was stopped.

New direction:

```text
thesis-first gold market model
data audit
execution realism
trade construction
read-only validation
```

Stage39 remains blocked.

---

## 4. Data Audit Summary

Confirmed usable:

```text
H1 AMarkets XAUUSD bars:
    rows = 25,643
    date range = 2022-05-01 to 2026-06-16

1m AMarkets XAUUSD bars:
    rows ≈ 1,536,273

macro_daily_regime:
    rows = 1,620
    date range = 2022-01-01 to 2026-06-08

event reaction layer:
    present but not true forecast/surprise layer
```

Known issues:

```text
macro_context_h1 labels collapsed to neutral; do not use it.
Use macro_daily_regime joined by date.
COT missing.
ETF flow missing.
forecast/consensus missing.
```

---

## 5. AMarkets XAUUSD Symbol Spec

From MT5 screenshot:

```text
SYMBOL = XAUUSD
DIGITS = 2
POINT = 0.01
CONTRACT_SIZE = 100
SPREAD_TYPE = floating
STOPS_LEVEL = 0
PROFIT_CURRENCY = USD
MARGIN_CURRENCY = USD
CALCULATION = CFD Leverage
MIN_VOLUME = 0.01
MAX_VOLUME = 100
VOLUME_STEP = 0.01
SWAP_TYPE = In points
SWAP_LONG = -64.7
SWAP_SHORT = 34.1
TRIPLE_SWAP_DAY = Wednesday
```

Conversion used:

```text
spread_price_distance = spread_points * 0.01
```

Still unresolved:

```text
tick size/value shown as 0 / unreliable
commission not shown
exact server timezone/rollover UTC incomplete
USD P/L per lot not fully resolved
```

---

## 6. Execution Cost Model Used

Stage38A cost model:

```text
raw = 0 points -> 0.00 price units
base_p50 = 37 points -> 0.37 price units
normal_p75 = 43 points -> 0.43 price units
stress_p90 = 49 points -> 0.49 price units
high_p95 = 51 points -> 0.51 price units
tail_p99 = 70 points -> 0.70 price units
```

Main evaluation metric:

```text
r_stress_p90
```

No raw-only pass allowed.

---

## 7. T1 Original Setup

T1:

```text
T1_REGIME_FILTERED_STRUCTURE_CONTINUATION
```

Initial variant grid:

```text
2 levels:
    previous_day_high
    rolling_48h_high

3 entries:
    V1_CLOSE_ACCEPTANCE
    V2_RETEST_CONFIRMATION
    V3_STRICT_NEXT_BAR_HOLD

2 targets:
    TP_1R
    TP_1_5R

1 time stop:
    TIME_5H
```

Total variants:

```text
12
```

---

## 8. First T1 Read-only Result

Output:

```text
trade_count_total = 3438
variant_count = 12
pass_research_interest_count = 2
watchlist_count = 3
kill_count = 7
```

Best first-pass variant:

```text
V3_STRICT_NEXT_BAR_HOLD__rolling_48h_high__TP_1R__TIME_5H
trade_count = 127
stress_p90_pf = 1.31535809
avg_R_p90 = 0.10203053
```

But deep diagnostics showed:

```text
2022 = -3.34R
2023 = -8.53R
2024 = +0.92R
2025 = +23.91R
```

Conclusion:

```text
T1 first-pass edge = 2025-dependent
```

---

## 9. Era Ablation

Best first-pass variant:

```text
FULL:
    pf = 1.31535809
    net_R = +12.96R

EXCLUDE_2025:
    pf = 0.63550192
    net_R = -10.95R

ERA_2025_ONLY:
    pf = 3.16391321
    net_R = +23.91R
```

Decision:

```text
2025_DEPENDENT_EDGE
```

---

## 10. 2025 Feature Diagnostic

Potential 2025 separation features:

```text
ATR_H1_14 higher
D1 distance from MA50 higher
H4 distance from MA50 higher
```

Macro score alone was not sufficient:

```text
macro_score_long_gold was higher in pre2025, but pre2025 performance was worse.
```

Interpretation:

```text
T1 is more structural expansion than pure macro score.
```

---

## 11. Normalized Structural Filter

Locked filter:

```text
d1_trend_pct = (d1_close - d1_ma50) / d1_ma50
h4_trend_pct = (h4_close - h4_ma50) / h4_ma50
atr_pct_price = atr_h1_14 / entry_price

d1_trend_pct >= 0.05
h4_trend_pct >= 0.02
atr_pct_price >= 0.003
```

On original first-pass best variant:

```text
selected_trades = 33
selected_pf = 4.3902
selected_net_R = +15.55R
selected_pre2025_pf = 1.6263
selected_pre2025_net_R = +0.91R
```

This justified locked retest across all 12 variants.

---

## 12. Locked Structural Filter Retest Across 12 Variants

Result:

```text
variant_count = 12
pass_count = 2
watch_count = 6
weak_count = 2
kill_count = 2
```

Lead locked variant:

```text
V1_CLOSE_ACCEPTANCE__previous_day_high__TP_1_5R__TIME_5H

selected_trades = 94
selected_pf = 1.7004909
selected_net_R = +24.4149R
selected_pre2025_net_R = +2.4112R
rejected_pf = 0.8679597
decision = LOCKED_FILTER_PASS_RESEARCH
```

Interpretation:

```text
The edge is not only the V3 strict-hold entry.
The structural-expansion state is the key explanatory condition.
```

---

## 13. Final Locked Candidate Diagnostics

Lead variant:

```text
V1_CLOSE_ACCEPTANCE__previous_day_high__TP_1_5R__TIME_5H
```

Final result:

```text
trade_count = 94
pf = 1.7004909028327415
net_R = 24.41491088
avg_R = 0.2597330944680851
win_rate = 0.574468085106383
max_dd_R = 7.130497549999998

pre2025_trade_count = 25
pre2025_pf = 1.272298309086442
pre2025_net_R = 2.41122672

y2025_trade_count = 69
y2025_pf = 1.8463310631770342
y2025_net_R = 22.00368416

max_year_positive_contribution_share = 0.8742361341528676
max_month_positive_contribution_share = 0.5202378975146063

candidate_decision = LOCKED_CANDIDATE_LOW_CONFIDENCE_2025_DOMINATED
```

Final decision:

```text
T1 is positive but not promotable.
```

---

## 14. Final T1 Status

```text
T1_STATUS = LOW_CONFIDENCE_2025_DOMINATED_RESEARCH_CANDIDATE
T1_ACTIVE_DEVELOPMENT = PAUSED
T1_FORWARD_OBSERVATION = OPTIONAL_LATER
STAGE39 = NO_GO
EA = NO_GO
PAPER_LIVE = NO_GO
LIVE_ORDER = NO_GO
```

Reason:

```text
2025 contributes 87.42% of positive yearly contribution.
2025-04 contributes 52.02% of positive monthly contribution.
```

---

## 15. Recommended Next Phase

Primary next phase:

```text
Stage38B / T3 COT data foundation
```

Why:

```text
T1 reached a useful conclusion but is not promotable.
T3 remains blocked by missing COT.
COT is free.
COT is directly tied to positioning / squeeze / crowding thesis.
```

Next artifacts in fresh session:

```text
docs/STAGE38B_COT_DATA_PLAN.md
tools/stage38b_download_cftc_cot_gold.py
app/stage38b_cot_gold_loader.py
data/reports/stage38b_cot_audit/
```

Do not start with live trading.

---

## 16. Optional Later T1 Forward Observation

Only if needed:

```text
app/stage38a_t1_locked_candidate_forward_monitor.py
```

Rules:

```text
read-only
no orders
no Telegram trade alerts
no paper/live
no EA
no Stage39
```

But this is secondary. COT/T3 is recommended first.

---

## 17. Files Created in Current Session

Important docs/scripts:

```text
STAGE38A_GOLD_MARKET_THESIS_ROADMAP.md
STAGE38A_GOLD_MARKET_THESIS_RECONSTRUCTION.md
STAGE38A_THESIS_TEMPLATES_V0.md
STAGE38A_DATA_FEASIBILITY_MATRIX.md
STAGE38A_SENIOR_REVIEW_ACTION_PLAN.md
STAGE38A_LOCAL_DATA_AUDIT_CHECKLIST.md
STAGE38A_LOCAL_DATA_AUDIT_RESULT_V0.md
STAGE38A_LOCAL_DATA_AUDIT_RESULT_V1_SCHEMA_HEADERS.md
STAGE38A_LOCAL_DATA_AUDIT_RESULT_V2_COVERAGE.md
STAGE38A_SPREAD_PERCENTILE_AUDIT_RESULT.md
STAGE38A_EXECUTION_COST_MODEL_V0.md
STAGE38A_TRADE_CONSTRUCTION_SPEC_V0.md
STAGE38A_T1_READ_ONLY_TEST_DESIGN.md
STAGE38A_T1_IMPLEMENTATION_PLAN_READ_ONLY.md
STAGE38A_DATA_GAP_REMEDIATION_PLAN.md
STAGE38A_AMARKETS_XAUUSD_SYMBOL_SPEC_CAPTURE.md
STAGE38A_AMARKETS_XAUUSD_SYMBOL_SPEC_EXTRACTED.md
STAGE38A_T1_READ_ONLY_RESULT_REVIEW.md
STAGE38A_T1_DEEP_DIAGNOSTICS_REVIEW.md
STAGE38A_T1_ERA_ABLATION_REVIEW.md
STAGE38A_T1_2025_REGIME_DIAGNOSTIC_REVIEW.md
STAGE38A_T1_NORMALIZED_FILTER_REVIEW.md
STAGE38A_T1_LOCKED_STRUCTURAL_FILTER_RETEST_REVIEW.md
STAGE38A_T1_FINAL_CANDIDATE_DECISION.md
```

Scripts:

```text
stage38a_audit_sqlite_coverage.sh
stage38a_audit_spread_percentiles.sh
app/stage38a_t1_read_only_test.py
app/stage38a_t1_deep_diagnostics.py
app/stage38a_t1_era_ablation.py
app/stage38a_t1_2025_regime_diagnostic.py
app/stage38a_t1_normalized_regime_filter_diagnostic.py
app/stage38a_t1_locked_structural_filter_retest.py
app/stage38a_t1_locked_candidate_final_diagnostics.py
```

---

## 18. Suggested New Session Opening Prompt

Use this prompt in the new session:

```text
چپ‌چین ادامه بده. این بسته انتقالی پروژه XAUUSD Stage38A است. لطفاً ابتدا آن را مبنا قرار بده و بدون برگشت غیرضروری ادامه بده.

وضعیت فعلی:
- T1 به‌عنوان LOW_CONFIDENCE_2025_DOMINATED_RESEARCH_CANDIDATE بسته شد.
- Stage39، EA، paper-live و live order همگی NO-GO هستند.
- توسعه فعال T1 متوقف شود.
- گام بعدی پیشنهادی: Stage38B / T3 COT data foundation.
- هدف: ساخت برنامه و سپس ابزار رایگان CFTC COT برای gold positioning، بدون هزینه و بدون live trading.

لطفاً گام بعدی را از docs/STAGE38B_COT_DATA_PLAN.md شروع کن و اگر روشن است همان پیام فایل و دستورات mv/git را بده.
```

---

## 19. Commit This Transfer Pack

```bash
cd ~/Desktop/xauusd-trader
mkdir -p docs
mv ~/Downloads/XAUUSD_STAGE38A_TRANSFER_PACK_AFTER_T1.md docs/XAUUSD_STAGE38A_TRANSFER_PACK_AFTER_T1.md
git status --short
git add -A
git commit -m "Add Stage38A transfer pack after T1 final diagnostics"
git pull --rebase origin main
git push
```
