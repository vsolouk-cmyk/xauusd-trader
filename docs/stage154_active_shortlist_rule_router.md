# Stage154 Active Shortlist Rule Router

Stage151 locked one M5 rule. That is safe, but it can stay inactive for hours. Stage154 keeps the validated Stage150/150B candidate universe cached and only evaluates the latest bar against those cached PASS candidates.

It does not run discovery again and does not send orders. It writes a Stage134-compatible KV for the best currently-active cached candidate.

Recommended M5 run:

```bash
python3 app/stage154_active_shortlist_rule_router.py \
  --root /Users/vahid/Desktop/xauusd-trader \
  --bars /Users/vahid/Downloads/xauusd_fundamental_event_inbox/amarkets_xauusd_5m.csv \
  --score-csv /Users/vahid/Desktop/xauusd-trader/reports/stage150_mtf_separated_validation_discovery/m5/stage150_candidate_scores.csv \
  --tf m5 \
  --timeframe-minutes 5 \
  --max-feature-age-sec 7200 \
  --timestamp-shift-hours -3 \
  --write-mt5
```

Set Stage134:

```text
InpRuleStateKvFile:
xauusd_stage154_m5_active_router_rule_state_kv.csv

InpAllowedRules:
all
```

`InpAllowedRules=all` is acceptable only because Stage154 restricts selection to cached PASS candidates and the account remains demo-only.


## Stage154B hotfix

The router now inserts the repository root into `sys.path`, so the normal command works directly:

```bash
python3 app/stage154_active_shortlist_rule_router.py --help
```

This avoids `ModuleNotFoundError: No module named 'app'` in terminal and launchd.
