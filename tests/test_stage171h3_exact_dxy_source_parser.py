import importlib.util
from pathlib import Path
import pandas as pd

MOD_PATH = Path(__file__).parents[1] / "app" / "stage171h_h64l_forward_feature_materializer.py"
spec = importlib.util.spec_from_file_location("stage171h3", MOD_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_stooq_header_schema(tmp_path):
    p = tmp_path / "stooq_dx_f_dxy_daily.csv"
    dates = pd.date_range("2026-05-01", periods=30, freq="D")
    pd.DataFrame({"Date": dates.strftime("%Y-%m-%d"), "Open": 100, "High": 101, "Low": 99, "Close": range(100,130), "Volume": 1}).to_csv(p, index=False)
    s, reason = mod.load_series_file(p, "dxy")
    assert reason is None
    assert len(s) == 30
    assert s.attrs["source_contract"] == "DXY_OR_ICE_USDX_FUTURES_SERIES"


def test_stooq_headerless_yyyymmdd(tmp_path):
    p = tmp_path / "stooq_dx_f_dxy_daily.csv"
    rows=[]
    for i, d in enumerate(pd.date_range("2026-05-01", periods=30, freq="D")):
        rows.append([d.strftime("%Y%m%d"), 100+i, 101+i, 99+i, 100.5+i, 10])
    pd.DataFrame(rows).to_csv(p, index=False, header=False)
    s, reason = mod.load_series_file(p, "dxy")
    assert reason is None
    assert s.iloc[-1]["date"].date().isoformat() == "2026-05-30"


def test_rate_limit_body_is_diagnostic(tmp_path):
    p = tmp_path / "stooq_dx_f_dxy_daily.csv"
    p.write_text("Too Many Requests", encoding="utf-8")
    s, reason = mod.load_series_file(p, "dxy")
    assert s is None
    assert reason == "RATE_LIMIT_RESPONSE_NOT_CSV"


def test_broad_fred_proxy_is_not_exact_dxy(tmp_path):
    root = tmp_path / "repo"
    inbox = tmp_path / "inbox"
    (root / "data/fred").mkdir(parents=True)
    inbox.mkdir()
    dates = pd.date_range("2026-05-01", periods=30, freq="D")
    pd.DataFrame({"observation_date": dates, "DTWEXBGS": range(100,130)}).to_csv(root / "data/fred/DTWEXBGS.csv", index=False)
    exact = inbox / "stooq_dx_f_dxy_daily.csv"
    pd.DataFrame({"Date": dates, "Open": 100, "High": 101, "Low": 99, "Close": range(90,120), "Volume": 1}).to_csv(exact, index=False)
    s, meta = mod.choose_series(root, inbox, "dxy", pd.Timestamp("2026-05-30", tz="UTC"))
    assert "stooq_dx_f" in meta["path"]
    assert meta["source_contract"] == "DXY_OR_ICE_USDX_FUTURES_SERIES"
    broad = [x for x in meta["candidate_diagnostics"] if "DTWEXBGS" in x["path"]][0]
    assert broad["reason"] == "BROAD_DOLLAR_PROXY_NOT_EXACT_DXY"
