# Stage47B LoaderFix4 — Robust normalized CSV parser

Status: `HOTFIX_READY_NO_PROMOTION`

This hotfix fixes the case where LoaderFix3 selected the correct M5 normalized CSV but loaded zero usable rows.

Root cause:

- The selected file was correct: `normalized_twelvedata_XAU_USD_5min_*.csv`.
- The parser did not recognize normalized timestamp columns such as `timestamp_utc`.
- Therefore required OHLC mapping was incomplete and the run ended as `NO_DATA_STOP_NO_PROMOTION`.

Fixes:

- Add robust timestamp aliases: `timestamp_utc`, `utc_timestamp`, `candle_timestamp_utc`, etc.
- Add broader OHLC aliases for normalized/mid/bid/ask variants.
- Add CSV delimiter sniffing.
- Add load diagnostics: fieldnames, normalized fieldnames, selected mapping, sample rows, parse-fail counts, symbol/timeframe filter counts.
- Keep exact timeframe source selection from LoaderFix3.
- No ML, no rescue, no promotion, no paper/live/EA.

Recommended run:

```bash
python3 app/stage47b_liquidity_sweep_reversal_scan.py   --csv data/normalized/normalized_twelvedata_XAU_USD_5min_20260604T060243Z.csv   --timeframe M5   --out reports/stage47b
```
