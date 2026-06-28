import json
from pathlib import Path

from app.stage114_official_event_and_fundamental_normalizer import run, build_parser


def test_stage114_normalizes_fred_and_bls(tmp_path):
    root = tmp_path / "repo"
    inbox = tmp_path / "Downloads" / "xauusd_fundamental_event_inbox"
    fred = inbox / "fred_macro"
    bls = inbox / "events" / "bls"
    fred.mkdir(parents=True)
    bls.mkdir(parents=True)
    (fred / "DFII10.csv").write_text("DATE,DFII10\n2026-01-01,1.80\n2026-01-02,.\n", encoding="utf-8")
    (bls / "bls_core_macro_2017_2026.json").write_text(json.dumps({
        "status": "REQUEST_SUCCEEDED",
        "Results": {"series": [{"seriesID": "CUSR0000SA0", "data": [{"year": "2026", "period": "M01", "periodName": "January", "value": "320.1"}]}]}
    }), encoding="utf-8")

    args = build_parser().parse_args([
        "--root", str(root),
        "--downloads-dir", str(tmp_path / "Downloads"),
        "--manifest", str(root / "missing_manifest.csv"),
    ])
    summary = run(args)
    assert summary["input_files_discovered"] == 2
    outputs = {o["dataset"]: o for o in summary["normalized_outputs"]}
    assert "fred_macro" in outputs
    assert "bls_macro" in outputs
    assert (root / "data" / "fundamental_event_inbox" / "normalized" / "fred_macro_normalized.csv").exists()
    assert (inbox / "README_XAUUSD_FUNDAMENTAL_EVENT_INBOX.md").exists()
