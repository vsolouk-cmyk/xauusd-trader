# XAUUSD Stage66 Corrected Operational Plan — Speed-Compatible Governance

Date: 2026-06-25  
Purpose: document the corrected operational path after the Stage65→Stage66 expert review, so it can be sent for external analytical approval before implementation.

---

## 1. Executive decision

The current project state must be corrected immediately.

Stage65 daily forward-shadow ledger is technically valid, but it must not remain the main path. A daily ledger that requires 180 calendar days and at least 5 new forward signals before any meaningful decision is structurally incompatible with the project objective: reaching a practical, operational, commercially usable XAUUSD/gold trading system as fast as prudently possible.

The corrected path is:

1. Keep Stage65 only as background telemetry.
2. Immediately run historical concentration and outlier audit on H64L.
3. Immediately run rolling-origin / forward-like replay using existing historical data.
4. Build a no-order paper-execution simulator for H64L with explicit sizing, risk, mark-to-market, and governance.
5. In parallel, pre-register only 2–4 complementary macro theses to address the likely frequency gap.
6. Replace the 180-day future ledger as the main gate with faster, risk-aware decision gates.
7. Do not move to real broker order, EA, paper-live, or live until a later explicit governance gate is approved.

This plan does not weaken governance. It corrects the sequence: risk should be controlled by sizing, simulation, staged exposure, concentration audit, and fast historical replay, not by putting the project into a six-month waiting room.

---

## 2. Current facts that caused the redesign

### 2.1 Strong survivor exists

The locked survivor is:

```text
H64L_H1_FULL_MACRO_TAILWIND_LONG
horizon_days: 120
benchmark: EXTERNAL_SPOT_B1_TREND_ONLY_REFERENCE
```

Stage64R external transfer headline:

```text
joined_return_days: 3578
candidate_active_days: 336
candidate_mean_bps: 1059.5781768455959
external_B1_active_days: 1296
external_B1_mean_bps: 672.7337370199871
mean_excess_vs_external_B1_bps: 386.8444398256088
one_sided_p_uncorrected_z_approx: 7.937411793850522e-07
positive_excess_splits_vs_external_B1: 3
max_split_share_of_candidate_active_days: 0.3898809523809524
max_year_share_of_candidate_active_days: 0.2916666666666667
```

Interpretation:

- The signal is not a weak intraday candidate.
- The thesis has market logic: gold tends to perform better when gold trend, dollar weakness, real-yield decline, ETF flow, and central-bank demand align.
- The p-value / implied z-score is strong enough to justify immediate controlled operationalization work.
- But the mean return is unusually large and the positive split count is low enough that concentration risk must be audited before sizing decisions.

### 2.2 Stage65 has become a bottleneck

Latest Stage65B showed:

```text
status: STAGE65B_DAILY_OPERATION_COMPLETE_NO_PROMOTION
decision: STAGE65_FORWARD_LEDGER_ACTIVE_CONTINUE_DAILY_NO_ORDER
macro_dataset_latest_date: 2026-06-24
external_d1_latest_date: 2026-06-25
stage65_returncode: 0
forward_governance_ready: false
observed_new_signals: 0
calendar_span_days: 0
matured_observations: 0
observed_new_signals_min: 5
calendar_span_min_days: 180
```

Interpretation:

- Stage65 is functioning.
- Data freshness is acceptable.
- The current signal is inactive.
- The ledger has not produced any forward evidence yet.
- If this remains the main gate, the project waits for future calendar time rather than extracting decision value from available data.

### 2.3 Expert review diagnosis

The expert review correctly identified these structural problems:

1. The project moved from over-aggressive candidate hunting to over-conservative gate bureaucracy.
2. A 120-day position horizon was confused with a 120–180 day decision cycle.
3. Gates designed for intraday/high-frequency candidates were copied into a low-frequency macro-regime thesis.
4. The current tracks emphasized more validation but lacked a direct path to controlled deployment/paper execution.
5. Concentration risk around the large 10.6% average return must be tested quickly.
6. Risk of tactical deployment should be controlled by sizing and staged exposure, not by waiting indefinitely.

---

## 3. Corrected governing principle

The project’s overriding decision rule is:

```text
Every stage, validation, patch, gate, and recommendation must be judged by whether it materially reduces time-to-decision or time-to-operational-readiness while preserving catastrophic-risk controls.
```

Practical meaning:

- Waiting is justified only if real time is the only way to obtain the required evidence.
- Historical replay, concentration audit, and paper simulation must be used first when they can answer the decision question faster.
- Forward shadow is useful as telemetry, but not as the main engine of progress.
- No stage should become a research ritual if it does not produce a clear operational decision.

---

## 4. Corrected architecture

The corrected Stage66 architecture has six tracks.

```text
Track A: Stage65 background telemetry
Track B: H64L concentration / outlier / split audit
Track C: Rolling-origin / forward-like historical replay
Track D: H64L no-order paper-execution simulator
Track E: Limited complementary macro thesis program
Track F: Governance redesign and decision dashboard
```

Execution order:

```text
Immediate package 1:
  Track A + Track B + Track C + Track F

Immediate package 2:
  Track D

Parallel package 3:
  Track E
```

Reason for this order:

- Track B and C are fastest because they use existing data.
- Track F prevents the same gate mistake from recurring.
- Track D should start after B/C define concentration and risk assumptions.
- Track E runs in parallel to solve the frequency gap, but must not become another uncontrolled megascan.

---

## 5. Track A — Stage65 as background telemetry only

### Objective

Keep collecting real forward evidence without letting it block the main project.

### Operational decision

Stage65 should be moved to a scheduled GitHub Actions workflow and treated as a passive background process.

### What Stage65 is allowed to do

- Refresh/confirm Stage64K and external D1 files.
- Run Stage65 daily.
- Append to forward signal ledger.
- Append to observation ledger when observations mature.
- Produce daily summary JSON/MD.
- Alert only on:
  - signal activation,
  - data staleness,
  - governance violation,
  - script failure,
  - ledger corruption.

### What Stage65 is not allowed to do

- It must not block Stage66.
- It must not be a prerequisite for paper simulation.
- It must not authorize paper order.
- It must not authorize broker connection.
- It must not authorize EA promotion.
- It must not authorize live.
- It must not use historical event filtering.
- It must not backfill forward ledger manually.

### Deliverables

```text
.github/workflows/stage65_forward_shadow_daily.yml
app/stage65b_forward_shadow_daily_ops.py
configs/stage65b_forward_shadow_daily_ops.json
reports/stage65b_forward_shadow_daily_ops/*.json
reports/stage65b_forward_shadow_daily_ops/*.md
data/forward_shadow/stage65_macro_signal_ledger.csv
data/forward_shadow/stage65_observation_ledger.csv
```

### Decision output

Stage65 produces telemetry, not deployment approval.

Possible labels:

```text
STAGE65_BACKGROUND_OK_SIGNAL_INACTIVE
STAGE65_BACKGROUND_OK_SIGNAL_ACTIVE
STAGE65_BACKGROUND_DATA_STALE
STAGE65_BACKGROUND_LEDGER_ERROR
STAGE65_BACKGROUND_GOVERNANCE_BREACH
```

---

## 6. Track B — Stage66A concentration / outlier / split audit

### Objective

Determine whether H64L’s large historical edge is broad enough to support controlled paper execution, or whether it is mostly a few exceptional macro events.

This is the first and most urgent decision-value stage.

### Core questions

1. Which exact dates/regimes produced the 336 active candidate days?
2. Are the returns driven by one or two large events?
3. What happens if the top event, top year, or top split is removed?
4. Does the excess return over B1 survive after excluding the largest contributors?
5. Is the 10.6% mean return mostly mean reversion from a few outliers?
6. Is the signal tradable as a regime allocation, or only a historical explanation?

### Required inputs

```text
data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv
data/macro_regime/raw/broker_or_spot_gold_d1_ohlc_2011_present.csv
reports/stage64r*/summary.json if present
reports/stage64r*/report.md if present
```

If event-level Stage64R output does not exist, the Stage66A script must reconstruct candidate-active windows from the locked H64L rules and external D1 returns.

### Required calculations

#### 6.1 Event segmentation

Group contiguous active days into episodes.

For each episode:

```text
episode_id
start_date
end_date
active_days
entry_close
exit_close
raw_return_bps
benchmark_return_bps
excess_return_bps
max_favorable_excursion_bps
max_adverse_excursion_bps
max_drawdown_during_episode_bps
share_of_total_candidate_return
share_of_total_excess_return
dominant_calendar_year
dominant_macro_context
```

#### 6.2 Contribution concentration

Calculate:

```text
top_1_episode_return_share
top_2_episode_return_share
top_3_episode_return_share
top_1_episode_excess_share
top_2_episode_excess_share
top_3_episode_excess_share
herfindahl_return_concentration
gini_return_concentration
max_year_return_share
max_split_return_share
```

#### 6.3 Leave-one-out tests

Run these exclusions:

```text
drop_top_1_episode
drop_top_2_episodes
drop_top_3_episodes
drop_top_year
drop_top_split
drop_2020_if_present
drop_2024_if_present
drop_2025_if_present
drop_covid_like_period_if_present
drop_rate_pivot_like_period_if_present
```

For each exclusion, report:

```text
candidate_active_days_remaining
candidate_mean_bps_remaining
benchmark_mean_bps_remaining
mean_excess_bps_remaining
median_excess_bps_remaining
trimmed_mean_excess_bps_remaining
positive_episode_rate
positive_split_count
max_drawdown_proxy
status
```

#### 6.4 Robustness to return measure

Compare:

```text
mean
median
20% trimmed mean
winsorized mean
episode-level mean
day-level mean
split-level mean
year-level mean
```

#### 6.5 Path risk

Because H64L has a 120-day horizon, total return alone is not enough.

Calculate:

```text
maximum intra-horizon drawdown
time_underwater
worst_20_day_return_inside_signal
worst_60_day_return_inside_signal
MFE/MAE ratio
daily mark-to-market volatility
```

### Stage66A pass / caution / fail logic

This stage should not be a simplistic pass/fail. It must output a sizing implication.

```text
PASS_FAST:
  edge remains positive after dropping top episode and top year
  excess return remains positive on median or trimmed basis
  no single episode contributes more than 40% of excess
  at least 3 independent episodes remain meaningfully positive

PASS_SMALL_SIZE_ONLY:
  edge remains positive but top episode/year concentration is high
  mean remains strong but median/trimmed result is weaker
  path drawdowns are material but not thesis-breaking

RESEARCH_ONLY:
  edge disappears after dropping top episode or top year
  median and trimmed excess are near zero or negative
  most of the edge comes from one macro shock

KILL_OR_ARCHIVE:
  reconstructed results do not match Stage64R
  as-of lag safety fails
  rules cannot be reproduced
  external D1 alignment fails
```

### Expected decision value

Stage66A should answer in one run:

```text
Is H64L strong enough to become the main thesis with paper execution simulation?
If yes, what initial virtual/paper sizing band is justified?
If no, should H64L become only macro background telemetry?
```

---

## 7. Track C — Stage66B rolling-origin / forward-like historical replay

### Objective

Replace the slow 180-day future ledger as the main decision tool with a historical replay that mimics forward decision-making using only information available at each historical as-of date.

This is not ordinary backtest optimization. It is a forward-like replay.

### Core principle

For each historical as-of date, the system must behave as if it were running that day:

```text
Only data available after sample_available_after_utc is usable.
No future features.
No event calendar filtering.
No parameter retuning.
No post-hoc exclusion.
No reduced-scope rescue.
No threshold tuning.
```

### Required replay windows

Use rolling origins such as:

```text
train/evidence window: prior 5 years
decision window: next 1 year
step: 1 month or 1 quarter
horizon checkpoints: 20d, 60d, 120d
```

This does not mean the system retrains a model. It means it tests whether the locked H64L rule would have been accepted and then how it performed prospectively in each historical slice.

### Required outputs

For every rolling-origin slice:

```text
asof_date
available_history_start
available_history_end
forward_window_start
forward_window_end
candidate_active_days_forward
candidate_episode_count_forward
candidate_return_20d
candidate_return_60d
candidate_return_120d
benchmark_return_20d
benchmark_return_60d
benchmark_return_120d
excess_20d
excess_60d
excess_120d
max_drawdown_forward
signal_frequency_forward
stage_decision_that_would_have_been_made
```

Aggregate:

```text
number_of_origins
positive_excess_origins_20d
positive_excess_origins_60d
positive_excess_origins_120d
average_excess_by_origin
median_excess_by_origin
worst_origin_excess
best_origin_excess
origin_concentration
era_breakdown
pre_2020_vs_post_2020
pre_2024_vs_post_2024
```

### Decision logic

```text
PASS_FAST:
  H64L adds value in most rolling origins
  60d or 120d excess is positive in multiple independent eras
  no single era controls the result

PASS_WITH_SHORTER_CHECKPOINT:
  120d is positive but earlier 20d/60d checkpoint gives useful risk control
  proceed to paper-execution simulator with checkpoint governance

PASS_LOW_FREQUENCY_ONLY:
  edge is strong but signal frequency too low
  keep H64L as main macro allocation thesis but prioritize complementary shorter thesis search

RESEARCH_ONLY:
  edge appears only in one or two origins
  use H64L as explanatory macro context, not primary operational thesis

KILL_OR_ARCHIVE:
  rolling-origin replay cannot reproduce Stage64R strength
  edge flips negative after realistic as-of constraints
```

### Expected decision value

Stage66B should answer:

```text
Would this thesis have survived repeated historical as-of decision cycles?
Can we use 20d/60d checkpoints to manage a 120d regime position?
Is the edge stable enough to simulate paper execution now?
```

---

## 8. Track D — Stage66C no-order paper-execution simulator

### Objective

Build a realistic paper-execution layer for H64L without broker connection and without real orders.

This is the first operationalization layer, but it remains no-order.

### Why this is necessary

The previous Stage65 ledger records whether a signal is active, but it does not answer:

- How much would we allocate?
- When would the paper position enter?
- How would we mark it daily?
- What happens if regime deteriorates before 120 days?
- What drawdown is tolerable?
- What would the system do during news/event risk?
- How would paper P&L look under broker-like spread and conservative slippage?

### Paper-execution rules to define

#### Entry rule

Suggested default:

```text
If H64L signal_active is true as of feature_date D and sample_available_after_utc <= D+1 00:00 UTC:
  paper entry occurs at next available external D1 open or conservative next-day close proxy
```

Implementation should support both:

```text
entry_price_mode: next_d1_open
entry_price_mode: next_d1_close_conservative
```

If external D1 open is unavailable or unreliable, use close-to-close conservative proxy and label it clearly.

#### Exit rule

Base holding horizon:

```text
max_holding_days: 120
```

But add tactical checkpoints:

```text
checkpoint_20d
checkpoint_60d
checkpoint_120d
```

Possible exits:

```text
exit_at_120d
exit_if_signal_deactivates_after_min_hold
exit_if_macro_tailwind_breaks
exit_if_drawdown_guard_triggers
exit_if_data_quality_fails
exit_if_manual_governance_blackout_is_active
```

The initial implementation should compare these exit variants without selecting a new optimized rule post-hoc.

#### Sizing rule

Because this is paper simulation, use virtual sizing.

Suggested test bands:

```text
paper_risk_band_A: 0.10% account risk equivalent
paper_risk_band_B: 0.25% account risk equivalent
paper_risk_band_C: 0.50% account risk equivalent
```

If no hard stop is used, sizing should be notional-cap based:

```text
max_notional_exposure_A: 5% of virtual account
max_notional_exposure_B: 10% of virtual account
max_notional_exposure_C: 20% of virtual account
```

The report must show both return and drawdown under each sizing band.

#### Cost/slippage assumptions

Use conservative assumptions:

```text
spread_cost_source: AMarkets spread export if available
fallback_spread_bps: conservative fixed assumption
slippage_bps: conservative fixed assumption
round_trip_cost_bps: spread + slippage
```

Because Stage64O/P/Q did not establish full broker-specific claim, the simulator must label results as:

```text
BROKER_REALISM_APPROXIMATION_NO_BROKER_CLAIM
```

#### Risk guards

Paper simulation must include:

```text
max_daily_mark_to_market_loss
max_position_drawdown
max_total_virtual_drawdown
max_gap_loss_proxy
data_staleness_stop
macro_data_lag_stop
external_d1_missing_stop
event_blackout_annotation_only_initially
```

Historical event filtering remains forbidden for signal construction. Event calendar can only be used as forward annotation or blackout governance after explicit approval.

### Required outputs

```text
data/paper_sim/stage66c_h64l_paper_trade_ledger.csv
data/paper_sim/stage66c_h64l_daily_mark_to_market.csv
reports/stage66c_h64l_paper_execution_simulator/summary.json
reports/stage66c_h64l_paper_execution_simulator/report.md
```

### Decision logic

```text
PAPER_SIM_READY:
  Stage66A concentration not fatal
  Stage66B rolling-origin acceptable
  paper simulator produces coherent risk outputs
  no broker/order path activated

PAPER_SIM_ONLY_SMALL_SIZE:
  thesis acceptable but path risk or concentration requires smallest sizing band

PAPER_SIM_DELAY:
  signal frequency is too low or no recent activation
  continue simulator readiness while Track E searches complementary thesis

RESEARCH_ONLY:
  concentration/rolling-origin results are too weak for simulation

KILL_OR_ARCHIVE:
  paper simulator cannot reproduce return logic or violates as-of/data rules
```

### Important boundary

Stage66C is not paper-order.

It is a no-order paper-execution simulator. It does not connect to broker. It does not place orders. It does not promote EA. It does not authorize live.

---

## 9. Track E — Stage66D limited complementary macro thesis program

### Objective

Solve the likely frequency gap without returning to uncontrolled intraday candidate hunting.

### Why this is needed

H64L may be strong but low-frequency. Waiting for H64L activation alone may leave the system idle. The correct response is not to overtrade intraday noise; it is to define a small number of complementary macro theses with shorter horizons.

### Constraint

Maximum number of new theses:

```text
2 to 4
```

No broad unrestricted megascan.

Each thesis must be pre-registered before testing.

### Candidate thesis families

#### Thesis 1 — DXY / real-yield divergence continuation

Market logic:

```text
Gold can continue higher when DXY weakens and real yields fall, even before ETF flows confirm.
```

Potential horizon:

```text
20d / 60d
```

#### Thesis 2 — Gold trend with macro-neutral filter

Market logic:

```text
When gold trend is strong but macro indicators are not fully aligned, a smaller trend allocation may still be justified.
```

Potential horizon:

```text
20d / 60d
```

#### Thesis 3 — ETF-flow reversal / confirmation thesis

Market logic:

```text
ETF flows may lag price. A shift from outflow to reduced outflow or inflow can confirm trend continuation.
```

Potential horizon:

```text
60d / 120d
```

#### Thesis 4 — volatility-regime breakout continuation

Market logic:

```text
Gold breakouts during volatility expansion may persist if real-yield and DXY conditions are not adverse.
```

Potential horizon:

```text
10d / 20d / 60d
```

### Required pre-registration format

For each thesis:

```text
thesis_id
market_logic
allowed_features
forbidden_features
signal_rule
horizon
benchmark
cost_assumption
asof_lag_rules
sample_period
validation_splits
pass_gate
fail_gate
kill_switch
```

### Anti-overfitting rules

```text
no more than 4 theses
no more than 3 variants per thesis
no post-hoc event filtering
no threshold tuning after seeing outcome
no reduced-scope rescue
no adding features after failure unless registered as a new thesis generation
```

### Decision output

```text
PROMOTE_TO_PAPER_SIM_CANDIDATE
KEEP_AS_RESEARCH_WATCH
KILL
```

This track runs in parallel. It must not delay Stage66A/B/C.

---

## 10. Track F — Governance redesign

### Objective

Replace the current one-dimensional “wait for 180 days and 5 signals” gate with a multi-level decision architecture.

### Current problem

The current gate:

```text
observed_new_signals_min: 5
calendar_span_min_days: 180
```

is reasonable as background evidence, but unreasonable as the main gate for a 120-day macro-regime thesis.

### Corrected gate architecture

#### Gate 1 — Research survivor acceptance

Purpose:

```text
Decide whether H64L remains the primary project thesis.
```

Evidence:

```text
Stage64R pass
Stage64N4 replication
Stage66A concentration audit
Stage66B rolling-origin replay
```

Possible decisions:

```text
PRIMARY_THESIS_ACCEPTED
PRIMARY_THESIS_ACCEPTED_SMALL_SIZE_ONLY
RESEARCH_WATCH_ONLY
KILL_OR_ARCHIVE
```

#### Gate 2 — Paper-simulation readiness

Purpose:

```text
Decide whether to run no-order paper-execution simulator.
```

Evidence:

```text
Stage66A not fatal
Stage66B not fatal
data freshness valid
asof lag safety valid
cost assumptions defined
```

Possible decisions:

```text
PAPER_SIM_READY_NO_ORDER
PAPER_SIM_READY_SMALL_SIZE_ONLY
PAPER_SIM_DELAY
RESEARCH_ONLY
```

#### Gate 3 — Paper-order readiness

Purpose:

```text
Decide whether a future actual paper-order/broker-sim pathway can be considered.
```

This is not automatically reached by Stage66.

Minimum requirements:

```text
paper simulator stable
risk metrics acceptable
data refresh reliable
broker-realism assumptions explicitly reviewed
human approval
external expert approval if requested
```

Possible decisions:

```text
PAPER_ORDER_DESIGN_ALLOWED
PAPER_ORDER_BLOCKED
```

#### Gate 4 — Micro-live readiness

Purpose:

```text
Potential future stage only; not part of immediate implementation.
```

Minimum requirements:

```text
paper-order pass
broker connection tested
risk cap approved
manual kill switch available
maximum exposure tiny
explicit user approval
```

Possible decisions:

```text
MICRO_LIVE_DESIGN_ALLOWED
MICRO_LIVE_BLOCKED
```

### Retained hard blocks for immediate Stage66

```text
NO_LIVE
NO_REAL_ORDER
NO_BROKER_CONNECTION
NO_EA_PROMOTION
NO_AUTOMATED_EXECUTION
NO_HISTORICAL_EVENT_FILTER
NO_POST_HOC_RESCUE
NO_THRESHOLD_TUNING
NO_REDUCED_SCOPE_RETEST
```

### Modified interpretation of Stage65 governance

The old 180-day/5-signal gate remains only as:

```text
BACKGROUND_FORWARD_EVIDENCE_GATE
```

It no longer controls the main project path.

---

## 11. Implementation package sequence

### Package 1 — Stage66A/B/F + Stage65 background correction

This is the first implementation package after approval.

Files expected:

```text
app/stage66a_h64l_concentration_audit.py
app/stage66b_h64l_rolling_origin_replay.py
app/stage66f_governance_dashboard.py
configs/stage66a_h64l_concentration_audit.json
configs/stage66b_h64l_rolling_origin_replay.json
configs/stage66f_governance_dashboard.json
.github/workflows/stage65_forward_shadow_daily.yml
docs/stage66_corrected_operational_path.md
```

Outputs expected:

```text
reports/stage66a_h64l_concentration_audit/summary.json
reports/stage66a_h64l_concentration_audit/report.md
reports/stage66b_h64l_rolling_origin_replay/summary.json
reports/stage66b_h64l_rolling_origin_replay/report.md
reports/stage66f_governance_dashboard/summary.json
reports/stage66f_governance_dashboard/report.md
```

Decision expected:

```text
PRIMARY_THESIS_ACCEPTED
PRIMARY_THESIS_ACCEPTED_SMALL_SIZE_ONLY
RESEARCH_WATCH_ONLY
KILL_OR_ARCHIVE
```

### Package 2 — Stage66C paper-execution simulator

Only after Package 1 output is reviewed.

Files expected:

```text
app/stage66c_h64l_paper_execution_simulator.py
configs/stage66c_h64l_paper_execution_simulator.json
docs/stage66c_paper_execution_rules.md
```

Outputs expected:

```text
data/paper_sim/stage66c_h64l_paper_trade_ledger.csv
data/paper_sim/stage66c_h64l_daily_mark_to_market.csv
reports/stage66c_h64l_paper_execution_simulator/summary.json
reports/stage66c_h64l_paper_execution_simulator/report.md
```

Decision expected:

```text
PAPER_SIM_READY_NO_ORDER
PAPER_SIM_READY_SMALL_SIZE_ONLY
PAPER_SIM_DELAY
RESEARCH_ONLY
```

### Package 3 — Stage66D limited complementary thesis program

Can run in parallel after Package 1 starts.

Files expected:

```text
app/stage66d_limited_macro_thesis_preregistration.py
app/stage66d_limited_macro_thesis_scan.py
configs/stage66d_limited_macro_thesis_registry.json
docs/stage66d_limited_macro_thesis_rules.md
```

Outputs expected:

```text
reports/stage66d_limited_macro_thesis_scan/summary.json
reports/stage66d_limited_macro_thesis_scan/report.md
```

Decision expected:

```text
PROMOTE_TO_PAPER_SIM_CANDIDATE
KEEP_AS_RESEARCH_WATCH
KILL
```

---

## 12. Practical time-to-decision target

The corrected plan should target fast decision cycles.

### Immediate decision cycle

```text
Stage66A concentration audit: same day after implementation
Stage66B rolling-origin replay: same day or next implementation cycle
Stage66F governance dashboard: same package
```

Goal:

```text
Within 1–2 execution cycles, decide whether H64L is:
  primary thesis,
  primary thesis but small-size only,
  research watch,
  or killed/archived.
```

### Next decision cycle

```text
Stage66C paper-execution simulator: after Stage66A/B review
```

Goal:

```text
Within the next implementation cycle, decide whether no-order paper simulation is ready.
```

### Parallel decision cycle

```text
Stage66D limited thesis program
```

Goal:

```text
Within one implementation cycle, produce a shortlist or kill all complementary theses.
```

This is materially faster than waiting 180 days.

---

## 13. Expected expert approval questions

Please review and approve or correct the following items.

### 13.1 Strategic correction

Is it correct to demote Stage65 from main path to background telemetry while keeping it active for evidence collection?

### 13.2 H64L treatment

Is it correct to treat H64L as the primary thesis candidate now, subject to immediate concentration and rolling-origin audit, rather than waiting for 180 days of new forward ledger?

### 13.3 Concentration audit

Are the proposed concentration metrics sufficient?

Key metrics:

```text
top episode share
top year share
top split share
leave-one-episode-out
leave-one-year-out
median vs mean
trimmed mean
episode-level return distribution
path drawdown
MFE/MAE
```

### 13.4 Rolling-origin replay

Is rolling-origin / forward-like historical replay a valid substitute for the main decision value that Stage65 was incorrectly expected to provide over 180 days?

### 13.5 Paper simulation

Is it acceptable to move to no-order paper-execution simulation after Stage66A/B, provided no broker connection and no real order are enabled?

### 13.6 Micro-live boundary

Should micro-live remain outside the immediate implementation plan until paper simulation and a later explicit governance gate pass?

Recommended answer from this plan:

```text
Yes. Micro-live should remain future-only.
Immediate path should be paper-simulation, not broker/live.
```

### 13.7 Complementary theses

Is the 2–4 thesis cap strict enough to prevent a return to uncontrolled candidate hunting?

### 13.8 Gate redesign

Do the proposed gates better match the project objective?

```text
Gate 1: primary thesis acceptance
Gate 2: paper-simulation readiness
Gate 3: paper-order readiness
Gate 4: micro-live readiness
Stage65 180d/5-signal gate: background evidence only
```

---

## 14. My recommended approval wording

If the expert agrees, the approval can be phrased as:

```text
Approved with the following interpretation:
Stage65 remains active only as background forward telemetry.
The main path moves immediately to Stage66A concentration audit, Stage66B rolling-origin replay, and Stage66F governance redesign.
If Stage66A/B do not show fatal concentration or forward-like replay failure, Stage66C no-order paper-execution simulator is allowed.
No broker connection, no real order, no EA promotion, no paper-live/live are allowed at this stage.
Complementary thesis work is allowed only under strict pre-registration with a maximum of 2–4 thesis families.
The 180-day/5-signal Stage65 gate is retained only as background evidence, not as the main project blocker.
```

---

## 15. Bottom-line recommendation

Proceed to implementation only after this corrected plan is approved.

The next implementation should not be another daily-ledger patch. It should be:

```text
Stage66A + Stage66B + Stage66F + Stage65 background workflow correction
```

This package is the fastest safe way out of the current bottleneck because it extracts decision value from existing data, tests the main concentration risk, preserves governance, and moves the project toward paper-execution readiness without touching broker/live execution.

