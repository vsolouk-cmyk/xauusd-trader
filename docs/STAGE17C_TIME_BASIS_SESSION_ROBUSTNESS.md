# Stage 17C Time-Basis and Session Robustness Audit

Stage 17C audits the promoted Stage17B candidate before forward-shadow design.

## Why this exists

AMarkets/MT5 CSV timestamps may be broker server time rather than real UTC.

If bar timestamps are ahead of the report's generated UTC time, a forward collector that compares wall-clock UTC to bar timestamps can accidentally treat broker-time bars as future/forward-valid data.

## Candidate

```text
pdh_breakout_continuation_long_h32_cool4
```

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage17c_time_basis_session_robustness
cat data/reports/stage17c_time_basis_session_robustness/stage17c_time_basis_session_robustness.md
```

## What it checks

```text
- latest raw M1 bar timestamp vs generated UTC
- whether bar clock is likely broker/server time
- candidate robustness under timestamp shifts:
  0, -1, -2, -3, -4 hours
```

## Possible decisions

```text
TIME_BASIS_OK_FOR_FORWARD_DESIGN
TIME_OFFSET_AWARE_FORWARD_DESIGN_REQUIRED
BROKER_TIME_REQUIRED_NOT_UTC_FORWARD_READY
TIME_BASIS_REJECT_OR_RECHECK_CANDIDATE
TIME_BASIS_AUDIT_FAILED_NO_BASE
```

## Hard rule

Research audit only:

```text
No EA change
No automatic trading
No paper/live authorization
No direct conversion to order
```
