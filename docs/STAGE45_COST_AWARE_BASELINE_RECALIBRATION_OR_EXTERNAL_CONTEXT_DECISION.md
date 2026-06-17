# Stage45_COST_AWARE_BASELINE_RECALIBRATION_OR_EXTERNAL_CONTEXT_DECISION

## Purpose

Stage45 is a decision/recalibration diagnostic after Stage41, Stage42, Stage43, and Stage44 showed no strict or soft shortlist.

It does **not** create trading signals, does **not** promote candidates, and does **not** authorize EA, paper-live, or live trading.

## Why this stage exists

Stage41/42/43 covered H1, M15 intraday, and M15 context/regime thesis families. Stage44 aggregated those outputs and found the dominant blockers:

- no shortlist across recent scans
- cost-adjusted mean edge not sufficient
- quarter/worst-quarter fragility
- weak bootstrap tail/probability
- event scarcity for context-filtered theses
- weak residual versus benchmark
- train/OOS instability
- some concentration risk

Therefore another blind megascan is not the fastest path. The next efficient step is to decide whether the bottleneck is:

1. transaction cost / spread / slippage assumptions,
2. broker CFD feed noise,
3. lack of external macro/news/yields context,
4. rare-event sample scarcity,
5. or simply no robust baseline edge in the tested candle-only thesis space.

## Inputs

Default inputs read from the repo:

```text
reports/stage41/stage41_parallel_thesis_megascan_v2_candidates.csv
reports/stage41/stage41_parallel_thesis_megascan_v2_summary.json

reports/stage42/stage42_parallel_intraday_execution_megascan_v3_candidates.csv
reports/stage42/stage42_parallel_intraday_execution_megascan_v3_summary.json

reports/stage43/stage43_parallel_context_regime_megascan_v4_candidates.csv
reports/stage43/stage43_parallel_context_regime_megascan_v4_summary.json
```

## Outputs

```text
reports/stage45/stage45_cost_aware_baseline_recalibration_summary.json
reports/stage45/stage45_cost_aware_baseline_recalibration.md
reports/stage45/stage45_cost_aware_failure_reasons_long.csv
```

## What it computes

- aggregate numeric profile across recent candidate rows
- failed reason and bucket counts
- cost/slip sensitivity scenarios
- near-miss diagnostic under stricter and looser assumptions
- rough uniform bps improvement required to pass robust numeric gates
- recommendation for the next allowed branch

## Cost/slip scenario logic

The script does not reconstruct true gross returns. It uses an explicit sensitivity approximation:

```text
adjusted_metric = observed_metric + assumed_cost_saving_bps
```

This is diagnostic only. Any apparent pass under lower-cost scenarios is **not promotion**. It only indicates that feed/spread/slippage realism may need an audit.

## Promotion lock

Always locked:

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

## Allowed next outcomes

Stage45 may recommend one of these paths:

```text
Stage45B_EXTERNAL_CONTEXT_AND_REFERENCE_FEED_DECISION
Stage45C_FEED_AND_TRANSACTION_COST_REALISM_AUDIT
Stage45D_RARE_EVENT_SAMPLE_SIZE_DECISION
Stage46 new scan only after Stage45 selects an evidence-based direction
```

## Not allowed

```text
Stage41B/Stage42B/Stage43B without strict shortlist
post-hoc filtering of weak hours/months/years/quarters/context states
EA/paper/live from archived rows
ML before a robust cost-aware baseline exists
```

## Run

```bash
python3 scripts/stage45_cost_aware_baseline_recalibration.py --print-summary
```
