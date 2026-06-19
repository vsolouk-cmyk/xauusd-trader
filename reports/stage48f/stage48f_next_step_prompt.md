چپ‌چین ادامه بده.

Stage48F broker/reference alignment and cost-model calibration را اجرا کردم. خروجی‌های زیر را مبنا قرار بده:

```text
reports/stage48f/stage48f_broker_reference_alignment_cost_model_summary.json
reports/stage48f/stage48f_broker_reference_alignment_cost_model_report.md
reports/stage48f/stage48f_cost_model.json
reports/stage48f/stage48f_session_cost_profile.csv
```

اگر status برابر `COST_MODEL_READY_NO_PROMOTION` بود، مرحله بعدی باید طراحی یک broker-real cost-aware thesis یا rerun محدود با cost model جدید باشد. اگر insufficient بود، ابتدا alignment/time-offset/point-size/export را اصلاح کن. هیچ EA، paper-live یا live مجاز نیست.
