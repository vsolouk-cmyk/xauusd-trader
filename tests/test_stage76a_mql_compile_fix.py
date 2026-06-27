from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EA = ROOT / "mt5" / "K06_ObserverOnly_EA.mq5"


def test_mql_stringtolower_reference_fix_present():
    text = EA.read_text()
    assert "string v = value;" in text
    assert "StringToLower(v);" in text
    assert "string v = StringToLower(value);" not in text


def test_observer_only_no_order_calls():
    text = EA.read_text().lower()
    banned = ["ordersend", "ctrade", ".buy(", ".sell(", "positionopen"]
    for token in banned:
        assert token not in text, token


if __name__ == "__main__":
    test_mql_stringtolower_reference_fix_present()
    test_observer_only_no_order_calls()
    print("Stage76A MQL compile-fix static tests passed")
