# Article 2 Reviewer Risk Register V1

| Risk | Likely reviewer objection | Evidence-backed response | Required action |
| --- | --- | --- | --- |
| Article 1 overlap | This is an engineering appendix to the trading study. | The question, outcomes and benchmark concern corruption handling; Article 1 results are not re-estimated. | Keep profitability results out of the main contribution. |
| Toy benchmark | Twelve deterministic faults cannot represent all failures. | The suite is pre-specified and exhaustive only over its frozen taxonomy. | State this limitation; add external replication rather than more in-sample fault tuning. |
| Fail-open straw man | A warning-only arm is intentionally weak. | It isolates the scientific difference between detecting a fault and refusing unsafe execution. | Document exact checks available to each arm and avoid claims about all point-in-time systems. |
| Overhead framing | 43.44x overhead is operationally expensive. | Absolute median is 0.385 ms for the 15-case microbenchmark. | Report ratio and absolute time together; profile a realistic batch before stronger performance claims. |
| Coverage inflation | Scoped coverage hides the historical repository. | Scope is pre-registered to Article 2 functions and two production-core adapters. | Never call 95.94% whole-repository coverage. |
| No statistical inference | Results have no confidence intervals. | Faults are a frozen finite set, not a random sample from a population. | Use descriptive metrics; do not manufacture p-values. |
| Reproducibility gap | Private data prevent reproduction. | The fault benchmark uses deterministic fixtures and no raw market data. | Release minimal fixtures and software; distinguish method reproduction from Article 1 data reproduction. |
| Single-codebase validity | XAUUSD-specific integration may not generalize. | Core contracts are domain-agnostic, but only one codebase is evidenced. | Add a second-pipeline replication or retain a strict external-validity limitation. |
| Open-source readiness | Software paper lacks a citable public release. | Current evidence is hash-bound locally. | Add license, public release, version tag and archive DOI before submission. |
| AI disclosure | Draft provenance and accountability are unclear. | All numerical claims are generated from verified artifacts and remain author-reviewed. | Add the selected journal's current disclosure; verify every citation and sentence. |
