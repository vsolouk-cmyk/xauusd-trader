# Stage178 Package Manifest

Files:

- `app/stage178_commercial_edge_decision_sprint.py`
- `configs/stage178_commercial_edge_decision_sprint.json`
- `tests/test_stage178_commercial_edge_decision_sprint.py`
- `requirements/stage178.txt`
- `docs/STAGE178_COMMERCIAL_EDGE_DECISION_SPRINT.md`

Design guarantees:

- no order path;
- no hyperparameter scan;
- no holdout use in candidate selection;
- fixed costs and gates;
- reference walk-forward plus untouched AMarkets holdout;
- fail-closed on missing/invalid databases.

QA before delivery:

- Python compile: PASS
- Unit and synthetic end-to-end tests: 9/9 PASS
- neutral-outcome evaluation anti-leakage regression: PASS
- next-open entry contract: PASS
- feature-prefix causality: PASS
- non-overlapping episode selection: PASS
- canonical SQLite schema introspection: PASS
- triple-barrier resolver smoke test: PASS
- simple trend baseline comparison gate: enabled
