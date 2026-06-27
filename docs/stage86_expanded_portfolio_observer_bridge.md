# Stage86 Expanded Portfolio Observer Bridge

Stage86 expands the MT5 observer-only portfolio from the Stage77B three-rule set to the Stage85 five-rule set:

- `K06_RESILIENT_GOLD_VS_DXY_H120`
- `K03_SAFE_HAVEN_REALYIELD_H120`
- `K07_DXY_TREND_RELIEF_GOLD_TREND_H120`
- `S83_14_REALYIELD_120D_DOWN_GOLD_NOT_TRENDING_H120`
- `S83_13_DXY_120D_DOWN_GOLD_NOT_TRENDING_H120`

The bridge writes `data/mt5_bridge/portfolio_observer_signal.csv` in key/value schema for the observer EA.

## Hard blocks

- No automated order
- No paper order
- No broker connection
- No live
- No order authorization
- Observer display only

## Operator notes

The EA file changes only because the display list expands from three rules to five rules. It still has no execution path and refuses to initialize if its execution flag is set.
