# Stage26A Hotfix 1 — DB Loader Alignment

This hotfix corrects the Stage26A DB candle loader. The previous Stage26A implementation duplicated SQLite schema discovery and failed to identify the `bars` source already used successfully by Stage23D and Stage25D.

The hotfix reuses `load_bars_from_db` from Stage25C, which has already been validated in the project. No CSV fallback is introduced.
