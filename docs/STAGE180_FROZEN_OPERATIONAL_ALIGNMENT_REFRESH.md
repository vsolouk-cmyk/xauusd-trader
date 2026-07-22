# Stage180 frozen operational alignment refresh

The full Stage177C contract-discovery audit is no longer rerun whenever raw
AMarkets CSV files become newer. That audit was designed to establish the
time-zone contract, not to serve as a daily updater.

The routine updater now:

1. reads the previously PASSed contract from SQLite provenance;
2. parses the current AMarkets M5 and H1 files;
3. applies the frozen EU DST contract;
4. excludes raw history earlier than the floor of the existing PASS database;
5. checks parity against the existing overlap;
6. atomically rebuilds the operational alignment database;
7. lets Stage180 process newly completed bars.

This prevents the newly downloaded 2011-2014 segment from blocking the live
shadow cycle. The older segment remains available for a separate bounded
historical research audit.

No Dukascopy refresh is required for this routine operational update.
