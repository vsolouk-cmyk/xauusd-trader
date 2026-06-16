# Stage38B / T3 COT Overlay Gate Review

**Project:** XAUUSD / Gold Trading System  
**Stage:** Stage38B / T3 COT data foundation  
**Input:** `cot_gold_t3_overlay_gate_summary`, `cot_gold_t3_overlay_gate_audit`  
**Status:** `PASS_WITH_CAUTION`  
**Decision:** `PROCEED_TO_RESTRICTED_BASELINE_OVERLAY_RETEST_WITH_CAUTION`  
**Execution status:** `NO_GO` for Stage39 / EA / paper-live / live order

---

## 1. Purpose

This review records the result of the restricted COT overlay gate after the Stage38B interaction diagnostic.

The gate was deliberately narrow. It did **not** create a strategy, optimize entries, train a model, or justify any live/paper execution. It tested only whether three pre-declared COT × ATR regimes have enough risk/regime value to justify a restricted baseline-overlay retest.

---

## 2. Audit Result

```text
audit_status = PASS
decision = PROCEED_TO_RESTRICTED_BASELINE_OVERLAY_RETEST_WITH_CAUTION
source_event_rows = 429
events_written = 429
summary_rows_written = 58
warning_count = 0
note_count = 6
```

The audit is technically clean. However, the result is not strong enough to promote T3 into a standalone strategy.

---

## 3. Pre-declared Overlay Rules

The gate tested only these rules:

```text
AVOID_LONG_HOSTILE:
    cot_state == MM_SHORT_CROWDED
    atr_bucket == ATR_EXPANSION
    expected role = avoid-long / hostile long regime

SQUEEZE_DO_NOT_SHORT:
    cot_state == MM_EXTREME_SHORT
    atr_bucket == ATR_EXPANSION
    expected role = squeeze-risk / do-not-short regime

LOW_CONVICTION_BLOCK:
    cot_state == MM_NEUTRAL
    atr_bucket == ATR_LOW
    expected role = low-conviction / no-trade regime
```

The resulting long-side policy is:

```text
LONG_BLOCKED if AVOID_LONG_HOSTILE or LOW_CONVICTION_BLOCK
LONG_PERMITTED otherwise
```

The short-side caution is:

```text
SHORT_BLOCKED if SQUEEZE_DO_NOT_SHORT
```

---

## 4. Primary 120H Findings

```text
ALL:
    sample_count = 215
    mean_after_stress_cost = +36.97 bps
    win_rate_long = 0.572
    year concentration = acceptable

LONG_PERMITTED:
    sample_count = 191
    mean_after_stress_cost = +43.22 bps
    win_rate_long = 0.576
    max_positive_year_share = 0.580

LONG_BLOCKED:
    sample_count = 24
    mean_after_stress_cost = -12.82 bps
    win_rate_long = 0.542
    max_positive_year_share = 0.825
    note = YEAR_CONCENTRATED

AVOID_LONG_HOSTILE:
    sample_count = 11
    mean_after_stress_cost = -21.28 bps
    median = -37.79 bps
    win_rate_long = 0.455
    note = YEAR_CONCENTRATED

LOW_CONVICTION_BLOCK:
    sample_count = 13
    mean_after_stress_cost = -5.66 bps
    median = +12.24 bps
    win_rate_long = 0.615

SQUEEZE_DO_NOT_SHORT:
    sample_count = 10
    mean_after_stress_cost = +147.48 bps
    median = +163.55 bps
    win_rate_long = 0.800
    note = YEAR_CONCENTRATED
```

Interpretation:

- `LONG_PERMITTED` is better than `ALL`, but only moderately.
- `LONG_BLOCKED` is weaker than `LONG_PERMITTED`, supporting the gate direction.
- `AVOID_LONG_HOSTILE` is the cleaner negative long-side regime.
- `LOW_CONVICTION_BLOCK` is weaker than average but not a clean block on its own.
- `SQUEEZE_DO_NOT_SHORT` is strong but has only 10 samples and is year-concentrated.

---

## 5. Primary 240H Findings

```text
ALL:
    sample_count = 214
    mean_after_stress_cost = +82.52 bps
    win_rate_long = 0.589
    year concentration = acceptable

LONG_PERMITTED:
    sample_count = 190
    mean_after_stress_cost = +96.88 bps
    win_rate_long = 0.616
    max_positive_year_share = 0.565

LONG_BLOCKED:
    sample_count = 24
    mean_after_stress_cost = -31.14 bps
    win_rate_long = 0.375
    max_positive_year_share = 0.773
    note = YEAR_CONCENTRATED

AVOID_LONG_HOSTILE:
    sample_count = 11
    mean_after_stress_cost = -49.52 bps
    median = -90.40 bps
    win_rate_long = 0.273
    note = YEAR_CONCENTRATED

LOW_CONVICTION_BLOCK:
    sample_count = 13
    mean_after_stress_cost = -15.59 bps
    median = -3.52 bps
    win_rate_long = 0.462
    note = YEAR_CONCENTRATED

SQUEEZE_DO_NOT_SHORT:
    sample_count = 10
    mean_after_stress_cost = +256.22 bps
    median = +285.42 bps
    win_rate_long = 0.800
    note = YEAR_CONCENTRATED
```

Interpretation:

- The 240H horizon is more favorable than 120H.
- `LONG_PERMITTED` improves over `ALL` on trade-level mean and win rate.
- `LONG_BLOCKED` is meaningfully hostile for long exposure.
- `AVOID_LONG_HOSTILE` is the strongest avoid-long component.
- `LOW_CONVICTION_BLOCK` is directionally supportive but weaker.
- `SQUEEZE_DO_NOT_SHORT` remains the strongest squeeze-risk warning, but it is not tradable as a standalone long signal due to low sample count and year concentration.

---

## 6. Critical Limitations

```text
1. The improvement of LONG_PERMITTED over ALL is real but not large.
2. The blocked regimes are only 24 events at each primary horizon.
3. Several subgroups are YEAR_CONCENTRATED.
4. SQUEEZE_DO_NOT_SHORT has only 10 events.
5. This is event-level weekly COT logic, not an intraday entry system.
6. The result does not justify Stage39, EA, paper-live, or live order.
```

The COT overlay is useful as a **risk/regime gate**, not as a trading engine.

---

## 7. Locked Decision

```text
T3_COT_OVERLAY_GATE_STATUS = PASS_WITH_CAUTION
T3_STANDALONE_SIGNAL = NO_GO
T3_INTRADAY_ENTRY_SIGNAL = NO_GO
T3_x_T1_STRUCTURAL = NO_GO
T3_COT_ATR_OVERLAY = PROCEED_TO_RESTRICTED_BASELINE_OVERLAY_RETEST_WITH_CAUTION
STAGE39 = NO_GO
EA = NO_GO
PAPER_LIVE = NO_GO
LIVE_ORDER = NO_GO
```

---

## 8. Next Step

Create and run:

```text
app/stage38b_restricted_baseline_overlay_retest.py
```

The retest must compare:

```text
BASELINE_ALWAYS_LONG
vs
OVERLAY_LONG_PERMITTED_ONLY
vs
component overlays:
    AVOID_LONG_HOSTILE_ONLY
    LOW_CONVICTION_BLOCK_ONLY
    SQUEEZE_LONG_ONLY diagnostic watch
```

The primary comparison must use event-level COT release windows, not all repeated H1 rows.

---

## 9. Kill / Proceed Criteria

Proceed only if the restricted retest shows:

```text
1. LONG_PERMITTED improves event-clock return after stress cost vs ALL.
2. Improvement is visible on both 120H and 240H.
3. Improvement is not dominated by one year.
4. Blocked regimes have worse mean/median or worse win rate than permitted regimes.
5. Drawdown proxy improves or does not deteriorate.
```

Kill or downgrade if:

```text
1. Improvement is marginal after zero-return skipped windows.
2. Benefit comes only from one narrow year.
3. The overlay only improves trade-level averages but not event-clock results.
4. The rule is mainly a restatement of 2025 expansion behavior.
```
