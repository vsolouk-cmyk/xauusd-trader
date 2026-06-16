# Stage 6A v2 — Twelve Data resilience

## Fixes

- `--fetch-twelve` no longer crashes on SSL/certificate errors.
- Placeholder keys like `YOUR_KEY_HERE` are rejected early.
- The report now includes a clear `fetch_error`, `api_error`, or `invalid_or_placeholder_api_key` status.
- Optional JSON import is available with `--twelve-json-dir`.

## Normal local persistence

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage6a_local_data_store
cat data/reports/stage6a_local_store/stage6a_local_store.md
```

## Twelve Data fetch

Use your real API key, not the placeholder:

```bash
export TWELVE_DATA_API_KEY='PASTE_REAL_KEY'
python3 -m app.stage6a_local_data_store --fetch-twelve
cat data/reports/stage6a_local_store/stage6a_local_store.md
```

If macOS Python still reports certificate verification failure, fix Python certificates or import JSON files manually.

## Optional manual JSON import

Save Twelve Data API responses into a folder such as:

```text
~/Downloads/twelve_data/
  twelve_xauusd_1h.json
  twelve_xauusd_1m.json
```

Then import them:

```bash
python3 -m app.stage6a_local_data_store --twelve-json-dir ~/Downloads/twelve_data
cat data/reports/stage6a_local_store/stage6a_local_store.md
```

## Last-resort diagnostic

`--twelve-allow-insecure-ssl` bypasses SSL verification and should not be the default operational path.

```bash
python3 -m app.stage6a_local_data_store --fetch-twelve --twelve-allow-insecure-ssl
```

Hard rule: no order authorization.
