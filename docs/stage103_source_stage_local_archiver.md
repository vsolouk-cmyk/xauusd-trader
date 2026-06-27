# Stage103 Source Stage Local Archiver

Purpose: reduce repository source clutter after Stage100 by archiving superseded stage source/config/doc/test files locally, then removing those files from `app/`, `configs/`, `docs/`, and `tests/`.

This is not a thesis-discovery stage and does not touch MT5, broker connectivity, order state, or market data.

Preserved operational stages by default:

- Stage67D6 / Stage67E refresh support
- Stage95 COT official dataset builder
- Stage99 unified observer COT bridge
- Stage100 daily unified COT observer combo
- Stage103 archiver itself

Archived files are written into `_local_archive/source_stage_archives/*.archive.zip`, which is ignored by git.

Run first without `--apply` to inspect the archive plan. Run with `--apply` only after checking the plan.
