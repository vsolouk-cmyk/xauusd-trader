# Stage 9B Numeric SSL Resilience Patch

This patch updates:

```text
app/stage9b_macro_numeric_update.py
```

## Problem fixed

On some macOS/Python installations, HTTPS fetches fail with:

```text
SSL: CERTIFICATE_VERIFY_FAILED
unable to get local issuer certificate
```

This is a local certificate-store issue, not a FRED API-key issue.

## Preferred run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage9b_macro_numeric_update --start-date 2022-01-01
```

The updater now tries:

```text
default SSL
certifi SSL if certifi is installed
```

## Local fallback only

If macOS still fails and GitHub is not convenient, use:

```bash
python3 -m app.stage9b_macro_numeric_update --start-date 2022-01-01 --allow-insecure-ssl
```

This disables certificate verification only for the local FRED fetch fallback. It should not be the preferred production setting.

## GitHub Actions

Do not change GitHub workflow. Ubuntu runners normally have a valid certificate store.

## Hard rule

Data only. No EA change, no demo, no paper, no live authorization.
