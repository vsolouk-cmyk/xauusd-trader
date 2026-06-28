# Stage118 Macro/COT/SPDR Hard Audit

Stage118 audits the Stage117 review-queue rules before any observer or Stage119 portfolio work.

It is data-only. It does not touch MT5, EA, broker, paper-order, demo-order, or live surfaces.

## Inputs

- `data/fundamental_event_inbox/features/stage117_joined_macro_cot_dollar_h1_research_dataset.csv`
- `reports/stage117_segmented_macro_cot_dollar_discovery/stage117_selected_for_stage118.csv`
- `reports/stage117_segmented_macro_cot_dollar_discovery/stage117_selection_thresholds.csv`
- optional Stage116 summary for DXY/SPDR source context

## Audits

- recomputes Stage117 selected rule masks from frozen Stage117 thresholds
- validates selection / validation / tail-forward-proxy metrics
- runs cost stress at 0, 5, 10, 15, and 25 bps
- creates non-overlap metrics using the 120-hour horizon
- checks feature coverage
- creates rule overlap matrix
- flags candidate-only SPDR rule with stricter requirements

## Outputs

- `stage118_macro_cot_spdr_hard_audit_summary.json`
- `stage118_rule_audit_metrics.csv`
- `stage118_split_cost_stress_metrics.csv`
- `stage118_nonoverlap_cost_stress_metrics.csv`
- `stage118_cost_stress_summary.csv`
- `stage118_overlap_matrix.csv`
- `stage118_selected_for_stage119.csv`
- `stage118_rejected_rules.csv`

## Run

```bash
cd /Users/vahid/Desktop/xauusd-trader

python3 app/stage118_macro_cot_spdr_hard_audit.py   --root /Users/vahid/Desktop/xauusd-trader
```

## Decision semantics

- `HARD_PASS_STAGE119_AUDIT_QUEUE`: may enter Stage119 combined portfolio/observer-readiness review; still no order.
- `WATCH_STAGE119_ONLY_WITH_EXTRA_CONFIRMATION`: may be carried only as watch/context; not promotion.
- `FAIL_NO_STAGE119`: stop the rule unless upstream data/source bug is fixed and Stage117 reruns.
