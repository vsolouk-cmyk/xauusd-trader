# Fail-Closed Point-in-Time Provenance for Reproducible Trading-Strategy Audits: A Controlled Fault-Injection Study

**Manuscript status:** evidence-bound first draft; journal-neutral structure  
**Primary software-paper target:** SoftwareX, conditional on a citable public software release  
**Article boundary:** software/method contribution only; Article 1 trading results are not re-estimated

## Abstract

Computational trading research can silently accept unavailable information, revised data, stale artifacts, modified configurations, malformed market bars, or inconsistent transaction-cost calculations. Conventional point-in-time checks identify some of these conditions, but warning-only pipelines may continue and thereby preserve an unsafe result. We present a point-in-time, provenance-bound, fail-closed software architecture for reproducible trading-strategy audits. Its contracts jointly enforce aware UTC timestamps, data availability before the decision time, revision-vintage binding, data and configuration hashes, artifact freshness, required-source completeness, market-bar uniqueness and grid alignment, and transaction-cost identity. We evaluated three pre-specified architectures—naive latest-state, point-in-time fail-open, and the complete fail-closed architecture—using 12 isolated fault injections and three clean controls per arm. The naive arm detected 0% of faults and unsafely accepted 100%. The point-in-time fail-open arm detected 50% but still unsafely accepted 100%, because warnings did not block execution. The complete architecture detected 100%, reduced unsafe acceptance to 0%, and produced 0% false blocking on clean controls. Its median runtime was 385.028 microseconds for the 15-case microbenchmark (43.44× the naive arm), so the large relative overhead remained sub-millisecond in absolute terms. Verification covered 189/197 scoped executable statements (95.94%), both outcomes for all 11 semantic contracts, 13 new unit tests, 31 existing core regression tests, and two production-core adapters. Repeated runs reproduced an identical outcome digest. The experiment evaluates corruption detection and reproducibility, not trading profitability, and its external validity is limited by a finite fault taxonomy, deterministic fixtures, and one XAUUSD research codebase.

**Keywords:** point-in-time data; provenance; fail-closed systems; reproducible research; fault injection; backtesting; research software

## 1. Introduction

Reproducibility failures in computational research are often caused by the pipeline surrounding a model rather than by the model alone. Data leakage can make a scientific result appear stronger than it is [@kapoor2023leakage], while undeclared data dependencies and configuration changes create technical debt that ordinary unit tests may not expose [@sculley2015debt]. In trading research, the risk is acute because data are time-indexed, revised, published on different schedules, and transformed through cost-sensitive replay logic.

Point-in-time data handling is necessary but insufficient. A pipeline may recognize that an observation was unavailable at decision time and still continue after logging a warning. It may also validate time while accepting bytes whose manifest no longer matches, a configuration changed after the recorded run, or a net return inconsistent with declared costs. These are distinct failure modes with a common consequence: an apparently successful computation whose scientific provenance is unsafe.

This study asks:

> Does a point-in-time, provenance-bound, fail-closed architecture reduce unsafe acceptance of controlled research-pipeline corruption while preserving clean inputs and deterministic reproduction?

We answer this question with a frozen three-arm benchmark and a pre-specified suite of 12 isolated fault injections. The contribution is a software assurance method, not a new XAUUSD strategy and not a reinterpretation of prior empirical results.

### 1.1 Contributions

1. A unified contract layer connecting temporal availability, revision policy, cryptographic provenance, freshness, source completeness, bar integrity, and transaction-cost identity.
2. A fail-closed decision rule that distinguishes fault detection from safe refusal; warning-only detection is not counted as safe handling.
3. A deterministic fault-injection benchmark comparing naive, fail-open, and fail-closed architectures under identical fixtures.
4. A publication-evidence gate binding benchmark outcomes, semantic branches, scoped line coverage, regression tests, production-core adapters, and a reproducible digest.

## 2. Related work

Kapoor and Narayanan provide a cross-disciplinary taxonomy of leakage and show why leakage threatens reproducibility in machine-learning-based science [@kapoor2023leakage]. Pineau et al. document concrete institutional practices for improving reproducibility in machine-learning research [@pineau2021reproducibility]. Sculley et al. locate much of an ML system's risk in data dependencies, configuration, and surrounding infrastructure [@sculley2015debt]. General guidance on reproducible computational research emphasizes preserving raw inputs, recording provenance, automating analyses, and testing code [@sandve2013ten; @wilson2017good]. The W3C PROV model supplies a general vocabulary for representing entities, activities, and agents [@moreau2013prov].

Quantitative-finance research separately addresses selection-induced backtest overfitting [@bailey2017pbo]. That literature concerns the multiplicity and statistical validity of strategy searches. Our method addresses a complementary software-integrity question: whether the inputs and execution contracts of a declared audit are allowed to proceed after a detectable corruption. No claim is made that software integrity alone prevents specification search or establishes economic significance.

## 3. Architecture

### 3.1 Point-in-time contract

Every time-dependent input carries an availability timestamp distinct from its observation timestamp. Timestamps must be timezone-aware and normalized to UTC. The architecture blocks any observation whose availability exceeds the decision timestamp. Revised macroeconomic values additionally require a vintage identifier so that later revisions cannot silently replace the state available at the historical decision.

### 3.2 Provenance binding

Input bytes and frozen configuration bytes are bound to declared SHA-256 values. A mismatch blocks the run. Freshness contracts reject artifacts older than a pre-specified limit. Required-source contracts prevent an analysis from silently continuing when mandatory event context is absent. These checks turn provenance from descriptive metadata into an execution precondition.

### 3.3 Market and economic integrity

Market bars must have unique timestamps and align with the declared five-minute grid. The economic contract requires net return to equal gross return less the declared cost within a frozen tolerance. This protects the replay boundary where spread or slippage can otherwise be inconsistently applied.

### 3.4 Fail-closed gate

For the complete architecture, any failed contract rejects the case. The gate therefore separates two events:

- **Detection:** at least one check identifies the injected fault.
- **Safe handling:** the architecture refuses to accept the corrupted case.

A fail-open arm may detect a fault but still has unsafe acceptance equal to one. This distinction is the primary conceptual contrast of the experiment.

## 4. Evaluation design

### 4.1 Frozen arms

The benchmark contains three arms:

1. `NAIVE_LATEST_STATE`, which consumes the latest state without availability or provenance enforcement.
2. `POINT_IN_TIME_FAIL_OPEN`, which emits selected timing and integrity warnings but continues.
3. `POINT_IN_TIME_PROVENANCE_FAIL_CLOSED`, which evaluates all frozen contracts and blocks on any failure.

The arm definitions are fixed before execution. There is no parameter search, model fitting, strategy ranking, or alpha selection.

### 4.2 Fault taxonomy and controls

Each fault mutates one clean deterministic fixture. The 12 cases are future-data leakage, pre-publication COT use, timezone loss, schema drift, data-manifest tampering, configuration tampering, stale artifacts, missing event context, duplicate bars, off-grid bars, cost-contract corruption, and revised values without vintages. Three clean controls per arm estimate false blocking. Because the benchmark exhaustively evaluates a small pre-specified suite rather than samples faults from a population, results are reported descriptively without inferential p-values.

### 4.3 Metrics

For fault set \(F\) and clean controls \(C\), we define:

\[
\text{DetectionRate}=\frac{\sum_{i\in F}\mathbb{1}(\text{fault detected}_i)}{|F|},
\]

\[
\text{UnsafeAcceptanceRate}=\frac{\sum_{i\in F}\mathbb{1}(\text{accepted}_i)}{|F|},
\qquad
\text{FalseBlockingRate}=\frac{\sum_{i\in C}\mathbb{1}(\neg\text{accepted}_i)}{|C|}.
\]

Secondary measures are silent acceptance, deterministic reproduction, median and p95 runtime, overhead relative to the naive arm, scoped executable-statement coverage, and semantic true/false branch coverage.

### 4.4 Pre-specified publication gate

`ARTICLE2_EVIDENCE_SUFFICIENT` requires 100% complete-arm detection, 0% complete-arm unsafe acceptance, 0% false blocking, a stable digest, both outcomes for every semantic contract, at least 80% scoped line coverage, passing adapters, passing tests, a complete core manifest, and evidence-intake provenance. A failed requirement produces `BLOCK_ARTICLE2`.

## 5. Results

The benchmark outcomes are summarized in Table 1 and Figure 1. The naive arm detected none of the 12 faults and accepted all corrupted cases. The fail-open arm detected six faults but accepted every corrupted case. The complete arm detected and blocked all 12 faults while accepting all three clean controls.

**Table 1.** Generated file: `artifacts/article2/article2_manuscript_v1/table_1_arm_metrics.md`  
**Figure 1.** Generated file: `artifacts/article2/article2_manuscript_v1/figure_1_arm_safety_comparison.svg`

The complete arm's median runtime for all 15 cases was 385.028 microseconds, compared with 8.863 microseconds for the naive arm. This is a 43.44× relative overhead. The relative ratio is large because the baseline is extremely small; the absolute complete-arm runtime remains below one millisecond in this microbenchmark. These timings do not estimate overhead for a full historical backtest.

Verification covered 189 of 197 scoped executable statements (95.94%) and both pass and fail outcomes for all 11 semantic contracts. All 13 Article 2 unit tests and 31 pre-existing core regression tests passed without skips. Adapters to the Stage170C point-in-time enforcement and historical-replay cost-parity boundaries both passed. Independent repeated executions produced the same digest:

`25f8420eaf39296e38f9d9a9416cb7aa3aba6baad16781ca157d921d1e8d6410`

**Table 2.** Generated file: `artifacts/article2/article2_manuscript_v1/table_2_validation_evidence.md`

## 6. Discussion

The difference between detection and refusal is material. A warning-only pipeline can obtain a seemingly respectable detection rate while accepting every corrupted case. The complete architecture improves safety by making the contracts jointly necessary for execution. Provenance checks also detect failure classes that point-in-time logic alone cannot address, including modified data bytes, changed configurations, and stale artifacts.

The benchmark does not show that the architecture discovers profitable strategies. It shows that, for the frozen cases, declared failures become measurable and blocking rather than silent. Article 1 remains the empirical strategy audit; the present article treats that domain as a real-world integration case for a software method.

The overhead result should not be reduced to either the relative or absolute number alone. A 43.44× ratio may matter in extremely latency-sensitive paths, while 0.385 ms may be negligible in offline research validation. Production users should profile their own data scale and contract implementations.

## 7. Threats to validity

- **Construct validity:** the 12 faults operationalize selected temporal, provenance, completeness, market-data, and economic risks; they do not represent every possible research corruption.
- **Internal validity:** fixtures are deterministic and one fault is injected per case. Interacting faults may exhibit different detection behavior.
- **External validity:** production-core adapters are drawn from one mature XAUUSD research repository. Generalization to other instruments, frequencies, storage layers, and languages remains untested.
- **Measurement validity:** scoped coverage targets frozen Article 2 functions rather than the entire historical repository. Runtime is a microbenchmark on one recorded software environment.
- **Statistical conclusion validity:** the suite is exhaustive over a frozen finite taxonomy, not a random sample. Percentages are descriptive and should not be assigned population confidence intervals.
- **Reproducibility boundary:** raw market data and database bytes are excluded from this software-method benchmark; the deterministic fixtures reproduce the fault-injection result, not the full empirical Article 1 study.

## 8. Reproducibility and availability

The repository contains the benchmark implementation, frozen configuration, tests, adapters, evidence runner, retained expanded evidence, hash-bound ZIP, manuscript-input generator, and CI workflows. The manuscript tables and figure are generated directly from verified JSON evidence. A public archival release, software license, repository URL, release DOI, and minimal installation example must be inserted before submission.

## 9. Ethics, financial scope, and AI disclosure

The software does not place broker, demo, paper, or live orders. The study does not provide investment advice and makes no profitability claim. No human or animal participants are involved. The final manuscript must include an author-verified generative-AI disclosure tailored to the selected journal's current policy; no authorship or scientific accountability is delegated to an AI system.

## 10. Conclusion

A point-in-time check is not sufficient when a pipeline continues after warnings or lacks provenance and economic contracts. In the frozen benchmark, the combined point-in-time, provenance-bound, fail-closed architecture detected and blocked all controlled corruptions while preserving clean controls and deterministic reproduction. The next scientific step is external replication on a second research pipeline and evaluation of interacting faults, not additional tuning on the present cases.

## References

The machine-readable bibliography is `ARTICLE2_REFERENCES_V1.bib`. Citations and journal formatting must be revalidated immediately before submission.
