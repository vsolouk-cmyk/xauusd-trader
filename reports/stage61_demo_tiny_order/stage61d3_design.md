# Stage61D3 EA-Compatible Tiny Demo Signal

This hotfix aligns the tiny demo signal CSV with the compiled `Stage61_DemoExecutionHarness.mq5` parser.

The prior Stage61D2 CSV used the exporter schema where `direction` appeared before `symbol`. The compiled EA expects a 16-column execution schema where `symbol` is column 7, `side` is column 8, and `lot` is column 9. As a result, the EA read `0.01` as `side` and printed `unsupported side`.

Stage61D3 writes the exact 16-column schema consumed by the EA. Python still does not connect to the broker and does not submit orders.
