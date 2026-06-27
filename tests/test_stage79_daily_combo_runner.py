#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from app.stage79_daily_combo_runner import main, parse_key_value_csv


def write_child(path: Path, csv_path: Path | None = None, portfolio: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if csv_path is None:
        body = "print('ok')\n"
    else:
        if portfolio:
            body = f"""
from pathlib import Path
p=Path({str(csv_path)!r})
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text('key,value\\nfeature_date,2026-06-26\\nmode,OBSERVER_ONLY_NO_TRADE\\nany_signal_active,false\\nselected_rule,\\n', encoding='utf-8')
print('portfolio csv written')
"""
        else:
            body = f"""
from pathlib import Path
p=Path({str(csv_path)!r})
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text('key,value\\nthesis,K06_RESILIENT_GOLD_VS_DXY\\nfeature_date,2026-06-26\\nmode,OBSERVER_ONLY_NO_TRADE\\nsignal_active,false\\n', encoding='utf-8')
print('k06 csv written')
"""
    path.write_text("#!/usr/bin/env python3\n" + body, encoding="utf-8")


def main_test() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "app").mkdir()
        (root / "configs").mkdir()
        (root / "data/mt5_bridge").mkdir(parents=True)
        # dummy child scripts
        write_child(root / "app/stage67d6_download_format_aware_rebuild_macro.py")
        write_child(root / "app/stage67e_central_bank_changes_mapper.py")
        write_child(root / "app/stage76e_k06_observer_mode_fix.py", root / "data/mt5_bridge/k06_observer_signal.csv")
        write_child(root / "app/stage78_portfolio_observer_bridge.py", root / "data/mt5_bridge/portfolio_observer_signal.csv", portfolio=True)
        for cfg in [
            "stage67d6_download_format_aware_rebuild_macro.json",
            "stage67e_central_bank_changes_mapper.json",
            "stage76e_k06_observer_mode_fix.json",
            "stage78_portfolio_observer_bridge.json",
        ]:
            (root / "configs" / cfg).write_text("{}", encoding="utf-8")
        combo_cfg = root / "configs/stage79_daily_combo_runner.json"
        combo_cfg.write_text(json.dumps({"timeout_seconds": 20}), encoding="utf-8")
        rc = main(["--root", str(root), "--config", str(combo_cfg), "--out", str(root / "reports/stage79")])
        assert rc == 0
        summary = json.loads((root / "reports/stage79/stage79_daily_combo_runner_summary.json").read_text(encoding="utf-8"))
        assert summary["decision"] == "STAGE79_DAILY_COMBO_COMPLETE_OBSERVER_READY_NO_ORDER"
        assert summary["csv_snapshots"]["k06_observer_signal"]["mode"] == "OBSERVER_ONLY_NO_TRADE"
        assert summary["csv_snapshots"]["portfolio_observer_signal"]["any_signal_active"] == "false"
        parsed = parse_key_value_csv(root / "data/mt5_bridge/k06_observer_signal.csv")
        assert parsed["thesis"] == "K06_RESILIENT_GOLD_VS_DXY"


if __name__ == "__main__":
    main_test()
    print("Stage79 tests passed")
