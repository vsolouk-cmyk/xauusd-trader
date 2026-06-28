from pathlib import Path
import importlib.util

MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "stage114b_classification_and_macro_event_hotfix.py"
spec = importlib.util.spec_from_file_location("stage114b", MODULE_PATH)
stage114b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage114b)  # type: ignore


def test_canonical_filename_removes_hash_prefix():
    assert stage114b.canonical_filename("148364a82be6__DFII10.csv") == "DFII10.csv"
    assert stage114b.canonical_filename("DFII10.csv") == "DFII10.csv"


def test_classifier_handles_real_unknown_examples():
    cases = {
        "148364a82be6__DFII10.csv": "fred_macro",
        "bfb66e4c29fa__DGS10.csv": "fred_macro",
        "52375ae062fd__T5YIE.csv": "fred_macro",
        "3d2f96e9d8ac__BAMLH0A0HYM2.csv": "fred_macro",
        "bf3353fac304__fred_releases_dates_2009_present.json": "fred_release_calendar",
        "0aa03c0fd636__fut_disagg_txt_2020.zip": "cot_cftc",
        "0bc059a9d2f2__fut_disagg_xls_2025.zip": "cot_cftc",
        "com_disagg_txt_2026.zip": "cot_cftc",
        "cd74f85426f8__amarkets_xauusd_1m.csv": "technical_amarkets",
        "stooq_dx_f_dxy_daily.csv": "dxy_reference",
        "README_XAUUSD_FUNDAMENTAL_EVENT_INBOX.md": "reference_doc",
    }
    for filename, expected_family in cases.items():
        family, bucket, hint, logical = stage114b.classify_path(Path(filename))
        assert family == expected_family, (filename, family, expected_family)


def test_period_to_date():
    assert stage114b.period_to_date("2026", "M05") == "2026-05-01"
    assert stage114b.period_to_date("2026", "Q2") == "2026-04-01"
