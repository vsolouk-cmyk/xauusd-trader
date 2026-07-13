import importlib.util
import json
from pathlib import Path

import pandas as pd

MODULE_PATH = Path(__file__).parents[1] / "app" / "stage171h4_exact_dxy_downloader.py"
spec = importlib.util.spec_from_file_location("h4", MODULE_PATH)
h4 = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(h4)


def test_parse_yahoo_chart():
    payload = {
        "chart": {
            "result": [{
                "timestamp": [1704067200 + 86400 * i for i in range(30)],
                "indicators": {"quote": [{"close": [100 + i * 0.1 for i in range(30)]}]},
            }],
            "error": None,
        }
    }
    df = h4.parse_yahoo(json.dumps(payload).encode())
    assert len(df) == 30
    assert df.iloc[-1]["source_contract"] == "ICE_US_DOLLAR_INDEX_DELAYED_SERIES"


def test_quality_overlap_accepts_matching_exact_series():
    dates = pd.date_range("2026-01-01", periods=30, freq="D").strftime("%Y-%m-%d")
    old = pd.DataFrame({"date_utc": dates, "value": [100 + i * 0.1 for i in range(30)]})
    new = pd.DataFrame({"date_utc": dates, "value": [100.01 + i * 0.1 for i in range(30)]})
    q = h4.quality_checks(new, old, 0.03)
    assert q["pass"] is True
    assert q["overlap_rows"] == 30


def test_quality_rejects_wrong_scale():
    dates = pd.date_range("2026-01-01", periods=30, freq="D").strftime("%Y-%m-%d")
    old = pd.DataFrame({"date_utc": dates, "value": [100 + i * 0.1 for i in range(30)]})
    new = pd.DataFrame({"date_utc": dates, "value": [120 + i * 0.1 for i in range(30)]})
    q = h4.quality_checks(new, old, 0.03)
    assert q["pass"] is False
    assert q["overlap_ok"] is False


def test_fred_formula_reference_point():
    value = (
        h4.DXY_CONSTANT
        * (1.10 ** -0.576)
        * (150.0 ** 0.136)
        * (1.28 ** -0.119)
        * (1.36 ** 0.091)
        * (10.5 ** 0.042)
        * (0.90 ** 0.036)
    )
    assert 90 < value < 120


def test_orchestrator_config_orders_dxy_before_materializer():
    cfg = json.loads((Path(__file__).parents[1] / "configs" / "stage171f_h64l_4h_macro_gdelt_orchestrator.json").read_text())
    names = [x["name"] for x in cfg["local_pipeline"]]
    assert names.index("stage171h4_exact_dxy_downloader") < names.index("stage171h_forward_feature_materializer")
    assert next(x for x in cfg["local_pipeline"] if x["name"] == "stage171h4_exact_dxy_downloader")["required"] is True
