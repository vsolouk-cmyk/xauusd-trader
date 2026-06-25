# Stage66D Limited Macro Thesis Rules

This file pre-registers the rules for complementary thesis work after Package 1.

## Why 2-4 theses only?

The quota of 2-4 independent theses is selected to avoid repeating the Stage50-style expansion problem. The prior broad thesis/candidate expansion produced too many variants and too much post-hoc selection risk. The rule here is:

```text
independent thesis count: 2-4
variants per thesis: max 3
total tests: max 12
```

The thesis-to-candidate ratio must remain controlled. Increasing this quota without a separate explicit managerial decision is forbidden, not merely undesirable.

## Independence classification

Every proposed thesis must include:

```text
correlation_to_h64l_driver_set
classification_independent_or_h64l_variant
```

If a thesis primarily uses the H64L driver set — gold trend, DXY, real yield, ETF flow — it is an H64L variant and does not count as an independent complementary thesis.

## Multiple testing correction

With at most 12 tests, the default pass threshold is Bonferroni-corrected:

```text
p < 0.05 / 12 = 0.00417
```

Raw p < 0.05 is not enough for a new thesis pass.

## Governance

No order, broker connection, paper-live, live, or EA promotion can be authorized by Track D.
