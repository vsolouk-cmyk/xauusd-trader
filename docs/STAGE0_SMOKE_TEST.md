# Stage 0 Smoke Test

## Purpose

This test checks the minimum data pipeline:

1. collect raw data,
2. normalize raw JSON into CSV,
3. run data-quality report.

It does not test a trading strategy. It does not place orders.

## When it is required

Required:

- first setup on a new machine,
- after changing provider/API code,
- after changing GitHub Actions workflow,
- after changing dependencies,
- when a data provider error occurs.

Not required every time:

- normal documentation edits,
- README edits,
- pure refactoring not touching data ingestion,
- after the pipeline is already stable and GitHub Actions is doing the check.

## Local command

```bash
cd ~/Desktop/xauusd-trader
export TWELVEDATA_API_KEY='PASTE_KEY_HERE'
python3 -m app.xauusd_stage0_smoke --interval 1min --outputsize 100
```

## If it fails at collect

Do not run normalize or data_quality.

Check:

```bash
echo ${TWELVEDATA_API_KEY:+SET}
find data/raw -maxdepth 1 -type f -name '*.json' | sort | tail
```

The most common cause is that no raw JSON was created because API key/access/request failed.
