# Stage38A — T1 2025 Regime Diagnostic Review

**Project:** XAUUSD / Gold Trading System  
**Stage:** Stage38A  
**Document type:** Review of 2025-regime diagnostic and normalized-filter decision  
**Generated UTC:** 2026-06-16T14:02:29Z  
**Status:** 2025-like feature separation found; normalized feasibility test required  
**Execution authorization:** NO EA, NO paper-live, NO live order  
**Stage39 authorization:** NO-GO

---

چپ‌چین ادامه می‌دهم.

این سند نتیجه diagnostic مربوط به تفاوت ۲۰۲۵ با دوره‌های قبل را بررسی می‌کند.

Variant بررسی‌شده:

```text
V3_STRICT_NEXT_BAR_HOLD__rolling_48h_high__TP_1R__TIME_5H
```

---

## 1. Executive Decision

خروجی diagnostic نشان می‌دهد:

```text
pre2025_net_R = -10.94989175
y2025_net_R = 23.90776933
diagnostic_decision = 2025_FEATURE_SEPARATION_REQUIRED
STAGE39 = NO_GO
```

پس هنوز تصمیم تغییر نکرده است:

```text
T1_GENERAL_EDGE = FAIL
T1_2025_EDGE = STRONG
T1_STATUS = ERA_SPECIFIC_RESEARCH_ONLY
STAGE39 = NO_GO
```

اما حالا می‌دانیم جداسازی احتمالی ۲۰۲۵ از کدام جنس است.

---

## 2. Feature Separation Findings

خلاصه feature separation:

```text
macro_score_long_gold:
    pre2025_mean = 1.3711
    y2025_mean = 0.4087
    diff = -0.9624
    note = possible_2025_separation_feature

d_real_yield_20d:
    no_clear_separation

d_usd_20d_pct:
    no_clear_separation

atr_h1_14:
    pre2025_mean = 5.9353
    y2025_mean = 10.4952
    diff = +4.5599
    note = possible_2025_separation_feature

d1_trend_distance:
    pre2025_mean = 82.1568
    y2025_mean = 240.8489
    diff = +158.6921
    note = possible_2025_separation_feature

h4_trend_distance:
    pre2025_mean = 40.8706
    y2025_mean = 99.3638
    diff = +58.4932
    note = possible_2025_separation_feature
```

اما موارد normalized-by-ATR واضح نیستند:

```text
d1_trend_distance_atr:
    no_clear_separation

h4_trend_distance_atr:
    no_clear_separation
```

---

## 3. Interpretation

این خروجی مهم است.

۲۰۲۵ با چند ویژگی جدا می‌شود:

```text
1. ATR_H1_14 بالاتر
2. D1 distance from MA50 بالاتر
3. H4 distance from MA50 بالاتر
```

اما این جداسازی عمدتاً با مقادیر absolute دیده می‌شود، نه با normalization بر اساس ATR.

بنابراین دو احتمال داریم:

### احتمال خوب

```text
۲۰۲۵ واقعاً یک structural trend expansion regime بوده است.
```

در این صورت T1 ممکن است فقط در شرایط زیر کار کند:

```text
gold above D1/H4 trend strongly
volatility expanded
breakout continuation environment active
```

### احتمال بد

```text
این فقط اثر price-level / market-era / overfit 2025 است.
```

اگر جداسازی فقط با absolute distance دیده شود و با normalized/percentage distance تأیید نشود، استفاده از آن به‌عنوان filter خطرناک است.

---

## 4. Why Macro Score Alone Is Not Enough

جالب‌ترین یافته این است:

```text
macro_score_long_gold در pre2025 بالاتر از 2025 بوده، اما عملکرد pre2025 منفی است.
```

یعنی macro score فعلی به‌تنهایی تفکیک‌کننده خوبی نیست.

نتیجه:

```text
T1 should not be promoted based on current macro_score_long_gold.
```

احتمالاً T1 بیشتر به این نیاز دارد:

```text
macro not hostile
AND structural trend expansion
AND sufficient volatility
```

نه صرفاً:

```text
macro supportive
```

---

## 5. Required Next Diagnostic

قدم بعدی باید normalized feasibility باشد.

هدف:

```text
بررسی اینکه آیا ۲۰۲۵ را می‌توان با ویژگی‌های قابل مشاهده قبل از معامله و normalized تعریف کرد یا نه.
```

ویژگی‌های لازم:

```text
d1_trend_pct = (d1_close - d1_ma50) / d1_ma50
h4_trend_pct = (h4_close - h4_ma50) / h4_ma50
atr_pct_price = atr_h1_14 / entry_price
macro_score_long_gold
d_real_yield_20d
d_usd_20d_pct
```

و چند فیلتر diagnostic با آستانه‌های گرد و غیر optimized:

```text
D1 trend distance >= 5%
H4 trend distance >= 2%
ATR_H1 >= 0.30% of price
combined structural expansion = all three
```

این فیلترها هنوز strategy filters نیستند. فقط برای تشخیص‌اند.

---

## 6. Next Script

Create:

```text
app/stage38a_t1_normalized_regime_filter_diagnostic.py
```

Input:

```text
data/reports/stage38a_t1_read_only_test/stage38a_t1_trade_ledger.csv
```

Output:

```text
data/reports/stage38a_t1_normalized_regime_filter_diagnostic/
```

Files:

```text
stage38a_t1_normalized_regime_filter_summary.json
stage38a_t1_normalized_feature_summary.csv
stage38a_t1_normalized_filter_diagnostics.csv
stage38a_t1_normalized_filter_by_year.csv
stage38a_t1_normalized_filter_diagnostic.md
```

---

## 7. Decision After Next Diagnostic

If normalized structural filter works:

```text
T1 may become:
T1_STRUCTURAL_EXPANSION_CONTINUATION_RESEARCH_CANDIDATE
```

If it fails:

```text
T1 should be archived as 2025 historical artifact.
```

No middle ground:

```text
Either define 2025-like regime ex ante,
or stop spending time on T1 and move to COT/T3.
```

---

## 8. Current Gate

```text
2025_REGIME_DIAGNOSTIC_REVIEW = CREATED
T1_STATUS = 2025_FEATURE_SEPARATION_REQUIRED
NEXT = NORMALIZED_REGIME_FILTER_DIAGNOSTIC
STAGE39 = NO_GO
EA_PAPER_LIVE_ORDER = NO_GO
```

---

## 9. Recommended Commit

```bash
cd ~/Desktop/xauusd-trader
mkdir -p docs
mv ~/Downloads/STAGE38A_T1_2025_REGIME_DIAGNOSTIC_REVIEW.md docs/STAGE38A_T1_2025_REGIME_DIAGNOSTIC_REVIEW.md
git status --short
git add -A
git commit -m "Add Stage38A T1 2025 regime diagnostic review"
git pull --rebase origin main
git push
```

---

## 10. Practical Next Step

Run the normalized-filter diagnostic script:

```text
app/stage38a_t1_normalized_regime_filter_diagnostic.py
```

This remains read-only diagnostics.
