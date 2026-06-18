# Stage47B LoaderFix3 — Exact Timeframe Source Selection

This hotfix fixes two operational issues found during local execution:

1. The previous ZIP accidentally included `app/__pycache__`, which caused `mv ... app/* app/` to fail when `app/__pycache__` already existed.
2. CSV auto-discovery could select a `15min` file while `--timeframe M5` was requested, because the broad token `5m` matched the substring inside `15min`.

LoaderFix3 removes `__pycache__` from the package and uses exact timeframe filename matching. For `--timeframe M5`, valid filename matches include `5min` and `M5`; `15min` cannot win selection.

Status remains:

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```
