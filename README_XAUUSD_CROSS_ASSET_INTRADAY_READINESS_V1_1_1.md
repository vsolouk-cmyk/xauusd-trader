# XAUUSD Cross-Asset Intraday Readiness V1.1.1

This is a test-portability repair for macOS filesystem aliases.

## Root cause

On macOS, `/var/...` is an alias of `/private/var/...`. The production selector intentionally resolves candidate inventory paths to their canonical filesystem path. Two unit tests compared the resolved selected path with the unresolved `TemporaryDirectory` path using lexical `Path` equality, so they failed even though both paths identified the same file.

## Repair

- Inventory paths returned by the test fixture are canonicalized with `Path.resolve()`.
- A regression test verifies both canonical equality and `os.path.samefile()` identity.
- Runtime Python logic, candidate classification, MT5 MQL, atomic snapshot publication, readiness decisions, and no-order contract are unchanged.

No MetaEditor recompile is required for this repair if V1.1 MQL already compiled successfully.
