# Stage49 MultiTF Trend Persistence Hard Audit

- status: `HARD_AUDIT_COMPLETE_NO_PASS_NO_PROMOTION`
- next_allowed_step: `ARCHIVE_OR_REDESIGN_THESIS_NO_PROMOTION`
- promotion: `NO_GO`
- EA: `NO_GO`
- paper_live: `NO_GO`
- live: `NO_GO`

## Inputs

- db: `/Users/vahid/Desktop/xauusd-trader/data/broker_normalized/amarkets_multitf.sqlite`
- candidates_csv: `/Users/vahid/Desktop/xauusd-trader/reports/stage49_broker_multitf/stage49_multitf_trend_persistence_candidates.csv`
- cost_model: `/Users/vahid/Desktop/xauusd-trader/reports/stage48f/stage48f_cost_model.json`
- stress_cost_bps: `2.9820`

## Result

- diagnostic_candidates_loaded: `24`
- audited_candidates: `24`
- hard_audit_pass_count: `0`

## Top audited candidates

- `S49_MTF_H1W72_P85_M15S40_M5S20_H48` trades=2921 mean=-0.1794 oos_mean=9.3991 decl_mean=-0.4180 x2_mean=-3.1614 decision=`HARD_AUDIT_NO_PASS` notes=`mean_not_positive;win_rate_lt_52pct;oos_win_rate_lt_52pct;has_negative_year;worst_chrono_fold_not_positive;cost_x1_5_mean_not_positive;cost_x2_mean_not_positive;declustered_mean_not_positive;declustered_win_rate_lt_52pct;short_direction_mean_not_positive`
- `S49_MTF_H1W72_P85_M15S20_M5S20_H48` trades=3148 mean=-0.7818 oos_mean=7.3470 decl_mean=-1.2771 x2_mean=-3.7639 decision=`HARD_AUDIT_NO_PASS` notes=`mean_not_positive;win_rate_lt_52pct;oos_win_rate_lt_52pct;has_negative_year;worst_chrono_fold_not_positive;cost_x1_5_mean_not_positive;cost_x2_mean_not_positive;declustered_mean_not_positive;declustered_win_rate_lt_52pct;short_direction_mean_not_positive`
- `S49_MTF_H1W120_P85_M15S40_M5S20_H48` trades=2922 mean=-0.9963 oos_mean=6.9738 decl_mean=-1.2677 x2_mean=-3.9783 decision=`HARD_AUDIT_NO_PASS` notes=`mean_not_positive;win_rate_lt_52pct;oos_win_rate_lt_52pct;has_negative_year;worst_chrono_fold_not_positive;cost_x1_5_mean_not_positive;cost_x2_mean_not_positive;declustered_mean_not_positive;declustered_win_rate_lt_52pct;short_direction_mean_not_positive;long_direction_mean_not_positive`
- `S49_MTF_H1W120_P75_M15S40_M5S20_H48` trades=4555 mean=-1.1159 oos_mean=5.7070 decl_mean=-0.6800 x2_mean=-4.0979 decision=`HARD_AUDIT_NO_PASS` notes=`mean_not_positive;win_rate_lt_52pct;oos_win_rate_lt_52pct;has_negative_year;worst_chrono_fold_not_positive;cost_x1_5_mean_not_positive;cost_x2_mean_not_positive;declustered_mean_not_positive;declustered_win_rate_lt_52pct;short_direction_mean_not_positive;long_direction_mean_not_positive`
- `S49_MTF_H1W120_P85_M15S20_M5S20_H48` trades=3157 mean=-1.6924 oos_mean=3.7783 decl_mean=-2.3394 x2_mean=-4.6745 decision=`HARD_AUDIT_NO_PASS` notes=`mean_not_positive;win_rate_lt_52pct;oos_win_rate_lt_52pct;has_negative_year;worst_chrono_fold_not_positive;cost_x1_5_mean_not_positive;cost_x2_mean_not_positive;declustered_mean_not_positive;declustered_win_rate_lt_52pct;long_direction_mean_not_positive;short_direction_mean_not_positive`
- `S49_MTF_H1W72_P85_M15S40_M5S20_H24` trades=2923 mean=-1.5222 oos_mean=3.5135 decl_mean=-1.2579 x2_mean=-4.5043 decision=`HARD_AUDIT_NO_PASS` notes=`mean_not_positive;win_rate_lt_52pct;oos_win_rate_lt_52pct;has_negative_year;worst_chrono_fold_not_positive;cost_x1_5_mean_not_positive;cost_x2_mean_not_positive;declustered_mean_not_positive;declustered_win_rate_lt_52pct;long_direction_mean_not_positive;short_direction_mean_not_positive`
- `S49_MTF_H1W120_P75_M15S20_M5S20_H48` trades=4954 mean=-1.6639 oos_mean=3.2603 decl_mean=-1.4511 x2_mean=-4.6459 decision=`HARD_AUDIT_NO_PASS` notes=`mean_not_positive;win_rate_lt_52pct;oos_win_rate_lt_52pct;has_negative_year;worst_chrono_fold_not_positive;cost_x1_5_mean_not_positive;cost_x2_mean_not_positive;declustered_mean_not_positive;declustered_win_rate_lt_52pct;short_direction_mean_not_positive;long_direction_mean_not_positive`
- `S49_MTF_H1W72_P75_M15S40_M5S20_H48` trades=4566 mean=-1.8511 oos_mean=3.1006 decl_mean=-1.3291 x2_mean=-4.8331 decision=`HARD_AUDIT_NO_PASS` notes=`mean_not_positive;win_rate_lt_52pct;oos_win_rate_lt_52pct;has_negative_year;worst_chrono_fold_not_positive;cost_x1_5_mean_not_positive;cost_x2_mean_not_positive;declustered_mean_not_positive;declustered_win_rate_lt_52pct;long_direction_mean_not_positive;short_direction_mean_not_positive`
- `S49_MTF_H1W120_P85_M15S40_M5S20_H24` trades=2924 mean=-1.7496 oos_mean=2.7140 decl_mean=-1.7353 x2_mean=-4.7316 decision=`HARD_AUDIT_NO_PASS` notes=`mean_not_positive;win_rate_lt_52pct;oos_win_rate_lt_52pct;has_negative_year;worst_chrono_fold_not_positive;cost_x1_5_mean_not_positive;cost_x2_mean_not_positive;cost_x2_oos_mean_not_positive;declustered_mean_not_positive;declustered_win_rate_lt_52pct;short_direction_mean_not_positive;long_direction_mean_not_positive`
- `S49_MTF_H1W72_P85_M15S20_M5S20_H24` trades=3150 mean=-2.0441 oos_mean=2.1893 decl_mean=-1.8328 x2_mean=-5.0261 decision=`HARD_AUDIT_NO_PASS` notes=`mean_not_positive;win_rate_lt_52pct;oos_win_rate_lt_52pct;has_negative_year;worst_chrono_fold_not_positive;cost_x1_5_mean_not_positive;cost_x2_mean_not_positive;cost_x2_oos_mean_not_positive;declustered_mean_not_positive;declustered_win_rate_lt_52pct;long_direction_mean_not_positive;short_direction_mean_not_positive`

## Interpretation

This is a hard audit only. Passing this audit would still not authorize EA, paper-live, or live trading; it would only justify the next controlled forward-shadow design step.
