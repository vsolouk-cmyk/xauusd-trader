# XAUUSD Stage28A Discovery Factory Patch

## Added files

- `app/stage28a_discovery_factory_batch_runner.py`
- `app/run_active_shadow_suite.py`
- `tools/archive_inactive_xauusd_artifacts.py`
- `docs/STAGE28A_DISCOVERY_FACTORY.md`

## Run Stage28A discovery factory

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage28a_discovery_factory_batch_runner
cat data/reports/stage28a_discovery_factory_batch_runner/stage28a_discovery_factory_batch_runner.md
```

Optional faster/stricter run:

```bash
cd ~/Desktop/xauusd-trader
STAGE28A_MAX_RUNTIME_SECONDS=150 STAGE28A_MAX_EXACT=12 STAGE28A_MAX_EXACT_PER_FAMILY=2 python3 -m app.stage28a_discovery_factory_batch_runner
cat data/reports/stage28a_discovery_factory_batch_runner/stage28a_discovery_factory_batch_runner.md
```

## Run active shadow suite

This attempts CSV import/refresh first, then runs the four active research-shadow versions.

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.run_active_shadow_suite
cat data/reports/active_shadow_suite/active_shadow_suite.md
```

## Archive inactive artifacts safely

Dry-run first:

```bash
cd ~/Desktop/xauusd-trader
python3 tools/archive_inactive_xauusd_artifacts.py
```

Apply after review:

```bash
cd ~/Desktop/xauusd-trader
python3 tools/archive_inactive_xauusd_artifacts.py --apply
```

Include workflows only if dry-run looks correct:

```bash
cd ~/Desktop/xauusd-trader
python3 tools/archive_inactive_xauusd_artifacts.py --include-workflows
python3 tools/archive_inactive_xauusd_artifacts.py --include-workflows --apply
```

## Git commands

```bash
cd ~/Desktop/xauusd-trader
git add -A
git commit -m "Add Stage28A discovery factory and active suite runner"
git pull --rebase
git push
```
