from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EA = ROOT / "mql5/Experts/Advisors/XAUUSD/XAUUSD_Stage134_DemoExecutorPilot_EA.mq5"
TEXT = EA.read_text(encoding="utf-8")


def test_max_hold_default_is_h1_compatible_240_minutes():
    assert "input int InpMaxHoldMinutes = 240;" in TEXT


def test_market_closed_retcode_is_retryable():
    assert 'return(r == "10018");' in TEXT
    assert "DEMO_BUY_REJECTED_RETRYABLE_MARKET_CLOSED" in TEXT


def test_success_duplicate_is_based_on_accepted_retcode():
    assert "bool IsAcceptedRetcode" in TEXT
    assert 'g_last_success_signal_key=signal_key;' in TEXT
    assert "ok && accepted_retcode" in TEXT


def test_status_exports_retryable_flag():
    assert "last_retcode_retryable|" in TEXT
