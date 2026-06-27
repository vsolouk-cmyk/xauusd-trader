# Stage95 COT Official Dataset Builder

Stage95 builds a normalized COT positioning dataset for COMEX Gold from official CFTC Disaggregated COT historical files.

It does not run thesis discovery, does not change MT5/EA files, and cannot authorize orders.

## Preferred source

Official CFTC Historical Compressed COT files:

- Disaggregated Futures-and-Options Combined text ZIPs: `com_disagg_txt_<year>.zip`
- Disaggregated Futures Only text ZIPs: `fut_disagg_txt_<year>.zip`

The builder filters Gold COMEX contract code `088691` and normalizes Managed Money long/short/open interest fields.

## Outputs

- `data/external_frontiers/cot_positioning_normalized.csv`
- `reports/stage95_cot_official_dataset_builder/stage95_cot_official_dataset_builder_summary.json`
- `reports/stage95_cot_official_dataset_builder/stage95_cot_file_inventory.csv`
- `reports/stage95_cot_official_dataset_builder/stage95_cot_data_requirements.csv`
- `reports/stage95_cot_official_dataset_builder/stage95_thesis_queue.csv`

## Download modes

Default config does not download. It scans local files in repo and Downloads.

To download official files directly, run with `--download`. This requires internet/VPN access to CFTC.

```bash
python3 app/stage95_cot_official_dataset_builder.py \
  --root . \
  --config configs/stage95_cot_official_dataset_builder.json \
  --out reports/stage95_cot_official_dataset_builder \
  --download
```

## Hard blocks

- NO_AUTOMATED_ORDER
- NO_PAPER_ORDER
- NO_BROKER_CONNECTION
- NO_EA_PROMOTION
- NO_PAPER_LIVE
- NO_LIVE
- NO_ORDER_AUTHORIZATION_FROM_STAGE95
- NO_THRESHOLD_TUNING_FROM_STAGE95_DATA_BUILDER
- NO_DIRECT_MT5_OR_EA_CHANGE_FROM_STAGE95
