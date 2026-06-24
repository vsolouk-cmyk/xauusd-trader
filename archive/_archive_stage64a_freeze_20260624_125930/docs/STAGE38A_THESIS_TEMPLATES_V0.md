# Stage38A — Thesis Templates v0

**Project:** XAUUSD / Gold Trading System  
**Stage:** Stage38A  
**Document type:** Pre-implementation thesis templates  
**Generated UTC:** 2026-06-16T11:40:04Z  
**Status:** Research design document  
**Execution authorization:** NO EA, NO paper-live, NO live order, NO Stage39 code until thesis templates and data feasibility pass

---

چپ‌چین ادامه می‌دهم.

این سند سومین خروجی Stage38A است و هدف آن تبدیل نقشه بازار طلا به قالب‌های thesis قابل تست است.

اسناد مرجع این فایل:

```text
docs/STAGE38A_GOLD_MARKET_THESIS_ROADMAP.md
docs/STAGE38A_GOLD_MARKET_THESIS_RECONSTRUCTION.md
```

این فایل هنوز کد اجرایی نیست. این سند باید قبل از Stage39 تکمیل و commit شود تا هر implementation بعدی فقط از thesisهای مشخص، محدود، قابل توضیح و قابل ابطال شروع کند.

---

## 1. Executive Decision

سه thesis اولیه برای ادامه مشروط پروژه XAUUSD انتخاب می‌شوند:

1. Regime-filtered Structure Continuation
2. Event Surprise Follow-through / Fade
3. Positioning Squeeze / Exhaustion

این سه thesis تنها مسیرهای مجاز برای آماده‌سازی Stage39 هستند.

ممنوع است:

- ادامه Stage36/37 mining
- ساخت discovery factory جدید
- تولید variantهای زیاد بدون thesis
- اضافه کردن loader فقط برای «شاید بعداً لازم شود»
- شروع backtest پیش از تکمیل قالب thesis
- EA/paper/live/order authorization

هدف این سند این است که برای هر thesis دقیقاً مشخص شود:

- چرا باید در طلا کار کند؟
- در چه regimeهایی مجاز است؟
- در چه regimeهایی ممنوع است؟
- چه داده‌ای لازم دارد؟
- setup حداقلی چیست؟
- entry/stop/target/time-stop چیست؟
- چگونه اعتبارسنجی می‌شود؟
- چه چیزی thesis را باطل می‌کند؟
- سریع‌ترین تست امن چیست؟

---

## 2. Global Pre-Implementation Rules

این قواعد برای هر سه thesis اجباری است.

### 2.1 Thesis-first Rule

هیچ سیگنالی نباید فقط به دلیل خوب بودن PF یا win rate خام دنبال شود.

هر test باید از این ترتیب عبور کند:

```text
Market Logic
→ Permitted Regime
→ Required Data
→ Setup Definition
→ Trade Construction
→ Validation Metrics
→ Kill Criteria
→ Only then: Implementation
```

### 2.2 Maximum Variant Rule

برای هر thesis در Stage39 حداکثر 6 تا 12 variant اولیه مجاز است.

variantها باید از قبل تعریف شوند. تغییر threshold بعد از دیدن نتیجه ممنوع است، مگر در یک سند جداگانه با دلیل بازارمحور.

### 2.3 Regime Separation Rule

هر thesis باید جداگانه در این دو فضا گزارش شود:

```text
PERMITTED_REGIME_TRADES
FORBIDDEN_OR_OUTSIDE_REGIME_TRADES
```

اگر یک thesis فقط در کل داده خوب باشد ولی در regime مجاز خودش بهتر نباشد، thesis معتبر نیست.

### 2.4 Trade Construction Rule

هیچ thesis بدون این پنج مورد وارد Stage39 نمی‌شود:

```text
ENTRY_RULE
STOP_RULE
TARGET_RULE
TIME_STOP
SPREAD_OR_NEWS_FILTER
```

### 2.5 No Paper/Live Rule

حتی اگر Stage39 یک candidate بدهد، نتیجه فقط research candidate است.

مسیر بعدی باید این باشد:

```text
Stage39 backtest
→ strict research review
→ forward shadow
→ execution stress
→ paper decision
→ micro-live decision
```

---

## 3. Shared Regime Labels v0

برای هر thesis، این regimeها مبنا هستند:

```text
GOLD_BULL_MACRO_TAILWIND
GOLD_BEAR_MACRO_HEADWIND
RANGE_MACRO_CONFUSION
SAFE_HAVEN_SPIKE
POSITIONING_SQUEEZE_OR_CROWDING_REVERSAL
```

### 3.1 Minimum Regime Feature Set

حداقل featureهایی که باید برای regime labeling قابل بررسی باشند:

```text
real_yield_level
real_yield_slope_20d
real_yield_percentile_12m
dxy_slope_10d
dxy_slope_20d
gold_d1_trend
gold_h4_structure
gold_atr_percentile
vix_level
vix_jump
event_risk_flag
cot_net_spec_percentile
etf_flow_20d
spread_percentile
```

اگر همه این داده‌ها فوراً آماده نبودند، Stage39 فقط با thesisهایی شروع می‌شود که داده حداقلی لازم‌شان موجود است. نبود داده نباید با pattern mining جبران شود.

---

# Thesis 1 — Regime-filtered Structure Continuation

## 4. Thesis 1 Summary

### THESIS_NAME

```text
T1_REGIME_FILTERED_STRUCTURE_CONTINUATION
```

### MARKET_LOGIC

در طلا، sweep یک سطح مهم و سپس acceptance یا retest موفق می‌تواند نشان‌دهنده جذب liquidity و ادامه حرکت باشد. اما این منطق فقط در regimeهایی معتبر است که continuation از نظر macro و ساختار بزرگ‌تر معنی دارد.

Stage36E نشان داد high-sweep continuation long می‌تواند raw edge داشته باشد، اما بدون regime filter و trade construction، drawdown آن غیرقابل قبول بود. این thesis همان ایده را حفظ می‌کند ولی آن را فقط در محیط‌هایی تست می‌کند که ادامه حرکت طلا از نظر بازار منطقی است.

### WHY_THIS_SHOULD_WORK_IN_GOLD

طلا در دوره‌های macro tailwind یا safe-haven demand می‌تواند پس از شکست سطح‌های مهم، به جای برگشت سریع، حرکت continuation داشته باشد. به‌خصوص وقتی D1/H4 bias صعودی است و real yield یا دلار مانع اصلی نیستند، sweep سطح بالا می‌تواند نشانه acceptance باشد نه exhaustion.

### CORE_EDGE_HYPOTHESIS

```text
When gold is in a macro-bull or neutral-bull regime, a liquidity sweep of a meaningful high followed by acceptance/retest has positive continuation expectancy after realistic costs and structural stops.
```

---

## 5. Thesis 1 — Regime Rules

### PERMITTED_REGIMES

```text
GOLD_BULL_MACRO_TAILWIND
SAFE_HAVEN_SPIKE_AFTER_SPREAD_NORMALIZATION
NEUTRAL_BULL_STRUCTURE_IF_MACRO_NOT_HOSTILE
```

### FORBIDDEN_REGIMES

```text
GOLD_BEAR_MACRO_HEADWIND
RANGE_MACRO_CONFUSION_WITH_NO_ACCEPTANCE
POSITIONING_CROWDED_LONG_WITH_NO_CONFIRMATION
EXTREME_SPREAD_OR_NEWS_SHOCK_WINDOW
```

### REGIME_ENTRY_REQUIREMENTS

حداقل یکی از این ترکیب‌ها باید برقرار باشد:

```text
Case A — Macro bull:
real_yield_slope_20d <= 0
AND dxy_slope_20d <= 0 or gold_dxy_safe_haven_corise = true
AND gold_d1_trend != bearish

Case B — Structure bull:
gold_h4_structure = bullish
AND gold_d1_close_above_ma50 = true
AND real_yield_slope_20d is not strongly positive

Case C — Safe-haven continuation:
safe_haven_spike = true
AND spread_percentile is normalized after spike
AND H1/H4 structure holds above broken level
```

---

## 6. Thesis 1 — Required Data

### REQUIRED_DATA

```text
XAUUSD H1 OHLC
XAUUSD H4 OHLC
XAUUSD D1 OHLC
broker spread history
real yield level/slope
DXY or USD proxy
ATR H1/D1
event timestamps
```

### OPTIONAL_BUT_USEFUL_DATA

```text
COT gold positioning
ETF flow/holdings
VIX/SPX
geopolitical/safe-haven flag
```

### DATA_FEASIBILITY_DECISION

```text
T1 can start with OHLC + spread + real yield + DXY + H4/D1 structure.
COT/ETF improves filtering but is not mandatory for first feasibility test.
```

---

## 7. Thesis 1 — Setup Definition

### SETUP_DEFINITION

Long-side v0:

```text
1. Regime is permitted.
2. D1 or H4 structure is bullish or at least non-bearish.
3. Price sweeps a meaningful high:
   - 48h high, or
   - H4 swing high, or
   - previous day high, or
   - weekly high.
4. Sweep distance is meaningful:
   - above level by minimum ATR fraction or pip threshold.
5. Price closes above the swept level or retests it successfully.
6. Spread is not in extreme percentile.
7. No immediate high-impact event shock unless this is classified as post-event continuation.
```

Short-side v0 can be considered later only if macro bear structure is clearly defined. Initial Stage39 test should prioritize long-side because the strongest prior raw edge was high-sweep continuation long.

### LEVEL_PRIORITY

```text
Priority 1: previous day high / H4 swing high
Priority 2: 48h high
Priority 3: weekly high
Priority 4: round number only if supported by structure
```

### SWEEP_VALIDITY

A sweep is valid only if:

```text
sweep_distance >= min(ATR_fraction, pip_threshold)
AND level_age >= minimum bars
AND level is not created during illiquid/spread-distorted window
```

---

## 8. Thesis 1 — Trade Construction

### ENTRY_RULE

Preferred entry:

```text
Enter after retest of swept level and confirmation candle.
Do not chase immediately at the sweep candle close unless a separate momentum-continuation variant is explicitly defined.
```

Allowed entry variants:

```text
T1_V1_RETEST_CONFIRMATION
T1_V2_CLOSE_ACCEPTANCE
T1_V3_POST_EVENT_ACCEPTANCE_ONLY
```

### STOP_RULE

Stop must be structural:

```text
stop = below_retest_low_or_reclaim_level - ATR_buffer
```

Invalid stop types:

```text
fixed pip stop without volatility adjustment
stop based only on arbitrary percent
stop that ignores spread widening
```

### TARGET_RULE

Initial target logic:

```text
TP1 = 1.0R to 1.5R partial
TP2 = next H4/D1 liquidity level or trailing structure
```

### PARTIAL_EXIT_RULE

```text
Close 50% at TP1.
Move remaining stop to breakeven or structure-protected level only if follow-through confirms.
```

### TIME_STOP

```text
Exit if no follow-through within 3 to 5 H1 candles after entry.
```

### POSITION_SIZE_RULE

```text
Risk per trade should be volatility-adjusted.
High ATR percentile or safe-haven spike should reduce size.
No leverage increase is allowed to compensate for low frequency.
```

### SPREAD_FILTER

```text
No trade if spread_percentile >= 90
Caution/reduced size if spread_percentile >= 75
No entry during immediate news spike unless post-event spread normalized
```

---

## 9. Thesis 1 — Validation Metrics

### PRIMARY_METRICS

```text
net_pf
cost_stressed_pf
avg_R
max_drawdown_per_100_trades
win_rate
trade_count
regime_consistency
```

### STRUCTURE_SPECIFIC_METRICS

```text
retest_success_rate
acceptance_failure_rate
time_to_followthrough
max_adverse_excursion
max_favorable_excursion
stop_distance_distribution
TP1_hit_rate
TP2_hit_rate
```

### REQUIRED_COMPARISON

```text
T1 inside permitted regimes
vs
T1 outside permitted regimes
vs
raw Stage36E-style structure signal without regime filter
```

### PASS_CRITERIA_V0

```text
cost_stressed_pf >= 1.10
net_pf >= 1.25
avg_R > 0
permitted_regime_performance > outside_regime_performance
regime_consistency >= 70%
drawdown compatible with sizing
```

### KILL_CRITERIA

Kill T1 if:

```text
1. It is not positive inside macro-bull/neutral-bull regimes after costs.
2. Structural stops destroy expectancy.
3. Retest/confirmation does not improve raw sweep behavior.
4. Outside-regime performance is similar or better than permitted-regime performance.
5. Drawdown remains unacceptable after regime filtering and time stop.
```

### FASTEST_SAFE_TEST

```text
Implement a narrow backtest only for long-side high-sweep continuation:
- H4/D1 trend filter
- real_yield_slope_20d filter
- DXY non-hostile filter
- retest/confirmation entry
- structural stop
- 3-5 H1 candle time stop
No more than 6 initial variants.
```

---

# Thesis 2 — Event Surprise Follow-through / Fade

## 10. Thesis 2 Summary

### THESIS_NAME

```text
T2_EVENT_SURPRISE_FOLLOWTHROUGH_FADE
```

### MARKET_LOGIC

در طلا، event label به‌تنهایی کافی نیست. CPI، NFP، PCE یا FOMC فقط زمانی قابل معامله هستند که مقدار surprise، narrative فعال، pre-positioning و regime بازار با هم تفسیر شوند.

یک CPI بالاتر از انتظار می‌تواند در inflation-hedge regime برای طلا bullish باشد، اما در rate-hike-fear regime bearish شود. بنابراین event باید به surprise_z و conditional reaction تبدیل شود.

### WHY_THIS_SHOULD_WORK_IN_GOLD

طلا به انتظارات Fed، real yield و narrative تورمی بسیار حساس است. اگر event surprise باعث repricing معنادار سیاست پولی یا narrative شود و واکنش اولیه توسط بازار تأیید شود، follow-through کوتاه‌مدت می‌تواند قابل تست باشد.

### CORE_EDGE_HYPOTHESIS

```text
High-impact macro events produce tradable gold follow-through or fade only when surprise magnitude, pre-event drift, and gold regime agree.
```

---

## 11. Thesis 2 — Regime Rules

### PERMITTED_REGIMES

```text
GOLD_BULL_MACRO_TAILWIND with dovish/disinflation surprise
GOLD_BEAR_MACRO_HEADWIND with hawkish surprise
SAFE_HAVEN_SPIKE after confirmation and spread normalization
RANGE_MACRO_CONFUSION only after clear post-event acceptance breakout
```

### FORBIDDEN_REGIMES

```text
ambiguous reaction
surprise and regime conflict
spread extreme immediately after release
pre-event guessing
no actual/forecast/previous data
event timestamp uncertainty
low-impact event without evidence
```

### EVENT_DIRECTION_EXAMPLES

```text
CPI above forecast + rate-hike-fear regime = bearish gold bias
CPI above forecast + inflation-hedge regime = bullish gold bias
CPI below forecast + Fed-pivot regime = bullish gold bias
NFP strong + active hawkish Fed = bearish gold bias
NFP weak + pivot expectation = bullish gold bias
FOMC dovish vs hawkish-priced market = bullish gold repricing
FOMC hawkish vs dovish-priced market = bearish gold repricing
```

---

## 12. Thesis 2 — Required Data

### REQUIRED_DATA

```text
event_type
event_timestamp_utc
actual
forecast
previous
surprise
surprise_z
XAUUSD M15 or H1 OHLC
XAUUSD spread around event
pre_event_drift_24h
reaction_15m
reaction_30m
reaction_1h
followthrough_4h
followthrough_24h
regime_at_event
```

### INITIAL_EVENT_SCOPE

برای v0 فقط این eventها مجازند:

```text
CPI
NFP
PCE
FOMC
```

Jobless Claims، Retail Sales و ISM فقط بعد از اثبات feasibility داده و edge اولیه اضافه شوند.

### DATA_FEASIBILITY_DECISION

```text
T2 cannot start without actual/forecast/previous data.
If reliable event surprise data is not accessible, T2 must remain blocked.
Do not replace event surprise with event/no-event labels.
```

---

## 13. Thesis 2 — Setup Definition

### SETUP_DEFINITION

```text
1. Event is high-impact and in approved event scope.
2. actual/forecast/previous are known.
3. surprise_z is meaningful.
4. Regime at event time is known.
5. Pre-event drift is measured.
6. Immediate reaction is observed.
7. Spread has normalized enough for execution.
8. Entry occurs only after confirmation, never before release.
9. Direction must match event × regime logic.
```

### SURPRISE_Z_DEFINITION

Initial formula:

```text
surprise = actual - forecast
surprise_z = surprise / rolling_std_surprise_for_event_type
```

If rolling historical standard deviation is not available initially:

```text
Use event-type normalized absolute surprise buckets:
small / medium / large
```

But this must be explicitly documented as a temporary approximation.

### PRE_EVENT_DRIFT

```text
pre_event_drift_24h = gold_return_from_24h_before_event_to_event_time
```

Use cases:

```text
If market already moved strongly in expected direction before event, post-event continuation may be weaker.
If event surprises against pre-event drift, reversal/fade may be stronger.
```

---

## 14. Thesis 2 — Trade Construction

### ENTRY_RULE

```text
No entry before event release.
Wait for first reaction window.
Enter only after confirmation on 15m/30m/H1 depending on available data.
```

Initial entry variants:

```text
T2_V1_15M_REACTION_CONFIRMATION
T2_V2_30M_ACCEPTANCE
T2_V3_H1_FOLLOWTHROUGH
T2_V4_FADE_FALSE_INITIAL_REACTION
```

### STOP_RULE

Stop must account for event volatility:

```text
stop = structure_level_or_reaction_extreme +/- ATR_event_buffer
```

Avoid:

```text
tight fixed pip stops immediately after event
stops inside event wick noise
entry during spread spike
```

### TARGET_RULE

```text
TP1 = 1R or nearest post-event liquidity level
TP2 = 4h follow-through target or next H4 structure level
```

### TIME_STOP

Event edge decays quickly.

```text
Exit if no directional confirmation within 2 to 4 H1 candles.
For 15m variant, exit if no follow-through within 4 to 8 M15 candles.
```

### SPREAD_FILTER

```text
No entry while spread_percentile >= 90
No entry in first minutes if spread is abnormal
Require spread normalization relative to pre-event median
```

### NEWS_FILTER

```text
If another high-impact event is scheduled within the holding window, either skip trade or shorten time stop.
```

---

## 15. Thesis 2 — Validation Metrics

### PRIMARY_METRICS

```text
event_count
trade_count
directional_accuracy
net_pf
cost_stressed_pf
avg_R
false_initial_reaction_rate
followthrough_4h_rate
followthrough_24h_rate
```

### EVENT_SPECIFIC_METRICS

```text
surprise_bucket_performance
surprise_z_correlation_with_followthrough
pre_event_drift_effect
reaction_15m_to_4h_continuation
reaction_30m_to_4h_continuation
spread_slippage_sensitivity
regime_consistency
```

### REQUIRED_COMPARISON

```text
event label only
vs
surprise_z only
vs
surprise_z × regime
vs
surprise_z × regime × pre_event_drift
```

### PASS_CRITERIA_V0

```text
surprise_z × regime must outperform raw event label.
cost_stressed_pf >= 1.10
avg_R > 0
event execution feasible after spread filter
directional consistency materially improves after regime filter
```

### KILL_CRITERIA

Kill T2 if:

```text
1. Reliable event surprise data cannot be obtained.
2. surprise_z does not improve directional follow-through versus raw event labels.
3. Spread/slippage makes post-event entry unrealistic.
4. Regime-conditioned reactions remain incoherent.
5. Edge exists only by overfitting event-specific thresholds.
```

### FASTEST_SAFE_TEST

```text
Build a minimal event database for CPI and NFP only:
- actual/forecast/previous
- surprise_z or surprise bucket
- regime at event
- pre_event_drift_24h
- reaction_15m/30m/1h
- followthrough_4h/24h

Then test only 4 initial variants:
1. CPI dovish surprise in macro bull
2. CPI hawkish surprise in macro bear
3. NFP weak surprise in pivot/bull context
4. NFP strong surprise in hawkish/bear context
```

---

# Thesis 3 — Positioning Squeeze / Exhaustion

## 16. Thesis 3 Summary

### THESIS_NAME

```text
T3_POSITIONING_SQUEEZE_EXHAUSTION
```

### MARKET_LOGIC

وقتی positioning بازار طلا بیش از حد یک‌طرفه می‌شود، continuation کور خطرناک است. در چنین شرایطی یک catalyst می‌تواند liquidation، stop cascade یا reversal ایجاد کند.

این thesis کم‌فرکانس‌تر است، اما برای دو کار مهم استفاده می‌شود:

1. تولید setupهای high-conviction reversal/squeeze.
2. فیلتر کردن continuation tradeهایی که در جهت crowd قرار دارند.

### WHY_THIS_SHOULD_WORK_IN_GOLD

بازار طلا به positioning speculative، ETF flows و جریان‌های سرمایه‌گذاری حساس است. وقتی speculative positioning یا ETF flow بیش از حد کشیده می‌شود، قیمت می‌تواند در ظاهر trend داشته باشد اما continuation risk/reward بدتر شود.

### CORE_EDGE_HYPOTHESIS

```text
COT/ETF positioning extremes combined with daily/H4 structural failure can identify gold exhaustion or squeeze setups and reduce drawdown of naive continuation trades.
```

---

## 17. Thesis 3 — Regime Rules

### PERMITTED_REGIMES

```text
POSITIONING_SQUEEZE_OR_CROWDING_REVERSAL
GOLD_BULL_WITH_CROWDED_SHORT_SQUEEZE
GOLD_BEAR_WITH_CROWDED_LONG_LIQUIDATION
POST_EVENT_POSITIONING_REVERSAL
```

### FORBIDDEN_REGIMES

```text
normal positioning percentile
no positioning data
no ETF/flow proxy
no daily/H4 structural confirmation
H1-only signal
continuation in crowded direction without confirmation
```

### POSITIONING INTERPRETATION

```text
COT net speculative percentile > 90:
crowded long risk
watch for failed breakout, long liquidation, or rally exhaustion

COT net speculative percentile < 10:
crowded short risk
watch for short squeeze, failed breakdown, reclaim

ETF flow divergence:
price rising while ETF flows weaken = exhaustion warning
price falling while ETF flows stabilize/reverse = squeeze/reversal warning
```

---

## 18. Thesis 3 — Required Data

### REQUIRED_DATA

```text
CFTC COT gold futures positioning
net speculative long/short
COT percentile over lookback window
4-week COT change
XAUUSD D1 OHLC
XAUUSD H4 OHLC
XAUUSD H1 OHLC for entry
major daily/H4 levels
```

### STRONGLY_RECOMMENDED_DATA

```text
ETF holdings/flows such as GLD/IAU
VIX/SPX risk state
event timestamps
real yield/DXY context
```

### DATA_FEASIBILITY_DECISION

```text
T3 can start with COT + D1/H4/H1 structure.
ETF flow is strongly recommended but not mandatory for the first COT-only feasibility test.
If COT data cannot be added, T3 must remain blocked.
```

---

## 19. Thesis 3 — Setup Definition

### SETUP_DEFINITION_LONG_SQUEEZE

```text
1. COT net speculative percentile is extremely low.
2. Gold is near major support or has recently broken down.
3. Breakdown fails or price reclaims key H4/D1 level.
4. DXY/real-yield context is not aggressively hostile.
5. Entry only after reclaim confirmation.
6. Stop below failed breakdown structure.
7. Target next H4/D1 liquidity level.
```

### SETUP_DEFINITION_LONG_LIQUIDATION_SHORT_OR_FADE

```text
1. COT net speculative percentile is extremely high.
2. Gold is near major resistance or recently broke out.
3. Breakout fails or acceptance above level does not hold.
4. ETF flow divergence or weakening flow is present if available.
5. Entry only after failure confirmation.
6. Stop above failed breakout structure.
7. Target prior H4/D1 support or liquidity pool.
```

### SETUP_DEFINITION_CONTINUATION_FILTER

This thesis can also act as a filter:

```text
If continuation signal is long
AND COT crowded long percentile > 90
AND ETF flow weakening or D1/H4 exhaustion present
THEN block or reduce continuation long.
```

---

## 20. Thesis 3 — Trade Construction

### ENTRY_RULE

```text
No entry solely because COT is extreme.
Entry requires structural confirmation:
- failed breakout,
- failed breakdown,
- reclaim,
- rejection,
- post-event reversal confirmation.
```

Initial entry variants:

```text
T3_V1_CROWDED_LONG_FAILED_BREAKOUT_FADE
T3_V2_CROWDED_SHORT_RECLAIM_LONG
T3_V3_COT_EXTREME_CONTINUATION_BLOCK_FILTER
T3_V4_COT_EXTREME_EVENT_REVERSAL
```

### STOP_RULE

```text
stop = beyond failed breakout/breakdown extreme + ATR buffer
```

### TARGET_RULE

Because frequency is low, target must be meaningful:

```text
minimum target = 2R preferred
or next major H4/D1 liquidity level
```

### TIME_STOP

```text
If reversal does not develop within 1 to 3 trading days, exit or reduce exposure.
For H1 entry, if price re-enters prior continuation structure quickly, invalidate.
```

### POSITION_SIZE_RULE

```text
Use reduced initial size.
Do not increase leverage because setup is high-conviction.
Squeeze timing is uncertain; avoid oversized early reversal attempts.
```

### SPREAD_FILTER

```text
Normal spread filter applies.
Avoid entry during event shock unless the event is part of the defined reversal setup and spread has normalized.
```

---

## 21. Thesis 3 — Validation Metrics

### PRIMARY_METRICS

```text
trade_count
avg_R
net_pf
cost_stressed_pf
max_drawdown
regime_consistency
```

### POSITIONING_SPECIFIC_METRICS

```text
forward_return_after_cot_extreme_1d
forward_return_after_cot_extreme_5d
forward_return_after_cot_extreme_20d
failed_breakout_success_rate
failed_breakdown_success_rate
continuation_block_effect
drawdown_reduction_from_cot_filter
ETF_divergence_contribution
```

### REQUIRED_COMPARISON

```text
structure reversal without COT
vs
structure reversal with COT extreme
vs
continuation signal without COT filter
vs
continuation signal with COT crowding filter
```

### PASS_CRITERIA_V0

```text
COT extreme improves reversal/squeeze setup quality
OR
COT filter reduces continuation drawdown materially
avg_R > 0
drawdown reduction is meaningful
sample reviewed qualitatively if low-frequency
```

### KILL_CRITERIA

Kill T3 if:

```text
1. COT extremes do not improve reversal or filtering behavior.
2. Timing is too poor to create executable setups.
3. ETF/flow data adds no usable information.
4. The thesis only works with hindsight structural labels.
5. Execution requires holding through unacceptable gap/news risk.
```

### FASTEST_SAFE_TEST

```text
Start with COT-only feasibility:
- compute weekly COT percentile
- align to daily/H4 gold data
- identify percentile >90 and <10 zones
- test forward gold returns after extremes
- test failed breakout/reclaim behavior inside extremes
- test whether COT filter reduces drawdown of T1 continuation trades
No more than 4 initial variants.
```

---

## 22. Cross-Thesis Interaction Rules

The three thesis families should not operate independently without conflict rules.

### 22.1 T1 vs T3 Conflict

If T1 gives long continuation but T3 shows crowded long exhaustion:

```text
T1 long should be blocked or reduced unless acceptance is very strong and flow confirms.
```

If T1 gives long continuation and T3 shows crowded short squeeze:

```text
T1 long confidence increases.
```

### 22.2 T2 vs T1 Alignment

If event surprise direction agrees with T1 structure:

```text
Post-event continuation variant may be allowed.
```

If event surprise conflicts with T1 structure:

```text
No trade or wait for reclaim/failure confirmation.
```

### 22.3 T2 vs T3 Alignment

If event shock occurs against crowded positioning:

```text
T3 squeeze/reversal setup has higher priority than ordinary event follow-through.
```

If event shock supports crowded positioning:

```text
Watch for spike-and-fade risk.
```

---

## 23. Stage39 Implementation Priority

Recommended implementation order, only after Stage38A documents are committed:

### Priority 1

```text
T1_REGIME_FILTERED_STRUCTURE_CONTINUATION
```

Reason:

- closest to prior raw edge
- can reuse existing OHLC/spread infrastructure
- requires fewer new external data sources than T2/T3
- directly tests whether Stage36E can be rescued by market-aware filtering

### Priority 2

```text
T3_POSITIONING_SQUEEZE_EXHAUSTION
```

Reason:

- COT is public and feasible
- adds a missing layer
- can work both as setup and filter
- useful for preventing crowded continuation trades

### Priority 3

```text
T2_EVENT_SURPRISE_FOLLOWTHROUGH_FADE
```

Reason:

- market logic is strong
- but event actual/forecast/previous history may be harder to obtain reliably
- execution realism around news is more difficult
- should start only with CPI/NFP feasibility

---

## 24. Stage39 File Candidates — For Later Only

These files are not authorized yet. They are listed only to keep naming consistent if Stage39 becomes allowed.

```text
app/stage39a_gold_regime_feature_store.py
app/stage39b_structure_continuation_thesis_backtest.py
app/stage39c_cot_positioning_squeeze_loader.py
app/stage39d_event_surprise_database_builder.py
app/stage39e_event_reaction_thesis_backtest.py
```

Do not create these files until the Stage39 readiness gate passes.

---

## 25. Final Stage38A Gate Checklist

Before any code, answer this checklist:

```text
[ ] Are the three thesis families defined?
[ ] Is each thesis market-based rather than pattern-based?
[ ] Are permitted regimes defined?
[ ] Are forbidden regimes defined?
[ ] Is required data listed?
[ ] Is data feasibility known?
[ ] Is setup definition precise?
[ ] Is entry rule defined?
[ ] Is stop rule defined?
[ ] Is target rule defined?
[ ] Is time stop defined?
[ ] Is spread/news filter defined?
[ ] Are validation metrics frozen before backtest?
[ ] Are kill criteria explicit?
[ ] Is the fastest safe test defined?
[ ] Is Stage39 still blocked until this checklist passes?
```

Current status:

```text
STAGE38A_THESIS_TEMPLATES=CREATED
STAGE39_IMPLEMENTATION=BLOCKED_UNTIL_GATE_CHECK
EA_PAPER_LIVE_ORDER=NO_GO
```

---

## 26. Recommended Commit

After placing this file in the repo:

```bash
cd ~/Desktop/xauusd-trader
git status --short
git add -A
git commit -m "Add Stage38A thesis templates v0"
git pull --rebase origin main
git push
```

---

## 27. Next Practical Step

After this file is committed, the next practical non-coding step is:

```text
Create docs/STAGE38A_DATA_FEASIBILITY_MATRIX.md
```

That next file should decide which required data sources are already available, which are feasible, which are blocked, and which thesis can be tested first without overbuilding.
