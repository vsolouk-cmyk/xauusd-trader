# Stage163 macro-supported side discovery

Stage163 is a read-only/offline discovery step. It does not write MT5 KV files and it does not enable demo or live orders.

## Why this stage exists

Stage159 produced a technical shortlist, but Stage161 classified all shortlisted candidates as `MACRO_CONFLICTED` under the current macro context. The current macro context is a USD / real-yield headwind for gold. Therefore a long-only continuation shortlist should not be released to demo.

Stage163 scans both long and short technical sides on M5 bars and keeps only the side supported by the current Stage161 macro pressure. If the supported side is `SHORT`, this still does not mean the system may trade; the current execution path must first be reviewed and patched for sell-side governance.

## Run

```bash
cd /Users/vahid/Desktop/xauusd-trader

python3 app/stage163_macro_supported_side_discovery.py \
  --root /Users/vahid/Desktop/xauusd-trader \
  --bars-m5 /Users/vahid/Downloads/xauusd_fundamental_event_inbox/amarkets_xauusd_5m.csv \
  --stage161-summary reports/stage161_macro_aware_candidate_classifier/stage161_macro_aware_candidate_classifier_summary.json \
  --timestamp-shift-hours -3 \
  --horizon-hours 4 \
  --min-events 100 \
  --min-mean-bps 1.5 \
  --min-hit-rate 0.515 \
  --min-recent-mean-bps 1.0
```

## Outputs

```text
reports/stage163_macro_supported_side_discovery/stage163_macro_supported_side_discovery_summary.json
reports/stage163_macro_supported_side_discovery/stage163_macro_supported_side_candidate_scores.csv
reports/stage163_macro_supported_side_discovery/stage163_macro_supported_side_shortlist.csv
reports/stage163_macro_supported_side_discovery/stage163_macro_supported_side_current_active.csv
reports/stage163_macro_supported_side_discovery/stage163_macro_supported_side_context.json
```

## Decision rule

- If no macro-supported side candidate survives: keep Stage157 freeze, wait for regime change or rebuild thesis.
- If macro-supported long candidates survive: still requires manual review before any locked-family writer.
- If macro-supported short candidates survive: no order release; a separate sell-side execution and governance patch is required before demo.

## Safety

Stage163 is not an execution stage. It only produces reports.
