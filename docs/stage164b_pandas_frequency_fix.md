# Stage164B Pandas Frequency Compatibility Hotfix

این hotfix فقط خطای compatibility در pandas/Python 3.14 را اصلاح می‌کند.
در Stage164 اولیه ruleهای resample به شکل `1H` و `4H` ساخته می‌شدند. در pandas جدید، `H` uppercase ممکن است invalid باشد و باید `h` lowercase استفاده شود.

تغییرات:

- `1H` به `1h` تبدیل شد.
- `4H` به `4h` تبدیل شد.
- fallback H1 هم `1h` شد.
- `1D` به `1d` تبدیل شد تا ruleها یک‌دست و آینده‌سازگار باشند.
- رفتار مرحله همچنان read-only است.
- هیچ KV اجرایی تولید نمی‌شود.
- هیچ order آزاد نمی‌شود.

اجرای پیشنهادی همان command Stage164 است.
