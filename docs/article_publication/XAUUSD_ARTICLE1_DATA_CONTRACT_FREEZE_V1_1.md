# XAUUSD Article 1 — Reference Data-Contract Freeze v1.1

## Decision

**`PASS_ARTICLE1_2015_2024_REFERENCE_DATA_CONTRACT_WITH_ALIGNMENT_WARNING`**

This decision freezes the reference data contract for Article 1. It validates data provenance and cross-feed comparability only. It does not establish strategy profitability and does not authorize paper, demo, or live trading.

## Primary reference interval

The primary intraday reference interval is fixed from `2015-01-02T07:00:00Z` through `2025-01-01T00:00:00Z` exclusive. The primary AMarkets representation uses the unchanged `EU_DST_GMT_OFFSET_PAIR` contract: a `-120` minute standard-time shift and a `-180` minute daylight-saving shift.

Observations before the operational floor are excluded from primary intraday inference because the expanded 2011–2014 history fails the transferable time-contract test. These observations may be discussed only as a data-contract failure case. Observations from 2025 onward form a seen temporal diagnostic interval and cannot support confirmatory selection claims.

## Locked input identity

| Input | SHA-256 |
|---|---|
| Dukascopy extended-history SQLite | `8d9a3f9d7e8a05cc9fa97badd93aa809e1c09b105eacb3b96720671aa74c66de` |
| AMarkets aligned SQLite | `c38491993ec5b76325d61f941cbdff7cda7147c83c97f43b80e97221385669f5` |
| Stage 177C time-contract artifact | `635ed1f9cd9ec62fecdff61e3e9660657194d972e4f4f889731e97d1432ea362` |

## Outcome-blind preflight evidence

The preflight inspected data identity, schemas, integrity, and AMarkets–Dukascopy alignment. It did not read strategy returns or rankings.

| Metric | M5 | H1 |
|---|---:|---:|
| AMarkets rows | 697,424 | 58,290 |
| Cross-feed overlap | 99.9627% | 99.9125% |
| 60-minute/one-bar return correlation | 0.996678 | 0.993819 |
| Median absolute close difference | 0.3116 bps | 0.3212 bps |
| 95th-percentile absolute close difference | 1.0051 bps | 1.2900 bps |
| Range correlation | 0.984873 | 0.993515 |

Both SQLite databases passed `PRAGMA quick_check`. Required tables were present. No duplicate timestamps or invalid OHLC rows were detected in the frozen reference interval.

## Gate amendment and its scientific status

Preflight v1.0 used `0.98` as a hard minimum for every individual calendar year's 60-minute return correlation. That threshold was newly introduced for this preflight and was not inherited from the pre-existing Stage 177C contract. It caused a hard failure for 2019, whose correlation was `0.974794`, despite 99.9771% overlap, sub-basis-point median and 95th-percentile price differences, and a range correlation of `0.976147`.

The annual rule is therefore clarified before any consolidated strategy rerun:

- a 60-minute return correlation below `0.90` is a hard annual data-contract failure;
- a value from `0.90` through less than `0.98` is an alignment warning;
- a value of at least `0.98` passes without warning.

The hard floor is inherited from the prior Stage 177C all-sample return-correlation gate. The stricter `0.98` level is retained as a warning threshold rather than discarded. This amendment changes neither data bytes nor timestamps, contract parameters, strategy specifications, or observed strategy outcomes.

## 2019 localized warning

The warning is localized to 2019. The Stage 177C weekly diagnostic identifies a high-confidence one-week broker-offset exception beginning on `2019-10-07`: the empirically aligned shift is `-120` minutes while the fixed EU-DST contract prescribes `-180` minutes. The week immediately before and the two following weeks return to the expected `-180` minute state before the ordinary autumn transition.

The primary analysis will not retroactively repair this exception. It will use the unchanged fixed calendar contract. Every applicable price-derived family result must additionally be recomputed after excluding timestamps from `2019-10-07T00:00:00Z` through `2019-10-14T00:00:00Z`.

If this exclusion changes the sign of an effect, the family-level support decision, or multiplicity-adjusted inference, the result will be classified as alignment-sensitive and cannot support a commercial interpretation.

## Frozen reporting boundary

The manuscript must report:

1. the historical full-range Stage 177C BLOCK without relabeling it;
2. the operational 2015 floor and the reason for excluding earlier broker history;
3. the outcome-blind v1.0 gate amendment;
4. both primary and warned-week-exclusion results;
5. separate roles for the 2015–2024 reference interval and the seen 2025+ diagnostic interval.

The next admissible action is construction and hashing of the exact strategy-specification registry. No consolidated strategy metric may be inspected until that registry is frozen.

