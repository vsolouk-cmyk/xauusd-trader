# Stage116 Source-Specific WGC/SPDR/DXY Validator

Purpose: validate source-specific WGC ETF, WGC central-bank, SPDR GLD and DXY inputs before segmented discovery.

This stage is data-only. It does not promote candidates, touch MT5, modify the EA, connect to a broker, or permit paper/live orders.

## Outputs

- `data/fundamental_event_inbox/features/stage116_validated_dollar_pressure.csv`
- `data/fundamental_event_inbox/features/stage116_dxy_source_diagnostics.csv`
- `data/fundamental_event_inbox/features/stage116_validated_wgc_gold_etf_long.csv`
- `data/fundamental_event_inbox/features/stage116_validated_wgc_central_bank_gold_long.csv`
- `data/fundamental_event_inbox/features/stage116_validated_spdr_gld_long.csv`
- `reports/stage116_source_specific_wgc_spdr_dxy_validator/stage116_source_specific_wgc_spdr_dxy_validator_summary.json`
- `reports/stage116_source_specific_wgc_spdr_dxy_validator/stage116_xlsx_sheet_profiles.csv`

## DXY behavior

Direct DXY is accepted only if it has at least 50 valid dated close/value rows. If direct DXY is missing, blocked, HTML, or too short, Stage116 falls back to FRED `DTWEXBGS` from Stage115 feature outputs.

## WGC/SPDR behavior

WGC/SPDR Excel files are parsed into long-form candidate rows with workbook/sheet/date/metric/value provenance. These become validated candidates, not automatic hard trading features.

## Run

```bash
cd /Users/vahid/Desktop/xauusd-trader

python3 app/stage116_source_specific_wgc_spdr_dxy_validator.py \
  --root /Users/vahid/Desktop/xauusd-trader \
  --inbox ~/Downloads/xauusd_fundamental_event_inbox
```
