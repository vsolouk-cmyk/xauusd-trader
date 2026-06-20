# Stage49 Broker-Real Multi-Timeframe Trend Persistence Thesis

- status: `MULTITF_THESIS_DIAGNOSTIC_SURVIVORS_NEED_AUDIT_NO_PROMOTION`
- next_allowed_step: `HARD_AUDIT_SURVIVORS_NO_PROMOTION`
- promotion: `NO_GO`
- EA: `NO_GO`
- paper_live: `NO_GO`
- live: `NO_GO`

## Thesis

H1 range-expansion bars may show short-horizon directional persistence when M15 and M5 are aligned with the same direction and entry spread is below the broker-real cost gate.
This is not a liquidity-sweep reversal thesis and does not reuse the failed Stage47/48 rescue path.

## Inputs

- M5 rows: `292435`
- M15 rows: `97529`
- H1 rows: `24404`
- stress_cost_bps: `2.9820`
- max_spread_cost_bps: `3.0380`

## Top candidates

- `S49_MTF_H1W72_P85_M15S40_M5S20_H48` trades=`1728` oos_trades=`346` stress_mean=`26.7772` oos_stress_mean=`44.4752` decision=`DIAGNOSTIC_SURVIVOR_NEEDS_HARD_AUDIT` notes=``
- `S49_MTF_H1W120_P85_M15S40_M5S20_H48` trades=`1826` oos_trades=`366` stress_mean=`25.9713` oos_stress_mean=`42.8504` decision=`DIAGNOSTIC_SURVIVOR_NEEDS_HARD_AUDIT` notes=``
- `S49_MTF_H1W120_P85_M15S20_M5S20_H48` trades=`1978` oos_trades=`396` stress_mean=`26.0592` oos_stress_mean=`42.4376` decision=`DIAGNOSTIC_SURVIVOR_NEEDS_HARD_AUDIT` notes=``
- `S49_MTF_H1W72_P85_M15S20_M5S20_H48` trades=`1877` oos_trades=`376` stress_mean=`26.2913` oos_stress_mean=`42.2632` decision=`DIAGNOSTIC_SURVIVOR_NEEDS_HARD_AUDIT` notes=``
- `S49_MTF_H1W72_P85_M15S40_M5S20_H24` trades=`1729` oos_trades=`346` stress_mean=`25.4407` oos_stress_mean=`42.1313` decision=`DIAGNOSTIC_SURVIVOR_NEEDS_HARD_AUDIT` notes=``
- `S49_MTF_H1W72_P85_M15S20_M5S20_H24` trades=`1878` oos_trades=`376` stress_mean=`25.1922` oos_stress_mean=`41.0344` decision=`DIAGNOSTIC_SURVIVOR_NEEDS_HARD_AUDIT` notes=``
- `S49_MTF_H1W120_P85_M15S40_M5S20_H24` trades=`1827` oos_trades=`366` stress_mean=`25.1850` oos_stress_mean=`40.7054` decision=`DIAGNOSTIC_SURVIVOR_NEEDS_HARD_AUDIT` notes=``
- `S49_MTF_H1W120_P85_M15S20_M5S20_H24` trades=`1979` oos_trades=`396` stress_mean=`24.9583` oos_stress_mean=`40.2726` decision=`DIAGNOSTIC_SURVIVOR_NEEDS_HARD_AUDIT` notes=``
- `S49_MTF_H1W72_P85_M15S40_M5S20_H12` trades=`1730` oos_trades=`346` stress_mean=`25.2911` oos_stress_mean=`39.3792` decision=`DIAGNOSTIC_SURVIVOR_NEEDS_HARD_AUDIT` notes=``
- `S49_MTF_H1W120_P85_M15S40_M5S20_H12` trades=`1828` oos_trades=`366` stress_mean=`24.8245` oos_stress_mean=`38.0458` decision=`DIAGNOSTIC_SURVIVOR_NEEDS_HARD_AUDIT` notes=``

## Interpretation

This is a cost-aware diagnostic only. Survivors, if any, require hard audit before any further consideration. No EA, paper-live, live trading, or promotion is authorized.
