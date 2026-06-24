# Stage38A — T1 Normalized Regime Filter Review

**Project:** XAUUSD / Gold Trading System  
**Stage:** Stage38A  
**Document type:** Review of normalized structural-expansion diagnostic  
**Generated UTC:** 2026-06-16T14:07:04Z  
**Status:** Structural-expansion filter feasible; locked retest required  
**Execution authorization:** NO EA, NO paper-live, NO live order  
**Stage39 authorization:** NO-GO

---

چپ‌چین ادامه می‌دهم.

این سند نتیجه diagnostic فیلتر normalized structural expansion را بررسی می‌کند.

Variant اصلی بررسی‌شده:

```text
V3_STRICT_NEXT_BAR_HOLD__rolling_48h_high__TP_1R__TIME_5H
```

---

## 1. Executive Decision

خروجی diagnostic:

```text
diagnostic_decision = STRUCTURAL_EXPANSION_FILTER_FEASIBLE_NEEDS_LOCKED_RETEST

structural_expansion_selected_trades = 33
structural_expansion_selected_pf = 4.390162426111025
structural_expansion_selected_net_R = 15.547905929999999

structural_expansion_pre2025_pf = 1.6262997182818835
structural_expansion_pre2025_net_R = 0.9139097199999999

STAGE39 = NO_GO
EA_PAPER_LIVE_ORDER = NO_GO
```

Decision:

```text
T1_GENERAL_EDGE = FAIL
T1_2025_ONLY_ARTIFACT = NOT_CONFIRMED
STRUCTURAL_EXPANSION_FILTER = FEASIBLE_BUT_NOT_VALIDATED
NEXT = LOCKED_STRUCTURAL_FILTER_RETEST
STAGE39 = NO_GO
```

---

## 2. What Improved

قبل از فیلتر structural expansion:

```text
pre2025:
    pf = 0.63550192
    net_R = -10.94989175

2025:
    pf = 3.16391321
    net_R = 23.90776933
```

بعد از فیلتر قفل‌شده زیر:

```text
D1 trend pct >= 5%
H4 trend pct >= 2%
ATR pct price >= 0.30%
```

برای best variant:

```text
selected_trades = 33
selected_pf = 4.3902
selected_net_R = 15.5479

selected_pre2025:
    trades = 6
    pf = 1.6263
    net_R = 0.9139

selected_2025:
    trades = 27
    pf = 5.6799
    net_R = 14.6340
```

Interpretation:

```text
The structural expansion filter reduced the pre2025 damage.
It did not merely select 2025 trades.
It converted the selected pre2025 sample from negative to mildly positive.
```

This is important.

---

## 3. What Still Blocks Promotion

Promotion is still blocked because:

```text
1. selected_trades = 33, below the original 50-trade research threshold.
2. selected_pre2025_trades = 6, too small to prove broad robustness.
3. 2025 still dominates net R.
4. the filter has been tested only on the best variant, not all 12 variants.
5. no locked retest has yet been performed.
6. no walk-forward or unseen-period validation exists.
```

Therefore:

```text
No Stage39.
No EA.
No paper-live.
No order.
```

---

## 4. Why This Result Is Worth Continuing

This result is better than the previous era-ablation result.

Previously:

```text
The edge looked 2025-dependent.
```

Now:

```text
A pre-trade structural/volatility filter partially explains the 2025 dependency.
```

This makes a narrower thesis plausible:

```text
T1_STRUCTURAL_EXPANSION_CONTINUATION:
Strict hold above rolling 48h high can work when gold is already in a strong D1/H4 structural expansion and H1 volatility is sufficiently expanded.
```

But this thesis is not validated yet.

---

## 5. Locked Filter Definition

The next retest must use exactly this filter:

```text
d1_trend_pct = (d1_close - d1_ma50) / d1_ma50
h4_trend_pct = (h4_close - h4_ma50) / h4_ma50
atr_pct_price = atr_h1_14 / entry_price

LOCKED_FILTER:
    d1_trend_pct >= 0.05
    h4_trend_pct >= 0.02
    atr_pct_price >= 0.003
```

No threshold search is allowed.

No new variant generation is allowed.

No optimization is allowed.

---

## 6. Required Next Diagnostic

Next script:

```text
app/stage38a_t1_locked_structural_filter_retest.py
```

Purpose:

```text
Apply the locked structural-expansion filter to the existing 12-variant trade ledger.
```

Input:

```text
data/reports/stage38a_t1_read_only_test/stage38a_t1_trade_ledger.csv
```

Output:

```text
data/reports/stage38a_t1_locked_structural_filter_retest/
```

Required files:

```text
stage38a_t1_locked_structural_filter_summary.json
stage38a_t1_locked_structural_filter_variant_metrics.csv
stage38a_t1_locked_structural_filter_variant_years.csv
stage38a_t1_locked_structural_filter_selected_trades.csv
stage38a_t1_locked_structural_filter_rejected_metrics.csv
stage38a_t1_locked_structural_filter_retest.md
```

---

## 7. What the Locked Retest Must Answer

```text
1. Does the filter improve more than one variant?
2. Does the filter specifically improve V3 variants?
3. Does rolling_48h_high remain better than previous_day_high?
4. Does TP_1R remain better than TP_1_5R?
5. How many trades survive per variant?
6. Does pre2025 remain non-disastrous after filter?
7. Does the rejected group become weak or negative?
8. Is the selected group still too sparse?
9. Does the result still depend mostly on 2025?
10. Should T1 continue or be archived?
```

---

## 8. Gate After Locked Retest

Possible outcomes:

### Outcome A — Continue T1 Narrowed

```text
LOCKED_FILTER_RETEST_PASS_RESEARCH:
    at least one locked-filter variant has:
        selected_trade_count >= 50
        p90_pf >= 1.20
        avg_R_p90 > 0
        rejected group worse than selected group
        pre2025 not catastrophic
```

Then:

```text
T1_STATUS = STRUCTURAL_EXPANSION_RESEARCH_CANDIDATE
```

Still:

```text
STAGE39 = NO_GO
```

### Outcome B — Watchlist Only

```text
selected_trade_count between 25 and 49
p90_pf strong
pre2025 not catastrophic
```

Then:

```text
T1_STATUS = LOW_SAMPLE_WATCHLIST
```

### Outcome C — Archive

```text
filter helps only the already-known best variant
sample remains too small
pre2025 still negative
2025 dominates completely
```

Then:

```text
T1_STATUS = ARCHIVE_AS_2025_ARTIFACT
NEXT = COT/T3
```

---

## 9. Current Decision

```text
NORMALIZED_FILTER_DIAGNOSTIC = PROMISING
LOCKED_RETEST_REQUIRED = TRUE
T1_STATUS = FEASIBLE_BUT_UNVALIDATED
STAGE39 = NO_GO
EA_PAPER_LIVE_ORDER = NO_GO
```

---

## 10. Recommended Commit

```bash
cd ~/Desktop/xauusd-trader
mkdir -p docs
mv ~/Downloads/STAGE38A_T1_NORMALIZED_FILTER_REVIEW.md docs/STAGE38A_T1_NORMALIZED_FILTER_REVIEW.md
git status --short
git add -A
git commit -m "Add Stage38A T1 normalized filter review"
git pull --rebase origin main
git push
```

---

## 11. Practical Next Step

Run:

```text
app/stage38a_t1_locked_structural_filter_retest.py
```

This remains read-only diagnostics.
