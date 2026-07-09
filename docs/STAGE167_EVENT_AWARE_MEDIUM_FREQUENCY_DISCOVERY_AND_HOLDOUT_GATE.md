# Stage167 Event-Aware Medium-Frequency Discovery and Holdout Gate

## Decision

Stage167 is not another forward-waiting stage.

It is a commercial kill/keep gate for event-aware medium-frequency rules. Its purpose is to prevent the recurring project failure mode:

- low-frequency rule,
- weak win rate or weak edge,
- recommendation to wait for more samples,
- eventual pivot after wasting time.

If a rule cannot produce enough samples and cannot pass the newest holdout segment after cost/slippage, it is killed.

## How it works

1. Reads AMarkets broker M5 bars.
2. Reads Stage166 current-event shock overlay if available.
3. Builds features: momentum, ATR/range, wick/body, session, event long/short pressure, shock regime.
4. Locks the newest 20% of bars as holdout and computes all thresholds only on train.
5. Scans event-aware medium-frequency rule families across 30m, 1h, 2h, 4h, and 8h horizons.
6. Applies cost/spread/slippage proxy.
7. Keeps only candidates that pass both train and holdout frequency, mean return, hit-rate, and left-tail gates.

## What it outputs

Runtime directory:

`reports/stage167_event_aware_medium_frequency_discovery_and_holdout_gate/`

Key outputs:

- `stage167_event_aware_holdout_gate_summary.json`
- `stage167_all_rule_scores.csv`
- `stage167_commercial_shortlist.csv`
- `stage167_all_rule_trades.csv`
- `stage167_top_rule_trades.csv`
- `stage167_train_thresholds.json`
- `stage167_holdout_map.json`
- `stage167_decision.md`

## How to interpret the result

If `commercial_shortlist_count = 0`, do not wait for more forward samples. The correct action is to kill or redesign the rule space.

If `commercial_shortlist_count > 0`, do not release demo orders yet. The next stage must run a costed execution replay and operational risk check before any demo routing.

## Default commercial gates

- Minimum train events: 150
- Minimum holdout events: 30
- Minimum train mean net bps: 1.5
- Minimum holdout mean net bps: 0.5
- Minimum train hit rate: 51.5%
- Minimum holdout hit rate: 50.5%
- Holdout p10 floor: -35 bps
- Max event-spike dependency: 55%

These defaults are deliberately stricter than a research scan but still permissive enough for medium-frequency discovery.

## Safety

Stage167 is read-only:

- `order_routing_allowed = false`
- `demo_release_allowed = false`

It does not write MT5 files and does not authorize live/demo orders.
