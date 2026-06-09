# Git ignore note for Stage 6A

Make sure local SQLite databases stay out of Git:

```gitignore
data/local/*.sqlite
data/local/*.sqlite-*
```

CSV exports from MT5/AMarkets should also remain local unless a small anonymized sample is intentionally committed.
