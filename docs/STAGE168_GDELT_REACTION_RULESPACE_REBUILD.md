# Stage168 GDELT Reaction Rulespace Rebuild

## Purpose

Stage167C proved that the GDELT historical event panel can be scanned, but the initial hard-coded event-aware medium-frequency rule families produced no commercial holdout candidate. Stage168 rebuilds the rule space instead of waiting for more samples.

## What this stage scans

Stage168 evaluates a broader post-event reaction surface:

- event family / category: general shock, net long pressure, net short pressure, geopolitical escalation, de-escalation, hawkish/dovish macro, inflation-energy shock, market stress, central-bank gold;
- positive-train event thresholds, not all-bar thresholds;
- entry lags after event hour: 0m, 60m, 180m, 360m, 720m;
- horizons: 60m, 120m, 240m, 480m, 1440m;
- price confirmation: none, momentum-align, momentum-fade, high-volatility;
- session filter: all vs London/NY.

## Safety

Read-only. It does not write MT5 execution files and does not authorize demo/live orders.

## Decision logic

- If no trainable event panel: stop and rebuild event panel.
- If shortlist is positive: run Stage169 execution replay before any demo release.
- If shortlist is zero: do not wait for more samples; kill or redesign the event thesis with stronger labeled event features.

## Expected outputs

`reports/stage168_gdelt_reaction_rulespace_rebuild/stage168_gdelt_reaction_rulespace_summary.json`

`reports/stage168_gdelt_reaction_rulespace_rebuild/stage168_all_reaction_rule_scores.csv`

`reports/stage168_gdelt_reaction_rulespace_rebuild/stage168_commercial_shortlist.csv`

`reports/stage168_gdelt_reaction_rulespace_rebuild/stage168_top_rule_trades.csv`

`reports/stage168_gdelt_reaction_rulespace_rebuild/stage168_decision.md`
