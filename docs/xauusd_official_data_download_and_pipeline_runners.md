# Stage116C Runner Observability and Official Economic Events Patch

## Purpose

This patch replaces the data runners with operator-visible progress and durable logs. It does not change trading, MT5, EA, broker, paper-order, or live-order surfaces.

## Why this patch exists

The official data batch can take a long time because it downloads many independent sources, including yearly COT zips and Census yearly files. A silent runner is operationally unsafe because it is hard to tell whether it is working, stuck, or partially failed.

The patch also clarifies the economic-events path. The project should not depend on a fragile commercial economic-calendar feed. The official economic-event backbone is:

- FRED release dates
- FOMC calendar snapshot
- Treasury auction calendar/query
- BLS actual macro releases
- BEA actual macro releases
- Census economic indicators

Stage115/Stage116 then convert these into event features. Forecast/surprise fields remain separate and should not block discovery.

## Security

API keys are read only from environment variables:

```bash
FRED_API_KEY
BLS_API_KEY
BEA_API_KEY
CENSUS_API_KEY
```

The runner masks exported key values in logs and stdout. Do not hardcode keys in repo files.

## Download-only runner

```bash
cd /Users/vahid/Desktop/xauusd-trader

python3 scripts/download_xauusd_official_data_batch.py \
  --inbox ~/Downloads/xauusd_fundamental_event_inbox
```

Optional:

```bash
python3 scripts/download_xauusd_official_data_batch.py \
  --inbox ~/Downloads/xauusd_fundamental_event_inbox \
  --include-cot-xls
```

Skip WGC direct attempts if browser/manual files are already present or WGC blocks curl:

```bash
python3 scripts/download_xauusd_official_data_batch.py \
  --inbox ~/Downloads/xauusd_fundamental_event_inbox \
  --skip-wgc-direct
```

Dry-run without downloading:

```bash
python3 scripts/download_xauusd_official_data_batch.py --dry-run
```

## Progress output

The runner prints:

```text
[01/13 START] FRED macro direct CSVs | items=10 | 2026-06-28T...
    [001/010] OK DFII10.csv 95.6KB 0.42s
[01/13 DONE ] FRED macro direct CSVs | ok=10 warn/fail=0 | elapsed=4.2s
```

## Logs

Download logs are saved under:

```text
~/Downloads/xauusd_fundamental_event_inbox/_logs/
```

Important files:

```text
download_xauusd_official_data_batch_<timestamp>.jsonl
download_xauusd_official_data_batch_latest_summary.json
```

## Full pipeline runner

Run existing downloaded files through unifier / normalizers / validators:

```bash
cd /Users/vahid/Desktop/xauusd-trader

python3 scripts/run_xauusd_fundamental_unify_normalize_pipeline.py
```

Download first, then run full pipeline:

```bash
python3 scripts/run_xauusd_fundamental_unify_normalize_pipeline.py --download-first
```

The pipeline prints step-level progress and writes logs to:

```text
reports/xauusd_fundamental_unify_normalize_pipeline/
```

## Expected next workflow

1. Run download batch when you need to refresh official data.
2. Run full pipeline.
3. Check Stage116 summary.
4. Start segmented discovery only if Stage116 says source validation is ready.


## Stage116C secure API-key handling

Do not hardcode API keys in repository code. The download runner now supports local env files that are intended to stay outside Git. Supported keys are:

```text
FRED_API_KEY
BLS_API_KEY
BEA_API_KEY
CENSUS_API_KEY
```

Recommended local file location:

```text
~/Downloads/xauusd_fundamental_event_inbox/.xauusd_official_data.env
```

Create it locally, then keep it out of Git:

```bash
cat > ~/Downloads/xauusd_fundamental_event_inbox/.xauusd_official_data.env <<'EOF'
FRED_API_KEY=PASTE_FRED_KEY_HERE
BEA_API_KEY=PASTE_BEA_KEY_HERE
CENSUS_API_KEY=PASTE_CENSUS_KEY_HERE
EOF
chmod 600 ~/Downloads/xauusd_fundamental_event_inbox/.xauusd_official_data.env
```

The runner auto-loads both:

```text
~/.xauusd_official_data.env
~/Downloads/xauusd_fundamental_event_inbox/.xauusd_official_data.env
```

You can also pass an explicit file:

```bash
python3 scripts/download_xauusd_official_data_batch.py \
  --inbox ~/Downloads/xauusd_fundamental_event_inbox \
  --env-file ~/Downloads/xauusd_fundamental_event_inbox/.xauusd_official_data.env
```

The runner reports only key presence and masks key values in logs.
