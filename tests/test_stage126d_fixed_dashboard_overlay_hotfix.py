from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_indicators_use_bottom_left_and_chart_change():
    for rel in [
        "mql5/Indicators/XAUUSD_Stage124F_Rule8OverlayIndicator.mq5",
        "mql5/Indicators/XAUUSD_Stage126_Rule9FrontierOverlayIndicator.mq5",
    ]:
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "CORNER_LEFT_LOWER" in text
        assert "CHARTEVENT_CHART_CHANGE" in text
        assert "OBJPROP_FONTSIZE" in text
        assert "OBJPROP_ANCHOR" in text
        assert "NO ORDER" in text
        assert "OrderSend" not in text
        assert "CTrade" not in text

def test_stage126d_script_copies_both_indicators():
    text = (ROOT / "app/stage126d_fixed_dashboard_overlay_hotfix.py").read_text(encoding="utf-8")
    assert "XAUUSD_Stage124F_Rule8OverlayIndicator.mq5" in text
    assert "XAUUSD_Stage126_Rule9FrontierOverlayIndicator.mq5" in text
    assert "NO_EA_CHANGE" in text
