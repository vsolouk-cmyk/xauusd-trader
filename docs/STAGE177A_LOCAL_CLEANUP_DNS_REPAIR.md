# Stage177A Local Cleanup — DNS/Curl Repair

The previous Python `urllib` version failed before authentication because
`api.github.com` did not resolve. This version:

- performs explicit DNS and HTTPS preflight;
- uses macOS `curl` for GitHub REST API calls;
- clearly separates DNS/network errors from token/permission errors;
- remains dry-run by default.

## Install

Copy the packaged files into the repository root.

## Network-only check

```bash
cd ~/Desktop/xauusd-trader

python3 tools/stage177a_local_actions_cleanup.py \
  --network-check-only
```

A healthy result includes:

```json
{
  "curl_resolution": "PASS",
  "curl_http_code": "200"
}
```

## Preview

```bash
python3 tools/stage177a_local_actions_cleanup.py \
  --purge-caches
```

## Execute

```bash
python3 tools/stage177a_local_actions_cleanup.py \
  --execute \
  --confirm DELETE_ALL_XAUUSD_ACTIONS_STORAGE \
  --purge-caches
```
