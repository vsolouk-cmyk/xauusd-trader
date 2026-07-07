# Stage155 Active Router Demo Risk Guard

Stage154 solved inactivity by routing among cached Stage150 PASS candidates, but the first Stage154-routed family closed negative and the prior M5 trend family was also negative.

Stage155 keeps the fast cached-router architecture, but adds a demo-risk guard:

- read Stage145 per-family performance summary;
- normalize candidate `rule_id` to a family key;
- block families that have at least one demo trade and are net negative;
- route only among remaining cached PASS candidates;
- write a Stage134-compatible KV;
- never send orders itself.

Recommended run:

```bash
python3 app/stage154_active_shortlist_rule_router.py \
  --root /Users/vahid/Desktop/xauusd-trader \
  --bars /Users/vahid/Downloads/xauusd_fundamental_event_inbox/amarkets_xauusd_5m.csv \
  --score-csv /Users/vahid/Desktop/xauusd-trader/reports/stage150_mtf_separated_validation_discovery/m5/stage150_candidate_scores.csv \
  --risk-summary /Users/vahid/Desktop/xauusd-trader/reports/stage145_clean_ledger_performance_gate/stage145_clean_ledger_performance_gate_summary.json \
  --tf m5 \
  --timeframe-minutes 5 \
  --max-feature-age-sec 7200 \
  --timestamp-shift-hours -3 \
  --write-mt5
```

Stage134 should point to:

```text
InpRuleStateKvFile:
xauusd_stage155_m5_active_router_rule_state_kv.csv

InpAllowedRules:
all
```

Use `--allow-negative-demo-families` only for explicit diagnostics, not for normal demo execution.
