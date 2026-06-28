# Stage112 Vol / Risk-Premium Rotation Frontier Discovery

## Status

Discovery-only patch. No order, no paper-order, no live, no broker connection, no EA mutation, and no MT5 bridge CSV write.

## Why this thesis follows Stage111

Stage111 correctly returned no selected candidate. The output showed that the available macro dataset had DXY, real-yield, VIX, gold trend, and central-bank 3m features, but did not expose the ETF-flow and COT numeric fields needed for the macro/flow absorption thesis. Therefore Stage112 moves to a frontier that is supported by the existing dataset: volatility / risk-premium rotation.

## Thesis

Gold often reacts not only to DXY and real yields but also to risk-premium regimes. The current 7-rule observer is mostly DXY / real-yield / central-bank / COT-decrowding oriented. Stage112 tests whether VIX/risk-premium states add incremental timing power over the existing observer.

## Historical segmentation

Stage112 persists split files under:

```text
reports/stage112_vol_risk_premium_rotation_frontier_discovery/splits/
```

Expected files:

```text
stage112_selection_rows.csv
stage112_validation_rows.csv
stage112_tail_forward_proxy_rows.csv
stage112_selection_quantile_thresholds.csv
stage112_split_manifest.json
```

Quantile thresholds are learned only from the selection segment and then applied unchanged to validation and tail-forward proxy. This is the project default for weekend discovery and prevents long forward-only waiting from blocking candidate discovery.

## Outputs

```text
reports/stage112_vol_risk_premium_rotation_frontier_discovery/stage112_vol_risk_premium_rotation_frontier_discovery_summary.json
reports/stage112_vol_risk_premium_rotation_frontier_discovery/stage112_vol_risk_premium_rotation_frontier_discovery_report.md
reports/stage112_vol_risk_premium_rotation_frontier_discovery/stage112_candidate_metrics.csv
reports/stage112_vol_risk_premium_rotation_frontier_discovery/stage112_selected_for_stage113.csv
reports/stage112_vol_risk_premium_rotation_frontier_discovery/stage112_review_queue.csv
reports/stage112_vol_risk_premium_rotation_frontier_discovery/stage112_overlap_matrix.csv
reports/stage112_vol_risk_premium_rotation_frontier_discovery/stage112_recent_signal_snapshot.csv
```

## Interpretation

If `stage112_selected_for_stage113.csv` is empty, this frontier is killed or left as research-only and the next thesis should start immediately.

If it has rows, the rows are only selected for Stage113 review. Stage112 does not authorize observer expansion by itself.
