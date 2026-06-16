# Stage38A — Trade Construction Spec v0

**Project:** XAUUSD / Gold Trading System  
**Stage:** Stage38A  
**Document type:** Pre-implementation trade construction specification  
**Generated UTC:** 2026-06-16T12:26:45Z  
**Status:** Required gate before any Stage39 strategy backtest  
**Execution authorization:** NO EA, NO paper-live, NO live order  
**Cost policy:** FREE-FIRST ONLY

---

چپ‌چین ادامه می‌دهم.

این سند trade construction را برای thesisهای Stage38A دقیق می‌کند. هدف این است که قبل از هر کدنویسی، entry، stop، target، time-stop، sizing، fill، cost و invalidation برای هر thesis روشن باشد.

این سند بعد از این اسناد می‌آید:

```text
docs/STAGE38A_GOLD_MARKET_THESIS_ROADMAP.md
docs/STAGE38A_GOLD_MARKET_THESIS_RECONSTRUCTION.md
docs/STAGE38A_THESIS_TEMPLATES_V0.md
docs/STAGE38A_DATA_FEASIBILITY_MATRIX.md
docs/STAGE38A_LOCAL_DATA_AUDIT_RESULT_V2_COVERAGE.md
docs/STAGE38A_SPREAD_PERCENTILE_AUDIT_RESULT.md
docs/STAGE38A_EXECUTION_COST_MODEL_V0.md
```

تصمیم کلیدی:

```text
T1 trade construction can be specified now.
T2 true-surprise trade construction remains blocked.
T2 event-reaction feasibility can be specified only as observational/non-executable.
T3 remains blocked until COT.
Stage39 remains blocked until T1 read-only test design is written and reviewed.
```

---

## 1. Executive Decision

Current status:

```text
T1_REGIME_FILTERED_STRUCTURE_CONTINUATION = TRADE_CONSTRUCTION_READY_V0
T2_EVENT_SURPRISE_FOLLOWTHROUGH_FADE = TRUE_SURPRISE_BLOCKED
T2_EVENT_REACTION_FEASIBILITY = OBSERVATIONAL_ONLY
T3_POSITIONING_SQUEEZE_EXHAUSTION = BLOCKED_UNTIL_COT
STAGE39_STRATEGY_CODE = NO_GO
EA_PAPER_LIVE_ORDER = NO_GO
```

The only thesis that can move to read-only test design next is:

```text
T1_REGIME_FILTERED_STRUCTURE_CONTINUATION
```

Even for T1, strategy code is still not authorized. The next allowed artifact is a read-only test design document, not a backtest implementation.

---

## 2. Global Construction Rules

These rules apply to all thesis families.

### 2.1 No Raw Signal Rule

No trade may be defined only by a raw price pattern.

Every trade must have:

```text
THESIS
REGIME
STRUCTURE
ENTRY
STOP
TARGET
TIME_STOP
COST_MODEL
INVALIDATION
```

### 2.2 No Perfect Execution Rule

The following assumptions are forbidden:

```text
perfect limit fill
zero spread
fixed optimistic spread
stop filled exactly at requested stop during gap/news/open stress
event entry before release
raw PF promotion
```

### 2.3 Cost Model Rule

All trade construction must use the Stage38A cost model:

```text
BASE_SPREAD_POINTS = 37
NORMAL_STRESS_SPREAD_POINTS = 43
DEFAULT_COST_STRESS_SPREAD_POINTS = 49
HIGH_STRESS_SPREAD_POINTS = 51
TAIL_STRESS_SPREAD_POINTS = 70
ABSOLUTE_OBSERVED_MAX_SPREAD_POINTS = 183
```

Unit:

```text
spread_points
```

No conversion to USD or price-unit is allowed until MT5 symbol specification is verified.

### 2.4 Blocked Window Rule

New entries are blocked by default during:

```text
Sunday 22:00-23:59 UTC
Monday 00:00-01:59 UTC
```

Any future exception must be explicitly justified and stress-tested with tail cost.

### 2.5 News Rule

For non-event theses:

```text
No new entry inside high-impact news danger window.
```

Default v0 news guard:

```text
guard_before = 60 minutes
guard_after = 30 minutes
```

For event-specific thesis:

```text
No entry before event release.
No entry until spread normalizes.
Use HIGH_STRESS or TAIL_STRESS.
```

### 2.6 Multi-Timeframe Rule

Every executable thesis must define hierarchy:

```text
D1 = macro/primary bias context
H4 = structural regime and levels
H1 = setup and confirmation
M15/M5/M1 = optional execution diagnostics only
```

For T1 v0, H1 is the primary test timeframe; H4/D1 are filters/structure.

---

# Part A — T1 Regime-filtered Structure Continuation

## 3. T1 Definition

### THESIS_NAME

```text
T1_REGIME_FILTERED_STRUCTURE_CONTINUATION
```

### Core Thesis

In a macro-supportive or non-hostile environment, a meaningful liquidity sweep of an important gold level followed by acceptance or retest confirmation can produce continuation expectancy after realistic cost.

### Current Data Status

```text
AMarkets MT5 H1 data = PASS
AMarkets MT5 1m data = PASS
macro_daily_regime = PASS
spread audit = PARTIAL PASS
execution cost model = CREATED
T1 read-only design = ALLOWED NEXT
T1 strategy backtest = STILL BLOCKED
```

### Primary Source

```text
data/local/xauusd_local_store.sqlite
table: bars
source: amarkets_mt5
symbol: XAUUSD
timeframe: 1h
```

### Secondary/diagnostic source

```text
data/local/xauusd_local_store.sqlite
table: bars
timeframe: 1m
```

---

## 4. T1 Regime Construction

### 4.1 Use macro_daily_regime, not macro_context_h1 labels

Audit showed:

```text
macro_context_h1.macro_regime = neutral for all rows
```

Therefore T1 must not use this label as the regime filter.

Use:

```text
macro_daily_regime.macro_regime
macro_daily_regime.macro_score_long_gold
macro_daily_regime.d_real_yield_20d
macro_daily_regime.d_usd_20d_pct
macro_daily_regime.rate_pressure_score
macro_daily_regime.usd_pressure_score
macro_daily_regime.regime_reason
```

### 4.2 Initial Regime Mapping

Map existing daily labels:

```text
supportive -> GOLD_BULL_MACRO_TAILWIND
hostile -> GOLD_BEAR_MACRO_HEADWIND
mixed -> RANGE_MACRO_CONFUSION
neutral -> NEUTRAL_BASELINE
```

For T1 long continuation v0:

```text
PERMITTED:
    supportive
    neutral only if H4/D1 structure is bullish and macro_score_long_gold >= 0

FORBIDDEN:
    hostile
    mixed unless a separate reclaim/range thesis is defined
```

### 4.3 Minimum Macro Condition for T1 Long

At least one of these must hold:

```text
Case A:
    macro_regime = supportive

Case B:
    macro_regime = neutral
    AND macro_score_long_gold >= 0
    AND d_real_yield_20d <= 0 OR d_usd_20d_pct <= 0

Case C:
    macro_regime = neutral
    AND H4/D1 structure is strongly bullish
    AND neither real-yield pressure nor USD pressure is hostile
```

No T1 long is allowed if:

```text
macro_regime = hostile
```

Unless future Stage38B explicitly defines a safe-haven override. That override is not authorized in v0.

---

## 5. T1 Structure Construction

### 5.1 Allowed Setup Family

Only one T1 family is authorized in v0:

```text
T1_HIGH_SWEEP_ACCEPTANCE_LONG
```

This means:

```text
Price sweeps a meaningful high and then accepts above that level or retests it successfully.
```

### 5.2 Meaningful Levels

Allowed levels:

```text
previous_day_high
rolling_48h_high
H4_swing_high
weekly_high
```

Initial priority:

```text
1. previous_day_high
2. H4_swing_high
3. rolling_48h_high
4. weekly_high
```

Round numbers are not allowed as standalone levels in v0.

### 5.3 Sweep Definition

A sweep is valid if:

```text
high_of_signal_bar > reference_level + sweep_buffer
```

Initial sweep buffer:

```text
sweep_buffer = max(0.10 * ATR_H1_14, DEFAULT_COST_STRESS_SPREAD_POINTS)
```

Because spread is in points and ATR may be in price units, implementation must later normalize units. Until then, the read-only design must explicitly define unit conversion.

If unit conversion is not verified:

```text
Use price-only ATR buffer for structure.
Use spread_points only for cost reporting.
Do not mix units silently.
```

### 5.4 Acceptance Definition

A sweep has acceptance if:

```text
H1 close > reference_level
AND close is not inside the lower 50% of the signal bar range
```

Alternative stricter acceptance:

```text
H1 close > reference_level
AND next H1 candle does not close back below reference_level
```

Initial variants allowed:

```text
T1_V1_CLOSE_ACCEPTANCE
T1_V2_RETEST_CONFIRMATION
T1_V3_STRICT_NEXT_BAR_HOLD
```

No more than these three entry variants are allowed in the first read-only design.

---

## 6. T1 Entry Rules

### 6.1 Entry Variant V1 — Close Acceptance

```text
ENTRY_NAME = T1_V1_CLOSE_ACCEPTANCE
ENTRY_TRIGGER = H1 candle closes above swept level
ENTRY_TIME = next H1 bar open
ORDER_TYPE_ASSUMPTION = market-at-next-bar-open
COST = DEFAULT_COST_STRESS_SPREAD_POINTS minimum
```

Use case:

```text
Momentum continuation after level acceptance.
```

Risk:

```text
May chase extended bars.
```

Control:

```text
Skip if signal candle range > ATR_H1_14 * max_range_multiplier
```

Initial max range rule:

```text
max_signal_range = 2.0 * ATR_H1_14
```

### 6.2 Entry Variant V2 — Retest Confirmation

```text
ENTRY_NAME = T1_V2_RETEST_CONFIRMATION
ENTRY_TRIGGER = price revisits reference_level after sweep and holds
ENTRY_TIME = after confirmation H1 candle closes back above reference_level
ORDER_TYPE_ASSUMPTION = confirmation market entry, not perfect limit fill
COST = DEFAULT_COST_STRESS_SPREAD_POINTS minimum
```

Retest is valid if:

```text
low_of_retest_bar <= reference_level + retest_tolerance
AND close_of_retest_bar > reference_level
```

Initial retest tolerance:

```text
retest_tolerance = 0.15 * ATR_H1_14
```

No perfect limit fill is allowed.

If future design uses limit entry:

```text
fill requires price to trade beyond level by fill_buffer
fill_buffer >= BASE_SPREAD_POINTS after unit conversion
```

### 6.3 Entry Variant V3 — Strict Next-Bar Hold

```text
ENTRY_NAME = T1_V3_STRICT_NEXT_BAR_HOLD
ENTRY_TRIGGER =
    bar_0 sweeps and closes above level
    bar_1 does not close below level
ENTRY_TIME = bar_2 open
ORDER_TYPE_ASSUMPTION = market-at-next-bar-open
COST = DEFAULT_COST_STRESS_SPREAD_POINTS minimum
```

Use case:

```text
Reduce failed acceptance/trap entries.
```

Risk:

```text
Later entry, lower R:R.
```

---

## 7. T1 Stop Rules

### 7.1 Structural Stop

Default stop:

```text
STOP = min(signal_bar_low, retest_bar_low) - ATR_BUFFER
```

Initial ATR buffer:

```text
ATR_BUFFER = 0.10 * ATR_H1_14
```

For V1:

```text
STOP = signal_bar_low - 0.10 * ATR_H1_14
```

For V2:

```text
STOP = retest_bar_low - 0.10 * ATR_H1_14
```

For V3:

```text
STOP = min(bar_0_low, bar_1_low) - 0.10 * ATR_H1_14
```

### 7.2 Stop Validity

Stop is invalid if:

```text
stop_distance < minimum_noise_distance
```

Initial minimum noise distance:

```text
minimum_noise_distance = 0.50 * ATR_H1_14
```

Stop is also invalid if:

```text
stop_distance > maximum_structure_distance
```

Initial maximum structure distance:

```text
maximum_structure_distance = 2.50 * ATR_H1_14
```

Reason:

```text
Too tight = noise stop.
Too wide = poor R:R and hidden volatility exposure.
```

### 7.3 Stop Fill

Normal stop fill assumption:

```text
stop fill includes DEFAULT_COST_STRESS_SPREAD_POINTS
```

Open/news stress stop fill assumption:

```text
stop fill includes TAIL_STRESS_SPREAD_POINTS
or next available adverse price if gap occurs
```

---

## 8. T1 Target Rules

### 8.1 TP1

Default:

```text
TP1 = 1.0R
```

Alternative:

```text
TP1 = 1.5R
```

Initial variants:

```text
T1_TARGET_A = TP1_1R
T1_TARGET_B = TP1_1_5R
```

No additional target mining is allowed in the first read-only design.

### 8.2 TP2

TP2 is allowed only if partial exit is modeled.

```text
TP2 = next H4/D1 liquidity level
or trailing structure exit
```

If next H4/D1 level is not defined programmatically in the read-only design:

```text
Do not use TP2.
Use single-exit TP1/time-stop design.
```

### 8.3 Partial Exit

Initial partial rule:

```text
Close 50% at TP1.
Move remaining stop only after price holds above TP1 or forms higher-low structure.
```

If partial exits are too complex for first test:

```text
Use single-position full exit at TP1.
```

Recommendation for first read-only design:

```text
Start with full exit variants only.
Add partial exit only after base construction is verified.
```

---

## 9. T1 Time Stop

Time stop is mandatory.

Default:

```text
Exit if no TP/SL within 5 H1 candles after entry.
```

Alternative stricter:

```text
Exit if no favorable progress of at least 0.5R within 3 H1 candles.
```

Initial allowed variants:

```text
T1_TIME_A = exit_after_5_H1_bars
T1_TIME_B = exit_if_less_than_0_5R_after_3_H1_bars
```

No indefinite hold is allowed.

---

## 10. T1 Position Sizing

Stage38A is research-only. Position sizing is simulated as normalized R, not live lots.

### 10.1 Research Unit

Use:

```text
risk_per_trade = 1R
```

Report performance in:

```text
R-multiple
net R after cost
cost-stressed R
```

### 10.2 Volatility Adjustment

No live sizing yet.

For research:

```text
stop_distance defines 1R
position size is implicit
```

Future live/paper sizing remains forbidden.

### 10.3 High Volatility Reduction

For diagnostic only:

```text
If ATR percentile >= 90:
    mark trade as high_vol
    report separately
```

Do not add a sizing rule until enough diagnostics exist.

---

## 11. T1 Cost Application

Every T1 report must include:

```text
RAW_NO_COST
BASE_COST_P50_37
NORMAL_STRESS_P75_43
DEFAULT_STRESS_P90_49
HIGH_STRESS_P95_51
TAIL_STRESS_P99_70
```

Pass cannot be based on raw result.

Minimum research interest:

```text
DEFAULT_STRESS_P90_PF >= 1.10
BASE_COST_P50_PF >= 1.25
avg_R_p90 > 0
```

But these are still research thresholds, not trading authorization.

---

## 12. T1 Forbidden Conditions

T1 long is forbidden if:

```text
macro_regime = hostile
blocked open/rollover window
high-impact news guard active
spread stress cannot be applied
reference level is not meaningful
signal candle range > 2.0 * ATR_H1_14
stop distance < 0.5 * ATR_H1_14
stop distance > 2.5 * ATR_H1_14
entry requires perfect limit fill
H4/D1 structure is bearish
```

For v0:

```text
No shorts.
No mean reversion.
No range fade.
No safe-haven override.
No COT filter yet.
```

---

## 13. T1 Invalidation Rules

A T1 trade is invalid if:

```text
1. price closes back below swept level before entry,
2. macro regime turns hostile before entry,
3. blocked news/open window begins before entry,
4. spread/cost model cannot be applied,
5. stop would be structurally meaningless,
6. entry candle is extreme and chase-like,
7. H4/D1 structure is not aligned.
```

A T1 thesis is invalidated if, after read-only design testing:

```text
1. performance is not better inside permitted regimes than outside,
2. p90 cost-stressed PF < 1.10,
3. avg_R_p90 <= 0,
4. drawdown remains unacceptable,
5. retest/acceptance does not improve raw sweep,
6. edge exists only in hostile or outside-regime trades,
7. edge disappears after blocked window removal.
```

---

## 14. T1 First Read-only Design Constraints

The first read-only design may include only:

```text
Entry variants:
1. V1_CLOSE_ACCEPTANCE
2. V2_RETEST_CONFIRMATION
3. V3_STRICT_NEXT_BAR_HOLD

Target variants:
1. TP1_1R
2. TP1_1_5R

Time stop variants:
1. 5_H1_BARS
2. 3_H1_BARS_IF_NO_0_5R_PROGRESS
```

Maximum combination count:

```text
3 entry variants × 2 target variants × 2 time-stop variants = 12
```

This satisfies the Stage38A maximum variant rule.

No threshold mining is allowed after results.

---

# Part B — T2 Event Surprise / Event Reaction

## 15. T2 Status

### THESIS_NAME

```text
T2_EVENT_SURPRISE_FOLLOWTHROUGH_FADE
```

### Current Decision

```text
T2_TRUE_SURPRISE = BLOCKED
T2_EVENT_REACTION_FEASIBILITY_ONLY = ALLOWED_LATER
```

Reason:

```text
actual/forecast/previous/surprise_z are not available in current schema.
forecast/consensus is not confirmed.
event files are reaction/shock proxies, not true surprise database.
```

---

## 16. T2 True Surprise Construction — Blocked

Required fields:

```text
event_type
event_timestamp_utc
actual
forecast
previous
surprise
surprise_z
pre_event_drift_24h
reaction_15m
reaction_30m
reaction_1h
followthrough_4h
followthrough_24h
regime_at_event
spread_state
```

Current missing blocker:

```text
forecast / consensus
```

Therefore:

```text
No T2 true-surprise backtest.
No T2 executable event trade.
No CPI/NFP/FOMC strategy until forecast/consensus is solved free.
```

---

## 17. T2 Event Reaction Feasibility — Observational Only

Existing event reaction tables can be used only to ask:

```text
Do macro shock classes have measurable gold reaction?
```

Allowed observational fields:

```text
event_class
event_channel
ret_1h
ret_4h
ret_12h
ret_24h
mfe_12h
mae_12h
direction_match_4h
direction_match_12h
normalized_impact_4h
normalized_impact_12h
```

Forbidden interpretation:

```text
Do not call this a surprise model.
Do not call this executable news strategy.
Do not infer forecast surprise from numeric shock alone.
```

### T2 Observational Trade Construction

No real trade construction is authorized.

Only hypothetical observation windows:

```text
anchor at event_time_utc
measure post-event returns
separate by event_class
separate by macro regime
no pre-event entry
no execution claim
```

---

# Part C — T3 Positioning Squeeze / Exhaustion

## 18. T3 Status

### THESIS_NAME

```text
T3_POSITIONING_SQUEEZE_EXHAUSTION
```

### Current Decision

```text
T3 = BLOCKED_UNTIL_FREE_COT_LAYER
```

Reason:

```text
No COT data.
No ETF flow data.
No positioning percentile.
```

---

## 19. T3 Construction — Future Only

No T3 backtest or executable design is authorized yet.

Before T3 construction:

```text
CFTC COT gold data must be imported.
COMEX gold mapping must be verified.
non-commercial long/short must be parsed.
net speculative position must be computed.
rolling percentile must be computed.
weekly COT must be aligned to D1/H4 gold.
```

### Future T3 Entry Rule

When data exists, T3 must still obey:

```text
No entry solely on COT extreme.
Entry requires H4/D1 structural failure or reclaim.
```

### Future T3 Stop Rule

```text
Stop beyond failed breakout/breakdown extreme + ATR buffer.
```

### Future T3 Target Rule

```text
Minimum 2R preferred
or next H4/D1 liquidity level.
```

### Future T3 Time Stop

```text
Exit/reduce if squeeze/reversal does not develop within 1 to 3 trading days.
```

Current T3 decision:

```text
DOCUMENT_ONLY
NO_TEST
NO_CODE
```

---

## 20. Cross-Thesis Conflict Rules

Only T1 is actionable for next read-only design. Still, conflict rules are recorded.

### T1 vs T2

If high-impact event window is active:

```text
T1 entry is blocked unless future event-specific design exists.
```

Current v0:

```text
T1 does not trade news.
```

### T1 vs T3

Since COT is missing:

```text
No T3 filter in v0.
```

Future rule:

```text
If COT crowded long extreme exists, block or reduce T1 long continuation unless structure and flow strongly confirm.
```

### T2 vs T3

Future only:

```text
If event shock occurs against crowded positioning, squeeze/reversal logic has priority over ordinary event follow-through.
```

---

## 21. Stage38A Gate After This Document

This document changes status to:

```text
T1_TRADE_CONSTRUCTION_SPEC = CREATED
T2_TRUE_SURPRISE = BLOCKED
T3_COT_REQUIRED = BLOCKED
EXECUTION_COST_MODEL = CREATED
T1_READ_ONLY_TEST_DESIGN = ALLOWED_NEXT
STAGE39_BACKTEST_CODE = STILL_BLOCKED
EA_PAPER_LIVE_ORDER = NO_GO
```

The next artifact should be:

```text
docs/STAGE38A_T1_READ_ONLY_TEST_DESIGN.md
```

Not code.

---

## 22. Checklist Before T1 Read-only Test Design

T1 read-only design must answer:

```text
[ ] Which exact bars table is primary?
[ ] How H4/D1 levels are derived from H1?
[ ] How previous_day_high is computed?
[ ] How rolling_48h_high is computed?
[ ] How H4_swing_high is computed?
[ ] How ATR_H1_14 is computed?
[ ] How macro_daily_regime is joined to H1 bars?
[ ] Which macro labels are permitted?
[ ] Which windows are blocked?
[ ] How cost levels are applied?
[ ] How unit mismatch is handled?
[ ] Which 12 variants are allowed?
[ ] What metrics are reported?
[ ] What is the kill rule?
```

---

## 23. Recommended Commit

After placing this file in the repo:

```bash
cd ~/Desktop/xauusd-trader
mkdir -p docs
cp ~/Downloads/STAGE38A_TRADE_CONSTRUCTION_SPEC_V0.md docs/STAGE38A_TRADE_CONSTRUCTION_SPEC_V0.md
git status --short
git add -A
git commit -m "Add Stage38A trade construction spec v0"
git pull --rebase origin main
git push
```

---

## 24. Practical Next Step

Create:

```text
docs/STAGE38A_T1_READ_ONLY_TEST_DESIGN.md
```

This next document should be a design-only document for the first T1 test. It should not create or authorize code yet.
