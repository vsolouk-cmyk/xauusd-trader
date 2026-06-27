from pathlib import Path
import csv
import json
import subprocess
import sys
import tempfile


def write_macro(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=[
            'feature_date_utc','gold_close','gold_sma20_over_50','dxy_ret_20d','real_yield_change_20d','vix_change_20d','dxy_sma20_over_50'
        ])
        w.writeheader()
        w.writerow({'feature_date_utc':'2026-06-25','gold_close':'4000','gold_sma20_over_50':'-1','dxy_ret_20d':'0.02','real_yield_change_20d':'0.1','vix_change_20d':'1','dxy_sma20_over_50':'0.1'})
        w.writerow({'feature_date_utc':'2026-06-26','gold_close':'4010','gold_sma20_over_50':'0.1','dxy_ret_20d':'0.02','real_yield_change_20d':'-0.1','vix_change_20d':'1','dxy_sma20_over_50':'-0.1'})


def main():
    repo = Path(__file__).resolve().parents[1]
    ea_text = (repo / 'mt5' / 'Portfolio_ObserverOnly_EA.mq5').read_text(encoding='utf-8')
    for token in ['OrderSend','CTrade','Buy(','Sell(','PositionOpen']:
        assert token not in ea_text, f'banned token present: {token}'

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        write_macro(root / 'data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv')
        lock_dir = root / 'reports/stage77b_corrected_portfolio_candidate_selection_historical_asof'
        lock_dir.mkdir(parents=True)
        (lock_dir / 'stage77b_corrected_portfolio_candidate_selection_historical_asof_summary.json').write_text(
            json.dumps({'disposition':'PORTFOLIO_READY_WITH_K06_PLUS_COMPLEMENTS'}), encoding='utf-8')
        (root / 'configs').mkdir()
        cfg_src = repo / 'configs' / 'stage78_portfolio_observer_bridge.json'
        cfg_dst = root / 'configs' / 'stage78_portfolio_observer_bridge.json'
        cfg_dst.write_text(cfg_src.read_text(encoding='utf-8'), encoding='utf-8')
        cmd = [sys.executable, str(repo / 'app' / 'stage78_portfolio_observer_bridge.py'), '--root', str(root), '--config', 'configs/stage78_portfolio_observer_bridge.json', '--out', 'reports/stage78']
        subprocess.check_call(cmd)
        summary = json.loads((root / 'reports/stage78/stage78_portfolio_observer_bridge_summary.json').read_text())
        assert summary['status'] == 'STAGE78_COMPLETE_NO_PROMOTION'
        assert summary['bridge_csv']['mode'] == 'OBSERVER_ONLY_NO_TRADE'
        bridge = (root / 'data/mt5_bridge/portfolio_observer_signal.csv').read_text(encoding='utf-8')
        assert 'mode,OBSERVER_ONLY_NO_TRADE' in bridge
        assert 'K06_RESILIENT_GOLD_VS_DXY_H120_signal_active,true' in bridge
    print('Stage78 tests passed')


if __name__ == '__main__':
    main()
