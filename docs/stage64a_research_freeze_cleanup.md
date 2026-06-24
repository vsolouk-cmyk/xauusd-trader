# Stage64A Research Freeze + Cleanup + Active/Archive Map + Experiment Ledger

## Purpose

Stage64A is a governance reset stage. It freezes the previous intraday candidate-first research program and creates the project artifacts needed before Stage64B corrected statistical audit and Stage64C macro-regime thesis specification.

## What it does

- Writes a research freeze memo.
- Writes an active/archive/reference-only map.
- Writes an experiment ledger skeleton with candidate/variant/thesis-family fields.
- Creates multiple-testing penalty group placeholders.
- Writes a summary JSON and report MD.

## What it does not do

- It does not mutate prior state databases.
- It does not move old reports physically.
- It does not generate signals.
- It does not create paper orders.
- It does not authorize EA, paper-live, or live trading.

## Run

```bash
python3 app/stage64a_research_freeze_cleanup.py   --root .   --config configs/stage64a_research_freeze_cleanup.json   --out reports/stage64a_research_freeze_cleanup
```

## Expected outputs

```text
reports/stage64a_research_freeze_cleanup/stage64a_research_freeze_memo.md
reports/stage64a_research_freeze_cleanup/stage64a_active_archive_reference_map.csv
reports/stage64a_research_freeze_cleanup/stage64a_active_archive_reference_map.json
reports/stage64a_research_freeze_cleanup/stage64a_experiment_ledger_skeleton.csv
reports/stage64a_research_freeze_cleanup/stage64a_experiment_ledger_skeleton.json
reports/stage64a_research_freeze_cleanup/stage64a_research_freeze_cleanup_report.md
reports/stage64a_research_freeze_cleanup/stage64a_research_freeze_cleanup_summary.json
```

## Review criteria

Stage64A is complete if the summary status is:

```text
RESEARCH_FREEZE_CLEANUP_MAP_LEDGER_COMPLETE_NO_PROMOTION
```

The next allowed step is Stage64B and Stage64C. No order path is authorized.
