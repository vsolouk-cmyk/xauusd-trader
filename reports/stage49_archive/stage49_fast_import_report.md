# Stage49 AMarkets Fast Persistent MultiTF Importer

- status: `IMPORT_COMPLETE`
- changed_timeframes: `5`
- skipped_timeframes: `0`
- db: `/Users/vahid/Desktop/xauusd-trader/data/broker_normalized/amarkets_multitf.sqlite`

## Timeframes

- M1: status=`IMPORTED` rows_in_db=`1460694` mode=`full_refresh` path=`/Users/vahid/Downloads/amarkets_xauusd_1m.csv`
- M5: status=`IMPORTED` rows_in_db=`292454` mode=`full_refresh` path=`/Users/vahid/Downloads/amarkets_xauusd_5m.csv`
- M15: status=`IMPORTED` rows_in_db=`97536` mode=`full_refresh` path=`/Users/vahid/Downloads/amarkets_xauusd_15m.csv`
- M30: status=`IMPORTED` rows_in_db=`48775` mode=`full_refresh` path=`/Users/vahid/Downloads/amarkets_xauusd_30m.csv`
- H1: status=`IMPORTED` rows_in_db=`24406` mode=`full_refresh` path=`/Users/vahid/Downloads/amarkets_xauusd_1h.csv`

## Notes

This importer is persistent. Unchanged files are skipped. Safely appended files are imported from the previous byte offset. Full refresh is used when the file appears rewritten or incompatible with the previous manifest.

No trading signal, promotion, EA, paper-live, or live action is authorized by this importer.
