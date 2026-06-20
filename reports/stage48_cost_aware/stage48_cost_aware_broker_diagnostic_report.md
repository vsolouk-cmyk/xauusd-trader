# Stage48 Cost-Aware Broker Diagnostic

- status: `COST_AWARE_DIAGNOSTIC_COMPLETE_NO_PROMOTION`
- next_allowed_step: `ARCHIVE_COST_AWARE_DIAGNOSTIC_NO_PROMOTION`
- promotion: `NO_GO`
- EA: `NO_GO`
- paper_live: `NO_GO`
- live: `NO_GO`

## Inputs

- broker_csv: `/Users/vahid/Downloads/amarkets_xauusd_5m.csv`
- cost_model: `reports/stage48f/stage48f_cost_model.json`
- selected_broker_time_offset_hours: `3.0`
- recommended_cost_bps: `2.9501`
- stress_cost_bps: `2.9820`
- extreme_cost_bps: `3.0380`

## Coverage

- broker_rows: `292435`
- broker_coverage_days: `1509.329861111111`
- trade_count: `387471`
- candidate_count: `27`
- diagnostic_survivor_count: `0`

## Top candidates

- `S48_COST_LB72_H48_SW30` trades=8681 oos_trades=1548 stress_mean=-3.8757 oos_stress_mean=-0.6653739298993229 decision=`NO_PASS` notes=`oos_stress_mean_not_positive;oos_stress_win_rate_lt_52pct`
- `S48_COST_LB72_H48_SW20` trades=10597 oos_trades=1629 stress_mean=-3.9139 oos_stress_mean=-1.312064670792121 decision=`NO_PASS` notes=`oos_stress_mean_not_positive;oos_stress_win_rate_lt_52pct`
- `S48_COST_LB72_H48_SW10` trades=13249 oos_trades=1735 stress_mean=-4.0433 oos_stress_mean=-1.3891298172218771 decision=`NO_PASS` notes=`oos_stress_mean_not_positive;oos_stress_win_rate_lt_52pct`
- `S48_COST_LB72_H24_SW30` trades=8686 oos_trades=1553 stress_mean=-3.9349 oos_stress_mean=-1.4924598393400104 decision=`NO_PASS` notes=`oos_stress_mean_not_positive;oos_stress_win_rate_lt_52pct`
- `S48_COST_LB72_H24_SW10` trades=13255 oos_trades=1741 stress_mean=-3.7267 oos_stress_mean=-1.8478954229920603 decision=`NO_PASS` notes=`oos_stress_mean_not_positive;oos_stress_win_rate_lt_52pct`
- `S48_COST_LB72_H24_SW20` trades=10602 oos_trades=1634 stress_mean=-3.9518 oos_stress_mean=-1.9235280849889402 decision=`NO_PASS` notes=`oos_stress_mean_not_positive;oos_stress_win_rate_lt_52pct`
- `S48_COST_LB48_H48_SW30` trades=10556 oos_trades=1911 stress_mean=-4.1169 oos_stress_mean=-2.167123388502037 decision=`NO_PASS` notes=`oos_stress_mean_not_positive;oos_stress_win_rate_lt_52pct`
- `S48_COST_LB48_H48_SW10` trades=16407 oos_trades=2169 stress_mean=-3.9821 oos_stress_mean=-2.7218175325601743 decision=`NO_PASS` notes=`oos_stress_mean_not_positive;oos_stress_win_rate_lt_52pct`
- `S48_COST_LB48_H48_SW20` trades=13016 oos_trades=2024 stress_mean=-4.1209 oos_stress_mean=-2.7481701010745425 decision=`NO_PASS` notes=`oos_stress_mean_not_positive;oos_stress_win_rate_lt_52pct`
- `S48_COST_LB72_H12_SW30` trades=8689 oos_trades=1556 stress_mean=-3.3610 oos_stress_mean=-3.0417916485999443 decision=`NO_PASS` notes=`oos_stress_mean_not_positive;oos_stress_win_rate_lt_52pct`

## Interpretation

This is a broker-real, cost-aware diagnostic using the Stage48F cost model. It does not authorize promotion, EA, paper-live, or live trading. If survivors exist, they require a separate hard audit; if none exist, archive this diagnostic.
