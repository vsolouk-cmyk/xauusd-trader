from pathlib import Path
import importlib.util
import sys

import pandas as pd

MODULE = Path(__file__).resolve().parents[1] / "app" / "stage163_macro_supported_side_discovery.py"
spec = importlib.util.spec_from_file_location("stage163_macro_supported_side_discovery", MODULE)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def test_mt5_tsv_loader_combines_date_and_time(tmp_path):
    p = tmp_path / "mt5.tsv"
    p.write_text(
        "<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>\n"
        "2026.07.08\t14:00:00\t4052.91\t4056.85\t4050.32\t4053.83\t465\t0\t34\n"
        "2026.07.08\t14:05:00\t4053.85\t4054.24\t4048.85\t4049.19\t427\t0\t33\n",
        encoding="utf-8",
    )
    df = mod.load_bars(p, timestamp_shift_hours=-3)
    assert len(df) == 2
    assert str(df["utc_time"].iloc[0]) == "2026-07-08 11:00:00+00:00"
    assert str(df["utc_time"].iloc[1]) == "2026-07-08 11:05:00+00:00"
    assert df.attrs["loader_selected_sep"] == "\t"
    assert df.attrs["loader_parse_mode"] == "split_date_time_mt5_tsv"
    assert df.attrs["loader_raw_row_count"] == 2


def test_normalized_csv_loader_still_uses_time_utc(tmp_path):
    p = tmp_path / "norm.csv"
    p.write_text(
        "time_utc,open,high,low,close,tick_volume\n"
        "2026-07-08T11:00:00Z,1,2,0.5,1.5,10\n"
        "2026-07-08T11:05:00Z,1.5,2.5,1,2,11\n",
        encoding="utf-8",
    )
    df = mod.load_bars(p, timestamp_shift_hours=0)
    assert len(df) == 2
    assert str(df["utc_time"].iloc[-1]) == "2026-07-08 11:05:00+00:00"
    assert df.attrs["loader_selected_sep"] == ","
    assert df.attrs["loader_parse_mode"] == "explicit_datetime_column"
