# Stage 4G next steps

Recommended process after running the AMarkets backfill validator:

1. Keep Stage 5A EA running in dry-run mode.
2. Run Stage 4G locally on AMarkets H1/M1 exports.
3. If Stage 4G fails, do not proceed to demo-order design; diagnose broker-feed mismatch.
4. If Stage 4G passes or passes with warnings, continue collecting live dry-run signals.
5. Add Stage 5C outcome tracker to resolve live dry-run signals using TP24/SL15/time-exit.

No order placement is authorized by this stage.
