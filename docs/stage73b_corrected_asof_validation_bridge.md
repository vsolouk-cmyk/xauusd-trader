# Stage73B Corrected As-Of Validation Bridge

Stage73B fixes two design problems in Stage73:

1. At an as-of date, calibration must use only outcomes that were already mature and known by that date. Entries before the as-of date but with exits after the as-of date are not known at the as-of date and are excluded from calibration.
2. Expected entry counts must be exposure-normalized. The raw number of entries before 2024 cannot be directly compared with a shorter 2024-2026 window.

It also changes interpretation of expectation error:

- Negative surprise can fail validation.
- Positive surprise is recorded as drift or upside regime shift, not a hard failure.
- Missing feature rows are counted only across the required trigger, date, and price columns for K06.

This stage does not authorize broker, EA, paper-live, live, or paper orders.
