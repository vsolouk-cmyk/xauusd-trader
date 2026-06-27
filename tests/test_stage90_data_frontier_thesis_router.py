
#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path


def write_csv(path: Path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # copy app/config into temp project structure
        src_root = Path(__file__).resolve().parents[1]
        (root/'app').mkdir()
        (root/'configs').mkdir()
        (root/'app'/'stage90_data_frontier_thesis_router.py').write_text((src_root/'app'/'stage90_data_frontier_thesis_router.py').read_text(), encoding='utf-8')
        (root/'configs'/'stage90_data_frontier_thesis_router.json').write_text((src_root/'configs'/'stage90_data_frontier_thesis_router.json').read_text(), encoding='utf-8')

        macro = root/'data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv'
        write_csv(macro, ['feature_date_utc','gold_close','dxy','real_yield','etf_flow_tonnes_3m','central_bank_demand_tonnes_3m','vix'], [
            ['2020-01-01','1500','100','1.0','1','1','15'],
            ['2020-01-02','1510','99','0.9','2','2','16'],
        ])
        (root/'reports/stage88_daily_unified_observer_combo').mkdir(parents=True)
        (root/'reports/stage88_daily_unified_observer_combo/stage88_daily_unified_observer_combo_summary.json').write_text(json.dumps({'decision':'OK','disposition':'DAILY_UNIFIED_COMBO_OBSERVER_READY_NO_ORDER'}), encoding='utf-8')
        (root/'reports/stage89_residual_regime_thesis_discovery').mkdir(parents=True)
        (root/'reports/stage89_residual_regime_thesis_discovery/stage89_residual_regime_thesis_discovery_summary.json').write_text(json.dumps({'decision':'NO_RESIDUAL_THESIS_SHORTLIST_NO_ORDER','disposition':'NO_RESIDUAL_THESIS_SHORTLIST','current_union_active_days': 100}), encoding='utf-8')

        # SQLite intraday inventory strong enough to select intraday.
        dbp = root/'data/local/bars.db'
        dbp.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(str(dbp))
        cur = con.cursor()
        cur.execute('CREATE TABLE bars (source TEXT, symbol TEXT, timeframe TEXT, utc_time TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL, spread REAL)')
        rows = [('amarkets','XAUUSD','m1',f'2024-01-01T00:{i%60:02d}:00Z',1,2,0,1.5,100,20) for i in range(12000)]
        cur.executemany('INSERT INTO bars VALUES (?,?,?,?,?,?,?,?,?,?)', rows)
        con.commit(); con.close()

        out = root/'reports/stage90_data_frontier_thesis_router'
        result = subprocess.run([
            sys.executable, str(root/'app/stage90_data_frontier_thesis_router.py'),
            '--root', str(root),
            '--config', 'configs/stage90_data_frontier_thesis_router.json',
            '--out', str(out),
        ], text=True, capture_output=True)
        assert result.returncode == 0, result.stderr + result.stdout
        summary = json.loads((out/'stage90_data_frontier_thesis_router_summary.json').read_text(encoding='utf-8'))
        assert summary['status'] == 'STAGE90_COMPLETE_NO_PROMOTION'
        assert summary['selected_frontier'] in {'INTRADAY_SESSION','COT_POSITIONING','EVENT_SURPRISE','FLOW_REFINEMENT'}
        assert (out/'stage90_frontier_readiness.csv').exists()
        assert (out/'stage90_data_requirements.csv').exists()
        assert (out/'stage90_thesis_queue.csv').exists()
        assert summary['hard_blocks']
    print('Stage90 tests passed')


if __name__ == '__main__':
    main()
