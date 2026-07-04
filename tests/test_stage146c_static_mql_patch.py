from pathlib import Path

EA = Path(__file__).resolve().parents[1] / 'mql5/Experts/Advisors/XAUUSD/XAUUSD_Stage134_DemoExecutorPilot_EA.mq5'
TXT = EA.read_text(encoding='utf-8')

def test_wildcard_allowed_rules_present():
    assert 'input string InpAllowedRules = "*";' in TXT
    assert 'allowed_raw == "*"' in TXT
    assert 'allowed_lc == "any"' in TXT
    assert 'allowed_lc == "all"' in TXT

def test_demo_only_guards_still_present():
    assert 'InpRequireDemoAccount' in TXT
    assert 'ACCOUNT_TRADE_MODE_DEMO' in TXT
    assert 'allow_real_account|false' in TXT
    assert 'BLOCKED_NOT_DEMO_ACCOUNT' in TXT

def test_duplicate_and_position_guards_still_present():
    assert 'HOLD_SIGNAL_ALREADY_EXECUTED' in TXT
    assert 'InpMaxOpenPositions' in TXT
    assert 'BLOCKED_MAX_OPEN_POSITIONS' in TXT
    assert 'InpMaxSpreadPoints' in TXT
    assert 'BLOCKED_SPREAD' in TXT

def test_signal_age_and_retry_defaults_relaxed():
    assert 'input int InpMaxSignalAgeSec = 7200;' in TXT
    assert 'input int InpMinSecondsBetweenOrderAttempts = 60;' in TXT
