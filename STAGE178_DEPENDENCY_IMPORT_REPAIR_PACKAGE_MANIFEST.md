# Stage178 Dependency Import Repair Package Manifest

## Purpose

Repair the Stage178 test-loader failure when `joblib` is not installed in the
active Python environment.

## Root cause

The original Stage178 module imported `joblib` and all scikit-learn classes at
module-import time. `unittest` therefore could not even load tests when the ML
dependency stack was incomplete.

## Changes

- Removes direct `joblib` use for model persistence and writes the selected
  model with Python `pickle` as `stage178_selected_model.pkl`.
- Loads scikit-learn lazily only when model construction or explicit dependency
  preflight is requested.
- Adds `--check-dependencies` with a concise, traceback-free failure message.
- Keeps non-ML unit tests importable when joblib/scikit-learn is incomplete.
- Skips only the ML end-to-end smoke test in a deliberately simulated missing-
  joblib environment.
- Adds regression tests for module import and dependency preflight without
  joblib.

## QA executed on the exact package contents

- Python compile: PASS
- Full unit suite with complete dependencies: 11/11 PASS
- End-to-end synthetic CLI/report smoke: PASS
- Explicit dependency preflight: PASS
- Simulated missing-joblib unit suite: PASS, 10 passed + 1 intentional skip
- Simulated missing-joblib module import: PASS
- Simulated missing-joblib CLI preflight: exit 3, concise message, no traceback
- Clean ZIP extraction and rerun: PASS

## Operational boundary

No paper, demo, or live execution is authorized by this repair.
