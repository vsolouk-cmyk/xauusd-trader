# Stage115 Feature-Grade Macro/Fundamental Builder

Stage115 converts Stage114B normalized/shell outputs into feature-grade or feature-candidate artifacts for the next historical-as-of discovery stage.

It does not create a signal, touch MT5, modify the EA, connect to broker, or allow paper/live orders.

## Inputs

Default inputs:

```text
reports/stage114b_classification_and_macro_event_hotfix/stage114b_corrected_file_classification.csv
data/fundamental_event_inbox/normalized/fred_macro_normalized.csv
data/fundamental_event_inbox/normalized/fred_release_calendar_normalized.csv
data/fundamental_event_inbox/normalized/dxy_reference_normalized.csv
data/fundamental_event_inbox/normalized/bls_macro_normalized.csv
data/fundamental_event_inbox/normalized/bea_macro_shell_normalized.csv
data/fundamental_event_inbox/normalized/census_macro_shell_normalized.csv
data/fundamental_event_inbox/normalized/treasury_auctions_normalized.csv
data/fundamental_event_inbox/normalized/fomc_calendar_extracted.csv
data/fundamental_event_inbox/normalized/wgc_gold_etf_xlsx_rows.csv
data/fundamental_event_inbox/normalized/wgc_central_bank_gold_xlsx_rows.csv
data/fundamental_event_inbox/normalized/spdr_gld_xlsx_rows.csv
```

## DXY policy

Direct DXY is used only if `dxy_reference_normalized.csv` has at least 50 valid close rows. If not, Stage115 automatically falls back to FRED `DTWEXBGS` as the dollar-pressure index and marks:

```text
dollar_pressure_source = FRED_DTWEXBGS_FALLBACK
```

This avoids blocking discovery when Stooq/Yahoo/Investing DXY downloads fail.

## COT policy

Stage115 parses CFTC zip files directly from the Stage114B corrected classification CSV. It prefers:

```text
fut_disagg_txt_*.zip
```

If that family is absent, it falls back to:

```text
com_disagg_txt_*.zip
```

The output includes managed-money net positioning, producer/commercial proxy net positioning, percentage-of-open-interest features, rolling z-scores, and 4w/12w decrowding changes.

## Run

```bash
cd /Users/vahid/Desktop/xauusd-trader

python3 app/stage115_feature_grade_macro_fundamental_builder.py \
  --root /Users/vahid/Desktop/xauusd-trader
```

## Outputs

```text
data/fundamental_event_inbox/features/stage115_daily_macro_feature_panel.csv
data/fundamental_event_inbox/features/stage115_fred_macro_daily_wide.csv
data/fundamental_event_inbox/features/stage115_cot_gold_weekly_features.csv
data/fundamental_event_inbox/features/stage115_fred_release_event_features.csv
data/fundamental_event_inbox/features/stage115_fomc_event_features.csv
data/fundamental_event_inbox/features/stage115_treasury_auction_event_features.csv
data/fundamental_event_inbox/features/stage115_bls_macro_feature_long.csv
data/fundamental_event_inbox/features/stage115_bea_event_shell_features.csv
data/fundamental_event_inbox/features/stage115_census_event_shell_features.csv
data/fundamental_event_inbox/features/stage115_wgc_gold_etf_feature_candidates.csv
data/fundamental_event_inbox/features/stage115_wgc_central_bank_gold_feature_candidates.csv
data/fundamental_event_inbox/features/stage115_spdr_gld_feature_candidates.csv
data/fundamental_event_inbox/features/stage115_unified_event_calendar_features.csv
data/fundamental_event_inbox/features/stage115_feature_inventory.csv
reports/stage115_feature_grade_macro_fundamental_builder/stage115_feature_grade_macro_fundamental_builder_summary.json
reports/stage115_feature_grade_macro_fundamental_builder/stage115_feature_grade_macro_fundamental_builder_report.md
```

## Interpretation

PASS criteria for continuing:

```text
cot_gold_weekly_feature_rows > 500
daily_macro_rows > 3000
dxy_fallback_active can be true, but dollar_pressure_index must exist through DTWEXBGS
remaining hard blocks unchanged
```

WGC/SPDR outputs are treated as feature candidates until a source-specific validator confirms field semantics.

## Hotfix note: CSV shell payload field size

Stage114B BEA/Census shell outputs may store large JSON payload fragments inside a single CSV field. Python's csv module has a conservative default field limit, often 131072 bytes. Stage115 now raises the CSV field-size limit at startup so these shell-normalized files can be read without blocking the macro/FRED/COT feature build.
