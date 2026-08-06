# XAUUSD/Gold Project — Methodology Audit and External Review Brief

Generated: 2026-07-09  
Prepared for: senior quantitative / systematic-trading reviewer  
Scope: XAUUSD/gold trading-system research after Stages 160–169, with special focus on whether event/news shock data should remain in alpha discovery, and whether the current data-mining / validation methodology is technically reliable.

---

## 1. Executive conclusion

The current conclusion should **not** be stated as “news/event data are useless and should be discarded.” A more precise conclusion is:

> With the current GDELT-derived article-count / keyword-score features and the deterministic event-reaction rule spaces tested in Stage167–168, the news/event branch has **not produced a commercially promotable alpha candidate** under the current holdout, cost, frequency, hit-rate, and left-tail gates. Therefore it should be removed from **execution alpha discovery for now**, but retained as a **current-event regime/risk guard** and as a candidate input for a future, better-labeled supervised/event-study framework.

This is a technically defensible interim decision, but it is **not a proof** that news/event data cannot help XAUUSD prediction. It is only a rejection of the current representation and rule-space.

The current workflow is strong in operational discipline, use of broker data, newest-holdout testing, and explicit kill decisions. However, it is not yet sufficient to claim that the best available data-mining and predictive methods have been applied. The main methodological gaps are: as-of timing verification across heterogeneous macro/news datasets, event-latency modeling, insufficiently labeled news events, lack of purged/embargoed cross-validation, lack of multiple-testing correction, coarse cost/slippage modeling, and absence of supervised meta-labeling / triple-barrier style candidate qualification.

Therefore, before continuing commercial discovery, the project should run a formal **Stage170A Methodology & Temporal Integrity Audit** rather than immediately continuing with another rule scan.

---

## 2. Data inventory and roles

### 2.1 Broker / technical data

Current main technical source:

- AMarkets XAUUSD M5, with around 319k rows from 2022-01-02 to 2026-07-09.
- Spread column present and non-null.
- This is the correct primary data source for executable strategy research because it reflects the broker environment better than generic vendor candles.

Role:

- Main source for tradeable price behavior.
- Should be used for labels, spread/cost proxy, volatility regimes, session behavior, and execution replay.

### 2.2 Scheduled/fundamental data

The project has already collected or constructed multiple fundamental/calendar/macro sources, including FRED-style macro variables, COT/CFTC, ETF/GLD/SPDR, WGC/central bank gold and economic calendar/event data.

Current concern:

- These sources are heterogeneous and have different release lags, revision behavior, time zones, and market-impact horizons.
- They must be audited under an **as-of availability model**. For example, revised macro data cannot be used as if it was available at the historical decision time.

Role:

- Best suited for regime priors, macro gating, scenario context and longer-horizon filters.
- Should not be directly mixed into intraday rules unless release time, publication lag and revision/vintage behavior are explicitly modeled.

### 2.3 News / shock data

Three attempted event/news paths exist:

1. Stage166D: market-implied post-shock proxy from XAUUSD behavior.
2. Stage166E: current-event RSS/API/manual intake. This became current-regime operational but not historically trainable.
3. Stage166F: GDELT historical backfill through GitHub Actions. This produced a historical, trainable event panel.

Outcome:

- GDELT from the local Mac failed with TLS timeout, but GitHub Actions successfully downloaded a usable artifact.
- Stage167C corrected sparse-threshold logic and scanned 120 event-aware rules; shortlist was zero.
- Stage168 broadened the GDELT reaction surface to 7,500 rules; shortlist was still zero.
- Stage169 killed the GDELT/news branch as execution alpha and retained it as current-event guard only.

Interpretation:

- The event panel is not technically empty anymore.
- The failure is now a **model / feature / rule-space failure**, not a data-ingestion failure.

---

## 3. What has been done so far

### 3.1 Stage166–166F: event/news panel construction

- Initial Stage166 current-event overlay was too sparse: only a few recent rows and no historical trainability.
- Stage166B/C attempted GDELT history directly but local network/TLS timeouts made it impractical.
- Stage166D created an offline market-implied post-shock proxy; it was trainable, but it is not external-news-backed and should not be interpreted as ex-ante news prediction.
- Stage166E ingested manual/RSS/API downloads and produced a current-event guard, but not a historically trainable panel.
- Stage166F used GitHub Actions to fetch GDELT history and produced a historical event panel.

### 3.2 Stage167–167C: event-aware medium-frequency rules

- Stage167 originally fast-stopped because the event panel was too sparse.
- Stage167B added health checks and correctly stopped when only recent events existed.
- Stage167C fixed sparse event quantiles by computing thresholds on the positive train distribution rather than all M5 bars.
- Stage167C scanned 120 rules after correction, but commercial shortlist remained zero.

### 3.3 Stage168: broader GDELT reaction rule space

- Stage168 scanned 7,500 GDELT reaction rules across event columns, entry lags, horizons, confirmations and sides.
- The panel was trainable, but no candidate survived the commercial gates.
- Some failed candidates had attractive holdout mean returns but failed because of low train sample count, weak train performance or left-tail problems.

### 3.4 Stage169: branch decision

- Stage169B killed the GDELT/news branch as an execution alpha source.
- It retained the panel as a current-event guard only.
- Current guard state was low, with a long safe-haven/dovish bias, but the action remained “log context only; do not use as alpha.”

---

## 4. Is it technically logical to remove news from alpha discovery?

### 4.1 Correct answer

Yes, but only conditionally:

- It is technically logical to stop using the **current GDELT keyword/count reaction rule-space** as an alpha discovery path.
- It is not technically logical to permanently discard all news/event information.

The correct stance is:

> Kill the current event-reaction rule alpha; preserve event/news as a regime guard and redesign the event thesis only if stronger labeled event data or a better supervised framework is introduced.

### 4.2 Why the kill decision is defensible

The kill decision is defensible because:

- The event panel became historically trainable.
- Sparse-threshold error was fixed.
- A broad reaction rule surface was tested.
- Newest 20% holdout and cost gates were applied.
- No candidate passed.

That is sufficient to reject the current implementation path.

### 4.3 Why this is not proof that news is useless

This is not proof that news cannot predict gold because:

- GDELT article counts are a noisy proxy for event intensity.
- Keyword buckets are not the same as hand-labeled market-relevant events.
- Publication time is not necessarily event time.
- Daily/hourly article volume may lag price movement rather than lead it.
- Event types may require different horizons: FOMC minutes, CPI shock, war escalation, oil shock and central-bank gold demand should not be treated with one generic reaction logic.
- Nonlinear interactions with DXY, real yield, volatility, liquidity session, and gold’s pre-event trend were not exhaustively modeled.

---

## 5. Correctness audit: what is strong and what remains weak

### 5.1 Strong points

The project has several technically strong components:

1. Broker-native M5 data is used, including spreads.
2. Newest 20% holdout is used, which approximates practical historical-as-of validation.
3. Stage outputs explicitly block demo/live release until gates pass.
4. The system is now willing to kill branches rather than wait indefinitely for low-frequency samples.
5. Event panel health checks were added after sparse-panel problems were identified.
6. GitHub Actions successfully bypassed the local-network GDELT bottleneck.

### 5.2 Weak / unresolved correctness risks

#### 5.2.1 As-of timing and information availability

The project must verify every feature under an `availability_time_utc` model. Required fields per feature:

- observation_time_utc
- release_time_utc
- ingestion_time_utc
- availability_time_utc
- source_timezone
- revision/vintage policy
- expected impact horizon

Without this, a feature can accidentally use information unavailable at the trade decision time.

High-risk examples:

- FRED/macroeconomic data revisions.
- COT report release timing versus reporting week end.
- ETF/GLD holding updates released after market hours.
- GDELT publication time versus actual event time.
- Manual events entered after the fact.

#### 5.2.2 Heterogeneous data alignment

A single “join nearest/as-of to M5” approach is not enough. Different features need different temporal semantics:

- Scheduled release shock: exact timestamp, short event window.
- Macro level: daily/weekly as-of regime state.
- COT: weekly delayed positioning state.
- ETF flow: daily close/update regime.
- GDELT/news: publication-time intensity, potentially lagging actual event.
- Market-implied shock: post-shock proxy only, never ex-ante news.

#### 5.2.3 Event-feature adequacy

Current event features are primarily article-count / keyword-score proxies. They are useful for intensity but weak for causality and directionality.

Missing or weak dimensions:

- Event novelty versus repeated coverage.
- Escalation/de-escalation label quality.
- Event geography and economic relevance.
- Asset-specific relevance to gold versus generic geopolitical volume.
- Market surprise: whether the event was already priced.
- Source reliability and duplication control.
- Latency between event occurrence and publication.

#### 5.2.4 Labeling method

Most tested rules used fixed horizons and simple return labels. This is interpretable but not necessarily optimal.

Better candidate-labeling framework should include:

- triple-barrier labels: profit-taking, stop-loss and vertical time barrier;
- volatility-scaled targets;
- adverse excursion and favorable excursion;
- meta-labeling to decide whether to take or skip a base signal;
- event-based sampling rather than every-bar sampling.

#### 5.2.5 Multiple testing / data-snooping risk

The project has run many stages and thousands of rule variants. Even with a holdout, repeated search creates data-snooping risk.

Required additions:

- candidate family registry and total test count tracking;
- Deflated Sharpe Ratio or related selection-bias correction;
- White Reality Check / Hansen SPA style test for broad rule universes;
- probability of backtest overfitting / combinatorial purged cross-validation where applicable.

#### 5.2.6 Validation design

The newest 20% holdout is necessary but not sufficient. The project should add:

- walk-forward expanding and rolling windows;
- purged/embargoed splits when labels overlap future horizons;
- regime-stratified validation: high-volatility, low-volatility, bull drift, dollar/rate regime, geopolitical shock regime;
- final untouched holdout only after candidate family design is frozen.

#### 5.2.7 Cost and execution realism

The cost model is currently a useful proxy, but still coarse. For execution readiness, it must include:

- broker spread from the actual bar / time of day;
- slippage scenario grid;
- fill timing: next bar open versus signal bar close;
- spread blowout around scheduled news;
- session-based liquidity;
- cooldown, max concurrent exposure, max daily loss, and stop behavior.

---

## 6. Efficiency audit: were the methods “best”?

No. They were appropriate for fast, interpretable triage, but not the best possible methods for final inference.

### 6.1 What the current methods are good for

The deterministic rule scans are good for:

- fast falsification of simple theses;
- interpretability;
- operational discipline;
- avoiding black-box overfitting at early stages;
- quickly identifying whether a large obvious effect exists.

### 6.2 What they are not good for

They are not ideal for:

- nonlinear interactions;
- delayed and heterogeneous event effects;
- conditional regimes;
- weak but persistent edge;
- interactions between macro, price action and event flow;
- meta-selection of when a base signal should be skipped.

### 6.3 More suitable next methodology

The next methodology should be layered, not purely rule-scan-based:

1. **Data integrity layer**  
   Build an availability-time feature registry and as-of replay checks.

2. **Event-study layer**  
   Measure abnormal return / volatility behavior around event classes before generating trading rules.

3. **Candidate signal layer**  
   Keep interpretable base rules, but separate signal generation from signal acceptance.

4. **Labeling layer**  
   Use volatility-scaled triple-barrier labels and MFE/MAE diagnostics.

5. **Meta-model layer**  
   Use simple supervised models first: logistic regression, regularized tree/gradient boosting, calibrated probability outputs. Avoid deep learning until data quality and validation are much stronger.

6. **Validation layer**  
   Use walk-forward + purged/embargoed CV + final newest holdout.

7. **Selection-bias layer**  
   Apply DSR/PBO/SPA-style adjustment across candidate families.

8. **Execution layer**  
   Only after a candidate passes, run realistic execution replay with broker spread, slippage, session and risk rules.

---

## 7. Comparison with external methodology

### 7.1 Event studies

MacKinlay’s event-study framework emphasizes event definition, event windows and abnormal returns relative to expected returns. This implies that before trading GDELT news counts, the project should first run event studies by event class and horizon. Current Stage168 went directly to rule scanning, which is faster but less diagnostically clear.

### 7.2 Real-time/vintage macro data

FRED/ALFRED documentation emphasizes real-time periods and vintage dates. This matters because macro data can be revised. The project should not use final revised macro values in historical decision points unless explicitly modeling them as ex-post research variables.

### 7.3 GDELT

GDELT DOC 2.0 and TimelineVolRaw can supply raw article-count time series, but this is a media-volume proxy, not a clean causal event label. It is useful as an event-intensity measure, less reliable as a directional alpha by itself.

### 7.4 Data snooping and backtest overfitting

White’s Reality Check and Bailey/Lopez de Prado’s Deflated Sharpe Ratio literature directly apply because this project has tested many rule variants. A candidate passing one holdout after extensive search is not enough unless selection bias is measured.

### 7.5 Gold and news/text literature

Recent research suggests news/text features can contain complementary predictive information for gold, but such studies often rely on NLP features, human-labeled headlines or richer text representations rather than only raw article counts. This supports the conclusion that news should not be discarded, but must be represented more carefully.

---

## 8. Recommended decision

### 8.1 Immediate recommendation

Do not run Stage170 non-news discovery yet as the next action. First run a formal methodology audit stage.

Recommended next stage:

> Stage170A — Methodology, Temporal Integrity and Feature Adequacy Audit

Purpose:

- freeze current state;
- audit all feature availability timing;
- classify every data source by latency, revision behavior and expected effect horizon;
- audit label construction and horizon overlap;
- define proper validation protocol;
- decide which candidate discovery families are methodologically allowed.

### 8.2 What to do with news now

- Keep Stage169 guard active.
- Do not use GDELT/news as direct alpha.
- Do not discard the GDELT artifact.
- Do not spend more time improving GDELT fetch coverage unless the next methodology explicitly requires it.
- Consider future labeled event dataset if external expert agrees.

### 8.3 What to do with non-news alpha

Proceed only after the audit confirms:

- technical features are as-of safe;
- labels are properly formed;
- validation protocol is robust;
- cost and execution assumptions are acceptable;
- multiple-testing discipline is in place.

---

## 9. Concrete questions for external specialist

1. Is the current decision to demote GDELT/news from alpha to guard technically justified given Stage167C and Stage168 outcomes?
2. Should the project invest in hand-labeled event data, or is GDELT/article-count data too weak for XAUUSD execution alpha?
3. What validation design is most appropriate: walk-forward, CPCV, purged k-fold with embargo, or a simpler holdout hierarchy?
4. Should labels be fixed-horizon returns or volatility-scaled triple-barrier labels?
5. Which feature families should be prioritized for gold: real yield/DXY regimes, central-bank demand, ETF flows, COT positioning, volatility regimes, session microstructure, or event shock flow?
6. What multiple-testing correction should be mandatory before a candidate can move to execution replay?
7. What minimum execution realism is required before demo release on MT5?
8. Should the project use supervised meta-labeling on top of interpretable base signals, or remain purely rule-based?
9. How should heterogeneous time availability be modeled for macro, COT, ETF, WGC, scheduled releases and news?
10. Should current-event guard ever block trades, size trades down, or only log context?

---

## 10. Proposed next deliverable

Create Stage170A with no trading/discovery output. It should produce:

- `stage170a_methodology_audit_summary.json`
- `stage170a_feature_availability_registry.csv`
- `stage170a_temporal_alignment_audit.csv`
- `stage170a_labeling_validation_audit.csv`
- `stage170a_methodology_decision.md`

Decision states:

- `METHODOLOGY_READY_FOR_NON_NEWS_DISCOVERY`
- `BLOCKED_BY_ASOF_TIMING_RISK`
- `BLOCKED_BY_LABELING_OR_VALIDATION_RISK`
- `REQUIRES_EXTERNAL_REVIEW_BEFORE_NEXT_DISCOVERY`

Given current evidence, the expected decision should be:

> `REQUIRES_EXTERNAL_REVIEW_BEFORE_NEXT_DISCOVERY`

---

## 11. External reference anchors

The following references are relevant to the audit and can be shared with a specialist:

1. A. Craig MacKinlay, “Event Studies in Economics and Finance,” Journal of Economic Literature, 1997.  
   https://www.bu.edu/econ/files/2011/01/MacKinlay-1996-Event-Studies-in-Economics-and-Finance.pdf

2. FRED API documentation on real-time periods and vintage dates.  
   https://fred.stlouisfed.org/docs/api/fred/realtime_period.html  
   https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html

3. GDELT DOC 2.0 API and TimelineVolRaw documentation.  
   https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/  
   https://blog.gdeltproject.org/gdelt-2-0-api-now-supports-raw-result-counts/

4. David H. Bailey and Marcos Lopez de Prado, “The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and Non-Normality,” 2014.  
   https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551

5. Halbert White, “A Reality Check for Data Snooping,” Econometrica, 2000.  
   https://www.ssc.wisc.edu/~bhansen/718/White2000.pdf

6. Sinha and Khandait, “Impact of News on the Commodity Market: Dataset and Results,” 2020.  
   https://arxiv.org/abs/2009.04202

7. Liu, “Textual analysis and gold futures price forecasting,” 2024.  
   https://www.sciencedirect.com/science/article/abs/pii/S1544612324011450

---

## 12. Final reviewer-facing status

The project is not blocked by lack of data alone. It is blocked by methodology risk. The correct next move is not another broad scan, but a formal audit of temporal integrity, feature adequacy, labeling, validation and multiple-testing correction. News/event data should stay in the system as a guard and potential future feature class, but the current GDELT-count reaction alpha branch should remain killed until stronger labels or better modeling justify reopening it.
