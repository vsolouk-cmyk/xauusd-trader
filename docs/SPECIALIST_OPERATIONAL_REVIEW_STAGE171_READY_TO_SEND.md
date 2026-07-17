# Operational Review for Specialist — H64L Rescue After Final Recommendation

**Review period:** from adoption of the specialist’s latest H64L-rescue recommendation through 2026-07-14  
**Purpose:** independent reassessment of H64L’s role and the project’s next commercial step.

## Executive conclusion

The specialist recommendation was directionally valuable: it stopped a broad deterministic-scan/methodology loop and forced attention onto a concrete macro thesis. The project successfully recovered the exact H64L rule and built a fail-closed forward data/shadow pipeline.

However, the operational work also exposed assumptions that weaken the case for treating H64L as the main path:

1. the historical edge and claimed replication have not yet been independently reproduced under a current historical-as-of audit;
2. the initial forward inputs contained material source/semantic defects;
3. the exact rule is structurally expected to be low-frequency because it requires four simultaneous macro tailwinds; Stage172 must quantify the actual independent episode frequency;
4. after the data defects were repaired, the first two valid forward snapshots produced a clean `NO SIGNAL` with all four conditions failing;
5. extensive plumbing work delivered operational readiness but no evidence yet of commercial expectancy.

The recommended program decision is therefore:

> Keep H64L as an unattended macro-regime overlay, complete one final historical-as-of decision audit, and immediately develop a primary intraday trade generator in parallel. Do not wait for H64L forward hits.

## 1. Specialist recommendation adopted

The last specialist view was interpreted as follows:

- stop broad deterministic scanning;
- do not continue universal methodology infrastructure as the main path;
- rescue H64L because archived evidence reportedly showed a strong z-score, independent replication and coherent macro logic;
- retain GDELT only as guard/context;
- consider supervised learning as a second path after H64L rescue.

The project accepted that direction and created Stage171 as a narrow rescue track.

## 2. Exact rule recovered

The archived exact rule was recovered and locked with high confidence:

- `gold_sma20_over_50 > 0`
- `dxy_ret_20d < 0`
- `real_yield_change_20d < 0`
- `etf_flow_tonnes_3m > 0`

No threshold reoptimization was performed. Order routing remained disabled.

The four condition thresholds are locked. The original holding horizon, independent-episode construction and historical release/as-of convention are not yet locked by the recovered artifact and must be resolved or explicitly governed in Stage172 without selecting among alternatives by performance.

## 3. Operational implementation completed

The following capabilities now work:

- durable H64L shadow ledger;
- exact-rule metadata and governance;
- four-hour local orchestrator;
- official macro download and normalization;
- stale-source blocking;
- current forward feature materialization;
- current-event GDELT guard intake;
- persistent DXY series with source validation and non-destructive backup;
- no-order/no-demo controls.

This is meaningful infrastructure, but it should now be frozen unless a genuine operational failure appears.

## 4. Material discrepancies found during rescue

### 4.1 ETF feature semantics and unit

An earlier forward value around `12349.69` was being accepted as `etf_flow_tonnes_3m`. That magnitude was not credible as a three-month tonnes flow. The new materializer currently interprets the feature as the difference in monthly total holdings and obtains about `-433.53` tonnes between February and May 2026. This is an operational interpretation, not proof that it matches the archived Stage64R feature definition.

This correction changes the current condition from a pass to a fail. Before any future positive H64L signal is used, the specialist should confirm the exact archived Stage64R ETF definition:

- sum of monthly fund flows;
- difference in total holdings;
- regional/global aggregation;
- gross or net tonnes;
- release-date/as-of convention.

### 4.2 DXY source contract

The pipeline initially selected FRED `DTWEXBGS`, which is a broad trade-weighted dollar index, not ICE DXY. It is now rejected as a silent substitute.

Direct Yahoo `DX-Y.NYB` requests currently return 429, and Stooq returns HTML rather than data. The operational source is now an ICE-formula reconstruction from six official FRED FX rates. It passes overlap and plausibility controls, but the specialist should confirm whether a formula-reconstructed index is acceptable for the original H64L rule or whether direct ICE settlement/reference data is mandatory.

### 4.3 Historical Stage64K versus forward data

The archived Stage64K builder was a historical/preflight artifact and could rebuild successfully while remaining frozen at June 2026. A dedicated forward materializer was required. This shows that prior infrastructure readiness did not equal operational forward readiness.

## 5. Current valid forward observations

Valid snapshots exist for 2026-07-10 and 2026-07-13.

In both:

- `gold_sma20_over_50 < 0`;
- `dxy_ret_20d > 0`;
- `real_yield_change_20d > 0`;
- `etf_flow_tonnes_3m < 0`.

Therefore H64L is unambiguously inactive. This does not refute historical edge, but it demonstrates the likely sparsity of a four-condition conjunction.

## 6. Where the project diverges from the optimistic specialist interpretation

The project has not disproved the claimed historical H64L result. It has shown that the claim cannot yet be treated as commercially sufficient because:

- the original historical episode/trade table and frequency have not been re-audited in the current path;
- feature semantics required substantial repair;
- two current valid observations are inactive;
- a primary trading system cannot depend on an unknown waiting time for a rare macro regime;
- commercial usefulness requires both edge and opportunity frequency.

Thus the revised interpretation is:

> H64L may be a valuable high-conviction regime overlay, but it is not yet justified as the primary trade generator.

## 7. Requested specialist decisions

Please provide an explicit view on these questions:

1. Was H64L originally intended as a standalone entry generator, a long-only macro allocation regime, or an overlay/filter on intraday entries?
2. What were the exact independent episode count, annual frequency, holding horizon, cost assumptions, z-score calculation and holdout years behind the reported strong result?
3. What exact ETF feature definition was used in Stage64R?
4. Is formula-reconstructed ICE DXY acceptable, or must the audit use a direct DXY reference series?
5. Should a positive but fewer-than-six-episodes-per-year result be classified as overlay-only?
6. Do you agree that the active path should now be a parallel intraday baseline shortlist rather than waiting for H64L?

## 8. Proposed Stage172

### Track A — final H64L audit

- exact rule only;
- historical-as-of joins;
- locked final ~20% holdout;
- independent episode count and spacing;
- net expectancy after costs;
- drawdown and concentration;
- drift/baseline comparison;
- final classification: `KILL`, `OVERLAY_ONLY` or `SHADOW_CANDIDATE`.

### Track B — primary generator shortlist

Only three families:

1. higher-timeframe trend plus intraday pullback;
2. London/NY breakout or continuation;
3. volatility expansion with macro/news guards.

No supervised model should begin until one simple cost-aware baseline survives the locked holdout.

## Final recommendation

Freeze Stage171 infrastructure. Continue unattended H64L observation. Do not wait for a hit. Complete the H64L audit and primary intraday shortlist in parallel. Commercial evidence—not additional pipeline readiness—must determine the next promotion.
