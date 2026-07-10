# Stage171F2 Macro Rebuild + GDELT Branch Hotfix

## Why this hotfix exists

The first Stage171F run proved that LaunchAgent, AMarkets freshness inspection, official macro download, and normalization were operational. It also exposed three wiring defects:

1. Stage67D6 expected a different incoming-file contract and was not the correct rebuild adapter for the current inbox.
2. The archived Stage64K builder was invoked without its mandatory `--config` and `--out` arguments.
3. Until the first GitHub workflow publication, the local importer treated an old Downloads artifact as a successful GDELT refresh.

## Fixes

- Removes Stage67D6 from the four-hour production chain.
- Calls the archived Stage64K builder with its archived configuration and explicit report output directory.
- Makes Stage64K a required pipeline step.
- Blocks shadow evaluation unless Stage64K rebuild completes and the resulting feature dataset is fresh.
- Rejects Downloads GDELT artifacts older than 18 hours.
- Updates the GitHub workflow to merge the previous published panel with each incremental refresh before publishing the snapshot branch.
- Cleans the orphan publication branch so only snapshot files are committed.

## Non-goals

- No rule optimization.
- No MT5 signal.
- No order routing.
- No demo/live authorization.
- GDELT remains guard/context only.

## Important source limitation

The official download batch polls automatable sources. In the observed run, WGC direct downloads were HTML/blocked. This hotfix does not claim to bypass WGC access restrictions; it preserves existing valid WGC/SPDR data and reports failures. AMarkets remains manual.
