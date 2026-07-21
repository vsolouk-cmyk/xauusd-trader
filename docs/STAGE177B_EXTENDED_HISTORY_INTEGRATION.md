# Stage177B — Extended History Integration and AMarkets Alignment

## Objective

Integrate the accepted Dukascopy H1 and M5 artifacts into one internally consistent local research store, then measure timestamp and price transfer against the AMarkets broker feed.

This stage is research-only. It does not generate signals or orders.

## Canonical data contract

- Direct Dukascopy H1 is used from 2003-05-05 until the start of M5 coverage.
- Dukascopy M5 is primary from 2010-01-01 onward.
- Canonical H1 from 2010 onward is derived from M5.
- AMarkets remains the broker-specific execution and cost reference.
- The generated database is stored under `data/local/` and ignored by Git through a nested `.gitignore`.

## Inputs

Place the two Stage177A artifacts in `~/Downloads`:

- `stage177a-dukascopy-h1_full-bid-*.zip`
- `stage177a-dukascopy-m5_full-bid-*.zip`

The scripts automatically select the newest matching artifacts. Explicit paths can also be supplied.

## Run core integration

```bash
cd ~/Desktop/xauusd-trader

python3 app/stage177b_extended_history_integration.py
```

Explicit-input form:

```bash
python3 app/stage177b_extended_history_integration.py \
  --h1-artifact ~/Downloads/stage177a-dukascopy-h1_full-bid-29779031949.zip \
  --m5-artifact ~/Downloads/stage177a-dukascopy-m5_full-bid-29779341735.zip
```

Expected decision:

```text
PASS_REFERENCE_FEED_INTEGRATED_AMARKETS_PARITY_PENDING
```

Expected local database:

```text
data/local/stage177b_extended_history/xauusd_extended_history.sqlite
```

The database contains:

```text
dukascopy_h1_direct
dukascopy_m5
dukascopy_h1_from_m5
dukascopy_h1_canonical
provenance
```

## Run AMarkets cross-feed alignment

The script searches the known Downloads locations automatically:

```bash
python3 app/stage177b_amarkets_crossfeed.py
```

Explicit paths:

```bash
python3 app/stage177b_amarkets_crossfeed.py \
  --amarkets-h1 ~/Downloads/amarkets_xauusd_1h.csv \
  --amarkets-m5 ~/Downloads/amarkets_xauusd_5m.csv
```

The shift sign is defined as follows:

```text
UTC timestamp = naive AMarkets timestamp + shift_minutes
```

Expected reports:

```text
reports/stage177b_extended_history_integration/stage177b_summary.json
reports/stage177b_extended_history_integration/stage177b_decision.md
reports/stage177b_extended_history_integration/stage177b_h1_m5_parity_anomalies.csv
reports/stage177b_extended_history_integration/stage177b_amarkets_crossfeed_summary.json
reports/stage177b_extended_history_integration/stage177b_amarkets_crossfeed_decision.md
reports/stage177b_extended_history_integration/stage177b_h1_shift_candidates.csv
reports/stage177b_extended_history_integration/stage177b_m5_shift_candidates.csv
```

## Tests

```bash
cd ~/Desktop/xauusd-trader

python3 -m py_compile \
  app/stage177b_extended_history_integration.py \
  app/stage177b_amarkets_crossfeed.py

python3 -m unittest discover \
  -s tests \
  -p 'test_stage177b*.py' \
  -v
```

Expected:

```text
Ran 6 tests

OK
```

## Fail-closed conditions

Stage177B refuses integration when:

- an artifact does not report `PASS_DOWNLOAD_COMPLETE`;
- any chunk hash differs from the manifest;
- the parsed row count differs from the manifest;
- duplicate, non-monotonic, invalid OHLC, or negative-volume rows exist;
- H1/M5 exact OHLC parity falls below 99.9%;
- AMarkets overlap or alignment is too weak for automatic acceptance.

A cross-feed `REVIEW` decision does not invalidate Dukascopy history. It means timestamp mapping or broker-transfer quality must be resolved before strategy revalidation.
