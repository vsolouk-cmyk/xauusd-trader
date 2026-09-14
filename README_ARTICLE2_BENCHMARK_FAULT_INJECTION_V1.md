# XAUUSD Article 2 Benchmark/Fault-Injection Package V1

This package closes the specific software-evidence gaps identified in the Article 2 intake audit. It adds a frozen three-arm benchmark, twelve isolated fault injections, adapters to the existing Stage170C and historical-replay core, scoped coverage, deterministic reproduction, a fail-closed publication-evidence gate and read-only bundle verification.

It does not rerun the collector, search for trading alpha, place orders or change Article 1 results.

## Install into the project

Extract this package at the root of `~/Desktop/xauusd-trader`. Existing files are not replaced except where the same Article 2 package has already been installed.

Run the command in `docs/article2/ARTICLE2_BENCHMARK_AND_FAULT_INJECTION_PROTOCOL.md`. The runner creates and retains:

- `artifacts/article2/article2_evidence_v1/`
- `artifacts/article2/XAUUSD_ARTICLE2_BENCHMARK_FAULT_INJECTION_EVIDENCE_V1.zip`
- `artifacts/article2/XAUUSD_ARTICLE2_BENCHMARK_FAULT_INJECTION_EVIDENCE_V1.zip.sha256`

For GitHub QA, run **XAUUSD Article 2 Evidence QA** manually from the Actions tab after committing the locally verified evidence.

