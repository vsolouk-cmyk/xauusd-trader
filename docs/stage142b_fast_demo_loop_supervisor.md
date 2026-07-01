# Stage142B Fast Demo Loop Supervisor

Stage142 showed the right loop state but also showed a practical problem:
- Stage138 refresh can time out inside a 10-minute operational loop.

Stage142B keeps the high-frequency loop focused:
- Stage134 collector
- Stage139 position outcome collector
- Stage140 closed deal outcome collector
- Stage141 outcome ledger

Stage138 refresh is excluded by default and is only run when explicitly requested:

```bash
python3 app/stage142_demo_loop_supervisor.py \
  --root /Users/vahid/Desktop/xauusd-trader \
  --with-stage138-refresh \
  --write-mt5 \
  --timeout-sec 300
```

Normal fast loop:

```bash
python3 app/stage142_demo_loop_supervisor.py \
  --root /Users/vahid/Desktop/xauusd-trader \
  --write-mt5
```

Stage142B does not send orders and does not modify positions.
The only order sender remains the Stage134 EA on the MT5 demo chart.
