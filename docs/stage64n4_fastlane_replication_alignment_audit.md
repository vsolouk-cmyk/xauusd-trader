# Stage64N4 Fastlane Replication and Alignment Audit

This stage consolidates the next no-order replication/alignment work into a single fastlane run.
It is not a tuning stage, not a broad validation scan, not a broker connector, and not an order path.

## What it does

- Builds an immutable reproduction manifest for Stage64K/Stage64L/Stage64M/Stage64N3 inputs.
- Independently recomputes the H64L_H1_FULL_MACRO_TAILWIND_LONG / 120-day survivor from the Stage64K dataset and config rules.
- Compares the independent recomputation against the predeclared Stage64M headline statistics.
- Declares the broker/spot D1 alignment contract required before any broker XAUUSD claim.
- Retains event-calendar forward-only governance and blocks historical event filtering.

## What it does not do

- No new hypothesis scan.
- No parameter retuning.
- No rescue filter.
- No historical event-calendar filter.
- No paper-order, paper-live, live, EA promotion, or broker connection.
