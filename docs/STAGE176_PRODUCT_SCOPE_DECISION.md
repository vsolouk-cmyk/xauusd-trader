# Stage176 Product-Scope Decision

## Active product hypothesis

```text
Gold Allocation Decision Engine
```

The first commercially usable output, if validated, is a quarterly decision-support report rather than an automated high-frequency EA.

Expected shadow output:

```text
allocation state: HIGH / LOW
report publication timestamp
tradable timestamp
trailing four-quarter official purchases
prior expanding median
price versus 200D SMA
state-transition reason
data freshness and source hashes
```

## Timebox

Stage176 is the only research package for this formulation. One integration bugfix is allowed if a valid input fails because of code/schema incompatibility.

No research sub-stages are authorized.

The program decision deadline remains:

```text
2026-07-29
```

At that point:

```text
PASS  -> quarterly decision-support MVP and shadow operation
FAIL  -> kill Thesis A and escalate product scope
LOW POWER / DATA BLOCKED -> product-scope escalation, not another rule search
```

## Explicitly excluded

```text
- GVZ thesis auto-start
- direct price-prediction ML
- broad COT scan
- session breakout or trend/pullback rescan
- threshold grid around central-bank purchases
- leverage or order routing
```
