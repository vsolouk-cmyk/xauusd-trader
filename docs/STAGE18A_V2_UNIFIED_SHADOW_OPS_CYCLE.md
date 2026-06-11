# Stage 18A v2 Unified Shadow Ops Cycle

Stage18A v2 is the preferred manual runner.

It does:

```text
1. Import AMarkets CSVs once.
2. Run Stage16C true-forward shadow collector.
3. Run Stage17D broker-time PDH breakout collector.
4. Run Stage18E broker-time shortlist collector.
5. Produce one consolidated dashboard.
```

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage18a_unified_shadow_ops_cycle
cat data/reports/stage18a_unified_shadow_ops_cycle/stage18a_unified_shadow_ops_cycle.md
```

## Default files

```text
~/Downloads/amarkets_xauusd_1h.csv
~/Downloads/amarkets_xauusd_1m.csv
```

## Hard rule

Research shadow operations only:

```text
No EA change
No automatic trading
No paper/live authorization
No direct conversion to order
```
