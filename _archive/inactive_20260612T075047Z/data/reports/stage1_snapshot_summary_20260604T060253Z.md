# XAUUSD Stage 1 Snapshot Summary

- Generated at UTC: `2026-06-04T06:02:15.674642+00:00`
- Provider: `twelvedata`
- Symbol: `XAU/USD`
- Overall OK: `True`

## Interval quality

| Interval | OK | Rows | Missing ratio | Duplicate timestamps | Spread available | Start UTC | End UTC |
|---|---:|---:|---:|---:|---:|---|---|
| 1min | True | 500 | 0.000000 | 0 | False | 2026-06-03T21:42:00+00:00 | 2026-06-04T06:01:00+00:00 |
| 5min | True | 500 | 0.000000 | 0 | False | 2026-06-02T12:25:00+00:00 | 2026-06-04T06:00:00+00:00 |
| 15min | True | 500 | 0.000000 | 0 | False | 2026-05-30T01:15:00+00:00 | 2026-06-04T06:00:00+00:00 |
| 1h | True | 500 | 0.000000 | 0 | False | 2026-05-14T11:00:00+00:00 | 2026-06-04T06:00:00+00:00 |

## Cost model

Twelve Data Stage 1 does not provide broker bid/ask spread in this pipeline.
Baseline testing must therefore use conservative assumed costs and later validate with MT5/broker feed.

- `spread_available`: `False`
- `assumed_spread_usd`: `0.3`
- `assumed_slippage_usd`: `0.05`

## Files

- `1min`
  - raw: `data/raw/twelvedata_XAU_USD_1min_20260604T060238Z.json`
  - normalized: `data/normalized/normalized_twelvedata_XAU_USD_1min_20260604T060238Z.csv`
  - quality: `data/reports/quality_normalized_twelvedata_XAU_USD_1min_20260604T060238Z.json`
- `5min`
  - raw: `data/raw/twelvedata_XAU_USD_5min_20260604T060243Z.json`
  - normalized: `data/normalized/normalized_twelvedata_XAU_USD_5min_20260604T060243Z.csv`
  - quality: `data/reports/quality_normalized_twelvedata_XAU_USD_5min_20260604T060243Z.json`
- `15min`
  - raw: `data/raw/twelvedata_XAU_USD_15min_20260604T060247Z.json`
  - normalized: `data/normalized/normalized_twelvedata_XAU_USD_15min_20260604T060247Z.csv`
  - quality: `data/reports/quality_normalized_twelvedata_XAU_USD_15min_20260604T060247Z.json`
- `1h`
  - raw: `data/raw/twelvedata_XAU_USD_1h_20260604T060251Z.json`
  - normalized: `data/normalized/normalized_twelvedata_XAU_USD_1h_20260604T060251Z.csv`
  - quality: `data/reports/quality_normalized_twelvedata_XAU_USD_1h_20260604T060251Z.json`
