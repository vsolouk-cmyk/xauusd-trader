# Stage93 COT/Event Frontier Readiness Builder

Stage93 is a data-frontier preparation stage. It is used after:

- the unified macro observer is operational;
- residual macro-only discovery has no shortlist;
- intraday/session residual discovery has no shortlist.

Stage93 does not discover a strategy and does not change MT5, EA, CSV bridge, broker state, or any order authorization. It inventories COT and event-surprise files, creates normalized schema templates, and decides whether Stage94 can proceed to COT or event-surprise thesis discovery.

Required normalized COT fields include report date, public availability timestamp, market/contract, open interest, and managed-money positioning. Required event-surprise fields include event timestamp, availability timestamp, event type, actual, consensus, previous, and surprise.

All future discovery stages must use historical-as-of availability fields and must compute rolling z-scores using information available only up to the historical evaluation date.
