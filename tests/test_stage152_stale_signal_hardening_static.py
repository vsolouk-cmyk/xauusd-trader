from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
EA=ROOT/'mql5/Experts/Advisors/XAUUSD/XAUUSD_Stage134_DemoExecutorPilot_EA.mq5'
S151=ROOT/'app/stage151_locked_mtf_rule_state_writer.py'

def test_stage134_uses_feature_date_not_file_modified_time():
    text=EA.read_text(encoding='utf-8')
    assert 'ParseIsoUtc(feature_date' in text
    assert 'TimeGMT() - feature_dt_utc' in text
    assert 'signal_fresh_basis|feature_date_utc_not_file_modified_time' in text
    assert 'FileModifiedTime(InpRuleStateKvFile)' not in text.split('void EvaluateSignal()',1)[1]

def test_stage134_stale_blocks_before_active_rule():
    text=EA.read_text(encoding='utf-8')
    assert text.find('if(!signal_fresh)') < text.find('if(!IsTrueText(any_signal_active)')

def test_stage151_stale_guard_present():
    text=S151.read_text(encoding='utf-8')
    assert 'max_feature_age_sec' in text
    assert 'feature_fresh' in text
    assert 'raw_rule_active_before_stale_guard' in text
    assert 'STAGE151B_LOCKED_RULE_STALE_NO_ORDER' in text
