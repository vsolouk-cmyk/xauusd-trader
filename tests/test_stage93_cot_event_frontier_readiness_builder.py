import csv
import json
import subprocess
import sys
from pathlib import Path


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_stage93_builder(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir(parents=True, exist_ok=True)
    (root / "configs").mkdir()
    cfg_src = Path(__file__).resolve().parents[1] / "configs" / "stage93_cot_event_frontier_readiness_builder.json"
    cfg = json.loads(cfg_src.read_text())
    cfg["scan_roots"] = ["data/exogenous", "data/events"]
    cfg["output_templates_dir"] = "data/frontier_templates"
    cfg_path = root / "configs" / cfg_src.name
    write(cfg_path, json.dumps(cfg))

    # Reference reports are optional but should not break the builder.
    write(root / "reports/stage89_residual_regime_thesis_discovery/stage89_residual_regime_thesis_discovery_summary.json", json.dumps({"decision": "NO_RESIDUAL_THESIS_SHORTLIST_NO_ORDER", "disposition": "NO_RESIDUAL_THESIS_SHORTLIST"}))

    # COT-like file that is not fully normalized should be inventoried but not ready.
    write(root / "data/exogenous/gold_cot_raw.csv", "Market and Exchange Names,As of Date in Form YYYY-MM-DD,Open Interest\nGOLD - COMMODITY EXCHANGE INC.,2026-06-23,1000\n")
    # Event normalized file with insufficient rows should not be ready.
    write(root / "data/events/macro_event_surprise_normalized.csv", "event_datetime_utc,available_after_utc,country,event_type,event_name,actual,consensus,previous,surprise\n2026-01-01T13:30:00Z,2026-01-01T13:31:00Z,US,NFP,NFP,100,90,80,10\n")

    script = Path(__file__).resolve().parents[1] / "app" / "stage93_cot_event_frontier_readiness_builder.py"
    out = root / "reports/stage93"
    subprocess.check_call([sys.executable, str(script), "--root", str(root), "--config", str(cfg_path), "--out", str(out)])
    summary = json.loads((out / "stage93_cot_event_frontier_readiness_builder_summary.json").read_text())
    assert summary["status"] == "STAGE93_COMPLETE_NO_PROMOTION"
    assert summary["decision"] == "STAGE93_EXTERNAL_FRONTIER_DATA_NOT_READY_NO_ORDER"
    assert (root / "data/frontier_templates/stage93_cot_positioning_normalized_template.csv").exists()
    assert (root / "data/frontier_templates/stage93_event_surprise_normalized_template.csv").exists()


if __name__ == "__main__":
    test_stage93_builder(Path("/tmp/stage93_test"))
    print("Stage93 tests passed")
