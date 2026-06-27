
#!/usr/bin/env python3
from pathlib import Path
import csv, json, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'app' / 'stage68_signal_frequency_audit.py'

def write_csv(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ['feature_date_utc','gold_sma20_over_50','gold_sma50_over_200','dxy_ret_20d','dxy_sma20_over_50','real_yield_change_20d','vix_change_20d','etf_flow_tonnes_3m','central_bank_demand_tonnes_3m']
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for i in range(1, 121):
            active = i in (10, 11, 80)
            w.writerow({
                'feature_date_utc': f'2020-01-{(i-1)%28+1:02d}' if i < 29 else f'2020-02-{(i-29)%28+1:02d}',
                'gold_sma20_over_50': 1 if active else -1,
                'gold_sma50_over_200': 1 if active else -1,
                'dxy_ret_20d': -0.01 if active else 0.02,
                'dxy_sma20_over_50': -0.01 if active else 0.01,
                'real_yield_change_20d': -0.01 if active else 0.02,
                'vix_change_20d': 1,
                'etf_flow_tonnes_3m': 1,
                'central_bank_demand_tonnes_3m': 1,
            })

def main():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root/'app').mkdir(); (root/'configs').mkdir(); (root/'reports').mkdir(parents=True, exist_ok=True)
        # Use script from package path directly, but root has data/config.
        macro = root/'data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv'
        write_csv(macro)
        cfg = {'macro_dataset': 'data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv'}
        (root/'configs/stage68_signal_frequency_audit.json').write_text(json.dumps(cfg), encoding='utf-8')
        out = root/'reports/stage68_signal_frequency_audit'
        r = subprocess.run([sys.executable, str(SCRIPT), '--root', str(root), '--config', 'configs/stage68_signal_frequency_audit.json', '--out', str(out)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr + r.stdout
        summary = json.loads((out/'stage68_signal_frequency_audit_summary.json').read_text(encoding='utf-8'))
        assert summary['status'] == 'STAGE68_COMPLETE_NO_PROMOTION'
        assert summary['rule_metrics']['h64l_v2']['active_days'] == 3
        assert summary['rule_metrics']['h64l_v2']['contiguous_episode_count'] == 2
    print('Stage68 tests passed')

if __name__ == '__main__':
    main()
