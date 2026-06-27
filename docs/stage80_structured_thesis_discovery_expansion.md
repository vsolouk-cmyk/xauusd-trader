# Stage80 Structured Thesis Discovery Expansion

## Role

Stage80 continues discovery while the observer stack waits for a real signal. It is a structured thesis-first expansion, not a free threshold search and not a promotion path.

## What it does

- Uses the current macro feature dataset.
- Keeps the Stage77B selected observer portfolio as benchmark/reference.
- Evaluates 36 additional public/macro thesis candidates.
- Applies locked split metrics, corrected historical-as-of metrics, and overlap control against the Stage77B selected portfolio.
- Writes a shortlist for a later hard audit stage only.

## What it must not do

- No order authorization.
- No EA change.
- No broker connection.
- No paper-live or live.
- No threshold tuning based on Stage80 results.
- No ML.

## Expected command

```bash
python3 app/stage80_structured_thesis_discovery_expansion.py   --root .   --config configs/stage80_structured_thesis_discovery_expansion.json   --out reports/stage80_structured_thesis_discovery_expansion
```

## Primary outputs

- `stage80_structured_thesis_discovery_expansion_summary.json`
- `stage80_structured_thesis_discovery_expansion_report.md`
- `stage80_discovery_candidate_metrics.csv`
- `stage80_discovery_split_metrics.csv`
- `stage80_discovery_asof_metrics.csv`
- `stage80_discovery_pairwise_overlap.csv`
- `stage80_overlap_with_stage77b_selected.csv`
- `stage80_discovery_shortlist.csv`
- `stage80_discovery_entry_returns.csv`
- `stage80_missing_data_requirements.csv`

## Interpretation

If Stage80 returns `NEW_DISCOVERY_SHORTLIST_READY_FOR_HARD_AUDIT_NO_ORDER`, the next stage should be a hard audit of the shortlist, not an observer expansion and not an order harness.

If Stage80 returns `NO_NEW_THESIS_PASSING_DISCOVERY_NO_ORDER`, the correct action is either to add missing data families or return to operational monitoring, not to loosen thresholds.
