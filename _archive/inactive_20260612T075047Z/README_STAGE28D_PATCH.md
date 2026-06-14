# Stage28D Forward-Safe Meta-Gate Tracker Patch

Adds:

- `app/stage28d_forward_safe_meta_gate_tracker.py`
- `docs/STAGE28D_FORWARD_SAFE_META_GATE_TRACKER.md`
- updated `tools/archive_inactive_xauusd_artifacts.py` keep-list so Stage28B/28C/28D are not archived.

Install:

```bash
cd ~/Desktop/xauusd-trader
unzip -o ~/Downloads/xauusd_stage28d_forward_safe_meta_gate_tracker_patch.zip -d .
```

Run:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage28d_forward_safe_meta_gate_tracker
cat data/reports/stage28d_forward_safe_meta_gate_tracker/stage28d_forward_safe_meta_gate_tracker.md
```

Optional gate override:

```bash
STAGE28D_LONDON_RANGE_Q=0.60 STAGE28D_PRIOR_DAY_RANGE_Q=0.25 python3 -m app.stage28d_forward_safe_meta_gate_tracker
```
