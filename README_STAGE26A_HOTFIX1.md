# Stage26A Hotfix 1 — DB Loader Alignment

Fixes Stage26A DB-first loader by reusing the already validated Stage25C SQLite schema introspection path.

- DB-first remains enabled.
- CSV fallback remains disabled.
- Stage18A, Stage23D, and Stage25D are unchanged.
- Syntax checked with `python3 -m py_compile` before packaging.
