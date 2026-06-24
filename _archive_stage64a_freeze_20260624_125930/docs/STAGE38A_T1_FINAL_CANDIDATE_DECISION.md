# Stage38A — T1 Final Candidate Decision

**Project:** XAUUSD / Gold Trading System  
**Stage:** Stage38A  
**Document type:** Final decision after locked candidate diagnostics  
**Generated UTC:** 2026-06-16T14:17:57Z  
**Status:** T1 candidate positive but not promotable; Stage39 blocked  
**Execution authorization:** NO EA, NO paper-live, NO live order  
**Stage39 authorization:** NO-GO

---

چپ‌چین ادامه می‌دهم.

این سند تصمیم نهایی Stage38A برای thesis اول را ثبت می‌کند:

```text
T1_STRUCTURAL_EXPANSION_CONTINUATION
```

Lead locked candidate:

```text
V1_CLOSE_ACCEPTANCE__previous_day_high__TP_1_5R__TIME_5H
```

Locked structural-expansion filter:

```text
d1_trend_pct >= 0.05
h4_trend_pct >= 0.02
atr_pct_price >= 0.003
```

---

## 1. Executive Decision

Final diagnostic output:

```text
lead_variant = V1_CLOSE_ACCEPTANCE__previous_day_high__TP_1_5R__TIME_5H
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
stage39_status = NO_GO
```

Decision:

```text
T1_STATUS = LOW_CONFIDENCE_2025_DOMINATED_RESEARCH_CANDIDATE
STAGE39 = NO_GO
EA = NO_GO
PAPER_LIVE = NO_GO
LIVE_ORDER = NO_GO
ACTIVE_T1_CODING = STOP
```

---

## 2. Why T1 Is Not Killed

T1 is not killed because:

```text
1. The locked filter is pre-defined and interpretable.
2. Lead variant has 94 trades.
3. Lead variant has PF 1.70 after p90 cost.
4. Lead variant has net_R +24.41R.
5. pre2025 selected group is no longer catastrophic:
   pre2025_pf = 1.27
   pre2025_net_R = +2.41R
6. The rejected groups were weaker in the locked retest.
```

So this is not random noise at the first-pass level.

---

## 3. Why T1 Is Not Promoted

T1 is not promotable because:

```text
1. 2025 contributes 87.42% of positive yearly contribution.
2. 2025-04 alone contributes 52.02% of positive monthly contribution.
3. pre2025 has only 25 selected trades.
4. pre2025 net_R is positive but small.
5. month concentration violates robustness threshold.
6. year concentration violates robustness threshold.
7. no prospective observation exists.
8. no real execution/paper/live validation exists.
9. USD P/L conversion is still incomplete.
```

Main blocker:

```text
The edge remains 2025-dominated and month-concentrated.
```

---

## 4. Final Interpretation

The broad thesis failed:

```text
General T1 continuation across 2022–2026 = NOT SUPPORTED
```

The narrowed thesis remains plausible:

```text
In a strong gold structural-expansion state, close acceptance above previous-day high can have positive short-horizon continuation expectancy after p90 spread cost.
```

But this narrowed thesis is:

```text
low-confidence
2025-heavy
not production-ready
not Stage39-ready
```

---

## 5. Action Decision

Do not continue active T1 variant work now.

Allowed only:

```text
1. Archive T1 as low-confidence structural-expansion research candidate.
2. Optionally build a very light read-only forward observation monitor later.
3. Move primary research effort to free COT/T3 data layer.
```

Forbidden:

```text
1. Stage39 promotion
2. EA work
3. paper-live simulation
4. live order logic
5. more threshold optimization
6. more variant mining on T1
```

---

## 6. Recommended Next Phase

Primary next phase:

```text
Stage38B / T3 data foundation:
CFTC COT gold positioning layer
```

Reason:

```text
T1 reached a useful but not promotable conclusion.
T3 is blocked by missing COT data.
COT is free and thesis-relevant.
```

Optional secondary phase:

```text
T1 read-only forward monitor
```

But only after transfer to a new session and only as observation:

```text
No orders
No EA
No paper-live
No optimization
```

---

## 7. Gate Status

```text
T1_FINAL_DECISION = LOW_CONFIDENCE_2025_DOMINATED_RESEARCH_CANDIDATE
T1_ACTIVE_DEVELOPMENT = PAUSED
T1_FORWARD_OBSERVATION = OPTIONAL_LATER
T3_COT_DATA_LAYER = RECOMMENDED_NEXT
STAGE39 = NO_GO
EA_PAPER_LIVE_ORDER = NO_GO
```

---

## 8. Recommended Commit

```bash
cd ~/Desktop/xauusd-trader
mkdir -p docs
mv ~/Downloads/STAGE38A_T1_FINAL_CANDIDATE_DECISION.md docs/STAGE38A_T1_FINAL_CANDIDATE_DECISION.md
git status --short
git add -A
git commit -m "Add Stage38A T1 final candidate decision"
git pull --rebase origin main
git push
```
