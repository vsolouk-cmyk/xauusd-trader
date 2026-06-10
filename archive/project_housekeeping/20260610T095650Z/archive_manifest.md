# Project Housekeeping Archive Manifest

- generated_utc: `2026-06-10T09:56:50+00:00`
- apply: `True`
- archive_code: `True`
- archive_root: `archive/project_housekeeping/20260610T095650Z`

| Action | Classification/Category | Source | Destination |
|---|---|---|---|
| keep | keep_active | .github/workflows/xauusd_collectors.yml |  |
| keep | review_keep_unknown | .github/workflows/xauusd_data_store_refresh.yml |  |
| keep | review_keep_unknown | .github/workflows/xauusd_stage3d_forward_shadow.yml |  |
| keep | review_keep_unknown | data/reports/baseline_trades |  |
| keep | keep_active_collector_report | data/reports/stage10b_event_pipeline_update |  |
| keep | keep_active_collector_report | data/reports/stage9b_macro_numeric_update |  |
| keep | review_keep_unknown | data/reports/stage_data_file_audit |  |
| keep | review_keep_unknown | data/reports/stage_pipeline |  |
| keep | keep_required_pipeline_or_current_stage | app/stage10a_event_impact_lab.py |  |
| keep | keep_required_pipeline_or_current_stage | app/stage10b_event_pipeline_update.py |  |
| move | app_scripts | app/stage10b_gdelt_probe.py | archive/project_housekeeping/20260610T095650Z/app_scripts/app/stage10b_gdelt_probe.py |
| keep | keep_required_pipeline_or_current_stage | app/stage10c_numeric_shock_event_backfill.py |  |
| keep | keep_required_pipeline_or_current_stage | app/stage10d_event_impact_validation_lab.py |  |
| keep | keep_required_pipeline_or_current_stage | app/stage10e_event_aware_guard_simulation.py |  |
| keep | keep_required_pipeline_or_current_stage | app/stage11a_downtrend_short_thesis_lab.py |  |
| move | app_scripts | app/stage4g_amarkets_backfill_validation.py | archive/project_housekeeping/20260610T095650Z/app_scripts/app/stage4g_amarkets_backfill_validation.py |
| move | app_scripts | app/stage4h_session_guard_lab.py | archive/project_housekeeping/20260610T095650Z/app_scripts/app/stage4h_session_guard_lab.py |
| move | app_scripts | app/stage4i_guard_robustness.py | archive/project_housekeeping/20260610T095650Z/app_scripts/app/stage4i_guard_robustness.py |
| move | app_scripts | app/stage4j_shock_regime_lab.py | archive/project_housekeeping/20260610T095650Z/app_scripts/app/stage4j_shock_regime_lab.py |
| move | app_scripts | app/stage5a_ea_safety_audit.py | archive/project_housekeeping/20260610T095650Z/app_scripts/app/stage5a_ea_safety_audit.py |
| move | app_scripts | app/stage5a_patch_ea_csv_format.py | archive/project_housekeeping/20260610T095650Z/app_scripts/app/stage5a_patch_ea_csv_format.py |
| move | app_scripts | app/stage5b_dryrun_log_validator.py | archive/project_housekeeping/20260610T095650Z/app_scripts/app/stage5b_dryrun_log_validator.py |
| move | app_scripts | app/stage5c_live_outcome_tracker.py | archive/project_housekeeping/20260610T095650Z/app_scripts/app/stage5c_live_outcome_tracker.py |
| move | app_scripts | app/stage6a_local_data_store.py | archive/project_housekeeping/20260610T095650Z/app_scripts/app/stage6a_local_data_store.py |
| move | app_scripts | app/stage6b_persist_runner.py | archive/project_housekeeping/20260610T095650Z/app_scripts/app/stage6b_persist_runner.py |
| move | app_scripts | app/stage6c_db_evidence_report.py | archive/project_housekeeping/20260610T095650Z/app_scripts/app/stage6c_db_evidence_report.py |
| move | app_scripts | app/stage7a_strategy_thesis_lab.py | archive/project_housekeeping/20260610T095650Z/app_scripts/app/stage7a_strategy_thesis_lab.py |
| move | app_scripts | app/stage7b_strategy_redesign_lab.py | archive/project_housekeeping/20260610T095650Z/app_scripts/app/stage7b_strategy_redesign_lab.py |
| move | app_scripts | app/stage7c_edge_diagnostics_lab.py | archive/project_housekeeping/20260610T095650Z/app_scripts/app/stage7c_edge_diagnostics_lab.py |
| move | app_scripts | app/stage7d_exit_geometry_lab.py | archive/project_housekeeping/20260610T095650Z/app_scripts/app/stage7d_exit_geometry_lab.py |
| move | app_scripts | app/stage8a_regime_discovery_lab.py | archive/project_housekeeping/20260610T095650Z/app_scripts/app/stage8a_regime_discovery_lab.py |
| move | app_scripts | app/stage8b_single_regime_thesis_lab.py | archive/project_housekeeping/20260610T095650Z/app_scripts/app/stage8b_single_regime_thesis_lab.py |
| move | app_scripts | app/stage8c_robustness_validation.py | archive/project_housekeeping/20260610T095650Z/app_scripts/app/stage8c_robustness_validation.py |
| move | app_scripts | app/stage8d_forward_shadow_outcome_tracker.py | archive/project_housekeeping/20260610T095650Z/app_scripts/app/stage8d_forward_shadow_outcome_tracker.py |
| move | app_scripts | app/stage9a_macro_feature_store.py | archive/project_housekeeping/20260610T095650Z/app_scripts/app/stage9a_macro_feature_store.py |
| keep | keep_required_pipeline_or_current_stage | app/stage9b_macro_event_calendar_update.py |  |
| move | app_scripts | app/stage9b_macro_numeric_import_artifact.py | archive/project_housekeeping/20260610T095650Z/app_scripts/app/stage9b_macro_numeric_import_artifact.py |
| keep | keep_required_pipeline_or_current_stage | app/stage9b_macro_numeric_update.py |  |
| move | app_scripts | app/stage9c_macro_regime_interaction_lab.py | archive/project_housekeeping/20260610T095650Z/app_scripts/app/stage9c_macro_regime_interaction_lab.py |
| move | app_scripts | app/stage9d_macro_aware_forward_shadow_report.py | archive/project_housekeeping/20260610T095650Z/app_scripts/app/stage9d_macro_aware_forward_shadow_report.py |
| move | app_scripts | app/stage_data_file_audit.py | archive/project_housekeeping/20260610T095650Z/app_scripts/app/stage_data_file_audit.py |
| move | app_scripts | app/stage_pipeline_runner.py | archive/project_housekeeping/20260610T095650Z/app_scripts/app/stage_pipeline_runner.py |
