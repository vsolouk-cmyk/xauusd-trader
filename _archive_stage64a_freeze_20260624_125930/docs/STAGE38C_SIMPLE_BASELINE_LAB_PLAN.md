# Stage38C — Simple Baseline Lab Plan

**Project:** XAUUSD / Gold Trading System  
**Stage:** 38C  
**Status:** Plan + first read-only diagnostic  
**Trading status:** `NO-GO` for Stage39, EA, paper-live, and live orders  
**Previous stage:** Stage38B COT/T3 data foundation completed; COT/T3 not promotable as standalone edge

---

## 1. Purpose

Stage38C restarts the research loop from simple, cost-aware baselines. The goal is not to build a trading bot. The goal is to determine whether any simple XAUUSD intraday baseline has enough post-cost robustness to justify deeper diagnostics.

Stage38B produced useful COT infrastructure, but the restricted overlay retest showed only marginal event-clock uplift. Therefore COT is retained only as contextual annotation in Stage38C. It must not be used as an entry condition, primary filter, or optimizer input in this stage.

---

## 2. Current hard constraints

```text
Stage39 = NO-GO
EA = NO-GO
paper-live = NO-GO
live orders = NO-GO
ML = NO-GO
COT as standalone signal = NO-GO
COT as primary filter = NO-GO
```

Allowed work:

```text
read-only baseline diagnostics
cost-aware historical evaluation
session/regime breakdown
failure review
kill / watch / pass decision
```

---

## 3. Inputs

Primary bar data:

```text
table: bars
source: amarkets_mt5
symbol: XAUUSD
timeframe: 1h
expected timestamp column: utc_time
```

Optional context tables:

```text
cot_gold_t3_feature_states
cot_gold_h1_features_joined
macro_daily_regime
```

The first Stage38C script uses COT only as annotation if the COT feature-state table exists. It does not filter by COT.

---

## 4. Cost model

Stage38C must remain cost-aware from the beginning. The first diagnostic uses the Stage38A stress execution assumption by default:

```text
stress_p90_cost_price = 0.49 XAUUSD price units per completed trade
```

For each hypothetical event:

```text
gross_price = direction * (exit_price - entry_price)
net_price = gross_price - stress_p90_cost_price
net_bps = net_price / entry_price * 10000
```

No raw-only pass is allowed.

---

## 5. Baseline families in first diagnostic

The first Stage38C diagnostic intentionally uses simple baselines only.

### 5.1 London open continuation / reversal

Proxy hours:

```text
07:00 UTC
08:00 UTC
```

Signal:

```text
if entry_close > previous_day_close: continuation direction = long
if entry_close < previous_day_close: continuation direction = short
reversal = opposite direction
```

### 5.2 New York open continuation / reversal

Proxy hours:

```text
13:00 UTC
14:00 UTC
```

Signal logic is the same as London open.

### 5.3 Asia range breakout / fade

Asia range proxy:

```text
00:00 UTC through 05:00 UTC
```

Scan window:

```text
07:00 UTC through 16:00 UTC
```

Signal:

```text
first close above Asia high = long breakout
first close below Asia low = short breakout
fade = opposite direction
```

Only the first valid Asia-range event per day is used.

### 5.4 ATR expansion continuation / reversal

Scan window:

```text
07:00 UTC through 17:00 UTC
```

Rules:

```text
ATR_14 is computed from completed prior H1 true ranges.
A signal bar qualifies when current true range / ATR_14 >= threshold.
thresholds: 1.20 and 1.50
continuation direction = candle body direction
reversal = opposite direction
```

Only the first qualifying event per day per threshold is used.

### 5.5 HTF bias + intraday entry

Higher-timeframe bias is computed from completed prior daily candles only:

```text
if previous completed daily close > prior D1 MA20 and prior D1 MA20 > prior D1 MA50: long bias
if previous completed daily close < prior D1 MA20 and prior D1 MA20 < prior D1 MA50: short bias
otherwise: no event
```

Entry proxy hours:

```text
London 08:00 UTC
NY 13:00 UTC
```

---

## 6. Horizons

Default horizons:

```text
3H
5H
8H
24H
```

The initial diagnostic is not intended to optimize horizons. It only checks whether any simple family has a non-trivial post-cost signal worth deeper diagnostics.

---

## 7. Output tables

The first script creates:

```text
stage38c_baseline_events
stage38c_baseline_summary
stage38c_baseline_audit
```

Reports:

```text
data/reports/stage38c_simple_baseline_lab/stage38c_simple_baseline_lab.json
data/reports/stage38c_simple_baseline_lab/stage38c_simple_baseline_lab.md
```

---

## 8. Decision rules

The first diagnostic assigns each baseline/horizon combination one of:

```text
PASS_RESEARCH_INTEREST
WATCH
KILL
```

A baseline can only be considered research-interest if it is post-cost positive and not obviously one-year dominated.

Indicative rules:

```text
sample_count >= 80
mean_net_bps >= 5
positive_year_count >= 3
max_positive_year_share <= 0.75
t_stat_mean_net_bps >= 1.20
```

Anything weaker is watch or kill. A watch decision is not a promotion.

---

## 9. Interpretation discipline

A PASS in Stage38C does not authorize Stage39, EA, paper-live, or live orders. It only authorizes deeper diagnostics such as:

```text
era ablation
month/year contribution concentration
session breakdown
spread sensitivity
news-window sensitivity
forward-shadow design
```

A marginal result must be stopped quickly. The project rule remains: do not keep testing weak paths by hope.

---

## 10. Next artifact

```text
app/stage38c_simple_baseline_lab.py
```

Purpose:

```text
Generate first read-only, cost-aware baseline diagnostics over H1 AMarkets XAUUSD bars.
```
