# Stage28A Hotfix 1 — Active Suite Dependency + Family-Interleaved Factory

Research/shadow only. No EA, no paper/live, no orders.

This hotfix restores the Stage23B compatibility module required by Stage23D/25D/27D imports and updates Stage28A so timeout-limited runs interleave families instead of testing registry families in blocks.

Files:
- app/stage23b_continuation_no_trade_discovery.py
- app/stage28a_discovery_factory_batch_runner.py
- tools/archive_inactive_xauusd_artifacts.py

Run:
```bash
cd ~/Desktop/xauusd-trader
unzip -o ~/Downloads/xauusd_stage28a_hotfix1_active_suite_dependency_family_interleave_patch.zip -d .
python3 -m app.run_active_shadow_suite
python3 -m app.stage28a_discovery_factory_batch_runner
```
