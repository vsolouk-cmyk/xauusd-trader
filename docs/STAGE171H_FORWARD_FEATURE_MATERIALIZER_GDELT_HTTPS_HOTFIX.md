# Stage171H — Forward H64L Feature Materializer + GDELT HTTPS Fallback

## Decision

The archived Stage64K builder is retained as historical research evidence but removed from the critical forward-shadow chain. A successful historical rebuild does not imply fresh forward features.

Stage171H builds the exact four H64L inputs from current source data, applies mechanical as-of conventions, and blocks shadow logging on missing, stale, or implausible source data.

## H64L feature sources

- `gold_sma20_over_50`: completed AMarkets M5 daily bars; current UTC day excluded.
- `dxy_ret_20d`: freshest discoverable DXY daily source, through the day before the gold feature date.
- `real_yield_change_20d`: freshest discoverable real-yield daily source, through the day before the gold feature date.
- `etf_flow_tonnes_3m`: change in WGC total ETF holdings over three calendar months. This avoids the implausible `12349` value previously logged from the old derived dataset.

No SPDR substitution and no threshold change are allowed.

## GDELT

The local importer first uses the configured Git remote. If the repository remote is SSH and that transport fails, it derives the equivalent HTTPS URL and fetches the persistent `automation/gdelt-latest` branch without changing the working tree or configured remote.

The GitHub workflow remains four-hourly and uses one worker, five retries, 20-second backoff, and 20-second request spacing. The persistent Stage166G store retains prior observations for failed 429 ranges.

## Safety

- No MT5 signal is written.
- No order is routed.
- No demo/live release is authorized.
- No H64L threshold is optimized.
- Shadow is blocked if the new forward feature snapshot is not source-valid.
