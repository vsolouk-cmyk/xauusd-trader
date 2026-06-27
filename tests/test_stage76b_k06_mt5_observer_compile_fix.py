from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
EA = ROOT / "mt5" / "K06_ObserverOnly_EA.mq5"

def main():
    text = EA.read_text(encoding="utf-8")
    banned = ["OrderSend", "CTrade", ".Buy(", ".Sell(", "PositionOpen", "trade.Buy", "trade.Sell"]
    for token in banned:
        assert token not in text, f"banned trading token present: {token}"
    assert "InpAllowTrading" in text
    assert "return INIT_FAILED" in text
    assert "string v = value;" in text
    assert "StringToLower(v);" in text
    assert "StringToLower(value)" not in text
    assert "OBSERVER_ONLY_NO_TRADE" in text
    print("Stage76B compile-fix static tests passed")

if __name__ == "__main__":
    main()
