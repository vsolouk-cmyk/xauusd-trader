# Stage28C Forward-Safe Meta-Gate Validation

Stage28C validates the strict forward-safe meta-gates found by Stage28B Hotfix2.
It does not modify Stage18A, Stage23D, Stage25D, or Stage27D and it does not authorize paper/live/EA/order execution.

The main purpose is to reduce selection and threshold leakage risk:

1. full-sample static thresholds are reproduced only as diagnostic evidence;
2. expanding event-by-event thresholds use only earlier events;
3. yearly walk-forward thresholds use only prior years;
4. leave-one-year-out checks robustness.

The first target cluster is the Stage28B winning range-strength gate family:
`london_range >= q40` combined with `prior_day_range >= q25/q30/q35/q40`, plus nearby London/Asia range alternatives.

Run:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage28c_forward_safe_meta_gate_validation
cat data/reports/stage28c_forward_safe_meta_gate_validation/stage28c_forward_safe_meta_gate_validation.md
```
