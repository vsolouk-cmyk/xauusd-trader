# XAUUSD Stage38 Transfer Pack — Gold Market Thesis Reconstruction

Generated UTC: 2026-06-16T10:43:46Z

## 1. Purpose of this transfer pack

This package is for opening a new ChatGPT session and continuing the XAUUSD/gold project from a clean strategic point.

The project is no longer in variant-mining mode. The next phase is **Stage38A — Gold Market Thesis Reconstruction**, a market-structural and thesis-reconstruction phase. It should not start with new code, new backtests, new discovery factories, or additional Stage36-style branches.

The immediate reason for switching sessions is twofold:

1. The current conversation is very large and should be closed before context degradation.
2. A new strategic phase is beginning after a major cleanup of the repository and a branch-level failure decision.

## 2. Mandatory response style and operating rules

- Always begin project responses with: **چپ‌چین ادامه می‌دهم.**
- Use Persian unless the user explicitly asks otherwise.
- Keep formatting simple.
- Do not use HTML or decorative alignment tricks.
- Do not use explanatory boxes.
- Use code blocks only for terminal commands, paths, logs, or raw file contents.
- Keep answers technically complete; do not become shallow.
- Avoid unnecessary confirmation questions when the next technical step is clear.
- Always include a clear next step.
- For executable changes, provide downloadable patches and safe copy/paste commands.
- Use safe git flow only:
  - `git add -A`
  - `git commit -m "..."`
  - `git pull --rebase origin main`
  - `git push`
- No EA, no paper-live, no order authorization unless a later gate explicitly authorizes it.
- Monitor session length. If the session becomes heavy or a major phase begins, tell the user to move to a new session and provide a transfer package.

## 3. Current strategic conclusion

The project should **not** be abandoned like the crypto branch yet, but the prior approach should not continue.

The main conclusion from the technical project and senior analyst critique is:

- The implementation has been repeatedly checked and is not the primary suspected bottleneck.
- The probable bottleneck is the **upstream market framing**:
  - weak Gold Market Map,
  - insufficient regime definition,
  - raw macro features without conditional reaction logic,
  - missing event surprise magnitude,
  - missing positioning/flow layers,
  - incomplete trade construction,
  - and insufficient multi-timeframe hierarchy.

The project has not proven that gold is untradeable. It has shown that **the current thesis set and feature set were insufficient** to produce an executable, robust XAUUSD candidate.

## 4. Repository status after cleanup

The repository has been cleaned before Stage38.

Current minimal structure reported by the user:

```text
.
./.github
./.github/workflows
./.gitignore
./app
./app/.gitkeep
./app/__init__.py
./app/__pycache__
./app/providers
./app/stage32f_amarkets_csv_preflight.py
./app/stage32f_extended_shadow_refresh_cycle.py
./app/stage33d_strict_cost_aware_pre_paper_gate.py
./app/stage33e_short_confirmation_recency_filter.py
./app/stage35a_targeted_variant_generator.py
./app/stage35b_strict_variant_backtest_queue_evaluator.py
./app/stage35c_forward_confirmation_trigger_queue_pruner.py
./app/telegram_notify.py
./app/xauusd_collect.py
./app/xauusd_data_quality.py
./app/xauusd_normalize.py
./app/xauusd_sqlite_store.py
./app/xauusd_store_backfill.py
./app/xauusd_store_refresh.py
./configs
./configs/backfill.yaml
./configs/data_source.yaml
./configs/persistent_store.yaml
./configs/project.yaml
./configs/second_source.yaml
./data
./data/exogenous
./data/local
./data/macro
./data/normalized
./data/raw
./data/reports
./data/store
./docs
./docs/CACHE_AND_ARTIFACT_POLICY.md
./docs/DATA_SOURCE_DECISION.md
./docs/PERSISTENT_DATA_STORE.md
./docs/PROJECT_RULES.md
./docs/SQLITE_STORE_AND_WORKFLOW_CHAIN.md
./docs/STAGE32F_HF1_AMARKETS_CSV_PREFLIGHT_GATE.md
./docs/STAGE33E_SHORT_CONFIRMATION_RECENCY_FILTER.md
./docs/STAGE35C_FORWARD_CONFIRMATION_TRIGGER_QUEUE_PRUNER.md
./docs/STAGE37A_NONOVERLAP_RISK_NORMALIZATION_AUDIT.md
./requirements.txt
./tests
./tests/.gitkeep
./tools
./tools/archive_inactive_xauusd_artifacts.py
./tools/download_fred_exogenous.py
./tools/install_fred_artifact.py
```

`app/__pycache__` may reappear after Python execution and is not meaningful. It can be removed with:

```bash
cd ~/Desktop/xauusd-trader
find app tools -type d -name "__pycache__" -prune -exec rm -rf {} +
```

## 5. Minimal monitor status

The minimal Stage35C monitor runner has been tested successfully.

Uploaded latest monitor state:

```text
RUN_STATUS=OK
START_UTC=2026-06-16T10:35:53Z
END_UTC=2026-06-16T10:38:20Z
REPO_DIR=/Users/vahid/Desktop/xauusd-trader
PREFLIGHT_RC=0
REFRESH_RC=0
STAGE35C_RC=0
AUTO_RERUN_GATES=0
AUTO_RERUN_EXECUTED=0
STRICT_RERUN_RC=0
STAGE35C_SUMMARY_FOUND=true
STAGE35C_DECISION=STAGE35C_WAIT_FOR_MORE_FORWARD_EVENTS_RESEARCH_ONLY
STAGE35C_NEW_SIGNAL_COUNT=0
STAGE35C_MIN_NEW_EVENTS=5
STAGE35C_ACTION_REQUIRED=false
NO_STAGE36=true
NO_STAGE37=true
NO_DISCOVERY=true
NO_VARIANT_MINING=true
NO_EA_CHANGE=true
NO_PAPER_LIVE=true
NO_ORDER_AUTHORIZATION=true
LOG_FILE=/Users/vahid/Desktop/xauusd-trader/data/reports/stage35c_minimal_monitor/stage35c_minimal_monitor.log
```

Interpretation:

- The monitor is healthy.
- No Stage36/37/discovery/variant mining is being called.
- Stage35C still has `new_signal_count = 0`, minimum required is `5`.
- No action is currently required from Stage35C.
- No execution transition is authorized.

## 6. Current active components

### Keep active / available

- `stage32f_amarkets_csv_preflight.py`
- `stage32f_extended_shadow_refresh_cycle.py`
- `stage33d_strict_cost_aware_pre_paper_gate.py`
- `stage33e_short_confirmation_recency_filter.py`
- `stage35a_targeted_variant_generator.py`
- `stage35b_strict_variant_backtest_queue_evaluator.py`
- `stage35c_forward_confirmation_trigger_queue_pruner.py`
- data store utilities:
  - `xauusd_sqlite_store.py`
  - `xauusd_data_quality.py`
  - `xauusd_normalize.py`
  - `xauusd_collect.py`
  - `xauusd_store_refresh.py`
  - `xauusd_store_backfill.py`
- FRED/exogenous tools:
  - `tools/download_fred_exogenous.py`
  - `tools/install_fred_artifact.py`

### Do not revive automatically

- Stage36 branches
- Stage37 branches
- discovery factories
- variant mining
- old shadow suite wrappers
- old MQL5 dry-run artifacts
- old GitHub workflows
- old scheduler runner

## 7. Project history condensed

### Early path

The project began with a baseline-first XAUUSD approach using broker/manual data, GitHub Actions, MT5/EA dry-run concepts, and local SQLite storage. The initial goal was a commercially usable systematic gold strategy.

The project progressively tested:

- baseline signal behavior,
- broker-time and session behavior,
- event-aware guards,
- macro/exogenous context,
- forward shadow tracking,
- dense forward variants,
- strict cost-aware gates,
- short confirmation gates,
- alternative branches after degradation.

### Stage31 — Exogenous macro path

Stage31 tested exogenous/macro features. One candidate was historically strong but low-cadence and remained only on a watchlist. The macro feature ingestion path did not produce a robust actionable transition.

Important outcome:

- Exogenous/macros were not discarded completely.
- They remain important for Stage38, but prior use was too raw and context-free.

### Stage32–35 — Dense forward and h13/h14 path

A handoff/calendar-style family became the main live research thread.

Key status:

- h13/h14 showed promising behavior but degraded in recent forward confirmation.
- Stage35C now waits for additional new forward events.
- Current `new_signal_count = 0`, `min_new_events = 5`.
- No promotion is allowed until sufficient forward confirmation exists and strict gates pass.

### Stage36 — New thesis branch sweep

Stage36 was launched because h13/h14 was pending/weak and the project needed a distinct thesis branch.

Branches tested:

1. Session/regime baseline.
2. Event-risk/no-news guard.
3. Volatility compression breakout/fade.
4. Market-structure sweep/reclaim.
5. Broker cost/time-window guard.

Outcome:

- None produced strict review-ready rows.
- The strongest raw edge was market-structure high sweep continuation long, especially roll48 high sweep continuation.
- However, drawdown and risk normalization blocked promotion.

### Stage37A — Branch-level decision / non-overlap risk normalization

Stage37A tested whether Stage36 structure drawdown was inflated by signal overlap.

Outcome:

- `total_strict_review_ready_rows = 0`
- `total_background_rows = 88`
- `nonoverlap_pass_rows = 0`
- `background_watchlist_rows = 20`
- top background variant:
  - `stage36e_roll48_high_sweep_continuation_long_h8`

Decision:

- No strict review-ready candidate exists.
- Do not continue mining the same Stage36 branches.
- Keep Stage35C and background watchlists only as monitors.
- Begin Stage38A: thesis reconstruction before further code.

## 8. Senior analyst critique to carry forward

A separate senior analyst review criticized the project from outside the pipeline logic.

Main critique:

- The project treated XAUUSD as a pattern-mining problem.
- Gold should be treated as a macro-policy, narrative-driven, liquidity-sensitive instrument.
- Raw DXY, real yield, VIX, oil, SPX columns are not enough.
- The missing layer is **conditional reaction logic**:
  - CPI surprise can be bullish for gold in an inflation-hedge regime,
  - bearish in a rate-hike-fear regime,
  - neutral in a soft-landing regime.
- Event labels are insufficient; event surprise magnitude and narrative context are required.
- Regime definitions must be market-structural, not just session/ATR/calendar proxies.
- Positioning and flow data are missing:
  - CFTC COT,
  - ETF flows,
  - central bank demand,
  - options skew if available.
- Full trade construction is missing:
  - entry precision,
  - stop logic,
  - target structure,
  - time stop,
  - partial exits,
  - volatility-adjusted sizing.
- Multi-timeframe hierarchy is required:
  - Weekly/Daily macro bias,
  - H4 structure,
  - H1 entry,
  - M15/M5 precision.

The critique was validated against the project results. It aligns with the failure of raw macro/exogenous tests and the failure of Stage36/37 to convert raw structure edge into executable risk.

## 9. Reports to carry into the new session

At minimum, use this transfer pack.

Recommended supporting reports if available:

1. `XAUUSD_project_scientific_technical_process_review.md`
   - Internal project review.
2. `XAUUSD_project_validation_and_rebuild_roadmap.md`
   - Validation of senior critique and proposed roadmap.
3. `XAUUSD_Senior_Analyst_Review.md`
   - External/strategic market critique.
4. `stage37a_nonoverlap_risk_normalization_audit.md`
   - Final branch-level technical decision.

If only one file can be uploaded to the new session, upload this transfer pack first. It contains the operationally required summary.

## 10. Stage38A definition

Stage38A should be a **non-coding or minimally coding planning/research stage**.

Primary deliverable:

`Gold Market Thesis Reconstruction Report`

It must include:

1. Gold Market Map.
2. Macro driver hierarchy.
3. Regime definitions.
4. Conditional reaction matrix.
5. Data gap analysis.
6. Candidate thesis shortlist.
7. Minimum viable setup definitions.
8. Go/no-go criteria for Stage39 implementation.

Stage38A should not:

- create new backtests,
- revive Stage36 branches,
- do more variant mining,
- authorize EA/paper/live/orders,
- rely on raw feature columns without market interpretation.

## 11. Required Stage38A content

### 11.1 Gold Market Map

Must answer:

- What drives gold over intraday, multi-day, and macro horizons?
- Which drivers dominate in which regimes?
- How do real yields, DXY, Fed expectations, inflation, risk sentiment, geopolitical risk, central banks, and positioning interact?
- When can gold and DXY rise together?
- When does high CPI push gold up versus down?

### 11.2 Regime definitions

At minimum:

1. Gold bull / macro tailwind.
2. Gold bear / macro headwind.
3. Range / macro confusion.
4. Safe-haven spike.
5. Positioning squeeze.

Each regime must include:

- market logic,
- measurable criteria,
- required data,
- allowed setup types,
- disallowed setup types,
- failure risks.

### 11.3 Conditional reaction matrix

Matrix examples:

- CPI surprise × regime.
- NFP surprise × Fed regime.
- FOMC tone × market pre-positioning.
- DXY impulse × risk-off vs yield-driven character.
- real yield slope × gold trend.
- equity stress × safe-haven response.
- geopolitical shock × liquidity/spread regime.

### 11.4 Data gap analysis

Essential new data layers:

- CFTC COT gold futures positioning.
- ETF flows such as GLD/IAU if accessible.
- Event actual/forecast/previous for CPI, NFP, PCE, FOMC, Claims, Retail Sales, ISM.
- Fed expectations or proxy from FRED/SOFR/fed funds futures if accessible.
- Real yield slope/rank, not just raw level.
- DXY trend character.
- VIX regime and equity trend.
- Multi-timeframe gold features:
  - D1 trend,
  - H4 structure,
  - H1 session behavior,
  - M15/M5 entry precision if available.

### 11.5 Thesis shortlist

Stage38A should propose no more than three thesis families.

Candidate examples:

1. Macro-tailwind structure continuation:
   - Only long in bull/neutral regimes.
   - Uses H4/D1 alignment.
   - Based on liquidity sweep/reclaim or breakout continuation.

2. Event-surprise reaction/follow-through:
   - Trades only when surprise magnitude and regime agree.
   - Requires actual/forecast/previous.
   - Uses pre-event drift and post-event confirmation.

3. Positioning squeeze / crowded trade reversal:
   - Uses COT/ETF flow extremes.
   - Low-frequency.
   - Requires weekly/daily validation, not high-frequency mining.

## 12. Stage39 should only happen if Stage38A passes

Stage39 should implement only thesis families that pass Stage38A go/no-go criteria.

Possible Stage39 modules:

- `stage39a_gold_regime_feature_store.py`
- `stage39b_event_surprise_database_builder.py`
- `stage39c_thesis_backtest_skeleton.py`

But these should not be created until Stage38A has produced a defensible thesis document.

## 13. Decision gate before any new code

Before writing Stage39 code, the new session must explicitly answer:

1. Which exact thesis are we testing?
2. Why should it work in gold?
3. Which regime permits it?
4. Which regime forbids it?
5. What data is required?
6. What is the minimum viable setup?
7. What is the trade construction?
8. What is the validation metric?
9. What would invalidate the thesis?
10. What is the fastest safe test?

If these cannot be answered, do not code.

## 14. Current practical next step in the new session

Start with:

“چپ‌چین ادامه می‌دهم. بر اساس بسته انتقالی، Stage38A را شروع می‌کنیم: بازسازی thesis بازار طلا پیش از هر کدنویسی.”

Then ask or proceed to produce:

`Stage38A Gold Market Thesis Reconstruction Report`

Recommended Stage38A structure:

1. Executive decision.
2. Why prior pipeline failed.
3. Gold market driver map.
4. Regime taxonomy.
5. Conditional reaction matrix.
6. Data inventory and gaps.
7. Data acquisition plan.
8. Three thesis candidates.
9. Minimum viable setup definitions.
10. Validation plan.
11. Kill criteria.
12. Stage39 readiness decision.

## 15. Important current state commands

Check minimal monitor:

```bash
cd ~/Desktop/xauusd-trader
cat data/reports/stage35c_minimal_monitor/latest_minimal_monitor_state.env
```

Remove pycache if needed:

```bash
cd ~/Desktop/xauusd-trader
find app tools -type d -name "__pycache__" -prune -exec rm -rf {} +
```

Git flow:

```bash
cd ~/Desktop/xauusd-trader
git status --short
git add -A
git commit -m "..."
git pull --rebase origin main
git push
```

## 16. Final instruction for the next session

Do not continue the old mining logic.

The next session should begin with market understanding and thesis reconstruction. The cleaned technical stack is available, but code is secondary until the market model is rebuilt.
