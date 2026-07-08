# Stage158 Trade Attribution Audit

## Purpose

Stage158 is a read-only root-cause audit for the XAUUSD demo execution loop. It answers the operational question:

> Are losses coming from weak rules, execution delay/slippage, bad exits, stale contamination, or active-router protocol hopping?

It does not generate signals, does not write a router KV, and does not send orders.

## Inputs

Default paths:

```text
/Users/vahid/Desktop/xauusd-trader/data/demo_execution/stage144_clean_demo_execution_ledger.csv
/Users/vahid/Desktop/xauusd-trader/reports/stage145_clean_ledger_performance_gate/stage145_clean_ledger_performance_gate_summary.json
/Users/vahid/Desktop/xauusd-trader/reports/stage150_mtf_separated_validation_discovery/m5/stage150_candidate_scores.csv
/Users/vahid/Downloads/xauusd_fundamental_event_inbox/amarkets_xauusd_5m.csv
```

The M5 bars are optional but strongly recommended because they enable theoretical horizon return, MFE, MAE, and entry-slippage diagnostics.

## Outputs

```text
/Users/vahid/Desktop/xauusd-trader/reports/stage158_trade_attribution_audit/stage158_trade_attribution_audit_summary.json
/Users/vahid/Desktop/xauusd-trader/reports/stage158_trade_attribution_audit/stage158_trade_attribution_audit_trades.csv
/Users/vahid/Desktop/xauusd-trader/reports/stage158_trade_attribution_audit/stage158_family_attribution_summary.csv
/Users/vahid/Desktop/xauusd-trader/reports/stage158_trade_attribution_audit/stage158_cohort_attribution_summary.csv
/Users/vahid/Desktop/xauusd-trader/reports/stage158_trade_attribution_audit/stage158_diagnosis_summary.csv
```

## Diagnosis labels

- `STALE_CONTAMINATED`: the feature date is too old versus normalized entry time.
- `ROUTER_PROTOCOL_FAIL`: multiple distinct rules traded the same feature-date context and the trade lost.
- `ROUTER_PROTOCOL_RISK_PROFIT`: same router-protocol issue, but this trade was profitable.
- `EXIT_FAIL`: the trade had meaningful favorable excursion, but exit/timeout/SL produced a loss.
- `RULE_FAIL`: the feature-date horizon itself was negative, so the rule likely failed.
- `EXECUTION_DELAY_RISK`: entry occurred late versus feature date.
- `EXECUTION_PRICE_RISK`: entry price was materially worse than feature bar close.
- `PROFIT_SMALL_N`: profitable but still not enough for promotion.
- `SMALL_N_UNRESOLVED`: not enough evidence to attribute.

## Operational decision after Stage158

- If router-protocol failures dominate, stop active-router demo and use locked-rule or locked-family demo protocol.
- If exit failures dominate, repair exit logic with MFE/MAE and timeout analysis before discarding rules.
- If rule failures dominate, rebuild discovery with stricter walk-forward, session, spread, and event filters.
- If stale contamination dominates, separate scientific ledger from operational ledger and judge only the post-fix cohort.

Stage157 freeze should stay active while Stage158 is reviewed.
