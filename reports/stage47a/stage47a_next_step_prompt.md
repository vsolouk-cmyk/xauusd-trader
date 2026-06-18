چپ‌چین ادامه بده.

این ادامه پروژه XAUUSD/gold بعد از Stage47A است. Stage46 external-context branch بسته و archived است. Stage47A فقط یک thesis جدید را برای طراحی scan مجاز دانست:

selected_thesis = STRUCT47_A_LIQUIDITY_SWEEP_REVERSAL
next_allowed_step = STAGE47B_LIQUIDITY_SWEEP_REVERSAL_SCAN_DESIGN
promotion/EA/paper_live/live = NO_GO

لطفاً Stage47B را فقط به‌صورت predefined scan design/implementation برای liquidity-sweep reversal آماده کن. هیچ rescue از Stage41/42/43، هیچ ادامه Stage46، هیچ post-hoc bad bucket filtering، هیچ ML و هیچ paper/live مجاز نیست.

Stage47B باید با candle/session data قابل اجرا باشد، cost-aware باشد، و خروجی summary/report/register بدهد. اگر schema واقعی repo مشخص نیست، loader را با introspection و smoke test محافظه‌کارانه بساز.
