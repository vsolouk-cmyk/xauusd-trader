# Stage 11B v2 Fast Grid

Stage 11B v1 created a very large grid and recomputed rolling/H4 features per variant. On an older MacBook this can take many hours.

v2 fixes that:

```text
default mode = fast
shared rolling/H4/session features are precomputed once
full grid is optional only
```

## Stop the old run

Press:

```text
Control + C
```

## Install/run v2

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage11b_alternative_short_thesis_lab
cat data/reports/stage11b_alternative_short_thesis_lab/stage11b_alternative_short_thesis_lab.md
```

## Optional full mode

Do not use this on the MacBook unless fast mode finds something worth expanding:

```bash
python3 -m app.stage11b_alternative_short_thesis_lab --mode full
```

## Hard rule

Research only. No EA change, no automatic news/trading, no paper/live authorization.
