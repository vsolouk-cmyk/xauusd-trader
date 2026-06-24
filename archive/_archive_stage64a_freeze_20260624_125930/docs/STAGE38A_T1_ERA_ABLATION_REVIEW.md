# Stage38A — T1 Era Ablation Review

**Project:** XAUUSD / Gold Trading System  
**Stage:** Stage38A  
**Document type:** Review of era-ablation result and 2025-dependent edge decision  
**Generated UTC:** 2026-06-16T13:58:28Z  
**Status:** T1 narrowed to 2025-like regime investigation  
**Execution authorization:** NO EA, NO paper-live, NO live order  
**Stage39 authorization:** NO-GO

---

چپ‌چین ادامه می‌دهم.

این سند نتیجه era ablation برای بهترین variant فعلی T1 را بررسی می‌کند:

```text
V3_STRICT_NEXT_BAR_HOLD__rolling_48h_high__TP_1R__TIME_5H
```

---

## 1. Executive Decision

Era ablation نتیجه را قطعی‌تر کرد:

```text
T1_EDGE_EXISTS = YES
T1_GENERAL_EDGE_2022_2026 = NO
T1_EDGE_DEPENDS_ON_2025 = YES
T1_STATUS = 2025_LIKE_REGIME_RESEARCH_ONLY
STAGE39 = NO_GO
EA_PAPER_LIVE_ORDER = NO_GO
```

خروجی کلیدی:

```text
FULL:
    pf = 1.31535809
    net_R = 12.95787758

EXCLUDE_2025:
    pf = 0.63550192
    net_R = -10.94989175

ERA_2025_ONLY:
    pf = 3.16391321
    net_R = 23.90776933

ERA_2024_2025:
    pf = 2.11796207
    net_R = 24.82417353

ERA_DECISION:
    2025_DEPENDENT_EDGE
```

نتیجه:

```text
The edge is real inside a specific era.
The edge is not robust as a general multi-year rule.
```

---

## 2. What This Means

این نتیجه بد نیست، اما معنایش این نیست که strategy آماده است.

معنای درست:

```text
The old broad T1 thesis is too wide.
The strict hold above rolling 48h high seems to work only when gold is in a 2025-like continuation environment.
```

بنابراین thesis باید از حالت زیر:

```text
Regime-filtered high sweep continuation works generally.
```

به حالت زیر محدود شود:

```text
Strict hold above rolling 48h high may work only during identifiable 2025-like gold continuation regimes.
```

---

## 3. Why Stage39 Is Still Blocked

Stage39 همچنان blocked است، چون اگر ۲۰۲۵ حذف شود:

```text
pf = 0.6355
net_R = -10.95R
```

این یعنی edge بدون ۲۰۲۵ نه فقط ضعیف، بلکه منفی است.

همچنین ۲۰۲۲–۲۰۲۳ بسیار بد بوده‌اند:

```text
ERA_2022_2023:
    pf = 0.37164049
    avg_R = -0.38278374
    net_R = -11.86629595
```

در مقابل:

```text
ERA_2025_ONLY:
    pf = 3.16391321
    avg_R = 0.3794884
    net_R = 23.90776933
```

پس اگر نتوانیم ۲۰۲۵-like regime را قبل از معامله تعریف کنیم، این نتیجه فقط period overfit است.

---

## 4. Important Positive Evidence

با وجود failure در robustness، چند نکته مثبت داریم:

```text
1. 2025-only edge بسیار قوی است.
2. 2024-2025 هم مثبت و قوی است.
3. 2024-only تقریباً breakeven/ضعیف مثبت است، نه فاجعه.
4. 2022-2023 منفی شدیدند و باید به‌عنوان forbidden-era بررسی شوند.
5. rolling_48h_high همچنان نسبت به previous_day_high در sample کمتر و تمیزتر است.
6. TP_1R در best variant بهتر از TP_1_5R است، یعنی continuation کوتاه و سریع‌تر جواب داده است.
```

این یعنی احتمالاً موضوع اصلی:

```text
not entry logic alone
but market-era filter
```

---

## 5. Year × Macro Bucket Interpretation

خروجی year × macro نشان می‌دهد:

```text
2022 supportive:
    trades=10, pf=0.4572, net_R=-3.3355

2023 supportive:
    trades=18, pf=0.4476, net_R=-5.1951

2024 neutral_non_hostile:
    trades=33, pf=1.0821, net_R=0.9164

2025 neutral_non_hostile:
    trades=54, pf=2.5199, net_R=16.7919

2025 supportive:
    trades=9, pf=inf, net_R=7.1158
```

Interpretation:

```text
The current supportive/neutral macro labels alone are not sufficient.
The same broad supportive bucket failed in 2022/2023 but succeeded in 2025.
```

Therefore:

```text
We need a better 2025-like regime descriptor.
```

Possible missing filters:

```text
1. gold D1/H4 trend strength
2. real yield slope/rank, not just supportive label
3. dollar trend character
4. ATR/volatility regime
5. price level / momentum maturity
6. market era after 2024 breakout
7. central bank / safe-haven / structural demand narrative not captured by current macro label
```

---

## 6. Decision About T1

Do not kill T1.

Do not promote T1.

Narrow T1:

```text
T1_NARROWED_THESIS:
Strict next-bar hold above rolling 48h high is a possible continuation setup only inside 2025-like gold continuation regimes.
```

Current status:

```text
T1_STATUS = ERA_SPECIFIC_RESEARCH_ONLY
```

---

## 7. Required Next Diagnostic

Next diagnostic:

```text
STAGE38A_T1_2025_REGIME_DIAGNOSTIC
```

Purpose:

```text
Find observable feature differences between losing eras and winning 2025-like eras.
```

It must not create new strategy variants.

It should diagnose:

```text
1. macro_score_long_gold distribution by year
2. d_real_yield_20d distribution by year
3. d_usd_20d_pct distribution by year
4. ATR_H1_14 distribution by year
5. D1 trend distance from MA50
6. H4 trend distance from MA50
7. UTC hour concentration
8. exit reason distribution
9. win/loss features for best variant
10. 2025 vs non-2025 feature separation
```

---

## 8. Next Script

Create:

```text
app/stage38a_t1_2025_regime_diagnostic.py
```

Input:

```text
data/reports/stage38a_t1_read_only_test/stage38a_t1_trade_ledger.csv
```

Output:

```text
data/reports/stage38a_t1_2025_regime_diagnostic/
```

Files:

```text
stage38a_t1_2025_regime_diagnostic_summary.json
stage38a_t1_2025_feature_summary.csv
stage38a_t1_2025_year_feature_summary.csv
stage38a_t1_2025_win_loss_features.csv
stage38a_t1_2025_hour_exit_summary.csv
stage38a_t1_2025_candidate_filter_notes.csv
stage38a_t1_2025_regime_diagnostic.md
```

---

## 9. Promotion Gate After 2025 Regime Diagnostic

T1 can continue only if the diagnostic finds an ex-ante filter such as:

```text
D1 trend strength above threshold
H4 trend strength above threshold
real-yield slope supportive
USD slope non-hostile
ATR regime not extreme
or another pre-trade observable state
```

But the filter must be:

```text
defined before retest
not optimized over many thresholds
not built from 2025 labels directly
not based on future performance
```

If no such filter exists:

```text
T1 should be archived as 2025-specific historical artifact.
```

---

## 10. Current Gate

```text
ERA_ABLATION_REVIEW = CREATED
T1_STATUS = 2025_DEPENDENT_EDGE
NEXT = 2025_REGIME_DIAGNOSTIC
STAGE39 = NO_GO
EA_PAPER_LIVE_ORDER = NO_GO
```

---

## 11. Recommended Commit

```bash
cd ~/Desktop/xauusd-trader
mkdir -p docs
mv ~/Downloads/STAGE38A_T1_ERA_ABLATION_REVIEW.md docs/STAGE38A_T1_ERA_ABLATION_REVIEW.md
git status --short
git add -A
git commit -m "Add Stage38A T1 era ablation review"
git pull --rebase origin main
git push
```

---

## 12. Practical Next Step

Run:

```text
app/stage38a_t1_2025_regime_diagnostic.py
```

This remains read-only diagnostics.
