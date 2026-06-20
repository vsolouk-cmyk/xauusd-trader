# Stage60 LoaderFix1 - UTC Timestamp Normalization

This hotfix updates `app/stage60_context_aware_family_scan.py` so event timestamps and broker M5 timestamps are both converted to integer UTC nanoseconds before `np.searchsorted`.

The fix addresses:

```text
TypeError: Cannot compare tz-naive and tz-aware timestamps
```

No trading permission is changed. This is a loader/evaluation hotfix only.
