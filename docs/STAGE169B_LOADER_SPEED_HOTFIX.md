# Stage169B Loader + Speed Hotfix

## Purpose

Stage169 originally failed on AMarkets M5 files exported as tab-separated text because the loader used default comma-separated parsing. The symptom was a single merged header column:

```text
['<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>']
```

Stage169B fixes this and reduces runtime.

## Fixes

1. Adds fast delimiter detection for tab, comma, semicolon, and pipe-separated CSV/TXT files.
2. Supports AMarkets/MT5 split `<DATE>` / `<TIME>` headers after delimiter detection.
3. Avoids loading the full M5 file in the normal Stage169 path. Stage168 already contains the locked split metadata, so Stage169B reads only a small bar-file sample for metadata and uses Stage168 split time.
4. Keeps full-bar loading only as a fallback when Stage168 split metadata is missing.

## Safety

- No MT5 signal files are written.
- `order_routing_allowed = False`.
- `demo_release_allowed = False`.
- This is a decision/guard export only.

## Expected effect

The command should start quickly and should no longer fail on tab-separated AMarkets broker CSV files.

## Next

If Stage169B completes, review:

```text
reports/stage169_event_branch_kill_and_current_guard/stage169_event_branch_kill_and_current_guard_summary.json
reports/stage169_event_branch_kill_and_current_guard/stage169_decision.md
```
