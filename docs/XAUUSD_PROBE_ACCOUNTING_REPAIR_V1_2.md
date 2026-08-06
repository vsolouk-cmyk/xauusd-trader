# XAUUSD Demo Probe Accounting Repair V1.2

This patch does not authorize or emit a new qualification probe.

It repairs terminal execution accounting in the MT5 bridge by:

- capturing the executable exit-side quote immediately before `PositionClose`;
- retrying MT5 history synchronization and selecting the terminal deal explicitly;
- recording the terminal deal price, realized profit, commission, swap, and fee;
- calculating adverse exit slippage in basis points;
- requiring non-zero exit requested/fill prices in future qualification inspection;
- tying the Python bridge, arming verifier, operational cycle, probe operator, and tests to the new EA program contract.

Existing V1.1 evidence remains valid for execution-plumbing qualification. Do not repeat a probe only to regenerate accounting fields.

After installation, native MetaEditor compilation is mandatory before re-arming.
