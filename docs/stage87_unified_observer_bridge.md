# Stage87 Unified Observer Bridge

## Purpose
Stage87 consolidates the previous single K06 observer and expanded portfolio observer into one observer-only bridge:

- one CSV: `data/mt5_bridge/unified_observer_signal.csv`
- one EA: `mt5/Unified_ObserverOnly_EA.mq5`

The unified observer includes the primary K06 status plus the full five-rule observer portfolio:

- K06
- K03
- K07
- S83_14
- S83_13

## Governance
Stage87 is display/telemetry only. It does not authorize orders, broker connection, paper-live, live, EA promotion, threshold tuning, or automated execution.

## Lock
Stage87 requires Stage85 disposition:

`PORTFOLIO_INCREMENT_SELECTED_FOR_STAGE86_OBSERVER_EXPANSION`

## Output
The bridge CSV is written as key/value rows so MT5 can read it safely from `MQL5/Files`.

## Operator flow
Run Stage87 after macro refresh and after the Stage85/Stage86 selection state is present. Copy only `unified_observer_signal.csv` to MT5 `MQL5/Files` unless auto-copy is wired later.

EA files are not daily artifacts. Replace/compile the EA only when the EA source changes.
