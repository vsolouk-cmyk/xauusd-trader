# Stage38A — Gold Market Thesis Reconstruction

**Project:** XAUUSD / Gold Trading System  
**Stage:** Stage38A  
**Document type:** Market-thesis reconstruction report  
**Generated UTC:** 2026-06-16T11:36:39Z  
**Status:** Strategic research document  
**Execution authorization:** NO EA, NO paper-live, NO live order, NO Stage39 code until this document's readiness gate passes

---

## 1. Executive Decision

Stage38A is approved as a non-coding, market-structural reconstruction phase.

The XAUUSD project should not be abandoned yet. However, the previous thesis-mining path must not continue. The technical stack, data loaders, SQLite store, monitoring scripts, backtest infrastructure, and strict gates have been useful, but the evidence up to Stage37A indicates that the main bottleneck is not implementation. The bottleneck is upstream market framing.

The project has treated XAUUSD too much as a pattern-mining problem. Gold must instead be framed as a macro-policy, narrative-driven, liquidity-sensitive instrument whose behavior changes across regimes.

Therefore:

- Stage38A: GO
- Stage39 implementation: NO-GO for now
- Stage36/37 revival: NO-GO
- new variant mining: NO-GO
- EA/paper-live/live order authorization: NO-GO
- background monitoring of existing Stage35C/h13/h14 only: allowed as monitor, not promotion

The immediate purpose of Stage38A is to decide whether the project can define no more than three defensible, measurable, execution-aware XAUUSD thesis families.

If Stage38A cannot produce these thesis families, the gold strategy-development branch should be frozen.

---

## 2. Why the Previous Pipeline Failed

The previous pipeline did not fail primarily because of bad code. It failed because the project started with patterns and gates before building a gold-market model.

A signal on H1 is not meaningful by itself unless the project knows:

- whether US real yields are rising or falling,
- whether USD strength is rate-driven or risk-off driven,
- whether a high CPI print is being interpreted as inflation-hedge bullish or rate-hike-fear bearish,
- whether the market is already crowded before an event,
- whether a gold move is continuation, liquidation, squeeze, or safe-haven repricing,
- whether the H1 setup is aligned with H4/D1 structure,
- whether spread/slippage conditions make the theoretical setup executable.

The project previously tested sessions, handoff windows, volatility states, calendar filters, market-structure variants, and strict cost-aware gates. These were useful, but they were not sufficient because they did not sit on top of a complete gold-market thesis.

The main lessons are:

1. Raw macro columns are not the same as macro interpretation.
2. Calendar labels are not the same as event surprise modeling.
3. Regime proxies such as session or ATR are not the same as gold-specific macro regimes.
4. Pattern-level edges can disappear when mixed across incompatible regimes.
5. Trade construction must be defined before validation, not after a raw signal looks promising.
6. Low-frequency, high-conviction setups need a different validation approach from high-frequency statistical setups.

---

## 3. Gold Market Driver Map

Gold should be modeled as the interaction of six primary driver layers.

---

### 3.1 Real Yields and Fed Expectations

This is the core macro layer.

Base logic:

- Falling real yields usually support gold.
- Rising real yields usually pressure gold.
- Dovish Fed repricing usually supports gold.
- Hawkish Fed repricing usually pressures gold.

But this relationship is not mechanical.

A fall in real yields during a crisis can produce a stronger gold rally than a normal monetary repricing. A fall in real yields during a strong risk-on environment may support gold less because safe-haven demand is weak. A rise in real yields can pressure gold, but if geopolitical demand or central-bank accumulation is dominant, gold can remain resilient.

Required interpreted features:

- real_yield_level
- real_yield_slope_20d
- real_yield_percentile_12m
- Fed expectation proxy
- change in expected policy path
- gold response to real-yield move

---

### 3.2 US Dollar Character

DXY is not enough as a raw feature. The character of USD movement matters.

Important cases:

- USD up because of rising US yields: usually bearish for gold.
- USD up because of global risk-off: gold and USD may rise together.
- USD down because of dovish Fed repricing: usually bullish for gold.
- USD down because of broad risk-on rotation: gold may rise weakly or remain range-bound.

Required interpreted features:

- DXY slope 10d/20d
- DXY impulse size
- DXY/gold correlation state
- USD move character: rate-driven vs risk-off-driven
- whether gold and DXY are co-rising

---

### 3.3 Inflation Narrative

Inflation data cannot be mapped mechanically.

A high CPI surprise can be bullish or bearish for gold depending on the active narrative.

Core cases:

- Inflation-hedge regime: high CPI surprise can be bullish.
- Rate-hike-fear regime: high CPI surprise can be bearish.
- Soft-landing regime: high CPI surprise may produce mixed or short-lived reaction.
- Crisis regime: CPI can become secondary to safe-haven demand.

Required interpreted features:

- CPI actual
- CPI forecast
- CPI previous
- CPI surprise_z
- recent inflation surprise trend
- Fed narrative at event time
- pre-event gold drift
- post-event reaction and follow-through

---

### 3.4 Risk Sentiment and Safe-Haven Demand

Gold can behave as a safe-haven asset during systemic risk, war, banking stress, geopolitical shock, or market panic.

Safe-haven behavior often includes:

- sharp repricing,
- failure of short-term mean reversion,
- gold and USD rising together,
- wider spreads,
- higher slippage,
- higher danger of late entries,
- headline-driven reversals.

Required interpreted features:

- VIX level and jump
- SPX drawdown or risk-off impulse
- gold/DXY co-rise flag
- ATR spike
- spread widening
- geopolitical/news risk flag
- distance from major daily/H4 levels

---

### 3.5 Positioning and Flow

This layer was largely missing in the previous project.

Minimum required positioning/flow layers:

- CFTC COT gold futures positioning
- speculative net long/short percentile
- 4-week positioning change
- ETF holdings/flows such as GLD/IAU if available
- flow divergence versus price
- crowding extremes

Use cases:

- identify crowded long risk,
- identify crowded short squeeze risk,
- avoid continuation into positioning extremes,
- detect possible exhaustion,
- separate momentum continuation from liquidation/squeeze.

---

### 3.6 Price Structure and Liquidity

Market structure remains important, but only under the right regime.

Relevant structure concepts:

- liquidity sweep,
- reclaim,
- acceptance above/below a level,
- breakout continuation,
- failed breakout,
- daily/H4 trend alignment,
- H1 entry structure,
- session timing,
- spread-aware execution.

The Stage36E high-sweep continuation branch was the closest raw edge to a real market thesis. However, without regime filters and full trade construction, the drawdown was unacceptable. The same structure can mean continuation in a macro bull regime and trap/exhaustion in a range or macro bear regime.

---

## 4. Regime Taxonomy

Stage38A defines five initial gold regimes. These should later be converted into simple, rule-based labels, not ML-heavy classifiers.

---

### 4.1 Regime 1 — Gold Bull / Macro Tailwind

#### Market Logic

Gold is supported by falling real yields, weak or non-hostile USD, dovish Fed repricing, inflation-hedge demand, safe-haven bid, or supportive flow/positioning.

In this regime, pullbacks are more likely to be bought, breakouts can sustain, and structure continuation has a plausible thesis.

#### Measurable Criteria v0

Potential criteria:

- real_yield_slope_20d < 0
- DXY_slope_20d <= 0, unless gold/DXY co-rise is safe-haven driven
- gold daily close above MA50 or H4 higher-high/higher-low structure
- ETF flow positive or COT momentum supportive if available
- VIX normal/elevated but not necessarily crisis
- no strong hawkish Fed repricing shock

#### Allowed Setups

- pullback long
- breakout continuation long
- high-sweep continuation long
- false-breakdown reclaim long
- event-follow-through long when surprise/regime agree

#### Disallowed Setups

- blind rally fade
- short continuation without macro regime break
- mean reversion against strong trend
- late short after dovish repricing

#### Failure Risks

- hawkish Fed repricing
- real-yield jump
- strong rate-driven USD rally
- crowded long positioning
- gold strength driven only by temporary headline

---

### 4.2 Regime 2 — Gold Bear / Macro Headwind

#### Market Logic

Gold is pressured by rising real yields, strong rate-driven USD, hawkish Fed repricing, negative ETF/flow behavior, or bearish H4/D1 structure.

Rallies tend to be sold. Breakouts can fail. Long continuation setups are dangerous unless safe-haven demand overrides the macro headwind.

#### Measurable Criteria v0

Potential criteria:

- real_yield_slope_20d > 0
- DXY_slope_20d > 0
- gold daily close below MA50 or H4 lower-high/lower-low structure
- ETF flow negative or COT speculative long falling
- event surprises interpreted as hawkish
- no active safe-haven shock

#### Allowed Setups

- rally fade
- failed breakout short
- low-sweep continuation short
- bearish retest after breakdown
- event-follow-through short when surprise/regime agree

#### Disallowed Setups

- high-sweep continuation long
- blind dip-buying
- long after hawkish CPI/NFP without confirmation
- mean reversion long in strong USD/yield impulse

#### Failure Risks

- geopolitical shock
- banking/credit stress
- sudden dovish Fed pivot
- crowded short squeeze
- central-bank or ETF demand override

---

### 4.3 Regime 3 — Range / Macro Confusion

#### Market Logic

Macro drivers are mixed. Real yields, USD, equity risk, inflation data, and Fed expectations do not point in the same direction. Gold trades between levels, with frequent sweeps, fake breaks, and unstable continuation.

This is the regime where pattern mining is most dangerous because many setups look promising in isolation but fail after costs.

#### Measurable Criteria v0

Potential criteria:

- real_yield_slope_20d near zero or unstable
- DXY_slope_20d near zero or unstable
- gold between MA50 and MA200 or inside H4 range
- compressed or directionless ATR
- major event/catalyst pending
- mixed macro score

#### Allowed Setups

- range fade with conservative R:R
- liquidity sweep and reclaim
- reduced-size mean reversion
- no-trade around high-impact events
- lower-frequency selectivity

#### Disallowed Setups

- breakout chasing
- trend continuation without confirmation
- increasing signal count to compensate for weak edge
- wide-stop trades inside noisy range

#### Failure Risks

- true breakout after catalyst
- transaction costs dominate
- false confidence from small PF edge
- regime shifts not detected quickly

---

### 4.4 Regime 4 — Safe-Haven Spike

#### Market Logic

A systemic or geopolitical shock drives urgent demand for gold. Gold can rise together with USD. Volatility expands and normal short-term mean reversion may fail.

This regime is tradable only with special caution because execution risk rises sharply.

#### Measurable Criteria v0

Potential criteria:

- VIX jump
- SPX sharp drawdown
- gold and DXY co-rise
- gold ATR spike
- spread widening
- major geopolitical/financial stress headline
- fast break of daily/H4 levels

#### Allowed Setups

- post-spike continuation after confirmation
- shallow pullback long if structure holds
- reduced-size trades only
- no-trade during immediate headline shock
- spread-aware entry

#### Disallowed Setups

- immediate mean reversion without evidence
- shorting because price is “too high”
- market entry during extreme spread
- normal H1 setup logic without crisis filter

#### Failure Risks

- headline reversal
- liquidity vacuum
- slippage and stop skip
- false or exaggerated news
- rapid transition back to range

---

### 4.5 Regime 5 — Positioning Squeeze / Crowding Reversal

#### Market Logic

Positioning is stretched. A catalyst against the crowded side can produce liquidation, stop cascades, or sharp reversals. Direction may be difficult to time, but the regime is important for blocking naive continuation trades.

#### Measurable Criteria v0

Potential criteria:

- COT net speculative percentile > 90 or < 10
- 4-week COT change extreme
- ETF flow reversal
- price/flow divergence
- daily/H4 failed breakout
- event shock against crowded positioning

#### Allowed Setups

- failed breakout reversal
- reclaim after liquidation
- squeeze continuation in direction of crowd exit
- low-frequency, high-conviction trade review
- tighter pre-trade qualitative checklist

#### Disallowed Setups

- continuation in crowded direction without confirmation
- high leverage
- H1-only entry without positioning context
- adding variants to force sample size

#### Failure Risks

- crowding can persist for weeks/months
- signal frequency is low
- timing is difficult
- early reversal attempts can be stopped repeatedly

---

## 5. Conditional Reaction Matrix

The same event or driver can produce opposite gold reactions depending on regime.

---

### 5.1 CPI Surprise × Regime

#### CPI Above Forecast

| Regime | Probable Gold Reaction | Trading Implication |
|---|---|---|
| Inflation-hedge regime | Bullish | long follow-through possible |
| Rate-hike-fear regime | Bearish | short/fade rallies possible |
| Soft-landing/range | Mixed or fake initial move | wait for confirmation |
| Safe-haven spike | CPI may be secondary | do not trade CPI mechanically |
| Crowded long | spike may fade | watch profit-taking/exhaustion |

#### CPI Below Forecast

| Regime | Probable Gold Reaction | Trading Implication |
|---|---|---|
| Fed-pivot narrative | Bullish | long continuation possible |
| Recession fear | Bullish or mixed | safe-haven interpretation possible |
| Risk-on rotation | weakly bullish or neutral | avoid overconfidence |
| Crowded long | bullish reaction may fade | require confirmation |
| Macro bear but disinflation shock | possible regime transition | monitor reversal |

---

### 5.2 NFP Surprise × Fed Regime

#### Strong NFP

| Fed Context | Probable Gold Reaction | Trading Implication |
|---|---|---|
| Active hawkish Fed | Bearish | short follow-through possible |
| Fed paused/dovish | limited or risk-on | avoid mechanical short |
| Recession fear | safe-haven demand may fall | gold neutral/down |
| Crowded short | bearish move may squeeze back | avoid late short |

#### Weak NFP

| Fed Context | Probable Gold Reaction | Trading Implication |
|---|---|---|
| Pivot expectation | Bullish | long follow-through possible |
| Recession panic | Bullish safe-haven | long possible after spread normalizes |
| Stagflation fear | regime-dependent | wait for confirmation |
| Crowded long | initial spike may fade | watch exhaustion |

---

### 5.3 FOMC Tone × Pre-positioning

| FOMC Tone | Market Already Positioned? | Probable Gold Reaction | Trading Implication |
|---|---|---|---|
| Hawkish | already hawkish | sell-the-rumor / buy-the-fact possible | avoid late short |
| Hawkish | dovish priced | bearish shock | short follow-through possible |
| Dovish | already dovish | spike may fade | require acceptance |
| Dovish | hawkish priced | bullish repricing | long continuation possible |
| Ambiguous | mixed | whipsaw risk | no-trade or wait |

---

### 5.4 DXY Impulse × Driver Character

| DXY Move | Character | Gold Implication |
|---|---|---|
| DXY up | rate/yield-driven | bearish gold |
| DXY up | global risk-off | gold may rise with USD |
| DXY down | dovish Fed | bullish gold |
| DXY down | broad risk-on | weak bullish or neutral |
| DXY mixed | no driver | avoid using DXY alone |

---

### 5.5 Real Yield Slope × Gold Trend

| Real Yield | Gold Trend | Regime Implication | Setup Bias |
|---|---|---|---|
| falling | gold above MA50 | macro tailwind | long continuation |
| rising | gold below MA50 | macro headwind | rally fade / short |
| mixed | gold range | confusion | sweep/reclaim only |
| rising | gold still strong | non-yield driver active | safe-haven/flow check |
| falling | gold weak | risk-on or flow problem | no blind long |

---

## 6. Data Gap Analysis

Stage39 cannot begin until the data requirements for selected thesis families are clear.

---

### 6.1 Essential Data Layer 1 — Required Before Stage39

| Data | Purpose | Minimum Requirement |
|---|---|---|
| XAUUSD D1/H4/H1 OHLC | multi-timeframe structure | broker-consistent history |
| spread history | execution realism | session/event-aware spread |
| 10Y real yield | macro regime | level, slope, percentile |
| DXY or USD proxy | dollar pressure | slope and impulse |
| CPI/NFP/PCE/FOMC event timestamps | event study | precise release time |
| actual/forecast/previous | surprise calculation | at least major events |
| ATR percentile | volatility regime | daily and H1 |

Without this layer, Stage39 is not allowed.

---

### 6.2 Essential Data Layer 2 — Required for Stronger Thesis Testing

| Data | Purpose | Minimum Requirement |
|---|---|---|
| CFTC COT gold positioning | crowding/squeeze | weekly net speculative positioning |
| ETF holdings/flows | investment flow | GLD/IAU or broader proxy |
| VIX/SPX | risk sentiment | risk-off/safe-haven state |
| Fed expectation proxy | policy repricing | SOFR/Fed funds proxy if accessible |
| event follow-through windows | reaction model | 15m/1h/4h/24h response |

---

### 6.3 Useful but Not Mandatory in v0

| Data | Purpose | Reason Not Mandatory |
|---|---|---|
| options skew | fear/crowding | access may be limited |
| LBMA clearing | OTC flow | lower frequency |
| WGC central bank demand | structural demand | quarterly, slow-moving |
| depth/DOM | execution detail | broker availability uncertain |
| advanced news classifier | narrative detection | avoid over-engineering first |

---

### 6.4 Data Source Principle

Stage38A should prefer simple and robust data sources. The project should not become blocked by premium or fragile data.

Priority order:

1. Use already available broker OHLC/spread data.
2. Use FRED or equivalent public macro series where available.
3. Add CFTC COT weekly data.
4. Add ETF flow/holding proxy.
5. Add event actual/forecast/previous only for the most important events first.
6. Avoid building a broad news AI classifier until simpler reaction models are tested.

---

## 7. Thesis Shortlist

Stage38A permits no more than three thesis families.

---

### 7.1 Thesis 1 — Regime-Filtered Structure Continuation

#### Market Logic

In a macro bull or neutral-bull environment, a sweep of a major high followed by acceptance/retest can indicate liquidity absorption and continuation rather than exhaustion.

This thesis preserves the useful part of the Stage36E high-sweep continuation idea but restricts it to regimes where continuation is logical.

#### Permitted Regimes

- Gold Bull / Macro Tailwind
- selected Safe-Haven Spike after spread normalization
- neutral-bull structure if macro drivers are not hostile

#### Forbidden Regimes

- Gold Bear / Macro Headwind
- Range / Macro Confusion unless converted to reclaim-only logic
- Positioning crowded long without confirmation

#### Minimum Viable Setup

1. D1 or H4 bias bullish.
2. Real-yield slope is falling or at least not rising aggressively.
3. DXY is not rate-driven bullish against gold.
4. Price sweeps a meaningful level:
   - 48h high,
   - H4 swing high,
   - daily level,
   - weekly level.
5. Price accepts above the swept level or retests it successfully.
6. Entry is on retest/confirmation, not immediate chase.
7. Stop is structural:
   - below reclaim level,
   - below sweep low,
   - ATR buffer included.
8. Target:
   - partial at 1R to 1.5R,
   - remainder toward next H4/D1 level.
9. Time stop:
   - exit if no follow-through within 3 to 5 H1 candles.
10. No trade during extreme spread/news shock.

#### Validation Metrics

- performance inside permitted regime vs outside regime
- cost-stressed PF
- average R after structural stop
- max adverse excursion
- time-to-follow-through
- failure rate after retest

#### Kill Criteria

Kill this thesis if high-sweep continuation is not positive after costs and structural stops even inside macro-bull/neutral-bull regimes.

---

### 7.2 Thesis 2 — Event Surprise Follow-through / Fade

#### Market Logic

High-impact events matter only when surprise magnitude and regime interpretation align. Event label alone is not enough.

The same CPI or NFP print can produce opposite gold reactions depending on Fed narrative, real-yield behavior, pre-positioning, and inflation/rate-hike context.

#### Permitted Regimes

- clear macro bull with dovish/disinflation surprise
- clear macro bear with hawkish surprise
- safe-haven regime after confirmation
- range only if post-event breakout is accepted

#### Forbidden Regimes

- ambiguous event reaction
- conflicting regime and surprise
- extreme spread period immediately after release
- pre-event guessing
- no actual/forecast/previous data

#### Minimum Viable Setup

1. Event type is one of:
   - CPI,
   - NFP,
   - PCE,
   - FOMC,
   - Jobless Claims if later justified.
2. actual, forecast, previous are known.
3. surprise_z is calculated.
4. regime at event time is known.
5. pre_event_drift_24h is calculated.
6. immediate reaction window:
   - 15m,
   - 30m,
   - 1h.
7. follow-through windows:
   - 4h,
   - 24h.
8. Trade only after reaction confirmation.
9. Direction must match the regime/event interpretation.
10. Time stop is short because event edge decays.

#### Example Logic

- CPI above forecast in rate-hike-fear regime:
  - gold bearish expectation,
  - short/fade rallies only after confirmation.

- CPI below forecast in Fed-pivot regime:
  - gold bullish expectation,
  - long follow-through after confirmation.

- NFP strong while Fed is actively hawkish:
  - gold bearish expectation.

- NFP weak while pivot expectation is active:
  - gold bullish expectation.

#### Validation Metrics

- surprise_z predictive value vs raw event labels
- regime-conditioned follow-through
- 15m reaction vs 4h continuation
- false initial reaction rate
- spread-adjusted event execution feasibility
- post-event entry slippage sensitivity

#### Kill Criteria

Kill this thesis if surprise_z × regime does not explain follow-through better than raw event labels.

---

### 7.3 Thesis 3 — Positioning Squeeze / Exhaustion

#### Market Logic

When gold positioning is extremely crowded, continuation becomes vulnerable. A catalyst against the crowded side can create liquidation, stop cascade, or squeeze. This thesis is lower-frequency but potentially higher-conviction.

#### Permitted Regimes

- COT extreme long or short
- ETF flow reversal
- price/flow divergence
- daily/H4 failed breakout
- event shock against crowd positioning

#### Forbidden Regimes

- no positioning data
- normal positioning percentile
- no structural failure/reclaim
- H1-only signal without daily/H4 confirmation
- continuation in crowded direction without extra confirmation

#### Minimum Viable Setup

1. COT net speculative position percentile:
   - > 90 for crowded long risk,
   - < 10 for crowded short squeeze risk.
2. 4-week COT change extreme.
3. ETF flow divergence or reversal if available.
4. Daily/H4 structure shows exhaustion:
   - failed breakout,
   - failed breakdown,
   - reclaim,
   - rejection at major level.
5. Entry only after confirmation.
6. Stop is structural, not fixed pip.
7. Target should justify low frequency:
   - minimum 2R preferred,
   - next daily/H4 liquidity level.
8. Each trade requires qualitative review.

#### Validation Metrics

- behavior after COT extremes
- continuation drawdown reduction
- reversal/squeeze frequency
- ETF divergence contribution
- structural failure confirmation value
- average R, not only win rate

#### Kill Criteria

Kill this thesis if COT/ETF extremes do not reduce drawdown, identify exhaustion, or improve filtering of continuation trades.

---

## 8. Minimum Viable Setup Template

Every Stage39 thesis must be documented with this template before implementation.

```text
THESIS_NAME:
MARKET_LOGIC:
PERMITTED_REGIMES:
FORBIDDEN_REGIMES:
REQUIRED_DATA:
SETUP_DEFINITION:
ENTRY_RULE:
STOP_RULE:
TARGET_RULE:
TIME_STOP:
POSITION_SIZE_RULE:
SPREAD_FILTER:
NEWS_FILTER:
MULTI_TIMEFRAME_REQUIREMENT:
VALIDATION_METRICS:
KILL_CRITERIA:
FASTEST_SAFE_TEST:
```

No Stage39 code should be written unless this template is complete for the thesis being implemented.

---

## 9. Validation Plan

Stage39 must be thesis-driven, not factory-driven.

Rules:

1. Each thesis may have only 6 to 12 variants initially.
2. All thresholds must be defined before backtest.
3. No threshold mining after seeing results.
4. Performance must be separated by permitted and forbidden regimes.
5. Outside-regime trades should be reported but not used to rescue the thesis.
6. Failure diagnostics are mandatory.
7. Forward shadow is allowed only for strict research candidates.
8. Paper/live remains forbidden until forward and execution realism pass.

---

### 9.1 Suggested Pass Metrics

| Metric | Suggested Threshold |
|---|---:|
| net PF | >= 1.25 |
| cost-stressed PF | >= 1.10 |
| avg R | positive |
| regime consistency | >= 70% |
| performance in permitted regime | better than all-data aggregate |
| max drawdown | sizing-compatible |
| degradation explanation | required |
| forward eligibility | only after strict research pass |

These thresholds are not final trading authorization. They are research-gate thresholds.

---

### 9.2 Failure Diagnostics

For each failed thesis or degraded candidate, produce:

```text
DEGRADATION_PERIOD:
REGIME_DISTRIBUTION:
VOLATILITY_STATE:
SPREAD_STATE:
EVENT_PROXIMITY:
DIRECTION_FAILURE:
STOP_HIT_PATTERN:
ENTRY_QUALITY:
H4_D1_ALIGNMENT:
POSITIONING_STATE:
CONCLUSION:
CONDITIONAL_FIX_OR_KILL:
```

This prevents the project from responding to degradation by blindly adding gates or variants.

---

## 10. Kill Criteria for the Gold Project

The gold strategy-development branch should be frozen if any of the following occurs:

1. Stage38A cannot define at least three measurable regimes.
2. Stage38A cannot define at least three market-based thesis families.
3. Required data for event surprise cannot be obtained or approximated.
4. COT/ETF/positioning layer cannot be added even as v0.
5. The thesis definitions regress into raw pattern mining.
6. Trade construction remains incomplete.
7. Stage39 regime-aware tests produce no strict research candidate.
8. h13/h14 background forward confirmation fails.
9. Any candidate requires unrealistic execution assumptions.
10. The project starts optimizing thresholds without market justification.

---

## 11. Stage39 Readiness Gate

Before Stage39 code, answer these ten questions for each thesis:

1. Which exact thesis are we testing?
2. Why should it work specifically in gold?
3. Which regime permits it?
4. Which regime forbids it?
5. What data is required?
6. What is the minimum viable setup?
7. What is the trade construction?
8. What is the validation metric?
9. What would invalidate the thesis?
10. What is the fastest safe test?

If these cannot be answered, do not code.

---

## 12. Stage39 Readiness Decision

Current decision:

```text
STAGE38A_STATUS=GO
STAGE39_STATUS=NO_GO_FOR_NOW
STAGE36_REVIVAL=NO_GO
STAGE37_REVIVAL=NO_GO
VARIANT_MINING=NO_GO
EA_CHANGE=NO_GO
PAPER_LIVE=NO_GO
ORDER_AUTHORIZATION=NO_GO
BACKGROUND_STAGE35C_MONITOR=ALLOWED_ONLY_AS_MONITOR
```

Stage39 becomes conditionally allowed only after:

1. this document is committed,
2. selected thesis templates are completed,
3. data feasibility is confirmed,
4. trade construction is explicit,
5. validation metrics are frozen before implementation.

---

## 13. Practical Repository Placement

Recommended path:

```text
docs/STAGE38A_GOLD_MARKET_THESIS_RECONSTRUCTION.md
```

This document should sit beside the Stage38A roadmap:

```text
docs/STAGE38A_GOLD_MARKET_THESIS_ROADMAP.md
```

The roadmap is the reference map. This reconstruction report is the formal decision document.

---

## 14. Next Step

The next practical step after committing this file is not code.

The next practical step is:

```text
Build THESIS_TEMPLATE_v0 for the three selected thesis families:
1. Regime-filtered Structure Continuation
2. Event Surprise Follow-through / Fade
3. Positioning Squeeze / Exhaustion
```

Only after those templates are complete should the project consider Stage38B/Stage39 implementation planning.

---

## 15. Safe Git Flow

Use this copy/paste flow after placing the file in the repo:

```bash
cd ~/Desktop/xauusd-trader
git status --short
git add -A
git commit -m "Add Stage38A gold market thesis reconstruction"
git pull --rebase origin main
git push
```
