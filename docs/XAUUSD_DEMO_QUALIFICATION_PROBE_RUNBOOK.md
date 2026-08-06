# XAUUSD Demo Qualification Probe V1.1

## Purpose

This repair preserves the V1 demo-only qualification path and corrects the operator state machine around `emit`, `inspect`, and `collect`.

The probe remains labelled `QUALIFICATION_PROBE_NOT_ALPHA` and uses the existing path:

`candidate file -> MT5 EA runtime guards -> broker request -> fill -> position -> timed EA close -> receipt/journal -> duplicate guard`

Python never calls a broker API and never sends or closes an order.

## V1.1 repairs

1. The emit intent is persisted as `PREPARED_NO_ORDER` before the MT5 permit/candidate activation edge.
2. After the candidate activation edge succeeds, the same summary is updated to `state=EMITTED`.
3. If the summary is missing, `inspect` attempts recovery from the outbox candidate, MT5 candidate, or MT5 probe permit.
4. If no intent exists, `inspect` returns `QUALIFICATION_PROBE_NOT_EMITTED_NO_ORDER` instead of a raw missing-file exception.
5. `collect` returns `QUALIFICATION_PROBE_EVIDENCE_NOT_READY` and creates no final ZIP until the full lifecycle passes.
6. A missing summary can no longer hide an already-written candidate intent.

## Why the reported ZIP was not produced

The final evidence ZIP is intentionally produced only after a successful lifecycle inspection. A run outside the safe market window cannot emit the probe, so there is no `qualification_probe_emit_summary.json` and no lifecycle to collect.

Safe execution windows remain:

- Monday–Thursday: 06:00–18:00 UTC
- Friday: 06:00–15:00 UTC

## Hard safety boundaries

- Demo account only.
- Login must equal `7907958` through the existing login-bound configuration.
- Symbol must be `XAUUSD`.
- Existing magic number remains `1782401`.
- Existing arming permit remains mandatory.
- Separate intent-bound probe permit is mandatory and consumed after the order attempt.
- Maximum permitted probe volume equals the broker minimum lot read from the fresh heartbeat.
- Exit duration remains bounded to 60–300 seconds.
- Weekend, rollover, Friday-close, stale-heartbeat and official-event blackout windows fail closed.
- Live-account fallback is absent.

## Install

Extract the package into the repository root. This V1.1 repair changes only:

- `app/xauusd_mt5_demo_qualification_probe.py`
- `tests/test_xauusd_mt5_demo_qualification_probe.py`
- this runbook

The MQL5 EA is unchanged from V1 and does not need recompilation solely for this repair.

## Test

```bash
python3 -m compileall -q app tests
python3 -m unittest tests.test_xauusd_mt5_demo_qualification_probe -v
```

Expected qualification-probe test count: `10`.

## Current no-intent status check

```bash
python3 app/xauusd_mt5_demo_qualification_probe.py inspect --root .
python3 app/xauusd_mt5_demo_qualification_probe.py collect --root .
```

Before a successful emit, expected decisions are:

```text
QUALIFICATION_PROBE_NOT_EMITTED_NO_ORDER
QUALIFICATION_PROBE_EVIDENCE_NOT_READY
```

No final evidence ZIP should exist in this state.

## Run in the next safe market window

```bash
python3 app/xauusd_mt5_demo_qualification_probe.py preflight --root .
python3 app/xauusd_mt5_demo_qualification_probe.py emit --root . --side LONG --exit-seconds 120
sleep 180
python3 app/xauusd_mt5_demo_qualification_probe.py inspect --root .
python3 app/xauusd_mt5_demo_qualification_probe.py collect --root .
```

Expected final artifact:

```text
~/Downloads/XAUUSD_DEMO_QUALIFICATION_PROBE_EVIDENCE.zip
```

Do not run another `emit` while any candidate, probe permit, active-position state, lockdown, or recovered intent remains unresolved.


## V1.2 accounting repair

The EA captures the executable exit-side quote before closing, retries MT5 history synchronization for the terminal deal, records adverse exit slippage, and writes realized profit, commission, swap, and fee to the append-only probe journal. Existing completed V1.1 evidence remains valid for plumbing but is not retroactively upgraded. Do not repeat a qualification probe solely to populate these accounting fields.
