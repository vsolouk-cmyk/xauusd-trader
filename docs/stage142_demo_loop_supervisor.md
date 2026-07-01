# Stage142 Demo Loop Supervisor

Stage142 coordinates the demo execution loop after the first profitable Stage141 ledger entry.

It does not send orders and does not modify positions. The only order sender remains the Stage134 EA on the MT5 demo chart.

Default sequence:
1. Stage138 broker technical discovery refresh
2. Stage134 demo executor collector
3. Stage139 position outcome collector
4. Stage140 closed deal outcome collector
5. Stage141 outcome ledger

Purpose:
- keep the loop operational,
- avoid manual scatter,
- preserve duplicate control,
- summarize whether the system is ready for the next distinct signal.

Run:

```bash
python3 app/stage142_demo_loop_supervisor.py \
  --root /Users/vahid/Desktop/xauusd-trader \
  --write-mt5
```

The next order is only allowed if Stage134 sees a distinct new signal key.
