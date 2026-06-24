# Stage38A — T1 Deep Diagnostics Review and Era Decision

**Project:** XAUUSD / Gold Trading System  
**Stage:** Stage38A  
**Document type:** Review of deep diagnostics and era-concentration decision  
**Generated UTC:** 2026-06-16T13:22:42Z  
**Status:** T1 first candidate downgraded to era-specific investigation  
**Execution authorization:** NO EA, NO paper-live, NO live order  
**Stage39 authorization:** NO-GO

---

چپ‌چین ادامه می‌دهم.

این سند نتیجه deep diagnostics روی بهترین variant تست T1 را بررسی می‌کند:

```text
V3_STRICT_NEXT_BAR_HOLD__rolling_48h_high__TP_1R__TIME_5H
```

نتیجه کلی:

```text
T1_EDGE_FOUND = YES
ROBUST_EDGE_CONFIRMED = NO
STAGE39 = NO_GO
NEXT = ERA_ABLATION_AND_2025_REGIME_DIAGNOSTIC
```

---

## 1. Executive Decision

خروجی deep diagnostics نشان می‌دهد که candidate هنوز robust نیست.

اعداد اصلی:

```text
best_trade_count = 127
best_net_R_p90 = 12.95787758
best_pf_p90 = 1.315358090323746
best_avg_R_p90 = 0.10203053212598426
best_win_rate_p90 = 0.6220472440944882
best_max_dd_R = 13.314009739999994
best_max_win_streak = 16
best_max_loss_streak = 6
year_count = 4
positive_year_count = 2
max_month_positive_contribution_share = 0.3313865595152303
max_year_net_R_share = 1.8450374440101789
robustness_decision = ROBUSTNESS_FAIL_OR_NEEDS_REVIEW
```

Decision:

```text
T1_BEST_VARIANT = RESEARCH_INTEREST_BUT_NOT_ROBUST
PROMOTION = BLOCKED
STAGE39 = NO_GO
```

---

## 2. Why the Result Failed Robustness

Yearly results:

```text
2022: trades=10,  pf=0.4572, avg_R=-0.3336, net_R=-3.3355
2023: trades=21,  pf=0.3304, avg_R=-0.4062, net_R=-8.5308
2024: trades=33,  pf=1.0821, avg_R=0.0278, net_R=0.9164
2025: trades=63,  pf=3.1639, avg_R=0.3795, net_R=23.9078
```

Interpretation:

```text
The full-period positive result is dominated by 2025.
2022 and 2023 are clearly negative.
2024 is only marginally positive.
2025 is very strong.
```

This means the thesis is not yet a stable 2022–2026 thesis. It may be:

```text
1. a 2025-specific gold regime effect,
2. a volatility/trend-structure regime effect,
3. a price-level / macro-tailwind effect,
4. a data or filtering artifact,
5. or a valid but narrower regime setup.
```

---

## 3. What Is Still Positive

This result should not be discarded.

Positive evidence:

```text
1. The best variant survives p90 cost.
2. It has 127 trades, not just a tiny sample.
3. The best monthly contribution is 33.1%, below the 35% monthly concentration threshold.
4. The best logic is interpretable: strict next-bar hold above rolling 48h high.
5. Previous-day-high variants are weaker, so rolling 48h liquidity seems meaningful.
6. TP_1R beats TP_1_5R, suggesting shallow continuation rather than large trend extension.
```

Therefore:

```text
T1 is not killed.
T1 is narrowed.
```

---

## 4. What Is Negative

Negative evidence:

```text
1. Only 2 of 4 years are positive.
2. 2022 and 2023 are strongly negative.
3. 2025 contributes more than total net R.
4. max_year_net_R_share = 1.845, far above the 0.50 robustness threshold.
5. best_max_dd_R = 13.31R is almost equal to full net R.
6. The edge may be a specific macro/structural era, not a general T1 rule.
```

Therefore:

```text
No Stage39.
No paper/live.
No candidate promotion.
```

---

## 5. Updated Thesis Interpretation

The earlier broad thesis:

```text
Regime-filtered high sweep continuation can work in non-hostile gold regimes.
```

must be narrowed to:

```text
Strict hold above rolling 48h high may work only in specific gold continuation eras, especially conditions resembling 2025.
```

That is not bad. It is actually more realistic for gold.

Gold is regime-sensitive. A strategy that fails in 2022–2023 but works in 2025 might still be useful if we can define the regime that separates these periods.

But until that separating regime is defined ex ante:

```text
candidate remains research-only.
```

---

## 6. Required Next Diagnostic

Next diagnostic:

```text
ERA_ABLATION_AND_2025_REGIME_DIAGNOSTIC
```

Purpose:

```text
Determine whether the 2025 edge is explainable by pre-defined market conditions or is just period overfit.
```

Questions:

```text
1. What happens if 2025 is excluded?
2. What happens if 2022–2023 are excluded?
3. What happens in 2024–2025 only?
4. Is 2025 edge associated with supportive macro regime?
5. Is 2025 edge associated with higher D1/H4 trend strength?
6. Is 2025 edge associated with lower/higher ATR?
7. Is 2025 edge associated with a specific UTC hour?
8. Are losses in 2022–2023 clustered by macro_regime?
9. Does TP_1R superiority persist in 2025 only?
10. Can we define an ex-ante 2025-like regime without using future information?
```

---

## 7. Next Script

Create:

```text
app/stage38a_t1_era_ablation.py
```

The script must only read existing report outputs:

```text
data/reports/stage38a_t1_read_only_test/stage38a_t1_trade_ledger.csv
```

It must not create new variants.

It should produce:

```text
data/reports/stage38a_t1_era_ablation/
```

Files:

```text
stage38a_t1_era_ablation_summary.json
stage38a_t1_era_ablation_windows.csv
stage38a_t1_era_ablation_year_macro.csv
stage38a_t1_era_ablation_year_hour.csv
stage38a_t1_era_ablation_variant_windows.csv
stage38a_t1_era_ablation.md
```

---

## 8. Updated Gate

Current gate after deep diagnostics:

```text
T1_FIRST_PASS = POSITIVE
T1_DEEP_DIAGNOSTICS = FAILED_ROBUSTNESS
T1_STATUS = ERA_SPECIFIC_RESEARCH_CANDIDATE
STAGE39 = NO_GO
NEXT = ERA_ABLATION
```

Promotion conditions after era ablation:

```text
T1 may continue only if:
1. the 2025 edge can be explained by pre-existing regime variables,
2. the filter can be defined without hindsight,
3. excluding 2025 does not reveal total thesis failure without explanation,
4. negative years are associated with forbidden/identifiable regimes,
5. no additional uncontrolled variant mining is introduced.
```

---

## 9. Decision

```text
DO_NOT_KILL_T1 = TRUE
DO_NOT_PROMOTE_T1 = TRUE
NARROW_T1_TO_ERA_DIAGNOSTIC = TRUE
STAGE39 = NO_GO
EA_PAPER_LIVE_ORDER = NO_GO
```

---

## 10. Recommended Commit

```bash
cd ~/Desktop/xauusd-trader
mkdir -p docs
mv ~/Downloads/STAGE38A_T1_DEEP_DIAGNOSTICS_REVIEW.md docs/STAGE38A_T1_DEEP_DIAGNOSTICS_REVIEW.md
git status --short
git add -A
git commit -m "Add Stage38A T1 deep diagnostics review"
git pull --rebase origin main
git push
```

---

## 11. Practical Next Step

Run the era-ablation diagnostic script:

```text
app/stage38a_t1_era_ablation.py
```

This is still read-only diagnostics.
