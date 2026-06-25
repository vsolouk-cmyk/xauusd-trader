# Stage64J1 - Full-Scope P1/P2 Source Acquisition Preflight

Stage64J1 is a governance and source-preflight stage. It does not fetch data by default, does not run validation, and does not authorize orders.

## Purpose

Stage64I killed the reduced-scope P0+VIX path as a promotion or continued-validation path. Stage64J allowed only two continuations:

1. Complete full-scope source acquisition under lag-safe rules.
2. Stop the macro-regime program.

Stage64J1 checks whether the required full-scope P1/P2 source files are present, schema-compatible, lag-safe, sufficiently populated, and coverage-compatible.

## Required files

- `data/macro_regime/raw/gold_etf_holdings_or_flows.csv`
- `data/macro_regime/raw/central_bank_gold_demand_monthly_quarterly.csv`
- `data/macro_regime/raw/macro_event_calendar_archive.csv`
- `data/macro_regime/raw/broker_or_spot_gold_d1_ohlc_2011_present.csv`

The broker/spot file is not required to explain the Stage64H failure, but it is required before broker-XAUUSD commercialization claims.

## Event calendar governance

The event calendar can only be used historically if it is known-before-event. If a reliable historical event archive cannot be acquired, the project may later decide to restrict event-calendar risk to forward-only governance. That change must be explicit in config and cannot be used to rescue Stage64H.

## Outputs

- `stage64j1_full_scope_p1_p2_source_acquisition_preflight_summary.json`
- `stage64j1_full_scope_p1_p2_source_acquisition_preflight_report.md`
- `stage64j1_source_preflight_checks.csv`
- `stage64j1_blocked_sources.csv`
- `stage64j1_source_template_manifest.json`

## Hard blocks

Stage64J1 blocks paper-order, EA promotion, paper-live, live, broker connection, full-scope validation claims, reduced-scope rescue filtering, and new intraday scans.
