# Stage177C — AMarkets DST-Aware UTC Contract

## Purpose

Stage177B proved that AMarkets 2022+ overlaps Dukascopy, but a single fixed
shift produced competing peaks at -120 and -180 minutes. Stage177C determines
whether those peaks form a stable broker-server DST contract.

This stage is research-only. It authorizes no paper, demo, or live orders.

## Method

1. Load AMarkets M5/H1 with the repaired Stage177B parser.
2. Evaluate candidate offsets per trading week.
3. Smooth weekly states with a transition-penalized Viterbi path.
4. Construct transferable candidates:
   - fixed offset;
   - US DST calendar with the inferred offset pair;
   - EU DST calendar with the inferred offset pair.
5. Infer candidate offset states and select the contract using only data before 2025-01-01.
6. Lock that contract, then validate it on the untouched 2025+ holdout.
7. Apply the selected contract to M5 and H1.
8. Derive UTC H1 from aligned M5 and compare it with canonical Dukascopy H1.
9. Only after all gates pass, write a separate AMarkets alignment SQLite DB.

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 app/stage177c_amarkets_dst_contract.py
```

## Outputs

```text
reports/stage177c_amarkets_dst_contract/stage177c_summary.json
reports/stage177c_amarkets_dst_contract/stage177c_decision.md
reports/stage177c_amarkets_dst_contract/stage177c_time_contract.json
reports/stage177c_amarkets_dst_contract/stage177c_train_weekly_offset_scores.csv
reports/stage177c_amarkets_dst_contract/stage177c_train_weekly_selected_states.csv
reports/stage177c_amarkets_dst_contract/stage177c_train_offset_segments.csv
reports/stage177c_amarkets_dst_contract/stage177c_weekly_offset_scores.csv
reports/stage177c_amarkets_dst_contract/stage177c_weekly_selected_states.csv
reports/stage177c_amarkets_dst_contract/stage177c_offset_segments.csv
reports/stage177c_amarkets_dst_contract/stage177c_contract_candidates.csv
```

On PASS only:

```text
data/local/stage177c_amarkets_alignment/xauusd_amarkets_alignment.sqlite
```

The local database directory contains a `.gitignore`; raw/aligned market data
must not be committed.

## Decisions

- `PASS_AMARKETS_DST_AWARE_UTC_CONTRACT`
- `REVIEW_AMARKETS_DST_CONTRACT`
- `BLOCK_AMARKETS_TIME_CONTRACT_UNRESOLVED`

A review/block exit code is 2 by design; reports are still written.
