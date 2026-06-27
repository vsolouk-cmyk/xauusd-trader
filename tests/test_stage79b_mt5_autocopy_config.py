#!/usr/bin/env python3
from pathlib import Path
import json

EXPECTED = "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files/"


def main():
    cfg_path = Path("configs/stage79_daily_combo_runner.json")
    assert cfg_path.exists(), f"missing config: {cfg_path}"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert cfg.get("copy_to_mt5_files") is True
    assert cfg.get("mt5_files_dir") == EXPECTED
    for key in ["run_stage67d6", "run_stage67e", "run_stage76e", "run_stage78"]:
        assert cfg.get(key) is True, f"{key} must remain enabled"
    print("Stage79B MT5 auto-copy config test passed")


if __name__ == "__main__":
    main()
