# Frozen Article 2 Results Prose

This file is generated from the verified evidence bundle. Do not edit reported values manually.

The benchmark compared three pre-specified architectures across 12 isolated fault cases and 3 clean controls per arm. The naive latest-state arm detected 0.00% of injected faults and unsafely accepted 100.00%. The point-in-time fail-open arm detected 50.00%, but its unsafe-acceptance rate remained 100.00% because warnings did not block execution. The complete point-in-time, provenance-bound, fail-closed arm detected 100.00%, reduced unsafe acceptance to 0.00%, and produced 0.00% false blocking across clean controls.

The complete arm's median runtime was 385.028 microseconds for the 15-case microbenchmark, corresponding to 43.44x the naive arm. This relative overhead must be interpreted together with the sub-millisecond absolute runtime and must not be generalized to full historical backtests.

Verification covered 189 of 197 scoped executable statements (95.94%) and both pass and fail outcomes for all 11 frozen semantic contracts (100.00%). All 13 Article 2 unit tests and 31 existing core regression tests passed without skips. Both production-core adapters passed. Repeated runs reproduced digest `25f8420eaf39296e38f9d9a9416cb7aa3aba6baad16781ca157d921d1e8d6410`.

The experiment did not rerun the evidence collector, re-estimate Article 1 trading results, search for alpha, or permit broker, demo, paper, or live orders. Its inference is limited to controlled corruption detection in the frozen benchmark and the selected XAUUSD research-pipeline adapters.
