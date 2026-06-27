# Stage104 Event-Surprise Dataset Readiness

Stage104 is the next data-frontier step after the macro / intraday / COT observer pipeline. It does **not** run thesis discovery. It first verifies whether enough event-surprise data exists to support a lag-safe Stage105 event-thesis scan.

## What it reads

Local event calendar or macro surprise exports in CSV/TSV/TXT/XLSX form. Common accepted schemas include:

- `event_time_utc`, `event`, `actual`, `consensus`
- `date`, `time`, `currency`, `impact`, `event`, `actual`, `forecast`, `previous`

Naive `date+time` values are localized using the config field `assume_naive_timezone` before conversion to UTC. Default is `UTC`; change it only if the source export is known to be in another timezone.

## What it writes

- `data/external_frontiers/event_surprise_normalized.csv`
- `reports/stage104_event_surprise_dataset_readiness/stage104_event_file_inventory.csv`
- `reports/stage104_event_surprise_dataset_readiness/stage104_event_type_counts.csv`
- `reports/stage104_event_surprise_dataset_readiness/stage104_event_data_requirements.csv`

## Readiness gates

Default gates:

- normalized rows >= 300
- accepted US/high-value event rows >= 200
- lag-safe same-event `surprise_z_asof` non-null rows >= 100

If ready, the next stage is Stage105 event-surprise thesis discovery. If not ready, the output tells which data/schema gap remains.

## Hard blocks

Stage104 cannot authorize orders, change MT5/EA files, connect to a broker, or alter the Stage100 observer state.
