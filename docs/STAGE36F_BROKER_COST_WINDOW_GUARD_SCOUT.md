# Stage36F — Broker Cost / Time-Window Guard Scout

This patch adds `app/stage36f_broker_cost_window_guard_scout.py`.

Purpose:

- Continue from Stage36E, where market-structure continuation showed strong raw PF but failed drawdown.
- Test whether broker spread, rollover, hour, and session filters can reduce drawdown enough to create a strict research-review candidate.
- Keep Stage35C h13/h14 confirmation in background.
- Authorize no EA, paper-live, or orders.

Inputs:

- `data/local/xauusd_local_store.sqlite`
- `data/reports/stage36e_market_structure_sweep_reclaim_scout/stage36e_signal_ledger.csv`
- `data/reports/stage36e_market_structure_sweep_reclaim_scout/stage36e_summary.json`

Outputs:

- `data/reports/stage36f_broker_cost_window_guard_scout/stage36f_broker_cost_window_guard_scout.md`
- `data/reports/stage36f_broker_cost_window_guard_scout/stage36f_summary.json`
- CSV audit and queues.
