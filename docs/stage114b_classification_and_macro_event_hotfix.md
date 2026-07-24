# Stage114B Classification and Macro/Event Hotfix

Status: infrastructure only. No order, no MT5, no EA, no broker connection.

## Why this stage exists

Stage114 ran successfully but left many important downloaded files in `unknown` because Stage113 copied files into `data/fundamental_event_inbox/raw/` with hash-prefixed names such as:

```text
148364a82be6__DFII10.csv
0aa03c0fd636__fut_disagg_txt_2020.zip
```

Stage114B strips this prefix before classification and recognizes the families that appeared in the real manifest:

- FRED macro CSVs: `DFII10`, `DGS10`, `DGS2`, `DFF`, `WALCL`, `T10YIE`, `T5YIE`, `DTWEXBGS`, `VIXCLS`, `BAMLH0A0HYM2`
- FRED release dates JSON
- COT zips: `fut_disagg_txt`, `fut_disagg_xls`, `com_disagg_txt`, `com_disagg_xls`
- DXY/Stooq reference CSV
- BLS, BEA, Census, FOMC, Treasury
- WGC ETF, WGC central-bank gold, SPDR GLD
- AMarkets technical files as reference-only

## Run

```bash
cd /Users/vahid/Desktop/xauusd-trader
python3 app/stage114b_classification_and_macro_event_hotfix.py \
  --root /Users/vahid/Desktop/xauusd-trader \
  --manifest data/fundamental_event_inbox/manifests/stage113_fundamental_event_file_manifest.csv
```

## Outputs

```text
reports/stage114b_classification_and_macro_event_hotfix/stage114b_classification_and_macro_event_hotfix_summary.json
reports/stage114b_classification_and_macro_event_hotfix/stage114b_corrected_file_classification.csv
reports/stage114b_classification_and_macro_event_hotfix/stage114b_remaining_unknown_files.csv
reports/stage114b_classification_and_macro_event_hotfix/stage114b_normalized_outputs.csv
```

Normalized outputs are written under:

```text
data/fundamental_event_inbox/normalized/
```

Key outputs:

```text
fred_macro_normalized.csv
fred_release_calendar_normalized.csv
dxy_reference_normalized.csv
bls_macro_normalized.csv
bea_macro_shell_normalized.csv
census_macro_shell_normalized.csv
treasury_auctions_normalized.csv
fomc_calendar_extracted.csv
cot_cftc_zip_registry.csv
wgc_gold_etf_xlsx_rows.csv
wgc_central_bank_gold_xlsx_rows.csv
spdr_gld_xlsx_rows.csv
```

## Interpretation

This stage fixes classification and macro/event shell normalization. It is not a discovery stage. If `remaining_unknown_count` is still high and contains important data files, stop and patch classifier again. If unknown files are only README/PDF/diagnostics, continue to Stage115.

Stage115 should build feature-grade COT/WGC parsers before restarting thesis discovery.

## FOMC decision-day normalization extension

Local FOMC current/historical HTML files downloaded by Stage116C are parsed into decision-day rows with statement and press-conference flags. Stage114B still performs no network calls.
