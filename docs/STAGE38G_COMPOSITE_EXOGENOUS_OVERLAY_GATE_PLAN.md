# STAGE38G — Composite Exogenous Overlay Gate Plan

## Purpose

Stage38G tests whether independent exogenous contexts can jointly improve event-clock performance.

Inputs:

- GLD/SPDR ETF flow context from Stage38F
- Macro/risk context from Stage38E
- COT context from Stage38B, if available

This is a read-only diagnostic. It is not a strategy and does not authorize paper/live trading.

## Why this stage exists

Individual modules produced useful but non-promotable signals:

```text
COT overlay = marginal / not promotable
Macro gate = watch-only / not promotable
GLD gate = watch-only / not promotable
```

The only defensible next test is a restricted composite overlay that checks whether weak independent filters combine into a meaningful avoid-long or long-permission context.

## Anti-overfitting constraint

Stage38G must not search arbitrary combinations.

It should only test pre-declared, economically interpretable policies:

1. Block GLD 20D outflow
2. Block GLD ETF outflow or 20D outflow
3. Block macro-hostile context
4. Block GLD-or-macro-hostile context
5. Block broad exogenous hostile context
6. Long only when GLD supportive and macro not hostile
7. Long only when GLD supportive and VIX is rising
8. Long only when GLD supportive and COT is not hostile, if COT state is available

No brute-force threshold search is allowed.

## Promotion criteria

A composite overlay is still not enough for Stage39. It can only become a baseline-context candidate if it passes all of the following:

```text
uplift_vs_baseline_event_clock_mean_bps >= +8 bps
worst_leave_one_year_out_event_clock_mean_bps > 0
positive_year_count >= 4
max_positive_year_share <= 0.55
trade_count >= 150 for 72H/120H overlays
no lookahead violations
```

If these fail, Stage38G is archived and the project should pivot away from exogenous-only overlays.

## Output tables

```text
stage38g_exogenous_composite_gate_events
stage38g_exogenous_composite_gate_summary
stage38g_exogenous_composite_gate_audit
```

## Final safety status

```text
Stage39 / EA / paper-live / live = NO-GO
```
