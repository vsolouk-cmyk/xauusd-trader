from pathlib import Path
import csv
import json
import subprocess
import sys
import tempfile


def write_macro(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['feature_date_utc','gold_close','gold_sma20_over_50','dxy_ret_20d','real_yield_change_20d'])
        w.writeheader()
        w.writerow({'feature_date_utc':'2026-06-26','gold_close':'4010','gold_sma20_over_50':'-0.1','dxy_ret_20d':'0.02','real_yield_change_20d':'0.1'})


def main():
    repo = Path(__file__).resolve().parents[1]
    ea_text = (repo / 'mt5' / 'K06_ObserverOnly_EA.mq5').read_text(encoding='utf-8')
    for token in ['OrderSend','CTrade','Buy(','Sell(','PositionOpen']:
        assert token not in ea_text, f'banned token present: {token}'
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        write_macro(root / 'data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv')
        (root / 'configs').mkdir()
        cfg_src = repo / 'configs' / 'stage76e_k06_observer_mode_fix.json'
        cfg_dst = root / 'configs' / 'stage76e_k06_observer_mode_fix.json'
        cfg_dst.write_text(cfg_src.read_text(encoding='utf-8'), encoding='utf-8')
        cmd = [sys.executable, str(repo / 'app' / 'stage76e_k06_observer_mode_fix.py'), '--root', str(root), '--config', 'configs/stage76e_k06_observer_mode_fix.json', '--out', 'reports/stage76e']
        subprocess.check_call(cmd)
        bridge = (root / 'data/mt5_bridge/k06_observer_signal.csv').read_text(encoding='utf-8')
        assert 'mode,OBSERVER_ONLY_NO_TRADE' in bridge
        assert 'ea_mode,OBSERVER_ONLY_NO_TRADE' in bridge
    print('Stage76E tests passed')


if __name__ == '__main__':
    main()
