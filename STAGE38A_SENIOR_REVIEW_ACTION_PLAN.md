# Stage38A — Senior Review Action Plan

**Project:** XAUUSD / Gold Trading System  
**Stage:** Stage38A  
**Document type:** Senior-review validation and corrective action plan  
**Generated UTC:** 2026-06-16T11:56:18Z  
**Status:** Required pre-Stage39 correction plan  
**Cost policy:** FREE-FIRST ONLY  
**Execution authorization:** NO EA, NO paper-live, NO live order, NO Stage39 strategy code until the corrective gates pass

---

چپ‌چین ادامه می‌دهم.

این سند پاسخ رسمی پروژه به نقد متخصص روی نقشه راه Stage38A است.

جمع‌بندی نقد متخصص:

```text
Strongly covered: 7 / 13
Partially covered: 4 / 13
Still missing: 2 / 13
```

نتیجه من:

نقد متخصص معتبر است. نقشه Stage38A از نظر market thesis، market map، regime، conditional reaction و positioning بسیار بهتر از مسیر قبلی است؛ اما برای عبور به Stage39 هنوز کامل نیست.

سه بدهی باید قبل از Stage39 بسته شوند:

```text
1. Execution Cost Model
2. Trade Construction Completion for Thesis 2 and Thesis 3
3. Degradation + Low-Frequency Review Templates
```

یک بدهی چهارم نیز باید همزمان اصلاح شود:

```text
4. Contextual PF / Success Threshold Justification
```

این چهار بدهی باید به gate رسمی Stage38A اضافه شوند.

---

## 1. Senior Review Verdict

### Confirmed Strengths

موارد زیر را تأیید می‌کنم که در Stage38A به شکل قابل قبول پوشش داده شده‌اند:

```text
1. Shift from pattern mining to thesis-driven design
2. Gold Market Map
3. Regime taxonomy
4. Conditional macro reaction logic
5. Event surprise concept
6. Practical handling of non-stationarity through regime-conditional testing
7. Multi-timeframe hierarchy
8. Positioning/flow commitment through COT/ETF
```

این‌ها نشان می‌دهد که Stage38A از نظر فکری مسیر درستی را شروع کرده است.

---

## 2. Confirmed Deficiency 1 — Execution Realism

### Senior Review Finding

نقد متخصص درست است: execution realism هنوز به اندازه کافی در Stage38A وارد نشده است.

موارد ناقص:

```text
news-window slippage
spread stress during CPI/NFP/FOMC
rollover cost for gold CFD
Sunday/open gap risk
partial fill / limit order non-fill
requote / stop skip risk
PF threshold derivation from real cost
```

### My Decision

این مورد را تأیید می‌کنم و آن را بدهی مهم قبل از Stage39 می‌دانم.

حتی اگر thesis درست باشد، بدون cost model واقعی، PF و avgR قابل اعتماد نیستند. اگر هزینه واقعی gold CFD در news یا rollover لحاظ نشود، Stage39 ممکن است candidate ظاهراً مثبت تولید کند که در اجرا نابود می‌شود.

### Corrective Action

باید یک سند مستقل ساخته شود:

```text
docs/STAGE38A_EXECUTION_COST_MODEL_V0.md
```

این سند باید قبل از Stage39 مشخص کند:

```text
1. Base spread model
2. Session spread model
3. News spread stress model
4. Rollover cost rule
5. Gap-risk handling
6. Slippage assumption
7. Limit order fill assumption
8. Stop execution assumption
9. Cost-stressed PF threshold
10. When a thesis is non-executable despite positive raw edge
```

### Free-Only Data Approach

هیچ داده پولی برای execution model مجاز نیست.

منابع/روش‌های رایگان:

```text
1. Existing AMarkets/MT5 spread columns if available
2. Historical bid/ask or spread in local CSV if present
3. If only mid/OHLC exists: conservative synthetic spread assumptions
4. News windows: stress multiplier based on observed local spread if available
5. Rollover: manual broker swap/contract specification from free broker pages
6. Gap risk: estimate from Sunday/open OHLC jumps in local broker data
7. Partial fill: assume no perfect fill for limit orders unless broker logs prove otherwise
```

### Minimum Execution Cost Model v0

```text
BASE_COST = observed median spread by session

STRESS_COST = max(
    observed spread percentile 90,
    session median spread × stress_multiplier
)

NEWS_COST = max(
    observed news-window spread,
    normal spread × news_multiplier
)

ROLLOVER_RULE:
    no new trades during rollover window
    open trades must include conservative rollover/swap cost if held through rollover

GAP_RULE:
    no new trades near weekly close/open
    stop execution must assume adverse gap if position held through weekend

LIMIT_FILL_RULE:
    retest limit entries must be tested with conservative fill assumption:
    either no-fill if price only touches level by less than buffer
    or worse-entry slippage buffer

STOP_RULE:
    stop filled at worse of stop level or next available adverse price in gap/news stress
```

### Gate Addition

Stage39 cannot begin unless this is true:

```text
[ ] execution cost model exists
[ ] spread source is audited
[ ] news-window cost rule is defined
[ ] rollover rule is defined
[ ] gap rule is defined
[ ] cost-stressed PF threshold is justified
```

---

## 3. Confirmed Deficiency 2 — Trade Construction for Thesis 2 and 3

### Senior Review Finding

نقد متخصص درست است: Thesis 1 نسبتاً trade-ready است، اما Thesis 2 و Thesis 3 هنوز به همان سطح precision نرسیده‌اند.

موارد ناقص:

```text
exact entry trigger
close candle vs limit vs stop order
trailing stop rule
position sizing rule
gap/news protocol during open position
event-specific stop behavior
low-frequency target logic
```

### My Decision

این مورد را تأیید می‌کنم.

Thesis 2 و Thesis 3 نباید وارد Stage39 شوند مگر اینکه trade construction آنها به سطح Thesis 1 برسد.

### Corrective Action

فایل Thesis Templates باید با یک سند تکمیلی تقویت شود:

```text
docs/STAGE38A_TRADE_CONSTRUCTION_SPEC_V0.md
```

این سند باید برای هر thesis مشخص کند:

```text
ENTRY_ORDER_TYPE
ENTRY_TIMING
CONFIRMATION_CANDLE
STOP_FORMULA
TRAILING_STOP_FORMULA
TARGET_STRUCTURE
PARTIAL_EXIT_RULE
TIME_STOP_RULE
POSITION_SIZING_RULE
SPREAD_FILTER
NEWS_GAP_PROTOCOL
INVALIDATION_RULE
```

### Thesis 2 — Required Precision

برای Event Surprise باید تصمیم‌ها این‌گونه دقیق شوند:

```text
ENTRY_TIMING:
    no entry before release
    first possible evaluation after 15m candle close
    preferred entry after 30m acceptance or H1 confirmation

ENTRY_ORDER_TYPE:
    market entry only if spread normalized
    otherwise no trade
    no limit order during immediate event spike

STOP_FORMULA:
    stop beyond reaction extreme + event_ATR_buffer
    stop must not sit inside event wick noise

TIME_STOP:
    2 to 4 H1 candles maximum unless continuation is confirmed

POSITION_SIZING:
    reduced size during event regime
    no normal-size trade if spread percentile > 75
    no trade if spread percentile > 90

GAP/NEWS_PROTOCOL:
    if another high-impact event occurs inside holding window, either skip or force shorter time stop
```

### Thesis 3 — Required Precision

برای Positioning Squeeze باید تصمیم‌ها این‌گونه دقیق شوند:

```text
ENTRY_TIMING:
    no entry solely on COT extreme
    entry only after H4/D1 failed breakout, failed breakdown, reclaim, or rejection confirmation

ENTRY_ORDER_TYPE:
    close-confirmation entry preferred
    retest limit entry allowed only with conservative fill assumption

STOP_FORMULA:
    stop beyond failed breakout/breakdown extreme + ATR buffer

TARGET:
    minimum 2R preferred
    or next H4/D1 liquidity pool

TRAILING:
    trail behind H4 swing only after price reaches at least 1R
    no aggressive trailing before squeeze begins

POSITION_SIZING:
    reduced initial size
    no leverage increase due to high-conviction narrative

TIME_STOP:
    if reversal/squeeze does not develop in 1 to 3 trading days, exit/reduce
```

### Gate Addition

Stage39 cannot begin unless:

```text
[ ] Thesis 2 entry trigger is exact
[ ] Thesis 2 stop/target/time-stop are exact
[ ] Thesis 2 event spread protocol is exact
[ ] Thesis 3 entry trigger is exact
[ ] Thesis 3 stop/target/time-stop are exact
[ ] Thesis 3 low-frequency sizing is exact
```

---

## 4. Confirmed Deficiency 3 — Degradation Diagnostic Template

### Senior Review Finding

نقد متخصص درست است: Stage38A گفت failure diagnostics لازم است، اما template کافی نداشت.

### My Decision

این مورد را تأیید می‌کنم.

بدون template، Stage39 ممکن است دوباره هر failure را با gate جدید یا variant جدید جواب دهد و وارد همان چرخه قبلی شود.

### Corrective Action

باید یک template رسمی اضافه شود.

می‌تواند در همان فایل trade construction یا در سند جداگانه باشد:

```text
docs/STAGE38A_DEGRADATION_AND_REVIEW_TEMPLATES.md
```

### Required Degradation Diagnostic Template

هر variant failed یا degraded باید این فرم را پر کند:

```text
VARIANT_NAME:
THESIS_NAME:
DEGRADATION_PERIOD:
SAMPLE_SIZE_BEFORE_DEGRADATION:
SAMPLE_SIZE_DURING_DEGRADATION:

1. REGIME_SHIFT_CHECK:
   Did the macro regime change?
   Which regime dominated during failures?

2. VOLATILITY_CHECK:
   Did ATR percentile change?
   Were failures concentrated in high-vol or low-vol states?

3. SPREAD_EXECUTION_CHECK:
   Did spread percentile increase?
   Were failures near news/rollover/illiquid sessions?

4. EVENT_PROXIMITY_CHECK:
   Were failures near CPI/NFP/FOMC/PCE or other high-impact events?

5. MTF_ALIGNMENT_CHECK:
   Were failed trades against D1/H4 bias?

6. ENTRY_QUALITY_CHECK:
   Did entry occur by chase, retest, close-confirmation, or poor fill?

7. STOP_BEHAVIOR_CHECK:
   Were stops structurally valid or inside noise?
   Did price hit stop before moving in intended direction?

8. POSITIONING_FLOW_CHECK:
   Was COT/ETF state crowded or divergent?

9. DIRECTIONAL_ASYMMETRY_CHECK:
   Are long and short failures different?

10. COST_SENSITIVITY_CHECK:
    Did the variant fail only after realistic costs?

CONCLUSION:
    conditional_fix / reduce_scope / keep_watchlist / kill
```

### Gate Addition

Stage39 output is invalid unless every candidate includes:

```text
[ ] degradation diagnostic available
[ ] failure reasons summarized
[ ] no blind variant expansion after failure
```

---

## 5. Confirmed Deficiency 4 — Low-Frequency Review Method

### Senior Review Finding

نقد متخصص درست است: Thesis 3 می‌گوید sample کم قابل قبول است، اما روش qualitative review تعریف نشده.

### My Decision

این مورد را تأیید می‌کنم.

برای low-frequency setups، فقط PF کافی نیست. ولی qualitative review هم نباید سلیقه‌ای و بدون فرم باشد.

### Corrective Action

برای Thesis 3 و هر setup کم‌فرکانس، یک review sheet لازم است.

### Low-Frequency Trade Review Template

```text
TRADE_ID:
THESIS_NAME:
DATE_TIME:
REGIME:
SETUP_TYPE:
D1_CONTEXT:
H4_CONTEXT:
COT_STATE:
ETF_FLOW_STATE:
EVENT_CONTEXT:
ENTRY_REASON:
ENTRY_TYPE:
STOP_REASON:
TARGET_REASON:
TIME_STOP_RULE:
SPREAD_STATE:
NEWS_RISK:
OUTCOME_R:
MAE:
MFE:
DID_TRADE_MATCH_THESIS:
DID_FAILURE_INVALIDATE_THESIS:
LESSON:
REVIEW_DECISION:
    valid_win / valid_loss / execution_failure / thesis_conflict / data_quality_issue
```

### Minimum Evidence Rule

برای low-frequency thesis:

```text
A small sample can remain active only if:
1. every trade has complete review sheet,
2. at least 70% of trades match thesis logic,
3. losses are explainable without post-hoc excuses,
4. execution failures are separated from thesis failures,
5. candidate is not promoted to paper/live from low sample alone.
```

---

## 6. Confirmed Deficiency 5 — PF Threshold Without Cost Context

### Senior Review Finding

نقد متخصص درست است: عدد PF >= 1.25 نباید فقط convention باشد. باید به cost model، spread واقعی، slippage و execution stress وصل شود.

### My Decision

این مورد را تأیید می‌کنم.

PF خام بدون cost context می‌تواند misleading باشد.

### Corrective Action

PF thresholds باید از سه لایه ساخته شوند:

```text
RAW_PF:
    before realistic spread/slippage stress

NET_PF:
    after observed median spread/session cost

COST_STRESSED_PF:
    after stress spread/news/rollover/gap assumptions
```

### Suggested Rule v0

```text
A thesis cannot pass only on raw PF.

Minimum:
    NET_PF >= 1.25
    COST_STRESSED_PF >= 1.10

But these thresholds must be revisited after execution cost model is built.
```

### Better Stage39 Gate

```text
If observed spread/slippage cost is high:
    required raw PF must increase.

If strategy trades news windows:
    cost-stressed PF is more important than raw PF.

If strategy is low-frequency:
    avgR and thesis-valid trade review are more important than PF alone.
```

---

## 7. Corrected Stage38A Gate Before Stage39

Stage39 remains blocked until all of these are done:

```text
[ ] STAGE38A_GOLD_MARKET_THESIS_ROADMAP.md committed
[ ] STAGE38A_GOLD_MARKET_THESIS_RECONSTRUCTION.md committed
[ ] STAGE38A_THESIS_TEMPLATES_V0.md committed
[ ] STAGE38A_DATA_FEASIBILITY_MATRIX.md committed
[ ] STAGE38A_LOCAL_DATA_AUDIT_CHECKLIST.md committed
[ ] STAGE38A_EXECUTION_COST_MODEL_V0.md created
[ ] STAGE38A_TRADE_CONSTRUCTION_SPEC_V0.md created
[ ] STAGE38A_DEGRADATION_AND_REVIEW_TEMPLATES.md created
[ ] local data availability audited
[ ] free-source data gaps identified
[ ] paid data rejected or deferred
[ ] T1/T2/T3 readiness individually decided
```

Current decision:

```text
STAGE38A_CORE_MARKET_MODEL=STRONG
STAGE38A_DATA_FEASIBILITY=IN_PROGRESS
EXECUTION_REALISM=BLOCKER_BEFORE_STAGE39
T2_T3_TRADE_CONSTRUCTION=BLOCKER_BEFORE_STAGE39
DEGRADATION_TEMPLATE=BLOCKER_BEFORE_STAGE39
LOW_FREQUENCY_REVIEW=BLOCKER_FOR_T3_PROMOTION
PF_THRESHOLD=REQUIRES_COST_MODEL
STAGE39=NO_GO_FOR_NOW
```

---

## 8. Recommended Document Sequence

Recommended order from here:

```text
1. docs/STAGE38A_LOCAL_DATA_AUDIT_CHECKLIST.md
2. docs/STAGE38A_EXECUTION_COST_MODEL_V0.md
3. docs/STAGE38A_TRADE_CONSTRUCTION_SPEC_V0.md
4. docs/STAGE38A_DEGRADATION_AND_REVIEW_TEMPLATES.md
5. docs/STAGE38A_STAGE39_READINESS_GATE.md
```

Reason:

```text
First audit what we have.
Then define execution cost because it affects PF threshold.
Then finalize trade construction.
Then lock diagnostic/review templates.
Then decide Stage39 readiness.
```

---

## 9. Senior Review Conclusion

The senior review does not invalidate Stage38A. It improves it.

My final decision:

```text
ACCEPT_REVIEW=YES
STAGE38A_CONTINUES=YES
STAGE39_REMAINS_BLOCKED=YES
EXECUTION_COST_MODEL_REQUIRED=YES
T2_T3_TRADE_CONSTRUCTION_REQUIRED=YES
DEGRADATION_TEMPLATE_REQUIRED=YES
LOW_FREQUENCY_REVIEW_REQUIRED=YES
PAID_DATA=NO_GO
```

The roadmap is fundamentally strong, but it should not be promoted to implementation until these corrective documents and gates are added.
