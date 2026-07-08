# Stage160/161 macro-regime candidate filter

## Purpose

Stage160/161 reconnect the refreshed XAUUSD official-data macro/fundamental pipeline to the current technical candidate repair path.

This package is read-only:

- no MT5 KV is written;
- no order surface is modified;
- no demo or real order is authorized;
- Stage157 freeze should remain active while outputs are reviewed.

## Stage160: macro pipeline readiness audit

Stage160 checks whether the refreshed feature files are present, non-empty, recently modified, and parseable enough for candidate classification.

Main inputs:

- `data/fundamental_event_inbox/features/stage115_daily_macro_feature_panel.csv`
- `data/fundamental_event_inbox/features/stage115_fred_macro_daily_wide.csv`
- `data/fundamental_event_inbox/features/stage115_cot_gold_weekly_features.csv`
- `data/fundamental_event_inbox/features/stage115_unified_event_calendar_features.csv`
- `data/fundamental_event_inbox/features/stage116_validated_dollar_pressure.csv`
- `data/fundamental_event_inbox/features/stage116_validated_spdr_gld_long.csv`
- `data/fundamental_event_inbox/features/stage117_joined_macro_cot_dollar_h1_research_dataset.csv`

Run:

```bash
cd /Users/vahid/Desktop/xauusd-trader

python3 app/stage160_macro_pipeline_readiness_audit.py \
  --root /Users/vahid/Desktop/xauusd-trader
```

Outputs:

```text
reports/stage160_macro_pipeline_readiness_audit/stage160_macro_pipeline_readiness_audit_summary.json
reports/stage160_macro_pipeline_readiness_audit/stage160_macro_feature_inventory.csv
reports/stage160_macro_pipeline_readiness_audit/stage160_macro_pipeline_status_kv.csv
```

Expected decisions:

```text
STAGE160_MACRO_PIPELINE_READY_FOR_CANDIDATE_CLASSIFICATION
STAGE160_MACRO_CORE_READY_WITH_WARNINGS_FOR_CLASSIFICATION_ONLY
STAGE160_MACRO_PIPELINE_BLOCKED_REPAIR_REQUIRED
```

Warnings are expected if WGC direct files are weak/empty. That is not automatically a hard blocker if core dollar/yield/COT/event files are ready.

## Stage161: macro-aware candidate classifier

Stage161 classifies Stage159 technical candidates and families against current macro/regime state.

Main inputs:

- Stage160 summary
- Stage159 technical shortlist
- Stage159 family repair summary
- refreshed Stage115/116 macro/event feature files

Run:

```bash
cd /Users/vahid/Desktop/xauusd-trader

python3 app/stage161_macro_aware_candidate_classifier.py \
  --root /Users/vahid/Desktop/xauusd-trader
```

Outputs:

```text
reports/stage161_macro_aware_candidate_classifier/stage161_macro_aware_candidate_classifier_summary.json
reports/stage161_macro_aware_candidate_classifier/stage161_macro_candidate_classification.csv
reports/stage161_macro_aware_candidate_classifier/stage161_macro_family_classification.csv
reports/stage161_macro_aware_candidate_classifier/stage161_macro_context_snapshot.json
```

Candidate labels:

```text
MACRO_SUPPORTED
MACRO_CONFLICTED
MACRO_MIXED_TECHNICAL_ONLY
EVENT_BLACKOUT_REQUIRED
MACRO_DATA_STALE_OR_INCOMPLETE_NO_DEMO_RELEASE
MACRO_UNKNOWN_NO_DEMO_RELEASE
REGIME_SPECIFIC_ONLY
MACRO_NEUTRAL_REVIEW_ONLY
```

## Interpretation

A technical Stage159 shortlist is not a trading policy. It becomes a candidate for locked-family review only if Stage161 shows a small number of macro-supported families and no event blackout.

Even then, Stage161 does not release demo orders. A separate Stage162 locked-family demo writer would be required, and only after manual review.

## Safety rule

Keep Stage157 freeze active until:

1. Stage160 says macro data is usable;
2. Stage161 identifies macro-supported candidates;
3. the candidate set is small and stable;
4. a separate locked-family demo protocol is intentionally created.
