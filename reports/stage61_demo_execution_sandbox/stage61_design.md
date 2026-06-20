# Stage61 Demo Execution Sandbox Design

Stage61 is a demo-only operational harness. Its purpose is to test MT5 order plumbing, spread gate behavior, position limits, max-hold cleanup, and logging on a demo account.

It is not a statistical edge validator. Forward-shadow evidence remains required for edge promotion.

## Components

- `app/stage61_demo_signal_exporter.py`: reads Stage58B true-forward shadow state and exports pending non-backfill signals to CSV.
- `mql5/Experts/Stage61_DemoExecutionHarness.mq5`: demo-only MT5 EA that polls a CSV file and may place tiny demo-only orders when explicitly enabled.
- `configs/stage61_demo_execution_sandbox.json`: tiny-risk defaults and no-live policy.

## Hard blocks

- Python exporter never connects to a broker.
- EA refuses non-demo accounts by default.
- EA input `AllowTrading` defaults to `false`.
- Live/paper-live remains `NO_GO`.
