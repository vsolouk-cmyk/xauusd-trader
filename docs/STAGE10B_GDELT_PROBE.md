# Stage 10B GDELT Probe

This is a diagnostic tool to answer one question:

```text
Can GitHub Actions fetch GDELT data?
```

It does not modify the event pipeline and does not create trading signals.

## Run locally

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage10b_gdelt_probe --timespan 7d --max-records 10 --timeout 60 --retries 2
cat data/reports/stage10b_gdelt_probe/gdelt_probe.md
```

Local timeout is acceptable. The main test is GitHub.

## GitHub workflow

After pushing, run:

```text
Actions -> XAUUSD GDELT Probe -> Run workflow
```

Download artifact:

```text
xauusd-gdelt-probe
```

Check:

```text
gdelt_probe.md
gdelt_probe_query_status.csv
gdelt_probe_sample_articles.csv
```

## Interpretation

```text
total_articles > 0
```

means GitHub can fetch GDELT and Stage 10B should be upgraded to use the probe's simpler query pattern.

```text
all queries error/timeout
```

means GDELT access is failing even from GitHub.

```text
status ok but articles=0
```

means connectivity works but query/timespan needs adjustment.

## Hard rule

Diagnostics only. No EA change, no automatic news trading.
