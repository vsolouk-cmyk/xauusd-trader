# Stage38A — T1 Read-only Test Design

**Project:** XAUUSD / Gold Trading System  
**Stage:** Stage38A  
**Document type:** Read-only test design for T1 thesis  
**Generated UTC:** 2026-06-16T12:30:47Z  
**Status:** Design-only; no implementation authorization  
**Execution authorization:** NO EA, NO paper-live, NO live order  
**Stage39 authorization:** NO-GO until this design is reviewed and explicitly converted into an implementation plan  
**Cost policy:** FREE-FIRST ONLY

---

چپ‌چین ادامه می‌دهم.

این سند طراحی تست read-only برای thesis اول Stage38A است:

```text
T1_REGIME_FILTERED_STRUCTURE_CONTINUATION
```

این سند کد نیست و اجازه Stage39 نمی‌دهد. هدف این است که قبل از نوشتن هر backtest، دقیقاً مشخص شود چه داده‌ای خوانده می‌شود، چه setupهایی مجازند، چه variantهایی تست می‌شوند، چه cost model اعمال می‌شود، و چه معیاری باعث pass/kill می‌شود.

این سند بعد از این اسناد می‌آید:

```text
docs/STAGE38A_GOLD_MARKET_THESIS_ROADMAP.md
docs/STAGE38A_GOLD_MARKET_THESIS_RECONSTRUCTION.md
docs/STAGE38A_THESIS_TEMPLATES_V0.md
docs/STAGE38A_DATA_FEASIBILITY_MATRIX.md
docs/STAGE38A_LOCAL_DATA_AUDIT_RESULT_V2_COVERAGE.md
docs/STAGE38A_SPREAD_PERCENTILE_AUDIT_RESULT.md
docs/STAGE38A_EXECUTION_COST_MODEL_V0.md
docs/STAGE38A_TRADE_CONSTRUCTION_SPEC_V0.md
```

---

## 1. Executive Decision

Current decision:

```text
T1_READ_ONLY_TEST_DESIGN = CREATED
T1_IMPLEMENTATION_CODE = STILL_BLOCKED
STAGE39 = NO_GO_FOR_NOW
EA_PAPER_LIVE_ORDER = NO_GO
```

T1 can move to implementation planning only after this design is accepted as:

```text
fixed
limited
non-mining
cost-aware
regime-aware
read-only
```

The first T1 test must not become a discovery factory.

---

## 2. Thesis Under Test

### THESIS_NAME

```text
T1_REGIME_FILTERED_STRUCTURE_CONTINUATION
```

### CORE_HYPOTHESIS

```text
In macro-supportive or non-hostile gold regimes, a meaningful sweep of an important upside liquidity level followed by acceptance or retest confirmation has positive continuation expectancy after conservative AMarkets spread-cost stress.
```

### Why this thesis is tested first

```text
1. It is closest to the prior raw edge from Stage36E high-sweep continuation.
2. It uses existing multi-year AMarkets MT5 H1 and 1m data.
3. It can use existing macro_daily_regime.
4. It does not depend on missing forecast/consensus data.
5. It does not depend on missing COT/ETF data.
6. It directly tests whether old pattern evidence becomes valid only under gold-aware macro filtering.
```

---

## 3. Non-goals

This test must not do any of the following:

```text
No new signal mining.
No Stage36 revival.
No Stage37 revival.
No strategy factory.
No threshold search after results.
No shorts.
No event surprise modeling.
No COT/ETF positioning model.
No EA/paper/live/order logic.
No paper-readiness claim.
No commercial-readiness claim.
```

This is only a read-only research design.

---

## 4. Primary Data Sources

### 4.1 Primary Price Source

Use local AMarkets MT5 bars:

```text
DB: data/local/xauusd_local_store.sqlite
TABLE: bars
SOURCE: amarkets_mt5
SYMBOL: XAUUSD
TIMEFRAME: 1h
```

Coverage from audit:

```text
rows = 25,643
min_utc = 2022-05-01T23:00:00+00:00
max_utc = 2026-06-16T12:00:00+00:00
```

This is the primary source for:

```text
H1 setup
H4 derived structure
D1 derived structure
previous day high
rolling 48h high
ATR_H1_14
entry/exit simulation
```

### 4.2 Execution Diagnostic Source

Use AMarkets MT5 1m bars for diagnostics only:

```text
DB: data/local/xauusd_local_store.sqlite
TABLE: bars
SOURCE: amarkets_mt5
SYMBOL: XAUUSD
TIMEFRAME: 1m
```

Coverage from audit:

```text
rows = 1,536,273
min_utc = 2022-05-01T23:01:00+00:00
max_utc = 2026-06-16T12:18:00+00:00
```

Allowed use in first read-only test:

```text
spread audit
blocked window validation
optional intra-H1 adverse/favorable excursion diagnostics
```

Not required in first implementation:

```text
tick-perfect execution
limit fill microstructure
order book
DOM
```

### 4.3 Macro Source

Use:

```text
DB: data/local/xauusd_local_store.sqlite
TABLE: macro_daily_regime
```

Important fields:

```text
obs_date
real_yield_10y
nominal_yield_10y
nominal_yield_2y
usd_index
d_real_yield_20d
d_usd_20d_pct
rate_pressure_score
usd_pressure_score
macro_score_long_gold
macro_regime
regime_reason
```

Coverage from audit:

```text
rows = 1,620
min_date = 2022-01-01
max_date = 2026-06-08
```

Do not use `macro_context_h1.macro_regime` as primary filter because audit showed all rows were `neutral`.

---

## 5. Derived Timeframes and Fields

### 5.1 H4 Bars

Derive H4 from H1.

Initial rule:

```text
H4 bar boundary = UTC 00, 04, 08, 12, 16, 20
```

Fields:

```text
h4_open
h4_high
h4_low
h4_close
h4_start_utc
h4_end_utc
```

### 5.2 D1 Bars

Derive D1 from H1.

Initial rule:

```text
D1 boundary = UTC 00:00 to 23:59
```

Potential issue:

```text
Broker day boundary may differ from UTC.
```

v0 decision:

```text
Use UTC daily boundary for reproducibility.
Record this as a limitation.
Do not optimize daily boundary in first test.
```

### 5.3 ATR

Compute:

```text
ATR_H1_14
ATR_H4_14
ATR_D1_14
```

First test minimum:

```text
ATR_H1_14
```

ATR formula:

```text
true_range = max(
    high - low,
    abs(high - previous_close),
    abs(low - previous_close)
)

ATR_H1_14 = rolling_mean(true_range, 14)
```

Do not use ATR variants in first design.

---

## 6. Macro Regime Join

### 6.1 Join Rule

Join each H1 bar to macro_daily_regime by UTC date:

```text
bar_date = date(utc_time)
join bar_date = macro_daily_regime.obs_date
```

If macro data for exact date is missing:

```text
forward-fill last available macro_daily_regime value
```

Maximum allowed forward-fill:

```text
max_ffill_days = 5 calendar days
```

If no macro regime within 5 days:

```text
skip trade candidate
```

### 6.2 Permitted Labels

For T1 long v0:

```text
permitted_macro_regime:
    supportive
    neutral_with_non_hostile_macro_score
```

Define:

```text
neutral_with_non_hostile_macro_score =
    macro_regime = neutral
    AND macro_score_long_gold >= 0
    AND (
        d_real_yield_20d <= 0
        OR d_usd_20d_pct <= 0
    )
```

### 6.3 Forbidden Labels

```text
hostile
mixed
missing_macro
```

Reason:

```text
T1 is continuation long. It should not operate in hostile macro or macro confusion in v0.
```

No safe-haven override in v0.

---

## 7. H4/D1 Structure Filter

### 7.1 D1 Structure Filter

For long continuation, require one of:

```text
D1_close > D1_MA50
OR
D1_close > D1_close_20d_ago
```

If MA50 is unavailable due to warmup:

```text
skip candidate
```

### 7.2 H4 Structure Filter

Require:

```text
H4_close > H4_MA50
OR
last_H4_swing_structure = bullish
```

For first design, to avoid complex swing logic, use:

```text
H4_close > H4_MA50
```

Swing structure can be added only in later design, not first read-only test.

### 7.3 Combined Structure Rule

Candidate is valid only if:

```text
D1 structure is bullish or non-bearish
AND H4 structure is bullish or non-bearish
```

Initial implementation rule:

```text
D1_close > D1_MA50
AND H4_close > H4_MA50
```

This is stricter but clean.

Do not optimize MA lengths.

---

## 8. Reference Level Definitions

The first read-only test may use only these levels:

```text
previous_day_high
rolling_48h_high
```

Reason:

```text
They are simple, reproducible, and do not require subjective swing detection.
```

H4 swing high is deferred.

Weekly high is deferred.

### 8.1 previous_day_high

For H1 bar at time `t`:

```text
previous_day_high = high of completed prior UTC day
```

No use of current day incomplete high.

### 8.2 rolling_48h_high

For H1 bar at time `t`:

```text
rolling_48h_high = max(high) over the previous 48 completed H1 bars before current bar
```

Exclude current bar.

### 8.3 Level Selection Rule

A candidate can use either level.

Initial level variants:

```text
LEVEL_A = previous_day_high
LEVEL_B = rolling_48h_high
```

This creates a clean factor but should not exceed total variant cap.

---

## 9. Sweep Definition

A sweep occurs when:

```text
H1_high > reference_level
```

But valid sweep requires minimum displacement.

Initial displacement rule:

```text
sweep_distance = H1_high - reference_level
sweep_distance >= 0.10 * ATR_H1_14
```

Do not mix spread_points into this price-space rule until point conversion is confirmed.

Cost is applied separately in spread_points stress reporting.

### 9.1 Signal Candle Quality

Skip if:

```text
H1_range > 2.0 * ATR_H1_14
```

Reason:

```text
Avoid late chase after an extreme candle.
```

Skip if:

```text
ATR_H1_14 is missing
```

---

## 10. Entry Variants

Only three entry variants are allowed.

### 10.1 V1 — Close Acceptance

```text
ENTRY_VARIANT = V1_CLOSE_ACCEPTANCE
CONDITION:
    signal_bar high sweeps reference level
    signal_bar close > reference level
    signal_bar close is not in lower 50% of signal_bar range

ENTRY:
    next H1 bar open
```

Close position in candle:

```text
close_position_ratio = (close - low) / (high - low)
must be >= 0.50
```

If `high == low`:

```text
skip candidate
```

### 10.2 V2 — Retest Confirmation

```text
ENTRY_VARIANT = V2_RETEST_CONFIRMATION
CONDITION:
    bar_0 sweeps and closes above reference level
    within next 3 H1 bars, a retest occurs
    retest bar low <= reference_level + 0.15 * ATR_H1_14
    retest bar close > reference_level

ENTRY:
    next H1 bar open after retest confirmation
```

No perfect limit fill.

If no retest within 3 H1 bars:

```text
no trade
```

### 10.3 V3 — Strict Next-Bar Hold

```text
ENTRY_VARIANT = V3_STRICT_NEXT_BAR_HOLD
CONDITION:
    bar_0 sweeps and closes above reference level
    bar_1 does not close below reference level

ENTRY:
    bar_2 open
```

If bar_1 closes below reference level:

```text
no trade
```

---

## 11. Stop Rules

### 11.1 V1 Stop

```text
stop = signal_bar_low - 0.10 * ATR_H1_14
```

### 11.2 V2 Stop

```text
stop = retest_bar_low - 0.10 * ATR_H1_14
```

### 11.3 V3 Stop

```text
stop = min(bar_0_low, bar_1_low) - 0.10 * ATR_H1_14
```

### 11.4 Stop Validity

Compute:

```text
stop_distance = entry_price - stop
```

Valid only if:

```text
stop_distance >= 0.50 * ATR_H1_14
AND
stop_distance <= 2.50 * ATR_H1_14
```

If invalid:

```text
skip trade
```

---

## 12. Target Rules

Two target variants:

```text
TARGET_A = 1.0R
TARGET_B = 1.5R
```

For long:

```text
target = entry_price + target_R * stop_distance
```

No TP2 in first read-only design.

No partial exits in first read-only design.

Reason:

```text
Keep first design clean and avoid exit-mining.
```

---

## 13. Time Stop Rules

Two time-stop variants:

### 13.1 TIME_A

```text
Exit after 5 completed H1 bars if TP/SL not hit.
```

Exit price:

```text
close of fifth H1 bar after entry
```

### 13.2 TIME_B

```text
If price has not reached at least +0.5R favorable progress within 3 completed H1 bars, exit at close of third H1 bar.
Otherwise continue until TP/SL or 5-bar max time stop.
```

Favorable progress:

```text
max_high_since_entry >= entry_price + 0.5 * stop_distance
```

---

## 14. Cost Application

Report every variant with these cost cases:

```text
RAW_NO_COST
BASE_COST_P50_37
NORMAL_STRESS_P75_43
DEFAULT_STRESS_P90_49
HIGH_STRESS_P95_51
TAIL_STRESS_P99_70
```

The first pass/fail decision must use:

```text
DEFAULT_STRESS_P90_49
```

### 14.1 Cost Placement

For read-only design:

```text
Apply cost to entry and exit as a conservative penalty in spread_points-equivalent R.
```

Because point conversion is not verified:

```text
Implementation design must explicitly define how spread_points maps to price.
If not verified, report cost sensitivity separately and avoid monetary interpretation.
```

### 14.2 Cost Sensitivity Metric

Required:

```text
cost_sensitivity_ratio = stress_p90_pf / raw_pf
```

If:

```text
cost_sensitivity_ratio < 0.70
```

then candidate is fragile.

---

## 15. Blocked Windows

No entry allowed during:

```text
Sunday 22:00-23:59 UTC
Monday 00:00-01:59 UTC
```

No entry allowed around high-impact scheduled event windows if available:

```text
guard_before = 60 minutes
guard_after = 30 minutes
```

If event table is incomplete:

```text
Still apply Sunday/Monday block.
Record event guard limitation.
```

No trade should be opened if exit time would likely cross weekend close unless explicitly flagged.

For v0:

```text
weekend hold is forbidden
```

---

## 16. Variant Matrix

Allowed combinations:

```text
Entry variants:
1. V1_CLOSE_ACCEPTANCE
2. V2_RETEST_CONFIRMATION
3. V3_STRICT_NEXT_BAR_HOLD

Level variants:
1. previous_day_high
2. rolling_48h_high

Target variants:
1. TP_1R
2. TP_1_5R

Time variants:
1. TIME_5H
2. TIME_3H_NO_0_5R_THEN_EXIT
```

This would produce:

```text
3 × 2 × 2 × 2 = 24 combinations
```

But Stage38A variant cap is 6–12. Therefore v0 must reduce combinations.

### 16.1 Authorized v0 Variant Set

Use only 12:

```text
For LEVEL_A = previous_day_high:
    V1 × TP_1R × TIME_5H
    V1 × TP_1_5R × TIME_5H
    V2 × TP_1R × TIME_5H
    V2 × TP_1_5R × TIME_5H
    V3 × TP_1R × TIME_5H
    V3 × TP_1_5R × TIME_5H

For LEVEL_B = rolling_48h_high:
    V1 × TP_1R × TIME_5H
    V1 × TP_1_5R × TIME_5H
    V2 × TP_1R × TIME_5H
    V2 × TP_1_5R × TIME_5H
    V3 × TP_1R × TIME_5H
    V3 × TP_1_5R × TIME_5H
```

TIME_B is deferred.

Reason:

```text
Time-stop variation can be added later only if base test survives.
```

Authorized initial variant count:

```text
12
```

---

## 17. Metrics

Every variant must report:

```text
variant_id
entry_variant
level_variant
target_variant
time_stop_variant
trade_count
gross_pf
base_cost_pf
stress_p90_pf
high_stress_p95_pf
tail_stress_p99_pf
avg_R_gross
avg_R_p90
win_rate_gross
win_rate_p90
max_drawdown_R_p90
median_R_p90
p10_R_p90
p90_R_p90
cost_sensitivity_ratio
permitted_regime_trade_count
forbidden_regime_trade_count
blocked_window_skipped_count
event_guard_skipped_count
invalid_stop_skipped_count
large_signal_skipped_count
```

Regime split required:

```text
supportive
neutral_non_hostile
hostile
mixed
missing_macro
```

The variant can only be considered if most trades are in permitted regimes.

---

## 18. Pass Criteria

Research-interest pass requires all:

```text
trade_count >= 50
stress_p90_pf >= 1.10
avg_R_p90 > 0
max_drawdown_R_p90 is not extreme relative to avg_R
permitted_regime performance > outside/forbidden performance
cost_sensitivity_ratio >= 0.70
```

Stronger candidate requires:

```text
base_cost_pf >= 1.25
stress_p90_pf >= 1.15
avg_R_p90 clearly positive
no dependency on blocked windows
no dependency on one month/year
```

These are research-only thresholds.

---

## 19. Kill Criteria

Kill T1 v0 if:

```text
1. No variant reaches stress_p90_pf >= 1.10.
2. Positive raw PF collapses under p90 cost.
3. Performance is not better in permitted regimes.
4. Most profit comes from hostile/mixed regimes.
5. Most profit comes from blocked or near-blocked windows.
6. Trade count is too small after filters.
7. Drawdown is unacceptable even in R terms.
8. Retest/acceptance does not improve raw sweep behavior.
9. Results are concentrated in one short period.
10. Unit conversion uncertainty prevents meaningful cost evaluation.
```

---

## 20. Diagnostics Required

Every failed or degraded variant must be diagnosed by:

```text
REGIME_DISTRIBUTION
YEARLY_PERFORMANCE
MONTHLY_CONCENTRATION
ENTRY_VARIANT_COMPARISON
LEVEL_VARIANT_COMPARISON
COST_SENSITIVITY
SPREAD_STRESS_IMPACT
BLOCKED_WINDOW_IMPACT
ATR_STATE
SIGNAL_CANDLE_RANGE
STOP_DISTANCE_DISTRIBUTION
TIME_TO_EXIT
MAE_MFE
```

No blind variant expansion after failure.

---

## 21. Implementation Boundary

This design does not authorize code yet.

The next document after this should be:

```text
docs/STAGE38A_T1_IMPLEMENTATION_PLAN_READ_ONLY.md
```

That implementation plan may define:

```text
script name
input tables
output report files
exact SQL queries
unit conversion handling
test result schema
validation checks
```

Only after that plan is reviewed should a read-only script be created.

Potential future script name:

```text
app/stage38a_t1_read_only_test.py
```

But this file is not authorized yet.

---

## 22. Gate Status

Current gate after this document:

```text
T1_READ_ONLY_TEST_DESIGN = CREATED
T1_IMPLEMENTATION_PLAN = ALLOWED_NEXT
T1_READ_ONLY_SCRIPT = NOT_YET_ALLOWED
STAGE39 = NO_GO
EA_PAPER_LIVE_ORDER = NO_GO
```

---

## 23. Recommended Commit

After placing this file in the repo:

```bash
cd ~/Desktop/xauusd-trader
mkdir -p docs
mv ~/Downloads/STAGE38A_T1_READ_ONLY_TEST_DESIGN.md docs/STAGE38A_T1_READ_ONLY_TEST_DESIGN.md
git status --short
git add -A
git commit -m "Add Stage38A T1 read-only test design"
git pull --rebase origin main
git push
```

---

## 24. Practical Next Step

Next artifact:

```text
docs/STAGE38A_T1_IMPLEMENTATION_PLAN_READ_ONLY.md
```

This next artifact may specify the future read-only script, but still should not create strategy code until accepted.
