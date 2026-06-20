# Stage51 Broker-Real Volatility Squeeze Breakout Hard Audit

- status: `VOLATILITY_SQUEEZE_HARD_AUDIT_PASS_NEEDS_FORWARD_SHADOW_NO_PROMOTION`
- next_allowed_step: `FORWARD_SHADOW_DESIGN_NO_PROMOTION`
- promotion: `NO_GO`
- EA: `NO_GO`
- paper_live: `NO_GO`
- live: `NO_GO`

## Thesis

M15 volatility compression may precede short-horizon directional continuation when price breaks out of the compressed range and M30 trend confirmation is aligned. This is not a session open-range thesis, not H1 expansion persistence, and not a liquidity-sweep reversal rescue.

## Inputs

- M5 rows: `292454`
- M15 rows: `97536`
- M30 rows: `48775`
- stress_cost_bps: `2.9820`
- extreme_spread_gate_bps: `3.0380`

## Result

- grid_candidate_count: `108`
- hard_audit_pass_count: `12`

## Top candidates
- `S51_VSQ_CW48_P20_B5_M3020_H24` trades=`293` mean=`5.8402` oos_mean=`32.2291` decision=`HARD_AUDIT_NO_PASS` notes=`win_rate_lt_52pct;is_mean_not_positive;positive_year_count_lt_4;negative_year_count_gt_1;worst_chrono_fold_not_positive;declustered_win_rate_lt_52pct`
- `S51_VSQ_CW48_P20_B5_M3040_H24` trades=`282` mean=`6.4174` oos_mean=`30.7169` decision=`HARD_AUDIT_NO_PASS` notes=`win_rate_lt_52pct;positive_year_count_lt_4;negative_year_count_gt_1;worst_chrono_fold_not_positive;declustered_win_rate_lt_52pct`
- `S51_VSQ_CW96_P20_B3_M3020_H24` trades=`251` mean=`6.6375` oos_mean=`27.7313` decision=`HARD_AUDIT_NO_PASS` notes=`win_rate_lt_52pct;declustered_win_rate_lt_52pct`
- `S51_VSQ_CW96_P20_B3_M3040_H24` trades=`251` mean=`6.6375` oos_mean=`27.7313` decision=`HARD_AUDIT_NO_PASS` notes=`win_rate_lt_52pct;declustered_win_rate_lt_52pct`
- `S51_VSQ_CW96_P20_B5_M3020_H12` trades=`187` mean=`8.4327` oos_mean=`26.4058` decision=`HARD_AUDIT_NO_PASS` notes=`worst_chrono_fold_not_positive`
- `S51_VSQ_CW96_P20_B5_M3040_H12` trades=`187` mean=`8.4327` oos_mean=`26.4058` decision=`HARD_AUDIT_NO_PASS` notes=`worst_chrono_fold_not_positive`
- `S51_VSQ_CW96_P20_B5_M3020_H24` trades=`187` mean=`9.1216` oos_mean=`25.7806` decision=`HARD_AUDIT_NO_PASS` notes=`win_rate_lt_52pct;worst_chrono_fold_not_positive;declustered_win_rate_lt_52pct`
- `S51_VSQ_CW96_P20_B5_M3040_H24` trades=`187` mean=`9.1216` oos_mean=`25.7806` decision=`HARD_AUDIT_NO_PASS` notes=`win_rate_lt_52pct;worst_chrono_fold_not_positive;declustered_win_rate_lt_52pct`
- `S51_VSQ_CW48_P20_B5_M3040_H12` trades=`282` mean=`5.9649` oos_mean=`25.5747` decision=`HARD_AUDIT_NO_PASS` notes=`win_rate_lt_52pct;positive_year_count_lt_4;negative_year_count_gt_1;worst_chrono_fold_not_positive`
- `S51_VSQ_CW48_P20_B5_M3020_H12` trades=`293` mean=`5.4564` oos_mean=`25.3478` decision=`HARD_AUDIT_NO_PASS` notes=`win_rate_lt_52pct;positive_year_count_lt_4;negative_year_count_gt_1;worst_chrono_fold_not_positive`

## Interpretation

This is a broker-real hard-audit diagnostic only. Passing it would still not authorize EA, paper-live, or live trading; it would only justify a controlled forward-shadow design package.
