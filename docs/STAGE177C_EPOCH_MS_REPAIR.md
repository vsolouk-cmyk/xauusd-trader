# Stage177C Epoch-Millisecond Repair

This repair fixes the synthetic DST-contract test on pandas builds whose
DatetimeIndex uses seconds, milliseconds, or microseconds rather than
nanoseconds internally.

The previous fixture used:

```python
timestamps.astype("int64") // 1_000_000
```

That assumes nanosecond storage. The repaired code explicitly converts to
`datetime64[ms]`, so the result is always Unix epoch milliseconds.

No DST model, threshold, train/holdout boundary, or trading permission changes.
