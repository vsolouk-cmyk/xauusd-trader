# Stage171H2 Active Macro Source Selection Hotfix

- Excludes `_repair_backups`, archive, inactive, reports and forward outputs from DXY/real-yield discovery.
- Selects the newest usable observation first; canonical active-path priority breaks date ties.
- Records candidate diagnostics in the summary.
- Keeps the production snapshot CSV fail-closed: it is written only when all quality gates pass.
- Always appends a separate diagnostic attempt ledger at `data/forward_shadow/h64l_forward_feature_attempts.csv`.
- No threshold optimization, demo authorization, order routing or live execution.
