# Stage171G — Weekend Unattended Forward Operations

## Purpose

Keep acquisition and shadow infrastructure moving while XAUUSD is closed, without permitting orders.

## GDELT corrections

- The DOC API is a rolling recent-window interface, not a dependable multi-year backfill source.
- Scheduled runs fetch only the last seven days in one sequential request per profile.
- A persistent point store retains older observations locally on the GitHub data branch.
- Only successful profile/time ranges replace prior observations.
- HTTP 429, timeout, or parsing failures retain prior data rather than overwriting it with zeros.
- Daily CSV shards provide inspectable, persistent lineage.

## Macro correction

The archived Stage64K builder expects archived Stage64 reports at their former active paths. The compatibility materializer copies only missing archived Stage64 report files into the ignored reports tree before Stage64K runs. It never overwrites active files.

## Execution policy

- Data collection and shadow logging may run unattended.
- Order routing, demo release, and threshold optimization remain disabled.
- A stale or failed macro rebuild blocks H64L shadow evaluation.
