# Article 1 Specification-Registry Freeze Memorandum

## Study

**Working title:** *From Apparent Edge to No-Go: A Point-in-Time, Cost-Aware Audit of Technical, Event, Cross-Asset, Machine-Learning, and Relative-Value Strategies in XAUUSD*  
**Registry:** `XAUUSD_ARTICLE1_LOCKED_SPECIFICATION_REGISTRY_V1_1`  
**Freeze time:** 2 September 2026, 05:19:30 UTC  
**Protocol stage:** Specification registry amended and frozen; the unified evaluation code has passed outcome-blind validation, and the final `main_run_manifest.json` will be frozen by that code immediately before outcome computation.

## Version 1.1 source-binding amendment

Version 1.0 bound the canonical time-series-momentum specification to SHA-256 `7c97785b6fa5778efcc8327bc0cefe74a10358d72a8a25bf44ebd1e081e340f8`. That digest belonged to a redacted intake copy of `app/xauusd_final_alpha_trend.py`; the copy contained malformed placeholders in three authorization-reporting statements and was not the executable project source. The Gap Pack copy, the original Final Alpha package manifest, and the current repository independently identify SHA-256 `b69caaaf0022e2d5956e0ebac964a06ab35e1279961c1ef04231a250962c7970` as the authoritative source.

The line-level comparison shows no change to the signal, lookback, volatility scaling, position sizing, cost model, temporal split, performance calculation, or decision gates. The amendment therefore repairs provenance without creating a new trading specification. It was made after the first registry preflight failed and before any consolidated rerun was executed. Version 1.0 is superseded and must not be used for execution.

## Purpose and inferential status

This memorandum freezes the exact strategy-specification universe to be carried forward into the consolidated Article 1 analysis. The historical project is a discovery and provenance corpus, not a collection of independent confirmatory experiments. Historical outcomes from the constituent research branches were already known when this registry was assembled. The consolidated rerun must therefore be described as a prospectively locked replication within a retrospective systematic audit; it cannot be represented as an untouched confirmatory experiment.

Registry inclusion did not depend on historical returns, Sharpe ratios, gate outcomes, or shortlist status. For each recoverable final fixed-registry branch, every exact specification in the associated source configuration was retained. This rule prevents the article from reconstructing a favorable universe by selecting only historical winners.

## Frozen universe

The registry contains 47 exact specifications. Thirty-nine are eligible for the primary locked rerun, and eight supervised-learning model–target combinations are restricted to a historical forensic case study.

| Source block | Registered | Primary rerun | Forensic only | Role |
| --- | ---: | ---: | ---: | --- |
| Successor technical and event-aware scan | 19 | 19 | 0 | Exact rule replication |
| Fixed-thesis cross-asset scan | 12 | 12 | 0 | Exact rule replication |
| Cross-asset event-response scan | 6 | 6 | 0 | Exact rule replication |
| Stage 178 supervised-learning screen | 8 | 0 | 8 | Historical selection and uncertainty case study |
| Canonical long-horizon time-series momentum | 1 | 1 | 0 | Canonical negative-control replication |
| Gold–silver relative value | 1 | 1 | 0 | Fixed relative-value replication |
| **Total** | **47** | **39** | **8** | |

The 39 primary specifications span 20 economically defined families and five parent categories: 16 canonical technical rules, nine event and news-response rules, 12 fixed-thesis cross-asset rules, one canonical time-series momentum rule, and one precious-metals relative-value rule.

## Machine-learning restriction

The eight Stage 178 model–target combinations remain in the registry so that the historical search burden is not understated. They are excluded from the primary rerun because the historical branch selected a candidate using earlier results and subsequently inspected the 2025+ AMarkets interval. Re-estimating those models inside the primary analysis would blur the distinction between prespecified replication and adaptive reuse. Their role is therefore limited to a forensic account of model selection, holdout reuse, and bootstrap uncertainty.

## Temporal and data contracts

The primary intraday window is bounded by 2 January 2015 at 07:00 UTC and 1 January 2025 at 00:00 UTC, subject to later source availability for the cross-asset panels. The 2025+ interval is a seen temporal diagnostic and cannot determine model inclusion, parameters, or primary support. Pre-2015 intraday observations are excluded from primary inference because they do not satisfy the frozen cross-feed data contract.

The AMarkets–Dukascopy alignment contract passes with a documented warning for 7–14 October 2019. Every applicable intraday specification must therefore be evaluated twice: once on the unchanged primary data and once after excluding the warned interval. If exclusion changes the sign of the estimated effect, the family-level support decision, or multiplicity-adjusted inference, the affected family must be classified as alignment-sensitive and unsupported for commercial interpretation.

Long-horizon time-series momentum and daily gold–silver relative value retain their separately documented warm-up and availability rules. They are not permitted to contribute pre-2015 evidence to the primary intraday cross-feed comparison.

## Source binding and immutability

Every registry row is bound to an exact source script, source configuration, and SHA-256 digest. The machine-readable JSON is authoritative; the CSV is a tabular projection for review. The registry validator rebuilds both files from the six bound configurations and requires a byte-exact match. Any change to a signal definition, direction, horizon, entry or exit rule, parameter, eligibility rule, timestamp treatment, or source binding creates a new registry version and must be recorded in the deviation log before performance is recomputed.

Independent-feed signal replication is required for the successor rules and the canonical time-series-momentum rule. It is not claimed for the cross-asset blocks because their locked feature panel contains AMarkets-derived XAU inputs; substituting only a Dukascopy outcome would not reproduce the same signal-generating process. This limitation is reported rather than concealed behind target-only replication.

The final execution manifest is intentionally not frozen in this registry artifact. The validated runner creates it immediately before outcome computation so that it can bind the installed runner, dependency environment, evaluation costs, resampling method, multiplicity procedure, random seeds, and output schema as they exist on the research workstation. The runner then verifies those frozen bindings again before reading reference outcomes.

## Remaining gate before the consolidated rerun

The next admissible sequence is:

1. validate the registry, source hashes, and required input hashes in the current repository;
2. install the validated unified outcome-blind runner without inspecting new consolidated performance output;
3. freeze the runner hash, environment, statistical settings, and registry hash in `main_run_manifest.json`;
4. execute the consolidated rerun once and retain all specifications, including failures and zero-trade rules.

No paper, demo, or live order is authorized by this registry.
