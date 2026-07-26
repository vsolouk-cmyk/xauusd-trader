# XAUUSD MT5 Login-Bound Review and Dry Cycle

This package accepts both the current V1.1 runtime success label
`PASS_MT5_DEMO_BRIDGE_RUNTIME_PREFLIGHT_DISABLED_NO_ORDER` and the optional
more-specific ready label. Authorization depends on `pass=true`,
`runtime_installation_pass=true`, `arming_readiness_pass=true`, empty failure
lists, DEMO mode, login 7907958, and the locked volume contract—not on wording
alone.

It creates only:

- a login-bound review report;
- reviewed inputs with `InpArmed=false`;
- a non-executable permit preview with `authorized=false`;
- an in-repo dry candidate preview.

It never writes `MQL5/Files/XAUUSD_DEMO_BRIDGE/arming_permit.txt` and never writes
the active MT5 candidate filename.
