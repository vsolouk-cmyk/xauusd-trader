# Stage129B persistent download runner and AMarkets pipeline audit

This patch makes the official data downloader persistent/incremental.

Default behavior after this patch:
- If a target output file already exists, is non-empty, and passes content validation, it is skipped.
- The skipped row is logged as `SKIPPED_EXISTING_VALID`.
- `--force-refresh` disables the skip and downloads everything again.
- `--refresh-stale-hours N` refreshes valid files older than N hours.

The combo fundamental pipeline does not import AMarkets broker bars as macro/fundamental features.
It may see AMarkets files through Stage113/Stage114B classification, where they are recognized as `technical_amarkets`.
They remain technical reference-only in the fundamental-event pipeline.

Broker/AMarkets bar import remains a separate broker-normalized path.
