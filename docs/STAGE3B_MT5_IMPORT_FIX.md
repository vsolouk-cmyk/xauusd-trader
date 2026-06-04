# Stage 3B MT5 Import Fix

## Problem

MT5 exported a tab-separated file with headers like:

```text
<DATE> <TIME> <OPEN> <HIGH> <LOW> <CLOSE> <TICKVOL> <VOL> <SPREAD>
```

The previous importer expected comma-separated CSV with direct columns like:

```text
time_utc,open,high,low,close
```

## Fix

The second-source importer now:

- auto-detects delimiter,
- cleans MT5 angle-bracket headers,
- combines DATE and TIME into time_utc,
- maps TICKVOL/VOL to volume.

## Command

```bash
python3 -m app.xauusd_second_source_import \
  --csv ~/Downloads/xauusd_1h_mt5.csv \
  --db data/second_source/second_source.sqlite \
  --interval 1h \
  --provider mt5
```

Then:

```bash
python3 -m app.xauusd_stage3a_second_source_validate
```
