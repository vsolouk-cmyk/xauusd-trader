# Stage48C next step prompt

چپ‌چین ادامه بده.

Stage48C broker spread row-level audit را اجرا کردم. لطفاً خروجی‌های زیر را بررسی کن:

- reports/stage48c/stage48c_broker_spread_row_level_audit_summary.json
- reports/stage48c/stage48c_broker_spread_row_level_audit_report.md
- reports/stage48c/stage48c_broker_spread_row_level_audit_inventory.csv

قواعد:
- این مرحله trading scan نیست.
- اگر broker_spread_row_level_ready=false بود، thesis جدید ممنوع است و باید collector/export broker-real طراحی شود.
- اگر broker_spread_row_level_ready=true بود، فقط Stage48D decision memo مجاز است، نه scan فوری.
