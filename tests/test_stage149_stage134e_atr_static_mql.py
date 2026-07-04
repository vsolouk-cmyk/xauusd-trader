from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EA = ROOT / "mql5/Experts/Advisors/XAUUSD/XAUUSD_Stage134_DemoExecutorPilot_EA.mq5"
TEXT = EA.read_text(encoding="utf-8")

def test_atr_inputs_present():
    assert "input bool InpUseAtrStops = true;" in TEXT
    assert "input ENUM_TIMEFRAMES InpAtrTimeframe = PERIOD_H1;" in TEXT
    assert "input double InpAtrStopLossMult = 1.5;" in TEXT
    assert "input double InpAtrTakeProfitMult = 2.0;" in TEXT

def test_atr_calculation_uses_closed_bars():
    assert "CopyRates(_Symbol, InpAtrTimeframe, 1, period + 1, rates)" in TEXT
    assert "rates[i+1].close" in TEXT

def test_fixed_fallback_still_available():
    assert "atr_unavailable_fallback_fixed" in TEXT
    assert "InpStopLossPoints" in TEXT
    assert "InpTakeProfitPoints" in TEXT

def test_retcode_10018_retry_hardening_preserved():
    assert 'return(r == "10018");' in TEXT
    assert "DEMO_BUY_REJECTED_RETRYABLE_MARKET_CLOSED" in TEXT
