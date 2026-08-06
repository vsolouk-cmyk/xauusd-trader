# XAUUSD Macro Data Readiness Inventory V1

Local-only inventory. It does not download data and has no trading or broker path.

Commands:

```bash
python3 app/xauusd_macro_data_inventory.py preflight --root .
python3 app/xauusd_macro_data_inventory.py run --root .
python3 app/xauusd_macro_data_inventory.py collect --root .
```

Expected artifact:

`~/Downloads/XAUUSD_MACRO_DATA_READINESS_RESULTS.zip`
