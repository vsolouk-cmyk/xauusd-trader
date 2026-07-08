# Stage156 Operational Unifier

Stage156 is a practical operational wrapper for the current demo loop.

It does not create a new trading thesis and it does not send orders. Orders remain delegated to Stage134.

What it does in one command:

1. Checks latest M5 CSV timestamp and applies `--timestamp-shift-hours -3`.
2. Optionally runs an existing DB/timeframe update command via `--db-update-command`.
3. Runs Stage155 risk-guarded active router.
4. Reads Stage155 KV and Stage134 status KV.
5. Optionally refreshes Stage144/145 via `--run-ledger`.
6. Writes `reports/stage156_operational_unifier/stage156_operational_unifier_summary.json`.

Default operational command:

```bash
python3 app/stage156_operational_unifier.py   --root /Users/vahid/Desktop/xauusd-trader   --bars-m5 /Users/vahid/Downloads/xauusd_fundamental_event_inbox/amarkets_xauusd_5m.csv   --score-csv /Users/vahid/Desktop/xauusd-trader/reports/stage150_mtf_separated_validation_discovery/m5/stage150_candidate_scores.csv   --risk-summary /Users/vahid/Desktop/xauusd-trader/reports/stage145_clean_ledger_performance_gate/stage145_clean_ledger_performance_gate_summary.json   --timestamp-shift-hours -3   --max-feature-age-sec 7200   --write-mt5
```

With ledger refresh:

```bash
python3 app/stage156_operational_unifier.py --write-mt5 --run-ledger
```

With an existing DB update command:

```bash
python3 app/stage156_operational_unifier.py   --db-update-command "python3 app/<CURRENT_DB_IMPORTER>.py <ARGS>"   --write-mt5
```

Stage156 intentionally keeps DB update optional because the current Stage150-155 execution route reads M5 CSV directly, while older Stage50-54 DB importers depend on the exact repo script name and command-line interface.
