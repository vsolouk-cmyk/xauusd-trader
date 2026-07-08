# Stage159 Locked-Family Repair Discovery

Stage159 is an offline repair-discovery audit after Stage145/157 froze order routing for negative demo expectancy. It does **not** write an execution KV and does **not** send orders.

## Why this exists

The failed path was not simply an MT5 execution issue. Stage155/156 selected active rules from a cached shortlist and routed them to demo, but the result mixed several families and contexts. That produced router-hopping risk and a ledger that was not a clean test of a stable rule or family.

Stage159 changes the research question:

- Do not ask: “Which candidate is active right now?”
- Ask: “Which family remains robust across chronological folds, sessions, and volatility regimes, and is not simply fitted to the latest market pocket?”

## Macro and regime note

Stage159 can inspect optional macro files, but it does not fabricate macro features. If macro files are missing or stale, the summary will mark the result as `macro_blind`. In that state, a technical shortlist may be useful for review, but it should not be promoted directly into a new demo writer without a macro/regime refresh.

Supported optional macro arguments:

- `--macro-dxy`
- `--macro-real-yield`
- `--macro-us10y`
- `--macro-required`

If `--macro-required` is used and macro files are missing/stale, Stage159 returns a no-demo-release decision.

## Outputs

- `reports/stage159_locked_family_repair_discovery/stage159_locked_family_repair_discovery_summary.json`
- `reports/stage159_locked_family_repair_discovery/stage159_locked_family_shortlist.csv`
- `reports/stage159_locked_family_repair_discovery/stage159_family_repair_summary.csv`
- `reports/stage159_locked_family_repair_discovery/stage159_session_repair_summary.csv`
- `reports/stage159_locked_family_repair_discovery/stage159_candidate_replay_scores.csv`

## Operating decision

Keep Stage157 freeze active while Stage159 is reviewed. If Stage159 finds no robust family, do not create another active router. Pivot to stricter discovery, higher timeframe, or macro-regime thesis.
