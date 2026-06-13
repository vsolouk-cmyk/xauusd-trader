from pathlib import Path
import subprocess
import tempfile
import pandas as pd

OUT_DIR = Path("data/exogenous")
OUT_DIR.mkdir(parents=True, exist_ok=True)

SERIES = {
    # Dollar strength proxy, not ICE DXY. FRED broad USD index.
    "dxy.csv": "DTWEXBGS",

    # 10-year nominal US Treasury yield
    "us10y.csv": "DGS10",

    # 10-year real yield / TIPS constant maturity
    "real_yield.csv": "DFII10",

    # CBOE VIX
    "vix.csv": "VIXCLS",

    # S&P 500 index
    "spx.csv": "SP500",

    # WTI crude oil
    "oil.csv": "DCOILWTICO",
}

START_DATE = "2022-05-01"


def download_with_curl(url: str, dest: Path) -> None:
    cmd = [
        "curl",
        "-L",
        "--retry", "3",
        "--retry-delay", "2",
        "--connect-timeout", "20",
        "--max-time", "90",
        "-o", str(dest),
        url,
    ]
    subprocess.run(cmd, check=True)


def normalize_fred_csv(raw_path: Path, series_id: str, out_path: Path) -> int:
    df = pd.read_csv(raw_path)

    # FRED CSV exports may use either DATE or observation_date depending on endpoint/format.
    time_col = None
    for candidate in ("DATE", "observation_date", "date", "timestamp"):
        if candidate in df.columns:
            time_col = candidate
            break

    if time_col is None or series_id not in df.columns:
        raise RuntimeError(
            f"Unexpected FRED format for {series_id}: columns={list(df.columns)}. "
            "Expected a date column like DATE/observation_date and the series column."
        )

    out = df.rename(columns={time_col: "timestamp", series_id: "close"})[["timestamp", "close"]].copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    out["close"] = pd.to_numeric(out["close"].replace(".", pd.NA), errors="coerce")
    out = out.dropna(subset=["timestamp", "close"])
    out = out[out["timestamp"] >= pd.Timestamp(START_DATE, tz="UTC")]
    out["timestamp"] = out["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    out.to_csv(out_path, index=False)
    return len(out)


for filename, series_id in SERIES.items():
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    print(f"Downloading {series_id} -> {filename}")

    with tempfile.TemporaryDirectory() as td:
        raw_path = Path(td) / f"{series_id}.csv"
        download_with_curl(url, raw_path)
        rows = normalize_fred_csv(raw_path, series_id, OUT_DIR / filename)

    print(f"Saved {OUT_DIR / filename} rows={rows}")

print("Done.")
