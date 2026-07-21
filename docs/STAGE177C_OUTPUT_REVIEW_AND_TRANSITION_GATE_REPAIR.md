# Stage177C Output Review and Transition-Gate Repair

## Observed result from Archive(8)

- Selected contract: `EU_DST_GMT_OFFSET_PAIR`
- Standard shift: `-120` minutes
- DST shift: `-180` minutes
- Selection used holdout: `False`
- All-sample M5 overlap: `806,433`
- All-sample M5 coverage: `99.915130%`
- All-sample 60-minute return correlation: `0.997659`
- Median absolute close difference: `0.316037 bps`
- Untouched holdout return correlation: `0.999766`
- Untouched holdout coverage: `99.612559%`
- H1 return correlation: `0.995559`
- Confident-week agreement, train: `99.616858%`
- Confident-week agreement, all sample: `99.667774%`

The only failed check was `transition_frequency`.

## Root cause

The raw weekly Viterbi path contained one isolated one-week excursion in
October 2019:

- EU-DST shift before the week: `-180`
- isolated week: `-120`
- EU-DST shift after the week: `-180`

That single transient segment creates two extra transition events. Counting
every raw transition produced four transitions in 2019 even though the stable
calendar pattern has two.

## Repair policy

The raw path remains unchanged and is still reported. For the
transition-frequency gate only, the program now collapses an isolated segment
of at most one week when both neighbouring segments have the same shift.
Segments lasting two weeks or longer are never collapsed.

New output:

- `stage177c_persistent_offset_segments.csv`

New summary fields preserve both raw and persistent transition profiles.

## Expected rerun decision

With the observed Archive(8) metrics, the persistent 2019 profile has two
transitions rather than four. All existing quantitative gates therefore pass,
so the expected decision is:

`PASS_AMARKETS_DST_AWARE_UTC_CONTRACT`

This pass authorizes the timestamp/data contract only. It does not authorize
paper, demo, or live execution.
