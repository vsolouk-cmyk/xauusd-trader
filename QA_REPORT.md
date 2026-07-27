# QA report

- Root cause reproduced conceptually: pandas datetime resolution can be microseconds on newer Python/pandas builds; the previous code assumed nanoseconds.
- Timestamp conversion now explicitly uses `datetime64[ms]`.
- Python compile: PASS.
- Unit tests: 9/9 PASS.
- Exact tail-beyond-legacy-cutoff regression: PASS.
- Truncated-tail rejection: PASS.
- True off-grid rejection: PASS.
- Explicit epoch-millisecond regression: PASS.
- 100,000-row MT5-format smoke test: PASS.
- Real 1,087,089-row user CSV was not available inside this execution environment, so full local end-to-end refresh remains to be run in the user's repo.
