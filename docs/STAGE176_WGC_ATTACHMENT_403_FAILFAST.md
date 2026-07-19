# Stage176 WGC Attachment 403 Fail-Fast Bugfix

## Purpose

This is an integration-only repair for Stage176. It does not alter the locked allocation thesis, thresholds, holdout, baselines, costs, or decision gates.

WGC legacy `/download/file/...` attachment endpoints may return HTTP 403 to both Python urllib and curl. Retrying these permanent denials wastes time and does not improve data coverage.

## Behaviour after patch

- The first attachment HTTP 403 is treated as permanent for that URL: no retry, no backoff, and no curl fallback.
- After two uncached attachment 403 responses in the same run, a circuit breaker disables further network attachment downloads.
- Existing cached attachments are still read and parsed.
- Report-page and dedicated Central Banks section extraction continues normally.
- The final vintage preflight remains fail-closed. Missing original vintages are not replaced with a revised current workbook.

Expected progress messages:

```text
403 is permanent for this attachment endpoint; skip curl and retry streak=1/2
circuit breaker: repeated attachment 403 responses; disable uncached attachment downloads for the rest of this run
attachment network fetch disabled for this run; use page/section/cache only
```

## Install

```bash
cd ~/Downloads

mv xauusd_stage176_wgc_attachment_403_failfast_patch.zip \
  ~/Desktop/xauusd-trader/

cd ~/Desktop/xauusd-trader

rm -rf _incoming_stage176_403failfast
mkdir _incoming_stage176_403failfast

unzip xauusd_stage176_wgc_attachment_403_failfast_patch.zip \
  -d _incoming_stage176_403failfast

rsync -a _incoming_stage176_403failfast/ ./

rm -rf _incoming_stage176_403failfast
rm xauusd_stage176_wgc_attachment_403_failfast_patch.zip
```

## Test

```bash
cd ~/Desktop/xauusd-trader

python3 -m unittest \
  tests/test_stage176_central_bank_allocation_falsification.py
```

Expected: 27 tests, OK.

## Rerun

```bash
python3 app/stage176_central_bank_allocation_falsification.py \
  --root ~/Desktop/xauusd-trader \
  --config configs/stage176_central_bank_allocation_falsification.json
```

All existing report and attachment cache files are retained.
