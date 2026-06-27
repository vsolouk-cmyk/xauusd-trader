from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EA = ROOT / "mt5" / "K06_ObserverOnly_EA.mq5"

BANNED_TOKENS = [
    "OrderSend",
    "CTrade",
    "Buy(",
    "Sell(",
    "PositionOpen",
]

REQUIRED_TOKENS = [
    "OnInit",
    "OnTimer",
    "FileOpen",
    "Comment",
    "InpAllowTrading",
]


def main() -> None:
    text = EA.read_text(encoding="utf-8")
    for token in BANNED_TOKENS:
        assert token not in text, f"banned token present in EA source: {token}"
    for token in REQUIRED_TOKENS:
        assert token in text, f"required observer token missing: {token}"
    assert "StringToLower(v);" in text
    assert "return INIT_FAILED;" in text
    print("Stage76C clean observer EA tests passed")


if __name__ == "__main__":
    main()
