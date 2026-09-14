# Article 2 Benchmark and Fault-Injection Protocol V1

## Frozen scientific boundary

Article 1 remains the empirical, point-in-time and cost-aware audit of XAUUSD strategy families. Article 2 does not rerun or reinterpret those strategy results. Its contribution is narrower: a reproducible software architecture that combines point-in-time availability, provenance binding and fail-closed decision gates.

The pre-registered question is whether the complete architecture reduces unsafe acceptance of controlled research-pipeline corruption while preserving clean inputs, deterministic outcomes and bounded runtime overhead.

## Benchmark arms

1. `NAIVE_LATEST_STATE`: consumes the latest state and does not enforce availability or provenance.
2. `POINT_IN_TIME_FAIL_OPEN`: checks selected timing and data-quality conditions but continues after warnings.
3. `POINT_IN_TIME_PROVENANCE_FAIL_CLOSED`: requires aware UTC timestamps, availability before decision time, revision vintages, manifest/config hashes, freshness, required sources, bar integrity and cost identities; any failed contract blocks the case.

The arms are fixed before execution. No search, parameter grid, trading-model fitting or alpha selection is performed.

## Controlled faults

Each case changes exactly one clean fixture. The matrix contains future-data leakage, pre-publication COT use, timezone loss, schema drift, manifest tampering, configuration tampering, stale artifacts, missing event context, duplicate bars, off-grid bars, cost-contract corruption and revised values without vintages.

## Metrics and gates

The primary measures are fault-detection rate, unsafe-acceptance rate and false-blocking rate. Secondary measures are silent acceptance, deterministic reproduction, runtime overhead, scoped executable-line coverage and semantic branch coverage.

`ARTICLE2_EVIDENCE_SUFFICIENT` requires all of the following:

- full-arm detection rate = 100%;
- full-arm unsafe acceptance = 0%;
- full-arm false blocking = 0%;
- deterministic outcome digest;
- 100% true/false outcome coverage for every frozen semantic contract;
- at least 80% scoped executable-line coverage;
- passing adapters to Stage170C as-of enforcement and historical-replay cost parity;
- passing unit tests and complete hash-bound core manifest;
- evidence-intake provenance bound to the run.

Failure of any gate produces `BLOCK_ARTICLE2`. Neither decision permits broker, demo, paper or live orders.

## Local execution

From the repository root, run:

```bash
python3 tools/article_publication/run_article2_evidence_suite.py \
  --root . \
  --intake-zip "$HOME/Downloads/XAUUSD_ARTICLE2_SOFTWARE_EVIDENCE_INTAKE_20260914T175601Z.zip" \
  --intake-root "$HOME/Downloads/XAUUSD_ARTICLE2_SOFTWARE_EVIDENCE_INTAKE_20260914T175601Z"
```

The output folder is `artifacts/article2/article2_evidence_v1/`. The corresponding ZIP and SHA-256 sidecar are created in `artifacts/article2/`. The expanded folder is intentionally retained.

Verify the saved output without changing it:

```bash
python3 tools/article_publication/verify_article2_evidence_bundle.py --root .
```

The Article 2 collector is not invoked by either command.

## GitHub Actions

After the verified local folder and ZIP have been committed, open **Actions → XAUUSD Article 2 Evidence QA → Run workflow**. The workflow compiles the selected code, runs the bounded unit suite and verifies that the committed ZIP matches the retained expanded folder.

