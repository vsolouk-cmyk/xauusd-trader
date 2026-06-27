from pathlib import Path
import csv
import json
import subprocess
import sys
import tempfile


def write_macro(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        'feature_date_utc','gold_close','gold_sma20_over_50','dxy_ret_20d','real_yield_change_20d',
        'vix_change_20d','dxy_sma20_over_50','dxy','real_yield','dxy_ret_120d','real_yield_change_120d'
    ]
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for i in range(130):
            row = {
                'feature_date_utc': f'2026-01-{(i % 28) + 1:02d}',
                'gold_close': str(3000 + i),
                'gold_sma20_over_50': '-0.05' if i == 129 else '0.1',
                'dxy_ret_20d': '0.02',
                'real_yield_change_20d': '0.1',
                'vix_change_20d': '2.0',
                'dxy_sma20_over_50': '0.01',
                'dxy': str(100 + i / 1000),
                'real_yield': str(1.0 + i / 1000),
                'dxy_ret_120d': '-0.02' if i == 129 else '',
                'real_yield_change_120d': '-0.3' if i == 129 else '',
            }
            w.writerow(row)


def main():
    repo = Path(__file__).resolve().parents[1]
    ea_text = (repo / 'mt5' / 'Portfolio_ObserverOnly_EA.mq5').read_text(encoding='utf-8')
    for token in ['OrderSend', 'CTrade', 'Buy(', 'Sell(', 'PositionOpen']:
        assert token not in ea_text, f'banned token present: {token}'
    assert 'S83_14_active' in ea_text
    assert 'S83_13_active' in ea_text

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        write_macro(root / 'data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv')
        lock_dir = root / 'reports/stage85_portfolio_increment_review'
        lock_dir.mkdir(parents=True)
        (lock_dir / 'stage85_portfolio_increment_review_summary.json').write_text(
            json.dumps({'disposition': 'PORTFOLIO_INCREMENT_SELECTED_FOR_STAGE86_OBSERVER_EXPANSION'}), encoding='utf-8')
        (root / 'configs').mkdir()
        cfg_src = repo / 'configs' / 'stage86_expanded_portfolio_observer_bridge.json'
        cfg_dst = root / 'configs' / 'stage86_expanded_portfolio_observer_bridge.json'
        cfg_dst.write_text(cfg_src.read_text(encoding='utf-8'), encoding='utf-8')
        cmd = [sys.executable, str(repo / 'app' / 'stage86_expanded_portfolio_observer_bridge.py'), '--root', str(root), '--config', 'configs/stage86_expanded_portfolio_observer_bridge.json', '--out', 'reports/stage86']
        subprocess.check_call(cmd)
        summary = json.loads((root / 'reports/stage86/stage86_expanded_portfolio_observer_bridge_summary.json').read_text())
        assert summary['status'] == 'STAGE86_COMPLETE_NO_PROMOTION'
        assert summary['lock_pass_count'] == 1
        assert len(summary['expanded_portfolio_rule_ids']) == 5
        assert 'S83_14_REALYIELD_120D_DOWN_GOLD_NOT_TRENDING_H120' in summary['expanded_portfolio_rule_ids']
        bridge = (root / 'data/mt5_bridge/portfolio_observer_signal.csv').read_text(encoding='utf-8')
        assert 'schema_version,stage86_expanded_portfolio_observer_v1' in bridge
        assert 'S83_14_active,true' in bridge
        assert 'S83_13_active,true' in bridge
        assert 'mode,OBSERVER_ONLY_NO_TRADE' in bridge
    print('Stage86 tests passed')


if __name__ == '__main__':
    main()
