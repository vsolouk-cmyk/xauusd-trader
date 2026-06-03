# XAUUSD Project Operating Rules

Carry these process rules into the new XAUUSD project.

## Collaboration rules

- Minimize back-and-forth.
- Do not ask for confirmation when the next technical step is clear.
- Provide ready-to-copy files, not code-injection snippets, whenever changes are non-trivial.
- Do not provide bash install scripts.
- Provide safe Git commands only: `git add -A`, `git commit`, `git pull --rebase`, `git push`.
- Do not rely on `gh` CLI.
- Include GitHub Actions workflow files whenever workflow behavior is affected.
- Always state which workflow to run from GitHub UI.
- Be direct and critical; do not reassure if a path is weak.

## Technical environment inherited from crypto project

- Local repo pattern: `~/Desktop/<repo-name>`.
- Downloads path: `~/Downloads`.
- Python command: `python3` locally.
- GitHub Actions are available but scheduling is unreliable.
- Avoid assuming precise cron execution.

## Research rules

- Baseline-first.
- Data-quality-first.
- No ML until simple baselines are tested.
- No paper-order until forward shadow passes.
- No live until paper-order passes.
- Every phase needs a kill-switch.
- If a path shows deterioration or fails to beat a simple baseline, stop quickly.

## XAUUSD-specific cautions

- XAUUSD is sensitive to sessions, news, dollar, yields, volatility, and broker spread.
- Do not build a scalping bot first.
- Treat spread/slippage/news windows as first-class features or filters.
- Broker feed matters; OANDA/MT5/CFD/futures feeds may differ.
