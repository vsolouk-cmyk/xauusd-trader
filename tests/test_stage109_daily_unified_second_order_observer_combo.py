from pathlib import Path
import csv
import importlib.util
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("stage109", ROOT / "app/stage109_daily_unified_second_order_observer_combo.py")
stage109 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stage109)


def test_parse_wide_bridge_csv(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    p = tmp_path / "unified_observer_signal.csv"
    header = ["schema_version", "stage", "mode", "execution_allowed", "order_authorized", "broker_connection_allowed", "rule_count", "C96_07_active", "S105_03_active"]
    values = ["stage108_unified_observer_second_order_v1", "Stage108_UNIFIED_OBSERVER_SECOND_ORDER_EXPANSION", "OBSERVER_ONLY_NO_TRADE", "false", "false", "false", "7", "false", "false"]
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerow(values)
    snap = stage109.parse_bridge_csv(p)
    assert snap["schema_version"] == "stage108_unified_observer_second_order_v1"
    assert snap["mode"] == "OBSERVER_ONLY_NO_TRADE"
    assert snap["C96_07_active"] == "false"
    assert snap["S105_03_active"] == "false"
    assert stage109.validate_snapshot(snap, stage109.default_config(tmp_path)) == []


def test_parse_key_value_bridge_csv(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    p = tmp_path / "unified_observer_signal.csv"
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["schema_version", "stage108_unified_observer_second_order_v1"])
        w.writerow(["stage", "Stage108_UNIFIED_OBSERVER_SECOND_ORDER_EXPANSION"])
        w.writerow(["mode", "OBSERVER_ONLY_NO_TRADE"])
        w.writerow(["execution_allowed", "false"])
        w.writerow(["order_authorized", "false"])
        w.writerow(["broker_connection_allowed", "false"])
        w.writerow(["rule_count", "7"])
        w.writerow(["C96_07_active", "false"])
        w.writerow(["S105_03_active", "false"])
    snap = stage109.parse_bridge_csv(p)
    assert snap["schema_version"] == "stage108_unified_observer_second_order_v1"
    assert stage109.validate_snapshot(snap, stage109.default_config(tmp_path)) == []


def test_main_with_stub_stage108(tmp_path):
    import shutil
    if tmp_path.exists():
        shutil.rmtree(tmp_path)
    root = tmp_path / "repo"
    (root / "app").mkdir(parents=True)
    (root / "configs").mkdir()
    (root / "data/mt5_bridge").mkdir(parents=True)
    # Stub stage108 writes the real wide bridge CSV shape.
    (root / "app/stage108_unified_observer_second_order_expansion.py").write_text(
        """
import argparse, csv, pathlib, json
p=argparse.ArgumentParser(); p.add_argument('--root'); p.add_argument('--config'); p.add_argument('--out'); a=p.parse_args()
root=pathlib.Path(a.root); out=pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
path=root/'data/mt5_bridge/unified_observer_signal.csv'; path.parent.mkdir(parents=True, exist_ok=True)
with path.open('w', newline='') as f:
    w=csv.writer(f); w.writerow(['schema_version','stage','mode','execution_allowed','order_authorized','broker_connection_allowed','rule_count','C96_07_active','S105_03_active']); w.writerow(['stage108_unified_observer_second_order_v1','Stage108_UNIFIED_OBSERVER_SECOND_ORDER_EXPANSION','OBSERVER_ONLY_NO_TRADE','false','false','false','7','false','false'])
print(json.dumps({'status':'STAGE108_COMPLETE_NO_PROMOTION','issues':[]}))
""",
        encoding="utf-8",
    )
    cfg = stage109.default_config(root)
    for k in ["macro_stage", "central_bank_stage", "cot_stage"]:
        cfg[k]["enabled"] = False
    cfg["mt5_files_path"] = str(root / "mt5files")
    cfgp = root / "configs/stage109_daily_unified_second_order_observer_combo.json"
    cfgp.write_text(json.dumps(cfg), encoding="utf-8")
    rc = stage109.main(["--root", str(root), "--config", str(cfgp), "--out", str(root/"reports/stage109"), "--skip-refresh", "--copy-to-mt5-files"])
    assert rc == 0
    summ = json.loads((root/"reports/stage109/stage109_daily_unified_second_order_observer_combo_summary.json").read_text())
    assert summ["status"] == "STAGE109_COMPLETE_NO_PROMOTION"
    assert summ["csv_snapshot"]["schema_version"] == "stage108_unified_observer_second_order_v1"
    assert summ["csv_copy"]["status"] == "COPIED"


if __name__ == "__main__":
    test_parse_wide_bridge_csv(Path('/tmp/stage109_test_wide'))
    test_parse_key_value_bridge_csv(Path('/tmp/stage109_test_kv'))
    test_main_with_stub_stage108(Path('/tmp/stage109_test_main'))
    print('Stage109 tests passed')
