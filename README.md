# XAUUSD Controlled-Paper Contract/Test-Isolation Repair

This overlay repairs two defects exposed by the first spread-source repair:

1. the unit fixture inherited the production `~/Downloads/...` spread candidates and could read the user's real AMarkets file, so the deliberate missing-file test was not isolated;
2. the Stage177C contract gate used brittle raw-string equality and did not report the decision/semantic evidence needed to diagnose a valid contract.

The repaired logger now:

- pins every unit fixture to its own temporary spread path;
- validates the Stage177C contract from exact substantive semantics;
- normalizes harmless decision/calendar/contract casing and whitespace;
- requires the locked `-120/-180` EU mapping, exact timestamp-shift semantics, and `selection_used_holdout=false`;
- retains fail-closed rejection for any actual shift, calendar, semantic, or holdout mismatch;
- preserves the AMarkets raw-CSV parity audit, spread guard, Stage180 frozen observation contract, and no-broker boundary.

No candidate, model, threshold, H1 entry/exit rule, risk limit, event guard, ledger data, or order authorization is changed.

See `docs/XAUUSD_CONTROLLED_PAPER_RUNBOOK.md` for installation and operation.
