# Article 1 Data-Contract Preflight — Runbook

## Purpose

This preflight resolves the Stage 177C scope conflict without rewriting its historical BLOCK decision. It validates only the frozen 2015–2024 AMarkets/Dukascopy reference window and does not inspect any strategy performance.

## Install the script

After downloading `article1_data_contract_preflight.py` to `~/Downloads`:

```bash
cd /Users/vahid/Desktop/xauusd-trader

mkdir -p tools/article_publication
mv ~/Downloads/article1_data_contract_preflight.py \
  tools/article_publication/article1_data_contract_preflight.py

chmod +x tools/article_publication/article1_data_contract_preflight.py
```

## Run

```bash
cd /Users/vahid/Desktop/xauusd-trader

python3 tools/article_publication/article1_data_contract_preflight.py \
  --project-root /Users/vahid/Desktop/xauusd-trader

preflight_rc=$?
echo "PREFLIGHT_EXIT_CODE=$preflight_rc"
```

Exit code `0` means the complete 2015–2024 data contract passed, possibly with a documented alignment warning. Exit code `2` is a deliberate fail-closed outcome; the result ZIP is still produced and must be sent for diagnosis.

## Expected output

The terminal prints one of:

```text
PASS_ARTICLE1_2015_2024_REFERENCE_DATA_CONTRACT
```

or the warning-qualified pass:

```text
PASS_ARTICLE1_2015_2024_REFERENCE_DATA_CONTRACT_WITH_ALIGNMENT_WARNING
```

or:

```text
BLOCK_ARTICLE1_REFERENCE_DATA_CONTRACT
```

It also creates a small upload file in Downloads:

```text
~/Downloads/XAUUSD_ARTICLE1_DATA_CONTRACT_PREFLIGHT_<UTC_TIMESTAMP>.zip
```

Upload that ZIP in either PASS or BLOCK state. No database or raw CSV needs to be uploaded again.

## Optional Git checkpoint after the result has been reviewed

Do not commit the generated report yet. The script itself may be staged after successful review:

```bash
cd /Users/vahid/Desktop/xauusd-trader
git status --short
```

The exact commit command will be provided only after the returned artifact is audited.
