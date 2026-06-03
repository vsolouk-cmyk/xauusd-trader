# Paste this into the new XAUUSD project

We are starting a separate XAUUSD/gold research project after freezing active strategy development in the crypto n8n-trader project.

The crypto project remains active only for scheduled data collection/observation. The active strategy objective moves to XAUUSD, but carefully and baseline-first.

The XAUUSD project must not start with ML or a bot. It must start with:

1. Data source decision.
2. Data collection and quality checks.
3. Baseline lab.
4. Regime ON/OFF model only if baselines work.
5. Forward shadow.
6. Paper-order only if forward shadow works.

Key process rules:

- Minimize back-and-forth.
- Provide ready-to-copy files.
- No bash install scripts.
- Safe Git commands only.
- Include workflow files when workflow behavior is affected.
- Do not rely on gh CLI.
- Critical, direct evaluation is preferred over reassurance.
- Use hard kill-switches to avoid long unproductive testing.

Initial research thesis:

XAUUSD may be better suited than the current crypto microstructure path because it is a single focused symbol with stronger institutional market structure, recognizable sessions, macro drivers, and baseline families such as trend following, volatility/session breakout, and higher-timeframe bias. However, this is not assumed; it must be validated with data and baselines before any ML or bot execution.

Do not copy the crypto microstructure model into XAUUSD. Build the XAUUSD project around data quality, baseline validation, and regime-aware ON/OFF filtering.
