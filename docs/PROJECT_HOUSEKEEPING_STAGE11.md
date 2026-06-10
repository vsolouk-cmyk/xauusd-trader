# Project Housekeeping for Stage 11

This package adds:

```text
app/maintenance_archive_obsolete_artifacts.py
.github/workflows/xauusd_collectors.yml
```

## Active collector workflow

```text
.github/workflows/xauusd_collectors.yml
```

Schedules:

```text
event_pipeline: every 3 hours on weekdays
macro_numeric: weekdays 21:15 UTC
macro_calendar: daily 06:25 UTC
```

Each artifact name includes GitHub run number and contains metadata JSON.

## Archive audit

First run audit only:

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.maintenance_archive_obsolete_artifacts
cat archive/project_housekeeping/*/archive_manifest.md
```

Apply moving workflows/reports to archive:

```bash
python3 -m app.maintenance_archive_obsolete_artifacts --apply
```

Optional code cleanup:

```bash
python3 -m app.maintenance_archive_obsolete_artifacts --apply --archive-code
```

The script never deletes files. It moves archive candidates into:

```text
archive/project_housekeeping/<UTC_TIMESTAMP>/
```

## Recommended push after cleanup

```bash
git add .
git commit -m "Archive obsolete research artifacts and add Stage 11 collectors"
git pull --rebase
git push
```
