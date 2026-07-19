# Stage176 WGC Vintage Input Contract

## Required semantics

Each row represents the official-sector / central-bank gold demand figure for one quarter as stated in that quarter's original World Gold Council Gold Demand Trends publication.

It is not:

```text
- today's revised historical table;
- monthly reported reserve changes;
- a central-bank reserves level;
- ETF holdings or flows;
- a value inferred from a future annual report.
```

## Required columns

```text
quarter
quarter_end_utc
release_timestamp_utc
official_sector_purchases_tonnes
source_url
source_file
source_sha256
source_kind
extraction_method
extraction_confidence
is_original_publication
notes
```

Aliases accepted by the loader are documented in the code, but the canonical names above should be used.

## Required evidence

For every row:

```text
is_original_publication = true
extraction_confidence >= 0.85
source_sha256 = 64-character SHA-256
source_file exists and matches source_sha256,
  or a traceable official source_url is present
release date is 10–180 days after quarter end
absolute quarterly value <= 600 tonnes
```

If multiple original rows exist for one quarter, the earliest publication is retained only when conflicting values differ by no more than 3 tonnes. Larger conflicts block the audit.

## Coverage

```text
first quarter = 2010Q1
valid quarters >= 56
missing quarters <= 2
```

A shorter series is low-quality for this thesis and is not repaired with revised values.

## Conservative date convention

If the publication source exposes only a date rather than an exact time, store it at `00:00:00Z`. Stage176 will still use the first complete daily price bar strictly after that calendar day, so it does not trade on the publication day's close.

## Template

Use:

```text
data/templates/stage176_wgc_official_sector_vintage_manifest_template.csv
```

The template intentionally contains no historical values. Values must come from original WGC publications or locally cached source snapshots.
