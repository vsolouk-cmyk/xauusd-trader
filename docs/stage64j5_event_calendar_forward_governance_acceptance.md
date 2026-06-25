# Stage64J5 - Event Calendar Forward-Only Governance Acceptance

This stage formalizes whether the project may proceed to a full-scope feature dataset preflight after ETF and central-bank source completion while the historical event-calendar archive is still unavailable.

It does not run validation, build targets, generate signals, connect to a broker, or authorize paper/live/order paths.

## Decision logic

Stage64J5 allows the next dataset preflight only if:

- ETF source preflight passed in Stage64J1.
- Central-bank source preflight passed in Stage64J1.
- A valid event-calendar forward-only governance manifest exists.
- The event-calendar manifest explicitly blocks historical backtest/event-filter use.

Broker/spot alignment remains required before commercialization or broker XAUUSD validation claims, but it does not block this research-only dataset preflight.

## Hard rule

Forward-only event governance must not be converted into a historical validation feature or post-hoc event filter.
