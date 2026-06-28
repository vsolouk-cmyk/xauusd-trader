# Stage113 Fundamental + Economic Event Inbox Unifier

## Purpose

Stage113 creates a single intake box for all manual fundamental and event-calendar downloads before any event-aware discovery stage.

This fixes the fragmented workflow where FRED/COT/central-bank/ETF/event files are downloaded manually, scattered in Downloads, and then imported by separate stage scripts.

## Scope

- Creates a single Downloads inbox.
- Creates source buckets under that inbox.
- Copies downloaded files into ignored project folders.
- Produces a manifest and download guide.
- Appends data paths to `.gitignore`.
- Does not normalize domain-specific schemas yet.
- Does not touch MT5, EA, broker, paper order, or live order components.

## Manual inbox path

```text
~/Downloads/xauusd_fundamental_event_inbox/
```

## Recommended bucket layout

```text
events/fred
events/bls
events/bea
events/census
events/fomc
events/treasury
cot/cftc
gold_etf/wgc
gld/spdr
central_bank_gold
fred_macro
macro_misc
```

## Project-side ignored data path

```text
data/fundamental_event_inbox/
```

## Run

```bash
cd /Users/vahid/Desktop/xauusd-trader

python3 app/stage113_fundamental_event_inbox_unifier.py   --root /Users/vahid/Desktop/xauusd-trader
```

## Outputs

```text
reports/stage113_fundamental_event_inbox_unifier/stage113_fundamental_event_inbox_unifier_summary.json
reports/stage113_fundamental_event_inbox_unifier/stage113_fundamental_event_inbox_unifier_report.md
reports/stage113_fundamental_event_inbox_unifier/stage113_download_guide.md
reports/stage113_fundamental_event_inbox_unifier/stage113_download_guide.csv
data/fundamental_event_inbox/manifests/stage113_fundamental_event_file_manifest.csv
```

## Operational rule

Before an event-aware or fundamental-aware discovery stage, first run Stage113 and inspect the manifest. Then write source-specific normalizers only for files that are actually present.

## No-order block

Stage113 is infrastructure only. It cannot authorize paper/live/demo orders.
