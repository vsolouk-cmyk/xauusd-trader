# Stage60 Demo Fast-Lane Policy

A demo account can accelerate execution plumbing validation, but it does not replace true-forward evidence for edge validation.

Recommended policy:

- Keep forward-shadow as the statistical evidence layer.
- Allow demo execution sandbox earlier only for order-routing, spread/slippage behavior, logging, reconnect, and kill-switch testing.
- Do not treat demo fills as proof of edge until signal generation is true-forward and sufficient.
- No paper-live or live trading is authorized by this stage.
