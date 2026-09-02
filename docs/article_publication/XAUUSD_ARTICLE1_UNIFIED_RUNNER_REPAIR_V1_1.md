# Article 1 Unified Runner Repair V1.1

## Failure classification

The first consolidated execution attempt terminated at 2 September 2026,
05:26:56 UTC while loading the second H1 feed. The runner requested
`dukascopy_h1_from_m5` from the hash-bound AMarkets alignment database. That
database correctly contains `amarkets_h1_from_m5_utc`, whereas the independently
hash-bound extended-history database contains `dukascopy_h1_from_m5`.

The traceback confirms that termination occurred before the successor runner
entered its candidate loop. Consequently, no consolidated specification trade
ledger, performance metric, multiplicity result, family-support decision, or
post-2024 outcome was computed. The aborted version 1.0 run directory remains
part of the audit trail and must not be deleted, renamed, or reused.

## Repair scope

Version 1.1 makes three implementation-only changes:

1. the AMarkets table is routed to input `amarkets_alignment_sqlite`;
2. the Dukascopy table is routed to input
   `dukascopy_extended_history_sqlite` in both the successor and canonical
   time-series-momentum cross-feed paths; and
3. the outcome-blind preflight now verifies the required table and column
   schema in each routed SQLite file before creating the run directory.

No strategy specification, source implementation, data-file hash, temporal
boundary, cost assumption, statistical rule, multiplicity procedure, cross-feed
threshold, or random seed has changed. The repair is recorded as `A1-DEV-002`
in the version 1.1 deviation log. The replacement execution uses a new,
non-overwritable directory:
`reports/article1_locked_reference_rerun_v1_1`.

## Installation

Run these commands in `zsh` after downloading
`XAUUSD_ARTICLE1_UNIFIED_RUNNER_REPAIR_V1_1.zip` to `~/Downloads`:

```zsh
article1_repair_zip="$HOME/Downloads/XAUUSD_ARTICLE1_UNIFIED_RUNNER_REPAIR_V1_1.zip"
article1_repair_incoming="$HOME/Downloads/XAUUSD_ARTICLE1_UNIFIED_RUNNER_REPAIR_V1_1_INCOMING"

mkdir -p "$article1_repair_incoming"
unzip -q "$article1_repair_zip" -d "$article1_repair_incoming"

cd /Users/vahid/Desktop/xauusd-trader
mkdir -p configs/article_publication docs/article_publication tools/article_publication

mv "$article1_repair_incoming/configs/article_publication/XAUUSD_ARTICLE1_EVALUATION_PROTOCOL_V1_1.json" configs/article_publication/
mv "$article1_repair_incoming/docs/article_publication/XAUUSD_ARTICLE1_PROTOCOL_DEVIATION_LOG_V1_1.json" docs/article_publication/
mv "$article1_repair_incoming/docs/article_publication/XAUUSD_ARTICLE1_UNIFIED_RUNNER_REPAIR_V1_1.md" docs/article_publication/
mv "$article1_repair_incoming/tools/article_publication/article1_unified_reference_runner_v1_1.py" tools/article_publication/
mv "$article1_repair_incoming/XAUUSD_ARTICLE1_UNIFIED_RUNNER_REPAIR_MANIFEST_V1_1.json" ./

rmdir "$article1_repair_incoming/configs/article_publication"
rmdir "$article1_repair_incoming/configs"
rmdir "$article1_repair_incoming/docs/article_publication"
rmdir "$article1_repair_incoming/docs"
rmdir "$article1_repair_incoming/tools/article_publication"
rmdir "$article1_repair_incoming/tools"
rmdir "$article1_repair_incoming"
```

Inspect and commit the versioned repair before outcome computation:

```zsh
cd /Users/vahid/Desktop/xauusd-trader
git status --short
git add -A
git commit -m "Repair Article 1 cross-feed input routing v1.1"
git pull --rebase
git push
```

If `git status --short` contains an unrelated change that should not be included,
stop before `git add -A` and resolve the repository-state issue first.

## Replacement execution

Do not execute the version 1.0 runner again. The following command performs the
new schema-aware preflight internally and creates only the version 1.1 run:

```zsh
cd /Users/vahid/Desktop/xauusd-trader

python3 tools/article_publication/article1_unified_reference_runner_v1_1.py execute --root "$PWD" > "$HOME/Downloads/XAUUSD_ARTICLE1_REFERENCE_RERUN_V1_1_CONSOLE.txt" 2>&1
article1_run_v11_rc=$?

cat "$HOME/Downloads/XAUUSD_ARTICLE1_REFERENCE_RERUN_V1_1_CONSOLE.txt"
echo "ARTICLE1_REFERENCE_RUN_V1_1_EXIT_CODE=$article1_run_v11_rc"
```

On success, return the single archive named
`XAUUSD_ARTICLE1_REFERENCE_RERUN_V1_1_<UTC>.zip` from `~/Downloads`.

On failure, do not repeat the command and do not remove either run directory.
Return both `XAUUSD_ARTICLE1_REFERENCE_RERUN_V1_1_FAILURE_<UTC>.zip` and
`XAUUSD_ARTICLE1_REFERENCE_RERUN_V1_1_CONSOLE.txt`.

No paper, demonstration, or live order is authorized by this repair.
