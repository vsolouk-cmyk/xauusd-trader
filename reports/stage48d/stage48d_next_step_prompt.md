چپ‌چین ادامه بده.

Stage48C نشان داد broker schema candidate داریم ولی row-level spread coverage کافی نیست. Stage48D validator را مبنا قرار بده.

کار بعدی:
1. اگر فایل MT5/broker export داریم، آن را با `app/stage48d_broker_spread_export_validator.py` validate کن.
2. اگر خروجی `BROKER_SPREAD_EXPORT_READY_NO_PROMOTION` بود، فقط Stage48E broker-realism decision memo مجاز است.
3. اگر خروجی insufficient بود، trading scan ممنوع است و باید export/collector را ادامه دهیم.

هیچ EA، paper-live، live یا trading thesis scan شروع نشود.
