# Stage27C — DB-First H1 ATR Gate Validation

Stage27C independently validates the strongest Stage27B gate, `h1_atr_drop_low30`, around the canonical Stage23/25 lineage.

It is research/shadow validation only. It does not modify Stage18A, Stage23D, Stage25D, any EA, paper/live flow, or orders.

Key design constraints:

- Market candles are DB-first via the validated Stage25C loader.
- AMarkets CSV market fallback is disabled.
- The canonical trade artifact is used only as research artifact.
- H1 ATR is anti-leakage checked: the H1 bar used at entry must be fully completed before or at the entry timestamp.
- The primary gate is `h1_atr_drop_low30_strict_completed`.

Run:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage27c_db_first_h1_atr_gate_validation
cat data/reports/stage27c_db_first_h1_atr_gate_validation/stage27c_db_first_h1_atr_gate_validation.md
```
