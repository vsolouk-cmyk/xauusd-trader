# STAGE39F_RECENCY_BIAS_AND_RULE_STABILITY_AUDIT

## Scope

Research-stage only.

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

Stage39F consumes the Stage39E frozen-rule OOS output and checks whether the apparent OOS improvement is a stable rule property or mostly a recency-biased artifact.

## Why this stage is needed

Stage39E left several frozen OOS watch rows, but the strongest rows show a common pattern:

- OOS and recent-third are much stronger than train.
- Early quarters are weak or negative after cost/slippage.
- Some rows still have large adverse path risk.
- Some rows fail because OOS stop-touch risk is too high.

Therefore the next step cannot be promotion. It must be a stability and recency-bias audit.

## Main checks

The script audits:

- full sample event count,
- train and OOS event count,
- full/train/OOS cost-stressed mean,
- full/train/OOS mean after cost plus 16 bps extra slippage,
- ex-2025 cost mean,
- leave-one-year-out minimum cost mean,
- worst quarter cost mean,
- worst quarter after cost plus 16 bps,
- full and OOS median MAE,
- full and OOS 100 bps stop-touch rate,
- OOS-vs-train gap and ratio,
- q4-vs-full concentration.

## Classifications

```text
STRICT_STABLE_FROZEN_RULE_WATCH_ONLY_NO_PROMOTION
```

The rule survives strict stability checks, but still remains research-only.

```text
RECENCY_BIASED_FROZEN_RULE_WATCH_ONLY_NO_PROMOTION
```

The rule remains interesting but is materially dominated by OOS/recent behavior, weak early quarters, weak train slippage survival, or recency concentration. This is not tradable.

```text
FAIL_RECENCY_STABILITY_NO_PROMOTION
```

The rule should not be extended with more filters.

## Expected inputs

```text
reports/stage39e/stage39e_frozen_rule_oos_summary.json
reports/stage39c/stage39c_condition_event_rows.csv
```

## Expected outputs

```text
reports/stage39f/stage39f_frozen_rule_recency_bias_summary.csv
reports/stage39f/stage39f_split_stability_audit.csv
reports/stage39f/stage39f_audited_events.csv
reports/stage39f/stage39f_frozen_rule_recency_bias_summary.json
reports/stage39f/stage39f_frozen_rule_recency_bias_audit.md
```

## Interpretation rule

No Stage39F output can authorize EA, paper-live, or live. If no row is classified as `STRICT_STABLE_FROZEN_RULE_WATCH_ONLY_NO_PROMOTION`, the default action is to archive Stage39A-F and wait for materially more forward data.
