from pathlib import Path


def test_stage108d_ea_has_chart_comment_and_no_trading():
    root = Path(__file__).resolve().parents[1]
    ea = root / "mt5" / "Unified_ObserverOnly_EA.mq5"
    text = ea.read_text(encoding="utf-8")
    assert '#property version   "1.09"' in text
    assert "void UpdateChartComment" in text
    assert "Comment(text);" in text
    assert 'Comment("");' in text
    assert "S105_03" in text
    forbidden = ["OrderSend", "CTrade", ".Buy(", ".Sell(", "trade.Buy", "trade.Sell"]
    for token in forbidden:
        assert token not in text


if __name__ == "__main__":
    test_stage108d_ea_has_chart_comment_and_no_trading()
    print("Stage108D tests passed")
