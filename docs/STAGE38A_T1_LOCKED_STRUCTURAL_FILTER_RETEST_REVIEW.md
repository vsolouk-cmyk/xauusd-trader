# Stage38A — T1 Locked Structural Filter Retest Review

**Project:** XAUUSD / Gold Trading System  
**Stage:** Stage38A  
**Document type:** Review of locked structural-expansion filter retest  
**Generated UTC:** 2026-06-16T14:11:17Z  
**Status:** T1 upgraded from 2025-artifact to low-confidence structural-expansion research candidate  
**Execution authorization:** NO EA, NO paper-live, NO live order  
**Stage39 authorization:** NO-GO

---

چپ‌چین ادامه می‌دهم.

این سند نتیجه retest قفل‌شده فیلتر structural expansion را بررسی می‌کند.

Locked filter:

```text
d1_trend_pct >= 0.05
h4_trend_pct >= 0.02
atr_pct_price >= 0.003
```

این آستانه‌ها بعد از diagnostic قفل شده‌اند و در این retest تغییر نکرده‌اند.

---

## 1. Executive Decision

نتیجه retest:

```text
variant_count = 12
pass_count = 2
watch_count = 6
weak_count = 2
kill_count = 2

best_locked_variant = V1_CLOSE_ACCEPTANCE__previous_day_high__TP_1_5R__TIME_5H
best_locked_decision = LOCKED_FILTER_PASS_RESEARCH
best_locked_trade_count = 94
best_locked_pf = 1.7004909028327415
best_locked_net_R = 24.41491088

STAGE39 = NO_GO
EA_PAPER_LIVE_ORDER = NO_GO
```

Decision:

```text
T1_STATUS = STRUCTURAL_EXPANSION_RESEARCH_CANDIDATE_LOW_CONFIDENCE
STAGE39 = NO_GO
NEXT = LOCKED_CANDIDATE_FINAL_DIAGNOSTICS
```

---

## 2. Why This Is Better Than Previous Results

Before locked structural filter, the best variant looked like:

```text
2025_DEPENDENT_EDGE
```

After locked structural filter:

```text
Two variants pass research.
Six variants are watchlist.
Rejected groups are mostly weaker than selected groups.
The filter improves several families, not only the original best variant.
```

Most important:

```text
The best variant changed from:
V3_STRICT_NEXT_BAR_HOLD__rolling_48h_high__TP_1R

to:
V1_CLOSE_ACCEPTANCE__previous_day_high__TP_1_5R
```

This means the real condition may not be the strict-hold entry itself. The stronger explanatory variable appears to be:

```text
market state = structural expansion
```

Inside that state, even a simpler close-acceptance entry over previous-day high works.

---

## 3. Best Locked Variant

```text
variant = V1_CLOSE_ACCEPTANCE__previous_day_high__TP_1_5R__TIME_5H
selected_trades = 94
selected_pf = 1.7004909
selected_net_R = 24.41491088
pre2025_net_R = 2.41122672
rejected_pf = 0.8679597
decision = LOCKED_FILTER_PASS_RESEARCH
```

Interpretation:

```text
The selected group is meaningfully stronger than the rejected group.
The selected sample size is above 50.
The pre2025 selected subset is no longer catastrophic.
```

This is the first result in Stage38A that can be treated as a plausible narrowed research candidate.

---

## 4. Important Remaining Weakness

Despite the improvement, the selected yearly distribution still shows 2025 dominance:

```text
2022: trades=2,  net_R=-0.75412904
2023: trades=7,  net_R=+1.09370396
2024: trades=16, net_R=+2.0716518
2025: trades=69, net_R=+22.00368416
```

So:

```text
pre2025 is no longer disastrous,
but 2025 is still the main profit engine.
```

This blocks Stage39.

---

## 5. Updated Thesis

The old broad T1 thesis:

```text
Regime-filtered high sweep continuation works in non-hostile regimes.
```

is replaced by the narrower thesis:

```text
T1_STRUCTURAL_EXPANSION_CONTINUATION:
In a gold structural-expansion state, defined by D1 trend distance, H4 trend distance, and expanded ATR relative to price, close acceptance above previous-day high may have positive short-horizon continuation expectancy after p90 spread cost.
```

Current lead setup:

```text
macro permitted by original T1 rules
D1 trend pct >= 5%
H4 trend pct >= 2%
ATR pct price >= 0.30%
level = previous_day_high
entry = close acceptance
target = 1.5R
time stop = 5 H1 bars
```

---

## 6. Why We Should Not Promote Yet

Blocked by:

```text
1. 2025 dominance remains high.
2. pre2025 positive sample is small.
3. no final monthly concentration test after locked filter.
4. no drawdown review after locked filter.
5. no forward-only observation.
6. no live/paper execution simulation.
7. USD P/L conversion is still not fully resolved.
```

Therefore:

```text
STAGE39 = NO_GO
```

---

## 7. Required Next Diagnostic

Next script:

```text
app/stage38a_t1_locked_candidate_final_diagnostics.py
```

Purpose:

```text
Run final concentration, drawdown, monthly/yearly, hour, and exit diagnostics on the locked best candidate.
```

Input:

```text
data/reports/stage38a_t1_read_only_test/stage38a_t1_trade_ledger.csv
```

Output:

```text
data/reports/stage38a_t1_locked_candidate_final_diagnostics/
```

Required files:

```text
stage38a_t1_locked_candidate_final_summary.json
stage38a_t1_locked_candidate_yearly.csv
stage38a_t1_locked_candidate_monthly.csv
stage38a_t1_locked_candidate_hourly.csv
stage38a_t1_locked_candidate_exit_reasons.csv
stage38a_t1_locked_candidate_drawdown.csv
stage38a_t1_locked_candidate_selected_trades.csv
stage38a_t1_locked_candidate_final_diagnostics.md
```

---

## 8. Gate After Final Diagnostics

Possible decisions:

### A. Candidate continues

```text
LOCKED_CANDIDATE_PROSPECTIVE_MONITOR_ALLOWED
```

Meaning:

```text
Build read-only forward monitor.
No orders.
No EA.
No paper-live.
```

### B. Candidate stays research-only

```text
LOCKED_CANDIDATE_LOW_CONFIDENCE
```

Meaning:

```text
Keep as a research candidate but do not spend more coding time until additional data/forward observations exist.
```

### C. Candidate archived

```text
LOCKED_CANDIDATE_ARCHIVE
```

Meaning:

```text
Move to COT/T3.
```

---

## 9. Current Gate

```text
LOCKED_STRUCTURAL_FILTER_RETEST = POSITIVE
T1_STATUS = STRUCTURAL_EXPANSION_RESEARCH_CANDIDATE_LOW_CONFIDENCE
NEXT = FINAL_LOCKED_CANDIDATE_DIAGNOSTICS
STAGE39 = NO_GO
EA_PAPER_LIVE_ORDER = NO_GO
```

---

## 10. Recommended Commit

```bash
cd ~/Desktop/xauusd-trader
mkdir -p docs
mv ~/Downloads/STAGE38A_T1_LOCKED_STRUCTURAL_FILTER_RETEST_REVIEW.md docs/STAGE38A_T1_LOCKED_STRUCTURAL_FILTER_RETEST_REVIEW.md
git status --short
git add -A
git commit -m "Add Stage38A T1 locked structural filter retest review"
git pull --rebase origin main
git push
```

---

## 11. Practical Next Step

Run:

```text
app/stage38a_t1_locked_candidate_final_diagnostics.py
```

This remains read-only diagnostics.
