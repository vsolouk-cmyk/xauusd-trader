# Stage177C Persistent Transition Gate Repair

The original gate counted every transition in the diagnostic weekly Viterbi
path. One isolated week in October 2019 created two extra transitions and
blocked an otherwise train-selected, untouched-holdout-validated EU DST
contract.

This repair preserves the raw path and adds a persistent path used only for the
transition-frequency gate. It collapses an isolated one-week excursion only
when the segments on both sides have the same shift. Excursions of two weeks or
longer remain untouched and can still fail the gate.

New report:

- `stage177c_persistent_offset_segments.csv`

The summary retains both raw and persistent transition profiles. No execution
permission is added; Stage177C remains a data/time-contract stage.
