from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "app/stage166f_github_gdelt_backfill.py"
WORKFLOW = ROOT / ".github/workflows/xauusd_stage166f_gdelt_backfill.yml"


def test_stage166f_parser_has_retry_flags() -> None:
    spec = importlib.util.spec_from_file_location("stage166f", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    parser = mod.build_arg_parser()
    args = parser.parse_args([
        "fetch", "--output-dir", "x", "--skip-network",
        "--max-retries", "4", "--retry-backoff-seconds", "3",
        "--request-delay-seconds", "2.5",
    ])
    assert args.max_retries == 4
    assert args.request_delay_seconds == 2.5


def test_workflow_yaml_and_four_hour_cron() -> None:
    obj = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(obj, dict)
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "17 */4 * * *" in text
    assert "automation/gdelt-latest" in text
    assert "contents: write" in text
