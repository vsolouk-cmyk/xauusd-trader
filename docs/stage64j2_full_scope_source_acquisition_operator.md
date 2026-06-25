# Stage64J2 - Full-Scope Source Acquisition Operator Plan

Stage64J2 is an operator/planning stage only. It does not fetch external data, does not validate, does not create signals, and does not authorize orders.

## Purpose

After Stage64J1 confirmed that full-scope source acquisition is blocked, Stage64J2 creates strict templates and an acquisition checklist for:

- Gold ETF holdings/flows
- Central-bank gold demand / official reserve-change prior
- Historical event calendar or forward-only event governance
- Broker/spot gold D1 alignment source

## Lag policies

- ETF holdings/flows: next session after publication unless exact timestamp proves earlier.
- Central-bank demand: official release lag only; slow prior, not timing signal.
- Event calendar: historical filtering only if the archive proves events were known before scheduled time; otherwise forward-only governance.
- Broker/spot D1: completed daily bar/session close only.

## Prohibited work

No reduced-scope retest, no rescue filtering, no intraday scan, no order path, no EA promotion, and no paper/live path.
