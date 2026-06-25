# XAUUSD Stage66 Corrected Operational Path — Package 1

Generated: 2026-06-25

## Purpose

This document replaces the previous Stage66 operational plan after the pre-implementation review.

The project objective is commercial readiness as fast as prudently possible. Stage65 daily forward-shadow must not become the main path. Stage65 remains background telemetry. Stage66 Package 1 is the fast decision package designed to answer:

1. Is H64L still credible after concentration/outlier audit?
2. Does H64L survive forward-like historical rolling-origin replay without lookahead?
3. Can we move to a no-order paper-execution simulator in Package 2 with pre-locked sizing and execution penalties?

This package does not authorize broker connection, EA promotion, paper-live, live, or any order path.

## Review issues incorporated

The pre-implementation review identified actionable issues that must be fixed before coding. Package 1 implements the following corrections:

- `IDEA-1`: PASS_FAST now requires at least 4 positive independent episodes. Three episodes is treated as boundary evidence and defaults to `PASS_SMALL_SIZE_ONLY` unless leave-one-out is very robust.
- `METHOD-1`: A data integrity crosscheck is added before Stage66A/B so both tracks do not silently share the same data/lag bug.
- `METHOD-2`: Episode merge logic is pre-locked at `merge_episode_inactive_trading_days_lt = 5` and must not be changed after seeing results.
- `METHOD-3`: Rolling-origin replay cannot be `PASS_FAST` with fewer than 8 independent origins.
- `IMPL-3`: H64L rule is locked in `configs/h64l_locked_rule_v1.json` with checksum verification.
- `TEST-1`: Stage66A stops with `RECONSTRUCTION_MISMATCH` if reconstructed active events differ from the Stage64R 336 count by more than ±2%.
- `TEST-2`: A no-lookahead unit test is provided for Stage66B.
- `TEST-3`: Stage66F includes a pre-registered A×B decision matrix.
- `IMPL-4`: Stage66F is idempotent and must be regenerated after every A/B/C/D execution.
- `IMPL-1/2`: Stage66C rules are pre-locked for Package 2: feed mismatch penalty and sizing-band selection are defined now, before seeing Package 1 results.
- `IDEA-2/3/METHOD-4`: Track D thesis registry is pre-locked with H64L-driver correlation classification and Bonferroni p-value correction for at most 12 tests.

## Package 1 tracks

### Stage66-0 — Data integrity crosscheck

File:

```text
app/stage66_data_integrity_crosscheck.py
configs/stage66_data_integrity_crosscheck.json
```

Role:

- Verify the H64L locked rule hash.
- Confirm `Stage64K` and external D1 files exist and are current enough.
- Check as-of safety: `sample_available_after_utc` must not predate `feature_date_utc`.
- Perform cross-source gold close checks between Stage64K `gold_close` and external D1 close on fixed sample dates.
- Optionally use manual independent point checks if populated later.

Decision:

- `PASS`: Stage66A/B allowed.
- `PASS_WITH_WARNINGS`: Stage66A/B allowed, but warnings are visible in Stage66F.
- `FAIL`: Stop Package 1 and fix data first.

### Stage66A — H64L concentration / episode / outlier audit

File:

```text
app/stage66a_h64l_concentration_audit.py
configs/stage66a_h64l_concentration_audit.json
```

Role:

- Reconstruct H64L from locked rules only.
- Reconcile active event count with Stage64R expected count: 336 ±2%.
- Group active days into independent episodes using the locked merge rule.
- Run leave-one-out episode analysis.
- Detect whether the edge is concentrated in too few episodes.

Pre-locked episode rule:

```text
merge_episode_inactive_trading_days_lt = 5
```

Meaning: if two active stretches are separated by fewer than 5 inactive trading rows, they are one episode. This cannot be changed after seeing results.

Decision logic:

```text
PASS_FAST:
  reconstructed active count passes ±2%
  positive independent episodes >= 4
  leave-one-out minimum mean return > 0
  max episode active-day share <= 45%

PASS_SMALL_SIZE_ONLY:
  reconstructed active count passes ±2%
  positive independent episodes >= 3
  leave-one-out minimum mean return > 0

PASS_LOW_FREQUENCY_ONLY:
  active events exist, but concentration/episode evidence is not enough for faster sizing confidence

KILL_OR_ARCHIVE_RECONSTRUCTION_MISMATCH:
  reconstructed active count differs from 336 by more than ±2%
```

### Stage66B — Rolling-origin forward-like historical replay

File:

```text
app/stage66b_h64l_rolling_origin_replay.py
configs/stage66b_h64l_rolling_origin_replay.json
```

Role:

- Use the existing history to create forward-like origins.
- Enforce no-lookahead through `sample_available_after_utc`.
- Avoid waiting 180 real calendar days just to discover whether the thesis is decision-relevant.

Pre-locked minimum:

```text
minimum_independent_origins_for_pass_fast = 8
```

Decision logic:

```text
PASS_FAST_FORWARD_LIKE_REPLAY_NO_ORDER:
  no lookahead breach
  independent origins >= 8
  enough signal origins
  mean return > 0
  positive origin share >= 50%

PASS_LOW_FREQUENCY_ONLY_NOT_PASS_FAST:
  replay is positive enough to continue, but independent origins are too few for PASS_FAST

INSUFFICIENT_SIGNAL_ORIGINS_CONTINUE_HISTORICAL_ONLY:
  not enough replay signal density

KILL_OR_ARCHIVE_LOOKAHEAD_BREACH:
  any no-lookahead breach
```

### Stage66F — Governance dashboard

File:

```text
app/stage66f_governance_dashboard.py
```

Role:

- Regenerate after every Stage66A/B/C/D run.
- Combine Stage66A and Stage66B decisions through a pre-registered decision matrix.
- Prevent ambiguous interpretation after results.

Rule:

```text
Every execution of Stage66A, Stage66B, Stage66C, or Stage66D must be followed immediately by Stage66F.
```

Key matrix outcomes:

```text
A_PASS_FAST + B_PASS_FAST:
  PAPER_SIM_READY_BAND_B_NO_ORDER_PACKAGE2

A_PASS_SMALL_SIZE_ONLY + B_PASS_LOW_FREQUENCY_ONLY:
  PAPER_SIM_READY_BAND_A_NO_ORDER_CONCENTRATION_AND_FREQUENCY_WARNINGS

A_PASS_LOW_FREQUENCY_ONLY + B_PASS_LOW_FREQUENCY_ONLY:
  NO_FAST_DEPLOYMENT_BACKGROUND_PLUS_THESIS_D_REQUIRED

Any A_KILL or B_KILL:
  stop and fix the relevant issue before continuing
```

## Stage66C pre-lock for Package 2

Stage66C is not executed in Package 1, but its key post-hoc selection risks are locked now.

File:

```text
configs/stage66c_h64l_paper_execution_simulator.json
```

Locked rules:

```text
feed_mismatch_penalty_bps_per_side = 20
band_A = 0.1% target capital risk, default
band_B = 0.25%, only if Stage66A is PASS_FAST
band_C = 0.5%, reporting sensitivity only, never selected operationally from Package 1
```

This prevents selecting sizing after seeing which band looks best.

## Stage66D pre-lock for complementary thesis registry

Files:

```text
configs/stage66d_limited_macro_thesis_registry.json
docs/stage66d_limited_macro_thesis_rules.md
```

Rules:

- 2 to 4 independent theses only.
- Maximum 3 variants per thesis.
- Maximum 12 total tests.
- Bonferroni-corrected significance threshold: p < 0.05 / 12 = 0.00417.
- Any thesis using the same H64L driver set must be classified as H64L variant, not independent thesis.
- Increasing the thesis quota requires a separate explicit managerial decision.

## Hard blocks

The following remain blocked:

```text
NO_PAPER_ORDER
NO_EA_PROMOTION
NO_PAPER_LIVE
NO_LIVE
NO_BROKER_CONNECTION
NO_ORDER_AUTHORIZATION_FROM_STAGE66_PACKAGE1
NO_THRESHOLD_TUNING
NO_RESCUE_FILTERING
NO_REDUCED_SCOPE_RETEST
NO_HISTORICAL_EVENT_FILTER_FROM_FORWARD_ONLY_GOVERNANCE
```

## Execution sequence

Run in this exact order:

```bash
cd /Users/vahid/Desktop/xauusd-trader

python3 app/stage66_data_integrity_crosscheck.py \
  --root . \
  --config configs/stage66_data_integrity_crosscheck.json \
  --out reports/stage66_data_integrity_crosscheck

python3 app/stage66a_h64l_concentration_audit.py \
  --root . \
  --config configs/stage66a_h64l_concentration_audit.json \
  --out reports/stage66a_h64l_concentration_audit \
  --write-events

python3 tests/test_stage66b_no_lookahead.py

python3 app/stage66b_h64l_rolling_origin_replay.py \
  --root . \
  --config configs/stage66b_h64l_rolling_origin_replay.json \
  --out reports/stage66b_h64l_rolling_origin_replay

python3 app/stage66f_governance_dashboard.py \
  --root . \
  --out reports/stage66f_governance_dashboard
```

## Outputs to inspect/send back

```text
reports/stage66_data_integrity_crosscheck/stage66_data_integrity_crosscheck_summary.json
reports/stage66a_h64l_concentration_audit/stage66a_h64l_concentration_audit_summary.json
reports/stage66b_h64l_rolling_origin_replay/stage66b_h64l_rolling_origin_replay_summary.json
reports/stage66f_governance_dashboard/stage66f_governance_dashboard_summary.json
```

## Decision after Package 1

The project exits the current conservative waiting trap only if Package 1 gives actionable routing:

- If dashboard says `PAPER_SIM_READY...`: build Stage66C no-order paper-execution simulator immediately.
- If dashboard says `NO_FAST_DEPLOYMENT...`: keep H64L as background macro thesis and start Stage66D limited independent thesis registry immediately.
- If dashboard says `STOP...`: fix data/rule/reconstruction/lookahead issue first.

Stage65 remains daily background telemetry only.
