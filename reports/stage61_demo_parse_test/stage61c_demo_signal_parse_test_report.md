# Stage61C Demo Signal Parse Test

- status: `DEMO_SIGNAL_PARSE_TEST_FILE_READY_NO_PROMOTION`
- decision: `COPY_PARSE_TEST_SIGNAL_TO_MT5_FILES_KEEP_ALLOWTRADING_FALSE_NO_PROMOTION`
- next_allowed_step: `ATTACH_EA_WITH_ALLOWTRADING_FALSE_AND_VERIFY_PARSE_NO_ORDER`
- promotion: `NO_GO`
- EA: `DEMO_HARNESS_PARSE_TEST_ONLY`
- paper_live: `NO_GO`
- live: `NO_GO`

## Generated file
- mt5_signal_csv: `/Users/vahid/Desktop/xauusd-trader/reports/stage61_demo_parse_test/mt5_files/stage61_demo_signals.csv`
- generated_rows: `1`
- allow_trading_required: `False`
- orders_created_by_python: `0`

## MT5 test instruction
Copy the generated CSV to the terminal `MQL5/Files` folder as `stage61_demo_signals.csv`, attach the compiled Stage61 EA to a demo XAUUSD chart, keep `AllowTrading=false`, and confirm that the EA parses the signal but sends no order.

## Interpretation
Stage61C is a parse-only demo harness test. It does not authorize paper-live, live trading, or order submission.
