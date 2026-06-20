# Stage52 LoaderFix2 — Combined Import and True Forward Runner

This patch adds an orchestration helper only:

- First runs `app/stage49_amarkets_multitf_importer_fast.py`.
- Then runs `app/stage52_volatility_squeeze_forward_shadow.py`.
- Keeps the broker data persistent in `data/broker_normalized/amarkets_multitf.sqlite`.
- Keeps Stage52 state persistent in `data/shadow/stage52_forward_shadow.sqlite`.

It does not alter promotion rules and does not authorize EA, paper-live, or live trading.

Use `--reset-forward-state` only once when intentionally reinitializing the true-forward watermark. For routine updates, never pass reset.
