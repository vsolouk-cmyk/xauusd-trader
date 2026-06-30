# Stage131B SameFile install hotfix

Fixes a macOS case-insensitive filesystem issue in Stage131 indicator installation.

Problem:
- In tests or certain local layouts, `mql5/Indicators` and `MQL5/Indicators` can resolve to the same path.
- `shutil.copy2(src, dst)` raises `SameFileError` when source and destination are the same file.

Fix:
- Resolve source and destination before copy.
- If they are the same path, skip copy and record the destination as installed.
- Also catches `shutil.SameFileError` defensively.

No order, EA logic, broker, paper-live, or live path is changed.
