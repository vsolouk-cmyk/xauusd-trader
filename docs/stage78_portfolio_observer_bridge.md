# Stage78 Portfolio Observer Bridge

Purpose: convert the Stage77B selected portfolio into an observer-only MT5 bridge.

Selected portfolio expected from Stage77B:

- `K06_RESILIENT_GOLD_VS_DXY_H120`
- `K03_SAFE_HAVEN_REALYIELD_H120`
- `K07_DXY_TREND_RELIEF_GOLD_TREND_H120`

The stage writes:

```text
data/mt5_bridge/portfolio_observer_signal.csv
```

The companion EA only reads and displays/logs the CSV. It does not include trade-sending calls and does not authorize execution.

Run:

```bash
python3 app/stage78_portfolio_observer_bridge.py \
  --root . \
  --config configs/stage78_portfolio_observer_bridge.json \
  --out reports/stage78_portfolio_observer_bridge
```
