# Stage114 Official Event and Fundamental Normalizer

Stage114 fixes the missing executable error after Stage113. It is infrastructure only: no order, no paper-order, no MT5/EA, no broker connection.

## Purpose

- Scan the manual inbox and nested buckets.
- Accept flat-root files without requiring manual folder moves.
- Read Stage113 manifest when present, without relying on a brittle schema.
- Normalize first-pass official/fundamental/event datasets.
- Rebuild `README_XAUUSD_FUNDAMENTAL_EVENT_INBOX.md` inside the manual inbox with command-line download instructions.

## Supported first-pass parsers

- FRED CSV: `DFII10`, `VIXCLS`, `DTWEXBGS`, `DGS10`, `DGS2`, `T10YIE`, `DFF`, `WALCL`.
- DXY CSV: Stooq, Investing-style, or existing `dxy.csv` style files.
- BLS v2 JSON without API key.
- Treasury auction CSV from FiscalData.
- FOMC HTML snapshot/date text extraction.
- CFTC COT zip registry.
- WGC ETF and central-bank XLSX raw-row extraction when `openpyxl` is available.

## Outputs

Default normalized outputs are written to:

```text
data/fundamental_event_inbox/normalized/
```

Reports are written to:

```text
reports/stage114_official_event_and_fundamental_normalizer/
```

## Run

```bash
cd /Users/vahid/Desktop/xauusd-trader
python3 app/stage114_official_event_and_fundamental_normalizer.py \
  --root /Users/vahid/Desktop/xauusd-trader \
  --manifest data/fundamental_event_inbox/manifests/stage113_fundamental_event_file_manifest.csv
```

## Important

COT and WGC outputs from Stage114 are intentionally conservative. Stage114 registers and extracts raw rows. A later Stage115 should convert these into feature-grade time series for discovery.
