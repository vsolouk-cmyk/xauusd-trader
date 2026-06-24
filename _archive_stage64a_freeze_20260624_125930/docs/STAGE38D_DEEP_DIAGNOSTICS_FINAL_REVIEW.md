# STAGE38D Deep Diagnostics Final Review

**Project:** XAUUSD / Gold Research  
**Stage:** Stage38D — M5/M15 Session Baseline Lab  
**Status:** Final review after deep diagnostics  
**Decision:** LOW_CONFIDENCE_ARCHIVE_OR_PIVOT_REVIEW  
**Trading status:** Stage39 / EA / paper-live / live = NO-GO

---

## 1. Executive Decision

Stage38D does not provide a promotable intraday baseline.

The only Stage38D WATCH candidate was:

```text
candidate_id = D1_M5_ASIA_RANGE_BREAKOUT_LONG_FIRST_48
timeframe = M5
baseline_family = ASIA_RANGE
baseline_name = ASIA_RANGE_BREAKOUT_LONG_FIRST
horizon_bars = 48
horizon_minutes = 240
sample_count = 507
```

Deep diagnostics downgraded it to:

```text
LOW_CONFIDENCE_RESEARCH_ONLY
```

Therefore:

```text
PROMOTE_TO_STRATEGY = NO
PROMOTE_TO_STAGE39 = NO
PROMOTE_TO_EA = NO
PROMOTE_TO_PAPER_LIVE = NO
LIVE_ORDER = NO
```

---

## 2. Deep Diagnostic Result

Final candidate summary:

```text
mean_net_bps = +2.41
median_net_bps = +0.59
win_rate_net = 0.509
t_stat_mean_net_bps = 1.66
pre2025_mean_net_bps = +0.60
exclude_2025_mean_net_bps = +1.06
y2025_mean_net_bps = +6.60
y2026_mean_net_bps = +4.73
first_half_mean_net_bps = -0.36
second_half_mean_net_bps = +5.17
cost_x_1_5_mean_net_bps = +2.41
cost_x_2_mean_net_bps = +2.41
worst_loo_mean_net_bps = +1.06
worst_loo_excluded_year = 2025
max_positive_year_share = 0.487
max_positive_month_share = 0.082
note = WEAK_FIRST_HALF_LT_0_5BPS
```

---

## 3. Interpretation

The candidate is not statistically or economically strong enough.

Key problems:

1. **Mean is too small.**  
   `+2.41 bps` is not enough margin for a retail CFD execution path once slippage, spread fluctuation, timing uncertainty, rollover conditions, and broker-specific fill behavior are considered.

2. **Pre-2025 performance is weak.**  
   `pre2025_mean_net_bps = +0.60`, which is not a robust edge.

3. **First chronological half is negative.**  
   `first_half_mean_net_bps = -0.36`. This blocks promotion.

4. **The apparent improvement is concentrated in the later regime.**  
   2025 and 2026 are materially stronger than earlier data. This resembles the repeated pattern found in earlier Stage38A/38C diagnostics.

5. **No Stage38D candidate reached PASS.**  
   Stage38D produced only one WATCH and 41 KILL rows before deep diagnostics.

---

## 4. Final Stage38D Decision

```text
STAGE38D_DATA_PREP = SUCCESS
M5_M15_DERIVATION = SUCCESS
M5_M15_AVAILABILITY_REAUDIT = SUCCESS
STAGE38D_BASELINE_LAB = WEAK
STAGE38D_DEEP_DIAGNOSTIC = LOW_CONFIDENCE_RESEARCH_ONLY
STAGE38D_ACTIVE_DEVELOPMENT = STOP
```

Stage38D should be archived as a completed negative/weak research branch.

The derived M5/M15 data remains useful for future diagnostics, but the tested session baselines are not promotable.

---

## 5. What Must Not Happen Next

Do not continue by adding arbitrary filters to this candidate.

Blocked next steps:

```text
free filter mining
parameter sweep expansion
Stage39
EA
paper-live
live orders
Telegram trade alerts
model training on this baseline
```

Reason: the base edge is too small, and continued filtering would likely become overfitting.

---

## 6. Recommended Pivot

The next useful path is not another session breakout variant.

Recommended Stage38E:

```text
Stage38E — Free Macro/Risk Data Foundation
```

Rationale:

- Gold is sensitive to rates, real yields, dollar pressure, risk sentiment, and macro regime.
- T1/T3/Stage38C/Stage38D all showed that simple technical/session baselines are not enough.
- The current database has XAUUSD bars and COT, but it still lacks a reliable cross-market macro/risk layer.
- Before further baseline work, the project needs a free, reproducible macro/risk feature foundation.

Stage38E should remain data-first and read-only.

---

## 7. Immediate Next Artifact

```text
docs/STAGE38E_FREE_MACRO_RISK_DATA_FOUNDATION_PLAN.md
```

Then:

```text
app/stage38e_macro_risk_data_availability_audit.py
```

No trading system work should start before this data foundation is audited.
