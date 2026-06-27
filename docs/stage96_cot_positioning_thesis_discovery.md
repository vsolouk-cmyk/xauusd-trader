# Stage96 COT Positioning Thesis Discovery

## Role

Stage96 discovers COT-positioning thesis candidates after:

- Stage88 unified observer is operational.
- Stage89 macro-only residual discovery produced no shortlist.
- Stage92 intraday/session residual discovery produced no shortlist.
- Stage95 built `data/external_frontiers/cot_positioning_normalized.csv`.

This stage is research-only. It cannot authorize orders, connect to a broker, modify MT5, or promote an EA.

## Data

Inputs:

```text
configs/stage96_cot_positioning_thesis_discovery.json
data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv
data/external_frontiers/cot_positioning_normalized.csv
```

Output directory:

```text
reports/stage96_cot_positioning_thesis_discovery/
```

Main outputs:

```text
stage96_cot_positioning_thesis_discovery_summary.json
stage96_cot_positioning_thesis_discovery_report.md
stage96_cot_candidate_metrics.csv
stage96_cot_thesis_shortlist.csv
stage96_cot_entry_returns.csv
stage96_cot_joined_daily_snapshot.csv
```

## COT join rule

The COT dataset is joined to daily macro rows by `available_after_utc`, not by raw report date. If `available_after_utc` is missing, Stage96 assumes a three-calendar-day availability lag from the Tuesday report date. This is a conservative no-lookahead default for Friday publication timing.

## Discovery design

Stage96 uses a fixed candidate set in the config. It does not tune thresholds during the run.

Default mode is residual-only: COT rules are evaluated on days where the existing unified observer portfolio is inactive.

Current unified observer portfolio reference:

```text
K06
K03
K07
S83_14
S83_13
```

## Hard blocks

```text
NO_AUTOMATED_ORDER
NO_PAPER_ORDER
NO_BROKER_CONNECTION
NO_EA_PROMOTION
NO_PAPER_LIVE
NO_LIVE
NO_ORDER_AUTHORIZATION_FROM_STAGE96
NO_THRESHOLD_TUNING_FROM_STAGE96_DISCOVERY
NO_DIRECT_MT5_OR_EA_CHANGE_FROM_STAGE96
```

## Next stage

If Stage96 produces a shortlist, the next stage is Stage97 hard audit on only that shortlist.

If Stage96 produces no shortlist, COT positioning does not add a defensible residual thesis under the current fixed rules and data. Continue only with event-surprise data building or source-quality flow datasets.
