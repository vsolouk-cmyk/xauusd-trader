# Stage49 AMarkets Multi-Timeframe Importer + Next Thesis

Status: `PATCH_READY_NO_PROMOTION`

This package intentionally combines two items that belong together:

1. A reusable AMarkets multi-timeframe importer for periodically updated MT5 exports.
2. A next broker-real, cost-aware thesis diagnostic that uses the imported multi-timeframe data.

No EA, paper-live, live trading, or promotion is authorized by this package.

## Permanent input convention

Default input directory:

```text
~/Downloads
```

Default files:

```text
amarkets_xauusd_1m.csv
amarkets_xauusd_5m.csv
amarkets_xauusd_15m.csv
amarkets_xauusd_30m.csv
amarkets_xauusd_1h.csv
```

The importer also accepts explicit `--m1`, `--m5`, `--m15`, `--m30`, and `--h1` paths.

## Importer outputs

```text
data/broker_normalized/amarkets/amarkets_xauusd_m1_normalized.csv
data/broker_normalized/amarkets/amarkets_xauusd_m5_normalized.csv
data/broker_normalized/amarkets/amarkets_xauusd_m15_normalized.csv
data/broker_normalized/amarkets/amarkets_xauusd_m30_normalized.csv
data/broker_normalized/amarkets/amarkets_xauusd_h1_normalized.csv
data/broker_normalized/amarkets_multitf.sqlite
reports/stage49_broker_multitf/stage49_amarkets_multitf_import_summary.json
reports/stage49_broker_multitf/stage49_amarkets_multitf_import_report.md
reports/stage49_broker_multitf/stage49_amarkets_multitf_import_inventory.csv
```

## Next thesis

Name:

```text
BROKER_REAL_MULTITF_TREND_PERSISTENCE_AFTER_H1_EXPANSION
```

Hypothesis:

```text
After an H1 range-expansion bar, short-horizon directional persistence may exist when M15 and M5 are aligned with the expansion direction and entry spread is below the broker-real cost gate.
```

This is deliberately not a liquidity-sweep reversal thesis. It uses AMarkets broker-real M5/M15/H1 and the Stage48F cost model.

## Thesis diagnostic outputs

```text
reports/stage49_broker_multitf/stage49_multitf_trend_persistence_summary.json
reports/stage49_broker_multitf/stage49_multitf_trend_persistence_report.md
reports/stage49_broker_multitf/stage49_multitf_trend_persistence_candidates.csv
reports/stage49_broker_multitf/stage49_multitf_trend_persistence_event_sample.csv
```

## Guardrails

- No post-hoc rescue of Stage47/48 failed liquidity-sweep family.
- No EA, paper-live, live, or promotion from importer or diagnostic scan.
- If diagnostic survivors appear, they require hard audit.
- If no survivors appear, archive the thesis branch.
