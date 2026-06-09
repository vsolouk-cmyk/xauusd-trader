# Stage 8B Single Regime Thesis Lab

Stage 8B converts the strongest actionable Stage 8A discovery into one testable thesis.

## Thesis

```text
h4_up_compression_long_continuation_v1
```

Rationale:

- Stage 8A showed favorable long forward distribution in H4 uptrend.
- Stage 8A showed favorable long forward distribution in mid_high compression.
- Stage 8A showed favorable long forward distribution in London-NY overlap / New York.
- Year=2025 is not used as a trading rule.

## Definitions tested

Same thesis, limited execution definitions:

```text
base_h4up_compression_mid_high
liquidity_session
confirmed_h1
confirmed_session
```

## Exit geometries

```text
time_exit_12h
tp15_sl12_h12
tp18_sl12_h12
tp24_sl15_h12_control
```

Both overlap and non-overlap execution are reported. Macro-blocked and unguarded variants are reported.

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage8b_single_regime_thesis_lab
cat data/reports/stage8b_single_regime_thesis_lab/stage8b_single_regime_thesis_lab.md
```

## Run with shock window

```bash
python3 -m app.stage8b_single_regime_thesis_lab \
  --shock-window 2026-06-08T00:00:00Z,2026-06-10T23:59:00Z,iran_israel_shock

cat data/reports/stage8b_single_regime_thesis_lab/stage8b_single_regime_thesis_lab.md
```

## Outputs

```text
data/reports/stage8b_single_regime_thesis_lab/stage8b_single_regime_thesis_lab.md
data/reports/stage8b_single_regime_thesis_lab/stage8b_single_regime_summaries.csv
data/reports/stage8b_single_regime_thesis_lab/stage8b_single_regime_trades.csv
data/reports/stage8b_single_regime_thesis_lab/stage8b_single_regime_thesis_lab.json
```

## Hard rule

Research only. No EA change, no demo, no paper, no live authorization.
