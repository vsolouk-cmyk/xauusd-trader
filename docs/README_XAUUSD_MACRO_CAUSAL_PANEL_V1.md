# XAUUSD Macro Causal Panel V1.1 — Gold As-of / Execution Repair

Repairs a gold-side look-ahead defect in V1. A decision row dated D now uses only the completed gold D1 bar from the previous trading row. The executable target enters at the open of D and exits at the close exactly 5 or 20 trading rows later. Same-day gold OHLC is not present in the feature file. Macro series remain availability-time aligned and forward targets remain physically separate.

The existing GVZ file is reused; no new download is required when it is already present. No paper, demo, MT5, broker, or live execution path exists.
