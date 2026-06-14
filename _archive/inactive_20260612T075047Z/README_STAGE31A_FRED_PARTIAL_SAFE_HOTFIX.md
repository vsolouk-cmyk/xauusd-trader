# Stage31A FRED Downloader Partial-safe Hotfix

## Purpose

Fixes GitHub Action failure caused by a transient FRED HTTP 504 on one series. The downloader now retries each series independently, writes a manifest, preserves any existing real CSV if refresh fails, and does not abort the whole workflow unless strict mode is enabled.

## Files

- `.github/workflows/xauusd_fred_exogenous.yml`
- `tools/download_fred_exogenous.py`
- `docs/STAGE31A_GITHUB_FRED_EXOGENOUS_WORKFLOW.md`

## Usage

```bash
cd ~/Desktop/xauusd-trader
unzip -o ~/Downloads/xauusd_stage31a_fred_partial_safe_hotfix.zip -d .

git add -A
git commit -m "Make FRED exogenous refresh partial safe"
git pull --rebase origin main
git push
```

Then run `XAUUSD FRED Exogenous Refresh` manually from GitHub Actions with `strict=0`.
