import csv
import datetime as dt
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_forward_materializer_end_to_end(tmp_path: Path):
    root = tmp_path / "repo"
    inbox = tmp_path / "inbox"
    app = root / "app"
    app.mkdir(parents=True)
    inbox.mkdir(parents=True)
    src = Path(__file__).parents[1] / "app" / "stage171h_h64l_forward_feature_materializer.py"
    target = app / src.name
    target.write_text(src.read_text())

    end = pd.Timestamp.now(tz="UTC").floor("D") - pd.Timedelta(days=1)
    days = pd.date_range(end=end, periods=80, freq="D", tz="UTC")
    rows = []
    for i, day in enumerate(days):
        for j in range(120):
            ts = day + pd.Timedelta(minutes=5*j)
            rows.append({"<DATE>": ts.strftime("%Y.%m.%d"), "<TIME>": ts.strftime("%H:%M:%S"), "<OPEN>": 2000+i, "<HIGH>": 2001+i, "<LOW>": 1999+i, "<CLOSE>": 2000+i+j/1000, "<TICKVOL>": 1, "<VOL>": 0, "<SPREAD>": 20})
    pd.DataFrame(rows).to_csv(inbox / "amarkets_xauusd_5m.csv", sep="\t", index=False)

    dxy = pd.DataFrame({"timestamp": days, "close": [110 - i*0.1 for i in range(len(days))]})
    ry = pd.DataFrame({"timestamp": days, "close": [2.5 - i*0.01 for i in range(len(days))]})
    ex = root / "data" / "exogenous"
    ex.mkdir(parents=True)
    dxy.to_csv(ex / "dxy.csv", index=False)
    ry.to_csv(ex / "real_yield.csv", index=False)

    norm = root / "data" / "fundamental_event_inbox" / "normalized"
    norm.mkdir(parents=True)
    month_dates = pd.date_range(end=end - pd.Timedelta(days=10), periods=7, freq="ME")
    wgc_rows = []
    for i, d in enumerate(month_dates):
        payload = {"ticker": str(d.date()), "All units in tonnes unless otherwise specified": 3000 + i*20}
        wgc_rows.append({"sheet": "Holdings by month", "raw_json": json.dumps(payload)})
    pd.DataFrame(wgc_rows).to_csv(norm / "wgc_gold_etf_xlsx_rows.csv", index=False)

    out = root / "data" / "forward_shadow" / "h64l_forward_feature_snapshots.csv"
    cmd = [sys.executable, str(target), "--root", str(root), "--inbox", str(inbox), "--out", str(out), "--max-etf-source-age-days", "365"]
    cp = subprocess.run(cmd, capture_output=True, text=True)
    assert cp.returncode == 0, cp.stdout + cp.stderr
    frame = pd.read_csv(out)
    assert len(frame) == 1
    r = frame.iloc[-1]
    assert bool(r["data_quality_pass"])
    assert r["dxy_ret_20d"] < 0
    assert r["real_yield_change_20d"] < 0
    assert 0 < r["etf_flow_tonnes_3m"] < 500


def test_https_remote_conversion():
    mod = load_module(Path(__file__).parents[1] / "app" / "stage171f_h64l_4h_macro_gdelt_orchestrator.py", "stage171h_orch")
    # Pure URL conversions are represented through a tiny fake git repo.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        subprocess.run(["git", "init", "-q"], cwd=p, check=True)
        subprocess.run(["git", "remote", "add", "origin", "git@github.com:owner/repo.git"], cwd=p, check=True)
        assert mod.remote_to_https(p, "origin") == "https://github.com/owner/repo.git"


def test_config_uses_forward_materializer():
    cfg = json.loads((Path(__file__).parents[1] / "configs" / "stage171f_h64l_4h_macro_gdelt_orchestrator.json").read_text())
    assert cfg["interval_seconds"] == 14400
    assert cfg["feature_dataset"].endswith("h64l_forward_feature_snapshots.csv")
    names = [x["name"] for x in cfg["local_pipeline"]]
    assert "stage171h_forward_feature_materializer" in names
    assert not any("stage64k" in n for n in names)
    assert cfg["gdelt"]["https_fallback"] is True
