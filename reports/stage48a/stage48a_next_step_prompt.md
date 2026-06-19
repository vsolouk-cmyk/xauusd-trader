چپ‌چین ادامه بده.

این ادامه پروژه XAUUSD/gold است. Stage47B liquidity-sweep reversal بعد از rerun روی 25,905 کندل و 2,658 trade با strict=0 و soft=0 archived/no-promotion شد.

Stage48A decision gate را مبنا بگیر:
- تصمیم: DO_NOT_START_ANOTHER_CANDLE_ONLY_RULE_SCAN
- promotion/EA/paper/live همه NO_GO
- گام مجاز بعدی: STAGE48B_EXECUTION_REALISM_AND_DATA_SOURCE_FEASIBILITY_PRECHECK
- هدف Stage48B: بررسی امکان جمع‌آوری MT5/broker bid-ask/spread یا داده event-calendar، نه اجرای scan معاملاتی.

لطفاً Stage48B را به‌صورت patch اجرایی data/precheck آماده کن: collector/precheck برای مسیرهای موجود، schema/report، smoke test، و خروجی‌های reports/stage48b. هیچ trading scan یا ML شروع نشود.
