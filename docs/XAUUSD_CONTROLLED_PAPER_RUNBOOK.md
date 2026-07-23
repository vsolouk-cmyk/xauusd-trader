# XAUUSD Controlled-Paper Bidirectional Runbook

## Purpose

Run the frozen Stage178/Stage180 candidate as a paper-only bidirectional probability-tail logger without broker connectivity.

## Direction contract

```text
LONG  = probability_up >= 0.60
SHORT = probability_up <= 0.40
NO POSITION = 0.40 < probability_up < 0.60
```

The Stage180 `direction` field is non-execution metadata. Side is derived only from probability tails.

## Order semantics

```text
signal row = i
entry = open of aligned AMarkets H1 row i+1
exit = close of aligned AMarkets H1 row i+24
```

## Observable guards

The entry spread guard uses the entry-hour spread for both LONG and SHORT. This is deliberately no-lookahead. Event data is mandatory and fails closed when absent.

## Cost semantics

```text
LONG observed spread  = entry M5 first spread
SHORT observed spread = exit H1 bucket final M5 spread
normal = max(3.0, observed spread + 0.5)
severe = max(4.5, observed spread * 1.5 + 2.0)
stress8 = max(8.0, observed spread + 4.0)
stress10 = max(10.0, observed spread + 6.0)
```

## Commands

```bash
python3 app/xauusd_controlled_paper.py preflight --root .
python3 app/xauusd_controlled_paper.py run --root .
```

## Required historical evidence

The preflight requires the V6 replay summary at:

```text
reports/xauusd_controlled_paper_replay/historical_asof_replay_summary.json
```

It must prove:

- commercial ledger/source hashes;
- 146 evaluated and 22 missing rows;
- 55 LONG and 91 SHORT reference trades;
- source-proven cost formulas;
- commercial metric parity;
- forward direction-policy parity;
- no forward wait.

## Boundary

No broker, demo, or live order is authorized.
