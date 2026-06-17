# STAGE39E_FROZEN_RULE_OUT_OF_SAMPLE_AUDIT

## Purpose

Stage39E freezes the surviving Stage39D condition rows and audits their chronological held-out behavior.

This is still research-stage only.

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

## Inputs

```text
reports/stage39d/stage39d_condition_robustness_summary.csv
reports/stage39c/stage39c_condition_event_rows.csv
```

Stage39E only admits Stage39D rows with:

```text
STRICT_CONDITION_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION
FORWARD_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION
```

Rows that failed Stage39D are excluded and must not be revived by filtering.

## Audit dimensions

For each frozen condition row, Stage39E evaluates:

- full-sample cost-stressed behavior,
- chronological train vs held-out OOS split,
- first half / second half,
- q1/q2/q3/q4,
- recent third,
- ex-2025 cost mean,
- leave-one-year-out minimum cost mean,
- slippage stress through +16 bps,
- median MAE/MFE,
- 100 bps stop/target touch behavior.

## Interpretation

`STRICT_FROZEN_OOS_WATCH_ONLY_NO_PROMOTION` means the frozen row survived this research-only audit, but it is still not tradable.

`FROZEN_OOS_WATCH_ONLY_NO_PROMOTION` means partial held-out robustness exists, but at least one strict risk/stress check is still not clean.

`FAIL_FROZEN_OOS_NO_PROMOTION`, `INSUFFICIENT_EVENTS_NO_PROMOTION`, and `INSUFFICIENT_OOS_EVENTS_NO_PROMOTION` should not be extended with more filters.

## Output files

```text
reports/stage39e/stage39e_frozen_rule_oos_summary.csv
reports/stage39e/stage39e_frozen_rule_oos_split_audit.csv
reports/stage39e/stage39e_frozen_rule_oos_audited_events.csv
reports/stage39e/stage39e_frozen_rule_oos_summary.json
reports/stage39e/stage39e_frozen_rule_oos_audit.md
```

## Command

```bash
python3 scripts/stage39e_frozen_rule_out_of_sample_audit.py \
  --stage39d-summary-csv reports/stage39d/stage39d_condition_robustness_summary.csv \
  --stage39c-events reports/stage39c/stage39c_condition_event_rows.csv \
  --cost-bps 8.0 \
  --extra-slippage-bps 0,4,8,12,16 \
  --oos-fraction 0.33 \
  --min-events 30 \
  --min-oos-events 10 \
  --min-oos-cost-mean-bps 15 \
  --min-oos-hit-rate-pct 55 \
  --min-ex2025-cost-mean-bps 10 \
  --min-loyo-cost-mean-bps 10 \
  --min-slip16-cost-mean-bps 10 \
  --max-touch-stop-100-pct 45 \
  --max-median-mae-abs-bps 100 \
  --output-dir reports/stage39e
```

## Next allowed step

Only if one or more rows are `STRICT_FROZEN_OOS_WATCH_ONLY_NO_PROMOTION`, the next step is a separate Stage39F rule-freeze package plus new-data observation protocol.

That is still research-only. It must not create trade alerts, paper-live execution, or EA logic.

If no row is strict, archive Stage39A-E and stop the filter-extension path.
