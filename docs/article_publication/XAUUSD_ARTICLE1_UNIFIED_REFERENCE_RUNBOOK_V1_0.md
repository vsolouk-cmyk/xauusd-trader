# Article 1 Unified Reference Rerun: Installation and Execution Record

## Scope

This package installs the amended version 1.1 specification registry and the
outcome-blind unified reference runner for Article 1. The runner evaluates all
39 primary specifications exactly once over their locked pre-2025 reference
windows. The eight Stage 178 model--target combinations remain historical
forensic evidence and are not refitted or rerun.

The runner does not read prior strategy-performance reports. Before computing
any consolidated outcome, it reconstructs the registry, verifies the bound
source and configuration hashes, verifies every required input hash, checks the
frozen data-contract decision, records the software environment, and writes an
immutable main-run manifest. Any failed check terminates the run without a
support decision.

## Installed files

- `configs/article_publication/XAUUSD_ARTICLE1_EVALUATION_PROTOCOL_V1_0.json`
- `docs/article_publication/XAUUSD_ARTICLE1_DATA_CONTRACT_DECISION_V1_1.json`
- `docs/article_publication/XAUUSD_ARTICLE1_LOCKED_SPECIFICATION_REGISTRY_V1_1.json`
- `docs/article_publication/XAUUSD_ARTICLE1_LOCKED_SPECIFICATION_REGISTRY_V1_1.csv`
- `docs/article_publication/XAUUSD_ARTICLE1_PROTOCOL_DEVIATION_LOG_V1_0.json`
- `docs/article_publication/XAUUSD_ARTICLE1_REGISTRY_FREEZE_MEMO_V1_1.md`
- `docs/article_publication/XAUUSD_ARTICLE1_UNIFIED_REFERENCE_RUNBOOK_V1_0.md`
- `tools/article_publication/article1_registry_preflight.py`
- `tools/article_publication/article1_unified_reference_runner.py`

Version 1.1 supersedes, but does not require deletion of, the version 1.0
registry artifacts. The earlier files should remain available as an audit
trail; they must not be used for execution.

## Installation on the research workstation

Run the following commands in `zsh`. They deliberately stage the downloaded
archive outside the repository, move each versioned artifact into its declared
location, and remove the empty staging directory.

```zsh
article1_zip="$HOME/Downloads/XAUUSD_ARTICLE1_EXECUTION_PACKAGE_V1_1.zip"
article1_incoming="$HOME/Downloads/XAUUSD_ARTICLE1_EXECUTION_PACKAGE_V1_1_INCOMING"

mkdir -p "$article1_incoming"
unzip -q "$article1_zip" -d "$article1_incoming"

cd /Users/vahid/Desktop/xauusd-trader
mkdir -p configs/article_publication docs/article_publication tools/article_publication

mv "$article1_incoming/configs/article_publication/XAUUSD_ARTICLE1_EVALUATION_PROTOCOL_V1_0.json" configs/article_publication/
mv "$article1_incoming/docs/article_publication/XAUUSD_ARTICLE1_DATA_CONTRACT_DECISION_V1_1.json" docs/article_publication/
mv "$article1_incoming/docs/article_publication/XAUUSD_ARTICLE1_LOCKED_SPECIFICATION_REGISTRY_V1_1.json" docs/article_publication/
mv "$article1_incoming/docs/article_publication/XAUUSD_ARTICLE1_LOCKED_SPECIFICATION_REGISTRY_V1_1.csv" docs/article_publication/
mv "$article1_incoming/docs/article_publication/XAUUSD_ARTICLE1_PROTOCOL_DEVIATION_LOG_V1_0.json" docs/article_publication/
mv "$article1_incoming/docs/article_publication/XAUUSD_ARTICLE1_REGISTRY_FREEZE_MEMO_V1_1.md" docs/article_publication/
mv "$article1_incoming/docs/article_publication/XAUUSD_ARTICLE1_UNIFIED_REFERENCE_RUNBOOK_V1_0.md" docs/article_publication/
mv "$article1_incoming/tools/article_publication/article1_registry_preflight.py" tools/article_publication/
mv "$article1_incoming/tools/article_publication/article1_unified_reference_runner.py" tools/article_publication/
mv "$article1_incoming/XAUUSD_ARTICLE1_EXECUTION_PACKAGE_MANIFEST_V1_1.json" ./

rmdir "$article1_incoming/configs/article_publication"
rmdir "$article1_incoming/configs"
rmdir "$article1_incoming/docs/article_publication"
rmdir "$article1_incoming/docs"
rmdir "$article1_incoming/tools/article_publication"
rmdir "$article1_incoming/tools"
rmdir "$article1_incoming"
```

Inspect and commit the protocol before outcome computation:

```zsh
cd /Users/vahid/Desktop/xauusd-trader
git status --short
git add -A
git commit -m "Lock Article 1 unified reference protocol v1.1"
git pull --rebase
git push
```

If `git status --short` reveals an unrelated change that should not be included,
stop before `git add -A` and resolve that repository-state issue first.

## Single admissible execution

No separate preflight upload is required. The `execute` command performs the
complete outcome-blind preflight internally and proceeds only if every gate
passes. The variable is named `article1_run_rc` because `status` is read-only in
`zsh`.

```zsh
cd /Users/vahid/Desktop/xauusd-trader

python3 tools/article_publication/article1_unified_reference_runner.py execute --root "$PWD" > "$HOME/Downloads/XAUUSD_ARTICLE1_REFERENCE_RERUN_CONSOLE.txt" 2>&1
article1_run_rc=$?

cat "$HOME/Downloads/XAUUSD_ARTICLE1_REFERENCE_RERUN_CONSOLE.txt"
echo "ARTICLE1_REFERENCE_RUN_EXIT_CODE=$article1_run_rc"
```

The run directory is intentionally non-overwritable. Do not rerun the command
after a successful execution. If execution stops after creating a partial run
directory, retain it unchanged for diagnosis; do not delete or rename it.

## Required return artifact

On success, upload the single archive reported as
`XAUUSD_ARTICLE1_REFERENCE_RERUN_<UTC>.zip` in `~/Downloads`.

On failure, upload both
`XAUUSD_ARTICLE1_REFERENCE_RERUN_FAILURE_<UTC>.zip` and
`XAUUSD_ARTICLE1_REFERENCE_RERUN_CONSOLE.txt`. A failure is a blocked scientific
gate, not authorization to modify a source, input, protocol, or run directory.

## Expected successful contents

The successful archive contains the outcome-blind preflight, frozen main-run
manifest, run lock, protocol and registry copies, normalized reference trades,
source-native metrics and gates, family-wise max-*t* decisions, independent-feed
replication diagnostics, the alignment-warning sensitivity analysis, the
deflated-Sharpe diagnostic, a compact run summary, and a checksum manifest.

All primary trade rows satisfy their source-specific start rule and exit
strictly before 1 January 2025. The archive records explicitly that no post-2024
outcome was computed and that no paper, demonstration, or live order was
authorized.
