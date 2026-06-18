چپ‌چین ادامه بده.

این ادامه پروژه XAUUSD/gold بعد از Stage47B implementation package است.

وضعیت:

```text
stage = Stage47B_LIQUIDITY_SWEEP_REVERSAL_SCAN_DESIGN
selected_thesis = STRUCT47_A_LIQUIDITY_SWEEP_REVERSAL
promotion/EA/paper_live/live = NO_GO
```

فایل اجرایی اضافه شده:

```text
app/stage47b_liquidity_sweep_reversal_scan.py
```

اول اسکریپت را روی دیتای واقعی repo اجرا کن. اگر schema واقعی متفاوت بود، loader را فقط با schema introspection اصلاح کن؛ ruleها، grid، windowها، و kill-switchها را بعد از دیدن نتیجه تغییر نده.

خروجی‌های مورد انتظار:

```text
reports/stage47b/stage47b_liquidity_sweep_reversal_summary.json
reports/stage47b/stage47b_liquidity_sweep_reversal_candidates.csv
reports/stage47b/stage47b_liquidity_sweep_reversal_trades.csv
reports/stage47b/stage47b_liquidity_sweep_reversal_report.md
```

اگر strict و soft هر دو صفر بودند، نتیجه را archive/kill کن و rescue یا post-hoc filtering انجام نده. اگر survivor وجود داشت، فقط Stage47C سخت‌گیرانه برای audit همان survivorها مجاز است.
