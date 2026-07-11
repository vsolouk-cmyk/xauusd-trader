import json, subprocess, sys
from pathlib import Path

def test_materializer_copies_missing_stage64j5(tmp_path):
    src=tmp_path/'archive/repo_cleanup_20260626/reports_inactive/stage64j5_event_calendar_forward_governance_acceptance'
    src.mkdir(parents=True)
    (src/'stage64j5_event_calendar_forward_governance_acceptance_summary.json').write_text('{}')
    script=Path(__file__).parents[1]/'app'/'stage171g_stage64_archive_compat_materializer.py'
    cp=subprocess.run([sys.executable,str(script),'--root',str(tmp_path)],text=True,capture_output=True)
    assert cp.returncode==0, cp.stderr
    dst=tmp_path/'reports/stage64j5_event_calendar_forward_governance_acceptance/stage64j5_event_calendar_forward_governance_acceptance_summary.json'
    assert dst.exists()
    summary=json.loads((tmp_path/'reports/stage171g_stage64_archive_compat_materializer/stage171g_stage64_archive_compat_summary.json').read_text())
    assert summary['required_stage64j5_exists'] is True

def test_orchestrator_contains_no_duplicate_gate():
    script=Path(__file__).parents[1]/'app'/'stage171f_h64l_4h_macro_gdelt_orchestrator.py'
    text=script.read_text()
    assert 'NO_NEW_FEATURE_SNAPSHOT_NO_DUPLICATE' in text
    assert 'inspect_shadow_ledger' in text
