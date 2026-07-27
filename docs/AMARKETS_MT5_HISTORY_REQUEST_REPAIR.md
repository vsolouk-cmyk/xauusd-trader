# AMarkets MT5 history request repair

This package provides a diagnostic exporter for broker bars. It is intended for the situation where MT5's **View → Symbols → Bars → Request** button waits and becomes enabled again without returning rows or an error.

The script records:

- current account login and server;
- `SERIES_SERVER_FIRSTDATE`;
- `SERIES_TERMINAL_FIRSTDATE`;
- synchronization state and terminal bar limit;
- every `CopyRates` attempt and MQL5 history error;
- bounded progress for every date chunk;
- a tab-separated AMarkets-compatible CSV when the server supplies the data.

It does not place, modify, or close orders.
