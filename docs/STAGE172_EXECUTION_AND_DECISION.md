# Stage172 — Dual-Track Decision Audit

## Scope

This package executes one read-only decision stage:

- Track A: exact H64L rule, historical-as-of, final 20% holdout, episode/frequency/cost/drawdown/concentration/drift comparison, ending only in `KILL`, `OVERLAY_ONLY`, or `SHADOW_CANDIDATE`.
- Track B: exactly three fixed baseline families on AMarkets M5/H1, long and short evaluated separately. No broad scan and no parameter search.

The package never routes orders and does not alter Stage171 scheduling or feature materialization.

## Important governance limitation

The exact H64L conditions are locked, but the archived rule-lock artifact supplied to Stage172 does not lock a holding horizon. Stage172 therefore declares a fixed 20-trading-day decision horizon in config. This is a governance assumption, not an optimized parameter. If authoritative archive evidence establishes another original horizon, change it once, record the evidence path/hash, and rerun the full audit; do not compare several horizons and select the best.

## Required inputs

Auto-discovery checks the configured paths for:

- AMarkets M5 and H1 OHLC;
- a historical H64L feature table containing the four exact feature columns and a date;
- preferably `available_after_utc` or equivalent;
- optional news calendar for ±60-minute blackout.

If the historical H64L table lacks availability timestamps, the configured conservative ETF release lag is applied and disclosed. A missing/invalid H64L source blocks Track A rather than manufacturing a result.

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m unittest tests/test_stage172_dual_track_decision_audit.py
python3 app/stage172_dual_track_decision_audit.py \
  --root ~/Desktop/xauusd-trader \
  --config configs/stage172_dual_track_decision_audit.json
```

Expected primary outputs:

```text
reports/stage172_dual_track_decision_audit/stage172_summary.json
reports/stage172_dual_track_decision_audit/stage172_decision.md
reports/stage172_dual_track_decision_audit/stage172_track_a_h64l_episodes.csv
reports/stage172_dual_track_decision_audit/stage172_track_b_baseline_trades.csv
```

A process exit code of `2` means fail-closed because required data or schema was unavailable. It is not permission to relax gates.

## Kill gates

### Track A

`INCONCLUSIVE_BLOCKED` if the historical-as-of feature source is missing or cannot be validated. This is not a statistical kill.

`KILL` only after Track A executes and any of these holds:

- fewer than 5 independent holdout episodes;
- holdout net expectancy below 3 bps per episode;
- does not beat same-horizon gold drift.

`OVERLAY_ONLY` if core edge gates pass but annual frequency is below 6, drawdown exceeds 350 bps, or year/regime concentration exceeds limits.

`SHADOW_CANDIDATE` only if every gate passes. This still authorizes log-only shadowing, not paper orders.

### Track B

Each direction of each family must independently pass all gates:

- at least 30 holdout trades;
- net expectancy ≥ 0.5 bps after cost/slippage;
- profit factor ≥ 1.05;
- drawdown ≤ 600 bps;
- no single year >55% of trades;
- no single session >70% of trades.

If no baseline survives, ML is forbidden and only the exact tested formulations are killed; the result must not be generalized to every possible formulation in the family. If one survives, any later supervised model may only act as an ON/OFF filter around that locked baseline.

## Fixed baseline definitions

1. H1 SMA50/SMA200 trend plus M5 EMA20 pullback/reclaim.
2. London/NY 12-bar range continuation in the H1 trend direction.
3. M5 volatility expansion (`range > 1.5×ATR14`, `ATR14 > 1.25×96-bar median`) with ±60-minute news blackout, as-of DXY/real-yield non-opposition, and non-opposing H1 trend. If either macro series or the news calendar is unavailable, this family is blocked rather than evaluated unguarded.

These are fixed hypotheses, not a grid.
