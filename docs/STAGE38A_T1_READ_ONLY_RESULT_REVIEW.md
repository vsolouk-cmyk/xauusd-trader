# Stage38A — T1 Read-only Result Review

**Project:** XAUUSD / Gold Trading System  
**Stage:** Stage38A  
**Document type:** Review of first T1 read-only result  
**Generated UTC:** 2026-06-16T13:18:09Z  
**Status:** First T1 result reviewed; robustness diagnostics required  
**Execution authorization:** NO EA, NO paper-live, NO live order  
**Stage39 authorization:** NO-GO

---

چپ‌چین ادامه می‌دهم.

این سند نتیجه اولین اجرای read-only برای thesis زیر را بررسی می‌کند:

```text
T1_REGIME_FILTERED_STRUCTURE_CONTINUATION
```

خروجی اجرا:

```text
T1_READ_ONLY_TEST = COMPLETED
PASS_RESEARCH_INTEREST_COUNT = 2
WATCHLIST_COUNT = 3
KILL_COUNT = 7
STAGE39 = NO_GO
EA_PAPER_LIVE_ORDER = NO_GO
```

---

## 1. Executive Decision

نتیجه فعلی:

```text
T1_FIRST_READ_ONLY_RESULT = PROMISING_BUT_NOT_PROMOTABLE
EDGE_LOCATION = V3_STRICT_NEXT_BAR_HOLD + rolling_48h_high
STAGE39 = NO_GO
NEXT_STEP = ROBUSTNESS_AND_DEGRADATION_DIAGNOSTICS
```

این نتیجه مثبت است، چون دو variant تحت cost-stressed p90 عبور کرده‌اند. اما هنوز promotion مجاز نیست، چون باید مشخص شود edge از کجا آمده، آیا در سال/ماه خاص متمرکز است، آیا drawdown قابل قبول است، و آیا variant فقط به دلیل یک ساختار خاص یا دوره خاص موفق شده است.

---

## 2. Key Findings

### 2.1 Data Coverage

```text
h1_rows = 25,643
h1_min_utc = 2022-05-01T23:00:00+00:00
h1_max_utc = 2026-06-16T12:00:00+00:00
macro_rows = 1,620
macro_min_date = 2022-01-01
macro_max_date = 2026-06-08
h1_gaps_gt_3h = 219
```

Interpretation:

```text
Price and macro coverage are sufficient for first read-only evaluation.
h1_gaps_gt_3h likely includes weekend/market-close gaps, but must be verified.
```

### 2.2 Cost Model Used

```text
POINT = 0.01
base_p50 = 37 points -> 0.37 price units
stress_p90 = 49 points -> 0.49 price units
tail_p99 = 70 points -> 0.70 price units
```

Interpretation:

```text
The result is not raw-only.
The main ranking uses stress_p90_pf, which is correct.
```

### 2.3 Best Variant

```text
variant_id = V3_STRICT_NEXT_BAR_HOLD__rolling_48h_high__TP_1R__TIME_5H
trade_count = 127
gross_pf = 1.56506351
base_p50_pf = 1.37234125
stress_p90_pf = 1.31535809
avg_R_p90 = 0.10203053
win_rate_p90 = 0.62204724
max_drawdown_R_p90 = 13.31400975
cost_sensitivity_ratio = 0.8404503
decision = PASS_RESEARCH_INTEREST
```

Interpretation:

```text
This is a real research-interest pass.
It survives p90 cost.
It is not just raw PF.
It has acceptable cost sensitivity.
It has enough trade count for first-pass research.
```

But:

```text
max_drawdown_R_p90 = 13.31R
```

This is not automatically fatal, but it requires deeper review.

---

## 3. Pattern of Results

The pass variants are:

```text
V3_STRICT_NEXT_BAR_HOLD + rolling_48h_high + TP_1R
V3_STRICT_NEXT_BAR_HOLD + rolling_48h_high + TP_1_5R
```

The watchlist variants include:

```text
V2_RETEST_CONFIRMATION + rolling_48h_high + TP_1_5R
V3_STRICT_NEXT_BAR_HOLD + previous_day_high + TP_1R
V3_STRICT_NEXT_BAR_HOLD + previous_day_high + TP_1_5R
```

Killed variants are mostly:

```text
V1_CLOSE_ACCEPTANCE
V2 previous_day_high
V2 rolling_48h_high TP_1R near breakeven but killed
```

Interpretation:

```text
The edge is not a generic high-sweep effect.
The edge is concentrated in the strict confirmation variant V3.
The rolling_48h_high level is stronger than previous_day_high.
```

This is valuable because it is structurally interpretable:

```text
Immediate close acceptance is too early/noisy.
Retest confirmation is weaker/mixed.
Strict next-bar hold filters traps better.
Rolling 48h high seems to capture active liquidity better than previous-day high.
```

---

## 4. Thesis Interpretation

The result supports a narrower thesis:

```text
In permitted/non-hostile macro regimes, continuation after sweeping and holding above a rolling 48h high has better expectancy than simple close acceptance or previous-day high breakout.
```

This is better than raw pattern mining because:

```text
1. It uses macro regime filtering.
2. It uses H4/D1 trend filters.
3. It uses p90 spread cost.
4. It rejects weaker entry logic.
5. It identifies strict confirmation as the main quality filter.
```

---

## 5. Why Stage39 Still Remains NO-GO

Stage39 remains blocked because the first result has not yet passed robustness diagnostics.

Missing diagnostics:

```text
1. yearly performance of the best variant
2. monthly concentration
3. drawdown path
4. regime split details
5. MAE/MFE or adverse excursion
6. trade clustering
7. sensitivity to blocked windows and data gaps
8. robustness of rolling_48h_high edge across different market eras
9. whether 127 trades are distributed enough
10. whether max drawdown 13.31R is acceptable relative to edge
```

Also:

```text
usd_pnl_conversion_resolved = false
```

This does not block R-based research, but it blocks any paper/live interpretation.

---

## 6. Immediate Next Diagnostic Questions

Before changing any strategy logic, answer these:

```text
1. Does the best V3 rolling_48h TP_1R variant work in multiple years?
2. Is profit concentrated in one year/month?
3. Is the drawdown caused by a specific macro regime or period?
4. Does the edge remain after excluding 2026 or 2022?
5. Are wins/losses clustered around particular UTC hours?
6. Are losses concentrated near Sunday/Monday/open gaps?
7. Is TP_1R consistently better than TP_1_5R because gold follow-through is shallow?
8. Does rolling_48h_high dominate previous_day_high for a structural reason?
9. How many trades come from supportive vs neutral_non_hostile?
10. Is the edge mainly from win rate or payoff?
```

---

## 7. Required Next Artifact

Next artifact:

```text
app/stage38a_t1_deep_diagnostics.py
```

Purpose:

```text
Read the existing stage38a_t1_trade_ledger.csv and produce deeper diagnostics.
```

This is not a new strategy test.

It must not generate new variants.

It only reviews the existing 12 variants.

---

## 8. Required Diagnostic Outputs

The diagnostic script should write:

```text
data/reports/stage38a_t1_deep_diagnostics/
```

Files:

```text
stage38a_t1_deep_diagnostics_summary.json
stage38a_t1_best_variant_yearly.csv
stage38a_t1_best_variant_monthly.csv
stage38a_t1_best_variant_hourly.csv
stage38a_t1_best_variant_regime.csv
stage38a_t1_best_variant_drawdown.csv
stage38a_t1_best_variant_streaks.csv
stage38a_t1_best_variant_exit_reasons.csv
stage38a_t1_variant_comparison_narrowed.csv
stage38a_t1_deep_diagnostics.md
```

The script should focus on:

```text
V3_STRICT_NEXT_BAR_HOLD__rolling_48h_high__TP_1R__TIME_5H
```

and compare it against:

```text
V3_STRICT_NEXT_BAR_HOLD__rolling_48h_high__TP_1_5R__TIME_5H
V3_STRICT_NEXT_BAR_HOLD__previous_day_high__TP_1R__TIME_5H
```

---

## 9. Promotion Gate After Deep Diagnostics

T1 may move from `PASS_RESEARCH_INTEREST` to `ROBUST_RESEARCH_CANDIDATE` only if:

```text
1. best variant remains positive across at least 3 calendar years or major market periods,
2. no single month contributes more than 35% of net R,
3. no single year contributes more than 50% of net R,
4. drawdown is explainable and not caused by forbidden conditions,
5. supportive/neutral_non_hostile regime split remains sensible,
6. p90 cost remains positive,
7. tail p99 result is not catastrophic,
8. result is not dependent on blocked windows,
9. no data-quality issue explains the edge,
10. no additional variant mining is needed.
```

Even if this passes:

```text
Stage39 still requires a separate readiness decision.
```

---

## 10. Current Decision

```text
T1_FIRST_RESULT = POSITIVE
T1_BEST_VARIANT = V3_STRICT_NEXT_BAR_HOLD__rolling_48h_high__TP_1R__TIME_5H
T1_EDGE_STATUS = RESEARCH_INTEREST
NEXT = DEEP_DIAGNOSTICS
STAGE39 = NO_GO
EA_PAPER_LIVE_ORDER = NO_GO
```

---

## 11. Recommended Commit

After placing this file in the repo:

```bash
cd ~/Desktop/xauusd-trader
mkdir -p docs
mv ~/Downloads/STAGE38A_T1_READ_ONLY_RESULT_REVIEW.md docs/STAGE38A_T1_READ_ONLY_RESULT_REVIEW.md
git status --short
git add -A
git commit -m "Add Stage38A T1 read-only result review"
git pull --rebase origin main
git push
```

---

## 12. Practical Next Step

Create:

```text
app/stage38a_t1_deep_diagnostics.py
```

This script must only read existing report CSVs and write diagnostics. It must not create new variants.
