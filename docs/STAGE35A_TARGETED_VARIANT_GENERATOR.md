# Stage35A — Targeted Variant Generator

Research-only stage.

Purpose: convert Stage34C controlled intake lanes into concrete targeted variant specifications while Stage33E continues background short confirmation for h13+h14.

This stage does not authorize EA changes, paper-live, live trading, or order routing.

Inputs:

- `data/reports/stage34c_controlled_intake_expansion/stage34c_summary.json`
- `data/reports/stage34c_controlled_intake_expansion/controlled_intake_plan.csv`
- `data/reports/stage33e_short_confirmation_recency_filter/stage33e_summary.json`

Outputs:

- `data/reports/stage35a_targeted_variant_generator/stage35a_targeted_variant_generator.md`
- `data/reports/stage35a_targeted_variant_generator/stage35a_summary.json`
- `data/reports/stage35a_targeted_variant_generator/targeted_variant_specs.csv`
- `data/reports/stage35a_targeted_variant_generator/stage35a_priority_plan.csv`
- `data/reports/stage35a_targeted_variant_generator/stage35a_kill_switches.csv`

Expected next stage if specs are generated:

- `Stage35B Strict Variant Backtest / Queue Evaluator`

Design constraints:

- no broad discovery
- no N=40 waiting by default
- h13+h14 remains background confirmation
- weak paths stay kill/repair unless targeted repair is justified
- every variant has a kill-switch
