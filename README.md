# XAUUSD Controlled-Paper Operational Freshness Guard

This overlay repairs an operational safety gap discovered after the first successful controlled-paper run: the logger reported `CONTROLLED_PAPER_ACTIVE_PAPER_LOG_ONLY_NO_BROKER` even though the newest AMarkets data and Stage180 summary were several hours old.

The repair adds a mandatory, non-disableable freshness gate. During an expected-open XAUUSD market, the logger blocks all ledger mutation unless:

- the Stage180 summary is at most 180 minutes old;
- the aligned H1 table is at most 180 minutes old;
- the AMarkets spread source is at most 90 minutes old;
- no required timestamp is more than 15 minutes in the future.

During the conservative weekend/daily maintenance closure schedule, age limits are deferred because new bars are not expected, but future-clock anomalies remain blocking.

A stale run still writes `controlled_paper_summary.json`, with decision:

`CONTROLLED_PAPER_BLOCKED_STALE_MARKET_DATA_NO_INGEST`

It does not insert signals, open positions, resolve positions, or alter risk state.

No model, threshold, H1 row semantics, spread guard, event guard, risk limit, existing ledger state, or broker boundary is changed.

See `docs/XAUUSD_CONTROLLED_PAPER_RUNBOOK.md` for installation and operation.
